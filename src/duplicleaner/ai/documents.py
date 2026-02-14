"""Document text extraction for DupliCleaner."""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from duplicleaner.db.database import Database
from duplicleaner.db.models import FileRecord, OCRResult
from duplicleaner.utils.logging import get_logger

logger = get_logger(__name__)

MAX_TEXT_CHARS = 200000

HAS_PDFMINER = False
try:
    from pdfminer.high_level import extract_text as pdf_extract_text
    HAS_PDFMINER = True
except Exception:
    HAS_PDFMINER = False

HAS_DOCX = False
try:
    import docx
    HAS_DOCX = True
except Exception:
    HAS_DOCX = False


@dataclass
class DocumentProgress:
    """Progress tracking for document text extraction."""
    total_files: int = 0
    processed_files: int = 0
    current_file: str = ""
    phase: str = "initializing"

    @property
    def percent_complete(self) -> float:
        if self.total_files == 0:
            return 0.0
        return (self.processed_files / self.total_files) * 100


class DocumentTextExtractor:
    """Extract text from document and text-based files."""

    def __init__(self, db: Database) -> None:
        self.db = db
        self.progress = DocumentProgress()

    def analyze_file(self, file_record: FileRecord) -> OCRResult | None:
        if not file_record.id:
            return None

        text = self.extract_text(file_record.path)
        if not text:
            return None

        result = OCRResult(
            file_id=file_record.id,
            extracted_text=text,
            confidence=1.0,
            language="en",
            created_at=datetime.now(),
        )
        self.db.add_ocr_result(result)
        return result

    def analyze_batch(self, file_records: list[FileRecord]) -> int:
        self.progress = DocumentProgress(
            total_files=len(file_records),
            phase="extracting",
        )
        extracted = 0
        for i, file_record in enumerate(file_records):
            self.progress.processed_files = i + 1
            self.progress.current_file = file_record.path
            if self.analyze_file(file_record):
                extracted += 1
        self.progress.phase = "complete"
        return extracted

    def extract_text(self, file_path: str) -> str | None:
        path = Path(file_path)
        ext = path.suffix.lower()

        if ext == ".pdf":
            return self._extract_pdf_text(file_path)
        if ext == ".docx":
            return self._extract_docx_text(file_path)
        if ext == ".rtf":
            text = self._read_text_file(file_path)
            return self._strip_rtf(text) if text else None

        if ext in {".txt", ".md", ".csv", ".tsv", ".json", ".xml", ".yaml", ".yml", ".ini", ".log"}:
            return self._read_text_file(file_path)

        if ext in {".odt", ".pptx", ".xlsx"}:
            return self._extract_ooxml_text(file_path, ext)

        return None

    def _read_text_file(self, file_path: str) -> str | None:
        try:
            with open(file_path, encoding="utf-8", errors="ignore") as f:
                text = f.read(MAX_TEXT_CHARS + 1)
            if not text:
                return None
            if len(text) > MAX_TEXT_CHARS:
                text = text[:MAX_TEXT_CHARS]
            return text.strip()
        except Exception as exc:
            logger.debug("Text read failed for %s: %s", file_path, exc)
            return None

    def _extract_pdf_text(self, file_path: str) -> str | None:
        if not HAS_PDFMINER:
            logger.warning("pdfminer.six not installed. PDF text extraction disabled.")
            return None
        try:
            text = pdf_extract_text(file_path) or ""
            text = text.strip()
            if len(text) > MAX_TEXT_CHARS:
                text = text[:MAX_TEXT_CHARS]
            return text or None
        except Exception as exc:
            logger.debug("PDF extraction failed for %s: %s", file_path, exc)
            return None

    def _extract_docx_text(self, file_path: str) -> str | None:
        if not HAS_DOCX:
            return self._extract_ooxml_text(file_path, ".docx")
        try:
            doc = docx.Document(file_path)
            parts = [p.text for p in doc.paragraphs if p.text]
            text = "\n".join(parts).strip()
            if len(text) > MAX_TEXT_CHARS:
                text = text[:MAX_TEXT_CHARS]
            return text or None
        except Exception as exc:
            logger.debug("DOCX extraction failed for %s: %s", file_path, exc)
            return None

    def _extract_ooxml_text(self, file_path: str, ext: str) -> str | None:
        try:
            with zipfile.ZipFile(file_path) as zf:
                texts = []
                if ext == ".docx":
                    paths = [p for p in zf.namelist() if p.startswith("word/") and p.endswith(".xml")]
                elif ext == ".pptx":
                    paths = [p for p in zf.namelist() if p.startswith("ppt/slides/") and p.endswith(".xml")]
                elif ext == ".xlsx":
                    paths = [p for p in zf.namelist() if p.startswith("xl/") and p.endswith(".xml")]
                elif ext == ".odt":
                    paths = [p for p in zf.namelist() if p.endswith("content.xml")]
                else:
                    paths = []

                for path in paths:
                    try:
                        data = zf.read(path).decode("utf-8", errors="ignore")
                        stripped = re.sub(r"<[^>]+>", " ", data)
                        stripped = re.sub(r"\s+", " ", stripped).strip()
                        if stripped:
                            texts.append(stripped)
                    except Exception:
                        continue

                text = " ".join(texts).strip()
                if len(text) > MAX_TEXT_CHARS:
                    text = text[:MAX_TEXT_CHARS]
                return text or None
        except Exception as exc:
            logger.debug("OOXML extraction failed for %s: %s", file_path, exc)
            return None

    def _strip_rtf(self, text: str) -> str:
        cleaned = re.sub(r"\\'[0-9a-fA-F]{2}", "", text)
        cleaned = re.sub(r"\\[a-zA-Z]+-?\d* ?", "", cleaned)
        cleaned = cleaned.replace("{", "").replace("}", "")
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned.strip()
