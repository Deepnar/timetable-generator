"""Generic subject room requirements.

Replaces the binary ``Subject.requires_lab`` with a declarative requirements
spec matched against room attributes, so the engine can express any "this
subject needs a particular kind of room" without hardcoding a two-value
lab/not-lab model. The legacy ``requires_lab`` boolean stays as a shorthand
for ``{"room_types": ["LAB"]}``.

A subject's requirements live in ``Subject.requirements_json``::

    {
        "session_type": "LAB",          # optional; overrides the derived session type
        "room_types": ["LAB", "SEMINAR_HALL"],   # optional; absent/empty = any
        "min_capacity": 40,             # optional; absent/0 = any
        "features": ["projector", "ac"] # optional; the room must satisfy every one
    }

``features`` is matched against the room's ``equipment_json`` tag list and the
legacy boolean columns (``projector`` -> ``has_projector``, ``ac`` ->
``has_ac``), so a tag can be free-form while the two common flags stay sugar.
An unknown feature is unsatisfiable: the room must carry it somewhere.
"""
from __future__ import annotations

from app.models.generation import SessionType

# feature tag -> legacy boolean column on Room
_FEATURE_ATTRS = {"projector": "has_projector", "ac": "has_ac"}


def effective_requirements(subject) -> dict:
    """The resolved requirement spec for a subject.

    ``requirements_json`` wins when set (an empty dict means "no constraints").
    Otherwise ``requires_lab`` is the legacy shorthand for a LAB room. A subject
    with neither declares nothing, so any room matches.
    """
    if subject.requirements_json is not None:
        return subject.requirements_json or {}
    if subject.requires_lab:
        return {"room_types": ["LAB"]}
    return {}


def subject_session_type(subject) -> SessionType:
    """The session kind a subject's sessions should carry.

    ``requirements_json.session_type`` wins when present (so a subject can be a
    ``LAB``, ``TUTORIAL``, ``SEMINAR`` or ``CUSTOM`` session without a schema
    change); otherwise ``requires_lab`` decides between ``LAB`` and ``LECTURE``.
    """
    declared = effective_requirements(subject).get("session_type")
    if declared is not None:
        try:
            return SessionType(str(declared))
        except ValueError:
            pass
    return SessionType.LAB if subject.requires_lab else SessionType.LECTURE


def room_matches_requirements(room, reqs) -> tuple[bool, str | None]:
    """Whether a room satisfies a subject's requirement spec.

    Returns ``(ok, reason)`` where ``reason`` describes the first unmet
    requirement (or ``None`` when the room matches).
    """
    reqs = reqs or {}

    room_types = reqs.get("room_types") or []
    if room_types and room.room_type.value not in room_types:
        return False, f"room type {room.room_type.value} not in {room_types}"

    min_capacity = reqs.get("min_capacity")
    if min_capacity and room.capacity < min_capacity:
        return False, f"capacity {room.capacity} below required {min_capacity}"

    equipment = {
        str(f).lower()
        for f in room.equipment_json or []
        if isinstance(f, str)
    }
    for feature in reqs.get("features") or []:
        tag = str(feature).lower()
        if tag in equipment:
            continue
        attr = _FEATURE_ATTRS.get(tag)
        if attr is not None and getattr(room, attr, False):
            continue
        return False, f"missing feature {feature}"

    return True, None
