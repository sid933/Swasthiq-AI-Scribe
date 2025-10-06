# scribe_mvp.py - Swasthiq AI Scribe MVP (Final Production Version with Sarvam STT Logic)

import streamlit as st
import tempfile
import os
import smtplib
from email.mime.text import MIMEText
from twilio.rest import Client
from datetime import datetime
from sarvamai import SarvamAI
import requests
import time
from email_validator import validate_email, EmailNotValidError
from io import BytesIO 

# --- API Clients & Initialization ---
# Ensure all API keys are set as environment variables on your hosting platform!

try:
    from openai import OpenAI
    client = OpenAI()
except Exception:
    client = None # Will fail gracefully if key is missing

SARVAM_BASE_URL = "https://api.sarvam.ai"  # Base URL (Verify documentation)

# --- Streamlit Session State Management ---
def initialize_session_state():
    """Initializes or resets key variables in Streamlit's session state."""
    # Resetting the whole session is the safest approach for an MVP
    if 'current_stage' not in st.session_state:
        st.session_state.clear()
        # Set persistent defaults
        st.session_state.current_stage = 0
        st.session_state.doctor_name = "Dr. A. Sharma"
        st.session_state.delivery_target = "Email"
        st.session_state.contact_input = "dr.a.sharma@clinic.com"
        st.session_state.raw_transcript = ""
        st.session_state.soap_note = ""
        st.session_state.audio_bytes = None
        st.session_state.input_mode = "Live Recording" 

# --- 1. CORE LOGIC FUNCTIONS ---

def transcribe_audio_sarvam_api(audio_bytes):
    """
    Transcribes the audio using the official Sarvam Batch STT SDK (Synchronous Method).
    This function handles saving the in-memory audio to a temporary file for the SDK.
    """
    sarvam_api_key = os.environ.get('SARVAM_AI_API_KEY')
    if not sarvam_api_key:
        return "Transcription API Error: SARVAM_AI_API_KEY not found in environment secrets."
    
    # 1. Save in-memory audio bytes to a temporary file
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_file:
            tmp_file.write(audio_bytes)
            audio_path = tmp_file.name
    except Exception as e:
        return f"File System Error: Could not save temporary audio file. Details: {e}"

    # 2. Initialize and Execute the Sarvam Job
    output_dir = os.path.join(tempfile.gettempdir(), f"sarvam_output_{int(time.time())}")
    
    try:
        # Initialize Sarvam Client
        client = SarvamAI(api_subscription_key=sarvam_api_key)

        # Create the Transcription Job (Includes Diarization for Doctor/Patient separation)
        job = client.speech_to_text_job.create_job(
            language_code="en-IN",
            model="saarika:v2.5",
            with_diarization=True,
            num_speakers=2 # Assuming 2 speakers: Doctor and Patient
        )

        # Upload the temporary audio file
        job.upload_files(file_paths=[audio_path])

        # Start the job and wait for completion (Synchronous)
        job.start()
        final_status = job.wait_until_complete()

        if job.is_failed():
            return f"Sarvam Job Failed: Status was FAILED. Check Sarvam logs for job {job.job_id}."

        # 3. Download and Extract the Transcript
        # Download output to a temporary directory
        job.download_outputs(output_dir=output_dir)

        # We need to find the transcription file (assuming one file per job)
        transcript_file_path = None
        for filename in os.listdir(output_dir):
            if filename.endswith('.txt') or filename.endswith('.json'):
                transcript_file_path = os.path.join(output_dir, filename)
                break
        
        if transcript_file_path:
            with open(transcript_file_path, 'r', encoding='utf-8') as f:
                # Assuming the output is plain text for simplicity
                transcript = f.read() 
                return transcript
        else:
            return "Sarvam Output Error: Transcript file not found in downloaded output."

    except Exception as e:
        return f"Sarvam SDK Execution Error: An unexpected error occurred during job processing. Details: {e}"

    finally:
        # 4. Cleanup temporary files and directories
        if os.path.exists(audio_path):
            os.unlink(audio_path)
        if os.path.exists(output_dir):
            import shutil
            shutil.rmtree(output_dir) 

    # 4. --- POLLING STAGE: Check job status until complete (Max 5 minutes) ---
    max_checks = 30
    
    for _ in range(max_checks):
        time.sleep(10) # Wait 10 seconds between checks
        try:
            # Hitting the corrected status endpoint
            status_response = requests.get(f"{SARVAM_BASE_URL}/status/{job_id}", headers=headers)
            status_response.raise_for_status()
            status_data = status_response.json()
            status = status_data.get('status')
            
            if status == "COMPLETED":
                return status_data['result']['transcript']
            
            elif status in ["FAILED", "REJECTED"]:
                return f"Sarvam Transcription Failed. Status: {status}. Message: {status_data.get('message', 'Check audio quality.')}"
            
        except requests.exceptions.RequestException as e:
            return f"Sarvam Status Check Error: Failed to get job status. Details: {e}"

    return "Sarvam Transcription Timeout: Job took too long (max 5 minutes)."


