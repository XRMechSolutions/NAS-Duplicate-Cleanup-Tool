"""AI modules for DupliCleaner.

Optional AI-powered features including face recognition,
scene classification, object detection, and OCR.
"""

from duplicleaner.ai.faces import (
    AgeStage,
    DetectedFace,
    FaceAnalysisProgress,
    FaceAnalyzer,
    FaceCluster,
    FaceMatch,
    TemporalChainResult,
)
from duplicleaner.ai.celebrities import (
    CelebrityIdentification,
    CelebrityIdentifier,
    CelebrityProgress,
)
from duplicleaner.ai.model_manager import ModelDownloadResult, ModelManager
from duplicleaner.ai.objects import ObjectDetector
from duplicleaner.ai.ocr import OCREngine
from duplicleaner.ai.pets import (
    DetectedPet,
    PetAnalysisProgress,
    PetAnalyzer,
    PetCluster,
    PetMatch,
)
from duplicleaner.ai.quality import QualityScorer
from duplicleaner.ai.scenes import SceneClassifier

__all__ = [
    "FaceAnalyzer",
    "FaceCluster",
    "FaceMatch",
    "DetectedFace",
    "FaceAnalysisProgress",
    "AgeStage",
    "TemporalChainResult",
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
    "CelebrityIdentifier",
    "CelebrityIdentification",
    "CelebrityProgress",
]
