"""Chart overlap, shared-song ranks and song coverage figures."""

from __future__ import annotations

import html
import textwrap

import plotly.graph_objects as go

A, SHARED, GREY = "#0072B2", "#6B5CA5", "#D9DEE5"
B = "#D55E00"


def label(text, width=25):
    return "<br>".join(html.escape(line) for line in textwrap.wrap(str(text), width))


def style(fig, height=350, left=50):
    fig.update_layout(template="plotly_white", height=height, font={"family": "Arial, sans-serif", "size": 14},
                      margin={"l": left, "r": 15, "t": 12, "b": 50}, paper_bgcolor="white")
    return fig


def overlap_profile(profile, names):
    """Compare overlap at five chart depths on a common percentage scale."""
    fig = go.Figure(go.Scatter(
        x=profile.cutoff, y=profile.overlap, mode="lines+markers+text",
        line={"color": "rgba(107,92,165,0.45)", "width": 3, "dash": "solid"},
        marker={"color": SHARED, "size": 11, "line": {"color": "white", "width": 1.5}},
        text=[f"{row.overlap * 100:.1f}".rstrip("0").rstrip(".") + "%" for row in profile.itertuples()],
        textposition="top center", textfont={"size": 13, "color": "#17324D"},
        cliponaxis=False, customdata=profile[["shared_tracks", "cutoff"]].to_numpy(),
        hovertemplate="<b>Top %{customdata[1]} in both countries</b><br>Shared songs: %{customdata[0]} / %{customdata[1]}"
                      "<br>Overlap: %{y:.1%}<extra></extra>",
    ))
    style(fig, 340, 65)
    fig.update_layout(
        margin={"l": 65, "r": 25, "t": 35, "b": 65}, showlegend=False,
        xaxis={"title": "Chart cutoff<br>(in both countries)", "range": [7, 53],
               "tickvals": profile.cutoff.tolist(), "ticktext": [f"Top {k}" for k in profile.cutoff],
               "showgrid": False, "fixedrange": True},
        yaxis={"title": "Overlap (%)", "range": [0, 1], "tickformat": ".0%",
               "dtick": .2, "fixedrange": True, "gridcolor": "#E8EDF2", "zeroline": False},
        meta={"chart": "overlap_by_depth", "country_a": names[0], "country_b": names[1],
              "y_axis_scale": "fixed", "y_axis_upper": 1},
    )
    return fig


def rank_scatter(shared, names):
    fig = go.Figure()
    fig.add_shape(type="line", x0=1, y0=1, x1=50, y1=50,
                  line={"color": "#94A3B8", "width": 1.2, "dash": "dot"}, layer="below")
    if shared.empty:
        fig.add_annotation(x=.5, y=.5, xref="paper", yref="paper",
                           text="No shared songs<br>in these two Top 50 charts", showarrow=False)
    else:
        groups = [
            (shared.rank_a.lt(shared.rank_b), "Higher in A", A, "circle", "a"),
            (shared.rank_b.lt(shared.rank_a), "Higher in B", B, "diamond", "b"),
            (shared.rank_a.eq(shared.rank_b), "Same rank", "#64748B", "square", "equal"),
        ]
        for mask, title, color, symbol, category in groups:
            rows = shared.loc[mask]
            if rows.empty:
                continue
            fig.add_trace(go.Scatter(x=rows.rank_a, y=rows.rank_b, mode="markers", name=title,
                marker={"color": color, "symbol": symbol, "size": 9, "opacity": .85,
                        "line": {"color": "white", "width": 1}},
                customdata=[[
                    label(r.name, 32), label(r.artists, 32), r.spotify_id,
                    "Same rank" if category == "equal" else
                    f"{int(abs(r.rank_a-r.rank_b))} {'place' if abs(r.rank_a-r.rank_b) == 1 else 'places'} higher in {label(names[0] if category == 'a' else names[1], 24)}",
                ] for r in rows.itertuples()],
                hovertemplate="<b>%{customdata[0]}</b><br>Artist: %{customdata[1]}"
                    + f"<br>A · {label(names[0], 24)} rank: %{{x}}<br>B · {label(names[1], 24)} rank: %{{y}}"
                    + "<br>%{customdata[3]}<extra></extra>",
                meta={"rank_comparison": category}))
    style(fig, 360, 70)
    fig.update_layout(
        margin={"l": 70, "r": 15, "t": 60, "b": 65}, showlegend=not shared.empty,
        legend={"orientation": "h", "x": 0, "y": 1.06, "xanchor": "left", "yanchor": "bottom",
                "font": {"size": 11}, "itemclick": False, "itemdoubleclick": False},
        xaxis={"title": {"text": "Country A rank<br>(1 = highest)", "font": {"color": A}},
               "range": [.5, 50.5], "tickvals": [1, 10, 20, 30, 40, 50], "fixedrange": True,
               "gridcolor": "#EDF1F5", "zeroline": False},
        yaxis={"title": {"text": "Country B rank<br>(1 = highest)", "font": {"color": B}},
               "range": [50.5, .5], "tickvals": [1, 10, 20, 30, 40, 50], "fixedrange": True,
               "gridcolor": "#EDF1F5", "zeroline": False},
        meta={"chart": "shared_song_ranks", "country_a": names[0], "country_b": names[1], "shared_count": len(shared)})
    return fig


