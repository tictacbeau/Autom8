"""
Tier 3 — Local Folder Watch.

Monitors data/watch/ for new files using watchdog.
Supported: .eml, .msg, .pdf, .docx, .png, .jpg, .jpeg, .tiff, .bmp
Each new file is parsed and inserted into email_cache for the matcher.
"""
import logging
import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

log = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".eml", ".msg", ".pdf", ".docx", ".png", ".jpg", ".jpeg", ".tiff", ".bmp"}


class RemittanceFileHandler(FileSystemEventHandler):
    """Processes files dropped into the watch folder."""

    def on_created(self, event):
        if event.is_directory:
            return
        path = Path(event.src_path)
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            return
        # Small delay to ensure the file is fully written
        time.sleep(0.5)
        self._process_file(path)

    def on_moved(self, event):
        """Handle files moved into the watch folder (e.g. drag-and-drop)."""
        if event.is_directory:
            return
        path = Path(event.dest_path)
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            return
        time.sleep(0.5)
        self._process_file(path)

    def _process_file(self, path: Path):
        """Extract text from file and insert into email_cache."""
        log.info("Folder watch: processing %s", path.name)
        try:
            from app.processing.text_extractor import extract_text_from_file
            from app.database import get_db, now_iso

            text, method = extract_text_from_file(str(path))

            # Build a synthetic email dict from the file
            email_dict = {
                "message_id":    f"folder:{path.name}",
                "subject":       path.stem,
                "sender":        "",
                "sender_domain": "",
                "received_date": now_iso(),
                "body_html":     "",
                "body_text":     text,
                "attachments":   [{"name": path.name, "path": str(path), "content_type": ""}],
                "source_tier":   "folder",
            }

            _insert_email_cache(email_dict)
            log.info("Folder watch: inserted %s (method: %s)", path.name, method)
        except Exception as e:
            log.error("Folder watch: error processing %s: %s", path.name, e)


def _insert_email_cache(email_dict: dict):
    """Thread-safe insert into email_cache using a fresh connection."""
    import sqlite3
    import json
    from app.config import DB_PATH
    from app.database import now_iso

    conn = sqlite3.connect(str(DB_PATH))
    try:
        conn.execute("""
            INSERT INTO email_cache
                (message_id, subject, sender, sender_domain, received_date, body_text, attachments, source_tier, fetched_at)
            VALUES (?,?,?,?,?,?,?,?,?)
            ON CONFLICT(message_id) DO NOTHING
        """, (
            email_dict["message_id"],
            email_dict["subject"],
            email_dict["sender"],
            email_dict["sender_domain"],
            email_dict["received_date"],
            email_dict["body_text"],
            json.dumps(email_dict["attachments"]),
            email_dict["source_tier"],
            now_iso(),
        ))
        conn.commit()
    finally:
        conn.close()


class FolderWatcher:
    """Manages the watchdog Observer for the watch folder."""

    def __init__(self, watch_path: str):
        self.watch_path = watch_path
        self._observer = None

    def start(self):
        Path(self.watch_path).mkdir(parents=True, exist_ok=True)
        handler = RemittanceFileHandler()
        self._observer = Observer()
        self._observer.schedule(handler, self.watch_path, recursive=False)
        self._observer.start()
        log.info("Folder watcher started on: %s", self.watch_path)

        # Process any files already in the folder (in case app restarted)
        self._process_existing()

        try:
            while self._observer.is_alive():
                self._observer.join(timeout=1)
        except KeyboardInterrupt:
            self.stop()

    def stop(self):
        if self._observer:
            self._observer.stop()
            self._observer.join()

    def _process_existing(self):
        """Process files already in the watch folder on startup."""
        for path in Path(self.watch_path).iterdir():
            if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
                handler = RemittanceFileHandler()
                handler._process_file(path)
