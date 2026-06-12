"""Mars Surface Logistics Calculator - calculation engine.

This package is intentionally free of third-party dependencies so that the
model and its test suite run on a bare Python 3.11+ interpreter. The Streamlit
UI (``app.py``) and the Excel export are the only parts that need extra
packages; see ``requirements.txt``.

Public surface
--------------
- :mod:`mars_logistics.units`       - physical/units constants and conversions
- :mod:`mars_logistics.defaults`    - canonical default assumptions + metadata
- :mod:`mars_logistics.model`       - the scenario calculation engine
- :mod:`mars_logistics.packing`     - dependency-aware mission bin packing
- :mod:`mars_logistics.validation`  - red/yellow/green readiness checks
- :mod:`mars_logistics.legacy`      - exact reproduction of the legacy lunar case
- :mod:`mars_logistics.sensitivity` - one-parameter sensitivity sweeps
- :mod:`mars_logistics.io_utils`    - CSV/JSON/Excel import & export helpers
"""

from . import units, defaults, model, packing, validation, legacy, sensitivity

__all__ = [
    "units",
    "defaults",
    "model",
    "packing",
    "validation",
    "legacy",
    "sensitivity",
]

__version__ = "0.1.0"
