import hashlib
import importlib
from pathlib import Path
import sys

import streamlit as st

st.set_page_config(page_title="Spotify Charts", page_icon="♫", layout="wide", initial_sidebar_state="collapsed")


@st.cache_resource(show_spinner=False)
def refresh_modules(source_version):
    # Hosted hot updates can retain imported page modules in sys.modules.
    importlib.invalidate_caches()
    modules = ("src.q5_data", "src.country_state", "src.map_assets", "src.q5_figures",
               "src.q6_data", "src.q6_figures", "src.q5_page", "src.q6_page")
    for name in modules:
        if name in sys.modules:
            importlib.reload(sys.modules[name])


source_root = Path(__file__).resolve().parent / "src"
source_version = tuple((path.name, hashlib.sha256(path.read_bytes()).hexdigest())
                       for path in sorted(source_root.glob("*.py")))
refresh_modules(source_version)

page = st.navigation(
    [
        st.Page("app.py", title="RQ5 · Musical Characteristics", default=True),
        st.Page("pages/6_Q6_Shared_Songs.py", title="RQ6 · Shared Songs"),
    ],
    position="top",
)
page.run()
