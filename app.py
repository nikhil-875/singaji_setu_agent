import queue
import streamlit as st
import pydub
import time
import json
from streamlit_webrtc import webrtc_streamer, WebRtcMode

# Import services and utilities
from services.transcription_service import TranscriptionService
from services.gemini_service import GeminiService
from utils.ui_components import get_default_schema
from config.settings import (
    GCS_BUCKET_NAME,
    get_gcp_project_id,
    GCP_LOCATION,
    validate_environment,
)


def format_time(seconds: float) -> str:
    seconds = max(0, int(seconds))
    m, s = divmod(seconds, 60)
    return f"{m:02d}:{s:02d}"


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


def initialize_transcription_service():
    """Initialize transcription service and related session state."""
    # Validate environment variables first
    if not validate_environment():
        st.warning(
            "⚠️ Environment validation failed. Transcription features will be limited."
        )

    if "transcription_service" not in st.session_state:
        # Get GCP project ID from environment or service account
        project_id = get_gcp_project_id()
        if not project_id:
            st.warning(
                "⚠️ GCP Project ID not found. Please set GCP_PROJECT_ID environment variable or check service account credentials."
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

    # Transcription-related session state
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


def get_current_step():
    """Determine the current workflow step based on session state."""
    audio_buffer = st.session_state.get("audio_buffer", pydub.AudioSegment.empty())
    has_audio = len(audio_buffer) > 0
    has_transcript = st.session_state.get("transcript") is not None
    has_payload = st.session_state.get("gemini_result") is not None

    if not has_audio:
        return "record"
    elif not has_transcript:
        return "transcribe"
    elif not has_payload:
        return "analyze"
    else:
        return "review"


def create_step_indicator():
    """Create a visual step indicator showing current progress."""
    step = get_current_step()
    steps = ["record", "transcribe", "analyze", "review"]

    cols = st.columns(len(steps))
    for i, step_name in enumerate(steps):
        with cols[i]:
            if step_name == step:
                st.markdown(f"🔵 **{step_name.title()}**")
            elif steps.index(step_name) < steps.index(step):
                st.markdown(f"✅ **{step_name.title()}**")
            else:
                st.markdown(f"⚪ {step_name.title()}")


def main():
    st.title("🌾 Farmer Interview Recorder")

    # Initialize transcription service
    initialize_transcription_service()

    # Session init for audio recording
    if "audio_buffer" not in st.session_state:
        st.session_state["audio_buffer"] = pydub.AudioSegment.empty()
    if "paused" not in st.session_state:
        st.session_state["paused"] = False
    if "start_time" not in st.session_state:
        st.session_state["start_time"] = None
    if "paused_at" not in st.session_state:
        st.session_state["paused_at"] = None
    if "total_paused" not in st.session_state:
        st.session_state["total_paused"] = 0.0

    # Add step indicator
    # create_step_indicator()

    # Create tabs for organized workflow
    tab1, tab2, tab3, tab4 = st.tabs(
        ["🎙️ **Record**", "🎯 **Transcribe**", "📊 **Analyze**", "📋 **Review**"]
    )

    with tab1:
        render_recording_tab()

    with tab2:
        render_transcription_tab()

    with tab3:
        render_analysis_tab()

    with tab4:
        render_review_tab()


def render_recording_tab():
    """Render the recording interface."""
    # st.header("🎙️ Record Farmer Interview")

    # Initialize WebRTC
    RTC_CONFIGURATION = {"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]}

    webrtc_ctx = webrtc_streamer(
        key="complete-audio-recorder",
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

        # Status and timer
        col1, col2, col3 = st.columns([2, 1, 1])
        with col1:
            if st.session_state["paused"]:
                st.warning("⏸️ **RECORDING PAUSED**")
            else:
                st.success("🎤 **RECORDING ACTIVE**")
        with col2:
            elapsed_time = get_elapsed_time()
            st.metric("⏱️ Duration", format_time(elapsed_time))
        with col3:
            button_text = "⏸️ Pause" if not st.session_state["paused"] else "▶️ Resume"
            button_type = "secondary" if not st.session_state["paused"] else "primary"
            if st.button(button_text, type=button_type, use_container_width=True):
                toggle_recording_pause()

    # Start time bookkeeping
    if webrtc_ctx.state.playing and st.session_state["start_time"] is None:
        st.session_state["start_time"] = time.time()

    # Recording loop
    while True:
        if webrtc_ctx.audio_receiver:
            try:
                audio_frames = webrtc_ctx.audio_receiver.get_frames(timeout=1)
            except queue.Empty:
                continue

            # Only buffer when not paused
            if not st.session_state["paused"]:
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
                    st.session_state["audio_buffer"] += sound_chunk
        else:
            break

    # Show recorded audio if available
    audio_buffer = st.session_state["audio_buffer"]
    if len(audio_buffer) > 0:
        st.success(
            "✅ **Recording Complete!** Switch to the Transcribe tab to process your audio."
        )

        with st.expander("🎵 **Audio Preview & Details**", expanded=False):
            # Audio playback
            audio_bytes = audio_buffer.export(format="wav").read()
            st.audio(audio_bytes, format="audio/wav")

            # Recording info
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("⏱️ Duration", f"{audio_buffer.duration_seconds:.2f}s")
            with col2:
                st.metric("🎚️ Sample Rate", f"{audio_buffer.frame_rate}Hz")
            with col3:
                file_size_bytes = len(audio_bytes)
                file_size_kb = file_size_bytes / 1024
                size_display = (
                    f"{file_size_kb / 1024:.2f} MB"
                    if file_size_kb >= 1024
                    else f"{file_size_kb:.1f} KB"
                )
                st.metric("💾 Size", size_display)

        # Quick actions
        col1, col2 = st.columns(2)
        with col1:
            st.download_button(
                label="📁 Download Audio",
                data=audio_bytes,
                file_name=f"farmer_interview_{int(time.time())}.wav",
                mime="audio/wav",
                use_container_width=True,
            )
        with col2:
            if st.button(
                "🔄 Start New Recording", type="primary", use_container_width=True
            ):
                reset_recording_session()


def render_transcription_tab():
    """Render the transcription interface."""
    # st.header("🎯 Transcribe Audio to Text")

    audio_buffer = st.session_state.get("audio_buffer", pydub.AudioSegment.empty())

    if len(audio_buffer) == 0:
        st.info(
            "💡 **No audio recorded yet.** Please record an interview first in the Record tab."
        )
        return

    if not st.session_state.get("transcription_service"):
        st.error(
            "❌ **Transcription service not available.** Please check your GCP credentials."
        )
        return

    # Transcription controls
    if st.session_state.get("transcript") is None:
        st.markdown("### 🤖 Start Transcription")

        col1, col2, col3 = st.columns([2, 1, 1])
        with col1:
            st.markdown("**Language:** Hindi (hi-IN) - Optimized for farmer interviews")
        with col2:
            st.markdown("**Processing:** ~2-5 minutes")
        with col3:
            if st.button(
                "🎙️ **Transcribe Now**", type="primary", use_container_width=True
            ):
                with st.spinner(
                    "🤖 Transcribing audio... This may take a few minutes."
                ):
                    transcript = process_transcription(audio_buffer)
                    if transcript:
                        st.session_state.transcript = transcript
                        st.success(
                            "✅ **Transcription complete!** Switch to Analyze tab for AI analysis."
                        )
                        st.rerun()
    else:
        st.success("✅ **Transcription Complete!**")

        with st.expander("📜 **View Transcript**", expanded=True):
            # Editable transcript
            edited_transcript = st.text_area(
                "Review & Edit Transcript:",
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


def render_analysis_tab():
    """Render the AI analysis interface."""
    # st.header("📊 AI-Powered Survey Analysis")

    transcript = st.session_state.get("edited_transcript") or st.session_state.get(
        "transcript"
    )

    if not transcript:
        st.info(
            "💡 **No transcript available.** Please transcribe audio first in the Transcribe tab."
        )
        return

    if not st.session_state.get("gemini_service"):
        st.error("❌ **Gemini service not available.**")
        return

    if st.session_state.get("gemini_result") is None:
        st.markdown("### 🤖 Generate Structured Survey Data")

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

        st.markdown("---")

        if st.button(
            "🚀 **Generate Survey Payload**", type="primary", use_container_width=True
        ):
            with st.spinner(
                "🤖 Analyzing transcript and generating structured data..."
            ):
                gemini_result = generate_survey_payload(transcript)
                if gemini_result:
                    st.session_state.gemini_result = gemini_result
                    st.success(
                        "✅ **Analysis complete!** Switch to Review tab to see results."
                    )
                    st.rerun()
    else:
        st.success("✅ **Analysis Complete!**")

        with st.expander("📊 **View Structured Data**", expanded=True):
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


def render_review_tab():
    """Render the review and summary interface."""
    # st.header("📋 Review & Export")

    audio_buffer = st.session_state.get("audio_buffer", pydub.AudioSegment.empty())
    transcript = st.session_state.get("edited_transcript") or st.session_state.get(
        "transcript"
    )
    payload = st.session_state.get("gemini_result")

    # Summary cards
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        has_audio = len(audio_buffer) > 0
    with col2:
        has_transcript = transcript is not None
    with col3:
        has_payload = payload is not None
    with col4:
        all_complete = has_audio and has_transcript and has_payload

    if all_complete:
        st.success(
            "🎉 **All processing complete!** Your farmer interview data is ready for export."
        )

        # Quick export section
        st.markdown("### 📤 Export Options")

        export_col1, export_col2, export_col3 = st.columns(3)

        with export_col1:
            if len(audio_buffer) > 0:
                audio_bytes = audio_buffer.export(format="wav").read()
                st.download_button(
                    label="📁 Audio File",
                    data=audio_bytes,
                    file_name=f"farmer_interview_{int(time.time())}.wav",
                    mime="audio/wav",
                    use_container_width=True,
                )

        with export_col2:
            if transcript:
                st.download_button(
                    label="📄 Transcript",
                    data=transcript,
                    file_name=f"farmer_transcript_{int(time.time())}.txt",
                    mime="text/plain",
                    use_container_width=True,
                )

        with export_col3:
            if payload:
                st.download_button(
                    label="📊 Survey JSON",
                    data=json.dumps(payload, indent=2, ensure_ascii=False),
                    file_name=f"farmer_complete_{int(time.time())}.json",
                    mime="application/json",
                    use_container_width=True,
                )

        # Summary display
        with st.expander("📋 **Complete Summary**", expanded=True):
            if payload:
                farmer_name = payload.get("farmerDetails", {}).get(
                    "farmerName", "Unknown"
                )
                village = payload.get("farmerDetails", {}).get("village", "Unknown")
                summary = payload.get("interviewMetadata", {}).get("summary", "")

                st.markdown(f"**👤 Farmer:** {farmer_name}")
                st.markdown(f"**📍 Location:** {village}")
                if summary:
                    st.markdown(f"**📝 Summary:** {summary}")

    else:
        st.warning(
            "⚠️ **Processing incomplete.** Please complete all steps before exporting."
        )


def get_elapsed_time():
    """Get the current elapsed recording time."""
    now = time.time()
    base_elapsed = 0.0
    if st.session_state["start_time"] is not None:
        base_elapsed = (
            now - st.session_state["start_time"] - st.session_state["total_paused"]
        )
        if st.session_state["paused"] and st.session_state["paused_at"] is not None:
            base_elapsed -= now - st.session_state["paused_at"]

    return max(base_elapsed, 0)


def toggle_recording_pause():
    """Toggle recording pause/resume state."""
    if not st.session_state["paused"]:
        st.session_state["paused"] = True
        st.session_state["paused_at"] = time.time()
    else:
        if st.session_state["paused_at"] is not None:
            st.session_state["total_paused"] += (
                time.time() - st.session_state["paused_at"]
            )
        st.session_state["paused"] = False
        st.session_state["paused_at"] = None
    st.rerun()


def reset_recording_session():
    """Reset all session state for a new recording."""
    st.session_state["audio_buffer"] = pydub.AudioSegment.empty()
    st.session_state["start_time"] = None
    st.session_state["paused"] = False
    st.session_state["paused_at"] = None
    st.session_state["total_paused"] = 0.0
    st.session_state.transcript = None
    st.session_state.gemini_result = None
    st.session_state.performance_metrics = None
    st.session_state.edited_transcript = None
    st.rerun()


if __name__ == "__main__":
    main()
