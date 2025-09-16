# app.py

import queue
import streamlit as st
import pydub
import time
import json
from streamlit_webrtc import webrtc_streamer, WebRtcMode
from io import BytesIO

# Local imports
from services.transcription_service import TranscriptionService
from services.gemini_service import GeminiService
from utils.ui_components import apply_custom_styling, get_default_schema
from config.settings import (
    APP_TITLE,
    APP_ICON,
    APP_LAYOUT,
    GCS_BUCKET_NAME,
    get_gcp_project_id,
    GCP_LOCATION,
    validate_environment,
)

# --- HELPER FUNCTIONS ---
def format_time(seconds: float) -> str:
    """Format seconds into MM:SS format."""
    seconds = max(0, int(seconds))
    m, s = divmod(seconds, 60)
    return f"{m:02d}:{s:02d}"


def initialize_services():
    """Initialize real API services and store them in session state."""
    if "services_initialized" not in st.session_state:
        # Validate environment variables first
        if not validate_environment():
            st.error(
                "❌ Environment validation failed. Please check the console for missing variables."
            )
            st.stop()

        # Initialize Transcription Service
        project_id = get_gcp_project_id()
        if not project_id:
            st.error(
                "❌ GCP Project ID not found. Please set GCP_PROJECT_ID environment variable or check service account credentials."
            )
            st.session_state.transcription_service = None
        else:
            st.session_state.transcription_service = TranscriptionService(
                gcs_bucket_name=GCS_BUCKET_NAME,
                gcp_project_id=project_id,
                gcp_location=GCP_LOCATION,
            )

        # Initialize Gemini Service
        st.session_state.gemini_service = GeminiService()
        st.session_state.services_initialized = True


def initialize_session_state():
    """Initialize or reset all session state variables for the workflow."""
    if "current_step" not in st.session_state:
        st.session_state.current_step = "workflow_selection"
        st.session_state.workflow_type = None
        st.session_state.audio_buffer = None
        st.session_state.transcript = None
        st.session_state.edited_transcript = None
        st.session_state.gemini_result = None

        # Live recording state
        st.session_state.is_recording = False
        st.session_state.is_paused = False
        st.session_state.start_time = 0
        st.session_state.total_paused_duration = 0
        st.session_state.pause_start_time = 0


# --- CORE PROCESSING LOGIC ---


def process_audio_upload(uploaded_file):
    """Handles the processing of an uploaded audio file."""
    with st.spinner("Processing uploaded audio file..."):
        try:
            audio_segment = pydub.AudioSegment.from_file(uploaded_file)
            st.session_state.audio_buffer = audio_segment
            st.toast("✅ Audio processed successfully!", icon="🎵")
            st.session_state.current_step = "transcribe"
            st.rerun()
        except Exception as e:
            st.error(f"❌ Failed to process audio file: {e}")


def run_transcription():
    """Runs the transcription process on the audio buffer."""
    if st.session_state.audio_buffer:
        with st.spinner("🤖 Transcribing audio... This may take a few minutes."):
            try:
                audio_bytes = st.session_state.audio_buffer.export(format="wav").read()
                audio_file_like = BytesIO(audio_bytes)
                audio_file_like.name = "processed_audio.wav"

                transcript_text = (
                    st.session_state.transcription_service.transcribe_full_file(
                        audio_file_like, language_code="hi-IN"
                    )
                )
                if transcript_text:
                    st.session_state.transcript = transcript_text
                    st.session_state.edited_transcript = transcript_text
                    st.session_state.current_step = "analyze"
                    st.success("✅ Transcription complete!")
                    st.rerun()
                else:
                    st.warning("Transcription returned an empty result.")
            except Exception as e:
                st.error(f"❌ Transcription failed: {e}")


def run_analysis():
    """Runs the Gemini analysis on the transcript."""
    transcript = st.session_state.get("edited_transcript")
    if transcript:
        # with st.spinner("🚀 Analyzing transcript with Gemini AI..."):
            try:
                schema = get_default_schema()
                schema_json = json.dumps(schema, indent=2)

                result = st.session_state.gemini_service.generate_json_payload(
                    schema_json, transcript
                )
                if result:
                    st.session_state.gemini_result = result
                    st.session_state.current_step = "export"
                    st.success("✅ AI analysis complete!")
                    st.rerun()
                else:
                    st.warning("AI analysis returned an empty result.")
            except Exception as e:
                st.error(f"❌ Payload generation failed: {e}")


# --- UI RENDERING FUNCTIONS (VIEWS) ---


