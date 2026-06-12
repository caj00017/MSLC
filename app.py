"""Mars Surface Logistics Calculator - Streamlit UI.

The UI is a thin shell over the calculation engine in :mod:`mars_logistics`.
All numbers come from the engine; this file only collects inputs, lays out the
dashboard, and wires up import/export. Run with:

    streamlit run app.py

The engine and its tests need no third-party packages; only this UI does
(streamlit, pandas, altair, and openpyxl for the Excel export).
"""

from __future__ import annotations

import os

import pandas as pd
import streamlit as st

try:
    import altair as alt
    _HAVE_ALTAIR = True
except Exception:  # pragma: no cover
    _HAVE_ALTAIR = False

from mars_logistics import defaults, io_utils, legacy, sensitivity
from mars_logistics.model import run_model

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

st.set_page_config(page_title="Mars Surface Logistics Calculator",
                   page_icon="🚀", layout="wide")


# ---------------------------------------------------------------------------
# Session state.
# ---------------------------------------------------------------------------

def _init_state() -> None:
    if "assumptions" not in st.session_state:
        a, assets, deps = io_utils.load_default_data(DATA_DIR)
        st.session_state.assumptions = a
        st.session_state.assets = assets
        st.session_state.dependencies = deps
        st.session_state.saved_scenarios = {}  # name -> dashboard dict (for compare)


_init_state()


def assumptions() -> dict:
    return st.session_state.assumptions


def _source_badge(key: str) -> str:
    meta = defaults.FIELD_METADATA.get(key, {})
    src = meta.get("source", "")
    return {
        defaults.LEGACY: " ⚠️legacy",
        defaults.REVIEW: " ⚠️review",
        defaults.MARS_PH: " ·placeholder",
        defaults.CONST: "",
    }.get(src, "")


# ---------------------------------------------------------------------------
# Sidebar - scenario controls.
# ---------------------------------------------------------------------------

def sidebar() -> None:
    st.sidebar.title("🚀 Scenario controls")

    preset = st.sidebar.selectbox("Load a preset scenario",
                                  ["(keep current)"] + list(defaults.SCENARIO_PRESETS))
    if preset != "(keep current)" and st.sidebar.button("Apply preset", use_container_width=True):
        st.session_state.assumptions = defaults.scenario_preset(preset)
        st.rerun()

    a = assumptions()
    st.sidebar.text_input("Scenario name", key="scenario_name",
                          value=a["scenario_name"],
                          on_change=lambda: a.update(
                              scenario_name=st.session_state.scenario_name))

    st.sidebar.subheader("Headline inputs")
    a["crew_count"] = st.sidebar.number_input(
        "Crew count (people)", min_value=1, max_value=1000,
        value=int(a["crew_count"]), step=1,
        help=defaults.FIELD_METADATA["crew_count"]["help"])
    a["operating_mode"] = st.sidebar.selectbox(
        "Operating mode", defaults.OPERATING_MODES,
        index=defaults.OPERATING_MODES.index(a["operating_mode"]),
        help=defaults.FIELD_METADATA["operating_mode"]["help"])
    a["surface_duration_sols"] = st.sidebar.number_input(
        "Surface duration (sols)", min_value=1, value=int(a["surface_duration_sols"]),
        help=defaults.FIELD_METADATA["surface_duration_sols"]["help"])
    a["landed_payload_kg_per_starship"] = st.sidebar.number_input(
        "Starship landed payload (kg) ⚠️configurable", min_value=1000.0,
        value=float(a["landed_payload_kg_per_starship"]), step=5000.0,
        help=defaults.FIELD_METADATA["landed_payload_kg_per_starship"]["help"])
    a["power_architecture"] = st.sidebar.selectbox(
        "Power architecture", ["solar", "nuclear", "hybrid"],
        index=["solar", "nuclear", "hybrid"].index(a["power_architecture"]))
    a["resupply_window_months"] = st.sidebar.number_input(
        "Resupply window (Earth months)", min_value=1.0,
        value=float(a["resupply_window_months"]),
        help=defaults.FIELD_METADATA["resupply_window_months"]["help"])

    st.sidebar.subheader("Capability toggles")
    for flag in ("include_greenhouse", "include_propellant_isru",
                 "include_surface_construction", "include_pressurized_rovers",
                 "oxygen_ISRU_enabled", "water_ISRU_enabled"):
        a[flag] = st.sidebar.checkbox(flag.replace("_", " "), value=bool(a[flag]),
                                      help=defaults.FIELD_METADATA.get(flag, {}).get("help"))

    if st.sidebar.button("Reset to defaults", use_container_width=True):
        st.session_state.assumptions = defaults.default_assumptions()
        st.rerun()

    st.sidebar.caption("⚠️ Many defaults are legacy lunar-derived placeholders. "
                       "Edit them on the Assumptions tab before trusting outputs.")


