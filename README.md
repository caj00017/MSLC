# Mars Surface Logistics Calculator

Estimates the **landed mass, cargo-mission count, setup sequence, power balance,
consumables, ISRU production, and resupply cadence** required to sustain a
configurable number of humans on the Martian surface using Starship-sized cargo
missions.

It is **auditable, unit-consistent, scenario-driven, and editable**: every number
is a named variable, every assumption can be edited/imported/exported, and the
calculation engine is fully separated from the UI.

> ⚠️ **Read this first.** Many default numbers are **legacy lunar-derived
> placeholders** carried over from an earlier study. They are useful for model
> architecture, test cases, and a first-pass estimate, but they are **not
> validated Mars design values.** The UI tags them `⚠️legacy` / `⚠️review`.
> Replace them with real engineering data before trusting any output.

---

## What it does

Answers the questions the study asked:

1. Landed mass for **minimal survival** of *N* humans.
2. Additional landed mass for **exploration** and **science**.
3. **Cargo Starships required before crew arrival.**
4. Missions required for each operating mode (**survival / exploration / science / thrive**).
5. **Resupply mass and cadence.**
6. Which **consumables, spares, and replacement hardware** dominate sustainment.
7. The **limiting resource** (mass, power, energy storage, water, O₂, food, ISRU
   throughput, excavation throughput, crew capacity, or dependency sequencing).

It produces a dashboard, editable tables, a **dependency-aware mission manifest**,
**red/yellow/green readiness checks** that gate crew arrival, sensitivity sweeps,
side-by-side scenario comparison, and CSV/JSON/Excel export.

## What it does NOT do

- It is **not** a validated Mars systems design. Defaults are placeholders.
- It does **not** model trajectory/EDL, detailed thermal, structural, or CFD.
- It does **not** fix the legacy spreadsheet's *values* — only its *logic*
  (the legacy `#DIV/0!`, circular references, and "PLACE HOLDER" cells are
  rebuilt cleanly from first principles).
- Propellant production stoichiometry is a lumped estimate unless you enable the
  (still placeholder) detailed path.

---

## Quick start

```bash
# 1) Engine + tests need NOTHING beyond Python 3.11+:
python -m unittest discover -s tests          # 31 tests, all green

# 2) The UI needs a few packages:
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

The model and test suite are **pure standard library** — they run on a bare
interpreter. Only the Streamlit UI and the one-click Excel export need the
packages in `requirements.txt` (CSV/JSON export work without them).

### How to run the tests

```bash
python -m unittest discover -s tests -v
```

The suite reproduces the legacy reference case exactly (day-power 108.15/62.4 kW,
night-energy 17,522.4/2,066.4 kWh, mass rollups 99,174.4/21,891.4/9,294.2 kg) and
checks usable-payload, consumables-with-recovery, ISRU sizing, habitat sizing,
mission-packing mass margins, dependency checking, resupply mass, import clamping,
divide-by-zero guards, and the crew-arrival gate.

---

## Project structure

```
app.py                              # Streamlit UI (thin shell over the engine)
mars_logistics/
  units.py                          # constants + unit conversions (kW vs kWh guard rail)
  defaults.py                       # canonical assumptions, metadata, seed assets, deps, presets
  model.py                          # the calculation engine (run_model)
  packing.py                        # dependency-aware mission bin packing
  validation.py                     # red/yellow/green readiness checks
  legacy.py                         # exact reproduction of the legacy lunar case
  sensitivity.py                    # one-parameter sensitivity sweeps
  io_utils.py                       # CSV / JSON / Excel import & export
data/
  default_assumptions.json          # flat {key: value} assumptions
  default_assets.csv                # editable asset catalog
  default_dependencies.csv          # editable dependency table
  default_mission_manifest.csv      # legacy reference manifest
tests/test_model.py                 # full test suite (stdlib unittest)
```

The `data/` files are **generated from** the canonical Python defaults
(`mars_logistics/io_utils.py:write_default_data_files`) and are what the app
loads at startup, so non-programmers can edit CSV/JSON directly.

---

## How to update assets

Edit `data/default_assets.csv` (or the **Assets** tab in the UI — it's a live,
add/remove-rows editor). Each row is one asset. Key columns:

- `unit_mass_kg`, `unit_volume_m3` — per-unit mass and volume.
- `quantity_fixed` / `quantity_per_crew` / `quantity_per_habitat` /
  `quantity_per_power_unit` / `quantity_per_ISRU_unit` — the quantity formula:
  `qty = fixed + per_crew·crew + per_habitat·habitats + per_power_unit·power_units + per_ISRU_unit·ISRU_units`.
- `power_peak_kw`, `power_continuous_kw`, `duty_cycle`, `energy_kWh_per_sol`.
- `category`, `scenario_group` (survival/exploration/science/thrive) — control
  when the asset activates.
- `criticality` (critical/important/optional), `minimum_quantity_before_crew`,
  `can_arrive_after_crew`, `prerequisite_asset_ids`, `dependency_type` — drive
  packing and the crew-arrival gate.
- `source_class`, `source_note`, `confidence`, `notes` — provenance.

Categories whose mass/power the engine sizes from **first-principles formulas**
(power generation, energy storage, power distribution, habitat, crew-O₂ ISRU) are
marked so their legacy catalog rows are *not* double-counted in Mars mode.

## How to update dependencies

Edit `data/default_dependencies.csv` (or the **Dependencies** tab). Each row is an
edge `asset_id → depends_on_asset_id` with a `rule`:

- `-1` — prerequisite must land on a **strictly earlier** mission.
- ` 0` — prerequisite may land on the **same or earlier** mission.

These generalize the legacy dependency matrix and are honoured by the packer.

## How to import/export scenarios

In the **Import/Export** tab you can download:

- **Scenario package (JSON)** — assumptions + assets + dependencies in one file.
- Assumptions (JSON), Asset catalog (CSV), Dependencies (CSV),
  Mission manifest (CSV), Dashboard (CSV), and a **full multi-sheet Excel workbook**.

…and upload any of those to replace the working set. Programmatically:

```python
from mars_logistics import io_utils
from mars_logistics.model import run_model

