"""Canonical default assumptions, field metadata, seed asset catalog, and
default dependency edges for the Mars Surface Logistics Calculator.

Design rules honoured here:
    * Every number is a *named* variable. No hidden constants.
    * Each assumption carries metadata: section, label, unit, help text, and a
      ``source`` class so the UI can label legacy/placeholder values honestly.
    * Assumptions are a flat ``{key: value}`` dict. Flat makes scenario import,
      export, and sensitivity overrides trivial and unambiguous.

Source classes
--------------
    LEGACY  - lunar-derived placeholder copied from the legacy spreadsheets.
              NOT a validated Mars value. Surfaced with a warning.
    MARS_PH - Mars-oriented engineering *placeholder*. Plausible, not designed.
    CONST   - a defensible physical constant (e.g. sol length, month length).
    REVIEW  - explicitly requires engineering review before use.
"""

from __future__ import annotations

from typing import Any, Dict, List

# Source-class identifiers (named, so the UI/README can reference them).
LEGACY = "legacy_lunar_analog_placeholder"
MARS_PH = "mars_engineering_placeholder"
CONST = "mars_constant"
REVIEW = "needs_engineering_review"

PLACEHOLDER_SOURCES = (LEGACY, REVIEW)

# Operating modes, in increasing order of capability.
OPERATING_MODES: List[str] = ["survival", "exploration", "science", "thrive"]

#: Which asset ``scenario_group`` values are active in each operating mode.
MODE_ACTIVE_GROUPS: Dict[str, List[str]] = {
    "survival": ["survival"],
    "exploration": ["survival", "exploration"],
    "science": ["survival", "exploration", "science"],
    "thrive": ["survival", "exploration", "science", "thrive"],
}

#: Sensitivity payload cases from the spec (kg of landed payload per Starship).
SENSITIVITY_PAYLOAD_CASES_KG: List[float] = [50000, 75000, 100000, 125000, 150000]

# Asset categories whose mass/power the Mars model sizes from first-principles
# *formulas* (power, storage, distribution, habitat, crew-O2 ISRU). Their
# catalog rows are legacy analogs kept for reference and for the legacy
# reproduction case; they are excluded from the Mars discrete-cargo rollup so
# nothing is double-counted.
FORMULA_COMPUTED_CATEGORIES = frozenset(
    {"power", "energy_storage", "power_distribution", "habitat", "ISRU"}
)


