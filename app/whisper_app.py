#!/usr/bin/env python3
"""Whisper Voice Typing — Desktop application with system tray.

Usage:
    python3 whisper_app.py
"""

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("AyatanaAppIndicator3", "0.1")

from gi.repository import Gtk, GLib, Gdk, Pango, AyatanaAppIndicator3
import subprocess
import signal
import sys
import os
import time
import threading
import urllib.request
from datetime import datetime
import fcntl

# Ensure app package is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
from history import History
from input_listener import InputListener
from recorder import Recorder


# ─── CSS ────────────────────────────────────────────────────────────────
_CSS = b"""
.history-window {
    background-color: #1e1e2e;
}
.search-entry {
    border-radius: 8px;
    padding: 6px 12px;
    font-size: 14px;
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
}
.search-entry:focus {
    border-color: #89b4fa;
}
.history-tree {
    background-color: #1e1e2e;
    color: #cdd6f4;
    font-size: 13px;
}
.history-tree:selected {
    background-color: #45475a;
}
.history-tree header button {
    background-color: #181825;
    color: #a6adc8;
    font-weight: bold;
    border-bottom: 1px solid #313244;
}
.status-label {
    color: #6c7086;
    font-size: 12px;
    padding: 4px 0;
}
.btn-danger {
    background-color: #45475a;
    color: #f38ba8;
    border-radius: 6px;
    padding: 4px 14px;
    border: 1px solid #f38ba8;
}
.btn-danger:hover {
    background-color: #f38ba8;
    color: #1e1e2e;
}
.header-bar-custom {
    padding: 8px 12px;
}
"""


# ─── History Window ─────────────────────────────────────────────────────
class HistoryWindow(Gtk.Window):
    """GTK window showing recognition history with search."""

    def __init__(self, history_db):
        super().__init__(title="Whisper Voice — История")
        self.history = history_db
        self.set_default_size(750, 520)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.get_style_context().add_class("history-window")

        # Hide instead of destroy
        self.connect("delete-event", self._on_delete)

        # Apply CSS
        css_provider = Gtk.CssProvider()
        css_provider.load_from_data(_CSS)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

        # Layout
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(vbox)

        # ── Header bar ──
        header = Gtk.Box(spacing=10)
        header.set_margin_start(12)
        header.set_margin_end(12)
        header.set_margin_top(10)
        header.set_margin_bottom(6)
        header.get_style_context().add_class("header-bar-custom")

        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_placeholder_text("Поиск по истории…")
        self.search_entry.get_style_context().add_class("search-entry")
        self.search_entry.connect("search-changed", self._on_search)
        header.pack_start(self.search_entry, True, True, 0)

        clear_btn = Gtk.Button(label="Очистить всё")
        clear_btn.get_style_context().add_class("btn-danger")
        clear_btn.connect("clicked", self._on_clear_all)
        header.pack_end(clear_btn, False, False, 0)

        vbox.pack_start(header, False, False, 0)

        # ── Tree view ──
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)

        # Columns: id(int), time_str, preview_text, full_text
        self.store = Gtk.ListStore(int, str, str, str)
        self.tree = Gtk.TreeView(model=self.store)
        self.tree.set_headers_visible(True)
        self.tree.set_activate_on_single_click(False)
        self.tree.get_style_context().add_class("history-tree")
        self.tree.connect("row-activated", self._on_row_activated)
        self.tree.connect("key-press-event", self._on_key_press)

        # Time column
        r_time = Gtk.CellRendererText()
        col_time = Gtk.TreeViewColumn("Время", r_time, text=1)
        col_time.set_min_width(155)
        col_time.set_resizable(True)
        self.tree.append_column(col_time)

        # Text column
        r_text = Gtk.CellRendererText()
        r_text.set_property("ellipsize", Pango.EllipsizeMode.END)
        col_text = Gtk.TreeViewColumn("Текст", r_text, text=2)
        col_text.set_expand(True)
        self.tree.append_column(col_text)

        scroll.add(self.tree)
        vbox.pack_start(scroll, True, True, 0)

        # ── Status bar ──
        self.status = Gtk.Label()
        self.status.get_style_context().add_class("status-label")
        self.status.set_halign(Gtk.Align.START)
        self.status.set_margin_start(14)
        self.status.set_margin_bottom(6)
        vbox.pack_start(self.status, False, False, 0)

        self._load_data()

    # ── Data ──

    def _load_data(self, query=None):
        self.store.clear()
        rows = (
            self.history.search(query) if query
            else self.history.get_recent(1000)
        )
        for row in rows:
            ts = datetime.fromtimestamp(row[1]).strftime("%d.%m.%Y  %H:%M:%S")
            preview = (row[2][:200]) if row[2] else ""
            self.store.append([row[0], ts, preview, row[2] or ""])
        self.status.set_text(f"Записей: {len(rows)}")

    def refresh(self):
        q = self.search_entry.get_text().strip()
        self._load_data(q if q else None)

    # ── Callbacks ──

    def _on_delete(self, widget, event):
        self.hide()
        return True

    def _on_search(self, entry):
        q = entry.get_text().strip()
        self._load_data(q if q else None)

    def _on_row_activated(self, tree, path, column):
        """Double-click → copy full text to clipboard."""
        it = self.store.get_iter(path)
        full = self.store.get_value(it, 3)
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.set_text(full, -1)
        self.status.set_text("📋 Скопировано в буфер обмена")

    def _on_key_press(self, widget, event):
        if event.keyval == Gdk.KEY_Delete:
            sel = self.tree.get_selection()
            model, it = sel.get_selected()
            if it:
                eid = model.get_value(it, 0)
                self.history.delete(eid)
                model.remove(it)
                self.status.set_text("🗑️ Запись удалена")

    def _on_clear_all(self, button):
        dlg = Gtk.MessageDialog(
            parent=self,
            flags=Gtk.DialogFlags.MODAL,
            type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.YES_NO,
            message_format="Очистить всю историю?\nЗаписи будут перемещены в архив.",
        )
        resp = dlg.run()
        dlg.destroy()
        if resp == Gtk.ResponseType.YES:
            self.history.clear()
            self._load_data()


