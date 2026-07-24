"""Whisper Voice Typing — Recognition history with SQLite + FTS5."""
import sqlite3
import os
import time
import threading

from config import HISTORY_DB, DATA_DIR, HISTORY_LIMIT


class History:
    """Thread-safe recognition history backed by SQLite with full-text search."""

    def __init__(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(HISTORY_DB, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        with self._lock:
            self.conn.executescript("""
                CREATE TABLE IF NOT EXISTS entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    text TEXT NOT NULL,
                    duration_ms INTEGER,
                    language TEXT DEFAULT 'auto'
                );

                CREATE TABLE IF NOT EXISTS archive (
                    id INTEGER PRIMARY KEY,
                    timestamp REAL NOT NULL,
                    text TEXT NOT NULL,
                    duration_ms INTEGER,
                    language TEXT
                );

                CREATE VIRTUAL TABLE IF NOT EXISTS entries_fts USING fts5(
                    text, content='entries', content_rowid='id',
                    tokenize='unicode61'
                );

                CREATE TRIGGER IF NOT EXISTS entries_ai AFTER INSERT ON entries BEGIN
                    INSERT INTO entries_fts(rowid, text) VALUES (new.id, new.text);
                END;
                CREATE TRIGGER IF NOT EXISTS entries_ad AFTER DELETE ON entries BEGIN
                    INSERT INTO entries_fts(entries_fts, rowid, text)
                        VALUES ('delete', old.id, old.text);
                END;
            """)

    def add_entry(self, text, duration_ms=None, language="auto"):
        """Add a new recognition entry. Returns the new row id."""
        with self._lock:
            cur = self.conn.execute(
                "INSERT INTO entries (timestamp, text, duration_ms, language) "
                "VALUES (?, ?, ?, ?)",
                (time.time(), text, duration_ms, language),
            )
            self.conn.commit()
            row_id = cur.lastrowid
        self._enforce_limit()
        return row_id

    def _enforce_limit(self):
        """Move oldest entries to archive when limit is exceeded."""
        with self._lock:
            count = self.conn.execute(
                "SELECT COUNT(*) FROM entries"
            ).fetchone()[0]
            if count <= HISTORY_LIMIT:
                return
            excess = count - HISTORY_LIMIT
            self.conn.execute(
                "INSERT INTO archive (id, timestamp, text, duration_ms, language) "
                "SELECT id, timestamp, text, duration_ms, language "
                "FROM entries ORDER BY timestamp ASC LIMIT ?",
                (excess,),
            )
            self.conn.execute(
                "DELETE FROM entries WHERE id IN ("
                "  SELECT id FROM entries ORDER BY timestamp ASC LIMIT ?"
                ")",
                (excess,),
            )
            self.conn.commit()

    def search(self, query, limit=100):
        """Full-text search via FTS5. Returns list of tuples."""
        with self._lock:
            if not query or not query.strip():
                return self.get_recent(limit)
            # Escape FTS5 special chars and add prefix matching
            safe_q = query.strip().replace('"', '""')
            tokens = safe_q.split()
            fts_query = " ".join(f'"{t}"*' for t in tokens if t)
            try:
                return self.conn.execute(
                    "SELECT e.id, e.timestamp, e.text, e.duration_ms, e.language "
                    "FROM entries e "
                    "JOIN entries_fts f ON e.id = f.rowid "
                    "WHERE entries_fts MATCH ? "
                    "ORDER BY e.timestamp DESC LIMIT ?",
                    (fts_query, limit),
                ).fetchall()
            except sqlite3.OperationalError:
                # Fallback to LIKE if FTS query is malformed
                return self.conn.execute(
                    "SELECT id, timestamp, text, duration_ms, language "
                    "FROM entries WHERE text LIKE ? "
                    "ORDER BY timestamp DESC LIMIT ?",
                    (f"%{query.strip()}%", limit),
                ).fetchall()

    def get_recent(self, limit=100):
        """Get most recent entries."""
        with self._lock:
            return self.conn.execute(
                "SELECT id, timestamp, text, duration_ms, language "
                "FROM entries ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()

    def delete(self, entry_id):
        """Delete a single entry by id."""
        with self._lock:
            self.conn.execute("DELETE FROM entries WHERE id = ?", (entry_id,))
            self.conn.commit()

    def clear(self):
        """Move all entries to archive, then clear the main table."""
        with self._lock:
            self.conn.execute(
                "INSERT OR IGNORE INTO archive "
                "(id, timestamp, text, duration_ms, language) "
                "SELECT id, timestamp, text, duration_ms, language FROM entries"
            )
            self.conn.execute("DELETE FROM entries")
            self.conn.commit()

    def close(self):
        self.conn.close()
