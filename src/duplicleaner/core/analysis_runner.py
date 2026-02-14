"""Run metadata and AI analysis pipelines."""

from __future__ import annotations

import contextlib
import threading
from collections.abc import Callable
from dataclasses import dataclass, field

from duplicleaner.ai.documents import DocumentTextExtractor
from duplicleaner.ai.objects import ObjectDetector
from duplicleaner.ai.ocr import OCREngine
from duplicleaner.ai.scenes import SceneClassifier
from duplicleaner.ai.summaries import SummaryEngine
from duplicleaner.core.metadata_extractor import MetadataExtractor
from duplicleaner.db.database import Database
from duplicleaner.utils.config import get_config
from duplicleaner.utils.logging import get_logger
from duplicleaner.utils.profiling import profile_block

logger = get_logger(__name__)


@dataclass
class AnalysisOptions:
    """Options for analysis run."""
    include_metadata: bool = True
    include_scenes: bool = True
    include_objects: bool = True
    include_ocr: bool = True
    include_summaries: bool = False
    include_audio: bool = False
    include_images: bool = True
    include_documents: bool = True
    include_data_files: bool = False
    document_extensions: list[str] = field(default_factory=list)
    data_extensions: list[str] = field(default_factory=list)
    reanalyze_existing: bool = False
    drive_id: str | None = None
    batch_limit: int = 200


@dataclass
class AnalysisStats:
    """Summary stats for an analysis run."""
    metadata: int = 0
    scenes: int = 0
    objects: int = 0
    ocr: int = 0
    summaries: int = 0
    audio: int = 0


