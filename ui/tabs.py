# ui/tabs.py
import streamlit as st
import json
# Services are initialized in session state from main.py
from utils.audio_processor import process_audio_and_chunk
from utils.ui_components import get_default_schema

def render_upload_tab():
    """Render the upload and transcribe tab."""
    st.header("Upload Farmer's Interview Audio")
    uploaded_file = st.file_uploader(
        "Supported formats: WAV, MP3, M4A, FLAC",
        type=["wav", "mp3", "m4a", "flac"],
        label_visibility="collapsed",
        key="audio_uploader",
    )
    if uploaded_file:
        st.audio(uploaded_file, format=uploaded_file.type)
        
        # Transcription options
        use_chunks = st.checkbox("Use chunked transcription (Real-time dashboard)", value=True)
        
        if st.button(
            "Start Transcription", type="primary", key="start_transcription_btn"
        ):
            st.session_state.transcript = None
            st.session_state.gemini_result = None
            st.session_state.performance_metrics = None
            st.session_state.edited_transcript = None
            
            if use_chunks:
                # Use chunked transcription with real-time dashboard
                audio_chunks = process_audio_and_chunk(uploaded_file)
                if audio_chunks:
                    transcript = (
                        st.session_state.transcription_service.transcribe_chunks(
                            audio_chunks
                        )
                    )
                else:
                    st.error("Failed to process audio chunks")
                    return
            else:
                # Use full file transcription
                transcript = (
                    st.session_state.transcription_service.transcribe_full_file(
                        uploaded_file
                    )
                )
            
            st.session_state.transcript = transcript
            st.session_state.edited_transcript = transcript
            st.success(
                "✅ Transcription complete! Please switch to the 'Review Transcript' tab to review and edit the transcript."
            )

def render_review_tab():
    """Render the review transcript tab."""
    st.header("Review & Edit Transcription Result")
    if st.session_state.get("performance_metrics"):
        metrics = st.session_state.performance_metrics
        m_col1, m_col2 = st.columns(2)
        m_col1.metric("Total Time", f"{metrics['total_time']:.2f}s")
        m_col2.metric("Chunks Processed", metrics["chunks_processed"])
        
    if st.session_state.get("transcript") is not None:
        # Editable text area for transcript
        edited = st.text_area(
            "Edit Transcript (Save your changes before proceeding):",
            value=st.session_state.get("edited_transcript") or st.session_state.get("transcript"),
            height=300,
            key="transcript_editor",
        )
        # Save button
        if st.button("💾 Save Edited Transcript", key="save_edited_transcript_btn"):
            st.session_state.edited_transcript = edited
            st.success(
                "Transcript saved! Now you can generate the payload using the edited transcript."
            )
        st.download_button(
            label="📥 Download Transcript",
            data=st.session_state.get("edited_transcript") or st.session_state.get("transcript"),
            file_name="transcript.txt",
            mime="text/plain",
        )
    else:
        st.info(
            "Please upload and transcribe a file in the first tab to see the result here."
        )

def render_payload_tab():
    """Render the generate survey payload tab."""
    st.header("Generate JSON Payload from Transcript")
    # Use the edited transcript if available, else the original
    transcript_to_use = (
        st.session_state.get("edited_transcript") or st.session_state.get("transcript")
    )
    if transcript_to_use:
        st.subheader("1. Define Your Survey Schema")
        default_schema = get_default_schema()
        schema_input = st.text_area(
            "Enter your desired JSON schema here:",
            value=json.dumps(default_schema, indent=2),
            height=250,
            key="schema_input",
        )

        st.subheader("2. Generate Payload")
        if st.button(
            "Generate Survey Payload", type="primary", key="generate_payload_btn"
        ):
            try:
                json.loads(schema_input)  # Validate schema before sending
                st.session_state.gemini_result = (
                    st.session_state.gemini_service.generate_json_payload(
                        schema_input, transcript_to_use
                    )
                )
            except json.JSONDecodeError:
                st.error("Invalid JSON schema provided. Please correct it.")

        if st.session_state.get("gemini_result"):
            st.subheader("Generated Payload:")
            st.json(st.session_state.gemini_result)

            # Display extra details
            # display_extra_details(st.session_state.gemini_result)

            # Download button for the JSON result
            st.download_button(
                label="📥 Download JSON Payload",
                data=json.dumps(
                    st.session_state.gemini_result, indent=2, ensure_ascii=False
                ),
                file_name="farmer_survey_payload.json",
                mime="application/json",
            )
    else:
        st.info(
            "A transcript is required for AI analysis. Please complete the transcription first."
        )