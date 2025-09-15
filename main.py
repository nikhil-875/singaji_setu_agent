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
    """Render the import audio workflow with clean UI."""
    with st.container():
        # Header card
        st.markdown("""
        <div style="background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
                    padding: 20px; border-radius: 10px; margin-bottom: 20px;">
            <h3 style="color: white; margin: 0; display: flex; align-items: center;">
                📁 Import Audio File
            </h3>
            <p style="color: #fce4ec; margin: 5px 0 0 0; font-size: 14px;">
                Upload existing audio recordings for processing
            </p>
        </div>
        """, unsafe_allow_html=True)

        # Upload section
        uploaded_file = st.file_uploader(
            "Choose audio file (WAV, MP3, M4A, FLAC)",
            type=["wav", "mp3", "m4a", "flac"],
            label_visibility="collapsed",
            key="audio_uploader",
        )

        if uploaded_file:
            # File preview card
            st.markdown("""
            <div style="background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 8px;
                        padding: 15px; margin: 15px 0;">
                <h4 style="color: #495057; margin: 0 0 10px 0;">📄 File Selected</h4>
            </div>
            """, unsafe_allow_html=True)

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
                st.metric("🎵 Format", uploaded_file.type.split('/')[-1].upper())

            # Process button
            if st.button("✅ **Process Audio**", type="primary", use_container_width=True):
                with st.spinner("🔄 Processing audio file..."):
                    try:
                        # Convert uploaded file to AudioSegment
                        audio_buffer = pydub.AudioSegment.from_file(uploaded_file)
                        st.session_state.audio_buffer = audio_buffer

                        # Success message
                        st.markdown("""
                        <div style="background: #d4edda; border: 1px solid #c3e6cb; border-radius: 8px;
                                    padding: 15px; margin: 20px 0;">
                            <h4 style="color: #155724; margin: 0;">✅ Audio Processed Successfully!</h4>
                            <p style="color: #155724; margin: 5px 0 0 0;">
                                Your audio is ready for transcription. Continue to the next step below.
                            </p>
                        </div>
                        """, unsafe_allow_html=True)
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Failed to process audio file: {e}")


def render_transcription_section():
    """Render the transcription section with clean UI."""
    with st.container():
        # Header card
        st.markdown("""
        <div style="background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
                    padding: 20px; border-radius: 10px; margin: 20px 0;">
            <h3 style="color: white; margin: 0; display: flex; align-items: center;">
                🎯 Step 2: Audio Transcription
            </h3>
            <p style="color: #e3f2fd; margin: 5px 0 0 0; font-size: 14px;">
                Convert your audio recording to text using AI
            </p>
        </div>
        """, unsafe_allow_html=True)

        audio_buffer = st.session_state.get("audio_buffer", pydub.AudioSegment.empty())

        if len(audio_buffer) == 0:
            st.markdown("""
            <div style="background: #fff3cd; border: 1px solid #ffeaa7; border-radius: 8px;
                        padding: 15px; text-align: center;">
                <h4 style="color: #856404; margin: 0;">⏳ Waiting for Audio</h4>
                <p style="color: #856404; margin: 5px 0 0 0;">
                    Please complete Step 1 first by recording or importing audio.
                </p>
            </div>
            """, unsafe_allow_html=True)
            return

        if not st.session_state.get("transcription_service"):
            st.markdown("""
            <div style="background: #f8d7da; border: 1px solid #f5c6cb; border-radius: 8px;
                        padding: 15px; text-align: center;">
                <h4 style="color: #721c24; margin: 0;">❌ Service Unavailable</h4>
                <p style="color: #721c24; margin: 5px 0 0 0;">
                    Transcription service not available. Please check your GCP credentials.
                </p>
            </div>
            """, unsafe_allow_html=True)
            return

        # Transcription status and controls
        if st.session_state.get("transcript") is None:
            # Ready to transcribe
            st.markdown("""
            <div style="background: #e3f2fd; border: 1px solid #bbdefb; border-radius: 8px;
                        padding: 15px; margin: 15px 0;">
                <h4 style="color: #1976d2; margin: 0 0 10px 0;">🤖 Ready to Transcribe</h4>
                <p style="color: #1976d2; margin: 0;">
                    Your audio is ready for transcription. This process may take 2-5 minutes.
                </p>
            </div>
            """, unsafe_allow_html=True)

            if st.button("🎙️ **Start Transcription**", type="primary", use_container_width=True):
                with st.spinner("🤖 Transcribing audio... This may take a few minutes."):
                    transcript = process_transcription(audio_buffer)
                    if transcript:
                        st.session_state.transcript = transcript
                        st.session_state.edited_transcript = transcript
                        st.success("✅ **Transcription complete!**")
                        st.rerun()
        else:
            # Transcription complete
            st.markdown("""
            <div style="background: #d4edda; border: 1px solid #c3e6cb; border-radius: 8px;
                        padding: 15px; margin: 15px 0;">
                <h4 style="color: #155724; margin: 0;">✅ Transcription Complete!</h4>
                <p style="color: #155724; margin: 5px 0 0 0;">
                    Your audio has been successfully converted to text. Review and edit if needed.
                </p>
            </div>
            """, unsafe_allow_html=True)

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
                if st.button("🔄 Transcribe Again", type="secondary", use_container_width=True):
                    st.session_state.transcript = None
                    st.session_state.edited_transcript = None
                    st.session_state.gemini_result = None
                    st.rerun()


