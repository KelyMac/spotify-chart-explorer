"""Chart validation and country-level feature summaries."""

from __future__ import annotations

import hashlib
import json
from numbers import Integral
from pathlib import Path

import numpy as np
import pandas as pd

FEATURES = {
    "energy": {"label": "Energy"},
    "danceability": {"label": "Danceability"},
    "valence": {"label": "Valence"},
    "acousticness": {"label": "Acousticness"},
}
EXPECTED_FIELDS = {
    "source_record", "spotify_id", "name", "artists", "daily_rank", "daily_movement", "weekly_movement",
    "country", "snapshot_date", "popularity", "is_explicit", "duration_ms", "album_name", "album_release_date",
    "danceability", "energy", "key", "loudness", "mode", "speechiness", "acousticness", "instrumentalness",
    "liveness", "valence", "tempo", "time_signature", "country_code", "iso3", "country_name", "duration_min",
}
REQUIRED_FIELDS = {"spotify_id", "name", "artists", "daily_rank", "snapshot_date", "country_code", "iso3", "country_name", *FEATURES}


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def fingerprint(root: Path) -> tuple:
    files = ["processed/charts_snapshot.csv", "processed/country_codes.csv", "output/charts_audit.json",
             "output/charts_date_coverage.csv", "output/preparation_manifest.json"]
    return tuple((name, (root / name).stat().st_mtime_ns, (root / name).stat().st_size) for name in files)


def validate_chart_frame(data: pd.DataFrame, expected_date: str) -> None:
    missing = REQUIRED_FIELDS - set(data.columns)
    if missing:
        raise ValueError(f"Required snapshot columns missing: {', '.join(sorted(missing))}")
    if data.empty:
        raise ValueError("The prepared snapshot has no country charts.")
    if set(data["snapshot_date"]) != {expected_date}:
        raise ValueError("Country charts do not share the prepared common date.")
    for code, rows in data.groupby("country_code"):
        if not code or len(rows) != 50 or rows["spotify_id"].nunique() != 50 or rows["spotify_id"].eq("").any():
            raise ValueError(f"{code or '(blank)'} does not have 50 distinct nonempty song IDs.")
        rank = pd.to_numeric(rows["daily_rank"], errors="coerce")
        if rank.isna().any() or set(rank) != set(range(1, 51)):
            raise ValueError(f"{code} does not have one of each rank 1–50.")


def read_snapshot(root: Path) -> tuple[pd.DataFrame, dict]:
    path = root / "processed/charts_snapshot.csv"
    data = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    missing = REQUIRED_FIELDS - set(data.columns)
    if missing:
        raise ValueError(f"Required snapshot columns missing: {', '.join(sorted(missing))}")
    audit = json.loads((root / "output/charts_audit.json").read_text(encoding="utf-8"))
    manifest = json.loads((root / "output/preparation_manifest.json").read_text(encoding="utf-8"))
    hashes = {entry["path"]: entry["sha256"] for entry in manifest["generated_files"]}
    if digest(path) != hashes.get("processed/charts_snapshot.csv"):
        raise ValueError("charts_snapshot.csv does not match its recorded checksum.")
    coverage = pd.read_csv(root / "output/charts_date_coverage.csv", dtype={"chart_date": str})
    chosen = coverage.sort_values(["complete_countries", "chart_date"]).iloc[-1]
    if chosen["chart_date"] != audit["selected_date"]:
        raise ValueError("The prepared date is inconsistent with the maximum-complete-country rule.")
    validate_chart_frame(data, audit["selected_date"])
    mapping = pd.read_csv(root / "processed/country_codes.csv", dtype=str, keep_default_na=False, encoding="utf-8-sig")
    country_mapping = mapping[mapping["country_type"].eq("country")].set_index("country_code")
    bad = set(data["country_code"]) - set(country_mapping.index)
    if bad:
        raise ValueError(f"Snapshot includes unclassified, Global or unknown country codes: {sorted(bad)}")
    for field in ("iso3", "country_name"):
        if not data[field].eq(data["country_code"].map(country_mapping[field])).all():
            raise ValueError(f"Snapshot {field} does not match the prepared country mapping.")
    invalid = {}
    for feature in FEATURES:
        numeric = pd.to_numeric(data[feature], errors="coerce")
        valid = numeric.between(0, 1) & np.isfinite(numeric)
        invalid[feature] = int((data[feature].str.strip().ne("") & ~valid).sum())
        data[feature] = numeric.where(valid)
    data["daily_rank"] = pd.to_numeric(data["daily_rank"])
    countries = data[["country_code", "iso3", "country_name"]].drop_duplicates().sort_values("country_name")
    metadata = {"snapshot_date": audit["selected_date"], "countries": len(countries), "rows": len(data),
                "actual_columns": list(data.columns), "missing_expected_fields": sorted(EXPECTED_FIELDS - set(data.columns)),
                "invalid_numeric_cells": invalid, "blank_country_policy": audit["blank_country_policy"],
                "source": audit["source"], "snapshot_sha256": digest(path),
                "date_selection_rule": audit["date_selection_rule"]}
    return data, metadata


