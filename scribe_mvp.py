# scribe_mvp.py - Swasthiq AI Scribe Minimum Viable Product (Live Recording Enabled)

import streamlit as st
import tempfile
import os
import smtplib
from email.mime.text import MIMEText
from twilio.rest import Client
from datetime import datetime
from email_validator import validate_email, EmailNotValidError

# --- Core Libraries for AI/ML/Utilities ---
try:
    from openai import OpenAI
except ImportError as e:
    st.error(f"Missing required library: {e}. Please install 'openai', 'twilio', and 'email-validator'.")
    st.stop()


# --- 1. CONFIGURATION AND INITIALIZATION ---

# Initialize OpenAI client (relies on OPENAI_API_KEY environment variable)
client = OpenAI()

# --- Streamlit Session State Management ---
def initialize_session_state():
    """Initializes or resets key variables in Streamlit's session state."""
    if 'current_stage' not in st.session_state:
        st.session_state.current_stage = 0  # 0: Setup, 1: Audio Recorded, 2: Processing, 3: Complete
    if 'audio_data' not in st.session_state:
        st.session_state.audio_data = None
    if 'raw_transcript' not in st.session_state:
        st.session_state.raw_transcript = ""
    if 'soap_note' not in st.session_state:
        st.session_state.soap_note = ""
    if 'contact_input' not in st.session_state:
        st.session_state.contact_input = ""
    if 'delivery_target' not in st.session_state:
        st.session_state.delivery_target = "Email"
    if 'doctor_name' not in st.session_state:
        st.session_state.doctor_name = "Dr. A. Sharma"

# --- 2. CORE LOGIC FUNCTIONS ---

def transcribe_audio_openai_api(audio_bytes):
    """Transcribes the audio bytes using the fast OpenAI Whisper API."""
    try:
        # Save audio bytes to a temporary WAV file for the API call
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_file:
            tmp_file.write(audio_bytes)
            tmp_file_path = tmp_file.name
        
        # Read the file-like object for the API
        with open(tmp_file_path, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-1", 
                file=audio_file,
                language="hi",
            )
        
        os.unlink(tmp_file_path) # Clean up temp file
        return transcript.text
        
    except Exception as e:
        return f"Transcription API Error: {e}"

def generate_soap_note_openai(transcript):
    """Sends the transcript to GPT-3.5-Turbo for structured SOAP note generation."""
    # (Same robust prompt as before)
    system_prompt = (
        "You are an expert medical scribe for an Indian doctor. Your task is to extract "
        "all clinical information from the raw transcript (which may contain mixed Hindi/English) "
        "and structure it strictly into the four sections of a clinical SOAP note. "
        "Keep the language professional, concise, and accurate."
    )
    
    user_prompt = (
        "**Raw Doctor-Patient Transcript:**\n"
        f"{transcript}\n\n"
        "**Please generate the note in the following structure:**\n"
        "S: [Subjective notes: Chief complaint, HPI, relevant history]\n"
        "O: [Objective notes: Vitals, physical exam, lab results]\n"
        "A: [Assessment: Final/Differential Diagnosis]\n"
        "P: [Plan: Treatments, medications (with dosage/frequency), and follow-up instructions]"
    )
    
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.1,
            max_tokens=700
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"AI Generation Error: {e}"

# --- Delivery Functions ---

def send_whatsapp_note(content, recipient_number):
    """Sends the note via Twilio WhatsApp API."""
    account_sid = os.environ.get('TWILIO_ACCOUNT_SID')
    auth_token = os.environ.get('TWILIO_AUTH_TOKEN')
    from_whatsapp_number = os.environ.get('TWILIO_WHATSAPP_NUMBER')
    
    if not all([account_sid, auth_token, from_whatsapp_number]):
        return "WhatsApp Failed: Twilio credentials not set up."

    try:
        client = Client(account_sid, auth_token)
        message_body = f"🩺 Swasthiq AI Note (Review Required)\n\n{content}"
        
        client.messages.create(
            from_=from_whatsapp_number,
            body=message_body,
            to=f'whatsapp:{recipient_number}'
        )
        return f"Success! Note sent via WhatsApp to {recipient_number}."
    except Exception as e:
        return f"WhatsApp API Failed: {e}. Check number format (+91XXXXXXXXXX) and Sandbox linkage."

def send_email_note(content, recipient_email):
    """Sends the note via Python's built-in SMTP library."""
    smtp_server = os.environ.get('SMTP_SERVER')
    smtp_port = int(os.environ.get('SMTP_PORT', 587))
    sender_email = os.environ.get('SENDER_EMAIL')
    sender_password = os.environ.get('SENDER_PASSWORD')

    if not all([smtp_server, sender_email, sender_password]):
        return "Email Failed: SMTP credentials not set up."
        
    msg = MIMEText(content)
    msg['Subject'] = f"Swasthiq AI Scribe - Final SOAP Note {datetime.now().strftime('%Y-%m-%d')}"
    msg['From'] = sender_email
    msg['To'] = recipient_email

    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, recipient_email, msg.as_string())
        return f"Success! Note sent via Email to {recipient_email}."
    except Exception as e:
        return f"Email SMTP Failed: {e}. Check SMTP credentials (App Password)."