a, assets, deps = io_utils.load_default_data("data")
results = run_model(a, assets, deps)
open("scenario.json", "w").write(io_utils.scenario_to_json(a, assets, deps))
```

---

## How to interpret outputs

- **Total initial landed mass** — everything needed to stand the base up.
  Split into **pre-crew** (must be on the surface and verified before humans
  arrive) and **post-crew**.
- **Cargo Starships (full setup / pre-crew)** come from the **dependency-aware
  packer**, not a naive `ceil(mass / payload)` (that naive number is shown too,
  for comparison).
- **Power margin** — installed continuous capacity minus continuous demand.
  Both **power capacity (kW)** and **energy storage (kWh)** are required; average
  power alone is insufficient (sized separately).
- **Storage autonomy (sols)** — how long energy storage carries the critical load
  through night / outage / dust storm.
- **Net water/O₂/food import** — mass to land/resupply *after* recovery and ISRU.
- **Max crew-sols (stockpile)** — how long the landed stockpile sustains the crew.
- **Limiting resource** — the binding constraint (smallest slack).
- **Readiness** — 🟢/🟡/🔴 checks. **Crew arrival is blocked** while any critical
  crew check is 🔴.

## Operating modes

| Mode | Includes | Intent |
|------|----------|--------|
| **survival** | survival-group assets only | keep N humans alive |
| **exploration** | + exploration assets (mobility, assembly) | survive **and** explore |
| **science** | + science payloads | survive, explore **and** do science |
| **thrive** | + greenhouse, construction, expanded ISRU, optional propellant | grow / settle |

More capability never *reduces* required landed mass (verified by a test).

## Crew life-support ISRU vs propellant ISRU

These are **modeled entirely separately** (a core requirement):

- **Crew-survival O₂ ISRU** keeps people breathing. Sized from the crew O₂ makeup
  rate; its mass and power feed the survival power balance.
- **Propellant ISRU** (optional) makes return-vehicle O₂/CH₄. It has its own
  target, deadline, storage, and power, and is reported in its own mass/power
  lines. It never offsets crew-survival oxygen.

## Why Starship payload is configurable, not fixed

The landed Mars cargo payload of Starship is not a published, fixed number. It is
a **user input** with explicit sensitivity cases (50/75/100/125/150 t). Usable
payload is derived:

```
usable_payload = landed_payload × packing_efficiency × (1 − unallocated_margin)
              = 100,000 × 0.90 × (1 − 0.20) = 72,000 kg   (defaults)
```

---

## Provenance: which values came from where

Each assumption carries a `source` class (shown in the UI and in
`mars_logistics/defaults.py`):

- **`legacy_lunar_analog_placeholder`** — copied from the legacy lunar
  spreadsheets (e.g. 8 kg/crew/sol water, 45 % O₂ recovery, 0.2 kWh/kg batteries,
  15.6 kg/sol ISRU, 8 kg·km⁻¹·kW⁻¹ cable, 45 kg battery modules). **Not Mars
  values.**
- **`mars_engineering_placeholder`** — Mars-oriented but still placeholder
  (plausible, not designed).
- **`mars_constant`** — defensible physical constants (sol = 24.65979 h,
  30.4375 days/month, 26-month transfer opportunity).
- **`needs_engineering_review`** — explicitly flagged for review before use
  (habitat mass, solar specific power, dust storm autonomy, regolith water
  fraction, propellant targets, …).

The **legacy reference reproduction** (Legacy tab / `mars_logistics/legacy.py`)
reproduces the original spreadsheet totals exactly, *including* its documented
inconsistencies (e.g. the thrive vs survive battery-mass mismatch), preserved as
notes rather than silently corrected.

---

## Core formulas (engine)

Time, payload, consumables-with-recovery, ISRU sizing, habitat sizing, power
balance, solar/nuclear/hybrid generation, energy storage (autonomy → kWh →
mass → units), spares, and resupply are all implemented in
`mars_logistics/model.py` exactly as specified, with `safe_div` guarding every
denominator and `max(0, …)` clamping every import. See the module docstrings and
`tests/test_model.py` for the authoritative, checked behavior.
