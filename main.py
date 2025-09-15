import streamlit as st

# Import services
from services.transcription_service import TranscriptionService
from services.gemini_service import GeminiService

# main.py - Add these imports

# Import UI components
from ui.tabs import render_upload_tab, render_review_tab, render_payload_tab
from ui.live_tab import render_live_tab

# Import utilities
from utils.ui_components import apply_custom_styling

# Import configuration
from config.settings import APP_TITLE, APP_ICON, APP_LAYOUT, GCS_BUCKET_NAME, get_gcp_project_id, GCP_LOCATION, validate_environment


def initialize_session_state():
    """Initialize all session state variables."""
    # Validate environment variables first
    if not validate_environment():
        st.error("❌ Environment validation failed. Please check the console for missing variables.")
        st.stop()
    
    if "transcription_service" not in st.session_state:
        # Get GCP project ID from environment or service account
        project_id = get_gcp_project_id()
        if not project_id:
            st.error("❌ GCP Project ID not found. Please set GCP_PROJECT_ID environment variable or check service account credentials.")
            st.session_state.transcription_service = None
        else:
            st.session_state.transcription_service = TranscriptionService(
                gcs_bucket_name=GCS_BUCKET_NAME,
                gcp_project_id=project_id,
                gcp_location=GCP_LOCATION
            )
    if "gemini_service" not in st.session_state:
        st.session_state.gemini_service = GeminiService()
    if "transcript" not in st.session_state:
        st.session_state.transcript = None
    if "gemini_result" not in st.session_state:
        st.session_state.gemini_result = None
    if "performance_metrics" not in st.session_state:
        st.session_state.performance_metrics = None
    if "edited_transcript" not in st.session_state:
        st.session_state.edited_transcript = None


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

    # Create tabs
    tab_labels = [
        "**1. Upload & Transcribe** 🎙️",
        "**2. Review Transcript** 📜",
        "**3. Generate Survey Payload** 🤖",
        "**4. Live Transcription (Beta)** 🔴",
    ]
    tab1, tab2, tab3, tab4 = st.tabs(tab_labels)

    # Render tab content
    with tab1:
        render_upload_tab()

    with tab2:
        render_review_tab()

    with tab3:
        render_payload_tab()

    with tab4:
        render_live_tab()


if __name__ == "__main__":
    main()