# ---------------------------------------------------------------------------
# Dashboard tab.
# ---------------------------------------------------------------------------

def _fmt(x, unit=""):
    if isinstance(x, (int, float)):
        return f"{x:,.0f}{unit}" if abs(x) >= 100 else f"{x:,.2f}{unit}"
    return str(x)


def dashboard_tab(results: dict) -> None:
    d = results["dashboard"]
    ready = results["readiness"]

    if ready["crew_arrival_allowed"]:
        st.success("✅ Crew arrival readiness: all critical checks pass.")
    else:
        st.error("⛔ Crew arrival BLOCKED — failing: "
                 + ", ".join(ready["blocking_checks"]))

    c = st.columns(4)
    c[0].metric("Crew", _fmt(d["crew_count"]))
    c[1].metric("Operating mode", d["operating_mode"])
    c[2].metric("Surface duration", f"{d['surface_duration_sols']:,.0f} sols",
                f"{d['surface_duration_earth_days']:,.0f} Earth days")
    c[3].metric("Limiting resource", d["limiting_resource"])

    c = st.columns(4)
    c[0].metric("Landed payload / Starship", f"{d['landed_payload_kg']:,.0f} kg")
    c[1].metric("Usable payload / Starship", f"{d['usable_payload_kg']:,.0f} kg")
    c[2].metric("Total initial landed mass", f"{d['total_initial_landed_mass_kg']/1000:,.1f} t")
    c[3].metric("Pre-crew landed mass", f"{d['total_pre_crew_landed_mass_kg']/1000:,.1f} t")

    c = st.columns(4)
    c[0].metric("Cargo Starships (full setup)", _fmt(d["cargo_starships_full_setup"]))
    c[1].metric("Cargo Starships (pre-crew)", _fmt(d["cargo_starships_pre_crew"]))
    c[2].metric("Resupply Starships / window", _fmt(d["cargo_starships_per_resupply_window"]))
    c[3].metric("Resupply mass / window", f"{d['resupply_mass_per_window_kg']/1000:,.1f} t")

    c = st.columns(4)
    c[0].metric("Installed power capacity", f"{d['total_installed_power_capacity_kw']:,.1f} kW")
    c[1].metric("Critical load", f"{d['total_critical_load_kw']:,.1f} kW")
    c[2].metric("Power margin", f"{d['power_margin_kw']:,.1f} kW")
    c[3].metric("Energy storage", f"{d['total_energy_storage_kwh']:,.0f} kWh")

    c = st.columns(4)
    c[0].metric("Storage autonomy", f"{d['storage_autonomy_sols']:,.1f} sols")
    c[1].metric("Net water import", f"{d['net_water_import_kg']:,.0f} kg")
    c[2].metric("Net O₂ import", f"{d['net_o2_import_kg']:,.0f} kg")
    c[3].metric("Net food import", f"{d['net_food_import_kg']:,.0f} kg")

    c = st.columns(4)
    c[0].metric("O₂ ISRU production", f"{d['oxygen_isru_production_kg_per_sol']:,.1f} kg/sol")
    c[1].metric("Water ISRU production", f"{d['water_isru_production_kg_per_sol']:,.1f} kg/sol")
    c[2].metric("Max crew-sols (stockpile)", f"{d['max_crew_sols_supportable']:,.0f}")
    c[3].metric("Post-crew landed mass", f"{d['total_post_crew_landed_mass_kg']/1000:,.1f} t")

    st.subheader("Top five mass drivers")
    drivers = pd.DataFrame(d["top_five_mass_drivers"], columns=["category", "mass_kg"])
    if _HAVE_ALTAIR and not drivers.empty:
        st.altair_chart(
            alt.Chart(drivers).mark_bar().encode(
                x=alt.X("mass_kg:Q", title="Mass (kg)"),
                y=alt.Y("category:N", sort="-x", title=None)
            ).properties(height=200), use_container_width=True)
    else:
        st.dataframe(drivers, use_container_width=True)

    for w in results["warnings"]:
        st.caption("⚠️ " + w)


