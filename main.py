import streamlit as st

# Import services
from services.transcription_service import TranscriptionService
from services.gemini_service import GeminiService

# Import UI components
from ui.tabs import render_upload_tab, render_review_tab, render_payload_tab

# Import utilities
from utils.ui_components import apply_custom_styling

# Import configuration
from config.settings import APP_TITLE, APP_ICON, APP_LAYOUT


def initialize_session_state():
    """Initialize all session state variables."""
    if "transcription_service" not in st.session_state:
        st.session_state.transcription_service = TranscriptionService()
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
    ]
    tab1, tab2, tab3 = st.tabs(tab_labels)

    # Render tab content
    with tab1:
        render_upload_tab()

    with tab2:
        render_review_tab()

    with tab3:
        render_payload_tab()


if __name__ == "__main__":
    main()
