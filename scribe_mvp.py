# scribe_mvp.py - Swasthiq AI Scribe Minimum Viable Product

import streamlit as st
import tempfile
import os
import smtplib
from email.mime.text import MIMEText
from twilio.rest import Client
from datetime import datetime
import numpy as np
from email_validator import validate_email, EmailNotValidError

# --- Core Libraries for AI/ML/Utilities ---
try:
    import whisper
    from openai import OpenAI
except ImportError as e:
    st.error(f"Missing required library: {e}. Please install using pip.")
    st.stop()


# --- 1. CONFIGURATION AND INITIALIZATION ---

# Initialize OpenAI client (relies on OPENAI_API_KEY environment variable)
client = OpenAI()

# --- Streamlit Session State Management ---
def initialize_session_state():
    """Initializes or resets key variables in Streamlit's session state."""
    if 'current_stage' not in st.session_state:
        # 0: Setup, 1: Recording, 2: Uploaded, 3: Transcribed, 4: Scribing Complete
        st.session_state.current_stage = 0 
    if 'raw_transcript' not in st.session_state:
        st.session_state.raw_transcript = ""
    if 'soap_note' not in st.session_state:
        st.session_state.soap_note = ""
    if 'audio_file' not in st.session_state:
        st.session_state.audio_file = None
    if 'delivery_target' not in st.session_state:
        st.session_state.delivery_target = None
    if 'contact_input' not in st.session_state:
        st.session_state.contact_input = ""

# --- 2. CORE LOGIC FUNCTIONS ---

@st.cache_resource
def load_whisper_model():
    """Caches and loads the Whisper model for performance."""
    st.info("Downloading and loading Whisper 'base' model... (One-time step)")
    # Using 'base' model for decent speed/accuracy. Use 'large-v2' for production.
    return whisper.load_model("base")

def transcribe_audio_whisper(audio_path, model):
    """Transcribes the audio file using the local Whisper model."""
    try:
        # Transcribe with language hints for Hindi and English (code-mixing)
        result = model.transcribe(
            audio_path,
            fp16=False,
            language="hi",
            initial_prompt="This is a medical consultation between a doctor and patient in mixed Hindi and English.",
            temperature=0.0 # Use low temperature for deterministic transcription
        )
        return result["text"]
    except Exception as e:
        return f"Transcription Error: {e}"

def generate_soap_note_openai(transcript):
    """Sends the transcript to GPT-3.5-Turbo for structured SOAP note generation."""
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

def send_whatsapp_note(content, recipient_number):
    """Sends the note via Twilio WhatsApp API."""
    account_sid = os.environ.get('TWILIO_ACCOUNT_SID')
    auth_token = os.environ.get('TWILIO_AUTH_TOKEN')
    from_whatsapp_number = os.environ.get('TWILIO_WHATSAPP_NUMBER')
    
    if not all([account_sid, auth_token, from_whatsapp_number]):
        return "WhatsApp Failed: Twilio credentials not fully set up in environment."

    try:
        client = Client(account_sid, auth_token)
        message_body = (
            "🩺 Swasthiq AI Note (Review Required)\n"
            "----------------------------------\n"
            f"{content}"
        )
        
        client.messages.create(
            from_=from_whatsapp_number,
            body=message_body,
            to=f'whatsapp:{recipient_number}'
        )
        return f"Success! Note sent via WhatsApp to {recipient_number}."
        
    except Exception as e:
        return f"WhatsApp API Failed: {e}. Check number format (e.g., +91XXXXXXXXXX) and Sandbox linkage."

def send_email_note(content, recipient_email):
    """Sends the note via Python's built-in SMTP library."""
    smtp_server = os.environ.get('SMTP_SERVER')
    smtp_port = int(os.environ.get('SMTP_PORT', 587))
    sender_email = os.environ.get('SENDER_EMAIL')
    sender_password = os.environ.get('SENDER_PASSWORD')

    if not all([smtp_server, sender_email, sender_password]):
        return "Email Failed: SMTP credentials (Server, Port, Sender Email/Password) not set up."
        
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
        return f"Email SMTP Failed: {e}. Check your SMTP credentials and App Password setup (especially for Gmail)."

# --- 3. STREAMLIT APPLICATION LAYOUT ---

initialize_session_state()

st.title("Swasthiq AI Scribe MVP 🩺")
st.markdown("---")

# --------------------------
# --- STEP 1: USER SETUP & UPLOAD ---
# --------------------------

st.header("Step 1: Setup & Upload Audio")
st.markdown(
    "To begin, upload a pre-recorded audio file of the doctor-patient conversation. "
    "We simulate the Start/End flow by using a file upload, as this is more reliable for a quick MVP. "
    "*(Supports Hindi/English code-mixed speech)*"
)