def render_analysis_section():
    """Render the AI analysis section with clean UI."""
    with st.container():
        # Header card
        st.markdown("""
        <div style="background: linear-gradient(135deg, #a8edea 0%, #fed6e3 100%);
                    padding: 20px; border-radius: 10px; margin: 20px 0;">
            <h3 style="color: #2c3e50; margin: 0; display: flex; align-items: center;">
                📊 Step 3: AI Analysis & Survey Generation
            </h3>
            <p style="color: #34495e; margin: 5px 0 0 0; font-size: 14px;">
                Extract structured survey data from your transcript using AI
            </p>
        </div>
        """, unsafe_allow_html=True)

        transcript = st.session_state.get("edited_transcript") or st.session_state.get(
            "transcript"
        )

        if not transcript:
            st.markdown("""
            <div style="background: #fff3cd; border: 1px solid #ffeaa7; border-radius: 8px;
                        padding: 15px; text-align: center;">
                <h4 style="color: #856404; margin: 0;">⏳ Waiting for Transcript</h4>
                <p style="color: #856404; margin: 5px 0 0 0;">
                    Please complete Step 2 first by transcribing your audio.
                </p>
            </div>
            """, unsafe_allow_html=True)
            return

        if not st.session_state.get("gemini_service"):
            st.markdown("""
            <div style="background: #f8d7da; border: 1px solid #f5c6cb; border-radius: 8px;
                        padding: 15px; text-align: center;">
                <h4 style="color: #721c24; margin: 0;">❌ Service Unavailable</h4>
                <p style="color: #721c24; margin: 5px 0 0 0;">
                    Gemini service not available. Please check your API credentials.
                </p>
            </div>
            """, unsafe_allow_html=True)
            return

        if st.session_state.get("gemini_result") is None:
            # Ready to analyze
            st.markdown("""
            <div style="background: #e8f5e8; border: 1px solid #c8e6c9; border-radius: 8px;
                        padding: 15px; margin: 15px 0;">
                <h4 style="color: #2e7d32; margin: 0 0 10px 0;">🤖 Ready for AI Analysis</h4>
                <p style="color: #2e7d32; margin: 0 0 15px 0;">
                    Your transcript is ready for AI-powered analysis. This will extract structured survey data.
                </p>
            </div>
            """, unsafe_allow_html=True)

            # Info cards
            info_col1, info_col2 = st.columns(2)
            with info_col1:
                st.markdown("""
                <div style="background: #f3e5f5; border: 1px solid #ce93d8; border-radius: 8px;
                            padding: 15px; height: 100%;">
                    <h5 style="color: #4a148c; margin: 0 0 10px 0;">🔍 What it analyzes:</h5>
                    <ul style="color: #4a148c; margin: 0; padding-left: 20px;">
                        <li>Farmer details & demographics</li>
                        <li>Farm characteristics</li>
                        <li>Crop information</li>
                        <li>Challenges & needs</li>
                    </ul>
                </div>
                """, unsafe_allow_html=True)

            with info_col2:
                st.markdown("""
                <div style="background: #e3f2fd; border: 1px solid #90caf9; border-radius: 8px;
                            padding: 15px; height: 100%;">
                    <h5 style="color: #1565c0; margin: 0 0 10px 0;">📋 Output format:</h5>
                    <ul style="color: #1565c0; margin: 0; padding-left: 20px;">
                        <li>Structured JSON data</li>
                        <li>Database-ready format</li>
                        <li>Survey-complete records</li>
                        <li>Ready for analysis</li>
                    </ul>
                </div>
                """, unsafe_allow_html=True)

            if st.button("🚀 **Generate Survey Payload**", type="primary", use_container_width=True):
                with st.spinner("🤖 Analyzing transcript and generating structured data..."):
                    gemini_result = generate_survey_payload(transcript)
                    if gemini_result:
                        st.session_state.gemini_result = gemini_result
                        st.success("✅ **Analysis complete!**")
                        st.rerun()
        else:
            # Analysis complete
            st.markdown("""
            <div style="background: #d4edda; border: 1px solid #c3e6cb; border-radius: 8px;
                        padding: 15px; margin: 15px 0;">
                <h4 style="color: #155724; margin: 0;">✅ AI Analysis Complete!</h4>
                <p style="color: #155724; margin: 5px 0 0 0;">
                    Your transcript has been successfully analyzed and structured survey data has been generated.
                </p>
            </div>
            """, unsafe_allow_html=True)

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
                if st.button("🔄 Analyze Again", type="secondary", use_container_width=True):
                    st.session_state.gemini_result = None
                    st.rerun()


