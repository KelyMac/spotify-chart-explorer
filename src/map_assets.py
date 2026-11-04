"""Bundle map dependencies with the component instead of app/static routes."""

from pathlib import Path

from .q5_data import read_geography


def component_version(root: Path, filename: str) -> tuple:
    paths = [Path(__file__), root / "src/ui" / filename,
             root / "static/q5_plotly.min.js", root / "static/geo/world_50m.json",
             root / "static/geo/source.json"]
    return tuple(path.stat().st_mtime_ns for path in paths)


def component_script(root: Path, filename: str) -> str:
    read_geography(root)
    plotly = (root / "static/q5_plotly.min.js").read_text(encoding="utf-8")
    topology = (root / "static/geo/world_50m.json").read_text(encoding="utf-8")
    renderer = (root / "src/ui" / filename).read_text(encoding="utf-8")
    # Keep initialization inside the exported renderer: hosted environments can
    # recreate that function in a separate frame without its module globals.
    render_function = renderer.replace("export default function", "function", 1)
    return ("export default function (component) {\n"
            + "if (!window.Plotly) {\n" + plotly + "\n}\n"
            + "window.PlotlyGeoAssets ||= {topojson: {}};\n"
            + "window.PlotlyGeoAssets.topojson ||= {};\n"
            + "window.PlotlyGeoAssets.topojson.world_50m = " + topology + ";\n"
            + "return (\n" + render_function + "\n)(component);\n}\n")
