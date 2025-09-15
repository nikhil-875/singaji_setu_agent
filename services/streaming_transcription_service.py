# services/streaming_transcription_service.py

import os
import numpy as np
from typing import Callable
from google.cloud import speech
from config.settings import get_service_account_credentials

SAMPLE_RATE = 16000


def _ensure_creds():
    creds_path = get_service_account_credentials()
    if creds_path:
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = creds_path


def _ndarray_to_linear16_bytes(audio_ndarray: np.ndarray) -> bytes:
    """Convert audio ndarray to LINEAR16 bytes format."""
    if audio_ndarray.ndim > 1:
        audio_ndarray = audio_ndarray.mean(axis=1)

    if np.issubdtype(audio_ndarray.dtype, np.floating):
        audio_ndarray = (audio_ndarray * 32767).astype(np.int16)
    else:
        audio_ndarray = audio_ndarray.astype(np.int16)

    return audio_ndarray.tobytes()


def stream_audio_to_google(
    audio_queue, callback_to_update_ui: Callable[[str, bool], None]
):
    """Streams audio from a queue to Google Speech-to-Text."""
    _ensure_creds()
    client = speech.SpeechClient()

    config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
        sample_rate_hertz=SAMPLE_RATE,
        language_code="hi-IN",
        enable_automatic_punctuation=True,
        model="telephony",
    )
    streaming_config = speech.StreamingRecognitionConfig(
        config=config,
        interim_results=True,
    )

    def audio_generator(q):
        while True:
            chunk = q.get()
            if chunk is None:
                return
            try:
                audio_bytes = _ndarray_to_linear16_bytes(chunk)
                yield speech.StreamingRecognizeRequest(audio_content=audio_bytes)
            except Exception:
                continue

    try:
        responses = client.streaming_recognize(
            config=streaming_config, requests=audio_generator(audio_queue)
        )

        for response in responses:
            for result in response.results:
                if not result.alternatives:
                    continue
                transcript = result.alternatives[0].transcript
                callback_to_update_ui(transcript, result.is_final)
    except Exception as e:
        # Pass the error to the main thread to be displayed in the UI
        callback_to_update_ui(f"ERROR: {e}", True)
