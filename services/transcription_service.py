# services/transcription_service.py
import streamlit as st
import os
import time
import uuid
from io import BytesIO
from google.cloud import speech_v1p1beta1 as speech
from google.cloud import storage
from google.api_core.client_options import ClientOptions
from typing import Optional
from config.settings import get_service_account_credentials


class TranscriptionService:
    """
    Handles audio transcription using Google Cloud Speech-to-Text v1p1beta1
    with real-time dashboard.
    """

    def __init__(self, gcs_bucket_name: str, gcp_project_id: str, gcp_location: str):
        self.creds_path = get_service_account_credentials()
        self.gcs_bucket_name = gcs_bucket_name
        self.project_id = gcp_project_id
        self.location = gcp_location

        if not self.creds_path:
            st.error("❌ Google Cloud credentials not set.")
            self.speech_client = None
            self.storage_client = None
            return

        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = self.creds_path

        try:
            # Initialize v1p1beta1 client
            self.speech_client = speech.SpeechClient()
            self.storage_client = storage.Client()
            self._ensure_bucket_exists()
        except Exception as e:
            st.error(f"❌ Failed to initialize clients: {e}")
            self.speech_client = None
            self.storage_client = None

    def _ensure_bucket_exists(self):
        """Ensure the GCS bucket exists, create it if it doesn't."""
        try:
            bucket = self.storage_client.bucket(self.gcs_bucket_name)
            if not bucket.exists():
                st.info(f"🪣 Creating GCS bucket: {self.gcs_bucket_name}")
                bucket = self.storage_client.create_bucket(
                    self.gcs_bucket_name, location=self.location
                )
                st.success(f"✅ Created GCS bucket: {self.gcs_bucket_name}")
        except Exception as e:
            st.warning(f"⚠️ Could not verify/create GCS bucket: {e}")
            st.info("You may need to create the bucket manually or check permissions.")

    def _upload_to_gcs(self, audio_bytes: BytesIO, destination_blob_name: str) -> str:
        """Uploads audio data to a GCS bucket and returns the GCS URI."""
        try:
            bucket = self.storage_client.bucket(self.gcs_bucket_name)
            blob = bucket.blob(destination_blob_name)
            audio_bytes.seek(0)
            blob.upload_from_file(audio_bytes, content_type="audio/wav")
            return f"gs://{self.gcs_bucket_name}/{destination_blob_name}"
        except Exception as e:
            st.error(f"GCS Upload Failed: {e}")
            raise

    def transcribe_chunks(
        self, audio_chunks: list[tuple], language_code: str = "hi-IN"
    ) -> Optional[str]:
        """
        Transcribes audio chunks with real-time dashboard.
        """
        if not self.speech_client or not self.storage_client:
            st.error("Clients not initialized. Cannot transcribe.")
            return None

        full_transcript_parts = []
        live_dashboard = st.empty()
        start_time = time.time()

        try:
            for i, (chunk_buffer, time_label) in enumerate(audio_chunks):
                # Upload chunk to GCS for processing
                unique_filename = f"chunk-{uuid.uuid4()}.wav"
                try:
                    gcs_uri = self._upload_to_gcs(chunk_buffer, unique_filename)
                except Exception as e:
                    st.warning(f"Failed to upload chunk {i + 1}: {e}")
                    continue

                # Configure transcription for this chunk
                config = speech.RecognitionConfig(
                    language_code=language_code,
                    enable_automatic_punctuation=True,
                    model="telephony",
                )

                audio = speech.RecognitionAudio(uri=gcs_uri)

                # Process chunk
                try:
                    operation = self.speech_client.long_running_recognize(
                        config=config, audio=audio
                    )
                    response = operation.result()

                    # Extract transcript
                    chunk_transcript = ""
                    if response.results:
                        chunk_transcript = " ".join(
                            result.alternatives[0].transcript
                            for result in response.results
                        )

                    full_transcript_parts.append(chunk_transcript)

                    # Clean up the uploaded chunk
                    try:
                        bucket = self.storage_client.bucket(self.gcs_bucket_name)
                        blob = bucket.blob(unique_filename)
                        blob.delete()
                    except Exception:
                        pass

                except Exception as e:
                    st.warning(f"Chunk {i + 1} transcription failed: {e}")
                    full_transcript_parts.append(
                        f"[Chunk {i + 1} failed to transcribe]"
                    )

                # Update live dashboard
                elapsed_time = time.time() - start_time
                full_text_so_far = " ".join(full_transcript_parts)

                with live_dashboard.container():
                    st.subheader("🔴 Live Transcription Dashboard")
                    prog_col, time_col = st.columns(2)
                    prog_col.metric("Progress", f"{i + 1}/{len(audio_chunks)} Chunks")
                    time_col.metric("Time Elapsed", f"{elapsed_time:.1f}s")

                    st.progress((i + 1) / len(audio_chunks))

                    with st.expander("📜 View Live Transcript", expanded=True):
                        st.markdown(full_text_so_far)

                    # Show current chunk info
                    st.info(f"🎯 Processing: {time_label}")

            total_time = time.time() - start_time
            final_transcript = " ".join(full_transcript_parts)

            # Clear dashboard and show completion
            live_dashboard.empty()
            st.success(f"✅ Transcription complete in {total_time:.2f} seconds!")

            st.session_state.performance_metrics = {
                "total_time": total_time,
                "chunks_processed": len(audio_chunks),
            }

            return final_transcript

        except Exception as e:
            st.error(f"Transcription failed: {e}")
            return " ".join(full_transcript_parts) if full_transcript_parts else None

    def transcribe_full_file(
        self, uploaded_file, language_code: str = "hi-IN"
    ) -> Optional[str]:
        """
        Transcribes a full uploaded file directly.
        """
        if not self.speech_client or not self.storage_client:
            st.error("Clients not initialized. Cannot transcribe.")
            return None

        # Upload the full file directly
        unique_filename = f"interview-audio-{uuid.uuid4()}.wav"
        try:
            # Convert uploaded file to BytesIO if needed
            if hasattr(uploaded_file, "read"):
                file_buffer = BytesIO(uploaded_file.read())
            else:
                file_buffer = uploaded_file

            gcs_uri = self._upload_to_gcs(file_buffer, unique_filename)
        except Exception as e:
            st.error(f"Failed to upload file: {e}")
            return None

        # Configure transcription
        config = speech.RecognitionConfig(
            language_code=language_code,
            enable_automatic_punctuation=True,
            model="telephony",
        )

        audio = speech.RecognitionAudio(uri=gcs_uri)

        start_time = time.time()
        with st.spinner(
            "🤖 AI is analyzing the interview... This may take a few minutes for long audio."
        ):
            try:
                operation = self.speech_client.long_running_recognize(
                    config=config, audio=audio
                )
                response = operation.result()

                total_time = time.time() - start_time
                st.success(f"✅ Transcription complete in {total_time:.2f} seconds!")

                st.session_state.performance_metrics = {
                    "total_time": total_time,
                    "chunks_processed": "1 (Full File)",
                }

                # Extract transcript
                formatted_transcript = ""
                if response.results:
                    formatted_transcript = " ".join(
                        result.alternatives[0].transcript for result in response.results
                    )

                # Clean up the uploaded file
                try:
                    bucket = self.storage_client.bucket(self.gcs_bucket_name)
                    blob = bucket.blob(unique_filename)
                    blob.delete()
                except Exception as e:
                    st.warning(
                        f"Could not delete GCS file gs://{self.gcs_bucket_name}/{unique_filename}. Manual cleanup may be required. Error: {e}"
                    )

                return formatted_transcript

            except Exception as e:
                st.error(f"Transcription failed: {e}")
                return None
