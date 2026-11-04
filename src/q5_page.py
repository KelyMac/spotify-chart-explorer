"""RQ5: musical characteristics by country."""

from __future__ import annotations

import html
import json
from pathlib import Path

import streamlit as st

from .country_state import get_chart_context, initialize_context, reset_context, select_country
from .q5_data import DEFAULT_MIN_VALID, FEATURES, fingerprint, read_geography, read_snapshot, summarize_features, unmapped_countries, validate_min_valid
from .q5_figures import ROLE_COLORS, build_distribution, build_map

ROOT = Path(__file__).resolve().parents[1]


@st.cache_data(show_spinner=False)
def load_data(root: str, file_signature: tuple):
    return read_snapshot(Path(root))


@st.cache_data(show_spinner=False)
def aggregate(data, min_valid):
    return summarize_features(data, min_valid)


@st.cache_data(show_spinner=False)
def geography(root: str, geo_mtime: int):
    return read_geography(Path(root))


@st.cache_resource(show_spinner=False)
def map_component(source_version: int):
    return st.components.v2.component("spotify_q5_country_map",
        html='''<div class="q5-map-root"><div class="q5-map-tools" role="toolbar" aria-label="Map navigation">
          <button type="button" data-map-action="in" aria-label="Zoom in" title="Zoom in">+</button>
          <button type="button" data-map-action="out" aria-label="Zoom out" title="Zoom out">−</button>
          <button type="button" data-map-action="world" aria-label="World view">World view</button>
          <label>Focus area <select aria-label="Map region"><option value="world">World</option><option value="asia">Asia</option><option value="europe">Europe</option><option value="africa">Africa</option><option value="north_america">North America</option><option value="south_america">South America</option><option value="oceania">Oceania</option></select></label>
          </div><div class="q5-map-error" role="alert" hidden></div><div class="q5-map-plot"></div></div>''',
        css="""
        .q5-map-root{width:100%;height:100%;font-family:Arial,sans-serif;display:flex;flex-direction:column}
        .q5-map-plot{width:100%;min-height:220px;flex:1;min-width:0}
        .q5-map-plot .hoverlayer{visibility:hidden!important}
        .q5-map-tools{min-height:34px;display:flex;flex-wrap:wrap;align-items:center;gap:6px;padding:0 0 3px;box-sizing:border-box;font-size:13px}
        .q5-map-tools button,.q5-map-tools select{font:inherit;min-height:28px;border:1px solid #CBD5E1;background:white;color:#17324D;border-radius:5px;padding:3px 8px;cursor:pointer}
        .q5-map-tools button:first-child,.q5-map-tools button:nth-child(2){font-size:18px;min-width:30px;padding:1px 8px}
        .q5-map-tools button:hover{background:#EFF6FF}.q5-map-tools label{display:flex;flex-wrap:wrap;align-items:center;gap:5px;margin-left:4px;max-width:100%}
        .q5-map-tools select{max-width:100%}
        .q5-map-error{padding:18px;border:1px solid #E7A0A0;border-radius:6px;background:#FFF4F4;color:#842029;font:15px/1.5 Arial,sans-serif}.q5-map-error[hidden]{display:none}
        """,
        js=(ROOT / "src/ui/q5_map.js").read_text(encoding="utf-8"), isolate_styles=False)


def _sync_widgets():
    context = get_chart_context(st.session_state)
    for role in ROLE_COLORS:
        st.session_state[f"q5_{role}"] = context[role]


def _country_changed(role, codes):
    message = select_country(st.session_state, role, st.session_state[f"q5_{role}"], codes)
    st.session_state["q5_notice"] = message
    _sync_widgets()


def _map_clicked(codes):
    result = st.session_state.get("q5_world_map", {})
    event = result.get("country_click") if isinstance(result, dict) else getattr(result, "country_click", None)
    if not event:
        return
    role = event.get("target", "country_a")
    st.session_state["q5_notice"] = select_country(st.session_state, role, event.get("code"), codes)
    _sync_widgets()


def _reset():
    reset_context(st.session_state)
    _sync_widgets()
    st.session_state["q5_feature"] = "energy"
    st.session_state["q5_target"] = "country_a"
    st.session_state["q5_notice"] = None
    st.session_state["q5_reset_epoch"] = st.session_state.get("q5_reset_epoch", 0) + 1


