"""Phase 3 tests: objective-based instance variation (diversity strategies).

The diversity filter is seed-only by default: instance #1 is the deterministic
baseline and later instances are re-seeded re-rolls kept only if they clear the
Hamming gate. ``POST /generate`` gains a ``variation`` field that changes what
those re-rolls pursue:

* ``"random"`` (default) — plain seed-based diversity.
* ``"best"`` — every instance (including #1) is seeded and the highest-scoring
  distinct attempt is kept, so instance #1 can be the best timetable.
* ``"minimize-teacher-gaps"`` / ``"minimize-student-gaps"`` — seeded instances
  pack a teacher's / a group's sessions into contiguous slots (greedy reorders
  its search; OR-Tools adds a span term to the objective).

Instance #1 always stays the deterministic baseline unless ``variation="best"``.
"""
from collections import defaultdict

from app.tests.test_runner import (
    suite, test, seed_minimal, reset_db, create_admin, ensure_settings,
    TestingSessionLocal,
)


def _free_slots(slots, peer_key: str) -> int:
    """Total free slots inside every (peer, day) span of ``slots``."""
    by_day: dict[tuple, list] = defaultdict(list)
    for s in slots:
        if s[peer_key] is not None:
            by_day[(s[peer_key], s["day_of_week"])].append(s["slot_number"])
    gaps = 0
    for nums in by_day.values():
        span = max(nums) - min(nums) + 1
        gaps += span - len(nums)
    return gaps


def seed_two_subjects_one_group():
    """Group G with three one-hour subjects, two of them taught by one teacher.

    Returns ids. Used by the gap-minimisation tests: subject A (teacher FA) and
    subject C (same teacher FA) are different subjects, so FA's two sessions can
    share a day and the teacher-gap criterion has something to pack; all three
    subjects feed the student-gap criterion for the group.
    """
    reset_db()
    ensure_settings({"enable_soft_constraint_scoring": True})
    create_admin()
    db = TestingSessionLocal()
    try:
        from app.models.faculty import Faculty
        from app.models.groups import StudentGroup, GroupType
        from app.models.rooms import Room, RoomType
        from app.models.subjects import Subject
        from app.models.profiles import (
            TimetableProfile, ProfileResource, ProfileParameter, ParamType,
            ResourceType, ScopeType,
        )
        from app.models.subject_assignments import SubjectAssignment
        from app.models.admin import Admin as AdminModel

        admin = db.query(AdminModel).first()
        fac_a = Faculty(name="Alice", email="alice@var.test", department="CS")
        fac_b = Faculty(name="Bob", email="bob@var.test", department="CS")
        grp = StudentGroup(name="CS-A", group_type=GroupType.DIVISION,
                           department="CS", year=2, semester=3, strength=60)
        room = Room(name="R1", room_code="R1", room_type=RoomType.CLASSROOM,
                    capacity=80, building="A")
        subj_a = Subject(name="Maths", subject_code="M101", department="CS",
                         semester=3, hours_per_week=1, requires_lab=False)
        subj_b = Subject(name="Physics", subject_code="PH101", department="CS",
                         semester=3, hours_per_week=1, requires_lab=False)
        subj_c = Subject(name="English", subject_code="E101", department="CS",
                         semester=3, hours_per_week=1, requires_lab=False)
        prof = TimetableProfile(name="Variation profile",
                                scope_type=ScopeType.DIVISION,
                                academic_year="2025-26", semester=3,
                                department="CS", created_by=admin.id)
        db.add_all([fac_a, fac_b, grp, room, subj_a, subj_b, subj_c, prof])
        db.flush()

        db.add(ProfileResource(profile_id=prof.id,
                               resource_type=ResourceType.ROOM,
                               resource_id=room.id))
        for fid in (fac_a.id, fac_b.id):
            db.add(ProfileResource(profile_id=prof.id,
                                   resource_type=ResourceType.FACULTY,
                                   resource_id=fid))
        db.add(ProfileResource(profile_id=prof.id,
                               resource_type=ResourceType.STUDENT_GROUP,
                               resource_id=grp.id))
        for sid in (subj_a.id, subj_b.id, subj_c.id):
            db.add(ProfileResource(profile_id=prof.id,
                                   resource_type=ResourceType.SUBJECT,
                                   resource_id=sid))
        db.add(ProfileParameter(profile_id=prof.id, param_key="slots_per_day",
                                param_value="5", param_type=ParamType.INT))
        db.add(ProfileParameter(profile_id=prof.id, param_key="working_days",
                                param_value='["MON","TUE","WED","THU","FRI"]',
                                param_type=ParamType.JSON))

        db.add(SubjectAssignment(subject_id=subj_a.id, faculty_id=fac_a.id,
                                 group_id=grp.id, weekly_hours=1, load_share=1.0))
        db.add(SubjectAssignment(subject_id=subj_b.id, faculty_id=fac_b.id,
                                 group_id=grp.id, weekly_hours=1, load_share=1.0))
        db.add(SubjectAssignment(subject_id=subj_c.id, faculty_id=fac_a.id,
                                 group_id=grp.id, weekly_hours=1, load_share=1.0))
        db.commit()
        return {"profile": prof.id, "group": grp.id, "faculty_a": fac_a.id,
                "faculty_b": fac_b.id, "subject_a": subj_a.id,
                "subject_b": subj_b.id, "subject_c": subj_c.id,
                "room": room.id}
    finally:
        db.close()


