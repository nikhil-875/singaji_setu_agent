import queue
import streamlit as st
import pydub
import time
import json
from streamlit_webrtc import webrtc_streamer, WebRtcMode

# Import services
from services.transcription_service import TranscriptionService
from services.gemini_service import GeminiService

# Import utilities
from utils.ui_components import apply_custom_styling, get_default_schema

# Import configuration
from config.settings import (
    APP_TITLE,
    APP_ICON,
    APP_LAYOUT,
    GCS_BUCKET_NAME,
    get_gcp_project_id,
    GCP_LOCATION,
    validate_environment,
)


def format_time(seconds: float) -> str:
    """Format seconds into MM:SS format."""
    seconds = max(0, int(seconds))
    m, s = divmod(seconds, 60)
    return f"{m:02d}:{s:02d}"


def initialize_session_state():
    """Initialize all session state variables."""
    # Validate environment variables first
    if not validate_environment():
        st.error(
            "❌ Environment validation failed. Please check the console for missing variables."
        )
        st.stop()

    if "transcription_service" not in st.session_state:
        # Get GCP project ID from environment or service account
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

    if "gemini_service" not in st.session_state:
        st.session_state.gemini_service = GeminiService()

    # Core session state
    if "transcript" not in st.session_state:
        st.session_state.transcript = None
    if "gemini_result" not in st.session_state:
        st.session_state.gemini_result = None
    if "performance_metrics" not in st.session_state:
        st.session_state.performance_metrics = None
    if "edited_transcript" not in st.session_state:
        st.session_state.edited_transcript = None
    if "transcription_in_progress" not in st.session_state:
        st.session_state.transcription_in_progress = False

    # Live recording session state
    if "audio_buffer" not in st.session_state:
        st.session_state.audio_buffer = pydub.AudioSegment.empty()
    if "paused" not in st.session_state:
        st.session_state.paused = False
    if "start_time" not in st.session_state:
        st.session_state.start_time = None
    if "paused_at" not in st.session_state:
        st.session_state.paused_at = None
    if "total_paused" not in st.session_state:
        st.session_state.total_paused = 0.0


def process_transcription(
    audio_buffer: pydub.AudioSegment, language_code: str = "hi-IN"
):
    """Process transcription for recorded audio."""
    if not st.session_state.get("transcription_service"):
        st.error(
            "❌ Transcription service not available. Please check your GCP credentials."
        )
        return None

    try:
        st.session_state.transcription_in_progress = True

        # Export audio to bytes for processing
        audio_bytes = audio_buffer.export(format="wav").read()

        # Create a file-like object for transcription
        from io import BytesIO

        audio_file_like = BytesIO(audio_bytes)
        audio_file_like.name = "recorded_audio.wav"

        # Process transcription
        transcript = st.session_state.transcription_service.transcribe_full_file(
            audio_file_like, language_code=language_code
        )

        return transcript

    except Exception as e:
        st.error(f"❌ Transcription failed: {e}")
        return None
    finally:
        st.session_state.transcription_in_progress = False


def generate_survey_payload(transcript: str):
    """Generate structured survey payload from transcript using Gemini."""
    if not st.session_state.get("gemini_service"):
        st.error("❌ Gemini service not available.")
        return None

    try:
        schema = get_default_schema()
        schema_json = json.dumps(schema, indent=2)

        gemini_result = st.session_state.gemini_service.generate_json_payload(
            schema_json, transcript
        )

        return gemini_result

    except Exception as e:
        st.error(f"❌ Payload generation failed: {e}")
        return None


