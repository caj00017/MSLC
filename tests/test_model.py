"""Test suite for the Mars Surface Logistics Calculator.

Pure standard library (``unittest``) so it runs on a bare interpreter:

    python -m unittest discover -s tests        # or
    python tests/test_model.py

The suite covers every validation item the spec enumerates, anchored on the
legacy lunar reference numbers, which act as a calculation oracle.
"""

import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mars_logistics import defaults, legacy, units as U
from mars_logistics import io_utils
from mars_logistics.model import (
    run_model, compute_time, compute_usable_payload, compute_life_support,
    compute_oxygen_isru, compute_habitat, compute_energy_storage,
)
from mars_logistics.packing import CargoItem, pack_missions, verify_dependencies


def legacy_life_support_assumptions():
    """Legacy lunar base inputs (50 crew, 30 sols), EVA/leak zeroed so the
    makeup equals the documented recovery-adjusted values."""
    a = defaults.default_assumptions()
    a.update({
        "crew_count": 50, "surface_duration_sols": 30,
        "water_kg_per_crew_sol": 8.0, "water_recovery_rate": 0.98,
        "oxygen_kg_per_crew_sol": 1.1, "oxygen_recovery_rate": 0.45,
        "eva_hours_per_crew_sol": 0.0, "airlock_cycles_per_sol": 0.0,
        "cabin_leakage_kg_per_sol": 0.0, "include_greenhouse": False,
        "oxygen_ISRU_enabled": False, "water_ISRU_enabled": False,
        "food_closure_fraction": 0.0,
    })
    return a


class TestTimeConversion(unittest.TestCase):
    def test_sol_earth_day_conversion(self):
        self.assertAlmostEqual(U.EARTH_DAYS_PER_SOL, 24.65979 / 24.0, places=9)
        self.assertAlmostEqual(U.sols_to_earth_days(100), 100 * 24.65979 / 24.0, places=6)
        self.assertAlmostEqual(U.earth_days_to_sols(U.sols_to_earth_days(42)), 42, places=9)

    def test_resupply_window_timing(self):
        a = defaults.default_assumptions()
        a["resupply_window_months"] = 26
        t = compute_time(a)
        self.assertAlmostEqual(t["resupply_window_earth_days"], 26 * 30.4375, places=6)
        self.assertAlmostEqual(t["resupply_window_sols"],
                               26 * 30.4375 / (24.65979 / 24.0), places=6)


class TestPowerEnergySeparation(unittest.TestCase):
    def test_kw_vs_kwh(self):
        # Energy is power * time; never the same number unless time == 1 h.
        self.assertAlmostEqual(U.energy_kwh_per_sol(10.0), 10.0 * 24.65979, places=6)
        self.assertAlmostEqual(U.average_power_kw(40.0, 0.25), 10.0, places=9)
        self.assertAlmostEqual(U.energy_kwh_from_power(6.15, 336.0), 2066.4, places=6)

    def test_continuous_load_energy_consistency(self):
        # A purely continuous load's sol energy equals power * hours_per_sol.
        a = defaults.default_assumptions()
        r = run_model(a)
        hab_cont = r["power"]["habitat_continuous_kw"]
        hab_energy = U.energy_kwh_from_power(hab_cont, U.HOURS_PER_SOL)
        self.assertAlmostEqual(hab_energy, hab_cont * 24.65979, places=6)


class TestLegacyReproduction(unittest.TestCase):
    def test_legacy_day_power_totals(self):
        dp = legacy.legacy_day_power()
        self.assertAlmostEqual(dp["total_peak_power_kw"], 108.15, places=2)
        self.assertAlmostEqual(dp["total_continuous_power_kw"], 62.4, places=2)

    def test_legacy_night_energy_totals(self):
        self.assertAlmostEqual(legacy.legacy_night_energy("thrive")["night_energy_kwh"],
                               17522.4, places=1)
        self.assertAlmostEqual(legacy.legacy_night_energy("survive")["night_energy_kwh"],
                               2066.4, places=1)

    def test_legacy_battery_sizing(self):
        self.assertEqual(legacy.legacy_night_energy("thrive")["battery_units"], 1947)
        self.assertEqual(legacy.legacy_night_energy("survive")["battery_units"], 230)

    def test_legacy_total_mass_reproduction(self):
        tm = legacy.legacy_total_mass()
        self.assertAlmostEqual(tm["total_thrive_kg"], 99174.4, places=1)
        self.assertAlmostEqual(tm["total_survive_kg"], 21891.4, places=1)
        self.assertAlmostEqual(tm["total_fsp_kg"], 9294.2, places=1)

    def test_legacy_habitat_water_and_oxygen(self):
        ls = compute_life_support(legacy_life_support_assumptions(), 30)
        self.assertAlmostEqual(ls["water"]["gross_kg"], 12000.0, places=3)
        self.assertAlmostEqual(ls["water"]["makeup_before_isru_kg"], 240.0, places=3)
        self.assertAlmostEqual(ls["oxygen"]["gross_kg"], 1650.0, places=3)
        self.assertAlmostEqual(ls["oxygen"]["makeup_before_isru_kg"], 907.5, places=3)