# ---------------------------------------------------------------------------
# Charts tab.
# ---------------------------------------------------------------------------

def charts_tab(results: dict) -> None:
    if not _HAVE_ALTAIR:
        st.info("Install altair to see charts.")
        return
    a = assumptions()

    st.subheader("Initial landed mass by category")
    buckets = pd.DataFrame(
        [(b, m) for b, m in results["mass"]["buckets"].items() if m > 0],
        columns=["category", "mass_kg"])
    st.altair_chart(alt.Chart(buckets).mark_bar().encode(
        x="mass_kg:Q", y=alt.Y("category:N", sort="-x")), use_container_width=True)

    st.subheader("Power supply vs demand")
    p = results["power"]
    pdf = pd.DataFrame({
        "quantity": ["Continuous demand", "Required generation", "Installed capacity",
                     "Critical load"],
        "kW": [p["total_continuous_kw"], p["required_generation_kw"],
               p["installed_continuous_kw"], p["critical_load_kw"]]})
    st.altair_chart(alt.Chart(pdf).mark_bar().encode(
        x="kW:Q", y=alt.Y("quantity:N", sort="-x")), use_container_width=True)

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Starships vs crew count")
        rows = []
        for n in [2, 4, 8, 12, 20, 30]:
            aa = dict(a); aa["crew_count"] = n
            rr = run_model(aa, st.session_state.assets, st.session_state.dependencies)
            rows.append({"crew": n, "setup_missions": rr["missions"]["setup_missions_packed"]})
        st.altair_chart(alt.Chart(pd.DataFrame(rows)).mark_line(point=True).encode(
            x="crew:Q", y="setup_missions:Q"), use_container_width=True)
    with col2:
        st.subheader("Starships vs usable payload")
        rows = []
        for landed in defaults.SENSITIVITY_PAYLOAD_CASES_KG:
            aa = dict(a); aa["landed_payload_kg_per_starship"] = landed
            rr = run_model(aa, st.session_state.assets, st.session_state.dependencies)
            rows.append({"landed_kg": landed,
                         "setup_missions": rr["missions"]["setup_missions_packed"]})
        st.altair_chart(alt.Chart(pd.DataFrame(rows)).mark_line(point=True).encode(
            x="landed_kg:Q", y="setup_missions:Q"), use_container_width=True)

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Resupply mass vs interval")
        rows = []
        for months in [13, 26, 39, 52]:
            aa = dict(a); aa["resupply_window_months"] = months
            rr = run_model(aa, st.session_state.assets, st.session_state.dependencies)
            rows.append({"window_months": months,
                         "resupply_t": rr["sustainment"]["resupply"]["total_kg"] / 1000})
        st.altair_chart(alt.Chart(pd.DataFrame(rows)).mark_line(point=True).encode(
            x="window_months:Q", y="resupply_t:Q"), use_container_width=True)
    with col2:
        st.subheader("ISRU O₂ production vs demand")
        o2 = results["isru"]["oxygen"]
        idf = pd.DataFrame({"series": ["Required", "Produced"],
                            "kg_per_sol": [o2["required_per_sol"], o2["produced_per_sol"]]})
        st.altair_chart(alt.Chart(idf).mark_bar().encode(
            x="kg_per_sol:Q", y="series:N"), use_container_width=True)


# ---------------------------------------------------------------------------
# Assumptions tab (editable, grouped, with units + tooltips).
# ---------------------------------------------------------------------------

