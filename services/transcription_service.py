import streamlit as st
import os
import time
from google.cloud import speech
from typing import Optional
from config.settings import get_service_account_credentials

class TranscriptionService:
    """Handles audio transcription by chunking and processing sequentially."""

    def __init__(self):
        self.speech_client = self._initialize_client(speech.SpeechClient, "Speech")

    def _initialize_client(self, client_class, client_name):
        creds_path = get_service_account_credentials()
        if not creds_path:
            st.error(f"❌ Google Cloud credentials not set for {client_name} client.")
            return None
        try:
            # Set the credentials environment variable temporarily
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = creds_path
            client = client_class()
            return client
        except Exception as e:
            st.error(f"Failed to initialize Google {client_name} client: {e}")
            return None

    def transcribe_chunks(
        self, audio_chunks: list[tuple], language_code: str = "hi-IN"
    ) -> Optional[str]:
        if not self.speech_client:
            return None
        full_transcript_parts = []
        live_dashboard = st.empty()
        start_time = time.time()
        try:
            for i, (chunk_buffer, time_label) in enumerate(audio_chunks):
                config = speech.RecognitionConfig(
                    encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
                    language_code=language_code,
                    enable_automatic_punctuation=True,
                    use_enhanced=True,
                    model="telephony",
                )
                recognition_audio = speech.RecognitionAudio(
                    content=chunk_buffer.getvalue()
                )
                response = self.speech_client.recognize(
                    config=config, audio=recognition_audio
                )
                chunk_transcript = "".join(
                    result.alternatives[0].transcript for result in response.results
                )
                full_transcript_parts.append(chunk_transcript)
                elapsed_time = time.time() - start_time
                full_text_so_far = " ".join(full_transcript_parts)
                with live_dashboard.container():
                    st.subheader("🔴 Live Transcription Dashboard")
                    prog_col, time_col, _ = st.columns(3)
                    prog_col.metric("Progress", f"{i + 1}/{len(audio_chunks)} Chunks")
                    time_col.metric("Time Elapsed", f"{elapsed_time:.1f}s")
                    st.progress((i + 1) / len(audio_chunks))
                    with st.expander("📜 View Live Transcript", expanded=True):
                        st.markdown(full_text_so_far)
            total_time = time.time() - start_time
            final_transcript = " ".join(full_transcript_parts)
            live_dashboard.empty()
            st.success(f"✅ Transcription complete in {total_time:.2f} seconds!")
            st.session_state.performance_metrics = {
                "total_time": total_time,
                "chunks_processed": len(audio_chunks),
            }
            return final_transcript
        except Exception as e:
            st.error(f"Transcription failed during chunk {i + 1}: {e}")
            return " ".join(full_transcript_parts)
