"""Optional Redis client with graceful degradation.

Redis powers three opt-in features — generation-conflict locking, response
caching, and auth rate limiting. Every public function degrades to a documented
no-op (or an "unavailable" signal) when Redis is disabled or unreachable, so a
missing broker never breaks the request path: a downed Redis simply means "no
caching, no rate limiting, and concurrent generations run unlocked".

The client is created lazily on first use and commands are wrapped so a lost
connection is logged and treated as "feature off", never raised. The SQLite
test suite has no Redis: ``REDIS_ENABLED`` is forced off in
``app/tests/conftest.py``, and individual tests can substitute a fake client by
assigning ``app.services.redis_client._client``.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from uuid import uuid4

from app.config import settings

logger = logging.getLogger("timetable")

try:
    import redis as _redis_driver
except ImportError:  # pragma: no cover - redis is a declared dependency
    _redis_driver = None

_client = None

DEFAULT_LOCK_TIMEOUT = 600  # seconds; large generations can take minutes
DEFAULT_CACHE_TTL = 60  # seconds


def _get_client():
    """Lazily build the shared client. Returns None when Redis is disabled or
    the driver is unavailable."""
    global _client
    if not settings.REDIS_ENABLED or _redis_driver is None:
        return None
    if _client is None:
        _client = _redis_driver.Redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=0.5,
            socket_timeout=1.0,
        )
    return _client


# ── Generation-conflict locking ─────────────────────────────
@dataclass
class Lock:
    """An acquired Redis lock. Pass back to :func:`release_lock`."""

    key: str
    token: str


def acquire_lock(key: str, timeout: int = DEFAULT_LOCK_TIMEOUT):
    """Try to acquire a lock.

    Returns:
        Lock — acquired; call :func:`release_lock` when done.
        False — the lock is held by another caller (do not proceed).
        None — Redis unavailable; the caller should proceed unlocked.
    """
    client = _get_client()
    if client is None:
        return None
    token = uuid4().hex
    try:
        acquired = client.set(key, token, nx=True, px=int(timeout * 1000))
    except Exception:
        logger.debug("acquire_lock(%s) failed; proceeding unlocked", key)
        return None
    if acquired:
        return Lock(key=key, token=token)
    return False


def release_lock(lock) -> None:
    """Release a lock acquired with :func:`acquire_lock`. No-op for a busy or
    unavailable acquire (False/None) or a downed Redis. Compare-and-delete
    makes the release safe against a lock that already expired and was re-taken."""
    if not lock:
        return
    client = _get_client()
    if client is None:
        return
    try:
        client.eval(
            "if redis.call('get', KEYS[1]) == ARGV[1] then "
            "return redis.call('del', KEYS[1]) else return 0 end",
            1, lock.key, lock.token,
        )
    except Exception:
        logger.debug("release_lock(%s) failed; the key will expire", lock.key)


# ── Response caching ────────────────────────────────────────
def cache_get(key: str) -> str | None:
    client = _get_client()
    if client is None:
        return None
    try:
        return client.get(key)
    except Exception:
        logger.debug("cache_get(%s) failed; treating as a miss", key)
        return None


def cache_set(key: str, value: str, ttl: int = DEFAULT_CACHE_TTL) -> None:
    client = _get_client()
    if client is None:
        return
    try:
        client.set(key, value, ex=ttl)
    except Exception:
        logger.debug("cache_set(%s) failed", key)


def cache_get_json(key: str):
    raw = cache_get(key)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None


def cache_set_json(key: str, value, ttl: int = DEFAULT_CACHE_TTL) -> None:
    cache_set(key, json.dumps(value, default=str), ttl)


def cache_delete_prefix(prefix: str) -> None:
    """Delete every key starting with ``prefix`` (cache-bust on writes)."""
    client = _get_client()
    if client is None:
        return
    try:
        keys = list(client.scan_iter(match=f"{prefix}*"))
        if keys:
            client.delete(*keys)
    except Exception:
        logger.debug("cache_delete_prefix(%s) failed", prefix)


def cacheable_list(key: str, schema, rows, response, ttl: int = DEFAULT_CACHE_TTL) -> list:
    """Serialise ``rows`` through ``schema`` and cache the JSON body.

    The router sets ``X-Total-Count`` on ``response`` before calling; it is
    stored alongside the items so a cache hit can restore the header. Returns
    the serialised items (matching the endpoint's response model).
    """
    items = [schema.model_validate(r).model_dump(mode="json") for r in rows]
    total = response.headers.get("X-Total-Count") if response is not None else None
    cache_set_json(key, {"total": total, "items": items}, ttl)
    return items


def cache_serve_list(key: str, response) -> list | None:
    """Return the cached list body (restoring the total header) or None.
    ``response`` may be None for endpoints that do not paginate."""
    cached = cache_get_json(key)
    if cached is None:
        return None
    total = cached.get("total")
    if total is not None and response is not None:
        response.headers["X-Total-Count"] = str(total)
    return cached["items"]


# ── Auth rate limiting ──────────────────────────────────────
def check_rate_limit(scope: str, identifier: str, limit: int, window: int):
    """Fixed-window counter keyed by (scope, identifier).

    Returns True when the caller is allowed, False when it is over ``limit``
    requests per ``window`` seconds, and None when Redis is unavailable (the
    caller is allowed — a downed broker must never lock users out).
    """
    client = _get_client()
    if client is None:
        return None
    window_start = int(time.time() // window)
    key = f"timetable:ratelimit:{scope}:{identifier}:{window_start}"
    try:
        count = client.incr(key)
        if count == 1:
            client.expire(key, int(window) + 1)
    except Exception:
        logger.debug("check_rate_limit(%s) failed; allowing", key)
        return None
    return count <= limit
