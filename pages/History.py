# pages/2_History.py

import streamlit as st
import pandas as pd

st.title("📜 Conversation & Notes History")
st.caption("Search past records from the current session based on Patient Name.")

# --- MOCK HISTORY DATA FOR MVP ---
if 'history_data' not in st.session_state:
    # This should store the final SOAP notes sent
    st.session_state.history_data = [
        {'Patient Name': 'Ramesh Kumar', 'Date': '2025-10-01', 'Diagnosis': 'Common Cold', 'SOAP Note': 'S: Body ache, O: Stable, A: Viral, P: Symptomatic care.'},
        {'Patient Name': 'Priya Singh', 'Date': '2025-09-28', 'Diagnosis': 'Headache', 'SOAP Note': 'S: Migraine history, O: Vitals stable, A: Tension Headache, P: Refer to Neurologist.'},
    ]

# Convert to DataFrame for easy filtering
df_history = pd.DataFrame(st.session_state.history_data)

# Search Bar
search_term = st.text_input("Search by Patient Name:", "").lower()

# Filter Logic
if search_term:
    df_filtered = df_history[df_history['Patient Name'].str.lower().str.contains(search_term)]
else:
    df_filtered = df_history

st.subheader(f"Results ({len(df_filtered)} notes found)")
st.dataframe(df_filtered[['Patient Name', 'Date', 'Diagnosis']], use_container_width=True)

# Detail View
if not df_filtered.empty:
    selected_name = st.selectbox("View Detailed Note For:", df_filtered['Patient Name'].unique())
    
    detailed_note = df_filtered[df_filtered['Patient Name'] == selected_name].iloc[0]
    
    st.markdown("### Full SOAP Note")
    st.text_area(f"Note for {selected_name}", value=detailed_note['SOAP Note'], height=300)