DEFAULT_MIN_VALID = 40


def validate_min_valid(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral) or not 1 <= value <= 50:
        raise ValueError("Minimum valid feature count must be an integer between 1 and 50.")
    return int(value)


def summarize_features(data: pd.DataFrame, min_valid: int = DEFAULT_MIN_VALID) -> pd.DataFrame:
    min_valid = validate_min_valid(min_valid)
    records = []
    for code, rows in data.groupby("country_code", sort=True):
        for feature in FEATURES:
            values = pd.to_numeric(rows[feature], errors="coerce")
            values = values[values.between(0, 1) & np.isfinite(values)]
            available = len(values) >= min_valid
            records.append({"country_code": code, "country_name": rows["country_name"].iloc[0],
                "iso3": rows["iso3"].iloc[0], "snapshot_date": rows["snapshot_date"].iloc[0], "feature": feature,
                "n_valid": len(values), "chart_tracks": len(rows), "min_valid": min_valid,
                "median": float(values.median()) if available else np.nan,
                "q1": float(values.quantile(.25)) if available else np.nan,
                "q3": float(values.quantile(.75)) if available else np.nan,
                "status": "Available" if available else "Insufficient data"})
    return pd.DataFrame(records)


def feature_values(data: pd.DataFrame, code: str, feature: str) -> pd.DataFrame:
    rows = data[data["country_code"].eq(code)].copy()
    numeric = pd.to_numeric(rows[feature], errors="coerce")
    valid = numeric.between(0, 1) & np.isfinite(numeric)
    rows = rows.loc[valid].copy()
    rows[feature] = numeric[valid]
    return rows.sort_values(["daily_rank", "spotify_id"])


def stable_jitter(code: str, track_id: str) -> float:
    """Visual offset only, independent of feature, input ordering and slot."""
    integer = int.from_bytes(hashlib.sha256(f"{code}\0{track_id}".encode()).digest()[:8], "big")
    return (integer / (2**64 - 1) - .5) * .32


def read_geography(root: Path) -> dict:
    path = root / "static/geo/world_50m.json"
    source = json.loads((root / "static/geo/source.json").read_text(encoding="utf-8"))
    if digest(path) != source["sha256"]:
        raise ValueError("Local world geography differs from its recorded source hash.")
    topology = json.loads(path.read_text(encoding="utf-8"))
    if topology.get("type") != "Topology" or "countries" not in topology.get("objects", {}):
        raise ValueError("The local geography is not a valid country TopoJSON resource.")
    geometries = topology["objects"]["countries"]["geometries"]
    return {"iso3_codes": sorted({geometry["id"] for geometry in geometries}),
            "centers": {geometry["id"]: geometry.get("properties", {}).get("ct") for geometry in geometries},
            "source": source}


def unmapped_countries(data: pd.DataFrame, geography: dict) -> pd.DataFrame:
    countries = data[["country_code", "country_name", "iso3"]].drop_duplicates()
    result = countries[~countries["iso3"].isin(geography["iso3_codes"])].copy()
    result["reason"] = "No exact ISO3 match in the local map geometry"
    return result