def coverage_bars(songs, total, selected=None, limit=10, *, page=0, show_rank=False):
    start = page * limit
    rows = songs.iloc[start:start + limit].iloc[::-1]
    fig = go.Figure(go.Bar(x=rows.country_count, y=rows.spotify_id, orientation="h",
        marker_color=[SHARED if track == selected else A for track in rows.spotify_id],
        text=[str(count) for count in rows.country_count], textposition="outside", cliponaxis=False,
        customdata=[[r.spotify_id, label(r.name, 40), label(r.artists, 40), r.coverage_rank] for r in rows.itertuples()],
        hovertemplate="<b>%{customdata[1]}</b><br>Artist: %{customdata[2]}<br>Coverage rank (ties share rank): %{customdata[3]}<br>Chart countries: %{x}/"+str(total)+"<extra></extra>"))
    fig.update_layout(xaxis={"title": "Chart countries", "range": [0, total], "fixedrange": True},
        yaxis={"tickvals": rows.spotify_id.tolist(),
               "ticktext": [f"#{int(row.coverage_rank)} · {label(row.name, 21)}" if show_rank else label(row.name, 23)
                            for row in rows.itertuples()], "fixedrange": True},
        clickmode="event+select", showlegend=False,
        meta={"chart": "coverage_ranking", "page": page, "start": start + 1,
              "stop": start + len(rows), "total_songs": len(songs), "selected_song": selected})
    # Give wrapped song labels enough vertical space on every ranking page.
    row_heights = [max(32, 16 * (label(row.name, 21 if show_rank else 23).count("<br>") + 1) + 12)
                   for row in rows.itertuples()]
    height = max(150, 85 + sum(row_heights))
    return style(fig, height, 185 if show_rank else 160)


def coverage_map(countries, appearances, song, snapshot_date, height=365):
    fig = go.Figure()
    present = set(appearances.country_code)
    absent = countries[~countries.country_code.isin(present)]
    if not absent.empty:
        fig.add_trace(go.Choropleth(locations=absent.iso3, z=[1]*len(absent), zmin=0, zmax=1,
            colorscale=[[0, "#EDF0F4"], [1, "#EDF0F4"]], showscale=False,
            text=[f"{label(name)}<br>{snapshot_date}<br>Not in this Top 50" for name in absent.country_name],
            hovertemplate="%{text}<extra></extra>", name="Not charting"))
    fig.add_trace(go.Choropleth(locations=appearances.iso3, z=appearances.daily_rank, zmin=1, zmax=50,
        colorscale="Cividis", colorbar={"title": {"text": "Rank"}, "tickvals": [1, 10, 25, 50], "thickness": 12, "len": .75},
        text=[f"<b>{label(r.country_name)}</b><br>{snapshot_date}<br>{label(song['name'],35)}<br>Local chart rank: {int(r.daily_rank)}/50" for r in appearances.itertuples()],
        hovertemplate="%{text}<extra></extra>", name="Chart rank"))
    fig.update_traces(locationmode="ISO-3", marker_line_color="white", marker_line_width=.5)
    fig.update_layout(height=height, margin={"l": 0, "r": 0, "t": 0, "b": 0}, font={"size": 14},
        geo={"projection": {"type": "natural earth"}, "resolution": 50, "showframe": False, "showcoastlines": False,
             "showland": True, "landcolor": GREY, "showcountries": True, "countrycolor": "white", "lataxis": {"range": [-58, 85]}},
        uirevision="q6-coverage-map", meta={"spotify_id": song["spotify_id"], "snapshot_date": snapshot_date})
    return fig
