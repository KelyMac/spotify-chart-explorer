"""Country maps and song distributions."""

from __future__ import annotations

import html
import textwrap

import pandas as pd
import plotly.graph_objects as go

from .q5_data import FEATURES, feature_values, stable_jitter

ROLE_COLORS = {"country_a": "#0072B2", "country_b": "#D55E00"}
GREY = "#D9DEE5"


def _wrapped(value, width=32):
    return "<br>".join(html.escape(line) for line in textwrap.wrap(str(value), width=width))


def _hover(row, feature):
    label = FEATURES[feature]["label"]
    count = f"{int(row.n_valid)}/{int(row.chart_tracks)}"
    if row.status == "Available":
        text = f"Median: {row.median:.3f}<br>Q1 / Q3: {row.q1:.3f} / {row.q3:.3f}"
    else:
        text = f"Insufficient data<br>At least {int(row.min_valid)}/50 valid tracks required"
    return (f"<b>{_wrapped(row.country_name)}</b><br>Date: {row.snapshot_date}<br>Feature: {label}<br>"
            f"{text}<br>Valid tracks: {count}")


def _hover_details(row, feature):
    """Plain text fields for the cursor tooltip; format numbers once in Python."""
    available = row.status == "Available"
    return [row.country_code, row.country_name, row.snapshot_date, FEATURES[feature]["label"],
            f"{row.median:.3f}" if available else None,
            f"{row.q1:.3f}" if available else None,
            f"{row.q3:.3f}" if available else None,
            int(row.n_valid), int(row.chart_tracks), row.status, int(row.min_valid)]


def build_map(summary: pd.DataFrame, feature: str, context: dict, geography: dict, height=338, reset_epoch=0):
    values = summary[summary["feature"].eq(feature)].copy()
    values = values[values["iso3"].isin(geography["iso3_codes"])]
    fig = go.Figure()
    available = values[values["status"].eq("Available")]
    insufficient = values[~values["status"].eq("Available")]

    def trace(rows, role=None, grey=False):
        if rows.empty:
            return
        # Grey is a missing-data mask, not a numeric feature value.
        fig.add_trace(go.Choropleth(locations=rows["iso3"], locationmode="ISO-3",
            z=[1]*len(rows) if grey else rows["median"], zmin=0, zmax=1,
            colorscale=[[0, GREY], [1, GREY]] if grey else "Cividis", showscale=not role and not grey,
            colorbar={"title": {"text": "Median", "font": {"size": 13}}, "tickvals": [0, .5, 1],
                      "len": .75, "thickness": 12, "tickfont": {"size": 12}},
            marker={"line": {"color": ROLE_COLORS[role] if role else "#FFFFFF", "width": 3 if role else .45}},
            customdata=[_hover_details(row, feature) for row in rows.itertuples()],
            text=[_hover(row, feature) for row in rows.itertuples()], hovertemplate="%{text}<extra></extra>",
            name=role or ("Insufficient data" if grey else FEATURES[feature]["label"])))

    trace(available)
    trace(insufficient, grey=True)
    for role in ROLE_COLORS:
        selected = values[values["country_code"].eq(context.get(role))]
        if selected.empty:
            continue
        row = selected.iloc[0]
        trace(selected, role=role, grey=row["status"] != "Available")
        center = geography["centers"].get(row["iso3"])
        if center:
            fig.add_trace(go.Scattergeo(lon=[center[0]], lat=[center[1]], mode="markers+text",
                text=["A" if role == "country_a" else "B"], textposition="top center",
                textfont={"color": ROLE_COLORS[role], "size": 15},
                marker={"symbol": "circle-open", "size": 14, "color": ROLE_COLORS[role], "line": {"width": 2}},
                customdata=[[row["country_code"]]], hoverinfo="skip", showlegend=False, name=role))
    fig.update_layout(height=height, margin={"l": 0, "r": 0, "t": 0, "b": 0},
        paper_bgcolor="white", font={"family": "Arial, sans-serif", "size": 14}, showlegend=False,
        geo={"projection": {"type": "natural earth"}, "resolution": 50, "showframe": False,
             "showcoastlines": False, "showland": True, "landcolor": GREY, "bgcolor": "white",
             "showcountries": True, "countrycolor": "white", "countrywidth": .4,
             "lataxis": {"range": [-58, 85]}},
        dragmode="pan", uirevision=f"q5-world-{context['snapshot_date']}-{reset_epoch}")
    return fig