# Input section
with st.container(border=True):
    col1, col2 = st.columns(2)
    with col1:
        st.session_state.doctor_name = st.text_input("Doctor's Name:", value="Dr. A. Sharma")
        
        st.session_state.delivery_target = st.radio(
            "Select Delivery Method:",
            ("WhatsApp", "Email"),
            horizontal=True
        )

    with col2:
        if st.session_state.delivery_target == "WhatsApp":
            # WhatsApp input must be in E.164 format for Twilio: +91XXXXXXXXXX
            st.session_state.contact_input = st.text_input(
                "WhatsApp Number (e.g., +91XXXXXXXXXX):", 
                value="+919876543210"
            )
        else:
            st.session_state.contact_input = st.text_input(
                "Email Address:", 
                value="doctor.test@clinic.com"
            )
        
        uploaded_file = st.file_uploader(
            "Upload Audio File (WAV/MP3/M4A):",
            type=['wav', 'mp3', 'm4a']
        )

# --- Simulation Buttons (Start/End) ---
st.subheader("Simulated Recording Controls")
col_buttons = st.columns(5)

if col_buttons[0].button("▶️ Start Recording (Simulated)", use_container_width=True):
    st.session_state.current_stage = 1
    st.info("Recording simulated. Please ensure your uploaded file covers the entire session.")

if st.session_state.current_stage == 1:
    if col_buttons[2].button("⏸️ Pause (Simulated)", use_container_width=True):
        st.info("Recording paused. Continue by clicking 'End Session' once your file is ready.")

if st.session_state.current_stage >= 1:
    if col_buttons[4].button("⏹️ End Session & Transcribe", use_container_width=True, type="primary"):
        st.session_state.current_stage = 2


# --------------------------
# --- STEP 2: PROCESSING LOGIC ---
# --------------------------

if st.session_state.current_stage == 2:
    if uploaded_file is None:
        st.error("Please upload the audio file first.")
        st.session_state.current_stage = 0
        st.stop()
        
    if not st.session_state.doctor_name or not st.session_state.contact_input:
        st.error("Please fill in the contact information before transcribing.")
        st.session_state.current_stage = 0
        st.stop()

    # Load model and process
    whisper_model = load_whisper_model()
    
    with st.spinner("Processing audio and generating note..."):
        
        # Save uploaded file to temp location
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{uploaded_file.name.split('.')[-1]}") as tmp_file:
            tmp_file.write(uploaded_file.getvalue())
            tmp_file_path = tmp_file.name
            
        # A. Run Transcription
        st.info("Step A: Transcribing Audio (Hindi/English code-mix enabled)...")
        raw_transcript = transcribe_audio_whisper(tmp_file_path, whisper_model)
        
        if "Error" in raw_transcript:
            st.error(raw_transcript)
            os.unlink(tmp_file_path) 
            st.session_state.current_stage = 0
            st.stop()
            
        st.session_state.raw_transcript = raw_transcript
        
        # B. Generate SOAP Note
        st.info("Step B: Generating Structured SOAP Note (via OpenAI API)...")
        st.session_state.soap_note = generate_soap_note_openai(raw_transcript)
        
        # Clean up temp file
        os.unlink(tmp_file_path)
        
        if "Error" in st.session_state.soap_note:
            st.error(st.session_state.soap_note)
            st.session_state.current_stage = 0
            st.stop()
            
        st.session_state.current_stage = 4
        st.success("Scribing Complete! Review and send the final note below.")
        st.rerun() # Rerun to display Step 3 properly


# --------------------------
# --- STEP 3: REVIEW & SEND ---
# --------------------------

if st.session_state.current_stage == 4:
    st.markdown("---")
    st.header("Step 2: Review, Edit & Send Final Note")

    st.markdown(f"**Generated Note for:** {st.session_state.doctor_name} | **Delivery Target:** {st.session_state.contact_input}")
    
    # Display the raw transcript for comparison
    with st.expander("View Raw Transcript (for debugging and review)"):
        st.caption("Raw output from the audio. Please check for transcription errors.")
        st.text(st.session_state.raw_transcript)
        
    # Editable Text Area for the Doctor
    final_note_content = st.text_area(
        "📝 Edit Final SOAP Note Here:",
        value=st.session_state.soap_note,
        height=500
    )

    if st.button(f"✅ FINALIZE & SEND VIA {st.session_state.delivery_target}", use_container_width=True, type="primary"):
        
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
                try:
                    validate_email(st.session_state.contact_input, check_deliverability=False)
                    send_status = send_email_note(full_message_content, st.session_state.contact_input)
                except EmailNotValidError:
                    send_status = "Email Failed: Invalid email format."
            
            if "Success!" in send_status:
                st.balloons()
                st.success(send_status)
                st.session_state.current_stage = 0 # Reset for next session
                st.button("Start New Scribe Session")
            else:
                st.error(send_status)
                st.warning("Please check your environment variables and network connection.")

# --- FOOTER / RESET ---
st.markdown("---")
if st.button("Reset Application"):
    st.session_state.clear()
    st.experimental_rerun()