def render_sidebar():
    """Renders the sidebar for navigation and status."""
    with st.sidebar:
        st.markdown("---")
        steps = {
            "workflow_selection": "1. Audio Source",
            "input": "2. Record / Upload",
            "transcribe": "3. Transcribe",
            "analyze": "4. Analyze",
            "export": "5. Export",
        }
        current_step_index = list(steps.keys()).index(st.session_state.current_step)
        for i, (step_id, step_name) in enumerate(steps.items()):
            if i < current_step_index:
                st.markdown(f"✔️ ~~{step_name}~~")
            elif i == current_step_index:
                st.markdown(f"➡️ **{step_name}**")
            else:
                st.markdown(f"⏳ _{step_name}_")

        st.markdown("---")
        if st.button("🔄 Start Over", use_container_width=True, type="secondary"):
            for key in list(st.session_state.keys()):
                if key not in [
                    "services_initialized",
                    "transcription_service",
                    "gemini_service",
                ]:
                    del st.session_state[key]
            st.rerun()


def render_workflow_selection_view():
    """UI for selecting between live recording and file upload."""
    st.header("Step 1: Choose Your Audio Source")
    st.write("Select how you want to provide the farmer interview audio.")
    col1, col2 = st.columns(2)
    with col1:
        if st.button(
            "🎙️ **Start Recording**", use_container_width=True, key="start_rec"
        ):
            st.session_state.workflow_type = "live"
            st.session_state.current_step = "input"
            st.rerun()
    with col2:
        if st.button(
            "📁 **Upload Audio File**", use_container_width=True, key="start_upload"
        ):
            st.session_state.workflow_type = "upload"
            st.session_state.current_step = "input"
            st.rerun()


def render_input_view():
    """UI for the audio input step (either recording or uploading)."""
    st.header("Step 2: Provide Audio Input")
    workflow = st.session_state.get("workflow_type")
    if workflow == "live":
        render_live_recorder()
    elif workflow == "upload":
        render_file_uploader()
    else:
        st.warning("Please select a workflow first.")
        if st.button("⬅️ Go Back"):
            st.session_state.current_step = "workflow_selection"
            st.rerun()


def render_live_recorder():
    """UI for live audio recording with pause/resume."""
    st.subheader("Live Audio Recorder")
    webrtc_ctx = webrtc_streamer(
        key="live-recorder",
        mode=WebRtcMode.SENDONLY,
        audio_receiver_size=1024,
        media_stream_constraints={"audio": True, "video": False},
    )

    if webrtc_ctx.state.playing and not st.session_state.is_recording:
        st.session_state.is_recording = True
        st.session_state.start_time = time.time()
        st.rerun()
    elif not webrtc_ctx.state.playing and st.session_state.is_recording:
        st.session_state.is_recording = False
        st.session_state.is_paused = False
        st.rerun()

    status_indicator = st.empty()
    timer_placeholder = st.empty()

    if st.session_state.is_recording:
        col1, col2 = st.columns([1, 1])
        with col1:
            pause_resume_text = "▶️ Resume" if st.session_state.is_paused else "⏸️ Pause"
            if st.button(pause_resume_text, use_container_width=True):
                st.session_state.is_paused = not st.session_state.is_paused
                if st.session_state.is_paused:
                    st.session_state.pause_start_time = time.time()
                else:
                    st.session_state.total_paused_duration += (
                        time.time() - st.session_state.pause_start_time
                    )
                st.rerun()

        # This while loop is for continuous UI update, not for blocking processing
        while st.session_state.is_recording:
            if st.session_state.is_paused:
                status_indicator.warning("⏸️ RECORDING PAUSED")
            else:
                status_indicator.success("🎤 Recording...")
                # Accumulate audio frames only when not paused
                if webrtc_ctx.audio_receiver:
                    try:
                        audio_frames = webrtc_ctx.audio_receiver.get_frames(timeout=0.1)
                        sound_chunk = pydub.AudioSegment.empty()
                        for frame in audio_frames:
                            sound = pydub.AudioSegment(
                                frame.to_ndarray().tobytes(),
                                sample_width=frame.format.bytes,
                                frame_rate=frame.sample_rate,
                                channels=len(frame.layout.channels),
                            )
                            sound_chunk += sound
                        if len(sound_chunk) > 0:
                            st.session_state.audio_buffer = (
                                st.session_state.audio_buffer
                                or pydub.AudioSegment.empty()
                            ) + sound_chunk
                    except queue.Empty:
                        pass

            # Update timer
            now = time.time()
            elapsed_time = (
                now
                - st.session_state.start_time
                - st.session_state.total_paused_duration
            )
            if st.session_state.is_paused:
                elapsed_time -= now - st.session_state.pause_start_time
            timer_placeholder.info(f"⏱️ Duration: {format_time(elapsed_time)}")
            time.sleep(0.5)

    elif st.session_state.audio_buffer:
        status_indicator.info("✅ Recording finished.")
        st.audio(
            st.session_state.audio_buffer.export(format="wav").read(),
            format="audio/wav",
        )
        if st.button(
            "Continue to Transcription ➡️", type="primary", use_container_width=True
        ):
            st.session_state.current_step = "transcribe"
            st.rerun()


