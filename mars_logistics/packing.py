"""Dependency-aware mission bin packing.

The spec is explicit that the mission count must NOT be a naive
``ceil(total_mass / usable_payload)``. This module packs a list of
:class:`CargoItem` objects into Starship-sized cargo missions while honouring:

    * a per-mission usable mass limit,
    * an optional per-mission volume limit,
    * "prior" dependencies      - prerequisite must be on a strictly earlier mission,
    * "same-or-prior" deps      - prerequisite may be on the same or earlier mission,
    * criticality and pre-crew sequencing.

Items are processed in dependency (topological) order so that, combined with
append-only mission creation, an item is never placed earlier than any of its
prerequisites. Divisible items (consumables, battery banks) may be split across
missions; atomic items (a habitat module, a rover) are placed whole.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional

_CRITICALITY_RANK = {"critical": 0, "important": 1, "optional": 2}
_EPS = 1e-9


@dataclass
class CargoItem:
    """A single thing to land. ``dep_key`` is the identity used for dependency
    resolution (many physical items can share one dep_key, e.g. battery modules).
    """
    item_id: str
    asset_name: str
    mass_kg: float
    volume_m3: float
    bucket: str
    dep_key: str
    quantity: float = 1.0
    criticality: str = "important"
    scenario_group: str = "survival"
    required_phase: str = "setup"
    must_arrive_before_crew: bool = False
    can_arrive_after_crew: bool = True
    divisible: bool = False
    depends_on_prior: List[str] = field(default_factory=list)
    depends_on_same_or_prior: List[str] = field(default_factory=list)
    # populated by the packer for split (divisible) items:
    is_partial: bool = False


@dataclass
class Mission:
    """One cargo Starship's manifest."""
    index: int
    items: List[CargoItem] = field(default_factory=list)
    allocated_mass_kg: float = 0.0
    allocated_volume_m3: float = 0.0
    overweight: bool = False  # an oversized atomic item exceeded usable payload

    def add(self, item: CargoItem) -> None:
        self.items.append(item)
        self.allocated_mass_kg += item.mass_kg
        self.allocated_volume_m3 += item.volume_m3


def _dependency_depth(items: List[CargoItem]) -> Dict[str, int]:
    """Longest-path depth of each dep_key in the dependency DAG.

    Depth 0 = no prerequisites. Cycles are broken defensively (a node already on
    the current DFS stack contributes no further depth) so a bad dependency table
    can never hang the packer.
    """
    edges: Dict[str, set] = {}
    for it in items:
        edges.setdefault(it.dep_key, set())
        for d in list(it.depends_on_prior) + list(it.depends_on_same_or_prior):
            edges.setdefault(d, set()).add(it.dep_key)

    depth: Dict[str, int] = {}
    visiting: set = set()

    def visit(node: str) -> int:
        if node in depth:
            return depth[node]
        if node in visiting:
            return 0  # cycle guard
        visiting.add(node)
        prereqs = [src for src, dsts in edges.items() if node in dsts]
        best = 0
        for p in prereqs:
            best = max(best, visit(p) + 1)
        visiting.discard(node)
        depth[node] = best
        return best

    for key in list(edges.keys()):
        visit(key)
    return depth


def _sort_items(items: List[CargoItem]) -> List[CargoItem]:
    depth = _dependency_depth(items)
    return sorted(
        items,
        key=lambda it: (
            depth.get(it.dep_key, 0),
            0 if it.must_arrive_before_crew else 1,
            _CRITICALITY_RANK.get(it.criticality, 1),
            -it.mass_kg,
        ),
    )


