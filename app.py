import queue
import streamlit as st
import pydub
import time
from streamlit_webrtc import webrtc_streamer, WebRtcMode


def format_time(seconds: float) -> str:
    seconds = max(0, int(seconds))
    m, s = divmod(seconds, 60)
    return f"{m:02d}:{s:02d}"


def main():
    st.title("🎙️ Live Audio Recorder")

    # Session init
    if "audio_buffer" not in st.session_state:
        st.session_state["audio_buffer"] = pydub.AudioSegment.empty()
    if "paused" not in st.session_state:
        st.session_state["paused"] = False
    if "start_time" not in st.session_state:
        st.session_state["start_time"] = None
    if "paused_at" not in st.session_state:
        st.session_state["paused_at"] = None
    if "total_paused" not in st.session_state:
        st.session_state["total_paused"] = 0.0

    RTC_CONFIGURATION = {"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]}

    webrtc_ctx = webrtc_streamer(
        key="complete-audio-recorder",
        mode=WebRtcMode.SENDONLY,
        audio_receiver_size=1024,
        rtc_configuration=RTC_CONFIGURATION,
        media_stream_constraints={
            "audio": {
                "sampleRate": 44100,
                "channelCount": 1,
                "echoCancellation": True,
                "noiseSuppression": True,
            },
            "video": False,
        },
        audio_html_attrs={"muted": True},
    )

    # Conditional Controls - Show only when recording is active
    if webrtc_ctx.state.playing:
        st.markdown("---")
        # Single toggle button for play/pause
        button_text = "⏸️ Pause" if not st.session_state["paused"] else "▶️ Resume"
        button_type = "secondary" if not st.session_state["paused"] else "primary"

        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            if st.button(button_text, type=button_type, use_container_width=True):
                if not st.session_state["paused"]:
                    # Pause recording
                    st.session_state["paused"] = True
                    st.session_state["paused_at"] = time.time()
                else:
                    # Resume recording
                    if st.session_state["paused_at"] is not None:
                        st.session_state["total_paused"] += (
                            time.time() - st.session_state["paused_at"]
                        )
                    st.session_state["paused"] = False
                    st.session_state["paused_at"] = None
                st.rerun()

    # Start time bookkeeping
    if webrtc_ctx.state.playing and st.session_state["start_time"] is None:
        st.session_state["start_time"] = time.time()

    # Initialize UI placeholders for status and timer
    if webrtc_ctx.state.playing:
        col1, col2 = st.columns(2)
        with col1:
            status_placeholder = st.empty()
        with col2:
            timer_placeholder = st.empty()
    else:
        col1, col2 = st.columns(2)
        with col1:
            status_placeholder = st.empty()
        with col2:
            timer_placeholder = st.empty()

    # Recording loop
    while True:
        if webrtc_ctx.audio_receiver:
            # Update timer in real-time
            now = time.time()
            base_elapsed = 0.0
            if st.session_state["start_time"] is not None:
                base_elapsed = (
                    now
                    - st.session_state["start_time"]
                    - st.session_state["total_paused"]
                )
                if (
                    st.session_state["paused"]
                    and st.session_state["paused_at"] is not None
                ):
                    base_elapsed -= now - st.session_state["paused_at"]

            elapsed_time = max(base_elapsed, 0)

            # Update UI placeholders
            if st.session_state["paused"]:
                status_placeholder.warning("⏸️ RECORDING PAUSED")
            else:
                status_placeholder.success("🎤 Recording...")

            timer_placeholder.info(f"⏱️ {format_time(elapsed_time)}")

            try:
                audio_frames = webrtc_ctx.audio_receiver.get_frames(timeout=1)
            except queue.Empty:
                continue

            # Only buffer when not paused
            if not st.session_state["paused"]:
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
            break

    # Conditional Output - Show only when there's recorded audio
    audio_buffer = st.session_state["audio_buffer"]

    if len(audio_buffer) > 0:
        # Audio Playback Section
        st.markdown("### 🎵 Audio Playback")
        audio_bytes = audio_buffer.export(format="wav").read()
        st.audio(audio_bytes, format="audio/wav")

        # Recording Info
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("⏱️ Duration", f"{audio_buffer.duration_seconds:.2f}s")
        with col2:
            st.metric("🎚️ Sample Rate", f"{audio_buffer.frame_rate}Hz")
        with col3:
            file_size_bytes = len(audio_bytes)
            file_size_kb = file_size_bytes / 1024
            if file_size_kb >= 1024:
                file_size_mb = file_size_kb / 1024
                st.metric("💾 Size", f"{file_size_mb:.2f} MB")
            else:
                st.metric("💾 Size", f"{file_size_kb:.1f} KB")

        # Action Buttons
        st.markdown("### 📁 Actions")
        action_col1, action_col2 = st.columns(2)
        with action_col1:
            st.download_button(
                label="📁 Download WAV",
                data=audio_bytes,
                file_name=f"recording_{int(time.time())}.wav",
                mime="audio/wav",
                use_container_width=True,
            )
        with action_col2:
            if st.button("🔄 New Recording", type="primary", use_container_width=True):
                st.session_state["audio_buffer"] = pydub.AudioSegment.empty()
                st.session_state["start_time"] = None
                st.session_state["paused"] = False
                st.session_state["paused_at"] = None
                st.session_state["total_paused"] = 0.0
                st.rerun()


if __name__ == "__main__":
    main()
