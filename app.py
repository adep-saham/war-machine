import sys, os
sys.path.append(os.path.dirname(__file__))

import streamlit as st
from ui.upload_data import render_upload_data
from ui.war_room import render_war_room

st.set_page_config(page_title="Gold War Room", layout="wide")

tabs = st.tabs(["Upload Data", "War Room"])

with tabs[0]:
    render_upload_data()

with tabs[1]:
    render_war_room()
