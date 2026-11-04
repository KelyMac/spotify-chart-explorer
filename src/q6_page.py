"""Q6 page: two-country overlap and song-to-country coverage."""

from __future__ import annotations

import json
from collections import Counter
from functools import partial
from pathlib import Path

import streamlit as st

from .country_state import get_chart_context, initialize_context, reset_context, select_country
from .q5_data import fingerprint, read_geography, unmapped_countries
from .q5_page import load_data
from .q6_data import analyze_snapshot, overlap_by_depth, shared_songs, song_countries
from .q6_figures import coverage_bars, coverage_map, overlap_profile, rank_scatter
from .map_assets import component_script

ROOT = Path(__file__).resolve().parents[1]
PAGE_SIZE = 10


@st.cache_data(show_spinner=False)
def cached_analysis(data, snapshot_date):
    return analyze_snapshot(data, snapshot_date)


@st.cache_resource(show_spinner=False)
def local_map(source_version):
    return st.components.v2.component("spotify_q6_coverage_map",
        html='<div class="q6-map-error" role="alert" hidden></div><div class="q6-map-plot"></div>',
        css='''
        .q6-map-error{padding:18px;background:#FFF4F4;color:#842029;border:1px solid #E7A0A0;border-radius:6px;font:14px/1.5 Arial}
        .q6-map-error[hidden]{display:none}
        ''',
        js=component_script(ROOT, "q6_map.js"), isolate_styles=False)


def _changed(role, codes):
    st.session_state["q6_notice"] = select_country(st.session_state, role, st.session_state[f"q6_{role}"], codes)


def _reset():
    reset_context(st.session_state)
    st.session_state["q6_song"] = None
    st.session_state["q6_coverage_page"] = 0
    st.session_state["q6_notice"] = None


def _bar_selected(key):
    event = st.session_state.get(key, {})
    points = event.get("selection", {}).get("points", [])
    if points:
        st.session_state["q6_song"] = points[0]["customdata"][0]


def _song_changed(song_pages):
    selected = st.session_state["q6_song_picker"]
    st.session_state["q6_song"] = selected
    if selected is not None:
        st.session_state["q6_coverage_page"] = song_pages[selected]


def _coverage_page_changed():
    st.session_state["q6_coverage_page"] = st.session_state["q6_page_picker"]


def _coverage_page_step(delta, page_count):
    st.session_state["q6_coverage_page"] = max(0, min(page_count - 1,
        st.session_state["q6_coverage_page"] + delta))


def _song_labels(songs):
    """Searchable labels omit IDs; distinct same-name records stay selectable."""
    labels = {row.spotify_id: f"{row.name} — {row.artists}" for row in songs.itertuples()}
    counts = Counter(labels.values())
    seen = Counter()
    # Streamlit deserializes selectbox choices from their formatted label.
    # Duplicate labels would select the wrong ID, so number only those entries.
    for track in sorted(labels):
        base = labels[track]
        if counts[base] > 1:
            seen[base] += 1
            labels[track] = f"{base} [Entry {seen[base]}]"
    return labels


def _table(frame, labels):
    display = frame[list(labels)].rename(columns=labels)
    st.dataframe(display, hide_index=True, width="stretch", height=min(330, 36*len(display)+40))


