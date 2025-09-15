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

    # Step tracking for collapsible interface
    if "current_step" not in st.session_state:
        st.session_state.current_step = "workflow"  # Start with workflow selection


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
    """Render the live recording workflow."""
    with st.container():
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

        # Conditional Controls - Show only when recording is active
        if webrtc_ctx.state.playing:
            st.markdown("---")
            # Single toggle button for play/pause
            button_text = "⏸️ Pause" if not st.session_state.paused else "▶️ Resume"
            button_type = "secondary" if not st.session_state.paused else "primary"

            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                if st.button(button_text, type=button_type, use_container_width=True):
                    toggle_recording_pause()

        # Start time bookkeeping
        if webrtc_ctx.state.playing and st.session_state.start_time is None:
            st.session_state.start_time = time.time()

        # Initialize UI placeholders for status and timer
        if webrtc_ctx.state.playing:
            col1, col2 = st.columns(2)
            with col1:
                status_placeholder = st.empty()
            with col2:
                timer_placeholder = st.empty()
        else:
            # Create empty placeholders even when not recording
            col1, col2 = st.columns(2)
            with col1:
                status_placeholder = st.empty()
            with col2:
                timer_placeholder = st.empty()

        # Recording loop with real-time UI updates
        while webrtc_ctx.audio_receiver:
            # Update timer and status in real-time
            now = time.time()
            base_elapsed = 0.0
            if st.session_state.start_time is not None:
                base_elapsed = (
                    now - st.session_state.start_time - st.session_state.total_paused
                )
                if st.session_state.paused and st.session_state.paused_at is not None:
                    base_elapsed -= now - st.session_state.paused_at

            elapsed_time = max(base_elapsed, 0)

            # Update UI placeholders in real-time
            if st.session_state.paused:
                status_placeholder.warning("⏸️ RECORDING PAUSED")
            else:
                status_placeholder.success("🎤 Recording...")

            timer_placeholder.info(f"⏱️ {format_time(elapsed_time)}")

            try:
                audio_frames = webrtc_ctx.audio_receiver.get_frames(timeout=0.1)
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
            # Clear placeholders when recording stops
            try:
                status_placeholder.empty()
                timer_placeholder.empty()
            except (NameError, AttributeError):
                # Placeholders might not exist if recording never started
                pass

        # Show recorded audio if available
        audio_buffer = st.session_state.audio_buffer
        if len(audio_buffer) > 0:
            # Success card - compact
            st.markdown(
                """
            <div style="background: #d4edda; border: 1px solid #c3e6cb; border-radius: 6px;
                        padding: 10px; margin: 10px 0;">
                <div style="color: #155724; font-size: 14px; font-weight: bold;">✅ Recording Complete!</div>
                <div style="color: #155724; font-size: 12px; margin-top: 3px;">
                    Your audio is ready for transcription.
                </div>
            </div>
            """,
                unsafe_allow_html=True,
            )

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
            if st.button(
                "🔄 Start New Recording", type="secondary", use_container_width=True
            ):
                reset_recording_session()

            # Auto-advance to transcription when recording is complete
            if st.button(
                "Continue to Transcription ➡️", type="primary", use_container_width=True
            ):
                st.session_state.current_step = "transcribe"
                st.rerun()