def assumptions_tab() -> None:
    a = assumptions()
    st.caption("Every input is editable. ⚠️legacy / ⚠️review tags mark unvalidated "
               "placeholder values. Units are shown on each label.")
    for section in defaults.SECTION_ORDER:
        keys = [k for k, m in defaults.FIELD_METADATA.items() if m["section"] == section]
        if not keys:
            continue
        with st.expander(section, expanded=(section == "Scenario")):
            cols = st.columns(2)
            for i, key in enumerate(keys):
                meta = defaults.FIELD_METADATA[key]
                label = f"{key} ({meta['unit']}){_source_badge(key)}"
                val = a[key]
                target = cols[i % 2]
                if isinstance(val, bool):
                    a[key] = target.checkbox(label, value=val, help=meta["help"], key=f"a_{key}")
                elif isinstance(val, (int, float)):
                    a[key] = target.number_input(label, value=float(val), help=meta["help"],
                                                 key=f"a_{key}")
                else:
                    a[key] = target.text_input(label, value=str(val), help=meta["help"],
                                               key=f"a_{key}")


# ---------------------------------------------------------------------------
# Asset catalog + dependency tabs (editable data editors).
# ---------------------------------------------------------------------------

def assets_tab() -> None:
    st.caption("Editable asset catalog. source_class = legacy_lunar_analog_placeholder "
               "on seed rows. Add/remove rows freely.")
    df = pd.DataFrame(st.session_state.assets, columns=defaults.ASSET_COLUMNS)
    edited = st.data_editor(df, num_rows="dynamic", use_container_width=True,
                            key="asset_editor")
    st.session_state.assets = edited.to_dict("records")


def dependencies_tab() -> None:
    st.caption("Editable dependency table. rule: -1 = prerequisite must land on a "
               "strictly earlier mission; 0 = same or earlier mission.")
    df = pd.DataFrame(st.session_state.dependencies, columns=defaults.DEPENDENCY_COLUMNS)
    edited = st.data_editor(df, num_rows="dynamic", use_container_width=True,
                            key="dep_editor")
    st.session_state.dependencies = edited.to_dict("records")


# ---------------------------------------------------------------------------
# Missions, readiness, tables.
# ---------------------------------------------------------------------------

def missions_tab(results: dict) -> None:
    m = results["missions"]
    st.write(f"**Packed setup missions:** {m['setup_missions_packed']} "
             f"(naive ceil(mass/payload) = {m['setup_missions_simple']}). "
             f"**Pre-crew missions:** {m['pre_crew_missions']}. "
             f"Crew may arrive after mission {m['crew_arrival_index']}.")
    if m["dependency_violations"]:
        st.error(f"{len(m['dependency_violations'])} dependency violation(s): "
                 f"{m['dependency_violations']}")
    rows = []
    for mission in m["manifest"]:
        for it in mission.items:
            rows.append({
                "mission": mission.index + 1, "asset": it.asset_name,
                "qty": round(it.quantity, 2), "mass_kg": round(it.mass_kg, 1),
                "volume_m3": round(it.volume_m3, 2), "bucket": it.bucket,
                "criticality": it.criticality, "pre_crew": it.must_arrive_before_crew,
                "partial": it.is_partial})
    st.dataframe(pd.DataFrame(rows), use_container_width=True, height=400)

    summary = [{"mission": mm.index + 1, "items": len(mm.items),
                "allocated_mass_kg": round(mm.allocated_mass_kg, 1),
                "mass_margin_kg": round(results["usable_payload_kg"] - mm.allocated_mass_kg, 1),
                "allocated_volume_m3": round(mm.allocated_volume_m3, 2),
                "overweight": mm.overweight} for mm in m["manifest"]]
    st.subheader("Mission summary")
    st.dataframe(pd.DataFrame(summary), use_container_width=True)


def _status_icon(status: str) -> str:
    return {"green": "🟢", "yellow": "🟡", "red": "🔴"}.get(status, "⚪")


def readiness_tab(results: dict) -> None:
    ready = results["readiness"]
    if ready["crew_arrival_allowed"]:
        st.success("✅ Crew arrival allowed.")
    else:
        st.error("⛔ Crew arrival blocked: " + ", ".join(ready["blocking_checks"]))

    st.subheader("Crew-arrival readiness")
    st.dataframe(pd.DataFrame([
        {"": _status_icon(c["status"]), "check": c["name"], "value": c["value"],
         "requirement": c["requirement"]} for c in ready["crew_checks"]],
    ), use_container_width=True, height=430)

    st.subheader("Sustainment readiness")
    st.dataframe(pd.DataFrame([
        {"": _status_icon(c["status"]), "check": c["name"], "value": c["value"],
         "requirement": c["requirement"]} for c in ready["sustainment_checks"]],
    ), use_container_width=True)


