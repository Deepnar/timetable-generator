"""Redis Integration tests: generation-conflict locking, response caching,
and auth rate limiting.

The suite has no Redis, so every test either (a) monkeypatches
``app.services.redis_client`` with a dict-backed fake, or (b) verifies the
graceful-degradation path (Redis off → lock/cache/rate-limit all no-op and the
request path still works). ``REDIS_ENABLED`` is forced off in conftest; tests
that need a live client substitute ``redis_client._get_client``.
"""
import time

from app.tests.test_runner import suite, test
from app.services import redis_client as rc


class _FakeRedis:
    """Minimal in-memory stand-in for the subset of Redis commands the
    client issues (get/set/delete/scan_iter/incr/expire/eval). Tracks TTLs so
    expiry semantics hold. Not thread-safe; the suite runs sequentially.
    """

    def __init__(self):
        self._data = {}      # key -> (value, expires_at)
        self._counters = {}  # key -> int, for INCR-only rate-limit keys

    def _alive(self, key):
        entry = self._data.get(key)
        if entry is None:
            return False
        value, expires_at = entry
        if expires_at is not None and time.time() > expires_at:
            self._data.pop(key, None)
            return False
        return True

    def get(self, key):
        return self._data[key][0] if self._alive(key) else None

    def set(self, key, value, nx=False, ex=None, px=None):
        if nx and self._alive(key):
            return False
        expires = None
        if ex is not None:
            expires = time.time() + ex
        elif px is not None:
            expires = time.time() + px / 1000.0
        self._data[key] = (value, expires)
        return True

    def delete(self, *keys):
        removed = 0
        for k in keys:
            if self._data.pop(k, None) is not None:
                removed += 1
        return removed

    def scan_iter(self, match=None, **_):
        prefix = match[:-1] if match and match.endswith("*") else (match or "")
        return (k for k in list(self._data) if k.startswith(prefix))

    def incr(self, key):
        self._counters[key] = self._counters.get(key, 0) + 1
        return self._counters[key]

    def expire(self, key, seconds):
        if key in self._counters:
            if seconds <= 0:
                self._counters.pop(key, None)
            else:
                self._counters[key + ":expires"] = time.time() + seconds
        return 1

    def eval(self, script, numkeys, *args):
        key, token = args[0], args[1]
        if self._alive(key) and self._data[key][0] == token:
            self._data.pop(key, None)
            return 1
        return 0


def _fake_redis():
    """Point the module's client accessor at a fresh fake and return it."""
    fake = _FakeRedis()
    real = rc._get_client
    rc._get_client = lambda: fake
    return fake, real


def _restore_get_client(real):
    rc._get_client = real


