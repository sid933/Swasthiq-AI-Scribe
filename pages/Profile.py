# pages/3_Profile.py

import streamlit as st

st.title("👤 User Profile and Settings")
st.caption("Manage your API keys and contact preferences.")

st.subheader("Account Details")
st.info(f"Welcome back, **{st.session_state.get('doctor_name', 'Doctor')}**!")

# Display key settings (masked/non-sensitive for UI presentation)
st.markdown("""
- **Default Delivery:** E-mail (dr.a.sharma@clinic.com)
- **Transcription Service:** Sarvam AI
- **LLM Service:** OpenAI (GPT-3.5)
""")

st.subheader("User Actions")
if st.button("Reset All Session Data"):
    st.session_state.clear()
    st.rerun()