def tables_tab(results: dict) -> None:
    st.subheader("Life-support mass balance")
    ls = results["life_support"]
    st.dataframe(pd.DataFrame([
        {"resource": k, **{kk: round(vv, 1) if isinstance(vv, (int, float)) else vv
                           for kk, vv in v.items()}}
        for k, v in ls.items() if k in ("water", "oxygen", "food")]),
        use_container_width=True)

    st.subheader("Power balance")
    st.json({k: round(v, 2) for k, v in results["power"].items()
             if isinstance(v, (int, float))})

    st.subheader("Required asset quantities (active)")
    qrows = [{"asset": r["asset_name"], "category": r["category"],
              "quantity": r["quantity_required"], "unit_mass_kg": r["unit_mass_kg"],
              "active": r["active"]} for r in results["assets"]["quantities"]]
    st.dataframe(pd.DataFrame(qrows), use_container_width=True)

    st.subheader("Initial landed mass by category")
    st.dataframe(pd.DataFrame(
        [(b, round(m, 1)) for b, m in results["mass"]["buckets"].items()],
        columns=["category", "mass_kg"]), use_container_width=True)


# ---------------------------------------------------------------------------
# Sensitivity, comparison, legacy, import/export.
# ---------------------------------------------------------------------------

def sensitivity_tab() -> None:
    st.caption("Vary one parameter at a time; the engine is re-run for each value.")
    params = st.multiselect("Parameters to sweep", list(sensitivity.DEFAULT_SWEEPS),
                            default=["crew_count", "landed_payload_kg_per_starship"])
    if st.button("Run sensitivity sweep"):
        sweeps = {p: sensitivity.DEFAULT_SWEEPS[p] for p in params}
        rows = sensitivity.run_sensitivity(assumptions(), sweeps,
                                           st.session_state.assets,
                                           st.session_state.dependencies)
        st.dataframe(pd.DataFrame(rows), use_container_width=True, height=500)


def compare_tab(results: dict) -> None:
    st.caption("Save the current scenario, then compare saved scenarios side by side.")
    name = st.text_input("Snapshot name", value=results["dashboard"]["scenario_name"])
    if st.button("Save current scenario snapshot"):
        st.session_state.saved_scenarios[name] = results["dashboard"]
        st.success(f"Saved '{name}'.")
    if st.session_state.saved_scenarios:
        df = pd.DataFrame(st.session_state.saved_scenarios).T
        keep = ["crew_count", "operating_mode", "total_initial_landed_mass_kg",
                "cargo_starships_full_setup", "cargo_starships_pre_crew",
                "resupply_mass_per_window_kg", "power_margin_kw", "storage_autonomy_sols",
                "limiting_resource", "crew_arrival_allowed"]
        st.dataframe(df[[k for k in keep if k in df.columns]], use_container_width=True)
        if st.button("Clear saved snapshots"):
            st.session_state.saved_scenarios = {}
            st.rerun()


def legacy_tab() -> None:
    st.caption("Exact reproduction of the legacy lunar-analog reference case. "
               "These are PLACEHOLDERS, shown to validate the rebuilt engine.")
    s = legacy.legacy_summary()
    c = st.columns(4)
    c[0].metric("Day peak power", f"{s['day_power']['total_peak_power_kw']} kW")
    c[1].metric("Day continuous power", f"{s['day_power']['total_continuous_power_kw']} kW")
    c[2].metric("Night energy (thrive)", f"{s['night_thrive']['night_energy_kwh']:,.1f} kWh")
    c[3].metric("Night energy (survive)", f"{s['night_survive']['night_energy_kwh']:,.1f} kWh")
    c = st.columns(3)
    c[0].metric("Total mass thrive", f"{s['total_mass']['total_thrive_kg']:,.1f} kg")
    c[1].metric("Total mass survive", f"{s['total_mass']['total_survive_kg']:,.1f} kg")
    c[2].metric("Total mass w/ FSP", f"{s['total_mass']['total_fsp_kg']:,.1f} kg")
    st.subheader("Legacy total-mass rollup")
    st.dataframe(pd.DataFrame([{
        "item": l.item, "qty_thrive": l.qty_thrive, "mass_thrive_kg": l.mass_thrive_kg,
        "mass_survive_kg": l.mass_survive_kg, "mass_fsp_kg": l.mass_fsp_kg, "note": l.note
    } for l in s["total_mass"]["lines"]]), use_container_width=True)
    st.subheader("Legacy mission manifest (reference)")
    st.dataframe(pd.DataFrame([vars(m) for m in s["manifest"]]), use_container_width=True)


