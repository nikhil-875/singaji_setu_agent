import queue
import streamlit as st
import pydub
import time
from streamlit_webrtc import webrtc_streamer, WebRtcMode


def main():
    st.title("🎙️ Complete Audio Recorder (Latest API)")

    # Initialize session state
    if "audio_buffer" not in st.session_state:
        st.session_state["audio_buffer"] = pydub.AudioSegment.empty()

    # Sidebar settings
    st.sidebar.header("Settings")
    # record_seconds = st.sidebar.slider("Auto-stop after (seconds)", 5, 60, 30)  # Removed timeout

    # WebRTC configuration using modern API
    RTC_CONFIGURATION = {"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]}

    webrtc_ctx = webrtc_streamer(
        key="complete-audio-recorder",
        mode=WebRtcMode.SENDONLY,
        audio_receiver_size=1024,
        rtc_configuration=RTC_CONFIGURATION,  # ✅ Modern API
        media_stream_constraints={  # ✅ Modern API
            "audio": {
                "sampleRate": 44100,
                "channelCount": 1,
                "echoCancellation": True,
                "noiseSuppression": True,
            },
            "video": False,
        },
        audio_html_attrs={"muted": True},  # Prevent feedback
    )

    # Create UI elements
    col1, col2 = st.columns(2)
    with col1:
        status_placeholder = st.empty()
    with col2:
        timer_placeholder = st.empty()

    # progress_bar = st.progress(0)  # Removed for continuous recording

    # Recording logic
    start_time = time.time() if webrtc_ctx.state.playing else None

    while True:
        if webrtc_ctx.audio_receiver:
            current_time = time.time()
            elapsed = current_time - (start_time or current_time)

            # Update UI
            status_placeholder.success("🎤 Recording...")
            timer_placeholder.info(f"⏱️ {elapsed:.1f}s")
            # progress_bar.progress(min(elapsed / record_seconds, 1.0))  # Removed progress bar for continuous recording

            # Continuous recording - no auto-stop

            try:
                audio_frames = webrtc_ctx.audio_receiver.get_frames(timeout=1)
            except queue.Empty:
                continue

            # Process audio frames
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
                st.session_state["audio_buffer"] += sound_chunk
        else:
            status_placeholder.info("🔴 Click START to begin recording")
            timer_placeholder.info("⏱️ 0.0s")
            break

    # Handle completed recording
    audio_buffer = st.session_state["audio_buffer"]

    if len(audio_buffer) > 0:
        st.success(
            f"🎉 Recording completed! Duration: {audio_buffer.duration_seconds:.2f}s"
        )

        # Audio analysis
        st.subheader("📊 Audio Analysis")

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Duration", f"{audio_buffer.duration_seconds:.2f}s")
        with col2:
            st.metric("Sample Rate", f"{audio_buffer.frame_rate} Hz")
        with col3:
            st.metric("Channels", audio_buffer.channels)

        # Audio player
        st.subheader("🎵 Playback")
        audio_bytes = audio_buffer.export(format="wav").read()
        st.audio(audio_bytes, format="audio/wav")

        # Download options
        st.subheader("💾 Download")
        col1, col2, col3 = st.columns(3)

        with col1:
            st.download_button(
                label="📁 Download WAV",
                data=audio_bytes,
                file_name=f"recording_{int(time.time())}.wav",
                mime="audio/wav",
            )

        with col2:
            if st.button("🔄 New Recording"):
                st.session_state["audio_buffer"] = pydub.AudioSegment.empty()
                st.rerun()

        with col3:
            if st.button("🗑️ Clear All"):
                st.session_state.clear()
                st.rerun()


if __name__ == "__main__":
    main()