# ---------------------------------------------------------------------------
# Assumption field specifications.
# Each tuple: (key, default, section, unit, source, help)
# DEFAULT_ASSUMPTIONS and FIELD_METADATA are derived from this single list.
# ---------------------------------------------------------------------------
_FIELDS: List[tuple] = [
    # ---- A. Scenario -------------------------------------------------------
    ("scenario_name", "Mars survival baseline (engineering placeholder)",
     "Scenario", "text", MARS_PH, "Human-readable name stored with the scenario."),
    ("crew_count", 4, "Scenario", "people", MARS_PH,
     "Number of humans to sustain on the surface."),
    ("surface_duration_sols", 500, "Scenario", "sols", MARS_PH,
     "Crewed surface stay length. ~500 sols ~= one conjunction-class stay."),
    ("crew_arrival_sol", 0, "Scenario", "sol", MARS_PH,
     "Sol index at which crew arrives. Pre-deploy missions land before this."),
    ("predeploy_cargo_missions_allowed", True, "Scenario", "bool", MARS_PH,
     "If true, cargo may be landed before crew to satisfy readiness."),
    ("operating_mode", "survival", "Scenario", "enum", MARS_PH,
     "survival | exploration | science | thrive. Controls which assets activate."),
    ("resupply_window_months", 26, "Scenario", "Earth months", CONST,
     "Mars transfer/resupply opportunity spacing. ~26 Earth months."),
    ("target_days_of_supply_after_resupply", 780, "Scenario", "Earth days", MARS_PH,
     "Stockpile target immediately after each resupply (one synodic cycle ~780 d)."),
    ("emergency_reserve_sols", 60, "Scenario", "sols", MARS_PH,
     "Emergency reserve of each consumable, expressed as sols of full-crew demand."),
    ("contingency_margin_percent", 0.15, "Scenario", "fraction", MARS_PH,
     "Top-level contingency margin applied to resupply mass."),
    ("confidence_margin_percent", 0.10, "Scenario", "fraction", REVIEW,
     "Extra margin reflecting low confidence in placeholder inputs."),
    ("include_greenhouse", False, "Scenario", "bool", MARS_PH,
     "Add greenhouse water/energy/mass loads and food-closure contribution."),
    ("include_propellant_isru", False, "Scenario", "bool", MARS_PH,
     "Add return-propellant ISRU (kept entirely separate from crew O2)."),
    ("include_surface_construction", False, "Scenario", "bool", MARS_PH,
     "Force construction assets (assembly, construction rover) regardless of mode."),
    ("include_pressurized_rovers", False, "Scenario", "bool", MARS_PH,
     "Reserve mobility mass for pressurized exploration rovers."),
    ("include_return_vehicle_support", False, "Scenario", "bool", MARS_PH,
     "Account for return-vehicle servicing loads (couples to propellant ISRU)."),

    # ---- B. Starship cargo -------------------------------------------------
    ("landed_payload_kg_per_starship", 100000, "Starship cargo", "kg", REVIEW,
     "Landed Mars cargo payload per Starship. NOT a fixed known value - configure it."),
    ("packing_efficiency", 0.90, "Starship cargo", "fraction", MARS_PH,
     "Fraction of payload mass that is usable after packing inefficiency."),
    ("unallocated_margin_percent", 0.20, "Starship cargo", "fraction", MARS_PH,
     "Reserved/unallocated payload fraction (held back from planning)."),
    ("maximum_volume_m3_per_starship", 1000, "Starship cargo", "m^3", REVIEW,
     "Pressurized/unpressurized cargo volume per Starship. Placeholder."),
    ("launch_window_interval_months", 26, "Starship cargo", "Earth months", CONST,
     "Spacing between cargo launch opportunities."),
    ("cargo_mission_cost_per_kg", 0.0, "Starship cargo", "$/kg", REVIEW,
     "Optional landed cost per kg. 0 disables cost reporting."),
    ("mission_risk_loss_probability", 0.05, "Starship cargo", "fraction", REVIEW,
     "Per-mission probability of cargo loss (used by spare-mission policy)."),
    ("spare_cargo_mission_policy", "none", "Starship cargo", "enum", MARS_PH,
     "none | one_extra_per_window | probability_based."),

    # ---- C. Crew metabolic & ECLSS ----------------------------------------
    ("water_kg_per_crew_sol", 8.0, "Crew & ECLSS", "kg/crew/sol", LEGACY,
     "Total crew water demand per person per sol (potable + hygiene). Legacy=8."),
    ("oxygen_kg_per_crew_sol", 0.84, "Crew & ECLSS", "kg/crew/sol", MARS_PH,
     "Metabolic O2 per person per sol. ~0.84 kg (legacy lunar used 1.1)."),
    ("dry_food_kg_per_crew_sol", 0.62, "Crew & ECLSS", "kg/crew/sol", MARS_PH,
     "Dry food mass per person per sol."),
    ("hydrated_food_kg_per_crew_sol", 1.8, "Crew & ECLSS", "kg/crew/sol", MARS_PH,
     "As-served (hydrated) food mass per person per sol."),
    ("food_basis", "hydrated", "Crew & ECLSS", "enum", MARS_PH,
     "Which food rate drives stockpile mass: dry | hydrated."),
    ("CO2_generated_kg_per_crew_sol", 1.04, "Crew & ECLSS", "kg/crew/sol", MARS_PH,
     "CO2 produced per person per sol (sizing scrubber sorbent)."),
    ("water_recovery_rate", 0.90, "Crew & ECLSS", "fraction", MARS_PH,
     "Closed-loop water recovery fraction. Legacy lunar used 0.98."),
    ("oxygen_recovery_rate", 0.45, "Crew & ECLSS", "fraction", LEGACY,
     "O2 recovery fraction (e.g. CO2 reduction). Legacy=0.45."),
    ("food_closure_fraction", 0.0, "Crew & ECLSS", "fraction", MARS_PH,
     "Fraction of food grown locally. 0 = all food imported."),
    ("hygiene_water_mode", "standard", "Crew & ECLSS", "enum", MARS_PH,
     "minimal | standard | expanded (informational; adjust water rate to match)."),
    ("EVA_oxygen_kg_per_EVA_hour", 0.12, "Crew & ECLSS", "kg/EVA-hour", MARS_PH,
     "O2 consumed per EVA crew-hour."),
    ("EVA_water_kg_per_EVA_hour", 0.5, "Crew & ECLSS", "kg/EVA-hour", MARS_PH,
     "Water (sublimator/cooling) lost per EVA crew-hour."),
    ("eva_hours_per_crew_sol", 0.5, "Crew & ECLSS", "EVA-hour/crew/sol", MARS_PH,
     "Average EVA hours per crew member per sol."),
    ("airlock_loss_kg_per_cycle", 0.5, "Crew & ECLSS", "kg/cycle", MARS_PH,
     "Gas lost per airlock depress/repress cycle."),
    ("airlock_cycles_per_sol", 1.0, "Crew & ECLSS", "cycles/sol", MARS_PH,
     "Airlock cycles per sol across the whole base."),
    ("cabin_leakage_kg_per_sol", 0.5, "Crew & ECLSS", "kg/sol", MARS_PH,
     "Habitat atmosphere leakage per sol (whole base)."),
    ("ECLSS_spares_kg_per_crew_sol", 0.05, "Crew & ECLSS", "kg/crew/sol", REVIEW,
     "ECLSS spare-parts mass accrued per crew per sol."),
    ("ECLSS_filter_sorbent_kg_per_crew_sol", 0.10, "Crew & ECLSS", "kg/crew/sol", REVIEW,
     "Consumable filters/sorbent per crew per sol."),
    ("eclss_power_kw_per_crew", 0.6, "Crew & ECLSS", "kW/crew", MARS_PH,
     "Continuous ECLSS electrical load per crew member."),

    # ---- D. Habitat --------------------------------------------------------
    ("crew_capacity_per_habitat", 4, "Habitat", "people/habitat", MARS_PH,
     "Crew a single habitat module can support."),
    ("habitat_mass_kg", 20000, "Habitat", "kg", REVIEW,
     "Landed mass of one habitat module. Placeholder; needs design data."),
    ("habitat_power_continuous_kw", 15.0, "Habitat", "kW", MARS_PH,
     "Continuous electrical load per habitat (excludes ECLSS/thermal)."),
    ("habitat_power_peak_kw", 25.0, "Habitat", "kW", MARS_PH,
     "Peak electrical load per habitat."),
    ("habitat_volume_m3", 200, "Habitat", "m^3", MARS_PH,
     "Pressurized volume per habitat module."),
    ("radiation_shielding_mass_kg_per_habitat", 0.0, "Habitat", "kg", MARS_PH,
     "Imported shielding mass per habitat (0 if shielding is local regolith)."),
    ("shielding_local_material_fraction", 1.0, "Habitat", "fraction", REVIEW,
     "Fraction of shielding sourced locally; reduces imported shielding mass."),
    ("thermal_power_kw_per_habitat", 5.0, "Habitat", "kW", MARS_PH,
     "Continuous thermal-control electrical load per habitat."),
    ("deployment_equipment_mass_kg", 2000, "Habitat", "kg", MARS_PH,
     "One-time deployment/setup equipment mass."),
    ("habitat_lifetime_sols", 5000, "Habitat", "sols", REVIEW,
     "Service life of a habitat module."),
    ("habitat_spares_percent_per_year", 0.05, "Habitat", "fraction/yr", REVIEW,
     "Annual spares mass as a fraction of installed habitat mass."),
    ("minimum_habitat_redundancy", 1, "Habitat", "modules", MARS_PH,
     "Spare habitat modules beyond the count needed for crew capacity."),
    ("medical_module_mass_kg", 500, "Habitat", "kg", MARS_PH,
     "Medical / safe-haven module mass."),
    ("galley_hygiene_module_mass_kg", 800, "Habitat", "kg", MARS_PH,
     "Galley and hygiene module mass."),

    # ---- E. Power ----------------------------------------------------------
    ("power_architecture", "solar", "Power", "enum", MARS_PH,
     "solar | nuclear | hybrid. Selects the generation sizing path."),
    ("hybrid_nuclear_fraction", 0.5, "Power", "fraction", MARS_PH,
     "In hybrid mode, fraction of required generation served by nuclear."),
    ("solar_array_specific_power_kw_per_kg", 0.10, "Power", "kW/kg", REVIEW,
     "Array electrical output per kg at Mars insolation. Placeholder."),
    ("solar_array_degradation_percent_per_year", 0.02, "Power", "fraction/yr", MARS_PH,
     "Annual array performance loss (dust abrasion, UV)."),
    ("dust_derating_factor", 0.70, "Power", "fraction", MARS_PH,
     "Multiplier on array output for routine dust on panels (1.0 = clean)."),
    ("seasonal_derating_factor", 0.60, "Power", "fraction", MARS_PH,
     "Multiplier for orbital distance/season worst case."),
    ("effective_sun_hours_per_sol", 6.0, "Power", "hours/sol", REVIEW,
     "Full-output-equivalent sun hours per sol at the site."),
    ("nuclear_unit_power_kw", 40.0, "Power", "kW", MARS_PH,
     "Electrical output of one fission surface power unit."),
    ("nuclear_unit_mass_kg", 6000, "Power", "kg", REVIEW,
     "Landed mass of one fission surface power unit."),
    ("power_distribution_mass_kg_per_kw_km", 8.0, "Power", "kg/(kW*km)", LEGACY,
     "Cable specific mass. Legacy=8 kg per kW per km."),
    ("average_power_cable_length_km", 0.5, "Power", "km", LEGACY,
     "Average cable run length from generation to loads."),
    ("critical_load_autonomy_sols", 2.0, "Power", "sols", MARS_PH,
     "Sols of critical-load autonomy from storage (normal night/outage)."),
    ("dust_storm_autonomy_sols", 10.0, "Power", "sols", REVIEW,
     "Sols of critical-load autonomy required to ride out a dust storm."),
    ("power_outage_autonomy_sols", 1.0, "Power", "sols", MARS_PH,
     "Sols of autonomy for a generic power outage."),
    ("battery_specific_energy_kWh_per_kg", 0.20, "Power", "kWh/kg", LEGACY,
     "Energy storage specific energy. Legacy=0.2 (200 Wh/kg)."),
    ("battery_depth_of_discharge", 0.80, "Power", "fraction", MARS_PH,
     "Usable fraction of nameplate storage."),
    ("battery_roundtrip_efficiency", 0.90, "Power", "fraction", MARS_PH,
     "Charge/discharge round-trip efficiency."),
    ("battery_unit_mass_kg", 45.0, "Power", "kg", LEGACY,
     "Mass of one storage module. Legacy=45 kg."),
    ("inverter_power_processing_margin", 0.10, "Power", "fraction", MARS_PH,
     "Extra power-processing capacity above continuous load."),
    ("power_margin_percent", 0.20, "Power", "fraction", MARS_PH,
     "Generation margin above continuous demand."),
    ("simultaneity_factor", 1.0, "Power", "fraction", MARS_PH,
     "Fraction of peak loads assumed simultaneous (1.0 = all at once)."),

    # ---- F. ISRU -----------------------------------------------------------
    ("oxygen_ISRU_enabled", True, "ISRU", "bool", MARS_PH,
     "Produce crew-survival O2 locally (separate from propellant O2)."),
    ("oxygen_ISRU_unit_mass_kg", 1000, "ISRU", "kg", LEGACY,
     "Mass of one crew-O2 ISRU unit. Legacy baseline analog."),
    ("oxygen_ISRU_unit_power_kw", 15.0, "ISRU", "kW", LEGACY,
     "Power draw of one crew-O2 ISRU unit. Legacy baseline=15 kW."),
    ("oxygen_ISRU_output_kg_per_sol", 15.6, "ISRU", "kg/sol", LEGACY,
     "O2 output of one ISRU unit per sol. Legacy baseline=15.6."),
    ("oxygen_ISRU_utilization_factor", 1.0, "ISRU", "fraction", MARS_PH,
     "Fraction of nameplate output actually used."),
    ("oxygen_ISRU_availability", 0.90, "ISRU", "fraction", MARS_PH,
     "Operational availability of crew-O2 ISRU."),
    ("water_ISRU_enabled", False, "ISRU", "bool", MARS_PH,
     "Extract water from regolith/atmosphere locally."),
    ("water_extraction_unit_mass_kg", 800, "ISRU", "kg", REVIEW,
     "Mass of one water-extraction unit."),
    ("water_extraction_unit_power_kw", 10.0, "ISRU", "kW", REVIEW,
     "Power draw of one water-extraction unit."),
    ("regolith_processed_kg_per_sol_per_unit", 2700, "ISRU", "kg/sol", LEGACY,
     "Regolith throughput per excavation/processing unit per sol."),
    ("regolith_water_mass_fraction", 0.05, "ISRU", "fraction", REVIEW,
     "Water mass fraction of processed regolith. Highly site-dependent."),
    ("water_extraction_efficiency", 0.70, "ISRU", "fraction", REVIEW,
     "Fraction of available water actually captured."),
    ("water_ISRU_availability", 0.90, "ISRU", "fraction", MARS_PH,
     "Operational availability of water extraction."),
    ("propellant_ISRU_enabled", False, "ISRU", "bool", MARS_PH,
     "Produce return propellant. Entirely separate from crew O2."),
    ("propellant_O2_target_kg_per_window", 200000, "ISRU", "kg/window", REVIEW,
     "O2 to produce per launch window for return propellant."),
    ("propellant_CH4_target_kg_per_window", 60000, "ISRU", "kg/window", REVIEW,
     "CH4 to produce per launch window (if methane path enabled)."),
    ("propellant_production_deadline_sols", 480, "ISRU", "sols", MARS_PH,
     "Sols available to make the propellant target before departure."),
    ("propellant_storage_mass_fraction", 0.10, "ISRU", "fraction", REVIEW,
     "Tankage/storage mass as a fraction of stored propellant."),
    ("propellant_power_kw_per_kg_per_sol", 1.0, "ISRU", "kW/(kg/sol)", REVIEW,
     "Power per unit propellant production rate. Placeholder."),
    ("detailed_propellant_stoichiometry_enabled", False, "ISRU", "bool", MARS_PH,
     "Use Sabatier/electrolysis stoichiometry instead of the lumped estimate."),

    # ---- G. Greenhouse (active only when include_greenhouse) ---------------
    ("greenhouse_water_kg_per_crew_sol", 5.0, "Greenhouse", "kg/crew/sol", LEGACY,
     "Greenhouse water demand per crew per sol. Legacy=5."),
    ("greenhouse_energy_kWh_per_crew_sol", 20.0, "Greenhouse", "kWh/crew/sol", LEGACY,
     "Greenhouse lighting/energy per crew per sol. Legacy=20."),
    ("greenhouse_mass_kg_per_crew", 500, "Greenhouse", "kg/crew", REVIEW,
     "Greenhouse hardware mass allocated per crew member."),
    ("greenhouse_water_recovery_fraction", 0.95, "Greenhouse", "fraction", MARS_PH,
     "Fraction of greenhouse water recovered (transpiration capture)."),

    # ---- H. Margins / misc -------------------------------------------------
    ("storage_margin", 1.10, "Margins", "fraction", MARS_PH,
     "Multiplier on emergency-reserve stockpile sizing (1.10 = +10%)."),
    ("hardware_spares_percent_per_year", 0.05, "Margins", "fraction/yr", REVIEW,
     "Blended annual spares rate for power/ISRU/mobility hardware."),
    ("power_string_size_kw", 50.0, "Margins", "kW", MARS_PH,
     "Reference generation 'string' size used to count power units for scaling."),
    ("medical_resupply_kg_per_crew_window", 25.0, "Margins", "kg/crew/window", MARS_PH,
     "Medical consumable resupply mass per crew per window."),
    ("replacement_hardware_kg_per_window", 0.0, "Margins", "kg/window", MARS_PH,
     "Planned hardware replacement mass per resupply window."),
    ("science_payload_replenishment_kg_per_window", 0.0, "Margins", "kg/window", MARS_PH,
     "Science consumable/payload replenishment per resupply window."),
]