def export_tab(results: dict) -> None:
    a = assumptions()
    assets = st.session_state.assets
    deps = st.session_state.dependencies

    st.subheader("Download")
    c = st.columns(3)
    c[0].download_button("Scenario package (JSON)",
                         io_utils.scenario_to_json(a, assets, deps),
                         file_name="mars_scenario.json", mime="application/json")
    c[1].download_button("Assumptions (JSON)", io_utils.assumptions_to_json(a),
                         file_name="assumptions.json", mime="application/json")
    c[2].download_button("Asset catalog (CSV)", io_utils.assets_to_csv(assets),
                         file_name="assets.csv", mime="text/csv")
    c = st.columns(3)
    c[0].download_button("Dependencies (CSV)", io_utils.dependencies_to_csv(deps),
                         file_name="dependencies.csv", mime="text/csv")
    c[1].download_button("Mission manifest (CSV)", io_utils.manifest_to_csv(results),
                         file_name="mission_manifest.csv", mime="text/csv")
    c[2].download_button("Dashboard (CSV)", io_utils.dashboard_to_csv(results),
                         file_name="dashboard.csv", mime="text/csv")

    try:
        xlsx = io_utils.export_excel(results, assets)
        st.download_button("📊 Full workbook (Excel)", xlsx,
                           file_name="mars_logistics.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    except RuntimeError as exc:
        st.info(str(exc))

    st.subheader("Upload")
    up = st.file_uploader("Import a scenario package (JSON), assumptions (JSON), "
                          "assets (CSV), or dependencies (CSV)",
                          type=["json", "csv"])
    if up is not None:
        text = up.getvalue().decode("utf-8")
        try:
            if up.name.endswith(".json"):
                if '"mars_logistics_scenario"' in text or '"assets"' in text:
                    a2, assets2, deps2 = io_utils.scenario_from_json(text)
                    st.session_state.assumptions = a2
                    st.session_state.assets = assets2
                    st.session_state.dependencies = deps2
                    st.success("Imported scenario package.")
                else:
                    st.session_state.assumptions = io_utils.assumptions_from_json(text)
                    st.success("Imported assumptions.")
            elif "depends_on_asset_id" in text.splitlines()[0]:
                st.session_state.dependencies = io_utils.dependencies_from_csv(text)
                st.success("Imported dependencies.")
            else:
                st.session_state.assets = io_utils.assets_from_csv(text)
                st.success("Imported asset catalog.")
            st.rerun()
        except Exception as exc:  # pragma: no cover - UI feedback
            st.error(f"Import failed: {exc}")


# ---------------------------------------------------------------------------
# Main.
# ---------------------------------------------------------------------------

def main() -> None:
    sidebar()
    st.title("Mars Surface Logistics Calculator")
    st.caption("Estimates landed mass, cargo missions, power, consumables, ISRU, and "
               "resupply to sustain N humans on Mars using Starship-sized cargo missions.")

    results = run_model(assumptions(), st.session_state.assets,
                        st.session_state.dependencies)

    tabs = st.tabs(["Dashboard", "Charts", "Assumptions", "Assets", "Dependencies",
                    "Missions", "Readiness", "Tables", "Sensitivity", "Compare",
                    "Legacy", "Import/Export"])
    with tabs[0]:
        dashboard_tab(results)
    with tabs[1]:
        charts_tab(results)
    with tabs[2]:
        assumptions_tab()
    with tabs[3]:
        assets_tab()
    with tabs[4]:
        dependencies_tab()
    with tabs[5]:
        missions_tab(results)
    with tabs[6]:
        readiness_tab(results)
    with tabs[7]:
        tables_tab(results)
    with tabs[8]:
        sensitivity_tab()
    with tabs[9]:
        compare_tab(results)
    with tabs[10]:
        legacy_tab()
    with tabs[11]:
        export_tab(results)


if __name__ == "__main__":
    main()