def render_file_uploader():
    """UI for uploading an audio file."""
    st.subheader("Upload Audio File")
    uploaded_file = st.file_uploader(
        "Choose audio file (WAV, MP3, M4A, FLAC)",
        type=["wav", "mp3", "m4a", "flac"],
        label_visibility="collapsed",
    )
    if uploaded_file:
        st.audio(uploaded_file, format=uploaded_file.type)
        if st.button(
            "Process and Continue ➡️", type="primary", use_container_width=True
        ):
            process_audio_upload(uploaded_file)


def render_transcription_view():
    """UI for initiating and reviewing transcription."""
    st.header("Step 3: AI Transcription")
    if not st.session_state.get("audio_buffer"):
        st.warning("No audio data found. Please go back to Step 2.")
        return
    st.info(
        "Your audio is ready for transcription. This may take a few minutes for long recordings."
    )
    st.audio(
        st.session_state.audio_buffer.export(format="wav").read(), format="audio/wav"
    )
    if st.button("🎙️ **Start Transcription**", type="primary", use_container_width=True):
        run_transcription()


def render_analysis_view():
    """UI for reviewing transcript and running analysis."""
    st.header("Step 4: AI Analysis")
    transcript = st.session_state.get("transcript")
    if not transcript:
        st.warning("No transcript found. Please complete Step 3 first.")
        return
    st.info(
        "Review the transcript below. Edit if necessary before running the AI analysis."
    )
    edited = st.text_area(
        "**Editable Transcript**",
        value=st.session_state.get("edited_transcript", transcript),
        height=250,
    )
    st.session_state.edited_transcript = edited
    if st.button(
        "🚀 **Generate Survey Data**", type="primary", use_container_width=True
    ):
        run_analysis()


def render_export_view():
    """UI for viewing and exporting final results."""
    st.header("🎉 Step 5: Complete!")
    st.balloons()
    st.success(
        "Your farmer interview has been fully processed. All data is ready for download."
    )

    payload = st.session_state.get("gemini_result")
    transcript = st.session_state.get("edited_transcript")
    audio_buffer = st.session_state.get("audio_buffer")

    if not all([payload, transcript, audio_buffer]):
        st.error("Missing data. Please ensure all previous steps are complete.")
        return

    with st.container(border=True):
        farmer_name = payload.get("farmerDetails", {}).get("farmerName", "N/A")
        summary = payload.get("interviewMetadata", {}).get(
            "summary", "No summary available."
        )
        st.markdown(f"#### 📋 Summary for: {farmer_name}")
        st.markdown(summary)

    tab1, tab2, tab3 = st.tabs(["📊 Survey Data (JSON)", "📄 Transcript", "🎵 Audio"])
    with tab1:
        st.json(payload)
        st.download_button(
            "📥 Download JSON",
            json.dumps(payload, indent=2, ensure_ascii=False),
            f"survey_{int(time.time())}.json",
            "application/json",
            use_container_width=True,
        )
    with tab2:
        st.text(transcript)
        st.download_button(
            "📄 Download Transcript (.txt)",
            transcript,
            f"transcript_{int(time.time())}.txt",
            "text/plain",
            use_container_width=True,
        )
    with tab3:
        audio_bytes = audio_buffer.export(format="wav").read()
        st.audio(audio_bytes, format="audio/wav")
        st.download_button(
            "🎵 Download Audio (.wav)",
            audio_bytes,
            f"interview_{int(time.time())}.wav",
            "audio/wav",
            use_container_width=True,
        )


def main():
    """Main application function."""
    st.set_page_config(page_title=APP_TITLE, page_icon=APP_ICON, layout=APP_LAYOUT)
    apply_custom_styling()

    initialize_session_state()
    initialize_services()

    # --- Persistent App Header ---
    st.markdown(
        f"<h1 style='text-align: center;'>{APP_ICON} {APP_TITLE}</h1>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<p style='text-align: center; color: #7f8c8d;'>Intelligent processing of farmer interview surveys from audio recordings</p>",
        unsafe_allow_html=True,
    )
    st.markdown("---")

    render_sidebar()

    step_views = {
        "workflow_selection": render_workflow_selection_view,
        "input": render_input_view,
        "transcribe": render_transcription_view,
        "analyze": render_analysis_view,
        "export": render_export_view,
    }
    current_view = step_views.get(st.session_state.current_step)
    if current_view:
        current_view()
    else:
        st.error("Invalid state. Please start over.")


if __name__ == "__main__":
    main()
