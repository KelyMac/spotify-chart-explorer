"""Bundle map dependencies with the component instead of app/static routes."""

from pathlib import Path

from .q5_data import read_geography


def component_script(root: Path, filename: str) -> str:
    read_geography(root)
    plotly = (root / "static/q5_plotly.min.js").read_text(encoding="utf-8")
    topology = (root / "static/geo/world_50m.json").read_text(encoding="utf-8")
    renderer = (root / "src/ui" / filename).read_text(encoding="utf-8")
    # The bundled Plotly version reads this cache before requesting geography.
    return ("if (!window.Plotly) {\n" + plotly + "\n}\n"
            + "window.PlotlyGeoAssets ||= {topojson: {}};\n"
            + "window.PlotlyGeoAssets.topojson ||= {};\n"
            + "window.PlotlyGeoAssets.topojson.world_50m = " + topology + ";\n"
            + renderer)