def render_live_record_workflow():
    """Render the live recording workflow with clean UI."""
    with st.container():
        # Header card
        st.markdown("""
        <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    padding: 20px; border-radius: 10px; margin-bottom: 20px;">
            <h3 style="color: white; margin: 0; display: flex; align-items: center;">
                🎙️ Live Recording
            </h3>
            <p style="color: #e8eaf6; margin: 5px 0 0 0; font-size: 14px;">
                Record farmer interviews directly in your browser
            </p>
        </div>
        """, unsafe_allow_html=True)

        # Initialize WebRTC
        RTC_CONFIGURATION = {"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]}

        webrtc_ctx = webrtc_streamer(
            key="live-recorder",
            mode=WebRtcMode.SENDONLY,
            audio_receiver_size=1024,
            rtc_configuration=RTC_CONFIGURATION,
            media_stream_constraints={
                "audio": {
                    "sampleRate": 44100,
                    "channelCount": 1,
                    "echoCancellation": True,
                    "noiseSuppression": True,
                },
                "video": False,
            },
            audio_html_attrs={"muted": True},
        )

        # Recording controls
        if webrtc_ctx.state.playing:
            st.markdown("---")

            # Status and timer in a nice card
            status_col, timer_col, control_col = st.columns([2, 1, 1])

            with status_col:
                if st.session_state.paused:
                    st.markdown("""
                    <div style="background: #fff3cd; border: 1px solid #ffeaa7; border-radius: 8px;
                                padding: 15px; text-align: center;">
                        <h4 style="color: #856404; margin: 0;">⏸️ RECORDING PAUSED</h4>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown("""
                    <div style="background: #d4edda; border: 1px solid #c3e6cb; border-radius: 8px;
                                padding: 15px; text-align: center;">
                        <h4 style="color: #155724; margin: 0;">🎤 RECORDING ACTIVE</h4>
                    </div>
                    """, unsafe_allow_html=True)

            with timer_col:
                elapsed_time = get_elapsed_time()
                st.metric("⏱️ Duration", format_time(elapsed_time))

            with control_col:
                button_text = "⏸️ Pause" if not st.session_state.paused else "▶️ Resume"
                button_type = "secondary" if not st.session_state.paused else "primary"
                if st.button(button_text, type=button_type, use_container_width=True):
                    toggle_recording_pause()

        # Start time bookkeeping
        if webrtc_ctx.state.playing and st.session_state.start_time is None:
            st.session_state.start_time = time.time()

        # Recording loop
        while True:
            if webrtc_ctx.audio_receiver:
                try:
                    audio_frames = webrtc_ctx.audio_receiver.get_frames(timeout=1)
                except queue.Empty:
                    continue

                # Only buffer when not paused
                if not st.session_state.paused:
                    sound_chunk = pydub.AudioSegment.empty()
                    for audio_frame in audio_frames:
                        sound = pydub.AudioSegment(
                            data=audio_frame.to_ndarray().tobytes(),
                            sample_width=audio_frame.format.bytes,
                            frame_rate=audio_frame.sample_rate,
                            channels=len(audio_frame.layout.channels),
                        )
                        sound_chunk += sound
                    if len(sound_chunk) > 0:
                        st.session_state.audio_buffer += sound_chunk
            else:
                break

        # Show recorded audio if available
        audio_buffer = st.session_state.audio_buffer
        if len(audio_buffer) > 0:
            # Success card
            st.markdown("""
            <div style="background: #d4edda; border: 1px solid #c3e6cb; border-radius: 8px;
                        padding: 15px; margin: 20px 0;">
                <h4 style="color: #155724; margin: 0;">✅ Recording Complete!</h4>
                <p style="color: #155724; margin: 5px 0 0 0;">
                    Your audio is ready for transcription. Continue to the next step below.
                </p>
            </div>
            """, unsafe_allow_html=True)

            # Audio preview in a collapsible section
            with st.expander("🎵 View Audio Details", expanded=False):
                col1, col2 = st.columns(2)

                with col1:
                    audio_bytes = audio_buffer.export(format="wav").read()
                    st.audio(audio_bytes, format="audio/wav")

                with col2:
                    st.metric("⏱️ Duration", f"{audio_buffer.duration_seconds:.2f}s")
                    st.metric("🎚️ Sample Rate", f"{audio_buffer.frame_rate}Hz")
                    file_size_bytes = len(audio_bytes)
                    file_size_kb = file_size_bytes / 1024
                    size_display = (
                        f"{file_size_kb / 1024:.2f} MB"
                        if file_size_kb >= 1024
                        else f"{file_size_kb:.1f} KB"
                    )
                    st.metric("💾 Size", size_display)

                st.download_button(
                    label="📁 Download Audio",
                    data=audio_bytes,
                    file_name=f"farmer_interview_{int(time.time())}.wav",
                    mime="audio/wav",
                    use_container_width=True,
                )

            # Reset button
            if st.button("🔄 Start New Recording", type="secondary", use_container_width=True):
                reset_recording_session()


def render_import_audio_workflow():
    """Render the import audio workflow."""
    st.markdown("### 📁 Import Audio File")

    uploaded_file = st.file_uploader(
        "Upload farmer interview audio (WAV, MP3, M4A, FLAC)",
        type=["wav", "mp3", "m4a", "flac"],
        label_visibility="collapsed",
        key="audio_uploader",
    )

    if uploaded_file:
        st.audio(uploaded_file, format=uploaded_file.type)

        # File info
        col1, col2 = st.columns(2)
        with col1:
            st.info(f"**File:** {uploaded_file.name}")
        with col2:
            st.info(f"**Size:** {len(uploaded_file.getvalue()) / 1024:.1f} KB")

        # Convert uploaded file to audio buffer for consistent processing
        if st.button("✅ **Process Audio**", type="primary", use_container_width=True):
            try:
                # Convert uploaded file to AudioSegment
                audio_buffer = pydub.AudioSegment.from_file(uploaded_file)
                st.session_state.audio_buffer = audio_buffer
                st.success(
                    "✅ **Audio processed successfully!** Proceed to transcription."
                )
                st.rerun()
            except Exception as e:
                st.error(f"❌ Failed to process audio file: {e}")


def render_transcription_section():
    """Render the transcription section."""
    st.markdown("### 🎯 Transcription")

    audio_buffer = st.session_state.get("audio_buffer", pydub.AudioSegment.empty())

    if len(audio_buffer) == 0:
        st.info("💡 **No audio available.** Please record or import audio first.")
        return

    if not st.session_state.get("transcription_service"):
        st.error(
            "❌ **Transcription service not available.** Please check your GCP credentials."
        )
        return

    # Transcription controls
    if st.session_state.get("transcript") is None:
        if st.button(
            "🎙️ **Start Transcription**", type="primary", use_container_width=True
        ):
            with st.spinner("🤖 Transcribing audio... This may take a few minutes."):
                transcript = process_transcription(audio_buffer)
                if transcript:
                    st.session_state.transcript = transcript
                    st.session_state.edited_transcript = transcript
                    st.success("✅ **Transcription complete!**")
                    st.rerun()
    else:
        st.success("✅ **Transcription Complete!**")

        with st.expander("📜 **Review & Edit Transcript**", expanded=True):
            # Editable transcript
            edited_transcript = st.text_area(
                "Edit transcript if needed:",
                value=st.session_state.get("edited_transcript")
                or st.session_state.transcript,
                height=200,
                key="transcript_editor",
            )

            if st.button("💾 Save Changes", key="save_transcript_btn"):
                st.session_state.edited_transcript = edited_transcript
                st.success("Changes saved!")

        # Download options
        col1, col2 = st.columns(2)
        with col1:
            st.download_button(
                label="📄 Download Transcript",
                data=st.session_state.get("edited_transcript")
                or st.session_state.transcript,
                file_name=f"farmer_transcript_{int(time.time())}.txt",
                mime="text/plain",
                use_container_width=True,
            )
        with col2:
            if st.button(
                "🔄 Transcribe Again", type="secondary", use_container_width=True
            ):
                st.session_state.transcript = None
                st.session_state.edited_transcript = None
                st.session_state.gemini_result = None
                st.rerun()


def render_analysis_section():
    """Render the AI analysis section."""
    st.markdown("### 📊 AI Analysis")

    transcript = st.session_state.get("edited_transcript") or st.session_state.get(
        "transcript"
    )

    if not transcript:
        st.info("💡 **No transcript available.** Please transcribe audio first.")
        return

    if not st.session_state.get("gemini_service"):
        st.error("❌ **Gemini service not available.**")
        return

    if st.session_state.get("gemini_result") is None:
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**What it does:**")
            st.markdown("- Extracts farmer details")
            st.markdown("- Identifies challenges")
            st.markdown("- Analyzes farm data")
        with col2:
            st.markdown("**Output format:**")
            st.markdown("- Structured JSON")
            st.markdown("- Ready for database")
            st.markdown("- Survey-ready data")

        if st.button(
            "🚀 **Generate Survey Payload**", type="primary", use_container_width=True
        ):
            with st.spinner(
                "🤖 Analyzing transcript and generating structured data..."
            ):
                gemini_result = generate_survey_payload(transcript)
                if gemini_result:
                    st.session_state.gemini_result = gemini_result
                    st.success("✅ **Analysis complete!**")
                    st.rerun()
    else:
        st.success("✅ **Analysis Complete!**")

        with st.expander("📊 **Structured Survey Data**", expanded=True):
            st.json(st.session_state.gemini_result)

        # Download options
        col1, col2 = st.columns(2)
        with col1:
            st.download_button(
                label="📥 Download JSON",
                data=json.dumps(
                    st.session_state.gemini_result, indent=2, ensure_ascii=False
                ),
                file_name=f"farmer_survey_{int(time.time())}.json",
                mime="application/json",
                use_container_width=True,
            )
        with col2:
            if st.button(
                "🔄 Analyze Again", type="secondary", use_container_width=True
            ):
                st.session_state.gemini_result = None
                st.rerun()


def render_export_section():
    """Render the export section."""
    st.markdown("### 📤 Export & Summary")

    audio_buffer = st.session_state.get("audio_buffer", pydub.AudioSegment.empty())
    transcript = st.session_state.get("edited_transcript") or st.session_state.get(
        "transcript"
    )
    payload = st.session_state.get("gemini_result")

    # Progress indicators
    if audio_buffer and transcript and payload:
        st.success(
            "🎉 **All processing complete!** Your farmer interview data is ready."
        )

        # Summary display
        with st.expander("📋 **Complete Summary**", expanded=True):
            farmer_name = payload.get("farmerDetails", {}).get("farmerName", "Unknown")
            village = payload.get("farmerDetails", {}).get("village", "Unknown")
            summary = payload.get("interviewMetadata", {}).get("summary", "")

            st.markdown(f"**👤 Farmer:** {farmer_name}")
            st.markdown(f"**📍 Location:** {village}")
            if summary:
                st.markdown(f"**📝 Summary:** {summary}")

                # Quick export section
        st.markdown("#### Export Options")

        export_col1, export_col2, export_col3 = st.columns(3)

        with export_col1:
            audio_bytes = audio_buffer.export(format="wav").read()
            st.download_button(
                label="📁 Audio File",
                data=audio_bytes,
                file_name=f"farmer_interview_{int(time.time())}.wav",
                mime="audio/wav",
                use_container_width=True,
            )

        with export_col2:
            st.download_button(
                label="📄 Transcript",
                data=transcript,
                file_name=f"farmer_transcript_{int(time.time())}.txt",
                mime="text/plain",
                use_container_width=True,
            )

        with export_col3:
            st.download_button(
                label="📊 Survey JSON",
                data=json.dumps(payload, indent=2, ensure_ascii=False),
                file_name=f"farmer_complete_{int(time.time())}.json",
                mime="application/json",
                use_container_width=True,
            )
    else:
        st.warning("⚠️ **Processing incomplete.** Please complete all steps above.")


def get_elapsed_time():
    """Get the current elapsed recording time."""
    now = time.time()
    base_elapsed = 0.0
    if st.session_state.start_time is not None:
        base_elapsed = now - st.session_state.start_time - st.session_state.total_paused
        if st.session_state.paused and st.session_state.paused_at is not None:
            base_elapsed -= now - st.session_state.paused_at

    return max(base_elapsed, 0)


def toggle_recording_pause():
    """Toggle recording pause/resume state."""
    if not st.session_state.paused:
        st.session_state.paused = True
        st.session_state.paused_at = time.time()
    else:
        if st.session_state.paused_at is not None:
            st.session_state.total_paused += time.time() - st.session_state.paused_at
        st.session_state.paused = False
        st.session_state.paused_at = None
    st.rerun()


def reset_recording_session():
    """Reset all session state for a new recording."""
    st.session_state.audio_buffer = pydub.AudioSegment.empty()
    st.session_state.start_time = None
    st.session_state.paused = False
    st.session_state.paused_at = None
    st.session_state.total_paused = 0.0
    st.session_state.transcript = None
    st.session_state.gemini_result = None
    st.session_state.performance_metrics = None
    st.session_state.edited_transcript = None
    st.rerun()


def main():
    """Main application function."""
    # Configure page
    st.set_page_config(page_title=APP_TITLE, page_icon=APP_ICON, layout=APP_LAYOUT)

    # Apply custom styling
    apply_custom_styling()

    # Application header
    st.title(f"🌾 {APP_TITLE}")
    st.markdown(
        "An intelligent agent to process farmer interview surveys from audio recordings."
    )

    # Initialize session state
    initialize_session_state()

    # Top-level workflow selection
    st.markdown("---")
    workflow = st.radio(
        "Choose your workflow:",
        ["🎙️ Live Record Interview", "📁 Import Audio File"],
        horizontal=True,
        label_visibility="collapsed",
        key="workflow_selector",
    )

    # Render workflow-specific section
    if "Live Record" in workflow:
        render_live_record_workflow()
    else:
        render_import_audio_workflow()

    # Shared processing sections
    st.markdown("---")
    render_transcription_section()

    st.markdown("---")
    render_analysis_section()

    st.markdown("---")
    render_export_section()


if __name__ == "__main__":
    main()
