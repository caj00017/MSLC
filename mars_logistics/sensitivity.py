"""One-parameter sensitivity sweeps.

For each varied parameter the engine is re-run with that one value overridden,
and a compact row of headline outputs is recorded. This is intentionally simple
and transparent: no surrogate models, just repeated calls to ``run_model``.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from . import defaults
from .model import run_model

# Parameters the spec asks to vary, each with a default sweep of values.
DEFAULT_SWEEPS: Dict[str, List[Any]] = {
    "crew_count": [2, 4, 8, 12, 20],
    "landed_payload_kg_per_starship": list(defaults.SENSITIVITY_PAYLOAD_CASES_KG),
    "packing_efficiency": [0.80, 0.85, 0.90, 0.95],
    "unallocated_margin_percent": [0.10, 0.20, 0.30],
    "water_recovery_rate": [0.80, 0.90, 0.98],
    "oxygen_recovery_rate": [0.30, 0.45, 0.60],
    "food_closure_fraction": [0.0, 0.25, 0.50],
    "power_architecture": ["solar", "nuclear", "hybrid"],
    "battery_specific_energy_kWh_per_kg": [0.15, 0.20, 0.30],
    "dust_derating_factor": [0.5, 0.7, 0.9],
    "oxygen_ISRU_output_kg_per_sol": [10.0, 15.6, 25.0],
    "hardware_spares_percent_per_year": [0.02, 0.05, 0.10],
    "emergency_reserve_sols": [30, 60, 120],
    "resupply_window_months": [13, 26, 39],
}


def _row(param: str, value: Any, results: Dict[str, Any]) -> Dict[str, Any]:
    mass = results["mass"]
    return {
        "parameter": param,
        "value": value,
        "initial_landed_mass_kg": mass["initial_landed_kg"],
        "pre_crew_missions": results["missions"]["pre_crew_missions"],
        "total_setup_missions": results["missions"]["setup_missions_packed"],
        "resupply_mass_per_window_kg": results["sustainment"]["resupply"]["total_kg"],
        "resupply_starships_per_window": results["sustainment"]["resupply"]["starships_required"],
        "power_margin_kw": results["power"]["power_margin_kw"],
        "energy_storage_autonomy_sols": results["storage"]["autonomy_achieved_sols"],
        "limiting_resource": results["limiting_resource"]["name"],
        "top_mass_driver": mass["top_drivers"][0][0] if mass["top_drivers"] else "",
    }


def sweep_parameter(base_assumptions: Dict[str, Any], param: str, values: List[Any],
                    assets=None, dependencies=None) -> List[Dict[str, Any]]:
    """Run the model once per value of ``param`` and return one row per value."""
    rows: List[Dict[str, Any]] = []
    for value in values:
        overrides = dict(base_assumptions)
        overrides[param] = value
        results = run_model(overrides, assets, dependencies)
        rows.append(_row(param, value, results))
    return rows


def run_sensitivity(base_assumptions: Dict[str, Any],
                    sweeps: Optional[Dict[str, List[Any]]] = None,
                    assets=None, dependencies=None) -> List[Dict[str, Any]]:
    """Run every sweep in ``sweeps`` (defaults to :data:`DEFAULT_SWEEPS`)."""
    sweeps = sweeps if sweeps is not None else DEFAULT_SWEEPS
    rows: List[Dict[str, Any]] = []
    for param, values in sweeps.items():
        rows.extend(sweep_parameter(base_assumptions, param, values, assets, dependencies))
    return rows