# Derived dictionaries -------------------------------------------------------

DEFAULT_ASSUMPTIONS: Dict[str, Any] = {key: default for key, default, *_ in _FIELDS}

FIELD_METADATA: Dict[str, Dict[str, str]] = {
    key: {"section": section, "unit": unit, "source": source, "help": help_text}
    for key, _default, section, unit, source, help_text in _FIELDS
}

#: Sections in display order.
SECTION_ORDER: List[str] = [
    "Scenario", "Starship cargo", "Crew & ECLSS", "Habitat",
    "Power", "ISRU", "Greenhouse", "Margins",
]


def default_assumptions() -> Dict[str, Any]:
    """Return a fresh copy of the default assumptions (safe to mutate)."""
    return dict(DEFAULT_ASSUMPTIONS)


def is_placeholder(key: str) -> bool:
    """True if the field's source class means 'unvalidated placeholder'."""
    meta = FIELD_METADATA.get(key)
    return bool(meta) and meta["source"] in PLACEHOLDER_SOURCES


# ---------------------------------------------------------------------------
# Asset catalog.
# ---------------------------------------------------------------------------

#: Full asset-catalog column order. The first 29 columns are exactly the schema
#: from the spec; the trailing columns are named extras that carry per-asset
#: numbers the spec gave for specific assets (generator output, storage
#: capacity, cable sizing) plus a packing ``criticality`` field.
ASSET_COLUMNS: List[str] = [
    "asset_id", "asset_name", "category", "scenario_group", "unit_mass_kg",
    "unit_volume_m3", "quantity_fixed", "quantity_per_crew", "quantity_per_habitat",
    "quantity_per_power_unit", "quantity_per_ISRU_unit", "power_peak_kw",
    "power_continuous_kw", "duty_cycle", "energy_kWh_per_sol", "storage_capacity_kg",
    "production_resource_type", "production_kg_per_sol", "lifetime_sols",
    "spares_percent_per_year", "redundancy_minimum", "minimum_quantity_before_crew",
    "can_arrive_after_crew", "prerequisite_asset_ids", "dependency_type",
    "source_class", "source_note", "confidence", "notes",
    # named extras:
    "power_output_kw", "energy_capacity_kWh", "battery_specific_energy_kWh_per_kg",
    "cable_specific_mass_kg_per_km_per_kw", "cable_length_km", "criticality",
]