def render_import_audio_workflow():
    """Render the import audio workflow."""
    with st.container():
        # Upload section
        uploaded_file = st.file_uploader(
            "Choose audio file (WAV, MP3, M4A, FLAC)",
            type=["wav", "mp3", "m4a", "flac"],
            label_visibility="collapsed",
            key="audio_uploader",
        )

        if uploaded_file:
            # File preview card - compact
            st.markdown(
                """
            <div style="background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 6px;
                        padding: 8px; margin: 8px 0;">
                <div style="color: #495057; font-size: 14px; font-weight: bold;">📄 File Selected</div>
            </div>
            """,
                unsafe_allow_html=True,
            )

            # Audio preview and info
            col1, col2 = st.columns([1, 1])

            with col1:
                st.audio(uploaded_file, format=uploaded_file.type)

            with col2:
                file_size_kb = len(uploaded_file.getvalue()) / 1024
                size_display = (
                    f"{file_size_kb / 1024:.2f} MB"
                    if file_size_kb >= 1024
                    else f"{file_size_kb:.1f} KB"
                )

                st.metric("📄 File Name", uploaded_file.name)
                st.metric("💾 File Size", size_display)
                st.metric("🎵 Format", uploaded_file.type.split("/")[-1].upper())

            # Process button
            if st.button(
                "✅ **Process Audio**", type="primary", use_container_width=True
            ):
                with st.spinner("🔄 Processing audio file..."):
                    try:
                        # Convert uploaded file to AudioSegment
                        audio_buffer = pydub.AudioSegment.from_file(uploaded_file)
                        st.session_state.audio_buffer = audio_buffer

                        # Success message - compact
                        st.markdown(
                            """
                        <div style="background: #d4edda; border: 1px solid #c3e6cb; border-radius: 6px;
                                    padding: 10px; margin: 10px 0;">
                            <div style="color: #155724; font-size: 14px; font-weight: bold;">✅ Audio Processed Successfully!</div>
                            <div style="color: #155724; font-size: 12px; margin-top: 3px;">
                                Your audio is ready for transcription.
                            </div>
                        </div>
                        """,
                            unsafe_allow_html=True,
                        )
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Failed to process audio file: {e}")

            # Auto-advance to transcription when audio is processed
            if st.button(
                "Continue to Transcription ➡️", type="primary", use_container_width=True
            ):
                st.session_state.current_step = "transcribe"
                st.rerun()


def render_transcription_section():
    """Render the transcription section."""
    with st.container():
        audio_buffer = st.session_state.get("audio_buffer", pydub.AudioSegment.empty())

        if len(audio_buffer) == 0:
            st.markdown(
                """
            <div style="background: #fff3cd; border: 1px solid #ffeaa7; border-radius: 6px;
                        padding: 10px; text-align: center;">
                <div style="color: #856404; font-size: 14px; font-weight: bold;">⏳ Waiting for Audio</div>
                <div style="color: #856404; font-size: 12px; margin-top: 3px;">
                    Please complete Step 1 first by recording or importing audio.
                </div>
            </div>
            """,
                unsafe_allow_html=True,
            )
            return

        if not st.session_state.get("transcription_service"):
            st.markdown(
                """
            <div style="background: #f8d7da; border: 1px solid #f5c6cb; border-radius: 6px;
                        padding: 10px; text-align: center;">
                <div style="color: #721c24; font-size: 14px; font-weight: bold;">❌ Service Unavailable</div>
                <div style="color: #721c24; font-size: 12px; margin-top: 3px;">
                    Transcription service not available. Please check your GCP credentials.
                </div>
            </div>
            """,
                unsafe_allow_html=True,
            )
            return

        # Transcription status and controls
        if st.session_state.get("transcript") is None:
            # Ready to transcribe
            st.markdown(
                """
            <div style="background: #e3f2fd; border: 1px solid #bbdefb; border-radius: 6px;
                        padding: 10px; margin: 10px 0;">
                <div style="color: #1976d2; font-size: 14px; font-weight: bold;">🤖 Ready to Transcribe</div>
                <div style="color: #1976d2; font-size: 12px; margin-top: 3px;">
                    Your audio is ready for transcription. This process may take 2-5 minutes.
                </div>
            </div>
            """,
                unsafe_allow_html=True,
            )

            if st.button(
                "🎙️ **Start Transcription**", type="primary", use_container_width=True
            ):
                with st.spinner(
                    "🤖 Transcribing audio... This may take a few minutes."
                ):
                    transcript = process_transcription(audio_buffer)
                    if transcript:
                        st.session_state.transcript = transcript
                        st.session_state.edited_transcript = transcript
                        st.success("✅ **Transcription complete!**")
                        st.rerun()
        else:
            # Transcription complete
            st.markdown(
                """
            <div style="background: #d4edda; border: 1px solid #c3e6cb; border-radius: 6px;
                        padding: 10px; margin: 10px 0;">
                <div style="color: #155724; font-size: 14px; font-weight: bold;">✅ Transcription Complete!</div>
                <div style="color: #155724; font-size: 12px; margin-top: 3px;">
                    Your audio has been successfully converted to text. Review and edit if needed.
                </div>
            </div>
            """,
                unsafe_allow_html=True,
            )

            # Transcript review section
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

            # Action buttons
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

            # Auto-advance to analysis when transcription is complete
            if st.button(
                "Continue to AI Analysis ➡️", type="primary", use_container_width=True
            ):
                st.session_state.current_step = "analyze"
                st.rerun()


