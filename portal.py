import streamlit as st

st.set_page_config(page_title="Spotify Charts", page_icon="♫", layout="wide", initial_sidebar_state="collapsed")

page = st.navigation(
    [
        st.Page("app.py", title="RQ5 · Musical Characteristics", default=True),
        st.Page("pages/6_Q6_Shared_Songs.py", title="RQ6 · Shared Songs"),
    ],
    position="top",
)
page.run()