@suite("Phase 3 — Objective-based variation")
def _phase3_variation(s):
    def _run_row(run_id):
        from app.models.generation import TimetableGeneration
        db = TestingSessionLocal()
        try:
            return db.get(TimetableGeneration, run_id)
        finally:
            db.close()

    def _gen_instances(client, headers, profile_id, *, algorithm,
                       variation=None, instances_requested=1):
        body = {
            "profile_id": profile_id, "academic_year": "2025-26",
            "semester": 3, "timetable_type": "CLASS",
            "instances_requested": instances_requested,
            "algorithm": algorithm,
        }
        if variation is not None:
            body["variation"] = variation
        r = client.post("/generate/", headers=headers, json=body)
        assert r.status_code == 201, r.text
        gen_id = r.json()["id"]
        instances = client.get(f"/instances/{gen_id}", headers=headers).json()
        return gen_id, instances, [
            client.get(f"/instances/{inst['id']}/slots", headers=headers).json()
            for inst in instances
        ]

    @test("variation defaults to random and is echoed on the run")
    def t_default_variation(client):
        from app.tests.test_runner import login_token, auth_headers
        ids = seed_minimal()
        headers = auth_headers(login_token(client))
        gen_id, _, _ = _gen_instances(
            client, headers, ids["profile"], algorithm="GREEDY")
        row = _run_row(gen_id)
        assert row.variation.value == "random", row.variation
        r = client.get(f"/generate/{gen_id}/status", headers=headers)
        assert r.json()["variation"] == "random", r.json()

    @test("an explicit variation is persisted and returned")
    def t_explicit_variation(client):
        from app.models.generation import VariationMode
        from app.tests.test_runner import login_token, auth_headers
        ids = seed_minimal()
        headers = auth_headers(login_token(client))
        gen_id, _, _ = _gen_instances(
            client, headers, ids["profile"], algorithm="GREEDY",
            variation="minimize-teacher-gaps")
        row = _run_row(gen_id)
        assert row.variation == VariationMode.MINIMIZE_TEACHER_GAPS, row.variation
        r = client.get(f"/generate/{gen_id}/status", headers=headers)
        assert r.json()["variation"] == "minimize-teacher-gaps", r.json()

    @test("create_generation persists variation for the async worker")
    def t_async_persists_variation(client):
        from app.engine.scheduler import Scheduler
        from app.models.generation import AlgorithmType, VariationMode
        ids = seed_minimal()
        db = TestingSessionLocal()
        try:
            gen = Scheduler(db).create_generation(
                profile_id=ids["profile"], timetable_type="CLASS",
                academic_year="2025-26", semester=3,
                instances_requested=1, algorithm=AlgorithmType.GREEDY,
                triggered_by=ids["admin"],
                variation=VariationMode.BEST,
            )
            assert gen.variation == VariationMode.BEST, gen.variation
        finally:
            db.close()

    @test("instance #1 stays the baseline for minimize-* variations")
    def t_baseline_unchanged(client):
        from app.tests.test_runner import login_token, auth_headers
        ids = seed_minimal()
        headers = auth_headers(login_token(client))
        _, _, baseline = _gen_instances(
            client, headers, ids["profile"], algorithm="GREEDY")
        _, _, vary = _gen_instances(
            client, headers, ids["profile"], algorithm="GREEDY",
            variation="minimize-student-gaps")

        def sig(slots):
            return {(sl["student_group_id"], sl["day_of_week"],
                     sl["slot_number"], sl["subject_id"]) for sl in slots}

        assert sig(baseline[0]) == sig(vary[0]), (sig(baseline[0]), sig(vary[0]))

    @test("greedy minimize-student-gaps packs a group's sessions contiguously")
    def t_greedy_student_gaps(client):
        from app.tests.test_runner import login_token, auth_headers
        ids = seed_two_subjects_one_group()
        headers = auth_headers(login_token(client))
        _, instances, slots_by_instance = _gen_instances(
            client, headers, ids["profile"], algorithm="GREEDY",
            variation="minimize-student-gaps", instances_requested=2)
        assert len(slots_by_instance) == 2, slots_by_instance
        second = slots_by_instance[1]
        # A seeded re-roll pursuing the student-gap criterion must pack the
        # group's sessions with no free slots inside any of its days.
        assert _free_slots(second, "student_group_id") == 0, second
        first = slots_by_instance[0]
        sig1 = {(sl["student_group_id"], sl["day_of_week"], sl["slot_number"],
                 sl["subject_id"]) for sl in first}
        sig2 = {(sl["student_group_id"], sl["day_of_week"], sl["slot_number"],
                 sl["subject_id"]) for sl in second}
        assert sig1 != sig2, "instances must stay distinct"

    @test("OR-Tools minimize-teacher-gaps packs a teacher's sessions")
    def t_ortools_teacher_gaps(client):
        from app.tests.test_runner import login_token, auth_headers
        ids = seed_two_subjects_one_group()
        headers = auth_headers(login_token(client))
        _, instances, slots_by_instance = _gen_instances(
            client, headers, ids["profile"], algorithm="OR_TOOLS",
            variation="minimize-teacher-gaps", instances_requested=2)
        assert len(slots_by_instance) == 2, slots_by_instance
        second = slots_by_instance[1]
        # The teacher-gap span term is only in the objective for seeded
        # instances; a gap-free teacher day is achievable here, so an optimal
        # solution must avoid holes inside the teacher's day.
        assert _free_slots(second, "faculty_id") == 0, second

    @test("variation=best keeps the highest-scoring distinct attempt")
    def t_best_keeps_best(client):
        from app.engine.profile_resolver import ProfileResolver
        from app.engine.scorer import score_instance, ScoringContext
        from app.engine.solvers.greedy_solver import GreedySolver
        from app.models.generation import VariationMode
        from app.models.constraints import SoftConstraint
        from app.tests.test_runner import login_token, auth_headers
        ids = seed_minimal()
        # A second subject for the same group means the group can hold two
        # sessions in one day, so the student-gap score varies with the seed's
        # search order — giving "best" something to pick between.
        db = TestingSessionLocal()
        try:
            from app.models.subjects import Subject
            from app.models.profiles import (ProfileResource, ResourceType)
            from app.models.subject_assignments import SubjectAssignment
            from app.models.faculty import Faculty
            subj_c = Subject(name="English", subject_code="E101",
                             department="CS", semester=3, hours_per_week=1,
                             requires_lab=False)
            fac_c = Faculty(name="Cara", email="cara@x.com", department="CS")
            db.add_all([subj_c, fac_c]); db.flush()
            db.add(ProfileResource(profile_id=ids["profile"],
                                   resource_type=ResourceType.SUBJECT,
                                   resource_id=subj_c.id))
            db.add(ProfileResource(profile_id=ids["profile"],
                                   resource_type=ResourceType.FACULTY,
                                   resource_id=fac_c.id))
            db.add(SubjectAssignment(subject_id=subj_c.id,
                                     faculty_id=fac_c.id,
                                     group_id=ids["group"], weekly_hours=1,
                                     load_share=1.0))
            db.add(SoftConstraint(profile_id=ids["profile"],
                                  constraint_type="MINIMIZE_STUDENT_FREE_SLOTS",
                                  weight=1.0, is_active=True))
            db.commit()
        finally:
            db.close()

        headers = auth_headers(login_token(client))
        gen_id, instances, slots_by_instance = _gen_instances(
            client, headers, ids["profile"], algorithm="GREEDY",
            variation="best", instances_requested=1)
        assert instances[0]["soft_score"] is not None, instances

        # Recompute exactly what the scheduler compared: the six seeds it tried
        # for instance #1 (i=0 -> seeds 0..5), scored with the profile's soft
        # rules. The run must equal the highest-scoring attempt, and the stored
        # soft_score must be that attempt's score.
        db = TestingSessionLocal()
        try:
            resolved = ProfileResolver(db).resolve(ids["profile"])
            attempts = []
            for seed in range(6):
                solver = GreedySolver(
                    db, resolved, instance_id=99999, seed=seed,
                    variation=VariationMode.BEST)
                slots = solver.solve()
                score = score_instance(
                    slots, resolved.soft_constraints, ScoringContext(db))
                attempts.append((score, slots))
            best_score, best_slots = max(attempts, key=lambda t: t[0])
            assert best_score > 0.0, [t[0] for t in attempts]
        finally:
            db.close()

        assert instances[0]["soft_score"] == best_score, instances[0]["soft_score"]
        sig_run = {(sl["student_group_id"], sl["day_of_week"],
                    sl["slot_number"], sl["subject_id"])
                   for sl in slots_by_instance[0]}
        sig_best = {(sl.student_group_id, sl.day_of_week, sl.slot_number,
                     sl.subject_id) for sl in best_slots}
        assert sig_run == sig_best, (sig_run, sig_best)

    return [t_default_variation, t_explicit_variation,
            t_async_persists_variation, t_baseline_unchanged,
            t_greedy_student_gaps, t_ortools_teacher_gaps, t_best_keeps_best]