def pack_missions(
    items: List[CargoItem],
    usable_payload_kg: float,
    max_volume_m3: Optional[float] = None,
) -> List[Mission]:
    """Pack ``items`` into missions. Returns the ordered list of missions.

    A non-positive ``usable_payload_kg`` is a degenerate misconfiguration (e.g.
    zero packing efficiency): there is no capacity to pack into, so everything is
    placed in a single mission flagged ``overweight`` rather than looping forever.
    """
    missions: List[Mission] = []
    if usable_payload_kg <= _EPS:
        if items:
            m = Mission(index=0, overweight=True)
            for it in items:
                m.add(it)
            missions.append(m)
        return missions

    last_index: Dict[str, int] = {}  # dep_key -> highest mission index used
    use_volume = bool(max_volume_m3 and max_volume_m3 > 0)

    def ensure(idx: int) -> None:
        while len(missions) <= idx:
            missions.append(Mission(index=len(missions)))

    def earliest_for(it: CargoItem) -> int:
        e = 0
        for d in it.depends_on_prior:
            if d in last_index:
                e = max(e, last_index[d] + 1)
        for d in it.depends_on_same_or_prior:
            if d in last_index:
                e = max(e, last_index[d])
        return e

    def note_index(key: str, idx: int) -> None:
        last_index[key] = max(last_index.get(key, idx), idx)

    for item in _sort_items(items):
        start = earliest_for(item)

        if item.divisible and item.mass_kg > _EPS:
            remaining = item.mass_kg
            vol_per_kg = (item.volume_m3 / item.mass_kg) if item.mass_kg > _EPS else 0.0
            idx = start
            while remaining > _EPS:
                ensure(idx)
                m = missions[idx]
                free_mass = usable_payload_kg - m.allocated_mass_kg
                if free_mass <= _EPS:
                    idx += 1
                    continue
                add_mass = min(remaining, free_mass)
                if use_volume and vol_per_kg > 0:
                    free_vol = max_volume_m3 - m.allocated_volume_m3
                    if free_vol <= _EPS:
                        idx += 1
                        continue
                    add_mass = min(add_mass, free_vol / vol_per_kg)
                if add_mass <= _EPS:
                    # No progress possible even in a fresh mission (e.g. a single
                    # unit's volume exceeds a whole Starship). Force the remainder
                    # in and flag it rather than spinning forever.
                    if not m.items:
                        part = replace(item, mass_kg=remaining,
                                       volume_m3=remaining * vol_per_kg,
                                       quantity=item.quantity * (remaining / item.mass_kg),
                                       is_partial=(remaining < item.mass_kg - _EPS))
                        m.add(part)
                        m.overweight = True
                        note_index(item.dep_key, idx)
                        remaining = 0.0
                        break
                    idx += 1
                    continue
                frac = add_mass / item.mass_kg
                part = replace(
                    item,
                    mass_kg=add_mass,
                    volume_m3=add_mass * vol_per_kg,
                    quantity=item.quantity * frac,
                    is_partial=(add_mass < item.mass_kg - _EPS),
                )
                m.add(part)
                note_index(item.dep_key, idx)
                remaining -= add_mass
                idx += 1
        else:
            idx = start
            while True:
                ensure(idx)
                m = missions[idx]
                free_mass = usable_payload_kg - m.allocated_mass_kg
                fits_mass = item.mass_kg <= free_mass + _EPS
                fits_vol = True
                if use_volume:
                    free_vol = max_volume_m3 - m.allocated_volume_m3
                    fits_vol = item.volume_m3 <= free_vol + _EPS
                if fits_mass and fits_vol:
                    m.add(item)
                    note_index(item.dep_key, idx)
                    break
                # Oversized atomic item: nothing will ever hold it. Place it alone
                # in a fresh mission and flag the mission as overweight.
                if not m.items and item.mass_kg > usable_payload_kg + _EPS:
                    m.add(item)
                    m.overweight = True
                    note_index(item.dep_key, idx)
                    break
                idx += 1

    return missions


def first_mission_with_key(missions: List[Mission], dep_key: str) -> Optional[int]:
    """Index of the first mission containing an item with ``dep_key`` (or None)."""
    for m in missions:
        if any(it.dep_key == dep_key for it in m.items):
            return m.index
    return None


def crew_arrival_mission_index(missions: List[Mission]) -> int:
    """Mission index after which crew may arrive: one past the last mission that
    carries a ``must_arrive_before_crew`` item. Returns 0 if there are none."""
    last_pre = -1
    for m in missions:
        if any(it.must_arrive_before_crew for it in m.items):
            last_pre = m.index
    return last_pre + 1


def verify_dependencies(missions: List[Mission]) -> List[Dict[str, object]]:
    """Check that every placed item's dependencies are satisfied by the packing.

    Returns a list of violation records (empty when the packing is valid)."""
    placed_min: Dict[str, int] = {}
    placed_max: Dict[str, int] = {}
    for m in missions:
        for it in m.items:
            placed_min[it.dep_key] = min(placed_min.get(it.dep_key, m.index), m.index)
            placed_max[it.dep_key] = max(placed_max.get(it.dep_key, m.index), m.index)

    violations: List[Dict[str, object]] = []
    for m in missions:
        for it in m.items:
            for d in it.depends_on_prior:
                if d in placed_max and m.index <= placed_max[d]:
                    violations.append({
                        "item": it.item_id, "mission": m.index,
                        "depends_on": d, "rule": "prior",
                        "detail": f"must be strictly after mission {placed_max[d]}",
                    })
            for d in it.depends_on_same_or_prior:
                if d in placed_min and m.index < placed_min[d]:
                    violations.append({
                        "item": it.item_id, "mission": m.index,
                        "depends_on": d, "rule": "same_or_prior",
                        "detail": f"must be on or after mission {placed_min[d]}",
                    })
    return violations
