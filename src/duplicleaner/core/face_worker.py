"""Background face analysis worker.

Runs face detection on images while scans are in progress,
and can drain any remaining files after a scan completes.
"""

import contextlib
import threading
import time
from collections.abc import Callable

from duplicleaner.ai.faces import FaceAnalyzer
from duplicleaner.db.database import Database
from duplicleaner.utils.logging import get_logger

logger = get_logger(__name__)


class FaceAnalysisWorker:
    """Background worker that processes images for face analysis."""

    def __init__(
        self,
        db: Database,
        drive_id: str | None = None,
        batch_size: int = 50,
        poll_interval: float = 2.0,
        status_callback: Callable[[str], None] | None = None,
    ):
        self.db = db
        self.drive_id = drive_id
        self.batch_size = batch_size
        self.poll_interval = poll_interval
        self.status_callback = status_callback

        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._drain_requested = threading.Event()

    def start(self) -> None:
        """Start the worker thread."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._drain_requested.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def request_drain(self) -> None:
        """Stop after processing remaining queued files."""
        self._drain_requested.set()

    def stop(self, wait: bool = False) -> None:
        """Stop the worker."""
        self._stop_event.set()
        self._drain_requested.set()
        if wait and self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)

    def is_running(self) -> bool:
        """Return True if worker thread is alive."""
        return bool(self._thread and self._thread.is_alive())

    def _notify(self, message: str) -> None:
        if self.status_callback:
            with contextlib.suppress(Exception):
                self.status_callback(message)

    def _run(self) -> None:
        analyzer = FaceAnalyzer(self.db)
        if not analyzer.is_available():
            logger.warning("Face analysis worker disabled: dependencies not available")
            return

        backfilled = self.db.backfill_face_status_from_existing_faces(self.drive_id)
        if backfilled:
            logger.info(f"Backfilled face analysis status for {backfilled} files")

        while not self._stop_event.is_set():
            files = self.db.get_image_files_missing_face_analysis(
                limit=self.batch_size,
                drive_id=self.drive_id,
            )

            if not files:
                if self._drain_requested.is_set():
                    break
                time.sleep(self.poll_interval)
                continue

            for file_record in files:
                if self._stop_event.is_set():
                    break
                try:
                    analyzer.analyze_file(file_record)
                except Exception as exc:
                    logger.warning(f"Face analysis failed for {file_record.path}: {exc}")
                    self.db.mark_faces_analyzed(
                        file_record.id,
                        faces_found=0,
                        error=str(exc),
                    )

            # Short sleep to avoid tight loops
            time.sleep(0.1)

        self._notify("Face analysis worker stopped.")