class TestStarshipPayload(unittest.TestCase):
    def test_usable_payload_calculation(self):
        a = defaults.default_assumptions()
        a.update({"landed_payload_kg_per_starship": 100000,
                  "packing_efficiency": 0.90, "unallocated_margin_percent": 0.20})
        self.assertAlmostEqual(compute_usable_payload(a), 72000.0, places=6)

    def test_sensitivity_payload_cases(self):
        # Every documented payload case yields the expected usable payload.
        for landed in defaults.SENSITIVITY_PAYLOAD_CASES_KG:
            a = defaults.default_assumptions()
            a["landed_payload_kg_per_starship"] = landed
            self.assertAlmostEqual(compute_usable_payload(a), landed * 0.9 * 0.8, places=6)


class TestConsumablesWithRecovery(unittest.TestCase):
    def test_recovery_reduces_makeup(self):
        ls = compute_life_support(legacy_life_support_assumptions(), 30)
        # 98% water recovery -> 2% of gross is makeup.
        self.assertAlmostEqual(ls["water"]["makeup_before_isru_kg"],
                               ls["water"]["gross_kg"] * 0.02, places=6)
        # 45% O2 recovery -> 55% of gross is makeup (no EVA/leak here).
        self.assertAlmostEqual(ls["oxygen"]["makeup_before_isru_kg"],
                               ls["oxygen"]["gross_kg"] * 0.55, places=6)


class TestIsruSizing(unittest.TestCase):
    def test_oxygen_isru_unit_sizing(self):
        a = defaults.default_assumptions()
        a.update({"oxygen_ISRU_enabled": True, "oxygen_ISRU_output_kg_per_sol": 15.6,
                  "oxygen_ISRU_utilization_factor": 1.0, "oxygen_ISRU_availability": 1.0})
        # Legacy crew O2 demand of 30.25 kg/sol -> 1.9391 baseline systems -> 2 units.
        isru = compute_oxygen_isru(a, 30.25)
        self.assertAlmostEqual(isru["effective_output_per_unit"], 15.6, places=6)
        self.assertAlmostEqual(isru["fractional_units"], 1.93910, places=4)
        self.assertEqual(isru["units"], 2)
        self.assertAlmostEqual(isru["power_kw"], 2 * 15.0, places=6)

    def test_water_isru_throughput(self):
        a = defaults.default_assumptions()
        a.update({"water_ISRU_enabled": True, "regolith_processed_kg_per_sol_per_unit": 1000,
                  "regolith_water_mass_fraction": 0.05, "water_extraction_efficiency": 0.5,
                  "water_ISRU_availability": 1.0})
        from mars_logistics.model import compute_water_isru
        wi = compute_water_isru(a, 50.0)  # need 50 kg/sol; unit makes 1000*0.05*0.5 = 25
        self.assertAlmostEqual(wi["effective_output_per_unit"], 25.0, places=6)
        self.assertEqual(wi["units"], 2)


class TestHabitatSizing(unittest.TestCase):
    def test_habitat_quantity_sizing(self):
        a = defaults.default_assumptions()
        a.update({"crew_count": 50, "crew_capacity_per_habitat": 4,
                  "minimum_habitat_redundancy": 1})
        hab = compute_habitat(a)
        self.assertEqual(hab["count_base"], math.ceil(50 / 4))  # 13
        self.assertEqual(hab["count"], 14)
        self.assertEqual(hab["capacity"], 56)