@suite("Redis Integration — generation-conflict locking")
def _redis_locking(s):
    from app.engine.scheduler import Scheduler, GenerationLockError
    from app.models.generation import (AlgorithmType, TimetableGeneration,
                                       GenerationStatus)

    def _make_run(ids):
        from app.tests.test_runner import TestingSessionLocal
        db = TestingSessionLocal()
        try:
            gen = Scheduler(db).create_generation(
                profile_id=ids["profile"], timetable_type="CLASS",
                academic_year="2025-26", semester=3,
                instances_requested=1, algorithm=AlgorithmType.GREEDY,
                triggered_by=ids["admin"],
            )
            db.commit()
            return gen.id
        finally:
            db.close()

    @test("a busy lock marks the run FAILED and raises GenerationLockError")
    def t_busy_lock(client):
        from app.tests.test_runner import seed_minimal, TestingSessionLocal
        ids = seed_minimal()
        run_id = _make_run(ids)

        real_acquire = rc.acquire_lock
        rc.acquire_lock = lambda key, timeout=600: False
        try:
            db = TestingSessionLocal()
            try:
                raised = False
                try:
                    Scheduler(db).solve_generation(run_id)
                except GenerationLockError:
                    raised = True
                assert raised, "busy lock must raise GenerationLockError"
                row = db.get(TimetableGeneration, run_id)
                assert row.generation_status == GenerationStatus.FAILED
                assert "already running" in row.error_log
            finally:
                db.close()
        finally:
            rc.acquire_lock = real_acquire

    @test("a downed Redis degrades to an unlocked solve (COMPLETED)")
    def t_redis_down(client):
        from app.tests.test_runner import seed_minimal, TestingSessionLocal
        ids = seed_minimal()
        run_id = _make_run(ids)

        real_acquire = rc.acquire_lock
        rc.acquire_lock = lambda key, timeout=600: None
        try:
            db = TestingSessionLocal()
            try:
                Scheduler(db).solve_generation(run_id)
                row = db.get(TimetableGeneration, run_id)
                assert row.generation_status == GenerationStatus.COMPLETED, (
                    row.error_log or row.generation_status)
                assert row.instances_produced == 1
            finally:
                db.close()
        finally:
            rc.acquire_lock = real_acquire

    @test("an acquired lock is released after the solve")
    def t_lock_released(client):
        from app.tests.test_runner import seed_minimal, TestingSessionLocal
        ids = seed_minimal()
        run_id = _make_run(ids)

        released = []
        real_acquire = rc.acquire_lock
        real_release = rc.release_lock
        rc.acquire_lock = lambda key, timeout=600: rc.Lock(key=key, token="t")
        rc.release_lock = lambda lock: released.append(lock)
        try:
            db = TestingSessionLocal()
            try:
                Scheduler(db).solve_generation(run_id)
                assert len(released) == 1, "lock must be released after the solve"
                assert released[0].key.startswith("timetable:lock:generate:")
            finally:
                db.close()
        finally:
            rc.acquire_lock = real_acquire
            rc.release_lock = real_release

    @test("acquire/release round-trips against the fake Redis")
    def t_acquire_release(client):
        fake, real = _fake_redis()
        try:
            lock = rc.acquire_lock("timetable:lock:test", timeout=5)
            assert lock is not None, "first acquire must succeed"
            assert rc.acquire_lock("timetable:lock:test") is False, \
                "a second acquire must be refused while held"
            rc.release_lock(lock)
            assert rc.acquire_lock("timetable:lock:test") is not None, \
                "release must free the lock for the next caller"
        finally:
            _restore_get_client(real)

    @test("lock APIs degrade to no-ops with Redis disabled")
    def t_degraded(client):
        # conftest forces REDIS_ENABLED=False, so the real _get_client is None.
        assert rc.acquire_lock("timetable:lock:x") is None
        assert rc.cache_get("timetable:cache:x") is None
        assert rc.check_rate_limit("login", "1.2.3.4", 5, 60) is None
        rc.release_lock(False)  # must not raise
        rc.release_lock(None)

    @test("POST /generate returns 409 when the resources are locked")
    def t_http_409(client):
        from app.tests.test_runner import seed_minimal, login_token, auth_headers
        ids = seed_minimal()
        headers = auth_headers(login_token(client))

        real_acquire = rc.acquire_lock
        rc.acquire_lock = lambda key, timeout=600: False
        try:
            r = client.post("/generate/", headers=headers, json={
                "profile_id": ids["profile"], "academic_year": "2025-26",
                "semester": 3, "timetable_type": "CLASS",
                "instances_requested": 1, "algorithm": "GREEDY",
            })
            assert r.status_code == 409, r.text
            assert "already running" in r.json()["detail"]
        finally:
            rc.acquire_lock = real_acquire

    return [t_busy_lock, t_redis_down, t_lock_released, t_acquire_release,
            t_degraded, t_http_409]