def _summary(summary, feature, context):
    selected = summary[summary["feature"].eq(feature)].set_index("country_code")
    rows = [selected.loc[context[role]] for role in ROLE_COLORS if context.get(role)]
    shared_count = (len(rows) == 2
                    and all(row["status"] == "Available" and row["n_valid"] == row["chart_tracks"] for row in rows)
                    and rows[0]["chart_tracks"] == rows[1]["chart_tracks"])
    lines, medians = [], {}
    for role, color in ROLE_COLORS.items():
        code = context[role]
        if not code:
            continue
        row = selected.loc[code]
        label = "A" if role == "country_a" else "B"
        value = f"Median <b>{row['median']:.3f}</b>" if row["status"] == "Available" else "<b>Insufficient data</b>"
        count = "" if shared_count else f'<small>{int(row["n_valid"])}/{int(row["chart_tracks"])} valid</small>'
        lines.append(f'<div class="q5-country-summary"><span class="q5-country-name" style="color:{color}"><b>{label}</b> · {html.escape(row["country_name"])}</span><span class="q5-country-values">{value}{count}</span></div>')
        if row["status"] == "Available":
            medians[role] = row["median"]
    if len(medians) == 2:
        lines.append(f'<div class="q5-difference"><span>Median A − Median B</span><b>{medians["country_a"] - medians["country_b"]:+.3f}</b></div>')
    elif len(lines) == 1:
        lines.append('<div class="q5-summary-prompt">Add a second country to compare distributions.</div>')
    elif not lines:
        lines.append('<div class="q5-summary-prompt">Choose countries using search or click the map.</div>')
    if shared_count:
        count = int(rows[0]["chart_tracks"])
        lines.append(f'<div class="q5-validity">Both countries: {count}/{count} valid songs</div>')
    st.html('<div class="q5-summary">' + "".join(lines) + "</div>")


def _restore_min_valid():
    """Repair blank/stale persisted state before it reaches aggregation."""
    try:
        value = validate_min_valid(st.session_state.get("q5_min_valid"))
    except ValueError:
        try:
            value = validate_min_valid(st.session_state.get("q5_last_min_valid"))
        except ValueError:
            value = DEFAULT_MIN_VALID
    st.session_state["q5_min_valid"] = value
    st.session_state["q5_last_min_valid"] = value


