import streamlit as st
from ui.master_guardrail import render_master
from ui.price_input import render_price_input
from ui.market_share_data import render_market_share_upload
from ui.war_room import render_war_room
from ui.explorer import render_explorer

st.set_page_config(page_title="Gold War Room", layout="wide")

tabs = st.tabs([
    "Master & Guardrail",
    "Input Harga",
    "Market Share Data",
    "War Room",
    "Explorer"
])

with tabs[0]: render_master()
with tabs[1]: render_price_input()
with tabs[2]: render_market_share_upload()
with tabs[3]: render_war_room()
with tabs[4]: render_explorer()
