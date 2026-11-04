"""RQ5 data, figures and page state tests."""

from __future__ import annotations

import math
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from src.country_state import get_chart_context, initialize_context, reset_context, select_country
from src.q5_data import FEATURES, feature_values, read_geography, read_snapshot, summarize_features, unmapped_countries, validate_chart_frame
from src.q5_figures import ROLE_COLORS, build_distribution, build_map
from src.map_assets import component_script, component_name

ROOT = Path(__file__).resolve().parents[1]


def manual_quantile(values, fraction):
    values = sorted(float(value) for value in values)
    position = (len(values) - 1) * fraction
    low, high = math.floor(position), math.ceil(position)
    return values[low] + (values[high] - values[low]) * (position - low)


def app_text(app):
    return " ".join([m.value for m in app.markdown] + [element.proto.body for element in app.get("html")])


class Q5Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data, cls.metadata = read_snapshot(ROOT)
        cls.summary = summarize_features(cls.data)
        cls.geo = read_geography(ROOT)
        cls.context = {"version": 1, "snapshot_date": cls.metadata["snapshot_date"], "country_a": "SG", "country_b": "US"}

    def test_expected_schema_and_common_complete_date(self):
        self.assertEqual(self.metadata["missing_expected_fields"], [])
        validate_chart_frame(self.data, self.metadata["snapshot_date"])
        bad = self.data.copy()
        sg = bad["country_code"].eq("SG")
        bad.loc[bad[sg].index[0], "daily_rank"] = 2
        with self.assertRaises(ValueError):
            validate_chart_frame(bad, self.metadata["snapshot_date"])

    def test_three_countries_four_features_against_direct_values(self):
        for code in ("SG", "US", "JP"):
            for feature in FEATURES:
                with self.subTest(country=code, feature=feature):
                    values = [float(value) for value in self.data.loc[self.data["country_code"].eq(code), feature]
                              if math.isfinite(float(value)) and 0 <= float(value) <= 1]
                    row = self.summary[self.summary["country_code"].eq(code) & self.summary["feature"].eq(feature)].iloc[0]
                    self.assertEqual(row.n_valid, len(values))
                    for field, quantile in [("q1", .25), ("median", .5), ("q3", .75)]:
                        self.assertAlmostEqual(row[field], manual_quantile(values, quantile), places=12)

    def test_scatter_count_values_and_no_duplicate_box_outliers(self):
        for feature in FEATURES:
            fig = build_distribution(self.data, self.summary, feature, self.context)
            for trace in fig.data:
                code = trace.meta["country_code"]
                expected = feature_values(self.data, code, feature)
                if trace.type == "box":
                    self.assertFalse(trace.boxpoints)
                    self.assertAlmostEqual(trace.q1[0], manual_quantile(expected[feature], .25))
                    self.assertAlmostEqual(trace.median[0], manual_quantile(expected[feature], .5))
                    self.assertAlmostEqual(trace.q3[0], manual_quantile(expected[feature], .75))
                else:
                    self.assertEqual(len(trace.y), len(expected))
                    self.assertEqual(list(trace.y), expected[feature].tolist())
                    self.assertIn(FEATURES[feature]["label"], trace.hovertemplate)
                    self.assertEqual({row[3] for row in trace.customdata}, set(expected.spotify_id))
            self.assertEqual(tuple(fig.layout.yaxis.range), (0, 1))

    def test_missingness_threshold_boundary_does_not_filter_shared_chart(self):
        for missing, expected_n in [(10, 40), (11, 39), (50, 0)]:
            fixture = self.data.copy(deep=True)
            indexes = fixture[fixture.country_code.eq("SG")].index[:missing]
            fixture.loc[indexes, "energy"] = np.nan
            before_ids = set(fixture.spotify_id)
            summary = summarize_features(fixture, 40)
            row = summary[summary.country_code.eq("SG") & summary.feature.eq("energy")].iloc[0]
            self.assertEqual(row.n_valid, expected_n)
            self.assertEqual(set(fixture.spotify_id), before_ids)
            self.assertEqual(len(fixture), len(self.data))
            figure = build_distribution(fixture, summary, "energy", self.context)
            sg_songs = [t for t in figure.data if t.meta["country_code"] == "SG" and t.meta["kind"] == "songs"]
            if expected_n < 40:
                self.assertTrue(np.isnan(row["median"]))
                self.assertEqual(sg_songs, [])
                self.assertIn("Insufficient data", " ".join(a.text for a in figure.layout.annotations))
            else:
                self.assertEqual(len(sg_songs[0].y), 40)
            other_feature = summary[summary.country_code.eq("SG") & summary.feature.eq("valence")].iloc[0]
            self.assertEqual(other_feature.n_valid, 50)

    def test_invalid_feature_values_are_not_imputed_and_zero_is_valid(self):
        fixture = self.data.copy()
        fixture["energy"] = fixture["energy"].astype(object)
        indexes = fixture[fixture.country_code.eq("SG")].index[:5]
        for i, value in zip(indexes, [-.1, 1.1, np.inf, "invalid", 0]):
            fixture.at[i, "energy"] = value
        row = summarize_features(fixture).query("country_code == 'SG' and feature == 'energy'").iloc[0]
        self.assertEqual(row.n_valid, 46)
        values = feature_values(fixture, "SG", "energy")
        self.assertTrue(values.energy.eq(0).any())
        self.assertEqual(len(values), 46)

    def test_invalid_thresholds_raise_clear_validation_error(self):
        for value in (None, "40", True, 40.5, np.nan, 0, 51):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "integer between 1 and 50"):
                summarize_features(self.data, value)

    def test_streamlit_empty_threshold_state_restores_last_value_and_preserves_selection(self):
        from streamlit.testing.v1 import AppTest
        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20).run()
        app.session_state["q5_min_valid"] = None
        app.run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state["q5_min_valid"], 40)
        app.selectbox(key="q5_country_a").select("SG").run()
        app.selectbox(key="q5_country_b").select("US").run()
        app.selectbox(key="q5_feature").select("valence").run()
        app.session_state["q5_min_valid"] = 45
        app.run()
        app.session_state["q5_min_valid"] = None
        app.run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state["q5_min_valid"], 45)
        self.assertEqual(app.selectbox(key="q5_feature").value, "valence")
        self.assertEqual(app.selectbox(key="q5_country_a").value, "SG")
        self.assertEqual(app.selectbox(key="q5_country_b").value, "US")
        self.assertEqual(len(app.number_input), 0)

    def test_streamlit_recovers_existing_empty_threshold_state(self):
        from streamlit.testing.v1 import AppTest
        for last_value, expected in ((None, 40), (45, 45), (51, 40)):
            with self.subTest(last_value=last_value):
                app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20)
                app.session_state["q5_min_valid"] = None
                app.session_state["q5_last_min_valid"] = last_value
                app.run()
                self.assertFalse(app.exception)
                self.assertEqual(app.session_state["q5_min_valid"], expected)

    def test_reproducible_jitter_across_features_and_slots(self):
        energy = build_distribution(self.data, self.summary, "energy", self.context)
        valence = build_distribution(self.data, self.summary, "valence", self.context)
        for role in ROLE_COLORS:
            a = next(t for t in energy.data if t.meta["role"] == role and t.meta["kind"] == "songs")
            b = next(t for t in valence.data if t.meta["role"] == role and t.meta["kind"] == "songs")
            self.assertEqual(dict(zip((r[3] for r in a.customdata), a.x)), dict(zip((r[3] for r in b.customdata), b.x)))

    def test_map_fixed_scale_and_exact_country_mapping(self):
        self.assertTrue(unmapped_countries(self.data, self.geo).empty)
        for feature in FEATURES:
            figure = build_map(self.summary, feature, self.context, self.geo)
            main = figure.data[0]
            self.assertEqual((main.zmin, main.zmax), (0, 1))
            expected = self.summary[self.summary.feature.eq(feature)].set_index("iso3")
            for iso, value, text in zip(main.locations, main.z, main.text):
                self.assertAlmostEqual(value, expected.loc[iso, "median"])
                self.assertIn(FEATURES[feature]["label"], text)
                self.assertIn("Valid tracks: 50/50", text)
            for role, color in ROLE_COLORS.items():
                outline = next(t for t in figure.data if t.type == "choropleth" and t.name == role)
                self.assertEqual(outline.marker.line.color, color)
                self.assertEqual(outline.zmin, 0)
                self.assertEqual(outline.zmax, 1)
        bad = self.data.copy()
        bad.loc[bad.country_code.eq("SG"), "iso3"] = "ZZZ"
        self.assertEqual(unmapped_countries(bad, self.geo).country_code.tolist(), ["SG"])

    def test_shared_state_duplicate_guard_and_reset(self):
        state = {}
        initialize_context(state, self.metadata["snapshot_date"], self.data.country_code.unique())
        self.assertIsNone(select_country(state, "country_a", "SG", self.data.country_code.unique()))
        self.assertIsNotNone(select_country(state, "country_b", "SG", self.data.country_code.unique()))
        self.assertIsNone(get_chart_context(state)["country_b"])
        select_country(state, "country_b", "US", self.data.country_code.unique())
        reset_context(state)
        self.assertEqual(get_chart_context(state), {"version": 1, "snapshot_date": self.metadata["snapshot_date"], "country_a": None, "country_b": None})

    def test_streamlit_empty_single_two_feature_switch_and_reset(self):
        from streamlit.testing.v1 import AppTest
        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20).run()
        self.assertFalse(app.exception)
        component = app.get("bidi_component")[0].proto
        script = component_script(ROOT, "q5_map.js")
        self.assertEqual(component.js_content, script)
        self.assertEqual(component.component_name, component_name("q5", script))
        self.assertEqual(len(app.number_input), 0)
        self.assertIsNone(app.selectbox(key="q5_country_a").value)
        app.selectbox(key="q5_country_a").select("SG").run()
        self.assertFalse(app.exception)
        self.assertIn("Add a second country", app_text(app))
        app.selectbox(key="q5_country_b").select("US").run()
        for feature in FEATURES:
            app.selectbox(key="q5_feature").select(feature).run()
            self.assertFalse(app.exception)
            self.assertEqual(app.session_state["spotify_chart_context"]["country_a"], "SG")
            self.assertIn("Median A − Median B", app_text(app))
        stale = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20)
        stale.session_state["q5_feature"] = "unknown_feature"
        stale.session_state["spotify_chart_context"] = dict(app.session_state["spotify_chart_context"])
        stale.run()
        self.assertFalse(stale.exception)
        self.assertEqual(stale.selectbox(key="q5_feature").value, "energy")
        self.assertEqual(stale.selectbox(key="q5_country_a").value, "SG")
        self.assertEqual(stale.selectbox(key="q5_country_b").value, "US")
        self.assertEqual(len(stale.get("toggle")), 0)
        app.session_state["q5_min_valid"] = 45
        app.run()
        self.assertFalse(app.exception)
        app.button(key="q5_reset").click().run()
        self.assertFalse(app.exception)
        self.assertIsNone(app.selectbox(key="q5_country_a").value)
        self.assertIsNone(app.selectbox(key="q5_country_b").value)
        self.assertEqual(app.selectbox(key="q5_feature").value, "energy")

    def test_streamlit_synthetic_insufficient_and_empty_source_states(self):
        from streamlit.testing.v1 import AppTest
        fixture = self.data.copy()
        fixture.loc[fixture[fixture.country_code.eq("SG")].index[:11], "energy"] = np.nan
        with patch("src.q5_page.load_data", return_value=(fixture, self.metadata)):
            app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20).run()
            app.selectbox(key="q5_country_a").select("SG").run()
            self.assertFalse(app.exception)
            text = app_text(app)
            self.assertIn("Insufficient data", text)
            self.assertIn("39/50 valid", text)
            self.assertEqual(app.session_state["spotify_chart_context"]["country_a"], "SG")
        with patch("src.q5_page.load_data", side_effect=ValueError("No country charts are available")):
            app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20).run()
            self.assertFalse(app.exception)
            self.assertIn("No country charts", app.error[0].value)

    def test_portal_refreshes_stale_imported_page(self):
        import streamlit as st
        from streamlit.testing.v1 import AppTest

        st.cache_resource.clear()
        with patch("src.q5_page.map_component", side_effect=AssertionError("Stale page module was used")):
            app = AppTest.from_file(str(ROOT / "portal.py"), default_timeout=30).run()
            self.assertFalse(app.exception)
            component = app.get("bidi_component")[0].proto
            script = component_script(ROOT, "q5_map.js")
            self.assertEqual(component.js_content, script)
            self.assertEqual(component.component_name, component_name("q5", script))
        st.cache_resource.clear()


if __name__ == "__main__":
    unittest.main(verbosity=2)
