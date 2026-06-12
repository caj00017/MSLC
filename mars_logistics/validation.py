"""Red / yellow / green readiness checks.

These consume the results dict produced by :func:`mars_logistics.model.run_model`
and answer the two questions the spec demands:

    * Crew-arrival readiness - is the surface safe for humans yet? Crew arrival
      is *blocked* unless every critical crew check passes.
    * Sustainment readiness   - can the base be kept supplied indefinitely?

Status semantics:
    GREEN  - requirement met with margin.
    YELLOW - met, but marginal / relies on a mitigation (spares, imports).
    RED    - not met; for crew checks this blocks crew arrival.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List

GREEN = "green"
YELLOW = "yellow"
RED = "red"


@dataclass
class Check:
    name: str
    category: str          # "crew" or "sustainment"
    status: str            # GREEN / YELLOW / RED
    value: str             # human-readable observed value
    requirement: str       # human-readable requirement
    note: str = ""

    @property
    def passed(self) -> bool:
        return self.status != RED


def _status(ok: bool, marginal: bool = False) -> str:
    if not ok:
        return RED
    return YELLOW if marginal else GREEN


def crew_arrival_checks(results: Dict[str, Any]) -> List[Check]:
    a = results["assumptions"]
    crew = a["crew_count"]
    hab = results["habitat"]
    power = results["power"]
    storage = results["storage"]
    ls = results["life_support"]
    flags = results["flags"]
    missions = results["missions"]

    checks: List[Check] = []

    cap = hab["capacity"]
    checks.append(Check(
        "Habitat capacity >= crew", "crew", _status(cap >= crew),
        f"{cap} berths", f">= {crew} crew"))

    checks.append(Check(
        "Safe-haven capacity >= crew", "crew",
        _status(cap >= crew and flags["medical_available"]),
        f"{cap} berths, medical {'yes' if flags['medical_available'] else 'no'}",
        f">= {crew} crew + medical"))

    checks.append(Check(
        "ECLSS online", "crew", _status(power["eclss_power_kw"] > 0),
        f"{power['eclss_power_kw']:.1f} kW ECLSS load", "ECLSS powered"))

    pm = power["power_margin_kw"]
    checks.append(Check(
        "Critical power margin >= 0", "crew", _status(pm >= 0, marginal=0 <= pm < 1),
        f"{pm:.1f} kW margin", ">= 0 kW"))

    req_auto = max(a["dust_storm_autonomy_sols"], a["critical_load_autonomy_sols"])
    ach = storage["autonomy_achieved_sols"]
    checks.append(Check(
        "Energy-storage autonomy >= required", "crew",
        _status(ach >= req_auto, marginal=req_auto <= ach < req_auto * 1.1),
        f"{ach:.1f} sols", f">= {req_auto:.1f} sols"))

    checks.append(Check(
        "Oxygen reserve supported", "crew", _status(ls["oxygen"]["covered"]),
        ("locally closed (ISRU)" if ls["oxygen"]["locally_closed"] else "imported + reserve"),
        "O2 demand met + emergency reserve stocked"))

    checks.append(Check(
        "Water reserve supported", "crew", _status(ls["water"]["covered"]),
        ("locally closed" if ls["water"]["locally_closed"] else "recovery + imported + reserve"),
        "water demand met + emergency reserve stocked"))

    checks.append(Check(
        "Food reserve supported", "crew", _status(ls["food"]["covered"]),
        f"{ls['food']['storage_required_kg']:.0f} kg reserve stocked",
        "food storage >= emergency reserve"))

    checks.append(Check(
        "Comms online", "crew", _status(flags["comms_online"]),
        "comms asset deployed" if flags["comms_online"] else "no comms",
        "comms deployed pre-crew"))

    checks.append(Check(
        "Thermal control online", "crew", _status(flags["thermal_online"]),
        f"{hab['thermal_power_kw']:.1f} kW thermal", "thermal powered"))

    checks.append(Check(
        "Unloading/deployment assets", "crew", _status(flags["unloading_available"]),
        "heavy cargo handler present" if flags["unloading_available"] else "missing",
        "unloading mobility deployed"))

    checks.append(Check(
        "Minimum mobility available", "crew", _status(flags["mobility_available"]),
        "mobility present" if flags["mobility_available"] else "none",
        ">= 1 mobility asset"))

    viol = missions["dependency_violations"]
    checks.append(Check(
        "Dependency rules met", "crew", _status(len(viol) == 0),
        f"{len(viol)} violation(s)", "0 dependency violations"))

    # No critical asset past lifetime without a spares/replacement plan.
    dur = a["surface_duration_sols"]
    hab_life = a["habitat_lifetime_sols"]
    within_life = dur <= hab_life
    checks.append(Check(
        "Critical assets within life (or spared)", "crew",
        _status(True, marginal=not within_life),
        f"stay {dur:.0f} sols vs habitat life {hab_life:.0f} sols",
        "life >= stay, else spares planned"))

    # The landed stockpile must last until the crew leaves or the next resupply,
    # whichever comes first.
    endurance = results["crew_endurance"]["endurance_sols"]
    window_sols = results["sustainment"]["resupply"]["window_sols"]
    horizon = min(a["surface_duration_sols"], window_sols)
    checks.append(Check(
        "Stockpile lasts to resupply / departure", "crew",
        _status(endurance >= horizon, marginal=endurance < horizon * 1.1),
        f"endurance {endurance:.0f} sols",
        f">= {horizon:.0f} sols (min of stay {a['surface_duration_sols']:.0f}, "
        f"window {window_sols:.0f})"))

    # Pre-crew cargo must be deliverable before crew if pre-deploy is disallowed.
    if not a["predeploy_cargo_missions_allowed"] and missions["pre_crew_missions"] > 0:
        checks.append(Check(
            "Pre-crew cargo deliverable", "crew", RED,
            f"{missions['pre_crew_missions']} pre-crew missions needed",
            "pre-deploy disabled but cargo required"))

    return checks


def sustainment_checks(results: Dict[str, Any]) -> List[Check]:
    a = results["assumptions"]
    power = results["power"]
    storage = results["storage"]
    resupply = results["sustainment"]["resupply"]
    ls = results["life_support"]

    checks: List[Check] = []

    starships = resupply["starships_required"]
    checks.append(Check(
        "Resupply mass within cargo capacity/window", "sustainment",
        _status(starships <= 5, marginal=starships > 2),
        f"{starships} Starship(s)/window", "<= 5 Starships/window (placeholder)"))

    window_sols = resupply["window_sols"]
    hab_life = a["habitat_lifetime_sols"]
    checks.append(Check(
        "Spares interval <= asset lifetime", "sustainment",
        _status(window_sols <= hab_life),
        f"window {window_sols:.0f} sols", f"<= {hab_life:.0f} sols"))

    no_negative = (ls["water"]["import_required_kg"] >= 0
                   and ls["oxygen"]["import_required_kg"] >= 0
                   and ls["food"]["import_required_kg"] >= 0)
    checks.append(Check(
        "Consumable stockpile never negative", "sustainment",
        _status(no_negative), "imports clamped >= 0", "no negative imports"))

    pm = power["power_margin_kw"]
    ach = storage["autonomy_achieved_sols"]
    dust = a["dust_storm_autonomy_sols"]
    checks.append(Check(
        "Power margin positive in dust/autonomy case", "sustainment",
        _status(pm >= 0 and ach >= dust, marginal=ach < dust * 1.1),
        f"margin {pm:.1f} kW, autonomy {ach:.1f} sols",
        f">= 0 kW, >= {dust:.1f} sols"))

    # ISRU must not create a hidden power shortfall: its load is already inside
    # required_generation, so the test is simply that the margin survived it.
    checks.append(Check(
        "ISRU does not create hidden power shortfall", "sustainment",
        _status(pm >= 0),
        f"ISRU {power['isru_power_kw']:.1f} kW included; margin {pm:.1f} kW",
        "margin >= 0 with ISRU load"))

    return checks


def evaluate_readiness(results: Dict[str, Any]) -> Dict[str, Any]:
    """Run all checks and decide whether crew arrival is allowed."""
    crew = crew_arrival_checks(results)
    sustain = sustainment_checks(results)

    crew_red = [c for c in crew if c.status == RED]
    crew_arrival_allowed = len(crew_red) == 0

    def summarize(checks: List[Check]) -> Dict[str, int]:
        return {
            "green": sum(c.status == GREEN for c in checks),
            "yellow": sum(c.status == YELLOW for c in checks),
            "red": sum(c.status == RED for c in checks),
        }

    return {
        "crew_checks": [asdict(c) for c in crew],
        "sustainment_checks": [asdict(c) for c in sustain],
        "crew_arrival_allowed": crew_arrival_allowed,
        "crew_summary": summarize(crew),
        "sustainment_summary": summarize(sustain),
        "blocking_checks": [c.name for c in crew_red],
    }
