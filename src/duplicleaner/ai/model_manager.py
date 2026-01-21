"""AI model download manager.

Triggers downloads for optional AI models using their respective libraries.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable, Optional

from duplicleaner.utils.config import get_config
from duplicleaner.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ModelDownloadResult:
    model: str
    success: bool
    message: str


class ModelManager:
    """Download manager for AI models."""

    def __init__(self, progress_callback: Optional[Callable[[str], None]] = None) -> None:
        self.progress_callback = progress_callback

    def _notify(self, message: str) -> None:
        if self.progress_callback:
            try:
                self.progress_callback(message)
            except Exception:
                pass

    def download_faces(self) -> ModelDownloadResult:
        """Download InsightFace models (buffalo_l)."""
        try:
            import insightface
            from insightface.app import FaceAnalysis
        except Exception:
            return ModelDownloadResult("faces", False, "InsightFace not installed")

        config = get_config()
        models_dir = os.path.join(config.ai.models_directory, "insightface")
        os.environ.setdefault("INSIGHTFACE_HOME", models_dir)

        try:
            app = FaceAnalysis(name=config.ai.face_model)
            app.prepare(ctx_id=0 if config.ai.use_gpu else -1)
            return ModelDownloadResult("faces", True, "InsightFace model ready")
        except Exception as exc:
            return ModelDownloadResult("faces", False, f"InsightFace download failed: {exc}")

    def download_clip(self) -> ModelDownloadResult:
        """Download CLIP model weights."""
        try:
            import open_clip
            import torch
        except Exception:
            return ModelDownloadResult("clip", False, "open-clip-torch not installed")

        config = get_config()
        torch_home = os.path.join(config.ai.models_directory, "torch")
        os.environ.setdefault("TORCH_HOME", torch_home)

        try:
            model_name = config.ai.scene_model
            open_clip.create_model_and_transforms(model_name, pretrained="openai")
            return ModelDownloadResult("clip", True, "CLIP model ready")
        except Exception as exc:
            return ModelDownloadResult("clip", False, f"CLIP download failed: {exc}")

    def download_yolo(self) -> ModelDownloadResult:
        """Download YOLOv8 model weights."""
        try:
            from ultralytics import YOLO
        except Exception:
            return ModelDownloadResult("yolo", False, "Ultralytics not installed")

        config = get_config()
        model_name = f"{config.ai.object_model}.pt" if not config.ai.object_model.endswith(".pt") else config.ai.object_model

        try:
            YOLO(model_name)
            return ModelDownloadResult("yolo", True, "YOLO model ready")
        except Exception as exc:
            return ModelDownloadResult("yolo", False, f"YOLO download failed: {exc}")

    def download_ocr(self) -> ModelDownloadResult:
        """Download EasyOCR models."""
        try:
            import easyocr
        except Exception:
            return ModelDownloadResult("ocr", False, "EasyOCR not installed")

        config = get_config()
        model_dir = os.path.join(config.ai.models_directory, "easyocr")

        try:
            easyocr.Reader(
                config.ai.ocr_languages,
                gpu=config.ai.use_gpu,
                model_storage_directory=model_dir,
                download_enabled=True,
            )
            return ModelDownloadResult("ocr", True, "EasyOCR model ready")
        except Exception as exc:
            return ModelDownloadResult("ocr", False, f"EasyOCR download failed: {exc}")