# Numeric columns (used when loading CSV back into typed values).
ASSET_NUMERIC_COLUMNS = frozenset({
    "unit_mass_kg", "unit_volume_m3", "quantity_fixed", "quantity_per_crew",
    "quantity_per_habitat", "quantity_per_power_unit", "quantity_per_ISRU_unit",
    "power_peak_kw", "power_continuous_kw", "duty_cycle", "energy_kWh_per_sol",
    "storage_capacity_kg", "production_kg_per_sol", "lifetime_sols",
    "spares_percent_per_year", "redundancy_minimum", "minimum_quantity_before_crew",
    "power_output_kw", "energy_capacity_kWh", "battery_specific_energy_kWh_per_kg",
    "cable_specific_mass_kg_per_km_per_kw", "cable_length_km",
})

ASSET_BOOL_COLUMNS = frozenset({"can_arrive_after_crew"})


def _asset(**overrides) -> Dict[str, Any]:
    """Build one asset row, defaulting every column then applying overrides."""
    row: Dict[str, Any] = {
        "asset_id": "", "asset_name": "", "category": "", "scenario_group": "survival",
        "unit_mass_kg": 0.0, "unit_volume_m3": 0.0, "quantity_fixed": 0.0,
        "quantity_per_crew": 0.0, "quantity_per_habitat": 0.0,
        "quantity_per_power_unit": 0.0, "quantity_per_ISRU_unit": 0.0,
        "power_peak_kw": 0.0, "power_continuous_kw": 0.0, "duty_cycle": 0.0,
        "energy_kWh_per_sol": 0.0, "storage_capacity_kg": 0.0,
        "production_resource_type": "", "production_kg_per_sol": 0.0,
        "lifetime_sols": 5000.0, "spares_percent_per_year": 0.05,
        "redundancy_minimum": 0.0, "minimum_quantity_before_crew": 0.0,
        "can_arrive_after_crew": True, "prerequisite_asset_ids": "",
        "dependency_type": "", "source_class": LEGACY, "source_note": "",
        "confidence": "low", "notes": "", "power_output_kw": 0.0,
        "energy_capacity_kWh": 0.0, "battery_specific_energy_kWh_per_kg": 0.0,
        "cable_specific_mass_kg_per_km_per_kw": 0.0, "cable_length_km": 0.0,
        "criticality": "important",
    }
    row.update(overrides)
    return row


