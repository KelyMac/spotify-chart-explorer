import unittest
from itertools import combinations
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

from src.country_state import get_chart_context
from src.q5_data import read_snapshot
from src.q6_data import analyze_snapshot, overlap_by_depth, shared_songs, song_countries
from src.q6_figures import coverage_bars, coverage_map, overlap_profile, rank_scatter
from src.q6_page import _song_labels

ROOT = Path(__file__).resolve().parents[1]
PAGE = "pages/6_Q6_Shared_Songs.py"


def open_q6():
    from streamlit.testing.v1 import AppTest
    return AppTest.from_file(str(ROOT / "app.py"), default_timeout=20).run().switch_page(PAGE).run()


class Q6Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data, cls.metadata = read_snapshot(ROOT)
        cls.analysis = analyze_snapshot(cls.data, cls.metadata["snapshot_date"])
        cls.country_ids = {code: set(rows.spotify_id) for code, rows in cls.data.groupby("country_code")}
        cls.pairs = pd.DataFrame([
            {"country_a": a, "country_b": b, "shared_tracks": len(cls.country_ids[a] & cls.country_ids[b]),
             "overlap": len(cls.country_ids[a] & cls.country_ids[b]) / 50}
            for a, b in combinations(sorted(cls.country_ids), 2)
        ])

    def test_pairwise_song_ids_and_symmetry(self):
        pairs = pd.concat([self.pairs.sample(24, random_state=6105),
                           self.pairs[self.pairs.shared_tracks.eq(0)].head(1),
                           self.pairs.nlargest(1, "shared_tracks")])
        for pair in pairs.itertuples():
            expected = self.country_ids[pair.country_a] & self.country_ids[pair.country_b]
            forward = shared_songs(self.data, pair.country_a, pair.country_b, self.analysis["songs"])
            reverse = shared_songs(self.data, pair.country_b, pair.country_a, self.analysis["songs"])
            self.assertEqual(set(forward.spotify_id), expected)
            self.assertEqual(set(reverse.spotify_id), expected)
            ranks = forward.set_index("spotify_id")[["rank_a", "rank_b"]]
            reversed_ranks = reverse.set_index("spotify_id")[["rank_b", "rank_a"]]
            np.testing.assert_array_equal(ranks.sort_index(), reversed_ranks.sort_index())

    def test_coverage_counts_and_ranks_against_all_direct_rows(self):
        a = self.analysis
        self.assertEqual(a["songs"].country_count.sum(), len(self.data))
        self.assertLessEqual(a["songs"].country_count.max(), len(a["countries"]))
        actual = self.data.groupby("spotify_id").country_code.agg(lambda values: len(set(values)))
        for row in a["songs"].itertuples():
            self.assertEqual(row.country_count, actual.loc[row.spotify_id])
            self.assertEqual(row.coverage, row.country_count / len(a["countries"]))
        song = a["songs"].iloc[0]
        appearances = song_countries(self.data, song.spotify_id)
        expected = self.data[self.data.spotify_id.eq(song.spotify_id)]
        self.assertEqual(dict(zip(appearances.country_code, appearances.daily_rank)), dict(zip(expected.country_code, expected.daily_rank)))

    def test_missing_audio_does_not_change_membership_or_coverage(self):
        fixture = self.data.copy()
        for feature in ("energy", "danceability", "valence", "acousticness"):
            fixture[feature] = np.nan
        changed = analyze_snapshot(fixture, self.metadata["snapshot_date"])
        for key in ("countries", "songs"):
            pd.testing.assert_frame_equal(changed[key], self.analysis[key])

    def test_incomplete_or_absent_charts_are_not_zero_imputed(self):
        incomplete = self.data.drop(self.data.index[0])
        with self.assertRaises(ValueError):
            analyze_snapshot(incomplete, self.metadata["snapshot_date"])
        two = self.data[self.data.country_code.isin(["SG", "US"])]
        a = analyze_snapshot(two, self.metadata["snapshot_date"])
        self.assertEqual(set(a["countries"].country_code), {"SG", "US"})
        with self.assertRaises(ValueError):
            shared_songs(two, "SG", "JP", a["songs"])
        with self.assertRaises(ValueError):
            shared_songs(two, "SG", "SG", a["songs"])

    def test_shared_rows_and_zero_overlap_state(self):
        rng = np.random.default_rng(6105)
        pairs = self.pairs
        for index in rng.choice(len(pairs), size=12, replace=False):
            pair = pairs.iloc[index]
            common = shared_songs(self.data, pair.country_a, pair.country_b, self.analysis["songs"])
            self.assertEqual(len(common), pair.shared_tracks)
            for role in ("a", "b"):
                rows = self.data[self.data.country_code.eq(pair[f"country_{role}"])].set_index("spotify_id")
                for song in common.itertuples():
                    self.assertEqual(getattr(song, f"rank_{role}"), rows.loc[song.spotify_id, "daily_rank"])
        zero = pairs[pairs.shared_tracks.eq(0)].iloc[0]
        common = shared_songs(self.data, zero.country_a, zero.country_b, self.analysis["songs"])
        figure = rank_scatter(common, [zero.country_a, zero.country_b])
        self.assertEqual(len(figure.data), 0)
        self.assertIn("No shared songs", figure.layout.annotations[0].text)

    def test_song_labels_do_not_control_id_matching(self):
        fixture = self.data.copy()
        fixture["name"] = "Identical display title"
        unchanged = analyze_snapshot(fixture, self.metadata["snapshot_date"])
        pd.testing.assert_frame_equal(unchanged["countries"], self.analysis["countries"])
        self.assertEqual(len(unchanged["songs"]), len(self.analysis["songs"]))
        for pair in self.pairs.sample(12, random_state=6105).itertuples():
            original = shared_songs(self.data, pair.country_a, pair.country_b, self.analysis["songs"])
            renamed = shared_songs(fixture, pair.country_a, pair.country_b, unchanged["songs"])
            self.assertEqual(set(original.spotify_id), set(renamed.spotify_id))
        selected = self.analysis["songs"].iloc[0].spotify_id
        fixture.loc[fixture[fixture.spotify_id.eq(selected)].index[0], "name"] = "Alternate observed label"
        conflict = analyze_snapshot(fixture, self.metadata["snapshot_date"])
        self.assertIn(" | ", conflict["songs"].set_index("spotify_id").loc[selected, "name"])

    def test_overlap_depth_uses_both_top_k_and_agrees_with_id_sets(self):
        pairs = self.pairs
        selected = pd.concat([
            pairs.sample(12, random_state=6105),
            pairs[pairs.shared_tracks.eq(0)].head(1),
            pairs.nlargest(1, "shared_tracks"),
        ])
        for pair in selected.itertuples():
            common = shared_songs(self.data, pair.country_a, pair.country_b, self.analysis["songs"])
            profile = overlap_by_depth(common)
            for row in profile.itertuples():
                top = self.data[self.data.daily_rank.le(row.cutoff)]
                ids_a = set(top.loc[top.country_code.eq(pair.country_a), "spotify_id"])
                ids_b = set(top.loc[top.country_code.eq(pair.country_b), "spotify_id"])
                self.assertEqual(row.shared_tracks, len(ids_a & ids_b))
                self.assertEqual(row.overlap, len(ids_a & ids_b) / row.cutoff)
            self.assertTrue(profile.shared_tracks.is_monotonic_increasing)
            self.assertEqual(profile.iloc[-1].overlap, pair.overlap)
        # A shared song qualifies only when BOTH ranks meet the cutoff.
        fixture = pd.DataFrame({"rank_a": [1, 11, 50], "rank_b": [20, 1, 50]})
        self.assertEqual(overlap_by_depth(fixture).shared_tracks.tolist(), [0, 2, 2, 2, 3])
        all_shared = pd.DataFrame({"rank_a": range(1, 51), "rank_b": range(1, 51)})
        self.assertEqual(overlap_by_depth(all_shared).overlap.tolist(), [1]*5)
        self.assertEqual(overlap_by_depth(all_shared.iloc[:0]).overlap.tolist(), [0]*5)

    def test_figures_encode_correct_counts_fixed_scales_and_real_ranks(self):
        songs, countries = self.analysis["songs"], self.analysis["countries"]
        bars = coverage_bars(songs, len(countries))
        self.assertEqual(list(bars.data[0].x), songs.head(10).iloc[::-1].country_count.tolist())
        self.assertEqual([r[0] for r in bars.data[0].customdata], songs.head(10).iloc[::-1].spotify_id.tolist())
        for song in (songs.iloc[0], songs.iloc[-1]):
            appearances = song_countries(self.data, song.spotify_id)
            fig = coverage_map(countries, appearances, song.to_dict(), self.metadata["snapshot_date"])
            charted = fig.data[-1]
            self.assertEqual((charted.zmin, charted.zmax), (1, 50))
            self.assertEqual(dict(zip(charted.locations, charted.z)), dict(zip(appearances.iso3, appearances.daily_rank)))
            self.assertEqual(len(fig.data[0].locations) + len(charted.locations), len(countries))
        pair = shared_songs(self.data, "SG", "US", songs)
        points = rank_scatter(pair, ["SG", "US"])
        plotted = {}
        for trace in points.data:
            for x, y, details in zip(trace.x, trace.y, trace.customdata):
                self.assertNotIn(details[2], plotted)
                plotted[details[2]] = (x, y)
                expected = "a" if x < y else "b" if y < x else "equal"
                self.assertEqual(trace.meta["rank_comparison"], expected)
        self.assertEqual(plotted, {row.spotify_id: (row.rank_a, row.rank_b) for row in pair.itertuples()})
        self.assertEqual(list(points.layout.xaxis.range), [.5, 50.5])
        self.assertEqual(list(points.layout.yaxis.range), [50.5, .5])
        profile = overlap_by_depth(pair)
        curve = overlap_profile(profile, ["SG", "US"])
        self.assertEqual(list(curve.data[0].x), [10, 20, 30, 40, 50])
        self.assertEqual(list(curve.data[0].y), profile.overlap.tolist())
        self.assertEqual(list(curve.data[0].text), ["20%", "30%", "33.3%", "40%", "40%"])
        self.assertEqual(list(curve.layout.yaxis.range), [0, 1])
        self.assertEqual(curve.data[0].line.dash, "solid")
        self.assertEqual(list(curve.data[0].customdata[:, 0]), profile.shared_tracks.tolist())
        self.assertEqual(list(curve.data[0].customdata[:, 1]), profile.cutoff.tolist())
        # Use the same scale for every pair, including zero and full overlap.
        for peak in (0, .02, .1, .2, 1):
            fixture = profile.copy()
            fixture["overlap"] = [peak]*5
            chart = overlap_profile(fixture, ["A", "B"])
            self.assertEqual(list(chart.layout.yaxis.range), [0, 1])
            self.assertEqual(list(chart.data[0].y), [peak]*5)
            self.assertEqual(chart.layout.yaxis.tickformat, ".0%")

    def test_page_handoff_country_selection_and_reset(self):
        from streamlit.testing.v1 import AppTest
        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20).run()
        app.selectbox(key="q5_country_a").select("SG").run()
        app.selectbox(key="q5_country_b").select("US").run()
        app.switch_page(PAGE).run()
        self.assertFalse(app.exception)
        self.assertEqual(app.radio(key="q6_view").options,
                         ["Two-country overlap", "Cross-country coverage"])
        self.assertEqual(app.selectbox(key="q6_country_a").value, "SG")
        self.assertEqual(app.selectbox(key="q6_country_b").value, "US")
        self.assertIn("20 / 50", " ".join(m.value for m in app.markdown))
        app.selectbox(key="q6_country_b").select("JP").run()
        app.switch_page("app.py").run()
        self.assertFalse(app.exception)
        self.assertEqual(app.selectbox(key="q5_country_b").value, "JP")
        app.switch_page(PAGE).run()
        app.button[0].click().run()
        self.assertFalse(app.exception)
        self.assertIsNone(app.selectbox(key="q6_country_a").value)
        self.assertIsNone(get_chart_context(app.session_state)["country_b"])

    def test_page_empty_single_country_song_selection_and_view_persistence(self):
        app = open_q6()
        self.assertFalse(app.exception)
        self.assertTrue(app.info)
        app.selectbox(key="q6_country_a").select("SG").run()
        self.assertTrue(app.info)
        app.radio(key="q6_view").set_value("Cross-country coverage").run()
        self.assertFalse(app.exception)
        self.assertIsNone(app.selectbox(key="q6_song_picker").value)
        selected = self.analysis["songs"].iloc[0].spotify_id
        app.selectbox(key="q6_song_picker").select(selected).run()
        self.assertFalse(app.exception)
        self.assertIn("All charting countries and ranks (52)", [item.label for item in app.expander])
        self.assertFalse(app.caption)
        app.radio(key="q6_view").set_value("Two-country overlap").run()
        self.assertFalse(app.exception)
        self.assertEqual(app.selectbox(key="q6_country_a").value, "SG")
        self.assertEqual(app.session_state["q6_song"], selected)
        # Invalid saved views fall back without losing the selected song.
        app.switch_page("app.py").run()
        app.session_state["q6_view"] = "unknown_view"
        app.switch_page(PAGE).run()
        self.assertFalse(app.exception)
        self.assertEqual(app.radio(key="q6_view").value, "Two-country overlap")
        self.assertEqual(app.radio(key="q6_view").options,
                         ["Two-country overlap", "Cross-country coverage"])
        self.assertEqual(app.selectbox(key="q6_country_a").value, "SG")
        self.assertEqual(app.session_state["q6_song"], selected)
        app.radio(key="q6_view").set_value("Cross-country coverage").run()
        self.assertFalse(app.exception)
        self.assertEqual(app.selectbox(key="q6_song_picker").value, selected)
        app.button[0].click().run()
        self.assertIsNone(app.selectbox(key="q6_song_picker").value)

    def test_page_no_source_error_is_clear(self):
        with patch("src.q6_page.load_data", side_effect=ValueError("No complete charts available")):
            app = open_q6()
            self.assertFalse(app.exception)
            self.assertIn("No complete charts available", app.error[0].value)

    def test_song_search_hides_ids_and_preserves_distinct_same_name_entries(self):
        songs = self.analysis["songs"]
        labels = _song_labels(songs)
        self.assertEqual(len(set(labels.values())), len(songs))
        self.assertEqual(labels, _song_labels(songs.iloc[::-1]))
        for track, text in labels.items():
            self.assertNotIn(track, text)
        duplicate = songs[songs.duplicated(["name", "artists"], keep=False)]
        group = next(iter(duplicate.groupby(["name", "artists"])))[1]
        app = open_q6()
        app.radio(key="q6_view").set_value("Cross-country coverage").run()
        for row in group.itertuples():
            app.selectbox(key="q6_song_picker").select(row.spotify_id).run()
            self.assertFalse(app.exception)
            self.assertEqual(app.session_state["q6_song"], row.spotify_id)
            self.assertIn(f"All charting countries and ranks ({row.country_count})", [item.label for item in app.expander])

    def test_coverage_paging_search_follow_manual_browse_and_reset(self):
        songs = self.analysis["songs"]
        selected = songs.iloc[377]
        for page in (0, 1, 37, 196):
            expected = songs.iloc[page*10:(page+1)*10].iloc[::-1]
            bars = coverage_bars(songs, 72, selected.spotify_id, page=page, show_rank=True)
            self.assertEqual([row[0] for row in bars.data[0].customdata], expected.spotify_id.tolist())
            self.assertEqual(list(bars.data[0].x), expected.country_count.tolist())
            self.assertEqual(list(bars.layout.xaxis.range), [0, 72])
        app = open_q6()
        app.radio(key="q6_view").set_value("Cross-country coverage").run()
        self.assertTrue(app.button(key="q6_previous_page").disabled)
        app.selectbox(key="q6_song_picker").select(selected.spotify_id).run()
        self.assertEqual(app.selectbox(key="q6_page_picker").value, 37)
        app.button(key="q6_next_page").click().run()
        self.assertEqual(app.selectbox(key="q6_page_picker").value, 38)
        self.assertEqual(app.session_state["q6_song"], selected.spotify_id)
        app.radio(key="q6_view").set_value("Two-country overlap").run()
        app.radio(key="q6_view").set_value("Cross-country coverage").run()
        self.assertEqual(app.selectbox(key="q6_page_picker").value, 38)
        app.selectbox(key="q6_page_picker").select(196).run()
        self.assertTrue(app.button(key="q6_next_page").disabled)
        app.button[0].click().run()
        self.assertEqual(app.selectbox(key="q6_page_picker").value, 0)
        self.assertIsNone(app.selectbox(key="q6_song_picker").value)
        self.assertFalse(app.exception)


if __name__ == "__main__":
    unittest.main(verbosity=2)
