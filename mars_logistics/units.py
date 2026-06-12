"""Physical constants, unit conversions, and unit-safety helpers.

Every constant here is a named module-level variable. There are no hidden magic
numbers buried inside the model: if a quantity matters, it is named here or it
is a user-editable assumption in :mod:`mars_logistics.defaults`.

Unit discipline (enforced by naming and by tests):
    * kW   -> instantaneous power. Never summed with kWh.
    * kWh  -> energy = power * time. Always carries a time basis.
    * sol  -> one Martian solar day (the surface-operations time unit).
    * Earth day -> the 24 h calendar day (shown alongside sols for humans).
"""

from __future__ import annotations

import math

# --- Mars / Earth time bases -------------------------------------------------

#: Length of one Mars sol in hours (mean solar day). Spec default.
HOURS_PER_SOL: float = 24.65979

#: Hours in one Earth day, by definition.
HOURS_PER_EARTH_DAY: float = 24.0

#: One sol expressed in Earth days = 24.65979 / 24.
EARTH_DAYS_PER_SOL: float = HOURS_PER_SOL / HOURS_PER_EARTH_DAY

#: Mean Earth days per calendar month (Gregorian average), used to convert the
#: 26-Earth-month Mars transfer/resupply opportunity into days and sols.
EARTH_DAYS_PER_MONTH: float = 30.4375

#: Earth days in a Julian year, used for annualised spares rates.
EARTH_DAYS_PER_YEAR: float = 365.25


# --- Time conversion helpers -------------------------------------------------

def sols_to_earth_days(sols: float) -> float:
    """Convert a duration in sols to Earth days."""
    return sols * EARTH_DAYS_PER_SOL


def earth_days_to_sols(earth_days: float) -> float:
    """Convert a duration in Earth days to sols."""
    return earth_days / EARTH_DAYS_PER_SOL


def months_to_earth_days(months: float) -> float:
    """Convert a number of (average) Earth months to Earth days."""
    return months * EARTH_DAYS_PER_MONTH


def months_to_sols(months: float) -> float:
    """Convert a number of (average) Earth months to sols."""
    return earth_days_to_sols(months_to_earth_days(months))


def sols_to_hours(sols: float) -> float:
    """Convert a duration in sols to hours."""
    return sols * HOURS_PER_SOL


# --- Energy <-> power helpers (the kW vs kWh guard rail) ----------------------

def energy_kwh_from_power(power_kw: float, hours: float) -> float:
    """Energy (kWh) delivered by a constant power draw (kW) over ``hours``."""
    return power_kw * hours


def energy_kwh_per_sol(power_kw: float) -> float:
    """Energy used in one sol (kWh) by a constant power draw (kW)."""
    return power_kw * HOURS_PER_SOL


def average_power_kw(peak_power_kw: float, duty_cycle: float) -> float:
    """Duty-cycle-averaged power (kW) from a peak draw and a 0..1 duty cycle."""
    return peak_power_kw * duty_cycle


# --- Safe arithmetic ---------------------------------------------------------

def safe_div(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Division that returns ``default`` instead of raising on a zero/None
    denominator. The legacy spreadsheets produced ``#DIV/0!`` here; the model
    must not. Use this anywhere a denominator could be zero by configuration."""
    if denominator is None or denominator == 0:
        return default
    return numerator / denominator


def ceil_units(quantity: float) -> int:
    """Number of whole units needed to cover ``quantity`` (>= 0).

    Returns 0 for non-positive input so an unused subsystem costs zero units."""
    if quantity is None or quantity <= 0:
        return 0
    return int(math.ceil(quantity))