class AnalysisRunner:
    """Orchestrates metadata extraction and AI analysis."""

    def __init__(
        self,
        db: Database,
        status_callback: Callable[[str], None] | None = None,
        cancel_event: threading.Event | None = None,
    ) -> None:
        self.db = db
        self.config = get_config()
        self.status_callback = status_callback
        self.cancel_event = cancel_event or threading.Event()

    def run(self, options: AnalysisOptions) -> AnalysisStats:
        stats = AnalysisStats()
        with profile_block("analysis.run"):
            self._emit_preflight(options)
            if options.include_metadata and options.include_images:
                with profile_block("analysis.metadata"):
                    stats.metadata = self._run_metadata(options)
            if options.include_scenes and options.include_images:
                with profile_block("analysis.scenes"):
                    stats.scenes = self._run_scenes(options)
            if options.include_objects and options.include_images:
                with profile_block("analysis.objects"):
                    stats.objects = self._run_objects(options)
            if options.include_ocr:
                with profile_block("analysis.ocr"):
                    stats.ocr = self._run_ocr(options)
            if options.include_summaries:
                with profile_block("analysis.summaries"):
                    stats.summaries = self._run_summaries(options)
        return stats

    def _notify(self, message: str) -> None:
        if self.status_callback:
            with contextlib.suppress(Exception):
                self.status_callback(message)

    def _emit_preflight(self, options: AnalysisOptions) -> None:
        """Log how many files are eligible for analysis."""
        image_exts = self._image_extensions() if options.include_images else []
        doc_exts = options.document_extensions if options.include_documents else []
        data_exts = options.data_extensions if options.include_data_files else []

        total_images = self._count_files_by_extensions(image_exts, options.drive_id)
        total_docs = self._count_files_by_extensions(doc_exts, options.drive_id)
        total_data = self._count_files_by_extensions(data_exts, options.drive_id)

        self._notify(
            f"Analysis preflight: images {total_images}, docs {total_docs}, data {total_data}, "
            f"reanalyze={options.reanalyze_existing}"
        )

        if options.include_metadata and image_exts:
            missing = self._count_missing_metadata(image_exts, options.drive_id)
            self._notify(f"Preflight missing metadata: {missing}")
        if options.include_scenes and image_exts:
            missing = self._count_missing_scene_analysis(image_exts, options.drive_id)
            self._notify(f"Preflight missing scenes: {missing}")
        if options.include_objects and image_exts:
            missing = self._count_missing_scene_objects(image_exts, options.drive_id)
            self._notify(f"Preflight missing objects: {missing}")
        if options.include_ocr:
            if image_exts:
                missing = self._count_missing_ocr(image_exts, options.drive_id)
                self._notify(f"Preflight missing OCR (images): {missing}")
            if doc_exts or data_exts:
                missing = self._count_missing_ocr(doc_exts + data_exts, options.drive_id)
                self._notify(f"Preflight missing OCR (docs/data): {missing}")
        audio_exts = self._audio_extensions() if options.include_audio else []
        total_audio = self._count_files_by_extensions(audio_exts, options.drive_id)
        if total_audio > 0:
            self._notify(f"Preflight audio files: {total_audio}")
        if options.include_summaries:
            summary_exts = image_exts + doc_exts + data_exts + audio_exts
            missing = self._count_missing_summaries(summary_exts, options.drive_id)
            self._notify(f"Preflight missing summaries: {missing}")

    def _count_files_by_extensions(self, extensions: list[str], drive_id: str | None) -> int:
        if not extensions:
            return 0
        placeholders = ", ".join("?" for _ in extensions)
        query = f"""
            SELECT COUNT(*) FROM files
            WHERE is_deleted = FALSE
              AND LOWER(file_type) IN ({placeholders})
        """
        params: list = [ext.lower() for ext in extensions]
        if drive_id:
            query += " AND drive_id = ?"
            params.append(drive_id)
        with self.db.connection() as conn:
            return int(conn.execute(query, params).fetchone()[0])

    def _count_missing_metadata(self, extensions: list[str], drive_id: str | None) -> int:
        placeholders = ", ".join("?" for _ in extensions)
        query = f"""
            SELECT COUNT(*) FROM files f
            LEFT JOIN file_metadata m ON m.file_id = f.id
            WHERE f.is_deleted = FALSE
              AND LOWER(f.file_type) IN ({placeholders})
              AND m.file_id IS NULL
        """
        params: list = [ext.lower() for ext in extensions]
        if drive_id:
            query += " AND f.drive_id = ?"
            params.append(drive_id)
        with self.db.connection() as conn:
            return int(conn.execute(query, params).fetchone()[0])

    def _count_missing_scene_analysis(self, extensions: list[str], drive_id: str | None) -> int:
        placeholders = ", ".join("?" for _ in extensions)
        query = f"""
            SELECT COUNT(*) FROM files f
            LEFT JOIN scene_analysis s ON s.file_id = f.id
            WHERE f.is_deleted = FALSE
              AND LOWER(f.file_type) IN ({placeholders})
              AND s.file_id IS NULL
        """
        params: list = [ext.lower() for ext in extensions]
        if drive_id:
            query += " AND f.drive_id = ?"
            params.append(drive_id)
        with self.db.connection() as conn:
            return int(conn.execute(query, params).fetchone()[0])

    def _count_missing_scene_objects(self, extensions: list[str], drive_id: str | None) -> int:
        placeholders = ", ".join("?" for _ in extensions)
        query = f"""
            SELECT COUNT(*) FROM files f
            LEFT JOIN scene_analysis s ON s.file_id = f.id
            WHERE f.is_deleted = FALSE
              AND LOWER(f.file_type) IN ({placeholders})
              AND (s.file_id IS NULL OR s.objects IS NULL OR s.objects = '' OR s.objects = '[]')
        """
        params: list = [ext.lower() for ext in extensions]
        if drive_id:
            query += " AND f.drive_id = ?"
            params.append(drive_id)
        with self.db.connection() as conn:
            return int(conn.execute(query, params).fetchone()[0])

    def _count_missing_ocr(self, extensions: list[str], drive_id: str | None) -> int:
        placeholders = ", ".join("?" for _ in extensions)
        query = f"""
            SELECT COUNT(*) FROM files f
            LEFT JOIN ocr_results o ON o.file_id = f.id
            WHERE f.is_deleted = FALSE
              AND LOWER(f.file_type) IN ({placeholders})
              AND o.file_id IS NULL
        """
        params: list = [ext.lower() for ext in extensions]
        if drive_id:
            query += " AND f.drive_id = ?"
            params.append(drive_id)
        with self.db.connection() as conn:
            return int(conn.execute(query, params).fetchone()[0])

    def _count_missing_summaries(self, extensions: list[str], drive_id: str | None) -> int:
        placeholders = ", ".join("?" for _ in extensions)
        query = f"""
            SELECT COUNT(*) FROM files f
            LEFT JOIN ai_summaries a ON a.file_id = f.id
            WHERE f.is_deleted = FALSE
              AND LOWER(f.file_type) IN ({placeholders})
              AND a.file_id IS NULL
        """
        params: list = [ext.lower() for ext in extensions]
        if drive_id:
            query += " AND f.drive_id = ?"
            params.append(drive_id)
        with self.db.connection() as conn:
            return int(conn.execute(query, params).fetchone()[0])

    def _run_metadata(self, options: AnalysisOptions) -> int:
        extractor = MetadataExtractor(self.db)
        total = 0
        if options.reanalyze_existing:
            last_id = 0
            while not self.cancel_event.is_set():
                files = self.db.get_files_by_extensions_after_id(
                    extensions=self._image_extensions(),
                    last_id=last_id,
                    drive_id=options.drive_id,
                    limit=options.batch_limit,
                )
                if not files:
                    break
                self._notify(f"Metadata: processing {len(files)} images...")
                total += extractor.analyze_batch(files)
                last_id = files[-1].id or last_id
                if len(files) < options.batch_limit:
                    break
        else:
            while not self.cancel_event.is_set():
                files = self.db.get_image_files_missing_metadata(
                    limit=options.batch_limit,
                    drive_id=options.drive_id,
                )
                if not files:
                    break
                self._notify(f"Metadata: processing {len(files)} images...")
                total += extractor.analyze_batch(files)
                if len(files) < options.batch_limit:
                    break
        self._notify(f"Metadata: extracted for {total} files.")
        return total

    def _run_scenes(self, options: AnalysisOptions) -> int:
        classifier = SceneClassifier(
            self.db,
            model_name=self.config.ai.scene_model,
            pretrained="openai",
            use_gpu=self.config.ai.use_gpu,
        )
        if not classifier.is_available():
            self._notify("Scene analysis unavailable (missing CLIP dependencies).")
            return 0
        total = 0
        if options.reanalyze_existing:
            last_id = 0
            while not self.cancel_event.is_set():
                files = self.db.get_files_by_extensions_after_id(
                    extensions=self._image_extensions(),
                    last_id=last_id,
                    drive_id=options.drive_id,
                    limit=options.batch_limit,
                )
                if not files:
                    break
                self._notify(f"Scenes: processing {len(files)} images...")
                for file_record in files:
                    if self.cancel_event.is_set():
                        break
                    if classifier.analyze_file(file_record):
                        total += 1
                last_id = files[-1].id or last_id
                if len(files) < options.batch_limit:
                    break
        else:
            while not self.cancel_event.is_set():
                files = self.db.get_image_files_missing_scene_analysis(
                    limit=options.batch_limit,
                    drive_id=options.drive_id,
                )
                if not files:
                    break
                self._notify(f"Scenes: processing {len(files)} images...")
                for file_record in files:
                    if self.cancel_event.is_set():
                        break
                    if classifier.analyze_file(file_record):
                        total += 1
                if len(files) < options.batch_limit:
                    break
        self._notify(f"Scenes: analyzed {total} files.")
        return total

    def _run_objects(self, options: AnalysisOptions) -> int:
        detector = ObjectDetector(
            self.db,
            model_name=self.config.ai.object_model,
            use_gpu=self.config.ai.use_gpu,
            confidence_threshold=self.config.ai.object_confidence_threshold,
        )
        if not detector.is_available():
            self._notify("Object detection unavailable (missing YOLO dependencies).")
            return 0
        total = 0
        if options.reanalyze_existing:
            last_id = 0
            while not self.cancel_event.is_set():
                files = self.db.get_files_by_extensions_after_id(
                    extensions=self._image_extensions(),
                    last_id=last_id,
                    drive_id=options.drive_id,
                    limit=options.batch_limit,
                )
                if not files:
                    break
                self._notify(f"Objects: processing {len(files)} images...")
                for file_record in files:
                    if self.cancel_event.is_set():
                        break
                    labels = detector.analyze_file(file_record)
                    if labels is not None:
                        total += 1
                last_id = files[-1].id or last_id
                if len(files) < options.batch_limit:
                    break
        else:
            while not self.cancel_event.is_set():
                files = self.db.get_image_files_missing_scene_objects(
                    limit=options.batch_limit,
                    drive_id=options.drive_id,
                )
                if not files:
                    break
                self._notify(f"Objects: processing {len(files)} images...")
                for file_record in files:
                    if self.cancel_event.is_set():
                        break
                    labels = detector.analyze_file(file_record)
                    if labels is not None:
                        total += 1
                if len(files) < options.batch_limit:
                    break
        self._notify(f"Objects: analyzed {total} files.")
        return total

    def _run_ocr(self, options: AnalysisOptions) -> int:
        total = 0
        if options.include_images:
            engine = OCREngine(
                self.db,
                languages=self.config.ai.ocr_languages,
                use_gpu=self.config.ai.use_gpu,
            )
            if engine.is_available():
                if options.reanalyze_existing:
                    last_id = 0
                    while not self.cancel_event.is_set():
                        files = self.db.get_files_by_extensions_after_id(
                            extensions=self._image_extensions(),
                            last_id=last_id,
                            drive_id=options.drive_id,
                            limit=options.batch_limit,
                        )
                        if not files:
                            break
                        self._notify(f"OCR: processing {len(files)} images...")
                        for file_record in files:
                            if self.cancel_event.is_set():
                                break
                            if engine.analyze_file(file_record):
                                total += 1
                        last_id = files[-1].id or last_id
                        if len(files) < options.batch_limit:
                            break
                else:
                    while not self.cancel_event.is_set():
                        files = self.db.get_image_files_missing_ocr(
                            limit=options.batch_limit,
                            drive_id=options.drive_id,
                        )
                        if not files:
                            break
                        self._notify(f"OCR: processing {len(files)} images...")
                        for file_record in files:
                            if self.cancel_event.is_set():
                                break
                            if engine.analyze_file(file_record):
                                total += 1
                        if len(files) < options.batch_limit:
                            break
            else:
                self._notify("OCR unavailable (missing EasyOCR dependencies).")

        if options.include_documents or options.include_data_files:
            doc_exts = options.document_extensions or []
            data_exts = options.data_extensions or []
            extensions = []
            if options.include_documents:
                extensions.extend(doc_exts)
            if options.include_data_files:
                extensions.extend(data_exts)

            extractor = DocumentTextExtractor(self.db)
            if extensions:
                if options.reanalyze_existing:
                    last_id = 0
                    while not self.cancel_event.is_set():
                        files = self.db.get_files_by_extensions_after_id(
                            extensions=extensions,
                            last_id=last_id,
                            drive_id=options.drive_id,
                            limit=options.batch_limit,
                        )
                        if not files:
                            break
                        self._notify(f"Text: processing {len(files)} documents...")
                        total += extractor.analyze_batch(files)
                        last_id = files[-1].id or last_id
                        if len(files) < options.batch_limit:
                            break
                else:
                    while not self.cancel_event.is_set():
                        files = self.db.get_files_missing_ocr_by_extensions(
                            extensions=extensions,
                            limit=options.batch_limit,
                            drive_id=options.drive_id,
                        )
                        if not files:
                            break
                        self._notify(f"Text: processing {len(files)} documents...")
                        total += extractor.analyze_batch(files)
                        if len(files) < options.batch_limit:
                            break

        self._notify(f"OCR/Text: extracted for {total} files.")
        return total

    def _run_summaries(self, options: AnalysisOptions) -> int:
        engine = SummaryEngine(self.db)
        if not engine.is_available():
            self._notify("AI summaries unavailable (missing API key or provider).")
            return 0
        total = 0
        extensions = []
        if options.include_images:
            extensions.extend(self._image_extensions())
        if options.include_documents and options.document_extensions:
            extensions.extend(options.document_extensions)
        if options.include_data_files and options.data_extensions:
            extensions.extend(options.data_extensions)
        if options.include_audio:
            extensions.extend(self._audio_extensions())

        if options.reanalyze_existing:
            last_id = 0
            while not self.cancel_event.is_set():
                files = self.db.get_files_by_extensions_after_id(
                    extensions=extensions,
                    last_id=last_id,
                    drive_id=options.drive_id,
                    limit=options.batch_limit,
                )
                if not files:
                    break
                self._notify(f"Summaries: processing {len(files)} files...")
                for file_record in files:
                    if self.cancel_event.is_set():
                        break
                    if engine.analyze_file(file_record):
                        total += 1
                last_id = files[-1].id or last_id
                if len(files) < options.batch_limit:
                    break
        else:
            while not self.cancel_event.is_set():
                files = self.db.get_files_missing_summaries_by_extensions(
                    extensions=extensions,
                    limit=options.batch_limit,
                    drive_id=options.drive_id,
                )
                if not files:
                    break
                self._notify(f"Summaries: processing {len(files)} files...")
                for file_record in files:
                    if self.cancel_event.is_set():
                        break
                    if engine.analyze_file(file_record):
                        total += 1
                if len(files) < options.batch_limit:
                    break
        self._notify(f"Summaries: generated for {total} files.")
        return total

    def _image_extensions(self) -> list[str]:
        return [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif", ".webp", ".heic", ".heif"]

    def _audio_extensions(self) -> list[str]:
        return [".mp3", ".wav", ".m4a", ".flac", ".ogg", ".aac", ".wma", ".opus"]
