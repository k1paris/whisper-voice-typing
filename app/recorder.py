"""Whisper Voice Typing — Audio recording and server inference."""
import subprocess
import threading
import time
import os
import signal

from config import AUDIO_FILE, INFERENCE_URL


class Recorder:
    """Records microphone audio via parec, sends to whisper-server, pastes result."""

    def __init__(self, on_result=None, on_status=None):
        self.on_result = on_result      # callback(text, duration_ms)
        self.on_status = on_status      # callback(status_str)
        self._parec_proc = None
        self._recording = False
        self._record_start = None

    @property
    def is_recording(self):
        return self._recording

    def start_recording(self):
        """Start capturing microphone audio."""
        if self._recording:
            return
        self._recording = True
        self._record_start = time.time()

        # Clean up
        try:
            os.remove(AUDIO_FILE)
        except FileNotFoundError:
            pass
        subprocess.run(
            ["pkill", "-x", "parec"], capture_output=True
        )

        self._parec_proc = subprocess.Popen(
            [
                "parec",
                "--rate=16000",
                "--channels=1",
                "--format=s16le",
                "--file-format=wav",
                AUDIO_FILE,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        if self.on_status:
            self.on_status("recording")

    def stop_recording(self):
        """Stop recording, send to server, paste result. Runs synchronously."""
        if not self._recording:
            return
        self._recording = False

        # Trailing audio capture delay (matches original script)
        time.sleep(0.9)

        # Stop parec with SIGINT (graceful, flushes WAV header)
        if self._parec_proc:
            try:
                self._parec_proc.send_signal(signal.SIGINT)
                self._parec_proc.wait(timeout=3)
            except (subprocess.TimeoutExpired, OSError):
                try:
                    self._parec_proc.kill()
                except OSError:
                    pass
            self._parec_proc = None

        time.sleep(0.2)

        duration_ms = (
            int((time.time() - self._record_start) * 1000)
            if self._record_start else 0
        )

        if self.on_status:
            self.on_status("processing")

        # Verify audio file
        if not os.path.isfile(AUDIO_FILE) or os.path.getsize(AUDIO_FILE) == 0:
            if self.on_status:
                self.on_status("error")
            return

        # Recognize
        text = self._send_to_server()

        if text:
            self._paste_text(text)
            if self.on_result:
                self.on_result(text, duration_ms)
            if self.on_status:
                self.on_status("idle")
        else:
            if self.on_status:
                self.on_status("idle")

    def stop_recording_async(self):
        """Stop recording in a background thread (non-blocking)."""
        threading.Thread(target=self.stop_recording, daemon=True).start()

    def _send_to_server(self):
        """POST audio to whisper-server, return recognized text."""
        try:
            result = subprocess.run(
                [
                    "curl", "-s", INFERENCE_URL,
                    "-F", f"file=@{AUDIO_FILE}",
                    "-F", "language=auto",
                    "-F", "response_format=text",
                ],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode == 0:
                text = result.stdout.replace("\r", "").replace("\n", "")
                while "  " in text:
                    text = text.replace("  ", " ")
                text = text.strip()
                return text if text else None
        except Exception:
            pass
        return None

    def _paste_text(self, text):
        """Copy to clipboard and simulate Ctrl+V."""
        try:
            proc = subprocess.Popen(
                ["xclip", "-selection", "clipboard"],
                stdin=subprocess.PIPE,
            )
            proc.communicate(input=text.encode("utf-8"), timeout=3)
            time.sleep(0.05)
            subprocess.run(
                ["xdotool", "key", "--clearmodifiers", "ctrl+v"],
                capture_output=True, timeout=3,
            )
        except Exception:
            pass
