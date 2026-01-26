"""AI summary generation for images.

Supports OpenAI, Anthropic, and local Ollama-compatible endpoints.
"""

from __future__ import annotations

import base64
import json
import mimetypes
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from duplicleaner.db.database import Database
from duplicleaner.db.models import AISummary, FileRecord
from duplicleaner.utils.config import get_config
from duplicleaner.utils.keystore import AIProvider, get_keystore
from duplicleaner.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class SummaryProgress:
    """Progress tracking for summary generation."""
    total_files: int = 0
    processed_files: int = 0
    current_file: str = ""
    phase: str = "initializing"

    @property
    def percent_complete(self) -> float:
        if self.total_files == 0:
            return 0.0
        return (self.processed_files / self.total_files) * 100


class SummaryEngine:
    """Generate AI summaries for images."""

    def __init__(self, db: Database) -> None:
        self.db = db
        self.config = get_config()
        self.keystore = get_keystore()
        self.progress = SummaryProgress()

    def is_available(self) -> bool:
        provider = self.config.ai.summary_provider
        if provider == "local":
            return True
        if provider == "openai":
            return self.keystore.has_key(AIProvider.OPENAI)
        if provider == "anthropic":
            return self.keystore.has_key(AIProvider.ANTHROPIC)
        if provider == "google":
            return self.keystore.has_key(AIProvider.GOOGLE)
        return False

    def analyze_file(self, file_record: FileRecord) -> Optional[AISummary]:
        if not file_record.id:
            return None

        ext = (file_record.file_type or "").lower()
        doc_exts = set(self.config.ai.analysis_doc_extensions)
        data_exts = set(self.config.ai.analysis_data_extensions)

        if file_record.is_image:
            summary_text = self._generate_summary(file_record.path)
            if not summary_text:
                return None
            summary = AISummary(
                file_id=file_record.id,
                summary=summary_text,
                summary_model=self.config.ai.get_summary_model(),
                generated_at=datetime.now(),
                user_edited=False,
            )
            self.db.add_ai_summary(summary)
            return summary

        if ext in doc_exts or ext in data_exts or file_record.is_document:
            text = self._get_document_text(file_record.id)
            if not text:
                return None
            doc_summary = self._generate_text_summary(text)
            if not doc_summary:
                return None
            summary = AISummary(
                file_id=file_record.id,
                document_summary=doc_summary,
                summary_model=self.config.ai.get_summary_model(),
                generated_at=datetime.now(),
                user_edited=False,
            )
            self.db.add_ai_summary(summary)
            return summary

        return None

    def analyze_batch(self, file_records: list[FileRecord]) -> int:
        self.progress = SummaryProgress(
            total_files=len(file_records),
            phase="summarizing",
        )
        generated = 0
        for i, file_record in enumerate(file_records):
            self.progress.processed_files = i + 1
            self.progress.current_file = file_record.path
            if self.analyze_file(file_record):
                generated += 1
        self.progress.phase = "complete"
        return generated

    def _generate_summary(self, image_path: str) -> Optional[str]:
        provider = self.config.ai.summary_provider
        model = self.config.ai.get_summary_model()
        prompt = (
            "Describe the image in one concise sentence. "
            "Focus on people, setting, and notable objects."
        )

        image_b64, media_type = self._load_image_base64(image_path)
        if not image_b64:
            return None

        if provider == "local":
            return self._summarize_ollama(model, prompt, image_b64)
        if provider == "openai":
            key = self.keystore.get_key(AIProvider.OPENAI)
            if not key:
                return None
            return self._summarize_openai(model, key, prompt, image_b64, media_type)
        if provider == "anthropic":
            key = self.keystore.get_key(AIProvider.ANTHROPIC)
            if not key:
                return None
            return self._summarize_anthropic(model, key, prompt, image_b64, media_type)

        logger.warning("Unsupported summary provider: %s", provider)
        return None

    def _get_document_text(self, file_id: int) -> Optional[str]:
        result = self.db.get_ocr_result(file_id)
        if not result or not result.extracted_text:
            return None
        return result.extracted_text

    def _generate_text_summary(self, text: str) -> Optional[str]:
        provider = self.config.ai.summary_provider
        model = self.config.ai.get_summary_model()
        prompt = (
            "Summarize this document in 1-2 concise sentences. "
            "Focus on the main topic and key details."
        )
        snippet = text[:8000]

        if provider == "local":
            return self._summarize_ollama_text(model, prompt, snippet)
        if provider == "openai":
            key = self.keystore.get_key(AIProvider.OPENAI)
            if not key:
                return None
            return self._summarize_openai_text(model, key, prompt, snippet)
        if provider == "anthropic":
            key = self.keystore.get_key(AIProvider.ANTHROPIC)
            if not key:
                return None
            return self._summarize_anthropic_text(model, key, prompt, snippet)

        return None

    def _load_image_base64(self, image_path: str) -> tuple[Optional[str], str]:
        mime = mimetypes.guess_type(image_path)[0] or "image/jpeg"
        try:
            with open(image_path, "rb") as f:
                encoded = base64.b64encode(f.read()).decode("utf-8")
            return encoded, mime
        except Exception as exc:
            logger.warning("Failed to load image for summary: %s", exc)
            return None, mime

    def _summarize_openai(
        self,
        model: str,
        api_key: str,
        prompt: str,
        image_b64: str,
        media_type: str,
    ) -> Optional[str]:
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{image_b64}"}},
                    ],
                }
            ],
            "max_tokens": self.config.ai.summary_max_tokens,
            "temperature": self.config.ai.summary_temperature,
        }
        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                "https://api.openai.com/v1/chat/completions",
                data=data,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            return result["choices"][0]["message"]["content"].strip()
        except Exception as exc:
            logger.warning("OpenAI summary failed: %s", exc)
            return None

    def _summarize_anthropic(
        self,
        model: str,
        api_key: str,
        prompt: str,
        image_b64: str,
        media_type: str,
    ) -> Optional[str]:
        payload = {
            "model": model,
            "max_tokens": self.config.ai.summary_max_tokens,
            "temperature": self.config.ai.summary_temperature,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_b64}},
                    ],
                }
            ],
        }
        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                "https://api.anthropic.com/v1/messages",
                data=data,
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            content = result.get("content", [])
            if content:
                return content[0].get("text", "").strip() or None
            return None
        except Exception as exc:
            logger.warning("Anthropic summary failed: %s", exc)
            return None

    def _summarize_ollama(
        self,
        model: str,
        prompt: str,
        image_b64: str,
    ) -> Optional[str]:
        payload = {
            "model": model,
            "prompt": prompt,
            "images": [image_b64],
            "stream": False,
        }
        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                "http://localhost:11434/api/generate",
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            return str(result.get("response", "")).strip() or None
        except Exception as exc:
            logger.warning("Local summary failed: %s", exc)
            return None

    def _summarize_openai_text(
        self,
        model: str,
        api_key: str,
        prompt: str,
        text: str,
    ) -> Optional[str]:
        payload = {
            "model": model,
            "messages": [
                {"role": "user", "content": f"{prompt}\n\n{text}"},
            ],
            "max_tokens": self.config.ai.summary_max_tokens,
            "temperature": self.config.ai.summary_temperature,
        }
        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                "https://api.openai.com/v1/chat/completions",
                data=data,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            return result["choices"][0]["message"]["content"].strip()
        except Exception as exc:
            logger.warning("OpenAI text summary failed: %s", exc)
            return None

    def _summarize_anthropic_text(
        self,
        model: str,
        api_key: str,
        prompt: str,
        text: str,
    ) -> Optional[str]:
        payload = {
            "model": model,
            "max_tokens": self.config.ai.summary_max_tokens,
            "temperature": self.config.ai.summary_temperature,
            "messages": [
                {"role": "user", "content": f"{prompt}\n\n{text}"},
            ],
        }
        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                "https://api.anthropic.com/v1/messages",
                data=data,
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            content = result.get("content", [])
            if content:
                return content[0].get("text", "").strip() or None
            return None
        except Exception as exc:
            logger.warning("Anthropic text summary failed: %s", exc)
            return None

    def _summarize_ollama_text(
        self,
        model: str,
        prompt: str,
        text: str,
    ) -> Optional[str]:
        payload = {
            "model": model,
            "prompt": f"{prompt}\n\n{text}",
            "stream": False,
        }
        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                "http://localhost:11434/api/generate",
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            return str(result.get("response", "")).strip() or None
        except Exception as exc:
            logger.warning("Local text summary failed: %s", exc)
            return None
