# Home.py

import streamlit as st
from streamlit_option_menu import option_menu
import sys

# --- SIMULATE LOGIN CHECK ---
# For the MVP, we use a simple password screen.
def check_login():
    """Simple password check for MVP."""
    st.title("Swasthiq AI Scribe Login")
    password = st.text_input("Enter Clinic Password", type="password")
    
    if password == "swasthiq2025": # Simple hardcoded password for MVP
        st.session_state.logged_in = True
        st.experimental_rerun()
    elif password:
        st.error("Invalid password. Please contact support.")

if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    check_login()
    sys.exit()

# --- MAIN APP LAYOUT (If Logged In) ---

# The navigation bar mimics the Lyrebird tabs
selected = option_menu(
    menu_title=None,
    options=["Consult", "History", "Profile"],
    icons=["clipboard-data", "search", "person-circle"],
    menu_icon="cast",
    default_index=0,
    orientation="horizontal",
)

if selected == "Consult":
    # This acts as the container to load your 1_Consult.py logic
    # In a real multi-page Streamlit app, you would navigate.
    # For a unified look, this would ideally trigger the content of 1_Consult.py
    st.markdown("---")
    st.markdown("### Welcome to the Live Consultation Scribe. Please use the sidebar to proceed.")
    st.info("Please navigate to the sidebar to find the 'Consult' page. The main logic is now separated.")