# --- 3. STREAMLIT APPLICATION LAYOUT ---

initialize_session_state()

st.set_page_config(page_title="Swasthiq AI Scribe MVP", layout="wide")
st.title("Swasthiq AI Scribe MVP 🩺")
st.markdown("Automate your clinical documentation via voice-to-note.")
st.markdown("---")

# --------------------------
# --- STEP 1: USER SETUP & RECORDING ---
# --------------------------

st.header("Step 1: Record Consultation")

col_name, col_delivery = st.columns([1, 1])

with col_name:
    st.session_state.doctor_name = st.text_input(
        "Doctor's Name:", 
        value=st.session_state.doctor_name,
        key='name_input'
    )
    st.session_state.delivery_target = st.radio(
        "Select Delivery Method:",
        ("Email", "WhatsApp"),
        horizontal=True,
        key='delivery_radio'
    )

with col_delivery:
    if st.session_state.delivery_target == "WhatsApp":
        st.session_state.contact_input = st.text_input(
            "WhatsApp Number (e.g., +91XXXXXXXXXX):", 
            value=st.session_state.contact_input if st.session_state.contact_input else "+919876543210",
            key='contact_input_wa'
        )
    else:
        st.session_state.contact_input = st.text_input(
            "Email Address:", 
            value=st.session_state.contact_input if st.session_state.contact_input else "dr.a.sharma@clinic.com",
            key='contact_input_email'
        )

# --- Live Audio Input ---
st.subheader("Live Audio Recorder (Start/End)")
st.info("⚠️ **IMPORTANT:** You must grant browser permission for the microphone to work.")

# The st.audio_input widget serves as the combined START and STOP button
# The app logic will trigger when audio_data receives recorded bytes
st.session_state.audio_data = st.audio_input(
    "Click the microphone to START recording. Click it again to STOP (End Session).",
    sample_rate=16000, # Optimal for speech recognition
    key='audio_recorder'
)

# --------------------------
# --- STEP 2: PROCESSING LOGIC ---
# --------------------------

if st.session_state.audio_data is not None:
    # --- Triggered when recording stops ---
    st.session_state.current_stage = 1
    
    with st.spinner("Processing audio and generating note..."):
        
        # A. Run Transcription
        st.info("Step A: Transcribing Audio (Fast Whisper API)...")
        audio_bytes = st.session_state.audio_data.getvalue()
        raw_transcript = transcribe_audio_openai_api(audio_bytes)
        
        if "Error" in raw_transcript:
            st.error(raw_transcript)
            st.session_state.current_stage = 0
            st.stop()
            
        st.session_state.raw_transcript = raw_transcript
        
        # B. Generate SOAP Note
        st.info("Step B: Generating Structured SOAP Note (via GPT-3.5)...")
        st.session_state.soap_note = generate_soap_note_openai(raw_transcript)
        
        if "Error" in st.session_state.soap_note:
            st.error(st.session_state.soap_note)
            st.session_state.current_stage = 0
            st.stop()
            
        st.session_state.current_stage = 3
        st.success("Scribing Complete! Scroll down to review and send the final note.")
        st.balloons()


# --------------------------
# --- STEP 3: REVIEW & SEND ---
# --------------------------

if st.session_state.current_stage == 3:
    st.markdown("---")
    st.header("Step 2: Review, Edit & Send Final Note")

    st.caption(f"Note generated for: **{st.session_state.doctor_name}** | Sending via: **{st.session_state.delivery_target}** to **{st.session_state.contact_input}**")
    
    # Display the raw transcript for comparison
    with st.expander("View Raw Transcript (for reference)"):
        st.text(st.session_state.raw_transcript)
        
    # Editable Text Area for the Doctor
    final_note_content = st.text_area(
        "📝 Edit Final SOAP Note Here:",
        value=st.session_state.soap_note,
        height=500,
        key='final_note_edit'
    )

    if st.button(f"✅ FINALIZE & SEND NOTE", use_container_width=True, type="primary"):
        
        # Final content formatting
        full_message_content = (
            f"Doctor: {st.session_state.doctor_name}\n"
            f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"--- FINAL SOAP NOTE ---\n\n{final_note_content}"
        )
        
        with st.spinner(f"Sending note via {st.session_state.delivery_target}..."):
            
            # Decide delivery method
            if st.session_state.delivery_target == "WhatsApp":
                send_status = send_whatsapp_note(full_message_content, st.session_state.contact_input)
            else: # Email
                send_status = send_email_note(full_message_content, st.session_state.contact_input)
            
            if "Success!" in send_status:
                st.success(send_status)
                st.session_state.current_stage = 0 
                st.button("Start New Scribe Session", on_click=initialize_session_state)
            else:
                st.error(send_status)

# --- FOOTER / RESET ---
st.markdown("---")
if st.button("Reset Application"):
    st.session_state.clear()
    st.experimental_rerun()