def render(root: Path = ROOT):
    st.markdown("<style>" + (ROOT / "src/ui/portal.css").read_text(encoding="utf-8") + """
    .q5-summary{font-size:14px;line-height:1.4;color:#334155;padding:2px 0 3px;box-sizing:border-box}
    .q5-country-summary{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:9px;align-items:center;padding:2px 0;border-bottom:1px solid #E7EDF3}
    .q5-country-name{min-width:0;font-weight:600;overflow-wrap:anywhere;white-space:normal}
    .q5-country-values{white-space:nowrap;text-align:right}.q5-country-values small{display:inline-block;margin-left:.5rem;font-size:12px;color:#64748B}
    .q5-difference{display:flex;justify-content:space-between;gap:8px;padding-top:6px;flex-wrap:wrap}
    .q5-summary-prompt{padding-top:5px;color:#64748B}
    .q5-validity{font-size:12px;color:#64748B;padding-top:4px}
    .q5-chart-title{display:block;min-height:24px;line-height:24px;font-size:16px;font-weight:600;color:#17324D;margin:0;box-sizing:border-box}
    .st-key-q5_reset{padding-top:1.72rem}
    </style>""", unsafe_allow_html=True)
    st.title("How Do Charting Songs Sound Across Countries?")
    try:
        data, metadata = load_data(str(root), fingerprint(root))
    except (OSError, ValueError, KeyError) as error:
        st.error(f"Prepared chart data is unavailable: {error}")
        st.info("Check that the processed/ and output/ data files are present.")
        return
    codes = data[["country_code", "country_name"]].drop_duplicates().sort_values("country_name")
    names = codes.set_index("country_code")["country_name"].to_dict()
    choices = codes["country_code"].tolist()
    context = initialize_context(st.session_state, metadata["snapshot_date"], choices)
    if st.session_state.get("q5_feature") not in FEATURES:
        st.session_state["q5_feature"] = "energy"
    _restore_min_valid()
    st.session_state.setdefault("q5_target", "country_a")
    for role in ROLE_COLORS:
        st.session_state.setdefault(f"q5_{role}", context[role])
    feature_col, a_col, b_col, view_col, reset_col = st.columns([1.25, 1.8, 1.8, 1.4, .65], gap="small")
    with feature_col:
        feature = st.selectbox("Musical characteristics", list(FEATURES), format_func=lambda code: FEATURES[code]["label"], key="q5_feature")
    with a_col:
        st.selectbox("Country A", [code for code in choices if code != context["country_b"]], index=None,
            format_func=lambda code: f"{names[code]} ({code})", placeholder="Search Country A…", key="q5_country_a",
            on_change=_country_changed, args=("country_a", choices))
    with b_col:
        st.selectbox("Country B", [code for code in choices if code != context["country_a"]], index=None,
            format_func=lambda code: f"{names[code]} ({code})", placeholder="Search Country B…", key="q5_country_b",
            on_change=_country_changed, args=("country_b", choices))
    with view_col:
        view = st.selectbox("View", ["Side by side", "Stacked", "Map focus", "Distribution focus"], key="q5_view")
    with reset_col:
        st.button("Reset", key="q5_reset", on_click=_reset, width="stretch")
    st.radio("Click map to select", ["country_a", "country_b"], format_func=lambda value: "Country A" if value == "country_a" else "Country B",
             horizontal=True, key="q5_target")
    if st.session_state.get("q5_notice"):
        st.warning(st.session_state["q5_notice"])
    context = get_chart_context(st.session_state)
    min_valid = st.session_state["q5_min_valid"]
    summary = aggregate(data, min_valid)
    label = FEATURES[feature]["label"]
    map_height = 388 if view == "Side by side" else 476
    distribution_height = 334 if view == "Side by side" else 400
    geo, unmatched, map_error = None, data.iloc[0:0][["country_code", "country_name", "iso3"]], None
    try:
        geo_file = root / "static/geo/world_50m.json"
        geo = geography(str(root), geo_file.stat().st_mtime_ns)
        unmatched = unmapped_countries(data, geo)
        if not st.get_option("server.enableStaticServing"):
            raise ValueError("Local static serving is disabled. Start Streamlit from the project directory.")
        if not (root / "static/q5_plotly.min.js").is_file():
            raise ValueError("Missing static/q5_plotly.min.js.")
    except (OSError, ValueError, KeyError) as error:
        map_error = str(error)

    def show_map():
        st.html(f'<div class="q5-chart-title">{label} · country medians</div>')
        if map_error:
            st.error(f"World map unavailable: {map_error}")
            return
        figure = build_map(summary, feature, context, geo, map_height - 34, st.session_state.get("q5_reset_epoch", 0))
        base = st.get_option("server.baseUrlPath").strip("/")
        static_url = f"/{base + '/' if base else ''}app/static/"
        map_component((ROOT / "src/ui/q5_map.js").stat().st_mtime_ns)(data={"figure": json.loads(figure.to_json()), "feature": feature, "feature_label": label,
            "valid_codes": choices, "country_a": context["country_a"], "country_b": context["country_b"],
            "target": st.session_state["q5_target"], "plotly_url": static_url + "q5_plotly.min.js", "topojson_url": static_url + "geo/"},
            key="q5_world_map", height=map_height, on_country_click_change=lambda: _map_clicked(choices))
        if not unmatched.empty:
            st.warning(f"{len(unmatched)} chart geographies have no exact map match; use country search to compare them.")

    def show_distribution():
        st.html(f'<div class="q5-chart-title">{label} · song-level distributions</div>')
        fig = build_distribution(data, summary, feature, context, distribution_height)
        st.plotly_chart(fig, width="stretch", theme=None, config={"displayModeBar": False}, key="q5_distribution",
                        alt=f"{label} distributions for selected Country A and Country B; common linear axis from zero to {fig.layout.yaxis.range[1]}")
        _summary(summary, feature, context)

    if view == "Side by side":
        map_col, distribution_col = st.columns([1.6, 1], gap="medium")
        with map_col:
            show_map()
        with distribution_col:
            show_distribution()
    elif view == "Map focus":
        show_map()
    elif view == "Distribution focus":
        show_distribution()
    else:
        show_map()
        show_distribution()
