"""Whisper Voice Typing — Configuration."""
import os

# Paths
APP_DIR = os.path.dirname(os.path.abspath(__file__))
WHISPER_CPP_DIR = os.path.join(os.path.dirname(APP_DIR), "whisper.cpp")
WHISPER_SERVER_BIN = os.path.join(WHISPER_CPP_DIR, "build", "bin", "whisper-server")
WHISPER_MODEL = os.path.join(WHISPER_CPP_DIR, "models", "ggml-large-v3-turbo.bin")

# Server
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 8090
SERVER_URL = f"http://{SERVER_HOST}:{SERVER_PORT}"
INFERENCE_URL = f"{SERVER_URL}/inference"

# Input — auto-detected at runtime, this is the fallback
INPUT_DEVICE = "/dev/input/event3"

# Audio
AUDIO_FILE = "/tmp/whisper_voice.wav"

# History
DATA_DIR = os.path.expanduser("~/.local/share/whisper-app")
HISTORY_DB = os.path.join(DATA_DIR, "history.db")
HISTORY_LIMIT = 1000

# Icons (without extension — AppIndicator resolves .svg automatically)
ICONS_DIR = os.path.join(APP_DIR, "icons")
ICON_IDLE = os.path.join(ICONS_DIR, "whisper-idle")
ICON_RECORDING = os.path.join(ICONS_DIR, "whisper-recording")
ICON_ERROR = os.path.join(ICONS_DIR, "whisper-error")

# App
APP_NAME = "Whisper Voice"
APP_ID = "whisper-voice"