class TestEnergyStorage(unittest.TestCase):
    def test_battery_formula(self):
        a = defaults.default_assumptions()
        a.update({"critical_load_autonomy_sols": 1.0, "dust_storm_autonomy_sols": 1.0,
                  "power_outage_autonomy_sols": 1.0, "battery_roundtrip_efficiency": 1.0,
                  "battery_depth_of_discharge": 1.0, "battery_specific_energy_kWh_per_kg": 0.2,
                  "battery_unit_mass_kg": 45.0})
        st = compute_energy_storage(a, critical_load_kw=10.0)
        expected_kwh = 10.0 * U.HOURS_PER_SOL  # 1 sol autonomy, rt=dod=1
        self.assertAlmostEqual(st["storage_kwh_required"], expected_kwh, places=6)
        expected_mass = expected_kwh / 0.2
        self.assertEqual(st["battery_units"], math.ceil(expected_mass / 45.0))


class TestMissionPacking(unittest.TestCase):
    def test_mass_margin_never_negative(self):
        items = [CargoItem(f"i{i}", f"item {i}", mass_kg=30000, volume_m3=0,
                           bucket="Mobility", dep_key=f"i{i}") for i in range(5)]
        missions = pack_missions(items, usable_payload_kg=72000, max_volume_m3=None)
        for m in missions:
            self.assertLessEqual(m.allocated_mass_kg, 72000 + 1e-6)
            self.assertGreaterEqual(72000 - m.allocated_mass_kg, -1e-6)
        # 5 * 30 t = 150 t -> needs 3 missions (72 t each).
        self.assertEqual(len(missions), 3)

    def test_volume_constraint(self):
        items = [CargoItem(f"v{i}", f"vol {i}", mass_kg=1000, volume_m3=600,
                           bucket="Mobility", dep_key=f"v{i}") for i in range(3)]
        missions = pack_missions(items, usable_payload_kg=72000, max_volume_m3=1000)
        for m in missions:
            self.assertLessEqual(m.allocated_volume_m3, 1000 + 1e-6)
        self.assertEqual(len(missions), 3)  # volume-limited, one per mission

    def test_oversized_atomic_item_flagged(self):
        items = [CargoItem("big", "oversized", mass_kg=90000, volume_m3=0,
                           bucket="Habitat & crew systems", dep_key="big")]
        missions = pack_missions(items, usable_payload_kg=72000, max_volume_m3=None)
        self.assertTrue(any(m.overweight for m in missions))


class TestDependencyChecking(unittest.TestCase):
    def test_prior_dependency_lands_earlier(self):
        a = CargoItem("a", "prereq", mass_kg=40000, volume_m3=0, bucket="b", dep_key="a")
        b = CargoItem("b", "dependent", mass_kg=40000, volume_m3=0, bucket="b", dep_key="b",
                      depends_on_prior=["a"])
        missions = pack_missions([b, a], usable_payload_kg=72000, max_volume_m3=None)
        idx = {it.dep_key: m.index for m in missions for it in m.items}
        self.assertLess(idx["a"], idx["b"])
        self.assertEqual(verify_dependencies(missions), [])

    def test_same_or_prior_allows_same_mission(self):
        a = CargoItem("a", "prereq", mass_kg=20000, volume_m3=0, bucket="b", dep_key="a")
        b = CargoItem("b", "dependent", mass_kg=20000, volume_m3=0, bucket="b", dep_key="b",
                      depends_on_same_or_prior=["a"])
        missions = pack_missions([b, a], usable_payload_kg=72000, max_volume_m3=None)
        idx = {it.dep_key: m.index for m in missions for it in m.items}
        self.assertLessEqual(idx["a"], idx["b"])
        self.assertEqual(verify_dependencies(missions), [])

    def test_model_manifest_has_no_violations(self):
        r = run_model(defaults.default_assumptions())
        self.assertEqual(r["missions"]["dependency_violations"], [])


class TestResupply(unittest.TestCase):
    def test_resupply_mass_components_sum(self):
        r = run_model(defaults.default_assumptions())
        rs = r["sustainment"]["resupply"]
        recomputed = (rs["consumables_kg"] + rs["spares_kg"] + rs["medical_kg"]
                      + rs["replacement_kg"] + rs["science_kg"] + rs["contingency_kg"])
        self.assertAlmostEqual(rs["total_kg"], recomputed, places=3)
        self.assertEqual(rs["starships_required"],
                         math.ceil(rs["total_kg"] / r["usable_payload_kg"]))


