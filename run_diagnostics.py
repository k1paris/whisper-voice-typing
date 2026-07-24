#!/usr/bin/env python3
import sys
import os
import time
import subprocess
import threading
import urllib.request
import signal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

import config
from input_listener import InputListener

print("=== Whisper App Diagnostic Tests ===")

# Test 1: Groups
print("\n[1] Checking user groups...")
groups = subprocess.run(['groups'], capture_output=True, text=True).stdout
print(f"Groups: {groups.strip()}")
if 'input' not in groups:
    print("❌ ERROR: User is not in 'input' group. You must log out and log back in!")
else:
    print("✅ User in 'input' group.")

# Test 2: Keyboard detection
print("\n[2] Checking keyboard detection...")
device = InputListener.find_keyboard_device()
if device:
    print(f"✅ Auto-detected keyboard: {device}")
else:
    print(f"⚠️ Could not auto-detect keyboard. Fallback to: {config.INPUT_DEVICE}")
    device = config.INPUT_DEVICE

# Test 3: evtest permissions
print(f"\n[3] Checking evtest access to {device}...")
try:
    proc = subprocess.Popen(['evtest', device], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    time.sleep(1)
    proc.terminate()
    stdout, stderr = proc.communicate(timeout=2)
    if "Permission denied" in stderr or "Permission denied" in stdout:
        print(f"❌ ERROR: Permission denied for {device}. Are you really in 'input' group? Try running: sudo usermod -aG input $USER && newgrp input")
        print(f"Stderr: {stderr.strip()}")
    else:
        print("✅ evtest has read access.")
except Exception as e:
    print(f"❌ ERROR running evtest: {e}")

# Test 4: whisper-server startup
print("\n[4] Checking whisper-server startup...")
if not os.path.exists(config.WHISPER_SERVER_BIN):
    print(f"❌ ERROR: Server binary not found at {config.WHISPER_SERVER_BIN}")
else:
    print(f"Starting server: {config.WHISPER_SERVER_BIN} -m {config.WHISPER_MODEL} ...")
    server_proc = subprocess.Popen(
        [
            config.WHISPER_SERVER_BIN,
            "-m", config.WHISPER_MODEL,
            "--host", config.SERVER_HOST,
            "--port", str(config.SERVER_PORT),
            "-l", "auto",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    server_ready = False
    for _ in range(15):
        if server_proc.poll() is not None:
            print("❌ ERROR: Server crashed unexpectedly!")
            out, err = server_proc.communicate()
            print(f"Stderr: {err.decode('utf-8', errors='ignore')}")
            break
        try:
            urllib.request.urlopen(config.SERVER_URL, timeout=1)
            server_ready = True
            break
        except Exception:
            time.sleep(1)
            
    if server_ready:
        print("✅ whisper-server started and responds to HTTP.")
        server_proc.terminate()
        server_proc.wait()
    else:
        print("❌ ERROR: Server did not respond within 15 seconds.")
        if server_proc.poll() is None:
            server_proc.terminate()

# Test 5: DBus and GTK
print("\n[5] Checking DBus and GTK Tray availability...")
try:
    import gi
    gi.require_version("Gtk", "3.0")
    gi.require_version("AyatanaAppIndicator3", "0.1")
    from gi.repository import Gtk, AyatanaAppIndicator3
    print("✅ GTK3 and AppIndicator libraries loaded.")
except Exception as e:
    print(f"❌ ERROR loading GUI libraries: {e}")

# Test 6: parec
print("\n[6] Checking parec audio recording...")
try:
    audio_test_file = "/tmp/test_audio.wav"
    if os.path.exists(audio_test_file):
        os.remove(audio_test_file)
    p_proc = subprocess.Popen(["parec", "--rate=16000", "--channels=1", "--format=s16le", "--file-format=wav", audio_test_file])
    time.sleep(2)
    p_proc.send_signal(signal.SIGINT)
    p_proc.wait(timeout=3)
    if os.path.exists(audio_test_file) and os.path.getsize(audio_test_file) > 1000:
        print(f"✅ parec recorded successfully ({os.path.getsize(audio_test_file)} bytes).")
    else:
        print("❌ ERROR: parec did not record audio properly.")
except Exception as e:
    print(f"❌ ERROR with parec: {e}")

print("\n=== Tests complete ===")
