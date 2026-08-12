"""Date-resolution for mid-year changes (DD-022 #2 / DD-026 follow-up).

A published timetable is a weekly template; ``timetable_overrides`` make
exceptions to it. To answer "is there class on date X" (and to render a
truthful day card), the base weekly slots are resolved against the active
changes for the specific date:

* a **permanent** override (no ``date_from``/``date_to``) applies on every date;
* a **windowed** override (``TEMP`` with a date range) applies only inside its
  window — and wins over a permanent one for the same slot while it is active;
* a **SWAP** exchanges the two slots' faculty/room at their positions;
* a slot with a winning cover/change reports the new faculty/room (the
  original content is "hidden" while the cover applies).

This is the platform the day card, "where is teacher X", and the change list
sit on.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.generation import TimetableSlot
from app.models.overrides import TimetableOverride, OverrideType


def _applies_on(o: TimetableOverride, on_date: date) -> bool:
    """Whether an active override applies to ``on_date``."""
    if o.resolved_at is not None:
        return False
    if o.date_from is not None and on_date < o.date_from:
        return False
    if o.date_to is not None and on_date > o.date_to:
        return False
    return True


def _winning_override(overrides: list[TimetableOverride],
                      on_date: date) -> TimetableOverride | None:
    """Pick the override that wins for a slot on ``on_date``.

    Windowed (temp) overrides that cover the date beat permanent ones; among
    same-class candidates the most recently created wins. If only permanent
    changes exist, the newest permanent applies.
    """
    windowed = [o for o in overrides
                if _applies_on(o, on_date) and (o.date_from or o.date_to)]
    permanent = [o for o in overrides
                 if _applies_on(o, on_date) and not (o.date_from or o.date_to)]
    pool = windowed or permanent
    if not pool:
        return None
    return max(pool, key=lambda o: o.created_at)


def effective_slot(db: Session, slot: TimetableSlot,
                   on_date: date) -> tuple[int | None, int | None]:
    """The (faculty_id, room_id) that slot shows on ``on_date`` after
    resolving mid-year changes."""
    overrides = db.scalars(
        select(TimetableOverride).where(
            TimetableOverride.slot_id == slot.id,
            TimetableOverride.resolved_at.is_(None),
        )
    ).all()
    winner = _winning_override(overrides, on_date)
    if winner is None:
        return slot.faculty_id, slot.room_id

    if winner.override_type == OverrideType.SWAP and winner.swap_with_slot_id:
        partner = db.get(TimetableSlot, winner.swap_with_slot_id)
        if partner is not None:
            # A swaps faculty/room with B at B's position.
            return partner.faculty_id, partner.room_id
        return slot.faculty_id, slot.room_id

    fac = winner.new_faculty_id if winner.new_faculty_id is not None else slot.faculty_id
    room = winner.new_room_id if winner.new_room_id is not None else slot.room_id
    return fac, room


def resolve_slots_for_date(db: Session, slots: list[TimetableSlot],
                           on_date: date) -> dict[int, tuple[int | None, int | None]]:
    """Resolve every slot in ``slots`` for ``on_date``.

    ``slots`` should already be filtered to the slots that occur on that date
    (``day_of_week == on_date.weekday()``). Returns ``{slot_id: (faculty_id,
    room_id)}`` with the effective values (base values when no change wins).
    """
    return {s.id: effective_slot(db, s, on_date) for s in slots}