#: The 13 seed assets from the spec's legacy asset catalog.
SEED_ASSETS: List[Dict[str, Any]] = [
    _asset(
        asset_id="o2fr_pilot_plant", asset_name="O2fR pilot plant", category="ISRU",
        scenario_group="thrive", unit_mass_kg=1000, unit_volume_m3=8.0,
        power_peak_kw=40, power_continuous_kw=40, duty_cycle=1.0,
        production_resource_type="oxygen", production_kg_per_sol=15.6,
        lifetime_sols=3000, spares_percent_per_year=0.10, criticality="important",
        minimum_quantity_before_crew=0,
        prerequisite_asset_ids="shelter;comms_system;regolith_excavator_rover;power_cable",
        dependency_type="mixed",
        source_note="Power slide 12 in legacy quick-look study",
        notes="Oxygen-from-regolith pilot plant; lunar analog placeholder.",
    ),
    _asset(
        asset_id="science_payload", asset_name="Science mission payload",
        category="science", scenario_group="science", unit_mass_kg=100,
        unit_volume_m3=1.0, quantity_fixed=1, power_peak_kw=1, power_continuous_kw=1,
        duty_cycle=1.0,
        criticality="optional", prerequisite_asset_ids="shelter;comms_system",
        dependency_type="prior", notes="Science instruments; lunar analog placeholder.",
    ),
    _asset(
        asset_id="vsat_power_unit", asset_name="VSAT / power unit analog",
        category="power", scenario_group="survival", unit_mass_kg=700,
        unit_volume_m3=4.0, power_output_kw=50, power_peak_kw=0, duty_cycle=0.0,
        criticality="critical", minimum_quantity_before_crew=1,
        can_arrive_after_crew=False, prerequisite_asset_ids="power_cable",
        dependency_type="same_or_prior",
        source_note="Legacy sheet treated VSAT as producing 50 kW",
        notes="Power-system analog, not necessarily a Mars power architecture.",
    ),
    _asset(
        asset_id="battery_module", asset_name="Battery module",
        category="energy_storage", scenario_group="survival", unit_mass_kg=45,
        unit_volume_m3=0.05, energy_capacity_kWh=9,
        battery_specific_energy_kWh_per_kg=0.2, criticality="critical",
        minimum_quantity_before_crew=1, can_arrive_after_crew=False,
        prerequisite_asset_ids="vsat_power_unit", dependency_type="same_or_prior",
        source_note="200 Wh/kg; legacy note said Fuel Cell",
        notes="Battery/storage module placeholder.",
    ),
    _asset(
        asset_id="power_cable", asset_name="Power cable", category="power_distribution",
        scenario_group="survival", unit_mass_kg=432.6, unit_volume_m3=0.2,
        cable_specific_mass_kg_per_km_per_kw=8, cable_length_km=0.5,
        criticality="critical", minimum_quantity_before_crew=1,
        can_arrive_after_crew=False,
        source_note=("Mission-set sheet used 1,730.4 kg total for 4 cables, or "
                     "432.6 kg each. Quick-look row listed 40 kg for 0.5 km at "
                     "10 kW. Both notes preserved; sizing is formula-driven."),
        notes="mass = kg_per_km_per_kw * length_km * transmitted_kw (not hard-coded).",
    ),
    _asset(
        asset_id="shelter", asset_name="Shelter / habitat analog", category="habitat",
        scenario_group="survival", unit_mass_kg=1700, unit_volume_m3=30.0,
        power_peak_kw=3, power_continuous_kw=3, duty_cycle=1.0, criticality="critical",
        minimum_quantity_before_crew=2, can_arrive_after_crew=False,
        prerequisite_asset_ids="shelter_assembly_system;cargo_handling_rover_heavy",
        dependency_type="same_or_prior", source_note="Legacy shelter line item",
        notes="Lunar shelter analog; not a Mars habitat mass estimate.",
    ),
    _asset(
        asset_id="shelter_assembly_system", asset_name="Shelter assembly system",
        category="construction", scenario_group="exploration", unit_mass_kg=747,
        unit_volume_m3=6.0, quantity_fixed=1, power_peak_kw=1, power_continuous_kw=0.25,
        duty_cycle=0.25,
        criticality="important", minimum_quantity_before_crew=1,
        notes="Legacy bundle: LSMS, survey rover, command/monitoring suite, LDRS truss, truss robot.",
    ),
    _asset(
        asset_id="comms_system", asset_name="Comms system", category="communications",
        scenario_group="survival", unit_mass_kg=300, unit_volume_m3=2.0, quantity_fixed=1,
        power_peak_kw=0.15, power_continuous_kw=0.15, duty_cycle=1.0,
        criticality="critical", minimum_quantity_before_crew=1,
        can_arrive_after_crew=False, prerequisite_asset_ids="vsat_power_unit",
        dependency_type="same_or_prior",
        notes="Legacy note said mass and power need refinement.",
    ),
    _asset(
        asset_id="regolith_excavator_rover", asset_name="Regolith Excavator Rover",
        category="mobility_excavation", scenario_group="thrive", unit_mass_kg=66,
        unit_volume_m3=0.5, quantity_fixed=1, power_peak_kw=10, power_continuous_kw=2.5,
        duty_cycle=0.25,
        production_resource_type="regolith", production_kg_per_sol=2700,
        criticality="important", notes="Legacy RASSOR 2.0 analog.",
    ),
    _asset(
        asset_id="cargo_handling_rover_light", asset_name="Cargo Handling Rover - Light",
        category="mobility_logistics", scenario_group="exploration", unit_mass_kg=250,
        unit_volume_m3=2.0, quantity_fixed=1, power_peak_kw=10, power_continuous_kw=2.5,
        duty_cycle=0.25,
        criticality="important", notes="Legacy HL-MAPP analog.",
    ),
    _asset(
        asset_id="cargo_handling_rover_heavy", asset_name="Cargo Handling Rover - Heavy",
        category="mobility_logistics", scenario_group="survival", unit_mass_kg=1500,
        unit_volume_m3=6.0, quantity_fixed=1, power_peak_kw=20, power_continuous_kw=5,
        duty_cycle=0.25,
        criticality="critical", minimum_quantity_before_crew=1,
        can_arrive_after_crew=False,
        notes="Legacy sheet said mass is a guess; intended for payloads > 200 kg.",
    ),
    _asset(
        asset_id="highly_dexterous_rover", asset_name="Highly Dexterous Rover",
        category="mobility_robotics", scenario_group="exploration", unit_mass_kg=300,
        unit_volume_m3=2.0, quantity_fixed=1, power_peak_kw=10, power_continuous_kw=2.5,
        duty_cycle=0.25,
        criticality="important", notes="Dexterous manipulation rover analog.",
    ),
    _asset(
        asset_id="regolith_construction_rover", asset_name="Regolith Construction Rover",
        category="construction", scenario_group="thrive", unit_mass_kg=66,
        unit_volume_m3=0.5, quantity_fixed=1, power_peak_kw=10, power_continuous_kw=2.5,
        duty_cycle=0.25,
        criticality="optional",
        notes="Mass editable placeholder (legacy 66 or 300 kg). Appeared in day-power "
              "calc but not consistently in total mass.",
    ),
]