# ─── Main App ───────────────────────────────────────────────────────────
class WhisperApp:
    """System tray application: manages server, input, recording, history."""

    def __init__(self):
        self.history = History()
        self.history_window = None
        self.server_proc = None
        self._server_monitor_active = False

        # ── Tray indicator ──
        print("[App] Setting up tray icon...")
        self.indicator = AyatanaAppIndicator3.Indicator.new(
            config.APP_ID,
            "whisper-idle",
            AyatanaAppIndicator3.IndicatorCategory.APPLICATION_STATUS,
        )
        self.indicator.set_icon_theme_path(config.ICONS_DIR)
        self.indicator.set_status(
            AyatanaAppIndicator3.IndicatorStatus.ACTIVE
        )

        # ── Menu ──
        self.menu = Gtk.Menu()

        self.status_item = Gtk.MenuItem(label="⏳ Запуск сервера…")
        self.status_item.set_sensitive(False)
        self.menu.append(self.status_item)
        self.menu.append(Gtk.SeparatorMenuItem())

        history_item = Gtk.MenuItem(label="📋 История")
        history_item.connect("activate", self._on_show_history)
        self.menu.append(history_item)
        self.menu.append(Gtk.SeparatorMenuItem())

        restart_item = Gtk.MenuItem(label="🔄 Перезапустить сервер")
        restart_item.connect("activate", self._on_restart_server)
        self.menu.append(restart_item)
        self.menu.append(Gtk.SeparatorMenuItem())

        quit_item = Gtk.MenuItem(label="❌ Выход")
        quit_item.connect("activate", self._on_quit)
        self.menu.append(quit_item)

        self.menu.show_all()
        self.indicator.set_menu(self.menu)

        # ── Recorder ──
        self.recorder = Recorder(
            on_result=self._on_recognition_result,
            on_status=self._on_recorder_status,
        )

        # ── Input listener (auto-detect keyboard) ──
        device = (
            InputListener.find_keyboard_device() or config.INPUT_DEVICE
        )
        print(f"[App] Listening to keyboard on {device}")
        self.listener = InputListener(
            device=device,
            on_key_down=self._on_key_down,
            on_key_up=self._on_key_up,
            on_error=self._on_input_error,
        )

        # ── Launch ──
        print("[App] Starting server and listener...")
        self._start_server()
        self.listener.start()
        print("[App] Initialization complete, entering GTK main loop.")

    # ── Input error ──

    def _on_input_error(self, err_msg):
        GLib.idle_add(
            self._set_status,
            f"❌ Ошибка клавиатуры: {err_msg}", "error",
        )

    # ── Server management ──

    def _start_server(self):
        """Start whisper-server as a child process."""
        if self.server_proc and self.server_proc.poll() is None:
            return

        if not os.path.isfile(config.WHISPER_SERVER_BIN):
            GLib.idle_add(
                self._set_status,
                "❌ whisper-server не найден", "error",
            )
            return

        try:
            env = os.environ.copy()
            server_bin_dir = os.path.dirname(config.WHISPER_SERVER_BIN)
            env["LD_LIBRARY_PATH"] = server_bin_dir + ":" + env.get("LD_LIBRARY_PATH", "")

            self.server_log = open(os.path.join(config.DATA_DIR, "server.log"), "w")
            self.server_proc = subprocess.Popen(
                [
                    config.WHISPER_SERVER_BIN,
                    "-m", config.WHISPER_MODEL,
                    "--host", config.SERVER_HOST,
                    "--port", str(config.SERVER_PORT),
                    "-l", "auto",
                ],
                stdout=self.server_log,
                stderr=subprocess.STDOUT,
                env=env,
            )
        except Exception as exc:
            GLib.idle_add(
                self._set_status,
                f"❌ Ошибка запуска: {exc}", "error",
            )
            return

        self._server_monitor_active = True
        threading.Thread(target=self._wait_for_server, daemon=True).start()

    def _wait_for_server(self):
        """Poll the server until it responds (up to 120 s)."""
        for _ in range(120):
            if not self._server_monitor_active:
                return
            # Check process didn't crash
            if self.server_proc and self.server_proc.poll() is not None:
                GLib.idle_add(
                    self._set_status,
                    "❌ Сервер упал при запуске", "error",
                )
                return
            try:
                urllib.request.urlopen(config.SERVER_URL, timeout=1)
                GLib.idle_add(
                    self._set_status,
                    "✅ Готов  (Правый Ctrl — запись)", "idle",
                )
                return
            except Exception:
                time.sleep(1)
        GLib.idle_add(
            self._set_status,
            "❌ Сервер не запустился за 120 с", "error",
        )

    def _stop_server(self):
        self._server_monitor_active = False
        if self.server_proc:
            self.server_proc.terminate()
            try:
                self.server_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.server_proc.kill()
            self.server_proc = None

    # ── UI helpers ──

    def _set_status(self, text, icon_state=None):
        print(f"[Status] {text}")
        self.status_item.set_label(text)
        icon_map = {
            "idle": "whisper-idle",
            "recording": "whisper-recording",
            "error": "whisper-error",
        }
        if icon_state and icon_state in icon_map:
            self.indicator.set_icon_full(
                icon_map[icon_state], icon_state,
            )

    # ── Key callbacks ──

    def _on_key_down(self):
        GLib.idle_add(
            self._set_status, "🎤 Записываю…", "recording",
        )
        self.recorder.start_recording()

    def _on_key_up(self):
        self.recorder.stop_recording_async()

    # ── Recorder callbacks ──

    def _on_recognition_result(self, text, duration_ms):
        self.history.add_entry(text, duration_ms)
        if self.history_window and self.history_window.get_visible():
            GLib.idle_add(self.history_window.refresh)

    def _on_recorder_status(self, status):
        labels = {
            "recording":  ("🎤 Записываю…",                "recording"),
            "processing": ("⏳ Распознаю…",                "recording"),
            "idle":       ("✅ Готов  (Правый Ctrl — запись)", "idle"),
            "error":      ("❌ Ошибка записи",               "error"),
        }
        label, icon = labels.get(status, ("❓ …", "idle"))
        GLib.idle_add(self._set_status, label, icon)

    # ── Menu actions ──

    def _on_show_history(self, _item):
        if not self.history_window:
            self.history_window = HistoryWindow(self.history)
        self.history_window.refresh()
        self.history_window.show_all()
        self.history_window.present()

    def _on_restart_server(self, _item):
        GLib.idle_add(
            self._set_status, "⏳ Перезапуск сервера…", "error",
        )
        threading.Thread(target=self._do_restart, daemon=True).start()

    def _do_restart(self):
        self._stop_server()
        time.sleep(1)
        self._start_server()

    def _on_quit(self, _item):
        self.listener.stop()
        self._stop_server()
        self.history.close()
        Gtk.main_quit()

    # ── Run ──

    def run(self):
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        signal.signal(signal.SIGTERM, lambda *_: self._on_quit(None))
        Gtk.main()


# ─── Entry point ────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Prevent multiple instances using a lock file
    lock_file_path = os.path.join(config.DATA_DIR, "whisper_app.lock")
    try:
        # Create DATA_DIR if it doesn't exist yet
        os.makedirs(config.DATA_DIR, exist_ok=True)
        lock_fd = open(lock_file_path, "w")
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("❌ Приложение уже запущено. Выход.")
        sys.exit(0)

    app = WhisperApp()
    app.run()