class TestGuards(unittest.TestCase):
    def test_no_negative_imports_after_isru(self):
        a = defaults.default_assumptions()
        # ISRU output far exceeds demand -> O2 import must clamp to zero, not go negative.
        a.update({"oxygen_ISRU_enabled": True, "oxygen_ISRU_output_kg_per_sol": 10000,
                  "crew_count": 1})
        ls = compute_life_support(a, 100)
        self.assertGreaterEqual(ls["oxygen"]["import_required_kg"], 0.0)
        self.assertEqual(ls["oxygen"]["import_required_kg"], 0.0)

    def test_no_divide_by_zero_when_production_zero(self):
        a = defaults.default_assumptions()
        a.update({"oxygen_ISRU_enabled": True, "oxygen_ISRU_output_kg_per_sol": 0.0})
        isru = compute_oxygen_isru(a, 30.0)  # effective output 0 -> must not raise
        self.assertEqual(isru["units"], 0)
        self.assertEqual(isru["mass_kg"], 0.0)

    def test_degenerate_scenario_does_not_crash(self):
        a = defaults.default_assumptions()
        a.update({"effective_sun_hours_per_sol": 0.0, "battery_specific_energy_kWh_per_kg": 0.0,
                  "crew_capacity_per_habitat": 0.0, "oxygen_ISRU_output_kg_per_sol": 0.0,
                  "packing_efficiency": 0.0})
        r = run_model(a)  # must complete without ZeroDivisionError
        self.assertIn("dashboard", r)


class TestReadinessGating(unittest.TestCase):
    def test_default_scenario_allows_crew_arrival(self):
        r = run_model(defaults.default_assumptions())
        self.assertTrue(r["readiness"]["crew_arrival_allowed"])

    def test_no_crew_arrival_when_readiness_fails(self):
        a = defaults.default_assumptions()
        # Disallow pre-deploy while pre-crew cargo is still required -> RED, blocked.
        a["predeploy_cargo_missions_allowed"] = False
        r = run_model(a)
        self.assertFalse(r["readiness"]["crew_arrival_allowed"])
        self.assertTrue(len(r["readiness"]["blocking_checks"]) >= 1)


class TestModeScaling(unittest.TestCase):
    def test_capability_increases_mass(self):
        masses = []
        for mode in defaults.OPERATING_MODES:
            a = defaults.default_assumptions()
            a["operating_mode"] = mode
            masses.append(run_model(a)["mass"]["initial_landed_kg"])
        # More capability never reduces required landed mass.
        for lighter, heavier in zip(masses, masses[1:]):
            self.assertLessEqual(lighter, heavier + 1e-6)


class TestRoundTrip(unittest.TestCase):
    def test_scenario_json_round_trip(self):
        a = defaults.default_assumptions()
        assets = defaults.default_assets()
        deps = defaults.default_dependencies()
        text = io_utils.scenario_to_json(a, assets, deps)
        a2, assets2, deps2 = io_utils.scenario_from_json(text)
        self.assertEqual(a2["crew_count"], a["crew_count"])
        self.assertEqual(len(assets2), len(assets))
        self.assertEqual(len(deps2), len(deps))

    def test_assets_csv_round_trip(self):
        # The meaningful invariant is that dump-after-load is a fixed point:
        # once assets have been through a typed CSV load, re-serialising is stable.
        assets = defaults.default_assets()
        canonical = io_utils.assets_to_csv(io_utils.assets_from_csv(
            io_utils.assets_to_csv(assets)))
        reloaded = io_utils.assets_to_csv(io_utils.assets_from_csv(canonical))
        self.assertEqual(reloaded, canonical)
        # And the values survive: a spot-check on a known asset.
        loaded = {r["asset_id"]: r for r in io_utils.assets_from_csv(canonical)}
        self.assertAlmostEqual(loaded["o2fr_pilot_plant"]["unit_mass_kg"], 1000.0)
        self.assertAlmostEqual(loaded["power_cable"]["unit_mass_kg"], 432.6)


if __name__ == "__main__":
    unittest.main(verbosity=2)
