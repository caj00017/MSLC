"""The Mars Surface Logistics calculation engine.

Pure standard-library Python. The single public entry point is
:func:`run_model`, which takes a flat assumptions dict, an asset catalog (list
of dicts), and a dependency edge list, and returns one large results dict that
the UI, the exporters, and the readiness checker all consume.

Every intermediate quantity is named. Divide-by-zero is impossible by
construction (see :func:`mars_logistics.units.safe_div`); imports are clamped to
zero; and crew-survival oxygen is kept strictly separate from propellant oxygen.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from . import defaults
from . import units as U
from . import validation
from .packing import (
    CargoItem, pack_missions, crew_arrival_mission_index, verify_dependencies,
)


# ---------------------------------------------------------------------------
# Small building blocks (each independently testable).
# ---------------------------------------------------------------------------

def compute_time(a: Dict[str, Any]) -> Dict[str, float]:
    """Sol/Earth-day conversions and resupply-window timing."""
    surface_sols = float(a["surface_duration_sols"])
    window_months = float(a["resupply_window_months"])
    resupply_window_earth_days = U.months_to_earth_days(window_months)
    return {
        "hours_per_sol": U.HOURS_PER_SOL,
        "earth_days_per_sol": U.EARTH_DAYS_PER_SOL,
        "surface_duration_sols": surface_sols,
        "surface_duration_earth_days": U.sols_to_earth_days(surface_sols),
        "resupply_window_months": window_months,
        "resupply_window_earth_days": resupply_window_earth_days,
        "resupply_window_sols": U.earth_days_to_sols(resupply_window_earth_days),
    }


def compute_usable_payload(a: Dict[str, Any]) -> float:
    """usable = landed * packing_efficiency * (1 - unallocated_margin)."""
    return (float(a["landed_payload_kg_per_starship"])
            * float(a["packing_efficiency"])
            * (1.0 - float(a["unallocated_margin_percent"])))


def _food_rate(a: Dict[str, Any]) -> float:
    return (float(a["hydrated_food_kg_per_crew_sol"])
            if a.get("food_basis", "hydrated") == "hydrated"
            else float(a["dry_food_kg_per_crew_sol"]))


def compute_life_support(a: Dict[str, Any], duration_sols: float) -> Dict[str, Any]:
    """Water, oxygen, and food mass balances over ``duration_sols``.

    ISRU production is folded in here so imports are net of recovery + ISRU and
    clamped at zero. Emergency-reserve storage is sized from the makeup *rate*.
    """
    crew = float(a["crew_count"])
    reserve_sols = float(a["emergency_reserve_sols"])
    storage_margin = float(a["storage_margin"])

    # EVA / leakage flows (whole base, over the stay).
    eva_hours_total = crew * float(a["eva_hours_per_crew_sol"]) * duration_sols
    eva_o2 = eva_hours_total * float(a["EVA_oxygen_kg_per_EVA_hour"])
    eva_water = eva_hours_total * float(a["EVA_water_kg_per_EVA_hour"])
    airlock_loss = (float(a["airlock_cycles_per_sol"])
                    * float(a["airlock_loss_kg_per_cycle"]) * duration_sols)
    cabin_leak = float(a["cabin_leakage_kg_per_sol"]) * duration_sols

    # --- Oxygen ---------------------------------------------------------
    gross_o2 = crew * float(a["oxygen_kg_per_crew_sol"]) * duration_sols
    recovered_o2 = gross_o2 * float(a["oxygen_recovery_rate"])
    o2_makeup = gross_o2 - recovered_o2 + eva_o2 + airlock_loss + cabin_leak
    o2_makeup_rate = U.safe_div(o2_makeup, duration_sols)

    o2_isru = compute_oxygen_isru(a, o2_makeup_rate)
    o2_isru_produced = o2_isru["produced_per_sol"] * duration_sols
    o2_import = max(0.0, o2_makeup - o2_isru_produced)
    o2_storage = o2_makeup_rate * reserve_sols * storage_margin
    # "covered" = the supply plan closes: the emergency reserve is sized and the
    # demand is met by recovery + ISRU + landed makeup (import is clamped >= 0).
    o2_covered = o2_storage > 0 and (o2_isru_produced + o2_import) >= o2_makeup - 1e-6
    o2_locally_closed = o2_import <= 1e-6

    # --- Water ----------------------------------------------------------
    gross_water = crew * float(a["water_kg_per_crew_sol"]) * duration_sols
    recovered_water = gross_water * float(a["water_recovery_rate"])

    greenhouse_water_makeup = 0.0
    if a.get("include_greenhouse"):
        gh_gross = float(a["greenhouse_water_kg_per_crew_sol"]) * crew * duration_sols
        greenhouse_water_makeup = gh_gross * (1.0 - float(a["greenhouse_water_recovery_fraction"]))

    water_makeup = gross_water - recovered_water + eva_water + greenhouse_water_makeup
    water_makeup_rate = U.safe_div(water_makeup, duration_sols)

    water_isru = compute_water_isru(a, water_makeup_rate)
    water_isru_produced = water_isru["produced_per_sol"] * duration_sols
    water_import = max(0.0, water_makeup - water_isru_produced)
    water_storage = water_makeup_rate * reserve_sols * storage_margin
    water_covered = water_storage > 0 and (water_isru_produced + water_import) >= water_makeup - 1e-6
    water_locally_closed = water_import <= 1e-6

    # --- Food -----------------------------------------------------------
    food_rate = _food_rate(a)
    gross_food = crew * food_rate * duration_sols
    food_produced = gross_food * float(a["food_closure_fraction"])
    food_import = max(0.0, gross_food - food_produced)
    food_storage = crew * food_rate * reserve_sols * storage_margin
    food_covered = food_storage > 0
    food_locally_closed = float(a["food_closure_fraction"]) >= 1.0 - 1e-6

    return {
        "eva": {"hours_total": eva_hours_total, "o2_kg": eva_o2, "water_kg": eva_water,
                "airlock_loss_kg": airlock_loss, "cabin_leak_kg": cabin_leak},
        "oxygen": {
            "gross_kg": gross_o2, "recovered_kg": recovered_o2,
            "makeup_before_isru_kg": o2_makeup, "makeup_rate_kg_per_sol": o2_makeup_rate,
            "isru_produced_kg": o2_isru_produced, "import_required_kg": o2_import,
            "storage_required_kg": o2_storage, "covered": o2_covered,
            "locally_closed": o2_locally_closed,
        },
        "water": {
            "gross_kg": gross_water, "recovered_kg": recovered_water,
            "makeup_before_isru_kg": water_makeup, "makeup_rate_kg_per_sol": water_makeup_rate,
            "isru_produced_kg": water_isru_produced, "import_required_kg": water_import,
            "storage_required_kg": water_storage, "covered": water_covered,
            "locally_closed": water_locally_closed,
            "greenhouse_makeup_kg": greenhouse_water_makeup,
        },
        "food": {
            "gross_kg": gross_food, "produced_kg": food_produced,
            "import_required_kg": food_import, "storage_required_kg": food_storage,
            "rate_kg_per_crew_sol": food_rate, "covered": food_covered,
            "locally_closed": food_locally_closed,
        },
    }


def compute_oxygen_isru(a: Dict[str, Any], required_o2_per_sol: float) -> Dict[str, Any]:
    """Size crew-survival O2 ISRU. Returns zero units when disabled or when the
    effective per-unit output is non-positive (no divide-by-zero, no crash)."""
    unit_out = (float(a["oxygen_ISRU_output_kg_per_sol"])
                * float(a["oxygen_ISRU_utilization_factor"])
                * float(a["oxygen_ISRU_availability"]))
    if not a.get("oxygen_ISRU_enabled") or unit_out <= 0:
        return {"effective_output_per_unit": unit_out, "units": 0, "mass_kg": 0.0,
                "power_kw": 0.0, "produced_per_sol": 0.0,
                "required_per_sol": required_o2_per_sol,
                "fractional_units": 0.0}
    fractional = U.safe_div(required_o2_per_sol, unit_out)
    units = U.ceil_units(fractional)
    return {
        "effective_output_per_unit": unit_out,
        "fractional_units": fractional,
        "units": units,
        "mass_kg": units * float(a["oxygen_ISRU_unit_mass_kg"]),
        "power_kw": units * float(a["oxygen_ISRU_unit_power_kw"]),
        "produced_per_sol": units * unit_out,
        "required_per_sol": required_o2_per_sol,
    }


def compute_water_isru(a: Dict[str, Any], required_water_per_sol: float) -> Dict[str, Any]:
    """Size regolith water extraction. Disabled -> zero units."""
    unit_out = (float(a["regolith_processed_kg_per_sol_per_unit"])
                * float(a["regolith_water_mass_fraction"])
                * float(a["water_extraction_efficiency"])
                * float(a["water_ISRU_availability"]))
    if not a.get("water_ISRU_enabled") or unit_out <= 0:
        return {"effective_output_per_unit": unit_out, "units": 0, "mass_kg": 0.0,
                "power_kw": 0.0, "produced_per_sol": 0.0,
                "regolith_demand_per_sol": 0.0}
    units = U.ceil_units(U.safe_div(required_water_per_sol, unit_out))
    return {
        "effective_output_per_unit": unit_out,
        "units": units,
        "mass_kg": units * float(a["water_extraction_unit_mass_kg"]),
        "power_kw": units * float(a["water_extraction_unit_power_kw"]),
        "produced_per_sol": units * unit_out,
        "regolith_demand_per_sol": units * float(a["regolith_processed_kg_per_sol_per_unit"]),
    }


def compute_propellant_isru(a: Dict[str, Any], oxygen_unit_out: float) -> Dict[str, Any]:
    """Size return-propellant ISRU, kept entirely separate from crew O2."""
    if not a.get("include_propellant_isru") or not a.get("propellant_ISRU_enabled"):
        return {"enabled": False, "o2_units": 0, "mass_kg": 0.0, "power_kw": 0.0,
                "o2_rate_per_sol": 0.0, "ch4_rate_per_sol": 0.0,
                "storage_mass_kg": 0.0}
    deadline = float(a["propellant_production_deadline_sols"])
    o2_target = float(a["propellant_O2_target_kg_per_window"])
    ch4_target = float(a["propellant_CH4_target_kg_per_window"])
    o2_rate = U.safe_div(o2_target, deadline)
    ch4_rate = U.safe_div(ch4_target, deadline)
    o2_units = U.ceil_units(U.safe_div(o2_rate, oxygen_unit_out)) if oxygen_unit_out > 0 else 0
    storage_mass = float(a["propellant_storage_mass_fraction"]) * (o2_target + ch4_target)
    hardware_mass = o2_units * float(a["oxygen_ISRU_unit_mass_kg"])
    total_rate = o2_rate + ch4_rate
    power = (o2_units * float(a["oxygen_ISRU_unit_power_kw"])
             + total_rate * float(a["propellant_power_kw_per_kg_per_sol"]))
    return {
        "enabled": True, "o2_units": o2_units,
        "mass_kg": hardware_mass + storage_mass, "storage_mass_kg": storage_mass,
        "power_kw": power, "o2_rate_per_sol": o2_rate, "ch4_rate_per_sol": ch4_rate,
    }


def compute_habitat(a: Dict[str, Any]) -> Dict[str, Any]:
    crew = float(a["crew_count"])
    cap_per = float(a["crew_capacity_per_habitat"])
    base = U.ceil_units(U.safe_div(crew, cap_per))
    count = base + int(a["minimum_habitat_redundancy"])
    imported_shielding = (float(a["radiation_shielding_mass_kg_per_habitat"])
                          * (1.0 - float(a["shielding_local_material_fraction"]))
                          * count)
    mass_total = (count * float(a["habitat_mass_kg"])
                  + imported_shielding
                  + float(a["deployment_equipment_mass_kg"])
                  + float(a["medical_module_mass_kg"])
                  + float(a["galley_hygiene_module_mass_kg"]))
    return {
        "count_base": base, "count": count, "capacity": int(count * cap_per),
        "imported_shielding_kg": imported_shielding,
        "mass_total_kg": mass_total,
        "volume_total_m3": count * float(a["habitat_volume_m3"]),
        "power_continuous_kw": count * float(a["habitat_power_continuous_kw"]),
        "power_peak_kw": count * float(a["habitat_power_peak_kw"]),
        "thermal_power_kw": count * float(a["thermal_power_kw_per_habitat"]),
    }


# ---------------------------------------------------------------------------
# Asset activation, quantities, and power balance.
# ---------------------------------------------------------------------------

def _active_groups(a: Dict[str, Any]) -> List[str]:
    return defaults.MODE_ACTIVE_GROUPS.get(a["operating_mode"], ["survival"])


def _asset_is_active(row: Dict[str, Any], a: Dict[str, Any]) -> bool:
    groups = _active_groups(a)
    if row["scenario_group"] in groups:
        active = True
    else:
        active = False
    cat = row["category"]
    if a.get("include_surface_construction") and cat == "construction":
        active = True
    if a.get("include_pressurized_rovers") and cat in (
            "mobility_logistics", "mobility_robotics"):
        active = True
    return active


def compute_asset_quantities(assets: List[Dict[str, Any]], a: Dict[str, Any],
                             habitat_count: int, power_unit_count: int,
                             isru_unit_count: int) -> List[Dict[str, Any]]:
    """Apply the quantity formula to each asset and tag activation."""
    crew = float(a["crew_count"])
    out: List[Dict[str, Any]] = []
    for row in assets:
        qty = (float(row.get("quantity_fixed", 0))
               + float(row.get("quantity_per_crew", 0)) * crew
               + float(row.get("quantity_per_habitat", 0)) * habitat_count
               + float(row.get("quantity_per_power_unit", 0)) * power_unit_count
               + float(row.get("quantity_per_ISRU_unit", 0)) * isru_unit_count)
        qty = math.ceil(qty - 1e-9) if qty > 0 else 0
        qty = max(qty, int(row.get("redundancy_minimum", 0)) if qty > 0 else 0)
        rec = dict(row)
        rec["quantity_required"] = qty
        rec["active"] = _asset_is_active(row, a)
        out.append(rec)
    return out


def compute_power_balance(active_assets: List[Dict[str, Any]], a: Dict[str, Any],
                          habitat: Dict[str, Any], eclss_power_kw: float,
                          isru_power_kw: float) -> Dict[str, Any]:
    """Sum discrete-asset loads with the formula systems. kW and kWh stay
    strictly separate: peak/continuous are kW, energy is kWh/sol."""
    hours = U.HOURS_PER_SOL
    assets_peak = assets_cont = assets_energy = 0.0
    critical_assets_cont = 0.0
    for r in active_assets:
        if not r["active"]:
            continue
        if r["category"] in defaults.FORMULA_COMPUTED_CATEGORIES:
            continue  # generation/storage/distribution/habitat/ISRU sized by formula
        qty = r["quantity_required"]
        peak = qty * float(r.get("power_peak_kw", 0))
        cont = qty * float(r.get("power_continuous_kw", 0))
        avg = qty * float(r.get("power_peak_kw", 0)) * float(r.get("duty_cycle", 0))
        explicit = float(r.get("energy_kWh_per_sol", 0))
        energy = explicit * qty if explicit > 0 else U.energy_kwh_from_power(avg, hours)
        assets_peak += peak
        assets_cont += cont
        assets_energy += energy
        if r.get("criticality") == "critical":
            critical_assets_cont += cont

    hab_cont = habitat["power_continuous_kw"]
    hab_peak = habitat["power_peak_kw"]
    thermal = habitat["thermal_power_kw"]

    total_continuous = assets_cont + hab_cont + eclss_power_kw + isru_power_kw + thermal
    total_peak = ((assets_peak + hab_peak + eclss_power_kw + isru_power_kw + thermal)
                  * float(a["simultaneity_factor"]))
    total_energy = (assets_energy
                    + U.energy_kwh_from_power(hab_cont, hours)
                    + U.energy_kwh_from_power(eclss_power_kw, hours)
                    + U.energy_kwh_from_power(isru_power_kw, hours)
                    + U.energy_kwh_from_power(thermal, hours))
    required_generation = total_continuous * (1.0 + float(a["power_margin_percent"]))

    # Critical load drives storage autonomy: life-critical formula systems plus
    # any discrete asset flagged critical.
    critical_load = hab_cont + eclss_power_kw + thermal + critical_assets_cont

    return {
        "assets_peak_kw": assets_peak, "assets_continuous_kw": assets_cont,
        "assets_energy_kwh_per_sol": assets_energy,
        "habitat_continuous_kw": hab_cont, "habitat_peak_kw": hab_peak,
        "eclss_power_kw": eclss_power_kw, "isru_power_kw": isru_power_kw,
        "thermal_power_kw": thermal,
        "total_continuous_kw": total_continuous, "total_peak_kw": total_peak,
        "total_energy_kwh_per_sol": total_energy,
        "required_generation_kw": required_generation,
        "critical_load_kw": critical_load,
    }


def compute_generation(a: Dict[str, Any], power: Dict[str, Any],
                       time: Dict[str, Any]) -> Dict[str, Any]:
    """Size power generation for the selected architecture (solar/nuclear/hybrid).

    Solar is energy-limited (sized to deliver the sol's energy with margin);
    nuclear is power-limited (sized to the continuous load with margin).
    """
    arch = a["power_architecture"]
    required_gen_kw = power["required_generation_kw"]
    energy_per_sol = power["total_energy_kwh_per_sol"]
    sun_hours = float(a["effective_sun_hours_per_sol"])
    margin = float(a["power_margin_percent"])

    def solar(energy_kwh: float) -> Dict[str, float]:
        target = energy_kwh * (1.0 + margin)
        gen_kw = U.safe_div(target, sun_hours)
        derate = float(a["dust_derating_factor"]) * float(a["seasonal_derating_factor"])
        gen_kw_derated = U.safe_div(gen_kw, derate)
        mass = U.safe_div(gen_kw_derated, float(a["solar_array_specific_power_kw_per_kg"]))
        return {"generation_kw": gen_kw, "generation_kw_derated": gen_kw_derated,
                "mass_kg": mass, "continuous_equivalent_kw": U.safe_div(target, U.HOURS_PER_SOL)}

    def nuclear(req_kw: float) -> Dict[str, float]:
        unit = float(a["nuclear_unit_power_kw"])
        n = U.ceil_units(U.safe_div(req_kw, unit))
        return {"units": n, "mass_kg": n * float(a["nuclear_unit_mass_kg"]),
                "installed_kw": n * unit}

    result: Dict[str, Any] = {"architecture": arch}
    if arch == "nuclear":
        nuc = nuclear(required_gen_kw)
        result.update({"nuclear": nuc, "solar": None,
                       "generation_mass_kg": nuc["mass_kg"],
                       "installed_continuous_kw": nuc["installed_kw"]})
    elif arch == "hybrid":
        frac = float(a["hybrid_nuclear_fraction"])
        nuc = nuclear(required_gen_kw * frac)
        sol = solar(energy_per_sol * (1.0 - frac))
        result.update({"nuclear": nuc, "solar": sol,
                       "generation_mass_kg": nuc["mass_kg"] + sol["mass_kg"],
                       "installed_continuous_kw": nuc["installed_kw"]
                       + sol["continuous_equivalent_kw"]})
    else:  # solar (default)
        sol = solar(energy_per_sol)
        result.update({"nuclear": None, "solar": sol,
                       "generation_mass_kg": sol["mass_kg"],
                       "installed_continuous_kw": sol["continuous_equivalent_kw"]})

    result["power_margin_kw"] = result["installed_continuous_kw"] - power["total_continuous_kw"]
    return result


def compute_energy_storage(a: Dict[str, Any], critical_load_kw: float) -> Dict[str, Any]:
    """Battery sizing for the binding autonomy requirement.

        storage_kWh = critical_load * autonomy_hours / roundtrip / depth_of_discharge
        battery_mass = storage_kWh / specific_energy
        units = ceil(mass / unit_mass)
    """
    periods = {
        "critical_load": float(a["critical_load_autonomy_sols"]),
        "dust_storm": float(a["dust_storm_autonomy_sols"]),
        "power_outage": float(a["power_outage_autonomy_sols"]),
    }
    design_autonomy = max(periods.values()) if periods else 0.0
    rt = float(a["battery_roundtrip_efficiency"])
    dod = float(a["battery_depth_of_discharge"])
    spec = float(a["battery_specific_energy_kWh_per_kg"])
    unit_mass = float(a["battery_unit_mass_kg"])

    autonomy_hours = U.sols_to_hours(design_autonomy)
    storage_kwh = U.safe_div(U.safe_div(critical_load_kw * autonomy_hours, rt), dod)
    battery_mass = U.safe_div(storage_kwh, spec)
    units = U.ceil_units(U.safe_div(battery_mass, unit_mass))
    installed_mass = units * unit_mass
    installed_capacity = installed_mass * spec
    usable_capacity = installed_capacity * rt * dod
    autonomy_achieved = U.safe_div(
        usable_capacity, critical_load_kw * U.HOURS_PER_SOL) if critical_load_kw > 0 else design_autonomy

    by_period = {}
    for name, sols in periods.items():
        kwh = U.safe_div(U.safe_div(critical_load_kw * U.sols_to_hours(sols), rt), dod)
        by_period[name] = {"autonomy_sols": sols, "storage_kwh_required": kwh,
                           "battery_mass_kg": U.safe_div(kwh, spec)}

    return {
        "design_autonomy_sols": design_autonomy,
        "storage_kwh_required": storage_kwh,
        "battery_mass_kg": installed_mass,
        "battery_units": units,
        "installed_capacity_kwh": installed_capacity,
        "usable_capacity_kwh": usable_capacity,
        "autonomy_achieved_sols": autonomy_achieved,
        "autonomy_by_period": by_period,
        "critical_load_kw": critical_load_kw,
    }


def compute_distribution(a: Dict[str, Any], transmitted_kw: float) -> Dict[str, Any]:
    """Formula-driven cable mass (never a hard-coded value).

        mass = kg_per_km_per_kw * length_km * transmitted_kw
    """
    kg_per_km_per_kw = float(a["power_distribution_mass_kg_per_kw_km"])
    length_km = float(a["average_power_cable_length_km"])
    mass = kg_per_km_per_kw * length_km * transmitted_kw
    legacy_4_cable = 4 * defaults.SEED_ASSETS[4]["unit_mass_kg"]  # power_cable row
    return {
        "cable_mass_kg": mass, "transmitted_kw": transmitted_kw, "length_km": length_km,
        "kg_per_km_per_kw": kg_per_km_per_kw,
        "legacy_note": (f"Legacy fixed value was {legacy_4_cable:.1f} kg for 4x0.5 km "
                        f"cables; this model computes mass from the formula instead."),
    }


# ---------------------------------------------------------------------------
# Mass rollup, sustainment, cargo items, limiting resource.
# ---------------------------------------------------------------------------

def _bucket_masses(a, time, ls, habitat, isru, power_gen, storage, distribution,
                   active_assets, eclss) -> Dict[str, float]:
    crew = float(a["crew_count"])
    duration = time["surface_duration_sols"]

    consumables = (ls["water"]["import_required_kg"] + ls["water"]["storage_required_kg"]
                   + ls["oxygen"]["import_required_kg"] + ls["oxygen"]["storage_required_kg"]
                   + ls["food"]["import_required_kg"] + ls["food"]["storage_required_kg"]
                   + eclss["spares_total_kg"] + eclss["filters_total_kg"])

    buckets: Dict[str, float] = {b: 0.0 for b in defaults.MASS_BUCKET_ORDER}
    buckets["Crew consumables & reserves"] = consumables
    buckets["Habitat & crew systems"] = habitat["mass_total_kg"]
    buckets["Power generation"] = power_gen["generation_mass_kg"]
    buckets["Energy storage"] = storage["battery_mass_kg"]
    buckets["Power distribution"] = distribution["cable_mass_kg"]
    buckets["Crew O2 ISRU"] = isru["oxygen"]["mass_kg"]
    buckets["Water ISRU"] = isru["water"]["mass_kg"]
    buckets["Propellant ISRU"] = isru["propellant"]["mass_kg"]

    if a.get("include_greenhouse"):
        buckets["Greenhouse"] = float(a["greenhouse_mass_kg_per_crew"]) * crew

    for r in active_assets:
        if not r["active"]:
            continue
        bucket = defaults.CATEGORY_TO_BUCKET.get(r["category"])
        if bucket is None:
            continue  # formula-computed categories already counted
        buckets[bucket] += r["quantity_required"] * float(r["unit_mass_kg"])

    return buckets


# Buckets that must be on the surface before crew arrives.
_PRE_CREW_BUCKETS = frozenset({
    "Crew consumables & reserves", "Habitat & crew systems", "Power generation",
    "Energy storage", "Power distribution", "Crew O2 ISRU", "Communications",
})


def compute_sustainment(a, time, ls, installed_hardware_kg, usable_payload_kg) -> Dict[str, Any]:
    crew = float(a["crew_count"])
    window_sols = time["resupply_window_sols"]
    window_days = time["resupply_window_earth_days"]
    duration_sols = time["surface_duration_sols"]

    net_rate_per_crew_sol = (
        U.safe_div(ls["water"]["import_required_kg"], crew * duration_sols)
        + U.safe_div(ls["oxygen"]["import_required_kg"], crew * duration_sols)
        + U.safe_div(ls["food"]["import_required_kg"], crew * duration_sols)
        + float(a["ECLSS_spares_kg_per_crew_sol"])
        + float(a["ECLSS_filter_sorbent_kg_per_crew_sol"]))

    consumables = crew * net_rate_per_crew_sol * window_sols
    spares = (installed_hardware_kg * float(a["hardware_spares_percent_per_year"])
              * window_days / U.EARTH_DAYS_PER_YEAR)
    medical = crew * float(a["medical_resupply_kg_per_crew_window"])
    replacement = float(a["replacement_hardware_kg_per_window"])
    science = float(a["science_payload_replenishment_kg_per_window"])
    contingency = float(a["contingency_margin_percent"]) * (consumables + spares)
    total = consumables + spares + medical + replacement + science + contingency
    starships = U.ceil_units(U.safe_div(total, usable_payload_kg))

    period_spares = (installed_hardware_kg * float(a["hardware_spares_percent_per_year"])
                     * time["surface_duration_earth_days"] / U.EARTH_DAYS_PER_YEAR)

    return {
        "installed_hardware_kg": installed_hardware_kg,
        "net_consumables_rate_kg_per_crew_sol": net_rate_per_crew_sol,
        "period_spares_kg": period_spares,
        "resupply": {
            "consumables_kg": consumables, "spares_kg": spares, "medical_kg": medical,
            "replacement_kg": replacement, "science_kg": science,
            "contingency_kg": contingency, "total_kg": total,
            "starships_required": starships,
            "window_sols": window_sols, "window_earth_days": window_days,
        },
    }


def build_cargo_items(a, ls, habitat, isru, power_gen, storage, distribution,
                      active_assets, eclss, buckets) -> List[CargoItem]:
    """Synthesise the cargo manifest: formula systems become grouped pallets and
    discrete catalog assets become individual items, all dependency-tagged."""
    items: List[CargoItem] = []
    vol_factor = 0.004  # m^3 per kg fallback density for synthesized pallets

    def add(item_id, name, mass, bucket, dep_key, *, crit="important", divisible=False,
            pre_crew=False, prior=None, same=None, volume=None, qty=1.0, group="survival"):
        if mass <= 0:
            return
        items.append(CargoItem(
            item_id=item_id, asset_name=name, mass_kg=mass,
            volume_m3=volume if volume is not None else mass * vol_factor,
            bucket=bucket, dep_key=dep_key, quantity=qty, criticality=crit,
            scenario_group=group, must_arrive_before_crew=pre_crew,
            can_arrive_after_crew=not pre_crew, divisible=divisible,
            depends_on_prior=list(prior or []),
            depends_on_same_or_prior=list(same or []),
        ))

    # Formula systems (pre-crew critical infrastructure).
    add("power_generation", "Power generation", power_gen["generation_mass_kg"],
        "Power generation", "power_generation", crit="critical", divisible=True, pre_crew=True)
    add("power_distribution", "Power distribution", distribution["cable_mass_kg"],
        "Power distribution", "power_distribution", crit="critical", divisible=True,
        pre_crew=True, same=["power_generation"])
    add("energy_storage", "Energy storage", storage["battery_mass_kg"],
        "Energy storage", "energy_storage", crit="critical", divisible=True,
        pre_crew=True, same=["power_generation"], qty=storage["battery_units"])
    add("habitat", "Habitat & crew systems", habitat["mass_total_kg"],
        "Habitat & crew systems", "habitat", crit="critical", divisible=False, pre_crew=True,
        prior=["power_generation", "power_distribution"],
        same=["energy_storage", "cargo_handling_rover_heavy"],
        volume=habitat["volume_total_m3"])
    add("crew_o2_isru", "Crew O2 ISRU", isru["oxygen"]["mass_kg"],
        "Crew O2 ISRU", "crew_o2_isru", crit="critical", divisible=False, pre_crew=True,
        prior=["power_generation"], same=["power_distribution"])
    consumables_mass = buckets["Crew consumables & reserves"]
    add("crew_consumables", "Crew consumables & reserves", consumables_mass,
        "Crew consumables & reserves", "crew_consumables", crit="critical",
        divisible=True, pre_crew=True)

    # Water / propellant ISRU (not strictly pre-crew).
    add("water_isru", "Water ISRU", isru["water"]["mass_kg"], "Water ISRU", "water_isru",
        crit="important", prior=["power_generation"], same=["regolith_excavator_rover"])
    add("propellant_isru", "Propellant ISRU", isru["propellant"]["mass_kg"],
        "Propellant ISRU", "propellant_isru", crit="optional", prior=["power_generation"],
        group="thrive")
    if a.get("include_greenhouse"):
        add("greenhouse", "Greenhouse", buckets["Greenhouse"], "Greenhouse", "greenhouse",
            crit="optional", prior=["habitat"], same=["power_generation"], group="thrive")

    # Discrete catalog assets -> individual items, carrying their dependencies.
    remap = {"vsat_power_unit": "power_generation", "battery_module": "energy_storage",
             "power_cable": "power_distribution", "shelter": "habitat",
             "o2fr_pilot_plant": "crew_o2_isru"}
    for r in active_assets:
        if not r["active"] or r["category"] in defaults.FORMULA_COMPUTED_CATEGORIES:
            continue
        qty = r["quantity_required"]
        if qty <= 0:
            continue
        aid = r["asset_id"]
        prior, same = [], []
        for dep in str(r.get("prerequisite_asset_ids", "")).split(";"):
            dep = dep.strip()
            if not dep:
                continue
            dep = remap.get(dep, dep)
            (prior if str(r.get("dependency_type")) == "prior" else same).append(dep)
        pre_crew = (not bool(r.get("can_arrive_after_crew", True))
                    or float(r.get("minimum_quantity_before_crew", 0)) > 0)
        add(aid, r["asset_name"], qty * float(r["unit_mass_kg"]),
            defaults.CATEGORY_TO_BUCKET.get(r["category"], "Mobility"), aid,
            crit=str(r.get("criticality", "important")), divisible=False, pre_crew=pre_crew,
            prior=prior, same=same, qty=qty,
            volume=qty * float(r.get("unit_volume_m3", 0)), group=r["scenario_group"])
    return items


def compute_limiting_resource(a, habitat, power_gen, storage, ls, isru, excavation,
                              sustainment, usable_payload_kg, time) -> Dict[str, Any]:
    """Return the binding constraint as the candidate with the smallest slack.

    Slack is a dimensionless fraction: negative = the constraint is violated,
    small positive = tight, large = comfortable."""
    crew = max(float(a["crew_count"]), 1.0)
    candidates: Dict[str, float] = {}

    candidates["crew capacity"] = U.safe_div(habitat["capacity"] - crew, crew, 0.0)
    candidates["power"] = U.safe_div(power_gen["power_margin_kw"],
                                     max(power_gen["installed_continuous_kw"], 1e-9))
    candidates["energy storage"] = U.safe_div(
        storage["autonomy_achieved_sols"] - a["dust_storm_autonomy_sols"],
        max(float(a["dust_storm_autonomy_sols"]), 1e-9))

    # Consumables: slack = how far the landed stockpile endurance exceeds the
    # planning horizon (stay, or one resupply window, whichever is shorter).
    # Importing a consumable is the baseline plan, NOT a constraint violation;
    # a consumable only "limits" when it is under-provisioned for that horizon.
    horizon = max(min(time["surface_duration_sols"], time["resupply_window_sols"]), 1e-9)

    def endurance_slack(res: Dict[str, Any], rate: float) -> float:
        # Supply = landed imports + emergency reserve + local production
        # (ISRU for water/O2, grown food for food).
        supply = (res["import_required_kg"] + res["storage_required_kg"]
                  + res.get("isru_produced_kg", 0.0) + res.get("produced_kg", 0.0))
        return U.safe_div(supply, max(rate, 1e-9)) / horizon - 1.0

    o2 = ls["oxygen"]
    candidates["oxygen"] = endurance_slack(o2, o2["makeup_rate_kg_per_sol"])
    w = ls["water"]
    candidates["water"] = endurance_slack(w, w["makeup_rate_kg_per_sol"])
    f = ls["food"]
    candidates["food"] = endurance_slack(f, crew * f["rate_kg_per_crew_sol"])

    if isru["oxygen"]["units"] > 0:
        candidates["ISRU throughput"] = U.safe_div(
            isru["oxygen"]["produced_per_sol"] - isru["oxygen"]["required_per_sol"],
            max(isru["oxygen"]["required_per_sol"], 1e-9))
    if excavation["demand_kg_per_sol"] > 0:
        candidates["excavation throughput"] = U.safe_div(
            excavation["capacity_kg_per_sol"] - excavation["demand_kg_per_sol"],
            max(excavation["demand_kg_per_sol"], 1e-9))

    cargo_per_window = usable_payload_kg  # one Starship/window baseline
    candidates["resupply cadence"] = U.safe_div(
        cargo_per_window - sustainment["resupply"]["total_kg"],
        max(sustainment["resupply"]["total_kg"], 1e-9))

    ranked = sorted(candidates.items(), key=lambda kv: kv[1])
    name, slack = ranked[0]
    return {"name": name, "slack": slack, "ranked": ranked}


# ---------------------------------------------------------------------------
# Orchestration.
# ---------------------------------------------------------------------------

def run_model(assumptions: Dict[str, Any],
              assets: Optional[List[Dict[str, Any]]] = None,
              dependencies: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Run the full Mars logistics calculation and return the results dict."""
    a = dict(defaults.DEFAULT_ASSUMPTIONS)
    a.update(assumptions or {})
    assets = assets if assets is not None else defaults.default_assets()

    time = compute_time(a)
    duration = time["surface_duration_sols"]
    usable_payload_kg = compute_usable_payload(a)

    habitat = compute_habitat(a)
    ls = compute_life_support(a, duration)

    # ISRU bundle (crew O2 already sized inside life support; re-expose here).
    o2_isru = compute_oxygen_isru(a, ls["oxygen"]["makeup_rate_kg_per_sol"])
    water_isru = compute_water_isru(a, ls["water"]["makeup_rate_kg_per_sol"])
    prop_isru = compute_propellant_isru(a, o2_isru["effective_output_per_unit"])
    isru = {
        "oxygen": o2_isru, "water": water_isru, "propellant": prop_isru,
        "crew_survival_mass_kg": o2_isru["mass_kg"] + water_isru["mass_kg"],
        "crew_survival_power_kw": o2_isru["power_kw"] + water_isru["power_kw"],
        "propellant_mass_kg": prop_isru["mass_kg"], "propellant_power_kw": prop_isru["power_kw"],
        "total_mass_kg": o2_isru["mass_kg"] + water_isru["mass_kg"] + prop_isru["mass_kg"],
        "total_power_kw": o2_isru["power_kw"] + water_isru["power_kw"] + prop_isru["power_kw"],
    }

    eclss_power_kw = float(a["eclss_power_kw_per_crew"]) * float(a["crew_count"])
    eclss = {
        "power_kw": eclss_power_kw,
        "spares_total_kg": float(a["crew_count"]) * float(a["ECLSS_spares_kg_per_crew_sol"]) * duration,
        "filters_total_kg": float(a["crew_count"]) * float(a["ECLSS_filter_sorbent_kg_per_crew_sol"]) * duration,
    }

    # Power-unit / ISRU-unit counts (for asset quantity scaling). Power-unit
    # count needs the generation sizing, so we do a first pass with 0 and a
    # cheap second pass below once required generation is known.
    isru_unit_count = o2_isru["units"] + water_isru["units"]
    active_assets = compute_asset_quantities(assets, a, habitat["count"], 0, isru_unit_count)

    power = compute_power_balance(active_assets, a, habitat, eclss_power_kw, isru["total_power_kw"])
    power_gen = compute_generation(a, power, time)
    storage = compute_energy_storage(a, power["critical_load_kw"])
    distribution = compute_distribution(a, power["required_generation_kw"])
    power.update(power_gen)
    power_unit_count = U.ceil_units(
        U.safe_div(power["required_generation_kw"], float(a["power_string_size_kw"])))

    # Re-resolve quantities now that power_unit_count is known (cheap second pass).
    active_assets = compute_asset_quantities(assets, a, habitat["count"], power_unit_count, isru_unit_count)

    # Excavation throughput vs ISRU regolith demand.
    excavator_capacity = 0.0
    for r in active_assets:
        if r["active"] and r["category"] == "mobility_excavation":
            excavator_capacity += r["quantity_required"] * float(r.get("production_kg_per_sol", 0))
    excavation = {
        "demand_kg_per_sol": water_isru.get("regolith_demand_per_sol", 0.0),
        "capacity_kg_per_sol": excavator_capacity,
        "units": int(sum(r["quantity_required"] for r in active_assets
                         if r["active"] and r["category"] == "mobility_excavation")),
    }

    buckets = _bucket_masses(a, time, ls, habitat, isru, power_gen, storage,
                             distribution, active_assets, eclss)
    initial_landed = sum(buckets.values())
    pre_crew_mass = sum(m for b, m in buckets.items() if b in _PRE_CREW_BUCKETS)
    post_crew_mass = initial_landed - pre_crew_mass
    top_drivers = sorted(((b, m) for b, m in buckets.items() if m > 0),
                         key=lambda kv: kv[1], reverse=True)[:5]

    installed_hardware = (habitat["mass_total_kg"] + power_gen["generation_mass_kg"]
                          + storage["battery_mass_kg"] + distribution["cable_mass_kg"]
                          + isru["total_mass_kg"]
                          + sum(r["quantity_required"] * float(r["unit_mass_kg"])
                                for r in active_assets if r["active"]
                                and r["category"] not in defaults.FORMULA_COMPUTED_CATEGORIES))
    sustainment = compute_sustainment(a, time, ls, installed_hardware, usable_payload_kg)

    # Cargo manifest via dependency-aware packing.
    cargo_items = build_cargo_items(a, ls, habitat, isru, power_gen, storage,
                                    distribution, active_assets, eclss, buckets)
    missions = pack_missions(cargo_items, usable_payload_kg,
                             float(a["maximum_volume_m3_per_starship"]))
    dep_violations = verify_dependencies(missions)
    crew_index = crew_arrival_mission_index(missions)
    pre_crew_missions = sum(
        1 for m in missions if any(it.must_arrive_before_crew for it in m.items))

    # Crew endurance = how long the full landed stockpile sustains the crew.
    # Supply = landed makeup imports + emergency reserve + local ISRU production;
    # consumption is the makeup (net of recovery) rate for water/O2 and the gross
    # rate for food. This is what the dashboard reports as max crew-sols.
    crew = float(a["crew_count"])
    o2_supply = (ls["oxygen"]["import_required_kg"] + ls["oxygen"]["storage_required_kg"]
                 + ls["oxygen"]["isru_produced_kg"])
    w_supply = (ls["water"]["import_required_kg"] + ls["water"]["storage_required_kg"]
                + ls["water"]["isru_produced_kg"])
    f_supply = (ls["food"]["import_required_kg"] + ls["food"]["storage_required_kg"]
                + ls["food"]["produced_kg"])
    o2_rate = max(ls["oxygen"]["makeup_rate_kg_per_sol"], 1e-9)
    w_rate = max(ls["water"]["makeup_rate_kg_per_sol"], 1e-9)
    f_rate = max(crew * ls["food"]["rate_kg_per_crew_sol"], 1e-9)
    endurance_sols = min(U.safe_div(o2_supply, o2_rate), U.safe_div(w_supply, w_rate),
                         U.safe_div(f_supply, f_rate))
    crew_endurance = {"max_crew_sols": endurance_sols * crew,
                      "max_crew_days": U.sols_to_earth_days(endurance_sols) * crew,
                      "endurance_sols": endurance_sols}

    # Activation flags for readiness.
    def any_active(cats):
        return any(r["active"] and r["category"] in cats and r["quantity_required"] > 0
                   for r in active_assets)
    flags = {
        "comms_online": any_active({"communications"}),
        "thermal_online": habitat["thermal_power_kw"] > 0,
        "mobility_available": any_active({"mobility_excavation", "mobility_logistics",
                                          "mobility_robotics"}),
        "unloading_available": any(r["active"] and r["asset_id"] == "cargo_handling_rover_heavy"
                                   and r["quantity_required"] > 0 for r in active_assets),
        "medical_available": float(a["medical_module_mass_kg"]) > 0,
    }

    excavation_limit = {"demand_kg_per_sol": excavation["demand_kg_per_sol"],
                        "capacity_kg_per_sol": excavation["capacity_kg_per_sol"]}
    limiting = compute_limiting_resource(a, habitat, power_gen, storage, ls, isru,
                                         excavation_limit, sustainment, usable_payload_kg, time)

    setup_missions_simple = U.ceil_units(U.safe_div(initial_landed, usable_payload_kg))

    results: Dict[str, Any] = {
        "assumptions": a,
        "time": time,
        "usable_payload_kg": usable_payload_kg,
        "landed_payload_kg": float(a["landed_payload_kg_per_starship"]),
        "life_support": ls,
        "habitat": habitat,
        "eclss": eclss,
        "isru": isru,
        "excavation": excavation,
        "power": power,
        "storage": storage,
        "distribution": distribution,
        "assets": {"quantities": active_assets,
                   "active_ids": [r["asset_id"] for r in active_assets if r["active"]],
                   "power_unit_count": power_unit_count, "isru_unit_count": isru_unit_count},
        "mass": {"buckets": buckets, "initial_landed_kg": initial_landed,
                 "pre_crew_kg": pre_crew_mass, "post_crew_kg": post_crew_mass,
                 "top_drivers": top_drivers},
        "sustainment": sustainment,
        "missions": {
            "manifest": missions,
            "setup_missions_simple": setup_missions_simple,
            "setup_missions_packed": len(missions),
            "pre_crew_missions": pre_crew_missions,
            "crew_arrival_index": crew_index,
            "dependency_violations": dep_violations,
        },
        "crew_endurance": crew_endurance,
        "limiting_resource": limiting,
        "flags": flags,
        "warnings": list(defaults.PLACEHOLDER_WARNINGS),
    }
    results["readiness"] = validation.evaluate_readiness(results)
    results["dashboard"] = build_dashboard(results)
    return results


def build_dashboard(results: Dict[str, Any]) -> Dict[str, Any]:
    a = results["assumptions"]
    mass = results["mass"]
    power = results["power"]
    storage = results["storage"]
    ls = results["life_support"]
    isru = results["isru"]
    missions = results["missions"]
    return {
        "scenario_name": a["scenario_name"],
        "crew_count": a["crew_count"],
        "operating_mode": a["operating_mode"],
        "surface_duration_sols": results["time"]["surface_duration_sols"],
        "surface_duration_earth_days": results["time"]["surface_duration_earth_days"],
        "landed_payload_kg": results["landed_payload_kg"],
        "usable_payload_kg": results["usable_payload_kg"],
        "total_initial_landed_mass_kg": mass["initial_landed_kg"],
        "total_pre_crew_landed_mass_kg": mass["pre_crew_kg"],
        "total_post_crew_landed_mass_kg": mass["post_crew_kg"],
        "cargo_starships_pre_crew": missions["pre_crew_missions"],
        "cargo_starships_full_setup": missions["setup_missions_packed"],
        "cargo_starships_per_resupply_window": results["sustainment"]["resupply"]["starships_required"],
        "resupply_mass_per_window_kg": results["sustainment"]["resupply"]["total_kg"],
        "total_installed_power_capacity_kw": power["installed_continuous_kw"],
        "total_critical_load_kw": power["critical_load_kw"],
        "power_margin_kw": power["power_margin_kw"],
        "total_energy_storage_kwh": storage["installed_capacity_kwh"],
        "storage_autonomy_sols": storage["autonomy_achieved_sols"],
        "net_water_import_kg": ls["water"]["import_required_kg"],
        "net_o2_import_kg": ls["oxygen"]["import_required_kg"],
        "net_food_import_kg": ls["food"]["import_required_kg"],
        "water_isru_production_kg_per_sol": isru["water"]["produced_per_sol"],
        "oxygen_isru_production_kg_per_sol": isru["oxygen"]["produced_per_sol"],
        "max_crew_sols_supportable": results["crew_endurance"]["max_crew_sols"],
        "limiting_resource": results["limiting_resource"]["name"],
        "top_five_mass_drivers": mass["top_drivers"],
        "crew_arrival_allowed": results["readiness"]["crew_arrival_allowed"]
        if "readiness" in results else None,
    }
