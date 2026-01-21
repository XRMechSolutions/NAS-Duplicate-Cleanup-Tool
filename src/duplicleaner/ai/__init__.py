"""AI modules for DupliCleaner.

Optional AI-powered features including face recognition,
scene classification, object detection, and OCR.
"""

from duplicleaner.ai.faces import (
    FaceAnalyzer,
    FaceCluster,
    FaceMatch,
    DetectedFace,
    FaceAnalysisProgress,
    AgeStage,
)
from duplicleaner.ai.pets import (
    PetAnalyzer,
    PetCluster,
    PetMatch,
    DetectedPet,
    PetAnalysisProgress,
)
from duplicleaner.ai.scenes import SceneClassifier
from duplicleaner.ai.objects import ObjectDetector
from duplicleaner.ai.quality import QualityScorer
from duplicleaner.ai.ocr import OCREngine
from duplicleaner.ai.model_manager import ModelManager, ModelDownloadResult

__all__ = [
    "FaceAnalyzer",
    "FaceCluster",
    "FaceMatch",
    "DetectedFace",
    "FaceAnalysisProgress",
    "AgeStage",
    "PetAnalyzer",
    "PetCluster",
    "PetMatch",
    "DetectedPet",
    "PetAnalysisProgress",
    "SceneClassifier",
    "ObjectDetector",
    "QualityScorer",
    "OCREngine",
    "ModelManager",
    "ModelDownloadResult",
]