def render_export_section():
    """Render the export section with clean UI."""
    with st.container():
        # Header card
        st.markdown("""
        <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    padding: 20px; border-radius: 10px; margin: 20px 0;">
            <h3 style="color: white; margin: 0; display: flex; align-items: center;">
                📤 Step 4: Export & Summary
            </h3>
            <p style="color: #e8eaf6; margin: 5px 0 0 0; font-size: 14px;">
                Download your processed data and view a complete summary
            </p>
        </div>
        """, unsafe_allow_html=True)

        audio_buffer = st.session_state.get("audio_buffer", pydub.AudioSegment.empty())
        transcript = st.session_state.get("edited_transcript") or st.session_state.get(
            "transcript"
        )
        payload = st.session_state.get("gemini_result")

        # Progress indicators with better styling
        progress_col1, progress_col2, progress_col3 = st.columns(3)

        with progress_col1:
            if len(audio_buffer) > 0:
                st.markdown("""
                <div style="background: #d4edda; border: 1px solid #c3e6cb; border-radius: 8px;
                            padding: 10px; text-align: center; margin-bottom: 10px;">
                    <div style="color: #155724; font-size: 24px;">✅</div>
                    <div style="color: #155724; font-size: 12px; font-weight: bold;">Audio Ready</div>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown("""
                <div style="background: #f8d7da; border: 1px solid #f5c6cb; border-radius: 8px;
                            padding: 10px; text-align: center; margin-bottom: 10px;">
                    <div style="color: #721c24; font-size: 24px;">❌</div>
                    <div style="color: #721c24; font-size: 12px; font-weight: bold;">No Audio</div>
                </div>
                """, unsafe_allow_html=True)

        with progress_col2:
            if transcript:
                st.markdown("""
                <div style="background: #d4edda; border: 1px solid #c3e6cb; border-radius: 8px;
                            padding: 10px; text-align: center; margin-bottom: 10px;">
                    <div style="color: #155724; font-size: 24px;">✅</div>
                    <div style="color: #155724; font-size: 12px; font-weight: bold;">Transcript Ready</div>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown("""
                <div style="background: #f8d7da; border: 1px solid #f5c6cb; border-radius: 8px;
                            padding: 10px; text-align: center; margin-bottom: 10px;">
                    <div style="color: #721c24; font-size: 24px;">❌</div>
                    <div style="color: #721c24; font-size: 12px; font-weight: bold;">No Transcript</div>
                </div>
                """, unsafe_allow_html=True)

        with progress_col3:
            if payload:
                st.markdown("""
                <div style="background: #d4edda; border: 1px solid #c3e6cb; border-radius: 8px;
                            padding: 10px; text-align: center; margin-bottom: 10px;">
                    <div style="color: #155724; font-size: 24px;">✅</div>
                    <div style="color: #155724; font-size: 12px; font-weight: bold;">Survey Data Ready</div>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown("""
                <div style="background: #f8d7da; border: 1px solid #f5c6cb; border-radius: 8px;
                            padding: 10px; text-align: center; margin-bottom: 10px;">
                    <div style="color: #721c24; font-size: 24px;">❌</div>
                    <div style="color: #721c24; font-size: 12px; font-weight: bold;">No Survey Data</div>
                </div>
                """, unsafe_allow_html=True)

        if audio_buffer and transcript and payload:
            # Success celebration
            st.markdown("""
            <div style="background: linear-gradient(135deg, #ff9a9e 0%, #fecfef 100%, #fecfef 100%);
                        border: 2px solid #ff6b9d; border-radius: 12px; padding: 20px; margin: 20px 0;
                        text-align: center; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                <h2 style="color: white; margin: 0 0 10px 0; font-size: 28px;">🎉 Processing Complete!</h2>
                <p style="color: white; margin: 0; font-size: 16px;">
                    Your farmer interview has been fully processed. All data is ready for export!
                </p>
            </div>
            """, unsafe_allow_html=True)

            # Summary display in a nice card
            with st.expander("📋 **Complete Summary**", expanded=True):
                summary_col1, summary_col2 = st.columns(2)

                with summary_col1:
                    farmer_name = payload.get("farmerDetails", {}).get("farmerName", "Unknown")
                    village = payload.get("farmerDetails", {}).get("village", "Unknown")
                    contact = payload.get("farmerDetails", {}).get("contactNumber", "Not provided")

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
                st.markdown("""
                <div style="background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 8px;
                            padding: 15px; text-align: center; margin-bottom: 10px;">
                    <div style="font-size: 24px; margin-bottom: 5px;">🎵</div>
                    <div style="font-size: 12px; color: #6c757d; margin-bottom: 10px;">Audio Recording</div>
                </div>
                """, unsafe_allow_html=True)
                audio_bytes = audio_buffer.export(format="wav").read()
                st.download_button(
                    label="📁 Download Audio",
                    data=audio_bytes,
                    file_name=f"farmer_interview_{int(time.time())}.wav",
                    mime="audio/wav",
                    use_container_width=True,
                )

            with export_col2:
                st.markdown("""
                <div style="background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 8px;
                            padding: 15px; text-align: center; margin-bottom: 10px;">
                    <div style="font-size: 24px; margin-bottom: 5px;">📄</div>
                    <div style="font-size: 12px; color: #6c757d; margin-bottom: 10px;">Text Transcript</div>
                </div>
                """, unsafe_allow_html=True)
                st.download_button(
                    label="📄 Download Transcript",
                    data=transcript,
                    file_name=f"farmer_transcript_{int(time.time())}.txt",
                    mime="text/plain",
                    use_container_width=True,
                )

            with export_col3:
                st.markdown("""
                <div style="background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 8px;
                            padding: 15px; text-align: center; margin-bottom: 10px;">
                    <div style="font-size: 24px; margin-bottom: 5px;">📊</div>
                    <div style="font-size: 12px; color: #6c757d; margin-bottom: 10px;">Survey JSON</div>
                </div>
                """, unsafe_allow_html=True)
                st.download_button(
                    label="📊 Download Survey Data",
                    data=json.dumps(payload, indent=2, ensure_ascii=False),
                    file_name=f"farmer_complete_{int(time.time())}.json",
                    mime="application/json",
                    use_container_width=True,
                )
        else:
            # Incomplete processing warning
            st.markdown("""
            <div style="background: #fff3cd; border: 1px solid #ffeaa7; border-radius: 8px;
                        padding: 15px; text-align: center; margin: 20px 0;">
                <h4 style="color: #856404; margin: 0;">⚠️ Processing Incomplete</h4>
                <p style="color: #856404; margin: 5px 0 0 0;">
                    Please complete all previous steps before exporting your data.
                </p>
            </div>
            """, unsafe_allow_html=True)


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

    # Application header with improved design
    st.markdown("""
    <div style="text-align: center; margin-bottom: 30px;">
        <h1 style="color: #2c3e50; margin-bottom: 10px; font-size: 2.5em;">
            🌾 Singaji Setu Agent
        </h1>
        <p style="color: #7f8c8d; font-size: 1.2em; margin: 0;">
            Intelligent processing of farmer interview surveys from audio recordings
        </p>
    </div>
    """, unsafe_allow_html=True)

    # Initialize session state
    initialize_session_state()

    # Workflow selection with better design
    st.markdown("""
    <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                padding: 25px; border-radius: 12px; margin: 20px 0; text-align: center;">
        <h3 style="color: white; margin: 0 0 15px 0; font-size: 1.5em;">
            🚀 Choose Your Workflow
        </h3>
        <p style="color: #e8eaf6; margin: 0; font-size: 14px;">
            Select how you'd like to provide your farmer interview audio
        </p>
    </div>
    """, unsafe_allow_html=True)

    workflow = st.radio(
        "",
        ["🎙️ Live Record Interview", "📁 Import Audio File"],
        horizontal=True,
        label_visibility="collapsed",
        key="workflow_selector",
    )

    # Add spacing
    st.markdown("<br>", unsafe_allow_html=True)

    # Render workflow-specific section
    if "Live Record" in workflow:
        render_live_record_workflow()
    else:
        render_import_audio_workflow()

    # Shared processing sections with clear separators
    st.markdown("""
    <hr style="border: none; height: 2px; background: linear-gradient(90deg, #667eea, #764ba2);
                margin: 40px 0; border-radius: 1px;">
    """, unsafe_allow_html=True)

    render_transcription_section()

    st.markdown("""
    <hr style="border: none; height: 2px; background: linear-gradient(90deg, #a8edea, #fed6e3);
                margin: 40px 0; border-radius: 1px;">
    """, unsafe_allow_html=True)

    render_analysis_section()

    st.markdown("""
    <hr style="border: none; height: 2px; background: linear-gradient(90deg, #667eea, #764ba2);
                margin: 40px 0; border-radius: 1px;">
    """, unsafe_allow_html=True)

    render_export_section()


if __name__ == "__main__":
    main()
