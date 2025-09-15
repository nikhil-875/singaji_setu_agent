# ui/live_tab.py

import streamlit as st
import time
import queue
import threading
import pydub
from streamlit_webrtc import webrtc_streamer, WebRtcMode
from services.streaming_transcription_service import stream_audio_to_google
from utils.live_recorder import AudioRecorder


def render_live_tab():
    """Renders a stable audio recording and transcription tab."""
    st.header("Live Microphone Transcription")

    # Initialize recorder and transcription-related session state
    if "recorder" not in st.session_state:
        st.session_state.recorder = AudioRecorder()
    if "transcription_queue" not in st.session_state:
        st.session_state.transcription_queue = queue.Queue()
    if "transcription_results_queue" not in st.session_state:
        st.session_state.transcription_results_queue = queue.Queue()

    recorder: AudioRecorder = st.session_state.recorder
    transcription_queue = st.session_state.transcription_queue
    transcription_results_queue = st.session_state.transcription_results_queue

    # --- Transcription Callback and Thread Management ---
    def transcription_update_callback(transcript_piece, is_final):
        """Thread-safe callback that puts transcription results in a queue."""
        try:
            # Put transcription result in thread-safe queue
            transcription_results_queue.put({
                'transcript': transcript_piece,
                'is_final': is_final,
                'timestamp': time.time()
            })
        except Exception as e:
            print(f"Error in transcription callback: {e}")

    def start_transcription_thread():
        # Clear any previous transcripts
        st.session_state.final_transcript = ""
        st.session_state.interim_transcript = ""
        # Clear the results queue
        while not transcription_results_queue.empty():
            try:
                transcription_results_queue.get_nowait()
            except queue.Empty:
                break

        # Start the thread
        st.session_state.transcription_thread = threading.Thread(
            target=stream_audio_to_google,
            args=(transcription_queue, transcription_update_callback),
            daemon=True,
        )
        st.session_state.transcription_thread.start()

    # --- WebRTC Component ---
    # WebRTC configuration using modern API (matching working app.py)
    RTC_CONFIGURATION = {"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]}

    webrtc_ctx = webrtc_streamer(
        key="live-transcription-recorder",
        mode=WebRtcMode.SENDONLY,
        audio_receiver_size=1024,
        rtc_configuration=RTC_CONFIGURATION,  # ✅ Modern API
        media_stream_constraints={  # ✅ Modern API with enhanced audio settings
            "audio": {
                "sampleRate": 16000,  # Match transcription service sample rate
                "channelCount": 1,
                "echoCancellation": True,
                "noiseSuppression": True,
            },
            "video": False,
        },
        audio_html_attrs={"muted": True},  # Prevent feedback
    )

    # --- Main Recording and UI Loop ---
    status_placeholder = st.empty()
    transcript_placeholder = st.empty()
    timer_placeholder = st.empty()

    # Recording logic with continuous audio processing loop
    while True:
        if webrtc_ctx.audio_receiver:
            if not recorder.is_recording:
                recorder.start()
                start_transcription_thread()

            status_placeholder.success("🎤 Recording...")

            try:
                # Pull audio frames from the WebRTC component
                audio_frames = webrtc_ctx.audio_receiver.get_frames(timeout=1)
            except queue.Empty:
                time.sleep(0.01)  # Small delay to prevent busy waiting
                continue
            except Exception as e:
                st.error(f"Error getting audio frames: {e}")
                time.sleep(0.1)
                continue

            # Process frames for both recording and transcription
            sound_chunk = pydub.AudioSegment.empty()
            try:
                for frame in audio_frames:
                    try:
                        # Convert frame to audio segment for recording
                        audio_data = frame.to_ndarray().tobytes()
                        sound = pydub.AudioSegment(
                            data=audio_data,
                            sample_width=frame.format.bytes,
                            frame_rate=frame.sample_rate,
                            channels=len(frame.layout.channels),
                        )
                        sound_chunk += sound

                        # Put raw frame on queue for transcription
                        transcription_queue.put(frame.to_ndarray())

                    except Exception as e:
                        st.warning(f"Error processing individual audio frame: {e}")
                        continue

                if len(sound_chunk) > 0:
                    recorder.add_chunk(sound_chunk)

            except Exception as e:
                st.error(f"Error processing audio frames: {e}")
                time.sleep(0.1)
                continue
        else:
            if recorder.is_recording:
                recorder.stop()
                transcription_queue.put(None)  # Signal transcription thread to end
                st.rerun()

            status_placeholder.info("🔴 Click START to begin recording and transcription.")
            break

    # Process transcription results from the queue (thread-safe)
    try:
        while not transcription_results_queue.empty():
            result = transcription_results_queue.get_nowait()
            transcript_piece = result['transcript']
            is_final = result['is_final']

            if is_final:
                st.session_state.final_transcript += transcript_piece + " "
                st.session_state.interim_transcript = ""
            else:
                st.session_state.interim_transcript = transcript_piece
    except queue.Empty:
        pass

    # Update timer and transcript display
    duration = recorder.duration_seconds
    timer_placeholder.metric(
        "Duration", f"{int(duration // 60):02d}:{int(duration % 60):02d}"
    )

    # Enhanced transcript display with better user feedback
    final_transcript = st.session_state.get("final_transcript", "")
    interim_transcript = st.session_state.get("interim_transcript", "")

    # Show transcription status
    if recorder.is_recording:
        if not final_transcript and not interim_transcript:
            transcript_text = "🎧 Listening... (Start speaking to see transcription)"
        elif interim_transcript:
            transcript_text = final_transcript + interim_transcript + " ..."
        else:
            transcript_text = final_transcript + "🎙️ (Continue speaking...)"
    else:
        if final_transcript:
            transcript_text = final_transcript
        else:
            transcript_text = "No transcription available"

    transcript_placeholder.text_area(
        "Live Transcript",
        transcript_text,
        height=200,
        disabled=True
    )

    # Show transcription statistics
    if recorder.is_recording:
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Recording Status", "Active", "🔴")
        with col2:
            transcript_length = len((final_transcript + interim_transcript).strip())
            st.metric("Transcript Length", f"{transcript_length} chars")

    # Display playback/download options after stopping
    if not recorder.is_recording and recorder.duration_seconds > 0:
        st.markdown("---")
        st.markdown("### Recording Complete")

        audio_buffer = recorder.export_as_wav()
        if audio_buffer:
            st.audio(audio_buffer)
            st.download_button(
                label="Download as WAV",
                data=audio_buffer,
                file_name=f"recording_{int(time.time())}.wav",
                mime="audio/wav",
            )
