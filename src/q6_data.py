"""Song coverage and pairwise chart overlap."""

from __future__ import annotations

import pandas as pd

from .q5_data import validate_chart_frame


def analyze_snapshot(data: pd.DataFrame, snapshot_date: str) -> dict:
    validate_chart_frame(data, snapshot_date)
    countries = data[["country_code", "country_name", "iso3"]].drop_duplicates().sort_values("country_name").reset_index(drop=True)
    if countries.country_code.duplicated().any():
        raise ValueError("Country metadata are inconsistent within the snapshot.")
    def observed_text(series):
        # Retain distinct labels recorded for the same ID.
        return " | ".join(sorted(set(series.astype(str)) - {""}))

    songs = data.groupby("spotify_id", sort=True).agg(
        name=("name", observed_text), artists=("artists", observed_text),
        country_count=("country_code", "nunique"), best_rank=("daily_rank", "min"),
        median_rank=("daily_rank", "median"), worst_rank=("daily_rank", "max"),
        country_codes=("country_code", lambda values: ", ".join(sorted(set(values)))),
    ).reset_index()
    songs["coverage"] = songs.country_count / len(countries)
    songs = songs.sort_values(["country_count", "name", "spotify_id"], ascending=[False, True, True]).reset_index(drop=True)
    songs["coverage_rank"] = songs.country_count.rank(method="min", ascending=False).astype(int)
    return {"countries": countries, "songs": songs}


def shared_songs(data: pd.DataFrame, country_a: str, country_b: str, songs: pd.DataFrame) -> pd.DataFrame:
    valid = set(data.country_code)
    if country_a not in valid or country_b not in valid:
        raise ValueError("Both countries need complete charts on the selected date.")
    if country_a == country_b:
        raise ValueError("Country A and Country B must be different.")
    a = data.loc[data.country_code.eq(country_a), ["spotify_id", "daily_rank"]].rename(columns={"daily_rank": "rank_a"})
    b = data.loc[data.country_code.eq(country_b), ["spotify_id", "daily_rank"]].rename(columns={"daily_rank": "rank_b"})
    result = a.merge(b, on="spotify_id", how="inner", validate="one_to_one")
    result = result.merge(songs[["spotify_id", "name", "artists", "country_count"]], on="spotify_id", validate="one_to_one")
    return result.sort_values(["rank_a", "rank_b", "spotify_id"]).reset_index(drop=True)


def overlap_by_depth(shared: pd.DataFrame) -> pd.DataFrame:
    """Count IDs whose ranks are within both countries' Top k."""
    rows = []
    for cutoff in (10, 20, 30, 40, 50):
        count = int((shared.rank_a.le(cutoff) & shared.rank_b.le(cutoff)).sum())
        rows.append({"cutoff": cutoff, "shared_tracks": count, "overlap": count / cutoff})
    return pd.DataFrame(rows)


def song_countries(data: pd.DataFrame, spotify_id: str) -> pd.DataFrame:
    """Return the countries where a song charted, ordered by local rank."""
    rows = data.loc[data.spotify_id.eq(spotify_id), ["country_code", "country_name", "iso3", "daily_rank", "snapshot_date"]]
    if rows.empty:
        raise ValueError("This song ID is not present in the eligible snapshot.")
    return rows.sort_values(["daily_rank", "country_name"]).reset_index(drop=True)