def default_assets() -> List[Dict[str, Any]]:
    """Return a deep-ish copy of the seed asset catalog (rows are fresh dicts)."""
    return [dict(row) for row in SEED_ASSETS]


# ---------------------------------------------------------------------------
# Dependency edges (editable dependency table).
# Rule: -1 = prerequisite must land on a strictly EARLIER mission.
#        0 = prerequisite may land on the SAME or an earlier mission.
# These generalise the legacy dependency matrix to the asset-type level.
# ---------------------------------------------------------------------------

DEPENDENCY_COLUMNS: List[str] = ["asset_id", "depends_on_asset_id", "rule", "note"]

DEFAULT_DEPENDENCIES: List[Dict[str, Any]] = [
    {"asset_id": "o2fr_pilot_plant", "depends_on_asset_id": "shelter", "rule": -1,
     "note": "ISRU plant needs shelter established first."},
    {"asset_id": "o2fr_pilot_plant", "depends_on_asset_id": "comms_system", "rule": -1,
     "note": "ISRU plant needs comms first."},
    {"asset_id": "o2fr_pilot_plant", "depends_on_asset_id": "regolith_excavator_rover",
     "rule": 0, "note": "ISRU needs feedstock excavation."},
    {"asset_id": "o2fr_pilot_plant", "depends_on_asset_id": "cargo_handling_rover_light",
     "rule": 0, "note": "Unloading/placement."},
    {"asset_id": "o2fr_pilot_plant", "depends_on_asset_id": "cargo_handling_rover_heavy",
     "rule": 0, "note": "Unloading/placement."},
    {"asset_id": "o2fr_pilot_plant", "depends_on_asset_id": "power_cable", "rule": 0,
     "note": "ISRU needs power distribution."},
    {"asset_id": "science_payload", "depends_on_asset_id": "shelter", "rule": -1,
     "note": "Science needs shelter first."},
    {"asset_id": "science_payload", "depends_on_asset_id": "comms_system", "rule": -1,
     "note": "Science needs comms first."},
    {"asset_id": "science_payload", "depends_on_asset_id": "cargo_handling_rover_heavy",
     "rule": 0, "note": "Unloading."},
    {"asset_id": "science_payload", "depends_on_asset_id": "power_cable", "rule": 0,
     "note": "Power distribution."},
    {"asset_id": "shelter", "depends_on_asset_id": "shelter_assembly_system", "rule": 0,
     "note": "Shelter needs assembly system."},
    {"asset_id": "shelter", "depends_on_asset_id": "regolith_excavator_rover", "rule": 0,
     "note": "Shelter needs excavation (shielding/foundation)."},
    {"asset_id": "shelter", "depends_on_asset_id": "cargo_handling_rover_light", "rule": 0,
     "note": "Unloading."},
    {"asset_id": "shelter", "depends_on_asset_id": "cargo_handling_rover_heavy", "rule": 0,
     "note": "Unloading."},
    {"asset_id": "vsat_power_unit", "depends_on_asset_id": "power_cable", "rule": 0,
     "note": "Generator needs distribution."},
    {"asset_id": "battery_module", "depends_on_asset_id": "vsat_power_unit", "rule": 0,
     "note": "Storage needs generation to charge (Mars addition)."},
    {"asset_id": "comms_system", "depends_on_asset_id": "vsat_power_unit", "rule": 0,
     "note": "Comms needs power (Mars addition)."},
]


