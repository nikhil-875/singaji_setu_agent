# utils/live_recorder.py

import streamlit as st
import time
import pydub
import io


class AudioRecorder:
    """A class to handle audio recording using pydub, managing state and WAV file creation."""

    def __init__(self):
        self._is_recording = False
        self._audio_buffer = pydub.AudioSegment.empty()

    @property
    def is_recording(self) -> bool:
        """Returns True if the recorder is currently recording."""
        return self._is_recording

    def start(self):
        """Starts the recording session."""
        self._is_recording = True
        self._audio_buffer = pydub.AudioSegment.empty()

    def stop(self):
        """Stops the recording session."""
        self._is_recording = False

    def add_chunk(self, chunk: pydub.AudioSegment):
        """Adds an audio chunk (as a pydub.AudioSegment) to the internal buffer."""
        if self.is_recording and chunk:
            self._audio_buffer += chunk

    @property
    def duration_seconds(self) -> float:
        """Returns the current duration of the recording in seconds."""
        return self._audio_buffer.duration_seconds

    def export_as_wav(self) -> io.BytesIO | None:
        """Exports the recorded audio as a WAV file in memory."""
        if not self._audio_buffer:
            return None

        try:
            buffer = io.BytesIO()
            self._audio_buffer.export(buffer, format="wav")
            buffer.seek(0)
            return buffer
        except Exception as e:
            st.error(f"Error exporting WAV file: {e}")
            return None
