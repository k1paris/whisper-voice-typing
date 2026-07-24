"""Whisper Voice Typing — Keyboard input listener via evtest."""
import subprocess
import threading
import re
import time


class InputListener:
    """Listens for Right Ctrl key press/release via evtest subprocess."""

    def __init__(self, device, on_key_down=None, on_key_up=None, on_error=None):
        self.device = device
        self.on_key_down = on_key_down
        self.on_key_up = on_key_up
        self.on_error = on_error
        self._process = None
        self._thread = None
        self._running = False

    @staticmethod
    def find_keyboard_device():
        """Auto-detect keyboard from /proc/bus/input/devices.

        Returns /dev/input/eventN path or None.
        """
        best_match = None
        fallback_match = None
        try:
            with open("/proc/bus/input/devices", "r") as f:
                content = f.read()

            for block in content.split("\n\n"):
                if not block.strip():
                    continue
                has_kbd = "kbd" in block.lower()
                name_match = re.search(r'N: Name="(.+?)"', block)
                handler_match = re.search(r"H: Handlers=.*?(event\d+)", block)
                if not handler_match:
                    continue

                name = name_match.group(1).lower() if name_match else ""
                event = handler_match.group(1)

                if "keyboard" in name:
                    # Prefer the first actual keyboard
                    if not best_match:
                        best_match = f"/dev/input/{event}"
                elif has_kbd and "mouse" not in name and "video" not in name and "power" not in name and "audio" not in name:
                    if not fallback_match:
                        fallback_match = f"/dev/input/{event}"
            
            return best_match or fallback_match
        except Exception:
            pass
        return None

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._listen, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._process:
            try:
                self._process.terminate()
            except OSError:
                pass
            self._process = None

    def _listen(self):
        """Main loop: run evtest, parse output, call callbacks."""
        while self._running:
            try:
                self._process = subprocess.Popen(
                    ["evtest", self.device],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                
                # Check for immediate errors in stderr
                time.sleep(0.5)
                if self._process.poll() is not None:
                    _, err = self._process.communicate()
                    if "Permission denied" in err:
                        if self.on_error:
                            self.on_error("Permission denied. Нужен релогин для группы input!")
                        self._running = False
                        break

                for line in self._process.stdout:
                    if not self._running:
                        break
                    # evtest output: "... code 97 (KEY_RIGHTCTRL), value 1"
                    if "code 97 (KEY_RIGHTCTRL)" not in line:
                        continue
                    if "value 1" in line:
                        if self.on_key_down:
                            self.on_key_down()
                    elif "value 0" in line:
                        if self.on_key_up:
                            self.on_key_up()

                if self._process:
                    self._process.wait()
            except Exception:
                pass

            # Retry on crash (e.g. device unplugged)
            if self._running:
                time.sleep(2)