@suite("Redis Integration — response caching")
def _redis_caching(s):
    from app.tests.test_runner import seed_minimal, login_token, auth_headers

    @test("cache_get/set_json and prefix delete round-trip")
    def t_cache_roundtrip(client):
        fake, real = _fake_redis()
        try:
            assert rc.cache_get("k") is None
            rc.cache_set_json("k", [{"a": 1}])
            assert rc.cache_get_json("k") == [{"a": 1}]
            rc.cache_set_json("prefix:1", 1)
            rc.cache_set_json("prefix:2", 2)
            rc.cache_delete_prefix("prefix:")
            assert rc.cache_get_json("prefix:1") is None
            assert rc.cache_get_json("prefix:2") is None
            assert rc.cache_get_json("k") == [{"a": 1}], \
                "a prefix delete must not touch other keys"
        finally:
            _restore_get_client(real)

    @test("rooms list is served from cache and busted on write")
    def t_rooms_cache(client):
        ids = seed_minimal()
        headers = auth_headers(login_token(client))
        fake, real = _fake_redis()
        try:
            r1 = client.get("/rooms/", headers=headers)
            assert r1.status_code == 200, r1.text
            assert len(r1.json()) == 2, r1.text

            # Insert a third room straight into the DB, bypassing the router so
            # the cache is NOT busted: the next GET must still be the stale 2.
            from app.tests.test_runner import TestingSessionLocal
            from app.models.rooms import Room, RoomType
            db = TestingSessionLocal()
            try:
                db.add(Room(name="R3", room_code="R3",
                            room_type=RoomType.CLASSROOM, capacity=50,
                            building="A"))
                db.commit()
            finally:
                db.close()
            r2 = client.get("/rooms/", headers=headers)
            assert r2.status_code == 200, r2.text
            assert len(r2.json()) == 2, "cache must serve the stale list"

            # A write (POST) busts the cache, so the next GET reflects the DB
            # (seed's 2 rooms + the direct-insert R3 + the new R4).
            r3 = client.post("/rooms/", headers=headers, json={
                "name": "R4", "room_code": "R4", "room_type": "CLASSROOM",
                "capacity": 50, "building": "A",
            })
            assert r3.status_code == 201, r3.text
            r4 = client.get("/rooms/", headers=headers)
            assert r4.status_code == 200, r4.text
            assert len(r4.json()) == 4, "write must bust the cache"
        finally:
            _restore_get_client(real)

    @test("settings GET is cached and busted on PUT")
    def t_settings_cache(client):
        seed_minimal()
        headers = auth_headers(login_token(client))
        fake, real = _fake_redis()
        try:
            r1 = client.get("/settings/", headers=headers)
            assert r1.status_code == 200, r1.text

            # Flip the flag behind the router's back: the cached GET must not
            # see the change.
            from app.tests.test_runner import TestingSessionLocal
            from app.services.settings_service import get_settings
            db = TestingSessionLocal()
            try:
                row = get_settings(db)
                row.enable_lab_batches = not row.enable_lab_batches
                db.commit()
            finally:
                db.close()
            r2 = client.get("/settings/", headers=headers)
            assert r2.json() == r1.json(), "settings must be served from cache"

            # A PUT busts the cache and the next GET reflects the new state.
            body = r1.json()
            body["enable_lab_batches"] = not body["enable_lab_batches"]
            r3 = client.put("/settings/", headers=headers, json=body)
            assert r3.status_code == 200, r3.text
            r4 = client.get("/settings/", headers=headers)
            assert r4.json()["enable_lab_batches"] == body["enable_lab_batches"]
        finally:
            _restore_get_client(real)

    return [t_cache_roundtrip, t_rooms_cache, t_settings_cache]


@suite("Redis Integration — auth rate limiting")
def _redis_ratelimit(s):
    from app.tests.test_runner import seed_minimal

    @test("fixed-window counter blocks after the limit and resets per IP")
    def t_rate_limit_unit(client):
        fake, real = _fake_redis()
        try:
            for _ in range(5):
                assert rc.check_rate_limit("login", "1.2.3.4", 5, 60) is True
            assert rc.check_rate_limit("login", "1.2.3.4", 5, 60) is False, \
                "the 6th request in the window must be refused"
            assert rc.check_rate_limit("login", "1.2.3.5", 5, 60) is True, \
                "a different IP shares no counter"
            assert rc.check_rate_limit("register", "1.2.3.4", 5, 60) is True, \
                "a different scope shares no counter"
        finally:
            _restore_get_client(real)

    @test("POST /auth/login returns 429 once the per-IP limit is hit")
    def t_login_429(client):
        seed_minimal()
        fake, real = _fake_redis()
        try:
            for _ in range(5):
                r = client.post("/auth/login", json={
                    "email": "admin@example.com", "password": "wrong",
                })
                assert r.status_code == 403, r.text
            r = client.post("/auth/login", json={
                "email": "admin@example.com", "password": "admin123",
            })
            assert r.status_code == 429, r.text
            assert "Too many requests" in r.json()["detail"]
        finally:
            _restore_get_client(real)

    return [t_rate_limit_unit, t_login_429]