def render_analysis_section():
    """Render the AI analysis section."""
    with st.container():
        transcript = st.session_state.get("edited_transcript") or st.session_state.get(
            "transcript"
        )

        if not transcript:
            st.markdown(
                """
            <div style="background: #fff3cd; border: 1px solid #ffeaa7; border-radius: 6px;
                        padding: 10px; text-align: center;">
                <div style="color: #856404; font-size: 14px; font-weight: bold;">⏳ Waiting for Transcript</div>
                <div style="color: #856404; font-size: 12px; margin-top: 3px;">
                    Please complete Step 2 first by transcribing your audio.
                </div>
            </div>
            """,
                unsafe_allow_html=True,
            )
            return

        if not st.session_state.get("gemini_service"):
            st.markdown(
                """
            <div style="background: #f8d7da; border: 1px solid #f5c6cb; border-radius: 6px;
                        padding: 10px; text-align: center;">
                <div style="color: #721c24; font-size: 14px; font-weight: bold;">❌ Service Unavailable</div>
                <div style="color: #721c24; font-size: 12px; margin-top: 3px;">
                    Gemini service not available. Please check your API credentials.
                </div>
            </div>
            """,
                unsafe_allow_html=True,
            )
            return

        if st.session_state.get("gemini_result") is None:
            # Ready to analyze
            st.markdown(
                """
            <div style="background: #e8f5e8; border: 1px solid #c8e6c9; border-radius: 8px;
                        padding: 15px; margin: 15px 0;">
                <h4 style="color: #2e7d32; margin: 0 0 10px 0;">🤖 Ready for AI Analysis</h4>
                <p style="color: #2e7d32; margin: 0 0 15px 0;">
                    Your transcript is ready for AI-powered analysis. This will extract structured survey data.
                </p>
            </div>
            """,
                unsafe_allow_html=True,
            )

            # Info cards - compact
            info_col1, info_col2 = st.columns(2)
            with info_col1:
                st.markdown(
                    """
                <div style="background: #f3e5f5; border: 1px solid #ce93d8; border-radius: 6px;
                            padding: 10px; height: 100%;">
                    <div style="color: #4a148c; font-size: 13px; font-weight: bold; margin-bottom: 8px;">🔍 What it analyzes:</div>
                    <ul style="color: #4a148c; margin: 0; padding-left: 15px; font-size: 12px;">
                        <li>Farmer details & demographics</li>
                        <li>Farm characteristics</li>
                        <li>Crop information</li>
                        <li>Challenges & needs</li>
                    </ul>
                </div>
                """,
                    unsafe_allow_html=True,
                )

            with info_col2:
                st.markdown(
                    """
                <div style="background: #e3f2fd; border: 1px solid #90caf9; border-radius: 6px;
                            padding: 10px; height: 100%;">
                    <div style="color: #1565c0; font-size: 13px; font-weight: bold; margin-bottom: 8px;">📋 Output format:</div>
                    <ul style="color: #1565c0; margin: 0; padding-left: 15px; font-size: 12px;">
                        <li>Structured JSON data</li>
                        <li>Database-ready format</li>
                        <li>Survey-complete records</li>
                        <li>Ready for analysis</li>
                    </ul>
                </div>
                """,
                    unsafe_allow_html=True,
                )

            if st.button(
                "🚀 **Generate Survey Payload**",
                type="primary",
                use_container_width=True,
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
            # Analysis complete
            st.markdown(
                """
            <div style="background: #d4edda; border: 1px solid #c3e6cb; border-radius: 8px;
                        padding: 15px; margin: 15px 0;">
                <h4 style="color: #155724; margin: 0;">✅ AI Analysis Complete!</h4>
                <p style="color: #155724; margin: 5px 0 0 0;">
                    Your transcript has been successfully analyzed and structured survey data has been generated.
                </p>
            </div>
            """,
                unsafe_allow_html=True,
            )

            # Results section
            with st.expander("📊 **View Structured Survey Data**", expanded=True):
                st.json(st.session_state.gemini_result)

            # Action buttons
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

            # Auto-advance to export when analysis is complete
            if st.button(
                "Continue to Export ➡️", type="primary", use_container_width=True
            ):
                st.session_state.current_step = "export"
                st.rerun()


def render_export_section():
    """Render the export section."""
    with st.container():
        audio_buffer = st.session_state.get("audio_buffer", pydub.AudioSegment.empty())
        transcript = st.session_state.get("edited_transcript") or st.session_state.get(
            "transcript"
        )
        payload = st.session_state.get("gemini_result")

        # Progress indicators with better styling
        progress_col1, progress_col2, progress_col3 = st.columns(3)

        with progress_col1:
            if len(audio_buffer) > 0:
                st.markdown(
                    """
                <div style="background: #d4edda; border: 1px solid #c3e6cb; border-radius: 6px;
                            padding: 8px; text-align: center; margin-bottom: 8px;">
                    <div style="color: #155724; font-size: 18px;">✅</div>
                    <div style="color: #155724; font-size: 11px; font-weight: bold;">Audio Ready</div>
                </div>
                """,
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    """
                <div style="background: #f8d7da; border: 1px solid #f5c6cb; border-radius: 6px;
                            padding: 8px; text-align: center; margin-bottom: 8px;">
                    <div style="color: #721c24; font-size: 18px;">❌</div>
                    <div style="color: #721c24; font-size: 11px; font-weight: bold;">No Audio</div>
                </div>
                """,
                    unsafe_allow_html=True,
                )

        with progress_col2:
            if transcript:
                st.markdown(
                    """
                <div style="background: #d4edda; border: 1px solid #c3e6cb; border-radius: 6px;
                            padding: 8px; text-align: center; margin-bottom: 8px;">
                    <div style="color: #155724; font-size: 18px;">✅</div>
                    <div style="color: #155724; font-size: 11px; font-weight: bold;">Transcript Ready</div>
                </div>
                """,
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    """
                <div style="background: #f8d7da; border: 1px solid #f5c6cb; border-radius: 6px;
                            padding: 8px; text-align: center; margin-bottom: 8px;">
                    <div style="color: #721c24; font-size: 18px;">❌</div>
                    <div style="color: #721c24; font-size: 11px; font-weight: bold;">No Transcript</div>
                </div>
                """,
                    unsafe_allow_html=True,
                )

        with progress_col3:
            if payload:
                st.markdown(
                    """
                <div style="background: #d4edda; border: 1px solid #c3e6cb; border-radius: 6px;
                            padding: 8px; text-align: center; margin-bottom: 8px;">
                    <div style="color: #155724; font-size: 18px;">✅</div>
                    <div style="color: #155724; font-size: 11px; font-weight: bold;">Survey Data Ready</div>
                </div>
                """,
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    """
                <div style="background: #f8d7da; border: 1px solid #f5c6cb; border-radius: 6px;
                            padding: 8px; text-align: center; margin-bottom: 8px;">
                    <div style="color: #721c24; font-size: 18px;">❌</div>
                    <div style="color: #721c24; font-size: 11px; font-weight: bold;">No Survey Data</div>
                </div>
                """,
                    unsafe_allow_html=True,
                )

        if audio_buffer and transcript and payload:
            # Success celebration - compact
            st.markdown(
                """
            <div style="background: linear-gradient(135deg, #ff9a9e 0%, #fecfef 100%);
                        border: 1px solid #ff6b9d; border-radius: 8px; padding: 12px; margin: 12px 0;
                        text-align: center;">
                <div style="color: white; font-size: 18px; font-weight: bold; margin-bottom: 5px;">🎉 Processing Complete!</div>
                <div style="color: white; font-size: 13px;">
                    Your farmer interview has been fully processed. All data is ready for export!
                </div>
            </div>
            """,
                unsafe_allow_html=True,
            )

            # Summary display in a nice card
            with st.expander("📋 **Complete Summary**", expanded=True):
                summary_col1, summary_col2 = st.columns(2)

                with summary_col1:
                    farmer_name = payload.get("farmerDetails", {}).get(
                        "farmerName", "Unknown"
                    )
                    village = payload.get("farmerDetails", {}).get("village", "Unknown")
                    contact = payload.get("farmerDetails", {}).get(
                        "contactNumber", "Not provided"
                    )

                    st.markdown("#### 👤 Farmer Information")
                    st.markdown(f"**Name:** {farmer_name}")
                    st.markdown(f"**Village:** {village}")
                    st.markdown(f"**Contact:** {contact}")

                with summary_col2:
                    summary = payload.get("interviewMetadata", {}).get("summary", "")
                    if summary:
                        st.markdown("#### 📝 Interview Summary")
                        st.markdown(summary)
                    else:
                        st.markdown("#### 📝 Interview Summary")
                        st.markdown("*No summary available*")

            # Export section with nice cards
            st.markdown("#### 📤 Export Options")

            export_col1, export_col2, export_col3 = st.columns(3)

            with export_col1:
                st.markdown(
                    """
                <div style="background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 6px;
                            padding: 10px; text-align: center; margin-bottom: 8px;">
                    <div style="font-size: 20px; margin-bottom: 3px;">🎵</div>
                    <div style="font-size: 11px; color: #6c757d; margin-bottom: 8px;">Audio Recording</div>
                </div>
                """,
                    unsafe_allow_html=True,
                )
                audio_bytes = audio_buffer.export(format="wav").read()
                st.download_button(
                    label="📁 Download Audio",
                    data=audio_bytes,
                    file_name=f"farmer_interview_{int(time.time())}.wav",
                    mime="audio/wav",
                    use_container_width=True,
                )

            with export_col2:
                st.markdown(
                    """
                <div style="background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 6px;
                            padding: 10px; text-align: center; margin-bottom: 8px;">
                    <div style="font-size: 20px; margin-bottom: 3px;">📄</div>
                    <div style="font-size: 11px; color: #6c757d; margin-bottom: 8px;">Text Transcript</div>
                </div>
                """,
                    unsafe_allow_html=True,
                )
                st.download_button(
                    label="📄 Download Transcript",
                    data=transcript,
                    file_name=f"farmer_transcript_{int(time.time())}.txt",
                    mime="text/plain",
                    use_container_width=True,
                )

            with export_col3:
                st.markdown(
                    """
                <div style="background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 6px;
                            padding: 10px; text-align: center; margin-bottom: 8px;">
                    <div style="font-size: 20px; margin-bottom: 3px;">📊</div>
                    <div style="font-size: 11px; color: #6c757d; margin-bottom: 8px;">Survey JSON</div>
                </div>
                """,
                    unsafe_allow_html=True,
                )
                st.download_button(
                    label="📊 Download Survey Data",
                    data=json.dumps(payload, indent=2, ensure_ascii=False),
                    file_name=f"farmer_complete_{int(time.time())}.json",
                    mime="application/json",
                    use_container_width=True,
                )
        else:
            # Incomplete processing warning - compact
            st.markdown(
                """
            <div style="background: #fff3cd; border: 1px solid #ffeaa7; border-radius: 6px;
                        padding: 10px; text-align: center; margin: 10px 0;">
                <div style="color: #856404; font-size: 14px; font-weight: bold;">⚠️ Processing Incomplete</div>
                <div style="color: #856404; font-size: 12px; margin-top: 3px;">
                    Please complete all previous steps before exporting your data.
                </div>
            </div>
            """,
                unsafe_allow_html=True,
            )


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
    """Main application function with step-by-step collapsible interface."""
    # Configure page
    st.set_page_config(page_title=APP_TITLE, page_icon=APP_ICON, layout=APP_LAYOUT)

    # Apply custom styling
    apply_custom_styling()

    # Application header with compact design
    st.markdown(
        """
    <div style="text-align: center; margin-bottom: 15px;">
        <h1 style="color: #2c3e50; margin-bottom: 5px; font-size: 2em;">
            🌾 Singaji Setu Agent
        </h1>
        <p style="color: #7f8c8d; font-size: 1em; margin: 0;">
            Intelligent processing of farmer interview surveys from audio recordings
        </p>
    </div>
    """,
        unsafe_allow_html=True,
    )

    # Initialize session state
    initialize_session_state()

    # Top navigation bar with progress and reset option
    if st.session_state.current_step != "workflow":
        # Reset button in top-right
        col1, col2 = st.columns([6, 1])
        with col2:
            if st.button(
                "🔄 Reset", key="reset_workflow", help="Start over from the beginning"
            ):
                # Reset all session state
                for key in list(st.session_state.keys()):
                    del st.session_state[key]
                st.rerun()
                return

        # Progress bar
        step_order = ["workflow", "input", "transcribe", "analyze", "export"]
        current_index = step_order.index(st.session_state.current_step)
        progress_percentage = ((current_index + 1) / len(step_order)) * 100

        st.markdown(
            f"""
        <div style="margin-bottom: 20px;">
            <div style="display: flex; justify-content: space-between; margin-bottom: 8px;">
                <span style="font-size: 12px; color: #6c757d;">Progress</span>
                <span style="font-size: 12px; color: #6c757d;">{current_index + 1} of {len(step_order)} steps</span>
            </div>
            <div style="width: 100%; background: #e9ecef; border-radius: 10px; height: 8px;">
                <div style="width: {progress_percentage}%; background: linear-gradient(90deg, #667eea, #764ba2);
                            border-radius: 10px; height: 8px; transition: width 0.3s ease;"></div>
            </div>
        </div>
        """,
            unsafe_allow_html=True,
        )

    # Step-by-step workflow with collapsible sections
    steps = [
        (
            "workflow",
            "🚀 Step 1: Choose Audio Source",
            "Select how you'd like to provide your farmer interview audio",
        ),
        (
            "input",
            "🎙️ Step 2: Audio Input",
            "Record live interview or upload existing audio file",
        ),
        (
            "transcribe",
            "🎯 Step 3: AI Transcription",
            "Convert your audio recording to text using Google Speech-to-Text",
        ),
        (
            "analyze",
            "📊 Step 4: AI Analysis",
            "Extract structured survey data from your transcript using Gemini AI",
        ),
        (
            "export",
            "📤 Step 5: Export Results",
            "Download your processed data and view complete summary",
        ),
    ]

    # Render collapsible steps
    for step_id, step_title, step_desc in steps:
        is_current = st.session_state.current_step == step_id
        is_completed = get_step_completion_status(step_id)

        # Step header with status
        if is_completed:
            header_icon = "✅"
        elif is_current:
            header_icon = "🔵"
        else:
            header_icon = "⚪"

        # Create collapsible section
        expander_label = f"{header_icon} {step_title}"
        with st.expander(expander_label, expanded=is_current):
            st.markdown(
                f"""
            <div style="background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 6px;
                        padding: 12px; margin-bottom: 10px;">
                <p style="color: #495057; margin: 0; font-size: 14px;">
                    {step_desc}
                </p>
            </div>
            """,
                unsafe_allow_html=True,
            )

            # Render step content
            if step_id == "workflow":
                render_workflow_selection()
            elif step_id == "input":
                workflow = st.session_state.get("selected_workflow", "")
                if workflow == "live":
                    render_live_record_workflow()
                elif workflow == "upload":
                    render_import_audio_workflow()
                else:
                    st.info("Please select a workflow in Step 1 first.")
            elif step_id == "transcribe":
                render_transcription_section()
            elif step_id == "analyze":
                render_analysis_section()
            elif step_id == "export":
                render_export_section()

            # Clean navigation bar at the bottom
            if step_id not in [
                "workflow",
                "export",
            ]:  # No navigation for first and last steps
                st.markdown("---")
                nav_col1, nav_col2, nav_col3 = st.columns([1, 2, 1])

                with nav_col1:
                    prev_step = get_previous_step(step_id)
                    if prev_step:
                        if st.button(
                            "⬅️ Previous",
                            key=f"prev_{step_id}",
                            use_container_width=True,
                        ):
                            st.session_state.current_step = prev_step
                            st.rerun()

                with nav_col2:
                    # Step progress indicator
                    step_order = [
                        "workflow",
                        "input",
                        "transcribe",
                        "analyze",
                        "export",
                    ]
                    current_index = step_order.index(step_id) + 1  # 1-based indexing
                    total_steps = len(step_order)
                    st.markdown(
                        f"""
                    <div style="text-align: center; color: #6c757d; font-size: 12px;">
                        Step {current_index} of {total_steps}
                    </div>
                    """,
                        unsafe_allow_html=True,
                    )

                with nav_col3:
                    next_step = get_next_step(step_id)
                    if next_step:
                        button_text = "Continue ➡️"
                        if st.button(
                            button_text,
                            key=f"next_{step_id}",
                            use_container_width=True,
                            type="primary",
                        ):
                            st.session_state.current_step = next_step
                            st.rerun()


def get_step_completion_status(step_id):
    """Check if a step is completed."""
    if step_id == "workflow":
        return st.session_state.get("selected_workflow") is not None
    elif step_id == "input":
        return len(st.session_state.get("audio_buffer", pydub.AudioSegment.empty())) > 0
    elif step_id == "transcribe":
        return st.session_state.get("transcript") is not None
    elif step_id == "analyze":
        return st.session_state.get("gemini_result") is not None
    elif step_id == "export":
        return (
            len(st.session_state.get("audio_buffer", pydub.AudioSegment.empty())) > 0
            and st.session_state.get("transcript") is not None
            and st.session_state.get("gemini_result") is not None
        )
    return False


def get_previous_step(current_step):
    """Get the previous step ID."""
    step_order = ["workflow", "input", "transcribe", "analyze", "export"]
    try:
        current_index = step_order.index(current_step)
        return step_order[current_index - 1] if current_index > 0 else None
    except ValueError:
        return None


def get_next_step(current_step):
    """Get the next step ID."""
    step_order = ["workflow", "input", "transcribe", "analyze", "export"]
    try:
        current_index = step_order.index(current_step)
        return (
            step_order[current_index + 1]
            if current_index < len(step_order) - 1
            else None
        )
    except ValueError:
        return None


def render_workflow_selection():
    """Render the workflow selection step."""
    st.markdown("### Choose Your Audio Source")

    # Workflow options with better styling
    workflow_options = [
        {
            "name": "live",
            "icon": "🎙️",
            "title": "Live Recording",
            "description": "Record audio directly in your browser with real-time controls",
            "features": [
                "High-quality audio",
                "Pause/Resume",
                "Real-time feedback",
                "No file upload needed",
            ],
        },
        {
            "name": "upload",
            "icon": "📁",
            "title": "Upload File",
            "description": "Import existing audio recordings from your device",
            "features": [
                "Multiple formats",
                "Batch processing",
                "Existing recordings",
                "Quick setup",
            ],
        },
    ]

    for option in workflow_options:
        # Option card
        if st.button(
            f"{option['icon']} {option['title']}",
            key=f"workflow_{option['name']}",
            use_container_width=True,
            type="secondary"
            if st.session_state.get("selected_workflow") != option["name"]
            else "primary",
        ):
            st.session_state.selected_workflow = option["name"]

    # Show selected option details
    if st.session_state.get("selected_workflow"):
        selected_option = next(
            opt
            for opt in workflow_options
            if opt["name"] == st.session_state.selected_workflow
        )

        st.markdown(
            f"""
        <div style="background: #e3f2fd; border: 1px solid #bbdefb; border-radius: 8px;
                    padding: 15px; margin: 15px 0;">
            <h4 style="color: #1976d2; margin: 0 0 10px 0; display: flex; align-items: center;">
                {selected_option["icon"]} {selected_option["title"]}
            </h4>
            <p style="color: #1976d2; margin: 0 0 10px 0;">
                {selected_option["description"]}
            </p>
            <div style="display: flex; flex-wrap: wrap; gap: 8px;">
        """,
            unsafe_allow_html=True,
        )

        for feature in selected_option["features"]:
            st.markdown(
                f"""
            <span style="background: #bbdefb; color: #1976d2; padding: 4px 8px;
                        border-radius: 12px; font-size: 11px;">
                ✓ {feature}
            </span>
            """,
                unsafe_allow_html=True,
            )

        st.markdown("</div></div>", unsafe_allow_html=True)

        # Continue button
        if st.button(
            "Continue to Audio Input ➡️", type="primary", use_container_width=True
        ):
            st.session_state.current_step = "input"
            st.rerun()


if __name__ == "__main__":
    main()