def default_dependencies() -> List[Dict[str, Any]]:
    """Return a copy of the default dependency edge list."""
    return [dict(row) for row in DEFAULT_DEPENDENCIES]


# ---------------------------------------------------------------------------
# Mass-bucket display names for the "landed mass by category" outputs.
# ---------------------------------------------------------------------------
MASS_BUCKET_ORDER: List[str] = [
    "Crew consumables & reserves",
    "Habitat & crew systems",
    "Power generation",
    "Energy storage",
    "Power distribution",
    "Crew O2 ISRU",
    "Water ISRU",
    "Propellant ISRU",
    "Mobility",
    "Communications",
    "Science",
    "Construction",
    "Greenhouse",
]

#: Map an asset ``category`` to a mass bucket (for discrete catalog assets).
CATEGORY_TO_BUCKET: Dict[str, str] = {
    "mobility_excavation": "Mobility",
    "mobility_logistics": "Mobility",
    "mobility_robotics": "Mobility",
    "communications": "Communications",
    "science": "Science",
    "construction": "Construction",
}

# ---------------------------------------------------------------------------
# Built-in scenario presets (overrides applied on top of DEFAULT_ASSUMPTIONS).
# ---------------------------------------------------------------------------
SCENARIO_PRESETS: Dict[str, Dict[str, Any]] = {
    "Mars survival baseline (crew 4)": {
        "scenario_name": "Mars survival baseline (crew 4)",
        "crew_count": 4, "operating_mode": "survival",
    },
    "Mars exploration base (crew 8)": {
        "scenario_name": "Mars exploration base (crew 8)",
        "crew_count": 8, "operating_mode": "exploration",
        "include_pressurized_rovers": True,
    },
    "Mars thrive settlement (crew 12)": {
        "scenario_name": "Mars thrive settlement (crew 12)",
        "crew_count": 12, "operating_mode": "thrive",
        "include_greenhouse": True, "include_surface_construction": True,
        "water_ISRU_enabled": True, "food_closure_fraction": 0.30,
    },
    "Legacy lunar-derived Mars placeholder": {
        # Mirrors the embedded legacy node-model base inputs (crew 50, 30-day
        # period). These are lunar-derived PLACEHOLDERS, not Mars design values.
        "scenario_name": "Legacy lunar-derived Mars placeholder",
        "crew_count": 50, "surface_duration_sols": 30, "operating_mode": "thrive",
        "water_kg_per_crew_sol": 8.0, "water_recovery_rate": 0.98,
        "oxygen_kg_per_crew_sol": 1.1, "oxygen_recovery_rate": 0.45,
        "habitat_power_continuous_kw": 7.5, "crew_capacity_per_habitat": 4,
        "oxygen_ISRU_output_kg_per_sol": 15.6, "oxygen_ISRU_unit_power_kw": 15.0,
        "include_greenhouse": True,
    },
}


def scenario_preset(name: str) -> Dict[str, Any]:
    """Return default assumptions with a named preset's overrides applied."""
    a = default_assumptions()
    a.update(SCENARIO_PRESETS.get(name, {}))
    return a


# Warning strings the UI must surface (spec UI requirements).
PLACEHOLDER_WARNINGS: List[str] = [
    "Legacy lunar-derived values are placeholders and are not validated Mars system design values.",
    "Starship landed Mars payload is scenario-configurable and should not be treated as fixed.",
    "Crew oxygen and propellant oxygen are modeled separately.",
    "Power capacity and energy storage are both required; average power alone is insufficient.",
    "Crew arrival is blocked unless minimum survival readiness checks pass.",
]