def generate_soap_note_openai(transcript):
    """
    Generates SOAP note using GPT-3.5 with strict guardrails and a 
    **Relevance Gate** to prevent fabrication on irrelevant input.
    """
    if client is None:
        return "AI Generation Error: OpenAI client failed to initialize. Check API key."

    # --- FINAL RELEVANCE GATE (The explicit fix for non-clinical input) ---
    normalized_transcript = transcript.lower().strip()
    word_count = len(normalized_transcript.split())
    
    # Check for trivial content (e.g., just greetings, noise, or blank results)
    is_trivial = (word_count < 10 and 
                  not any(marker in normalized_transcript for marker in ['pain', 'fever', 'mg', 'diagnos', 'prescribe', 'consult', 'patient', 'doctor', 'treatment']))
    
    if is_trivial or not normalized_transcript:
        # MANDATED SAFE OUTPUT: Skips LLM call and returns hardcoded empty note.
        st.warning("Transcript judged non-clinical or trivial. Returning safe output.")
        return (
            "S: None (Trivial/Non-clinical audio. No patient conversation detected).\n"
            "O: None found in conversation.\n"
            "A: None found in conversation.\n"
            "P: None found in conversation."
        )

    # --- STRICT SYSTEM PROMPT (Anti-Hallucination) ---
    system_prompt = (
        "You are a highly specialized and STRICT medical transcription specialist. "
        "Your SOLE task is to extract information from the provided raw transcript and structure it into a SOAP note. "
        "YOU MUST FOLLOW THESE RULES RIGOROUSLY:\n"
        "1. **SOURCE CONSTRAINT (Factual Integrity):** You must ONLY use facts explicitly mentioned in the transcript. DO NOT add any external knowledge, dummy text, or make assumptions.\n"
        "2. **MISSING DATA RULE:** If you cannot find any information relevant to a specific section (O, A, or P) in the transcript, you MUST fill that section with the phrase: 'None found in conversation.'\n"
        "3. **OUTPUT FORMAT:** Maintain the exact S:, O:, A:, P: structure provided below."
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


# --- 3. STREAMLIT APPLICATION LAYOUT & FLOW ---

if __name__ == '__main__':
    initialize_session_state()

    st.set_page_config(page_title="Swasthiq AI Scribe MVP", layout="wide")
    st.title("Swasthiq AI Scribe MVP 🩺")
    st.markdown("Automate clinical notes using **Sarvam AI** transcription.")
    st.markdown("---")

    # --------------------------
    # --- STEP 1: USER SETUP & INPUT SOURCE ---
    # --------------------------

    st.header("Step 1: Input Source & Doctor Details")

    col_input, col_contact = st.columns([1, 1])

    with col_input:
        st.session_state.doctor_name = st.text_input(
            "Doctor's Name:", 
            value=st.session_state.doctor_name,
            key='name_input'
        )
        st.session_state.input_mode = st.radio(
            "Select Audio Source:", 
            ("Live Recording", "File Upload"), 
            horizontal=True, 
            key='input_mode_radio'
        )

    with col_contact:
        st.session_state.delivery_target = st.radio(
            "Select Delivery Method:",
            ("Email", "WhatsApp"),
            horizontal=True,
            key='delivery_radio'
        )
        if st.session_state.delivery_target == "WhatsApp":
            st.session_state.contact_input = st.text_input(
                "WhatsApp Number (e.g., +91XXXXXXXXXX):", 
                value=st.session_state.contact_input if st.session_state.delivery_target == 'WhatsApp' else "+919876543210",
                key='contact_input_wa'
            )
        else:
            st.session_state.contact_input = st.text_input(
                "Email Address:", 
                value=st.session_state.contact_input if st.session_state.delivery_target == 'Email' else "dr.a.sharma@clinic.com",
                key='contact_input_email'
            )

    # --- AUDIO SOURCE WIDGETS ---
    audio_source_data = None
    
    if st.session_state.input_mode == "Live Recording":
        st.subheader("🎤 Live Recording")
        audio_source_data = st.audio_input(
            "Click the mic to record the conversation:",
            sample_rate=16000, 
            key='live_audio_recorder'
        )
    
    else: # File Upload
        st.subheader("📁 Upload File")
        audio_source_data = st.file_uploader(
            "Upload Pre-recorded Audio File:",
            type=['wav', 'mp3', 'm4a'],
            key='file_uploader'
        )
        
    # Process when audio data is available
    if audio_source_data is not None and st.session_state.current_stage == 0:
        st.session_state.audio_bytes = audio_source_data.getvalue()
        
        process_button_label = "🚀 PROCESS & GENERATE NOTE"
        if st.button(process_button_label, use_container_width=True, type="primary"):
            st.session_state.current_stage = 2
            st.rerun() 

    # --------------------------
    # --- STEP 2: PROCESSING EXECUTION ---
    # --------------------------

    if st.session_state.current_stage == 2:
        if st.session_state.audio_bytes is None:
            st.error("No audio data found. Please record live or upload a file.")
            st.session_state.current_stage = 0
            st.stop()
            
        with st.spinner("Processing audio and generating note... This may take time due to API polling."):
            
            # A. Run Transcription using Sarvam API
            st.info("Step A: Transcribing Audio (Sarvam AI for Hindi/Code-Mix)...")
            raw_transcript = transcribe_audio_sarvam_api(st.session_state.audio_bytes)
            
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
            st.success("Scribing Complete! Scroll down to review and send.")
            st.balloons()
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
            st.caption("This transcript is the basis for the SOAP note.")
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
                
                if st.session_state.delivery_target == "WhatsApp":
                    send_status = send_whatsapp_note(full_message_content, st.session_state.contact_input)
                else: # Email
                    send_status = send_email_note(full_message_content, st.session_state.contact_input)
                
                if "Success!" in send_status:
                    st.success(send_status)
                    st.session_state.current_stage = 0 
                    st.session_state.audio_bytes = None
                    st.button("Start New Scribe Session")
                else:
                    st.error(send_status)

    # --- FOOTER / RESET ---
    st.markdown("---")
    if st.button("Reset Application"):
        st.session_state.clear()
        st.experimental_rerun()
