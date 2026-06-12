"""Exact reproduction of the legacy lunar-analog reference case.

This module is deliberately self-contained and driven by the numbers embedded
in the prompt, so it can serve as a *validation oracle*: the unit tests assert
that these functions reproduce the documented legacy totals exactly:

    * day-power totals        : 108.15 kW peak, 62.4 kW continuous
    * night-energy totals     : 17,522.4 kWh (thrive), 2,066.4 kWh (survive)
    * battery sizing          : 1,947 (thrive) / 230 (survive) 45-kg modules
    * total mass rollup       : 99,174.4 kg (thrive), 21,891.4 kg (survive),
                                9,294.2 kg (with fission surface power)

These are lunar-derived PLACEHOLDERS, not Mars design values. They exist to
(a) prove the rebuilt engine reproduces the legacy spreadsheet where intended,
and (b) preserve the documented inconsistencies as explicit notes rather than
silently "fixing" them.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List

# --- legacy constants (named, from the prompt) ------------------------------
LEGACY_NIGHT_HOURS: float = 336.0
LEGACY_BATTERY_SPECIFIC_ENERGY_KWH_PER_KG: float = 0.2
LEGACY_BATTERY_UNIT_MASS_KG: float = 45.0
LEGACY_VSAT_UNIT_MASS_KG: float = 700.0
LEGACY_VSAT_OUTPUT_KW: float = 50.0
LEGACY_CABLE_MASS_EACH_KG: float = 432.6
LEGACY_FSP_UNIT_POWER_KW: float = 100.0


@dataclass
class LegacyAsset:
    """One row of the legacy day/night operating set."""
    name: str
    quantity: int
    peak_kw_per_unit: float
    continuous_kw_per_unit: float
    on_at_night_thrive: bool = False
    on_at_night_survive: bool = False

    @property
    def total_peak_kw(self) -> float:
        return self.quantity * self.peak_kw_per_unit

    @property
    def total_continuous_kw(self) -> float:
        return self.quantity * self.continuous_kw_per_unit


#: Legacy day-operation set (per-unit values; shelter is 2 units @ 3 kW each).
LEGACY_DAY_ASSETS: List[LegacyAsset] = [
    LegacyAsset("O2fR pilot plant", 1, 40, 40, on_at_night_thrive=True),
    LegacyAsset("Science mission", 1, 1, 1, on_at_night_thrive=True),
    LegacyAsset("Shelter", 2, 3, 3, on_at_night_thrive=True, on_at_night_survive=True),
    LegacyAsset("Shelter assembly system", 1, 1, 0.25),
    LegacyAsset("Comms system", 1, 0.15, 0.15, on_at_night_thrive=True,
                on_at_night_survive=True),
    LegacyAsset("Regolith Construction Rover", 1, 10, 2.5),
    LegacyAsset("Regolith Excavator Rover", 1, 10, 2.5, on_at_night_thrive=True),
    LegacyAsset("Cargo Handling Rover - Light", 1, 10, 2.5),
    LegacyAsset("Cargo Handling Rover - Heavy", 1, 20, 5),
    LegacyAsset("Highly Dexterous Rover", 1, 10, 2.5, on_at_night_thrive=True),
]


def legacy_day_power() -> Dict[str, float]:
    """Reproduce the legacy day-power totals (108.15 kW peak, 62.4 kW cont.)."""
    peak = sum(a.total_peak_kw for a in LEGACY_DAY_ASSETS)
    cont = sum(a.total_continuous_kw for a in LEGACY_DAY_ASSETS)
    return {
        "total_peak_power_kw": peak,
        "total_continuous_power_kw": cont,
        "vsat_units_for_peak": math.ceil(peak / LEGACY_VSAT_OUTPUT_KW),
        "vsat_units_for_continuous": math.ceil(cont / LEGACY_VSAT_OUTPUT_KW),
    }


def legacy_night_energy(mode: str) -> Dict[str, float]:
    """Reproduce legacy night energy + battery sizing for 'thrive' or 'survive'.

    Night power is the sum of continuous loads operating through the 336-h night.
    Energy = power * night_hours. Battery mass = energy / specific_energy.
    """
    if mode == "thrive":
        active = [a for a in LEGACY_DAY_ASSETS if a.on_at_night_thrive]
    elif mode == "survive":
        active = [a for a in LEGACY_DAY_ASSETS if a.on_at_night_survive]
    else:  # pragma: no cover - guarded by caller
        raise ValueError("mode must be 'thrive' or 'survive'")

    night_power_kw = sum(a.total_continuous_kw for a in active)
    night_energy_kwh = night_power_kw * LEGACY_NIGHT_HOURS
    battery_mass_kg = night_energy_kwh / LEGACY_BATTERY_SPECIFIC_ENERGY_KWH_PER_KG
    battery_units = math.ceil(battery_mass_kg / LEGACY_BATTERY_UNIT_MASS_KG)
    return {
        "night_power_kw": night_power_kw,
        "night_energy_kwh": night_energy_kwh,
        "battery_mass_kg": battery_mass_kg,
        "battery_units": battery_units,
    }


@dataclass
class LegacyMassLine:
    """One line of the legacy total-mass rollup, with per-column masses."""
    item: str
    qty_thrive: float
    qty_survive: float
    qty_fsp: float
    mass_thrive_kg: float
    mass_survive_kg: float
    mass_fsp_kg: float
    note: str = ""


def legacy_total_mass() -> Dict[str, object]:
    """Reproduce the legacy total-mass rollup and its three column totals.

    Preserves the documented legacy inconsistency in the battery line:
      * thrive battery mass uses units * 45 kg  -> 1,947 * 45 = 87,615 kg
      * survive battery mass uses raw kWh/specific energy -> 10,332 kg
    This is faithful to the source spreadsheet and is flagged in the note.
    """
    thrive = legacy_night_energy("thrive")
    survive = legacy_night_energy("survive")

    battery_mass_thrive = thrive["battery_units"] * LEGACY_BATTERY_UNIT_MASS_KG
    battery_mass_survive = survive["battery_mass_kg"]  # raw, per legacy sheet

    lines: List[LegacyMassLine] = [
        LegacyMassLine("O2fR pilot plant", 1, 1, 1, 1000, 1000, 1000),
        LegacyMassLine("Science mission", 1, 1, 1, 100, 100, 100),
        LegacyMassLine("VSAT/power unit", 3, 3, 1,
                       3 * LEGACY_VSAT_UNIT_MASS_KG, 3 * LEGACY_VSAT_UNIT_MASS_KG,
                       1 * LEGACY_VSAT_UNIT_MASS_KG),
        LegacyMassLine("Battery", thrive["battery_units"], survive["battery_units"], 0,
                       battery_mass_thrive, battery_mass_survive, 0,
                       note="Legacy inconsistency: thrive=units*45, survive=raw kWh/0.2."),
        LegacyMassLine("FSP from LIT", 0, 0, 1, 0, 0, 0,
                       note="Fission surface power mass not in legacy rollup (0)."),
        LegacyMassLine("Power cable", 4, 4, 2,
                       4 * LEGACY_CABLE_MASS_EACH_KG, 4 * LEGACY_CABLE_MASS_EACH_KG,
                       2 * LEGACY_CABLE_MASS_EACH_KG),
        LegacyMassLine("Shelter", 2, 2, 2, 3400, 3400, 3400),
        LegacyMassLine("Shelter assembly system", 1, 1, 1, 747, 747, 747),
        LegacyMassLine("Comms system", 1, 1, 1, 300, 300, 300),
        LegacyMassLine("Regolith Excavator Rover", 2, 2, 2, 132, 132, 132),
        LegacyMassLine("Cargo Handling Rover - Light", 1, 1, 1, 250, 250, 250),
        LegacyMassLine("Cargo Handling Rover - Heavy", 1, 1, 1, 1500, 1500, 1500),
        LegacyMassLine("Highly Dexterous Rover", 1, 1, 1, 300, 300, 300),
    ]

    total_thrive = sum(l.mass_thrive_kg for l in lines)
    total_survive = sum(l.mass_survive_kg for l in lines)
    total_fsp = sum(l.mass_fsp_kg for l in lines)
    return {
        "lines": lines,
        "total_thrive_kg": total_thrive,
        "total_survive_kg": total_survive,
        "total_fsp_kg": total_fsp,
    }


# --- legacy mission manifest (reference data, not Mars truth) ----------------

@dataclass
class LegacyMission:
    mission: str
    year: int
    lander: str
    mode: str
    launch_mass_limit_kg: float
    allocated_mass_kg: float
    available_power_kw: float
    power_needed_kw: float
    available_energy_kwh: float
    energy_needed_kwh: float
    key_assets: str


LEGACY_MISSION_MANIFEST: List[LegacyMission] = [
    LegacyMission("LInc-1", 2030, "MK1", "Survive", 3000, 2992.6, 60, 20, 72, 0,
                  "1 VSAT, 8 batteries, 1 power cable, 1 heavy cargo handling rover"),
    LegacyMission("LInc-2", 2031, "MK1", "Survive", 3000, 2998.6, 110, 30, 432, 0,
                  "1 VSAT, 40 batteries, 1 power cable, 1 regolith excavator rover"),
    LegacyMission("LInc-3", 2032, "MK1", "Survive", 3000, 2977.6, 160, 30, 801, 0,
                  "1 VSAT, 41 batteries, 1 power cable"),
    LegacyMission("LInc-4", 2033, "MK1", "Thrive", 3000, 2976, 160, 40.15, 1323, 890.4,
                  "58 batteries, 1 comms system, 1 regolith excavator rover"),
    LegacyMission("LInc-5", 2034, "MK1", "Thrive", 3000, 2979.6, 160, 41.15, 1683, 890.4,
                  "40 batteries, 1 power cable, 1 shelter assembly system"),
    LegacyMission("LInc-6", 2035, "MK2", "Thrive", 30000, 29970, 160, 64.15, 7227, 2738.4,
                  "616 batteries, 1 shelter, 1 light cargo handling rover, 1 dexterous rover"),
    LegacyMission("LInc-7", 2036, "MK2", "Thrive", 30000, 29970, 160, 68.15, 12861, 4082.4,
                  "626 batteries, 1 science mission, 1 shelter"),
    LegacyMission("LInc-8", 2037, "MK2", "Thrive", 30000, 24310, 160, 108.15, 17523, 17522.4,
                  "518 batteries, 1 O2fR pilot plant"),
    LegacyMission("LInc-9", 2038, "MK2", "Thrive", 30000, 0, 160, 0, 0, 0,
                  "no additional assets"),
    LegacyMission("LInc-10", 2039, "MK2", "Thrive", 30000, 0, 160, 0, 0, 0,
                  "no additional assets"),
]


def legacy_summary() -> Dict[str, object]:
    """Bundle every legacy reproduction result for display/export."""
    return {
        "day_power": legacy_day_power(),
        "night_thrive": legacy_night_energy("thrive"),
        "night_survive": legacy_night_energy("survive"),
        "total_mass": legacy_total_mass(),
        "manifest": LEGACY_MISSION_MANIFEST,
    }
