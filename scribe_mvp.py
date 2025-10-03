# scribe_mvp.py - Swasthiq AI Scribe MVP (Sarvam STT + Factual GPT Summarization)
# Last Updated: October 2025

import streamlit as st
import tempfile
import os
import smtplib
from email.mime.text import MIMEText
from twilio.rest import Client
from datetime import datetime
import requests
import time
from email_validator import validate_email, EmailNotValidError
from io import BytesIO # Used for handling audio input from st.audio_input

# --- API Clients & Initialization ---

# Initialize OpenAI client (relies on OPENAI_API_KEY env var)
try:
    from openai import OpenAI
    client = OpenAI()
except Exception:
    client = None # Will be checked later, stopping execution if API key is missing

SARVAM_BASE_URL = "https://api.sarvam.ai" # Base URL (Verify documentation)

# --- Streamlit Session State Management ---
def initialize_session_state():
    """Initializes or resets key variables in Streamlit's session state."""
    defaults = {
        'current_stage': 0,  # 0: Setup, 1: Audio Recorded, 2: Processing, 3: Complete
        'audio_data': None,
        'raw_transcript': "",
        'soap_note': "",
        'contact_input': "+919876543210",
        'delivery_target': "Email",
        'doctor_name': "Dr. A. Sharma"
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

# --- 1. CORE LOGIC FUNCTIONS ---

def transcribe_audio_sarvam_api(audio_bytes):
    """
    Transcribes the audio using the Sarvam Batch STT API (Upload -> Poll) 
    for high-accuracy Hindi/Code-Mix transcription.
    
    NOTE: This is a simplified implementation of the full Sarvam API flow (Upload -> Job -> Poll).
    The API keys and endpoint URLs MUST be correctly configured in your environment secrets.
    """
    sarvam_api_key = os.environ.get('SARVAM_AI_API_KEY')
    if not sarvam_api_key:
        return "Transcription API Error: SARVAM_AI_API_KEY not found in environment secrets."

    headers = {"Authorization": f"Bearer {sarvam_api_key}"}
    
    # 1. --- STUB: Upload Audio ---
    # In a real app, this sends audio_bytes to a cloud storage and gets a URI.
    # We simulate this success for the MVP flow check.
    
    # 2. --- STUB: Submit Job ---
    try:
        # Placeholder for actual API call, submitting a job and getting job_id
        # For a real integration, replace this with the actual requests.post call
        job_id = f"job-{int(time.time())}" 
        
        # --- PLACEHOLDER CODE START: Replace with actual Sarvam API call logic ---
        # The actual integration would involve uploading audio bytes (or the URI) 
        # and checking the submission response status.
        
        # --- PLACEHOLDER CODE END ---
        
        # Simulating transcription processing time for the MVP test experience
        time.sleep(3) 

        # --- Since we cannot execute the actual network calls here, we use a mock output ---
        # NOTE: This mock output is for testing the *summarization* logic without 
        # relying on a live key, but MUST be replaced with the actual Sarvam result.
        # This function should only return the final transcript string.
        
        # If testing with real Sarvam API, the loop below polls for COMPLETED status
        
        # If your Sarvam key is live, uncomment the PULLING loop from the previous reply
        # and remove this mock return.
        
        # --- MOCK TRANSCRIPT (for testing GPT logic only) ---
        return "Doctor: patient ko subah se fever hai aur body mein pain hai. Patient: yes doctor I took paracetamol 650 mg, but it did not help. Doctor: okay, let's do a quick examination and then I will give you a stronger tablet and advise for blood test. Follow up next week."

    except Exception as e:
        return f"Sarvam API Integration Error: Failed to complete job simulation/call. Details: {e}"


def generate_soap_note_openai(transcript):
    """
    Generates SOAP note using GPT-3.5 with strict guardrails and a 
    **Relevance Gate** to prevent fabrication on irrelevant input.
    """
    if client is None:
        return "AI Generation Error: OpenAI client failed to initialize. Check API key."

    # --- FINAL STRICT SYSTEM PROMPT ---
    system_prompt = (
        "You are a highly specialized and STRICT medical transcription specialist. "
        "Your SOLE task is to extract information from the provided raw transcript and structure it into a SOAP note. "
        "YOU MUST FOLLOW THESE RULES RIGOROUSLY:\n"
        "1. **RELEVANCE GATE:** First, determine if the transcript contains any clinical data (symptoms, medications, diagnosis, patient complaints, etc.).\n"
        "2. **SOURCE CONSTRAINT (Factual Integrity):** You must ONLY use facts explicitly mentioned in the transcript. DO NOT add any external knowledge, dummy text, or make assumptions (NO Hallucination).\n"
        "3. **MISSING DATA RULE:** If the transcript is judged NON-RELEVANT (e.g., only 'hello 123') or if any section is empty, you MUST fill that section with the phrase: 'None found in conversation.'\n"
        "4. **OUTPUT FORMAT:** Maintain the exact S:, O:, A:, P: structure provided below."
    )
    
    # --- Check for extremely short/irrelevant inputs (The Code Fix for your "Hello 123" test) ---
    if len(transcript.split()) < 7:
        # Check if any part is highly clinical before bypassing. If less than 7 words, assume irrelevant.
        if "fever" not in transcript.lower() and "pain" not in transcript.lower() and "mg" not in transcript.lower():
            st.warning("Transcript is too short and non-clinical. Returning empty note.")
            return (
                "S: None found in conversation.\n"
                "O: None found in conversation.\n"
                "A: None found in conversation.\n"
                "P: None found in conversation."
            )

    user_prompt = (
        "---RAW CONSULTATION TRANSCRIPT---\n"
        f"{transcript}\n"
        "---END TRANSCRIPT---\n\n"
        "**Generate the note now, following all rules strictly:**\n"
        "S: [Subjective notes]\n"
        "O: [Objective findings]\n"
        "A: [Assessment/Diagnosis]\n"
        "P: [Plan/Treatment/Follow-up]"
    )
    
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.0,
            max_tokens=700
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"AI Generation Error: {e}"

# --- Delivery Functions (Remain the same) ---
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
        client.messages.create(from_=from_whatsapp_number, body=message_body, to=f'whatsapp:{recipient_number}')
        return f"Success! Note sent via WhatsApp to {recipient_number}."
    except Exception as e:
        return f"WhatsApp API Failed: {e}. Check number format and Sandbox linkage."

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

if __name__ == '__main__':
    initialize_session_state()

    st.set_page_config(page_title="Swasthiq AI Scribe MVP", layout="wide")
    st.title("Swasthiq AI Scribe MVP 🩺")
    st.markdown("Automate your clinical documentation via voice-to-note using **Sarvam AI** transcription.")
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
                value=st.session_state.contact_input,
                key='contact_input_wa'
            )
        else:
            st.session_state.contact_input = st.text_input(
                "Email Address:", 
                value=st.session_state.contact_input,
                key='contact_input_email'
            )

    st.subheader("Live Audio Recorder (Start/End Recording)")
    st.info("🎤 Click the microphone once to **START** recording. Click it again to **STOP** (End Session).")

    # st.audio_input returns audio data when the user stops recording
    audio_file_like_object = st.audio_input(
        "Click the mic to record your conversation:",
        sample_rate=16000, 
        key='audio_recorder'
    )
    
    # Check if a new recording is available
    if audio_file_like_object is not None and st.session_state.current_stage == 0:
        
        # Store the raw audio bytes
        st.session_state.audio_data = audio_file_like_object.getvalue()
        
        # --- Triggered when recording stops ---
        st.session_state.current_stage = 2
        
        # Check for empty recording
        if len(st.session_state.audio_data) < 1000: # Check size to prevent processing noise
            st.error("Recording too short or silent. Please ensure mic is active and try again.")
            st.session_state.current_stage = 0
            st.stop()
            
        with st.spinner("Processing audio and generating note... This may take up to 5 minutes due to batch API polling."):
            
            # A. Run Transcription using Sarvam API
            st.info("Step A: Transcribing Audio (Sarvam AI for Hindi/Code-Mix)...")
            raw_transcript = transcribe_audio_sarvam_api(st.session_state.audio_data)
            
            if "Error" in raw_transcript:
                st.error(raw_transcript)
                st.session_state.current_stage = 0
                st.stop()
                
            st.session_state.raw_transcript = raw_transcript
            
            # B. Generate SOAP Note using Factual GPT Prompt
            st.info("Step B: Generating Structured SOAP Note (GPT-3.5 with Factual Guardrails)...")
            st.session_state.soap_note = generate_soap_note_openai(raw_transcript)
            
            if "Error" in st.session_state.soap_note:
                st.error(st.session_state.soap_note)
                st.session_state.current_stage = 0
                st.stop()
                
            st.session_state.current_stage = 3
            st.success("Scribing Complete! Scroll down to review and send the final note.")
            st.rerun() 


    # --------------------------
    # --- STEP 3: REVIEW & SEND ---
    # --------------------------

    if st.session_state.current_stage == 3:
        st.markdown("---")
        st.header("Step 2: Review, Edit & Send Final Note")

        st.caption(f"Note generated for: **{st.session_state.doctor_name}** | Sending via: **{st.session_state.delivery_target}** to **{st.session_state.contact_input}**")
        
        # Display the raw transcript for comparison
        with st.expander("View Raw Transcript (Source of truth)"):
            st.caption("If this transcript is blank or inaccurate, the issue is with the Sarvam API key or poor audio quality.")
            st.text(st.session_state.raw_transcript)
            
        # Editable Text Area for the Doctor
        final_note_content = st.text_area(
            "📝 Edit Final SOAP Note Here (Check for 'None found' entries!):",
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
                    st.balloons()
                    st.success(send_status)
                    st.session_state.current_stage = 0 
                    st.session_state.audio_data = None
                    st.button("Start New Scribe Session", on_click=initialize_session_state)
                else:
                    st.error(send_status)

    # --- FOOTER / RESET ---
    st.markdown("---")
    if st.button("Reset Application"):
        st.session_state.clear()
        st.experimental_rerun()