def build_distribution(data: pd.DataFrame, summary: pd.DataFrame, feature: str, context: dict, height=338):
    fig, labels = go.Figure(), []
    feature_summary = summary[summary["feature"].eq(feature)].set_index("country_code")
    for position, role in enumerate(ROLE_COLORS):
        code = context.get(role)
        role_label = "Country A" if role == "country_a" else "Country B"
        if not code:
            labels.append(role_label)
            if any(context.get(key) for key in ROLE_COLORS):
                fig.add_annotation(x=position, y=.5, yref="paper", text=f"Select<br>{role_label}", showarrow=False,
                                   font={"size": 13, "color": "#64748B"})
            continue
        row = feature_summary.loc[code]
        labels.append(role_label)
        if row["status"] != "Available":
            fig.add_annotation(x=position, y=.5, yref="paper", text=f"Insufficient data<br>{row['n_valid']}/50 valid<br>Need {row['min_valid']}",
                               showarrow=False, font={"size": 12, "color": "#64748B"})
            continue
        rows = feature_values(data, code, feature)
        color = ROLE_COLORS[role]
        # Use the same quartiles as the country summary.
        q1, median, q3 = float(row["q1"]), float(row["median"]), float(row["q3"])
        iqr = q3 - q1
        whisker_values = rows.loc[rows[feature].between(q1 - 1.5*iqr, q3 + 1.5*iqr), feature]
        fig.add_trace(go.Box(x=[position], q1=[q1], median=[median], q3=[q3], orientation="v", boxpoints=False,
            lowerfence=[float(whisker_values.min())], upperfence=[float(whisker_values.max())],
            width=.45, line={"color": color, "width": 2}, fillcolor="rgba(0,114,178,.10)" if role == "country_a" else "rgba(213,94,0,.10)",
            name=role_label, showlegend=False, meta={"role": role, "country_code": code, "feature": feature, "kind": "box", "n_valid": len(rows)}))
        fig.add_trace(go.Scatter(x=[position + stable_jitter(code, track_id) for track_id in rows["spotify_id"]],
            y=rows[feature], mode="markers", marker={"color": color, "opacity": .55, "size": 6},
            customdata=[[_wrapped(r["name"]), _wrapped(r["artists"]), int(r["daily_rank"]), str(r["spotify_id"])] for _, r in rows.iterrows()],
            hovertemplate=f"<b>%{{customdata[0]}}</b><br>Artist: %{{customdata[1]}}<br>Local chart rank: %{{customdata[2]}}<br>{FEATURES[feature]['label']}: %{{y:.3f}}<extra>{role_label}</extra>",
            showlegend=False, name=role_label,
            meta={"role": role, "country_code": code, "feature": feature, "kind": "songs", "n_valid": len(rows)}))
    if not any(context.get(key) for key in ROLE_COLORS):
        fig.add_annotation(x=.5, y=.5, xref="paper", yref="paper",
                           text="Select countries above<br>to compare their songs", showarrow=False,
                           font={"size": 13, "color": "#64748B"})
    fig.update_layout(template="plotly_white", height=height, margin={"l": 48, "r": 12, "t": 18, "b": 45},
        font={"family": "Arial, sans-serif", "size": 14}, showlegend=False, dragmode=False,
        yaxis={"title": FEATURES[feature]["label"], "range": [0, 1], "tickmode": "array",
               "tickvals": [0, .25, .5, .75, 1], "fixedrange": True},
        xaxis={"range": [-.55, 1.55], "tickvals": [0, 1], "ticktext": labels, "fixedrange": True},
        uirevision=f"q5-distribution-{feature}")
    return fig