def render(root: Path = ROOT):
    st.markdown('<style>' + (ROOT / "src/ui/portal.css").read_text(encoding="utf-8") + '''
    .q6-stat{font-size:23px;font-weight:650;color:#17324D;margin:6px 0}
    </style>''', unsafe_allow_html=True)
    st.title("Which Songs Cross Borders?")
    try:
        data, metadata = load_data(str(root), fingerprint(root))
        analysis = cached_analysis(data, metadata["snapshot_date"])
    except (OSError, ValueError, KeyError) as error:
        st.error(f"Prepared chart data is unavailable: {error}")
        return
    countries, songs = analysis["countries"], analysis["songs"]
    codes = countries.country_code.tolist()
    names = countries.set_index("country_code").country_name.to_dict()
    context = initialize_context(st.session_state, metadata["snapshot_date"], codes)
    for role in ("country_a", "country_b"):
        st.session_state[f"q6_{role}"] = context[role]
    st.session_state.setdefault("q6_song", None)
    song_pages = {track: index // PAGE_SIZE for index, track in enumerate(songs.spotify_id)}
    page_count = max(1, (len(songs) + PAGE_SIZE - 1) // PAGE_SIZE)
    # Keep pagination when its widget is hidden by a view change.
    st.session_state.setdefault("q6_coverage_page", song_pages.get(st.session_state["q6_song"], 0))
    if st.session_state["q6_coverage_page"] not in range(page_count):
        st.session_state["q6_coverage_page"] = 0
    views = ["Two-country overlap", "Cross-country coverage"]
    if st.session_state.get("q6_view") not in views:
        st.session_state["q6_view"] = views[0]
    view_col, reset = st.columns([4, 1.2])
    with view_col:
        view = st.radio("Explore", views, horizontal=True, key="q6_view", label_visibility="collapsed")
    with reset:
        st.button("Reset", on_click=_reset, width="stretch")
    if view == "Two-country overlap":
        a, b = st.columns(2)
        with a:
            st.selectbox("Country A", [code for code in codes if code != context["country_b"]], index=None,
                format_func=lambda code: f"{names[code]} ({code})", placeholder="Search Country A", key="q6_country_a",
                on_change=_changed, args=("country_a", codes))
        with b:
            st.selectbox("Country B", [code for code in codes if code != context["country_a"]], index=None,
                format_func=lambda code: f"{names[code]} ({code})", placeholder="Search Country B", key="q6_country_b",
                on_change=_changed, args=("country_b", codes))
    if st.session_state.get("q6_notice"):
        st.warning(st.session_state["q6_notice"])
    context = get_chart_context(st.session_state)
    if view == "Two-country overlap":
        if not context["country_a"] or not context["country_b"]:
            st.info("Select two countries to compare their Top 50 charts.")
        else:
            common = shared_songs(data, context["country_a"], context["country_b"], songs)
            st.markdown(f'<div class="q6-stat">{len(common)} / 50 shared songs · {len(common)/50:.0%} overlap</div>', unsafe_allow_html=True)
            st.caption(f"A: {names[context['country_a']]} · B: {names[context['country_b']]} · Overlap = shared Spotify IDs / 50.")
            left, right = st.columns([1, 1.1])
            with left:
                st.subheader("Shared songs at different chart depths")
                profile = overlap_by_depth(common)
                st.plotly_chart(overlap_profile(profile, [context["country_a"], context["country_b"]]),
                    width="stretch", config={"displayModeBar": False}, key="q6_overlap_profile")
            with right:
                st.subheader("Which country ranks each song higher?")
                st.plotly_chart(rank_scatter(common, [names[context["country_a"]], names[context["country_b"]]]),
                    width="stretch", config={"displayModeBar": False}, key="q6_rank_scatter")
                st.caption("Each marker is one shared song. Dotted diagonal: equal rank in both countries.")
            with st.expander(f"Shared songs and both ranks ({len(common)})"):
                _table(common, {"name": "Track", "artists": "Artist", "rank_a": "Country A rank", "rank_b": "Country B rank", "country_count": f"Chart countries (of {len(countries)})"})
                st.download_button("Download shared songs CSV", common.drop(columns=["spotify_id"]).to_csv(index=False).encode("utf-8-sig"), "q6_shared_songs.csv", "text/csv")
    elif view == "Cross-country coverage":
        left, right = st.columns([1, 1.15])
        with left:
            st.subheader("Widest coverage song ranking")
            page = st.session_state["q6_coverage_page"]
            previous, picker, following = st.columns([1, 2.5, 1])
            with previous:
                st.button("Previous", key="q6_previous_page", disabled=page == 0, width="stretch",
                    on_click=_coverage_page_step, args=(-1, page_count))
            with picker:
                st.session_state["q6_page_picker"] = page
                st.selectbox("Song range", range(page_count), key="q6_page_picker", label_visibility="collapsed",
                    format_func=lambda value: f"Songs {value*PAGE_SIZE+1:,}–{min((value+1)*PAGE_SIZE, len(songs)):,} of {len(songs):,}",
                    on_change=_coverage_page_changed)
            with following:
                st.button("Next", key="q6_next_page", disabled=page == page_count-1, width="stretch",
                    on_click=_coverage_page_step, args=(1, page_count))
            # Reset chart selection when the page or selected song changes.
            bar_key = f"q6_coverage_bar_{page}_{st.session_state['q6_song'] or 'none'}"
            st.plotly_chart(coverage_bars(songs, len(countries), st.session_state["q6_song"],
                page=page, show_rank=True), width="stretch",
                config={"displayModeBar": False}, on_select=partial(_bar_selected, bar_key), selection_mode="points", key=bar_key)
        with right:
            st.subheader("Where did this song chart?")
            song_names = songs.set_index("spotify_id")
            song_labels = _song_labels(songs)
            st.session_state["q6_song_picker"] = st.session_state["q6_song"]
            selected = st.selectbox("Song", songs.spotify_id.tolist(), index=None, key="q6_song_picker", on_change=_song_changed,
                args=(song_pages,),
                placeholder="Search by track or artist",
                format_func=song_labels.__getitem__)
            if not selected:
                st.info("Select a song to see its charting countries and local ranks.")
            else:
                song = song_names.loc[selected].to_dict() | {"spotify_id": selected}
                appearances = song_countries(data, selected)
                try:
                    geo = read_geography(root)
                    if not unmapped_countries(data, geo).empty:
                        raise ValueError("Some country codes lack an exact geographic match; use the rank table.")
                    if not (root / "static/q5_plotly.min.js").is_file():
                        raise ValueError("Missing static/q5_plotly.min.js.")
                    figure = coverage_map(countries, appearances, song, metadata["snapshot_date"])
                    local_map((ROOT / "src/ui/q6_map.js").stat().st_mtime_ns)(
                        data={"figure": json.loads(figure.to_json())}, key="q6_map", height=365)
                except (OSError, ValueError, KeyError) as error:
                    st.error(f"World map unavailable: {error}")
                with st.expander(f"All charting countries and ranks ({len(appearances)})"):
                    _table(appearances, {"country_name": "Country / territory", "daily_rank": "Local rank", "country_code": "Code"})
        with st.expander("Full song coverage ranking and download"):
            _table(songs, {"coverage_rank": "Coverage rank", "name": "Track", "artists": "Artist", "country_count": f"Chart countries (of {len(countries)})", "coverage": "Share of eligible countries"})
            st.download_button("Download song coverage CSV", songs.drop(columns=["spotify_id"]).to_csv(index=False).encode("utf-8-sig"), "q6_song_coverage.csv", "text/csv")
