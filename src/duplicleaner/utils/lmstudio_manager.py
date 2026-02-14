"""LMStudio model management via the LMStudioMonitorService.

This module provides automatic model detection and switching for LMStudio,
leveraging the existing LMStudioMonitorService running on localhost:5000.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum

import requests

from duplicleaner.utils.logging import get_logger

logger = get_logger(__name__)


class ModelType(Enum):
    """Model type categories for intelligent routing."""
    TEXT = "text"
    VISION = "vision"
    UNKNOWN = "unknown"


@dataclass
class ModelInfo:
    """Information about a loaded model."""
    name: str
    path: str | None = None
    type: ModelType = ModelType.UNKNOWN


class LMStudioManager:
    """Manages LMStudio model loading and switching via the Monitor Service API."""

    def __init__(
        self,
        monitor_url: str = "http://localhost:5000",
        lmstudio_api_url: str = "http://localhost:1234/v1",
        health_check_timeout: int = 5,
        model_load_timeout: int = 120,
    ) -> None:
        """
        Initialize LMStudio manager.

        Args:
            monitor_url: URL of LMStudioMonitorService (default: http://localhost:5000)
            lmstudio_api_url: URL of LMStudio API (default: http://localhost:1234/v1)
            health_check_timeout: Timeout for health checks in seconds
            model_load_timeout: Maximum time to wait for model loading in seconds
        """
        self.monitor_url = monitor_url.rstrip("/")
        self.lmstudio_api_url = lmstudio_api_url.rstrip("/")
        self.health_check_timeout = health_check_timeout
        self.model_load_timeout = model_load_timeout

        # Model type detection patterns
        self.vision_keywords = {"vl", "vision", "llava", "qwen2.5-vl", "qwen-vl"}
        self.text_keywords = {"instruct", "chat", "text", "llama", "qwen", "mistral", "dolphin"}

    def is_available(self) -> bool:
        """Check if LMStudioMonitorService is running and accessible."""
        try:
            response = requests.get(
                f"{self.monitor_url}/api/health",
                timeout=self.health_check_timeout,
            )
            return response.status_code == 200
        except Exception as exc:
            logger.debug("LMStudioMonitorService not available: %s", exc)
            return False

    def get_current_model(self) -> ModelInfo | None:
        """
        Get information about the currently loaded model.

        Returns:
            ModelInfo if a model is loaded, None otherwise
        """
        try:
            response = requests.get(
                f"{self.monitor_url}/api/health",
                timeout=self.health_check_timeout,
            )
            response.raise_for_status()
            data = response.json()

            if not data.get("lmStudioRunning"):
                logger.warning("LMStudio is not running")
                return None

            model_name = data.get("modelName")
            if not model_name:
                logger.warning("No model loaded in LMStudio")
                return None

            model_type = self._detect_model_type(model_name)
            return ModelInfo(name=model_name, type=model_type)

        except Exception as exc:
            logger.warning("Failed to get current model: %s", exc)
            return None

    def load_model(self, model_path: str) -> bool:
        """
        Load a specific model in LMStudio.

        Args:
            model_path: Absolute path to the .gguf model file

        Returns:
            True if model loaded successfully, False otherwise
        """
        try:
            logger.info("Requesting model load: %s", model_path)

            response = requests.post(
                f"{self.monitor_url}/LMStudioApi/model",
                json={"ModelPath": model_path},
                timeout=self.model_load_timeout,
            )

            if response.status_code == 200:
                logger.info("Model load request successful")
                # Wait for model to actually load
                return self.wait_for_model_ready(timeout=self.model_load_timeout)
            else:
                logger.error("Model load request failed: %s", response.text)
                return False

        except Exception as exc:
            logger.error("Failed to load model: %s", exc)
            return False

    def wait_for_model_ready(self, timeout: int = 120) -> bool:
        """
        Wait for a model to be loaded and ready.

        Args:
            timeout: Maximum time to wait in seconds

        Returns:
            True if model is ready, False if timeout
        """
        start_time = time.time()
        last_model = None

        logger.info("Waiting for model to load (timeout: %ds)", timeout)

        while time.time() - start_time < timeout:
            model_info = self.get_current_model()

            if model_info:
                # Check if it's a different model than when we started
                if last_model is None:
                    last_model = model_info.name
                    logger.info("Model loading: %s", model_info.name)
                elif model_info.name == last_model:
                    logger.info("Model ready: %s", model_info.name)
                    return True

            time.sleep(2)

        logger.error("Timeout waiting for model to load")
        return False

    def restart_lmstudio(self) -> bool:
        """
        Restart LMStudio via the Monitor Service.

        Returns:
            True if restart successful, False otherwise
        """
        try:
            logger.info("Requesting LMStudio restart")

            response = requests.post(
                f"{self.monitor_url}/LMStudioApi/restart",
                timeout=30,
            )

            if response.status_code == 200:
                logger.info("LMStudio restart successful")
                # Wait for it to come back online
                time.sleep(10)
                return self.wait_for_model_ready(timeout=60)
            else:
                logger.error("LMStudio restart failed: %s", response.text)
                return False

        except Exception as exc:
            logger.error("Failed to restart LMStudio: %s", exc)
            return False

    def get_available_models(self) -> list[str]:
        """
        Get list of available models from LMStudio.

        Returns:
            List of model names (may be empty if query fails)
        """
        try:
            response = requests.get(
                f"{self.monitor_url}/LMStudioApi/models",
                timeout=self.health_check_timeout,
            )
            response.raise_for_status()
            data = response.json()

            # Extract model names from response
            if isinstance(data, list):
                return [model.get("id", "") for model in data if isinstance(model, dict)]
            return []

        except Exception as exc:
            logger.warning("Failed to get available models: %s", exc)
            return []

    def _detect_model_type(self, model_name: str) -> ModelType:
        """
        Detect if a model is a text or vision model based on its name.

        Args:
            model_name: Name of the model

        Returns:
            ModelType indicating text or vision model
        """
        name_lower = model_name.lower()

        # Check for vision keywords first (more specific)
        if any(keyword in name_lower for keyword in self.vision_keywords):
            return ModelType.VISION

        # Check for text keywords
        if any(keyword in name_lower for keyword in self.text_keywords):
            return ModelType.TEXT

        # Default to unknown
        logger.warning("Could not determine model type for: %s", model_name)
        return ModelType.UNKNOWN

    def ensure_model_type(self, required_type: ModelType) -> bool:
        """
        Ensure a model of the required type is loaded.

        This method checks the current model and provides guidance if the wrong type is loaded.
        It does NOT automatically switch models, as the user needs to select which specific
        model to load (there may be multiple text or vision models available).

        Args:
            required_type: The required model type (TEXT or VISION)

        Returns:
            True if correct model type is loaded, False if wrong type or no model
        """
        current = self.get_current_model()

        if not current:
            logger.warning("No model loaded in LMStudio")
            return False

        if current.type == required_type:
            logger.info("Correct model type already loaded: %s (%s)", current.name, required_type.value)
            return True

        if current.type == ModelType.UNKNOWN:
            logger.warning(
                "Cannot determine model type for '%s'. Please verify it's a %s model.",
                current.name,
                required_type.value,
            )
            return False

        # Wrong model type
        logger.error(
            "Wrong model type loaded. Current: %s (%s), Required: %s",
            current.name,
            current.type.value,
            required_type.value,
        )
        return False

    def get_model_recommendation(self, required_type: ModelType) -> str:
        """
        Get a recommendation for which model to load.

        Args:
            required_type: The required model type

        Returns:
            String with model recommendation
        """
        if required_type == ModelType.TEXT:
            return (
                "For text processing, load a text model such as:\n"
                "  - Josiefied-DeepSeek-R1-Qwen3-8B-abliterated (recommended for documents)\n"
                "  - Llama-3.2-3B-Instruct\n"
                "  - Qwen2.5-3B-Instruct"
            )
        elif required_type == ModelType.VISION:
            return (
                "For image processing, load a vision model such as:\n"
                "  - Qwen2.5-VL-7B (recommended)\n"
                "  - LLaVA-v1.6-7B\n"
                "  - Any model with 'VL' or 'vision' in the name"
            )
        else:
            return "Unknown model type required"
