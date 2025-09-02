import streamlit as st
import io
from pydub import AudioSegment
from typing import List, Tuple, Optional

# Constants
MAX_SYNC_DURATION_SECONDS = 59

def process_audio_and_chunk(
    uploaded_file: io.BytesIO,
    chunk_length_seconds: int = MAX_SYNC_DURATION_SECONDS,
) -> Optional[List[Tuple[io.BytesIO, str]]]:
    """
    Process audio file and split it into chunks for transcription.
    
    Args:
        uploaded_file: The uploaded audio file
        chunk_length_seconds: Length of each chunk in seconds (default: 59)
        
    Returns:
        List of tuples containing (chunk_buffer, time_label) or None if processing fails
    """
    try:
        st.info("🔄 Processing and chunking audio file...")
        audio = AudioSegment.from_file(uploaded_file).set_channels(1)
        chunk_length_ms = chunk_length_seconds * 1000
        chunks = [
            audio[i : i + chunk_length_ms]
            for i in range(0, len(audio), chunk_length_ms)
        ]
        chunk_data = []
        for i, chunk in enumerate(chunks):
            start_time_s = (i * chunk_length_ms) / 1000
            end_time_s = start_time_s + (len(chunk) / 1000)
            time_label = f"{start_time_s:.1f}s - {end_time_s:.1f}s"
            buffer = io.BytesIO()
            chunk.export(buffer, format="wav")
            buffer.seek(0)
            chunk_data.append((buffer, time_label))
        st.success(f"✅ Audio split into {len(chunks)} chunks of {chunk_length_seconds}s each.")
        return chunk_data
    except Exception as e:
        st.error(f"Audio processing error: {e}")
        return None
