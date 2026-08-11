"""Profile (and profile-combination) resolution for the engine.

Profiles are the solver's input contract, but a generation can be triggered
from a *combination* of profiles. Resolution turns either a single profile id
or a combination id into one :class:`ResolvedProfile` — a merged, de-duplicated
view of resources, parameters, and constraints — so the solvers keep reading a
single profile-like object either way.

Merge semantics (documented in the architecture doc §6.2):

* **Resources** — union across members, de-duplicated by ``(resource_type,
  resource_id)``.
* **Parameters** — on key collisions the member with the *highest weight*
  wins; ties break on the lower profile id for determinism.
* **Hard constraints** — union of the global rows plus every member's rows,
  de-duplicated by ``(constraint_type, config_json)``.
* **Soft constraints** — union of the global rows plus every member's rows,
  de-duplicated by ``(constraint_type, config_json)`` with the *highest weight*
  kept on collisions.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy.orm import Session
from sqlalchemy import select, or_

from app.models.profiles import (
    TimetableProfile,
    ProfileCombination,
    ProfileCombinationMember,
    ProfileResource,
    ProfileParameter,
    ResourceType,
)
from app.models.constraints import HardConstraint, SoftConstraint


@dataclass
class ResolvedProfile:
    """The merged view of one or more source profiles that the solvers read.

    A single-profile run resolves to a :class:`ResolvedProfile` whose data is
    exactly that profile's; a combination run is the merged union.
    ``profile_id`` is the single source profile for a plain run and ``None``
    for a combination run (the generation row carries ``combination_id``
    instead).
    """

    profile_id: int | None
    source_profile_ids: list[int]
    params: dict
    resources: dict
    hard_constraints: list
    soft_constraints: list
    # The effective scope of the run: the highest-weight member's scope_type
    # for a combination, or the single profile's for a plain run. Lets the
    # engine branch on scope (e.g. scope_type == EXAM auto-enables exam mode).
    scope_type: str | None = None

    def resource_ids(self, resource_type: ResourceType) -> list[int]:
        return self.resources.get(resource_type, [])


class ProfileResolver:
    """Resolve a profile id or combination id into a :class:`ResolvedProfile`."""

    def __init__(self, db: Session):
        self.db = db

    def resolve(
        self,
        profile_id: int | None = None,
        combination_id: int | None = None,
        *,
        require_active: bool = True,
    ) -> ResolvedProfile:
        """Resolve either a single profile or a combination.

        ``combination_id`` takes precedence when both are given. By default a
        missing or inactive profile is an error; pass ``require_active=False``
        when re-validating already-generated work (e.g. slot overrides) whose
        source profile may have been archived since.
        """
        if combination_id is not None:
            return self._resolve_combination(combination_id, require_active)
        if profile_id is not None:
            return self._resolve_single(profile_id, require_active)
        raise ValueError("Either profile_id or combination_id must be provided")

    # ── source loading ─────────────────────────────────────
    def _resolve_single(self, profile_id: int, require_active: bool) -> ResolvedProfile:
        query = select(TimetableProfile).where(TimetableProfile.id == profile_id)
        if require_active:
            query = query.where(TimetableProfile.is_active == True)
        profile = self.db.scalars(query).first()
        if not profile:
            if require_active:
                raise ValueError(f"Profile {profile_id} not found or inactive")
            raise ValueError(f"Profile {profile_id} not found")
        return self._merge(profile_id=profile.id, members=[(profile.id, 1.0)])

    def _resolve_combination(
        self, combination_id: int, require_active: bool
    ) -> ResolvedProfile:
        combination = self.db.scalars(
            select(ProfileCombination).where(
                ProfileCombination.id == combination_id)
        ).first()
        if not combination:
            raise ValueError(f"Combination {combination_id} not found")

        members = self.db.scalars(
            select(ProfileCombinationMember).where(
                ProfileCombinationMember.combination_id == combination_id)
        ).all()
        if not members:
            raise ValueError(
                f"Combination {combination_id} has no member profiles")

        weighted = [(m.profile_id, float(m.weight)) for m in members]
        ids = [pid for pid, _ in weighted]
        profiles = self.db.scalars(
            select(TimetableProfile).where(TimetableProfile.id.in_(ids))
        ).all()
        found = {p.id: p for p in profiles}
        for pid, _ in weighted:
            profile = found.get(pid)
            if profile is None:
                raise ValueError(
                    f"Combination {combination_id} references missing "
                    f"profile {pid}")
            if require_active and not profile.is_active:
                raise ValueError(
                    f"Combination {combination_id} references inactive "
                    f"profile {pid}")

        return self._merge(profile_id=None, members=weighted)

    # ── merging ────────────────────────────────────────────
    def _merge(self, profile_id, members: list[tuple[int, float]]) -> ResolvedProfile:
        # Highest weight wins on collisions; ties break on the lower profile id
        # so the merged output is deterministic regardless of row order.
        members = sorted(members, key=lambda m: (-m[1], m[0]))
        profile_ids = [pid for pid, _ in members]

        return ResolvedProfile(
            profile_id=profile_id,
            source_profile_ids=profile_ids,
            params=self._merge_params(profile_ids),
            resources=self._merge_resources(profile_ids),
            hard_constraints=self._merge_constraints(profile_ids, HardConstraint),
            soft_constraints=self._merge_constraints(profile_ids, SoftConstraint),
            scope_type=self._merge_scope(profile_ids),
        )

    def _merge_scope(self, profile_ids: list[int]) -> str | None:
        """The effective scope: the highest-weight member's scope_type.

        ``members`` was already sorted by (-weight, id), so the first profile
        in the list is authoritative on scope collisions.
        """
        if not profile_ids:
            return None
        profile = self.db.get(TimetableProfile, profile_ids[0])
        return getattr(profile.scope_type, "value", profile.scope_type) if profile else None

    def _merge_resources(self, profile_ids: list[int]) -> dict:
        resources: dict = {t: [] for t in ResourceType}
        if not profile_ids:
            return resources
        rows = self.db.scalars(
            select(ProfileResource).where(
                ProfileResource.profile_id.in_(profile_ids))
        ).all()
        seen: set[tuple] = set()
        for r in rows:
            key = (r.resource_type, r.resource_id)
            if key in seen:
                continue
            seen.add(key)
            resources[r.resource_type].append(r.resource_id)
        return resources

    def _merge_params(self, profile_ids: list[int]) -> dict:
        params: dict = {}
        if not profile_ids:
            return params
        rows = self.db.scalars(
            select(ProfileParameter).where(
                ProfileParameter.profile_id.in_(profile_ids))
        ).all()
        precedence = {pid: i for i, pid in enumerate(profile_ids)}
        for r in sorted(
            rows, key=lambda r: precedence.get(r.profile_id, len(profile_ids))
        ):
            if r.param_key in params:
                continue
            params[r.param_key] = self._cast_param(r)
        return params

    def _merge_constraints(self, profile_ids: list[int], model) -> list:
        if not profile_ids:
            return []
        rows = self.db.scalars(
            select(model).where(
                model.is_active == True,
                or_(
                    model.profile_id.in_(profile_ids),
                    model.profile_id.is_(None),
                ),
            )
        ).all()
        # De-duplicate identical rules (type + config) so a rule shared by two
        # members is not applied twice. For soft rules the highest weight wins
        # on collisions; ordering is irrelevant for hard rules.
        seen: set[tuple] = set()
        out = []
        for r in sorted(
            rows,
            key=lambda r: (
                float(getattr(r, "weight", 1.0) or 1.0),
                getattr(r, "id", 0),
            ),
            reverse=True,
        ):
            key = (
                r.constraint_type,
                json.dumps(r.config_json, sort_keys=True)
                if r.config_json is not None else None,
            )
            if key in seen:
                continue
            seen.add(key)
            out.append(r)
        return out

    @staticmethod
    def _cast_param(p: ProfileParameter):
        """Cast a stored parameter string into its Python value."""
        if p.param_type == "INT":
            return int(p.param_value)
        if p.param_type == "FLOAT":
            return float(p.param_value)
        if p.param_type == "BOOLEAN":
            return p.param_value.lower() == "true"
        if p.param_type == "JSON":
            return json.loads(p.param_value)
        return p.param_value
