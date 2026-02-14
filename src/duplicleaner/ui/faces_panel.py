"""Faces and Pets Panel for DupliCleaner.

Dear PyGui UI component for face recognition and pet tracking.
"""

import contextlib
import os
import queue
import subprocess
import threading
import time
from collections import deque
from collections.abc import Callable

import dearpygui.dearpygui as dpg
import numpy as np
from PIL import Image, ImageOps

from duplicleaner.ai.faces import FaceAnalysisProgress, FaceAnalyzer, FaceCluster
from duplicleaner.ai.pets import PetAnalysisProgress, PetAnalyzer, PetCluster
from duplicleaner.db.database import get_database
from duplicleaner.db.models import Face, Person, PetDetection
from duplicleaner.ui.theme import get_accent_color, get_status_color, get_text_color
from duplicleaner.utils.config import get_config, save_config
from duplicleaner.utils.logging import get_logger

logger = get_logger(__name__)


class FacesPanel:
    """UI panel for face recognition and pet tracking."""

    # Tag constants
    TAG_PANEL = "faces_panel"
    TAG_TABS = "faces_tabs"
    TAG_FACES_TAB = "faces_tab"
    TAG_PETS_TAB = "pets_tab"
    TAG_CLUSTER_VIEW = "face_cluster_view"
    TAG_PEOPLE_VIEW = "face_people_view"
    TAG_PET_CLUSTER_VIEW = "pet_cluster_view"
    TAG_PETS_VIEW = "pets_list_view"
    TAG_NAME_DIALOG = "name_dialog"
    TAG_PET_NAME_DIALOG = "pet_name_dialog"
    TAG_TIMELINE_DIALOG = "timeline_dialog"
    TAG_PROGRESS_DIALOG = "analysis_progress_dialog"
    TAG_TEXTURE_REGISTRY = "faces_texture_registry"
    TAG_RUN_FACE_BUTTON = "run_face_analysis_button"
    TAG_FACE_ANALYSIS_STATUS = "face_analysis_status_text"
    TAG_FACE_SETTINGS_GROUP = "face_settings_group"
    TAG_FACE_DET_THRESHOLD = "face_det_threshold"
    TAG_FACE_MATCH_THRESHOLD = "face_match_threshold"
    TAG_FACE_CLUSTER_THRESHOLD = "face_cluster_threshold"
    TAG_FACE_RESET_MODE = "face_reset_mode"
    TAG_FACE_RESET_BUTTON = "face_reset_button"
    TAG_FACE_RESET_SCOPE = "face_reset_scope"
    TAG_ASSIGN_DIALOG = "assign_person_dialog"
    TAG_ASSIGN_LIST = "assign_person_list"
    TAG_ASSIGN_BUTTON = "assign_person_button"
    TAG_FACE_PREVIEW_DIALOG = "face_preview_dialog"
    TAG_FACE_PREVIEW_IMAGE = "face_preview_image"
    TAG_FACE_PREVIEW_TEXT = "face_preview_text"
    TAG_FACE_PREVIEW_EXCLUDE = "face_preview_exclude"
    TAG_FACE_PREVIEW_DRAW = "face_preview_draw"
    TAG_FACE_PREVIEW_SAVE = "face_preview_save"
    TAG_FACE_PREVIEW_ROTATE_LEFT = "face_preview_rotate_left"
    TAG_FACE_PREVIEW_ROTATE_RIGHT = "face_preview_rotate_right"
    TAG_SPLIT_DIALOG = "face_split_dialog"
    TAG_SPLIT_CONTAINER = "face_split_container"
    TAG_SPLIT_STATUS = "face_split_status"
    TAG_SPLIT_ASSIGN = "face_split_assign"
    TAG_SPLIT_NAME = "face_split_name"

    # New tags for Phase 1-3 features
    TAG_RESET_CONFIRM_DIALOG = "reset_confirm_dialog"
    TAG_RESET_CONFIRM_TEXT = "reset_confirm_text"
    TAG_RESET_CONFIRM_COUNT = "reset_confirm_count"
    TAG_EDIT_PERSON_DIALOG = "edit_person_dialog"
    TAG_DELETE_PERSON_DIALOG = "delete_person_dialog"
    TAG_SHOW_HIDDEN_CHECKBOX = "show_hidden_checkbox"
    TAG_PEOPLE_SEARCH = "people_search_input"
    TAG_ALL_FACES_DIALOG = "all_faces_dialog"
    TAG_ALL_FACES_CONTAINER = "all_faces_container"
    TAG_NAME_DIALOG_FACES = "name_dialog_faces"
    TAG_INTERMEDIATE_CLUSTERS_DIALOG = "intermediate_clusters_dialog"
    TAG_INTERMEDIATE_CONTAINER = "intermediate_container"
    TAG_MIN_PHOTOS_FILTER_CHECKBOX = "min_photos_filter_checkbox"
    TAG_MIN_PHOTOS_INPUT = "min_photos_input"

    # Context menu tags
    TAG_CLUSTER_CONTEXT_MENU = "faces_cluster_ctx_menu"
    TAG_PEOPLE_CONTEXT_MENU = "faces_people_ctx_menu"
    TAG_GALLERY_CONTEXT_MENU = "faces_gallery_ctx_menu"

    # Tags for Person Photo Gallery
    TAG_PERSON_GALLERY_DIALOG = "person_gallery_dialog"
    TAG_PERSON_GALLERY_TITLE = "person_gallery_title"
    TAG_PERSON_GALLERY_INFO = "person_gallery_info"
    TAG_PERSON_GALLERY_CONTAINER = "person_gallery_container"
    TAG_PERSON_GALLERY_SORT = "person_gallery_sort"
    TAG_PHOTO_PREVIEW_DIALOG = "photo_preview_dialog"
    TAG_PHOTO_PREVIEW_IMAGE = "photo_preview_image"
    TAG_PHOTO_PREVIEW_INFO = "photo_preview_info"
    TAG_PHOTO_PREVIEW_CONTAINER = "photo_preview_container"
    TAG_CHOOSE_FACE_DIALOG = "choose_face_dialog"
    TAG_CHOOSE_FACE_CONTAINER = "choose_face_container"

    # Tags for timeline tabs and cross-age linking
    TAG_TIMELINE_TAB_BAR = "timeline_tab_bar"
    TAG_TIMELINE_TAB = "timeline_photos_tab"
    TAG_CHAIN_TAB = "timeline_chain_tab"
    TAG_GAPS_TAB = "timeline_gaps_tab"
    TAG_TIMELINE_PHOTOS_CONTENT = "timeline_photos_content"
    TAG_CHAIN_CONTENT = "timeline_chain_content"
    TAG_GAPS_CONTENT = "timeline_gaps_content"
    TAG_CROSS_AGE_DIALOG = "cross_age_linking_dialog"
    TAG_CROSS_AGE_CONTAINER = "cross_age_container"

    # Tags for Re-match Results dialog
    TAG_REMATCH_DIALOG = "rematch_results_dialog"
    TAG_REMATCH_CONTAINER = "rematch_results_container"
    TAG_REMATCH_HEADER = "rematch_results_header"

    # Tags for Relationships and Family Groups
    TAG_RELATIONSHIP_DIALOG = "relationship_dialog"
    TAG_RELATIONSHIP_PERSON_COMBO = "relationship_person_combo"
    TAG_RELATIONSHIP_TYPE_COMBO = "relationship_type_combo"
    TAG_FAMILY_GROUP_DIALOG = "family_group_dialog"
    TAG_FAMILY_GROUP_NAME_INPUT = "family_group_name_input"
    TAG_FAMILY_VIEW_CONTAINER = "family_group_view_container"
    TAG_FAMILY_MEMBER_DIALOG = "add_family_member_dialog"
    TAG_FAMILY_MEMBER_COMBO = "family_member_person_combo"
    TAG_FAMILY_MEMBER_ROLE_INPUT = "family_member_role_input"
    TAG_COOCCURRENCE_DIALOG = "cooccurrence_dialog"
    TAG_COOCCURRENCE_CONTAINER = "cooccurrence_container"

    # Tags for Celebrity Identification
    TAG_CELEBRITY_BUTTON = "identify_celebrities_btn"
    TAG_CELEBRITY_REVIEW_DIALOG = "celebrity_review_dialog"
    TAG_CELEBRITY_REVIEW_CONTAINER = "celebrity_review_container"
    TAG_CELEBRITY_REVIEW_STATUS = "celebrity_review_status"
    TAG_CELEBRITY_PROGRESS_DIALOG = "celebrity_progress_dialog"
    TAG_CELEBRITY_PROGRESS_BAR = "celebrity_progress_bar"
    TAG_CELEBRITY_PROGRESS_TEXT = "celebrity_progress_text"
    TAG_CELEBRITY_PENDING_COUNT = "celebrity_pending_count"
    TAG_CELEBRITY_ENABLED = "celebrity_enabled_checkbox"
    TAG_CELEBRITY_PROVIDER = "celebrity_provider_combo"
    TAG_CELEBRITY_AUTO_THRESHOLD = "celebrity_auto_threshold"
    TAG_CELEBRITY_MIN_CONFIDENCE = "celebrity_min_confidence"

    # Image extensions for preview
    IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff', '.tif', '.heic', '.heif'}

    # Thumbnail sizes
    GALLERY_THUMB_SIZE = 120
    PHOTO_PREVIEW_SIZE = 550

    def __init__(
        self,
        parent: int | str,
        on_photo_selected: Callable[[int], None] | None = None,
        on_status_update: Callable[[str], None] | None = None,
    ):
        """Initialize the faces panel.

        Args:
            parent: Parent window/container tag
            on_photo_selected: Callback when user selects a photo to view
        """
        self.parent = parent
        self.on_photo_selected = on_photo_selected
        self.on_status_update = on_status_update

        self.db = get_database()
        self.config = get_config()

        # Analyzers (created lazily with thread-safe initialization)
        self._face_analyzer: FaceAnalyzer | None = None
        self._pet_analyzer: PetAnalyzer | None = None
        self._analyzer_lock = threading.Lock()

        # Current state
        self._face_clusters: list[FaceCluster] = []
        self._pet_clusters: list[PetCluster] = []
        self._selected_cluster_id: int | None = None
        self._selected_cluster_snapshot: FaceCluster | None = None
        self._selected_person_id: int | None = None
        self._selected_pet_id: int | None = None
        self._current_view = "clusters"  # clusters, people, pets
        self._cluster_sort_mode: str = "default"  # default, closest, furthest, similar
        self._assign_person_map: list[tuple[str, int]] = []
        self._assign_mode: str = "cluster"
        self._name_mode: str = "cluster"
        self._drive_scope_map: list[tuple[str, str | None]] = []

        # Analysis thread
        self._analysis_thread: threading.Thread | None = None
        self._is_analyzing = False
        self._background_face_analysis = False
        self._auto_refresh_active = False
        self._auto_refresh_thread: threading.Thread | None = None
        self._is_clustering = False
        self._last_face_count = 0
        self._last_unassigned_faces = 0
        self._last_cluster_time = 0.0
        self._auto_refresh_interval = 6.0
        self._auto_cluster_interval = 20.0
        self._pause_auto_refresh = False
        self._pending_cluster_refresh = False
        self._pending_stats_refresh = False
        self._pending_cluster_done = False
        self._pending_auto_cluster = False
        self._pending_people_refresh = False
        self._pending_rematch_results: tuple[int, list] | None = None
        self._rematch_suggestions: list = []
        self._rematch_needs_refresh: bool = False
        self._last_rematch_refresh_time: float = 0.0

        # Thumbnail cache
        self._face_textures: dict[str, str] = {}
        self._pet_textures: dict[str, str] = {}
        self._texture_counter = 0
        self._texture_queue: queue.Queue = queue.Queue()
        self._texture_results: deque = deque()
        self._texture_requests: set[str] = set()
        self._texture_results_lock = threading.Lock()
        self._texture_worker_stop = threading.Event()
        self._texture_worker_threads: list[threading.Thread] = []
        self._num_texture_workers = 4  # Multiple workers for parallel loading
        self._preview_texture_tag: str | None = None
        self._preview_file_id: int | None = None
        self._preview_face_id: int | None = None
        self._preview_bbox: tuple[int, int, int, int] | None = None
        self._preview_scale: float = 1.0
        self._preview_display_size: tuple[int, int] = (1, 1)
        self._preview_orientation: int = 1
        self._preview_raw_size: tuple[int, int] = (1, 1)
        self._preview_dragging = False
        self._preview_drag_offset: tuple[float, float] = (0.0, 0.0)
        self._preview_resize_handle: str | None = None
        self._preview_hover_handle: str | None = None
        self._preview_resize_start: tuple[float, float] = (0.0, 0.0)
        self._preview_bbox_start: tuple[int, int, int, int] | None = None
        self._split_cluster_id: int | None = None
        self._split_face_ids: list[int] = []
        self._split_selected: set[int] = set()
        self._cluster_run_id: int | None = None
        self._intermediate_person_id: int | None = None
        self._intermediate_suggestions: list[dict] = []
        self._intermediate_auto_assigned: int = 0
        self._intermediate_needs_refresh: bool = False
        self._last_intermediate_refresh_time: float = 0.0
        self._total_clusters: int = 0
        self._filtered_clusters: int = 0

        # New state for Phase 1-3 features
        self._pending_reset_mode: str | None = None
        self._pending_reset_scope: str | None = None
        self._pending_reset_drive_id: str | None = None
        self._edit_person_id: int | None = None
        self._delete_person_id: int | None = None
        self._show_hidden_people: bool = False
        self._people_search_filter: str = ""

        # Person gallery state
        self._gallery_person_id: int | None = None
        self._gallery_faces: list = []
        self._gallery_sort: str = "date_desc"

        # View All dialog state
        self._all_faces_cluster_id: int | None = None
        self._all_faces_face_ids: list[int] = []
        self._all_faces_needs_refresh: bool = False
        self._all_faces_last_loaded: int = 0
        self._all_faces_stuck_count: int = 0
        self._gallery_selected_faces: set[int] = set()  # Selected face IDs for bulk operations
        self._gallery_removed_faces: set[int] = set()  # Faces marked as removed (for visual feedback)
        self._gallery_person_embeddings: list = []  # Cached person embeddings for similarity
        self._gallery_similarity_cache: dict[int, float] = {}  # Cached similarity scores
        self._gallery_photo_textures: dict[str, str] = {}
        self._gallery_texture_counter: int = 0
        self._photo_preview_texture: str | None = None
        self._photo_preview_file_path: str | None = None
        self._photo_preview_face_id: int | None = None
        self._faces_tab_active = False
        self._clusters_loaded = False
        self._pending_face_ui_refresh = False
        self._pending_gallery_refresh = False
        self._last_cluster_refresh_time = 0.0
        self._last_gallery_refresh_time = 0.0
        self._gallery_needs_refresh = False
        self._max_clusters_to_load = 40  # Start with first 40 clusters, increase as textures load
        self._last_missing_texture_count = 0
        self._stuck_refresh_count = 0
        self._last_scroll_y = 0.0  # Track scroll position for virtual scrolling

        # Context menu state
        self._ctx_menu_shown = False
        self._ctx_menu_open_time = 0.0
        self._ctx_cluster_id: int | None = None
        self._ctx_cluster_face_ids: list[int] = []
        self._ctx_person_id: int | None = None
        self._ctx_face_id: int | None = None
        self._ctx_file_id: int | None = None
        self._ctx_file_path: str | None = None
        self._cluster_handler_registries: list[int | str] = []
        self._people_row_handler_registries: list[int | str] = []
        self._gallery_card_handler_registries: list[int | str] = []

        # Relationship / family group state
        self._relationship_person_id: int | None = None
        self._family_group_id: int | None = None
        self._add_member_group_id: int | None = None
        self._family_handler_registries: list[int | str] = []

        # Celebrity identification state
        self._celebrity_identifier = None  # Lazy-loaded CelebrityIdentifier
        self._celebrity_thread: threading.Thread | None = None
        self._celebrity_cancel_event = threading.Event()
        self._celebrity_pending_results: list | None = None
        self._celebrity_review_handler_registries: list[int | str] = []

        # Build UI
        self._build_ui()
        self._create_context_menus()
        self._start_texture_worker()

    @property
    def face_analyzer(self) -> FaceAnalyzer:
        """Get or create face analyzer (thread-safe)."""
        if self._face_analyzer is None:
            with self._analyzer_lock:
                # Double-check after acquiring lock
                if self._face_analyzer is None:
                    self._face_analyzer = FaceAnalyzer(self.db)
        return self._face_analyzer

    @property
    def pet_analyzer(self) -> PetAnalyzer:
        """Get or create pet analyzer (thread-safe)."""
        if self._pet_analyzer is None:
            with self._analyzer_lock:
                # Double-check after acquiring lock
                if self._pet_analyzer is None:
                    self._pet_analyzer = PetAnalyzer(
                        self.db,
                        use_gpu=self.config.ai.use_gpu,
                        confidence_threshold=self.config.ai.pet_detection_threshold,
                        pets_only_mode=self.config.ai.pets_only_mode,
                    )
        return self._pet_analyzer

    def _build_ui(self) -> None:
        """Build the panel UI."""
        with dpg.child_window(parent=self.parent, tag=self.TAG_PANEL, autosize_x=True, autosize_y=True):
            # Header
            dpg.add_text("Faces & Pets", color=get_accent_color())
            dpg.add_separator()
            dpg.add_spacer(height=5)

            # Action buttons
            with dpg.group(horizontal=True):
                dpg.add_button(
                    label="Run Face Analysis",
                    tag=self.TAG_RUN_FACE_BUTTON,
                    callback=self._on_run_face_analysis,
                )
                dpg.add_button(
                    label="Run Pet Analysis",
                    tag="run_pet_analysis_btn",
                    callback=self._on_run_pet_analysis,
                )
                dpg.add_button(
                    label="Cluster Faces",
                    tag="cluster_faces_btn",
                    callback=self._on_cluster_faces,
                )
                dpg.add_button(
                    label="Cluster Pets",
                    tag="cluster_pets_btn",
                    callback=self._on_cluster_pets,
                )
                dpg.add_button(
                    label="Re-match Known",
                    tag="rematch_known_btn",
                    callback=self._on_rematch_known,
                )
                dpg.add_button(
                    label="Identify Celebrities",
                    tag=self.TAG_CELEBRITY_BUTTON,
                    callback=self._on_identify_celebrities,
                )
                dpg.add_button(label="Refresh", callback=self._refresh)
                dpg.add_button(label="Export", callback=self._on_export_persons)
                dpg.add_text("", tag=self.TAG_FACE_ANALYSIS_STATUS, color=get_status_color("warning"))
                dpg.add_button(
                    label="",
                    tag=self.TAG_CELEBRITY_PENDING_COUNT,
                    callback=self._show_celebrity_review_dialog,
                    show=False,
                    small=True,
                )

            dpg.add_spacer(height=10)

            # Face analysis settings
            with dpg.collapsing_header(label="Face Analysis Settings", default_open=False, tag=self.TAG_FACE_SETTINGS_GROUP):
                dpg.add_text("Detection confidence threshold")
                dpg.add_slider_float(
                    tag=self.TAG_FACE_DET_THRESHOLD,
                    default_value=self.config.ai.face_detection_threshold,
                    min_value=0.1,
                    max_value=0.99,
                    format="%.2f",
                    width=300,
                    callback=self._on_face_settings_changed,
                )
                dpg.add_text("Recognition similarity threshold")
                dpg.add_slider_float(
                    tag=self.TAG_FACE_MATCH_THRESHOLD,
                    default_value=self.config.ai.face_recognition_threshold,
                    min_value=0.3,
                    max_value=0.99,
                    format="%.2f",
                    width=300,
                    callback=self._on_face_settings_changed,
                )
                dpg.add_text("Clustering similarity threshold")
                dpg.add_slider_float(
                    tag=self.TAG_FACE_CLUSTER_THRESHOLD,
                    default_value=self.config.ai.face_clustering_threshold,
                    min_value=0.3,
                    max_value=0.99,
                    format="%.2f",
                    width=300,
                    callback=self._on_face_settings_changed,
                )
                dpg.add_text(
                    "Tip: Raise detection threshold to reduce false positives.",
                    color=get_text_color("disabled"),
                )
                dpg.add_spacer(height=8)
                with dpg.group(horizontal=True):
                    dpg.add_text("Reset faces:")
                    dpg.add_combo(
                        tag=self.TAG_FACE_RESET_MODE,
                        items=[
                            "Clear all faces",
                            "Clear low-confidence faces",
                            "Clear unassigned faces",
                        ],
                        default_value="Clear low-confidence faces",
                        width=220,
                    )
                    dpg.add_combo(
                        tag=self.TAG_FACE_RESET_SCOPE,
                        items=["All Drives"],
                        default_value="All Drives",
                        width=160,
                    )
                    dpg.add_button(
                        label="Clear",
                        tag=self.TAG_FACE_RESET_BUTTON,
                        callback=self._on_reset_faces_clicked,
                    )
                dpg.add_spacer(height=8)
                with dpg.group(horizontal=True):
                    dpg.add_text("Retry failed files:")
                    dpg.add_button(
                        label="Retry All Files with 0 Faces",
                        callback=self._on_retry_failed_face_analysis,
                        small=True,
                    )
                dpg.add_text(
                    "Clears analysis status for files that found 0 faces (may have failed to load).",
                    color=get_text_color("disabled"),
                    wrap=450,
                )

            # Pet analysis settings
            with dpg.collapsing_header(label="Pet Analysis Settings", default_open=False):
                dpg.add_text("Pet detection confidence threshold")
                dpg.add_slider_float(
                    tag="pet_detection_threshold",
                    default_value=self.config.ai.pet_detection_threshold,
                    min_value=0.3,
                    max_value=0.95,
                    format="%.2f",
                    width=300,
                    callback=self._on_pet_settings_changed,
                )
                dpg.add_checkbox(
                    label="Pets Only Mode (dog, cat, bird only - excludes wild animals)",
                    tag="pets_only_mode",
                    default_value=self.config.ai.pets_only_mode,
                    callback=self._on_pet_settings_changed,
                )
                dpg.add_text(
                    "Tip: Higher threshold and Pets Only Mode reduce false positives (e.g., humans in costumes).",
                    color=get_text_color("disabled"),
                    wrap=450,
                )

            # Celebrity identification settings
            with dpg.collapsing_header(label="Celebrity Identification Settings", default_open=False):
                dpg.add_checkbox(
                    label="Enable celebrity identification",
                    tag=self.TAG_CELEBRITY_ENABLED,
                    default_value=self.config.ai.celebrity_enabled,
                    callback=self._on_celebrity_settings_changed,
                )
                with dpg.group(horizontal=True):
                    dpg.add_text("Provider:")
                    dpg.add_combo(
                        items=["rekognition", "local_db"],
                        default_value=self.config.ai.celebrity_provider,
                        tag=self.TAG_CELEBRITY_PROVIDER,
                        width=200,
                        callback=self._on_celebrity_settings_changed,
                    )
                dpg.add_text("Auto-confirm threshold (matches above this are auto-assigned)")
                dpg.add_slider_float(
                    tag=self.TAG_CELEBRITY_AUTO_THRESHOLD,
                    default_value=self.config.ai.celebrity_auto_confirm_threshold,
                    min_value=0.5,
                    max_value=1.0,
                    format="%.2f",
                    width=300,
                    callback=self._on_celebrity_settings_changed,
                )
                dpg.add_text("Minimum confidence to show in review queue")
                dpg.add_slider_float(
                    tag=self.TAG_CELEBRITY_MIN_CONFIDENCE,
                    default_value=self.config.ai.celebrity_min_confidence,
                    min_value=0.3,
                    max_value=1.0,
                    format="%.2f",
                    width=300,
                    callback=self._on_celebrity_settings_changed,
                )
                dpg.add_text(
                    "rekognition: AWS cloud API (requires boto3 + AWS credentials). "
                    "local_db: Offline matching against a local celebrity embedding database.",
                    color=get_text_color("disabled"),
                    wrap=450,
                )

            # Statistics
            with dpg.group(horizontal=True):
                dpg.add_text("", tag="faces_stats_text")

            dpg.add_spacer(height=10)

            # Tab bar for Faces and Pets
            with dpg.tab_bar(tag=self.TAG_TABS):
                # Faces Tab
                with dpg.tab(label="Faces", tag=self.TAG_FACES_TAB):
                    self._build_faces_tab()

                # Pets Tab
                with dpg.tab(label="Pets", tag=self.TAG_PETS_TAB):
                    self._build_pets_tab()

        # Texture registry for face thumbnails
        with dpg.texture_registry(tag=self.TAG_TEXTURE_REGISTRY):
            pass

        # Create dialogs
        self._create_dialogs()

        self._refresh_drive_scopes()

    def _build_faces_tab(self) -> None:
        """Build the faces tab content."""
        # View selector
        with dpg.group(horizontal=True):
            dpg.add_text("View:")
            dpg.add_radio_button(
                items=["Unknown Clusters", "Named People"],
                default_value="Unknown Clusters",
                horizontal=True,
                callback=self._on_face_view_change,
                tag="face_view_selector"
            )

        dpg.add_spacer(height=5)

        # Min photos filter (for cluster view)
        with dpg.group(horizontal=True, tag="min_photos_filter_group"):
            dpg.add_checkbox(
                label="Min Photos Filter:",
                tag=self.TAG_MIN_PHOTOS_FILTER_CHECKBOX,
                default_value=self.config.ai.filter_by_min_photos,
                callback=self._on_min_photos_filter_toggle,
            )
            dpg.add_input_int(
                tag=self.TAG_MIN_PHOTOS_INPUT,
                default_value=self.config.ai.min_cluster_photos,
                min_value=1,
                max_value=50,
                width=60,
                step=1,
                callback=self._on_min_photos_change,
                enabled=self.config.ai.filter_by_min_photos,
            )
            dpg.add_text("(Only show faces in N+ photos)")

        # Sort options for clusters
        with dpg.group(horizontal=True, tag="cluster_sort_group"):
            dpg.add_text("Sort by:")
            dpg.add_combo(
                tag="cluster_sort_combo",
                items=[
                    "Cluster ID (default)",
                    "Closest to Known People First",
                    "Furthest from Known People First",
                    "Similar Clusters Together",
                ],
                default_value="Cluster ID (default)",
                width=240,
                callback=self._on_cluster_sort_change,
            )

        dpg.add_spacer(height=5)

        # Cluster view (default)
        with dpg.child_window(tag=self.TAG_CLUSTER_VIEW, height=400, border=True):
            dpg.add_text("Face Clusters", color=get_accent_color())
            dpg.add_separator()
            dpg.add_text("", tag="cluster_count_text", color=(180, 180, 180))
            dpg.add_text("No clusters found. Run 'Cluster Faces' to group similar faces.", tag="cluster_placeholder")

            # Clusters will be added dynamically
            with dpg.group(tag="face_clusters_container"):
                pass

        # People view (hidden initially)
        with dpg.child_window(tag=self.TAG_PEOPLE_VIEW, height=400, border=True, show=False):
            dpg.add_text("Named People", color=get_accent_color())
            dpg.add_separator()

            # Search and filter bar
            with dpg.group(horizontal=True):
                dpg.add_text("Search:")
                dpg.add_input_text(
                    tag=self.TAG_PEOPLE_SEARCH,
                    width=150,
                    hint="Filter by name...",
                    callback=self._on_people_search_change,
                )
                dpg.add_button(label="Clear", callback=self._clear_people_search, small=True)
                dpg.add_spacer(width=30)
                dpg.add_checkbox(
                    label="Show Hidden (0)",
                    tag=self.TAG_SHOW_HIDDEN_CHECKBOX,
                    default_value=False,
                    callback=self._on_show_hidden_change,
                )

            dpg.add_spacer(height=4)

            # People list
            with dpg.table(
                tag="people_table",
                header_row=True,
                borders_innerH=True,
                borders_outerH=True,
                resizable=True,
                policy=dpg.mvTable_SizingStretchProp,
                scrollY=True,
                height=310,
            ):
                dpg.add_table_column(label="Name", init_width_or_weight=150)
                dpg.add_table_column(label="Photos", init_width_or_weight=80)
                dpg.add_table_column(label="Age Range", init_width_or_weight=100)
                dpg.add_table_column(label="Actions", init_width_or_weight=200)

        # Family Groups section (below the people view, always visible)
        with dpg.collapsing_header(label="Family Groups", default_open=False):
            with dpg.group(horizontal=True):
                dpg.add_button(
                    label="Create Family Group",
                    callback=self._show_create_family_group_dialog,
                    small=True,
                )
            dpg.add_spacer(height=4)
            with dpg.child_window(
                tag=self.TAG_FAMILY_VIEW_CONTAINER,
                height=200,
                border=True,
            ):
                pass

    def _build_pets_tab(self) -> None:
        """Build the pets tab content."""
        # View selector
        with dpg.group(horizontal=True):
            dpg.add_text("View:")
            dpg.add_radio_button(
                items=["Unknown Clusters", "Named Pets"],
                default_value="Unknown Clusters",
                horizontal=True,
                callback=self._on_pet_view_change,
                tag="pet_view_selector"
            )

        dpg.add_spacer(height=10)

        # Pet cluster view
        with dpg.child_window(tag=self.TAG_PET_CLUSTER_VIEW, height=400, border=True):
            dpg.add_text("Pet Clusters", color=get_accent_color())
            dpg.add_separator()
            dpg.add_text("No clusters found. Run 'Cluster Pets' to group similar pets.", tag="pet_cluster_placeholder")

            with dpg.group(tag="pet_clusters_container"):
                pass

        # Named pets view (hidden initially)
        with dpg.child_window(tag=self.TAG_PETS_VIEW, height=400, border=True, show=False):
            dpg.add_text("Named Pets", color=get_accent_color())
            dpg.add_separator()

            with dpg.table(
                tag="pets_table",
                header_row=True,
                borders_innerH=True,
                borders_outerH=True,
                resizable=True,
                policy=dpg.mvTable_SizingStretchProp,
                scrollY=True,
                height=350,
            ):
                dpg.add_table_column(label="Name", init_width_or_weight=120)
                dpg.add_table_column(label="Species", init_width_or_weight=80)
                dpg.add_table_column(label="Breed", init_width_or_weight=100)
                dpg.add_table_column(label="Photos", init_width_or_weight=70)
                dpg.add_table_column(label="Actions", init_width_or_weight=150)

    def _create_dialogs(self) -> None:
        """Create modal dialogs."""
        with dpg.window(
            label="Assign or Create Person",
            tag=self.TAG_ASSIGN_DIALOG,
            modal=True,
            show=False,
            width=740,
            height=440,
            no_resize=True,
            pos=[140, 100],
        ):
            dpg.add_text("Sample faces:")
            with dpg.group(horizontal=True, tag=self.TAG_NAME_DIALOG_FACES):
                pass
            dpg.add_spacer(height=10)
            with dpg.group(horizontal=True):
                with dpg.child_window(width=340, height=250, border=True):
                    dpg.add_text("Create New Person", color=get_accent_color())
                    dpg.add_spacer(height=6)
                    dpg.add_text("Name:")
                    dpg.add_input_text(tag="person_name_input", width=300)
                    dpg.add_spacer(height=6)
                    dpg.add_checkbox(label="Enable age tracking (for children)", tag="enable_age_tracking")
                    dpg.add_text("Birth year (approximate):")
                    dpg.add_input_int(tag="birth_year_input", default_value=2000, width=100)
                    dpg.add_spacer(height=8)
                    dpg.add_button(label="Create & Assign", callback=self._save_person_name, width=140)

                with dpg.child_window(width=340, height=250, border=True):
                    dpg.add_text("Assign to Existing", color=get_accent_color())
                    dpg.add_spacer(height=6)
                    dpg.add_listbox(tag=self.TAG_ASSIGN_LIST, items=[], num_items=8, width=300)
                    dpg.add_spacer(height=8)
                    dpg.add_button(
                        label="Assign Selected",
                        tag=self.TAG_ASSIGN_BUTTON,
                        callback=self._assign_cluster_to_person,
                        width=140,
                    )

            dpg.add_spacer(height=10)
            dpg.add_button(label="Close", callback=self._cancel_assign_dialog, width=80)

        # Name pet dialog
        with dpg.window(
            label="Name This Pet",
            tag=self.TAG_PET_NAME_DIALOG,
            modal=True,
            show=False,
            width=400,
            height=300,
            no_resize=True,
            pos=[200, 150],
        ):
            dpg.add_text("Enter details for this pet:")
            dpg.add_text("Name:")
            dpg.add_input_text(tag="pet_name_input", width=300)
            dpg.add_text("Species:")
            dpg.add_input_text(tag="pet_species_input", width=200, readonly=True)
            dpg.add_text("Breed (optional):")
            dpg.add_input_text(tag="pet_breed_input", width=200)
            dpg.add_text("Birth year (optional):")
            dpg.add_input_int(tag="pet_birth_year_input", default_value=2020, width=100)
            dpg.add_text("Color/Markings description:")
            dpg.add_input_text(tag="pet_color_input", width=300)
            dpg.add_spacer(height=20)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Save", callback=self._save_pet_name)
                dpg.add_button(label="Cancel", callback=lambda: dpg.configure_item(self.TAG_PET_NAME_DIALOG, show=False))

        # Progress dialog
        with dpg.window(
            label="Analysis Progress",
            tag=self.TAG_PROGRESS_DIALOG,
            modal=True,
            show=False,
            width=450,
            height=200,
            no_resize=True,
            pos=[175, 200],
        ):
            dpg.add_text("Analyzing...", tag="progress_phase_text")
            dpg.add_spacer(height=10)
            dpg.add_progress_bar(tag="progress_bar", default_value=0.0, width=400)
            dpg.add_spacer(height=5)
            dpg.add_text("", tag="progress_detail_text")
            dpg.add_spacer(height=20)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Cancel", callback=self._cancel_analysis)
                dpg.add_button(label="Run in Background", callback=self._run_in_background)

        # Timeline dialog (expanded with tabs for chain analysis)
        with dpg.window(
            label="Age Timeline",
            tag=self.TAG_TIMELINE_DIALOG,
            modal=True,
            show=False,
            width=800,
            height=580,
            pos=[100, 80],
        ):
            dpg.add_text("", tag="timeline_title")
            dpg.add_separator()
            dpg.add_spacer(height=5)

            with dpg.tab_bar(tag=self.TAG_TIMELINE_TAB_BAR):
                with dpg.tab(label="Timeline", tag=self.TAG_TIMELINE_TAB):
                    with dpg.child_window(
                        tag=self.TAG_TIMELINE_PHOTOS_CONTENT,
                        height=430,
                        border=False,
                    ):
                        pass

                with dpg.tab(label="Chain Analysis", tag=self.TAG_CHAIN_TAB):
                    with dpg.child_window(
                        tag=self.TAG_CHAIN_CONTENT,
                        height=430,
                        border=False,
                    ):
                        pass

                with dpg.tab(label="Gap Alerts", tag=self.TAG_GAPS_TAB):
                    with dpg.child_window(
                        tag=self.TAG_GAPS_CONTENT,
                        height=430,
                        border=False,
                    ):
                        pass

            dpg.add_spacer(height=5)
            with dpg.group(horizontal=True):
                dpg.add_button(
                    label="Close",
                    callback=lambda: dpg.configure_item(self.TAG_TIMELINE_DIALOG, show=False),
                )
                dpg.add_button(label="Find More Photos", callback=self._find_more_photos)
                dpg.add_button(label="Build Chain", callback=self._on_build_chain)
                dpg.add_button(label="Review Chain Links", callback=self._on_review_chain_links)

        # Cross-age linking dialog (review weak links and transitive matches)
        with dpg.window(
            label="Review Chain Links",
            tag=self.TAG_CROSS_AGE_DIALOG,
            modal=True,
            show=False,
            width=900,
            height=620,
            pos=[80, 80],
        ):
            dpg.add_text("", tag="cross_age_title", color=get_accent_color())
            dpg.add_text("", tag="cross_age_summary", color=get_text_color("disabled"))
            dpg.add_spacer(height=6)
            with dpg.child_window(
                tag=self.TAG_CROSS_AGE_CONTAINER,
                width=-1,
                height=500,
                border=True,
            ):
                pass
            dpg.add_spacer(height=6)
            with dpg.group(horizontal=True):
                dpg.add_button(
                    label="Close",
                    callback=lambda: dpg.configure_item(self.TAG_CROSS_AGE_DIALOG, show=False),
                )

        # Face preview dialog
        with dpg.window(
            label="Face Preview",
            tag=self.TAG_FACE_PREVIEW_DIALOG,
            modal=False,
            show=False,
            width=920,
            height=740,
            pos=[120, 80],
        ):
            dpg.add_text("", tag=self.TAG_FACE_PREVIEW_TEXT)
            dpg.add_spacer(height=6)
            with dpg.child_window(width=-1, height=-1, border=False):
                dpg.add_drawlist(width=900, height=640, tag=self.TAG_FACE_PREVIEW_DRAW)
            dpg.add_spacer(height=6)
            with dpg.group(horizontal=True):
                dpg.add_button(
                    label="Exclude from face detection",
                    tag=self.TAG_FACE_PREVIEW_EXCLUDE,
                    callback=self._exclude_preview_file,
                )
                dpg.add_button(
                    label="Rotate Left",
                    tag=self.TAG_FACE_PREVIEW_ROTATE_LEFT,
                    callback=lambda: self._rotate_preview(90),
                )
                dpg.add_button(
                    label="Rotate Right",
                    tag=self.TAG_FACE_PREVIEW_ROTATE_RIGHT,
                    callback=lambda: self._rotate_preview(-90),
                )
                dpg.add_button(
                    label="Save Box",
                    tag=self.TAG_FACE_PREVIEW_SAVE,
                    callback=self._save_face_bbox,
                )
                dpg.add_button(
                    label="Close",
                    callback=lambda: dpg.configure_item(self.TAG_FACE_PREVIEW_DIALOG, show=False),
                )
            with dpg.handler_registry():
                dpg.add_mouse_down_handler(callback=self._on_preview_mouse_down)
                dpg.add_mouse_move_handler(callback=self._on_preview_mouse_move)
                dpg.add_mouse_drag_handler(callback=self._on_preview_mouse_drag)
                dpg.add_mouse_release_handler(callback=self._on_preview_mouse_up)

        # Intermediate clusters dialog (review suggestions for a person)
        with dpg.window(
            label="Suggested Clusters",
            tag=self.TAG_INTERMEDIATE_CLUSTERS_DIALOG,
            modal=True,
            show=False,
            width=980,
            height=680,
            pos=[110, 90],
        ):
            dpg.add_text("", tag="intermediate_title", color=get_accent_color())
            dpg.add_text("", tag="intermediate_summary", color=get_text_color("disabled"))
            dpg.add_spacer(height=6)
            with dpg.child_window(width=-1, height=520, border=True, tag=self.TAG_INTERMEDIATE_CONTAINER):
                pass
            dpg.add_spacer(height=6)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Close", callback=lambda: dpg.configure_item(self.TAG_INTERMEDIATE_CLUSTERS_DIALOG, show=False))

        # Re-match results dialog
        with dpg.window(
            label="Re-match Results",
            tag=self.TAG_REMATCH_DIALOG,
            modal=True,
            show=False,
            width=980,
            height=680,
            pos=[110, 90],
        ):
            dpg.add_text("", tag=self.TAG_REMATCH_HEADER, color=get_accent_color())
            dpg.add_spacer(height=6)
            with dpg.child_window(width=-1, height=540, border=True, tag=self.TAG_REMATCH_CONTAINER):
                pass
            dpg.add_spacer(height=6)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Done", callback=self._close_rematch_dialog)

        # Split cluster dialog
        with dpg.window(
            label="Split Cluster",
            tag=self.TAG_SPLIT_DIALOG,
            modal=True,
            show=False,
            width=920,
            height=700,
            pos=[140, 90],
        ):
            dpg.add_text("Select faces to split into a new person/assignment.")
            dpg.add_text("", tag=self.TAG_SPLIT_STATUS, color=get_text_color("disabled"))
            dpg.add_spacer(height=6)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Select All", callback=self._split_select_all, small=True)
                dpg.add_button(label="Deselect All", callback=self._split_deselect_all, small=True)
            dpg.add_spacer(height=4)
            with dpg.child_window(width=-1, height=500, border=True, tag=self.TAG_SPLIT_CONTAINER):
                pass
            dpg.add_spacer(height=6)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Assign Selected", tag=self.TAG_SPLIT_ASSIGN, callback=self._on_split_assign)
                dpg.add_button(label="Name Selected", tag=self.TAG_SPLIT_NAME, callback=self._on_split_name)
                dpg.add_button(label="Cancel", callback=self._cancel_split_dialog)

        # Reset confirmation dialog
        with dpg.window(
            label="Confirm Reset",
            tag=self.TAG_RESET_CONFIRM_DIALOG,
            modal=True,
            show=False,
            width=400,
            height=180,
            no_resize=True,
            pos=[250, 200],
        ):
            dpg.add_text("Are you sure you want to clear faces?", color=get_status_color("warning"))
            dpg.add_spacer(height=10)
            dpg.add_text("", tag=self.TAG_RESET_CONFIRM_TEXT)
            dpg.add_text("", tag=self.TAG_RESET_CONFIRM_COUNT, color=get_status_color("error"))
            dpg.add_spacer(height=20)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Yes, Clear", callback=self._confirm_reset)
                dpg.add_button(label="Cancel", callback=self._cancel_reset)

        # Edit person dialog
        with dpg.window(
            label="Edit Person",
            tag=self.TAG_EDIT_PERSON_DIALOG,
            modal=True,
            show=False,
            width=400,
            height=220,
            no_resize=True,
            pos=[220, 180],
        ):
            dpg.add_text("Edit person details:")
            dpg.add_spacer(height=8)
            dpg.add_text("Name:")
            dpg.add_input_text(tag="edit_person_name", width=300)
            dpg.add_text("Birth year (optional):")
            dpg.add_input_int(tag="edit_person_birth_year", width=100)
            dpg.add_spacer(height=20)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Save", callback=self._save_person_edit)
                dpg.add_button(label="Cancel", callback=lambda: dpg.configure_item(self.TAG_EDIT_PERSON_DIALOG, show=False))

        # Delete person confirmation dialog
        with dpg.window(
            label="Delete Person",
            tag=self.TAG_DELETE_PERSON_DIALOG,
            modal=True,
            show=False,
            width=400,
            height=180,
            no_resize=True,
            pos=[250, 200],
        ):
            dpg.add_text("Delete this person?", color=get_status_color("error"))
            dpg.add_spacer(height=10)
            dpg.add_text("", tag="delete_person_info")
            dpg.add_text("Their faces will return to Unknown Clusters.", color=get_text_color("secondary"))
            dpg.add_spacer(height=20)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Yes, Delete", callback=self._confirm_delete_person)
                dpg.add_button(label="Cancel", callback=lambda: dpg.configure_item(self.TAG_DELETE_PERSON_DIALOG, show=False))

        # Add Relationship dialog
        with dpg.window(
            label="Add Relationship",
            tag=self.TAG_RELATIONSHIP_DIALOG,
            modal=True,
            show=False,
            width=420,
            height=200,
            no_resize=True,
            pos=[220, 180],
        ):
            dpg.add_text("Add a relationship for this person:")
            dpg.add_spacer(height=8)
            dpg.add_text("Related person:")
            dpg.add_combo(tag=self.TAG_RELATIONSHIP_PERSON_COMBO, items=[], width=300)
            dpg.add_text("Relationship type:")
            dpg.add_combo(
                tag=self.TAG_RELATIONSHIP_TYPE_COMBO,
                items=["parent", "child", "sibling", "spouse", "other"],
                default_value="sibling",
                width=200,
            )
            dpg.add_spacer(height=12)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Save", callback=self._save_relationship)
                dpg.add_button(label="Cancel", callback=lambda: dpg.configure_item(self.TAG_RELATIONSHIP_DIALOG, show=False))

        # Create Family Group dialog
        with dpg.window(
            label="Create Family Group",
            tag=self.TAG_FAMILY_GROUP_DIALOG,
            modal=True,
            show=False,
            width=400,
            height=160,
            no_resize=True,
            pos=[230, 200],
        ):
            dpg.add_text("Create a new family group:")
            dpg.add_spacer(height=8)
            dpg.add_text("Group name:")
            dpg.add_input_text(tag=self.TAG_FAMILY_GROUP_NAME_INPUT, width=300)
            dpg.add_spacer(height=12)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Create", callback=self._save_family_group)
                dpg.add_button(label="Cancel", callback=lambda: dpg.configure_item(self.TAG_FAMILY_GROUP_DIALOG, show=False))

        # Add Member to Family Group dialog
        with dpg.window(
            label="Add Family Member",
            tag=self.TAG_FAMILY_MEMBER_DIALOG,
            modal=True,
            show=False,
            width=420,
            height=200,
            no_resize=True,
            pos=[220, 190],
        ):
            dpg.add_text("Add a person to this family group:")
            dpg.add_spacer(height=8)
            dpg.add_text("Person:")
            dpg.add_combo(tag=self.TAG_FAMILY_MEMBER_COMBO, items=[], width=300)
            dpg.add_text("Role (optional):")
            dpg.add_input_text(tag=self.TAG_FAMILY_MEMBER_ROLE_INPUT, hint="e.g. father, mother, child", width=200)
            dpg.add_spacer(height=12)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Add", callback=self._save_family_member)
                dpg.add_button(label="Cancel", callback=lambda: dpg.configure_item(self.TAG_FAMILY_MEMBER_DIALOG, show=False))

        # Co-occurrence / Suggest Relationships dialog
        with dpg.window(
            label="Suggest Relationships",
            tag=self.TAG_COOCCURRENCE_DIALOG,
            modal=False,
            show=False,
            width=600,
            height=450,
            pos=[180, 100],
        ):
            dpg.add_text("People who appear frequently together:")
            dpg.add_spacer(height=8)
            with dpg.child_window(width=-1, height=370, border=True, tag=self.TAG_COOCCURRENCE_CONTAINER):
                pass

        # View all faces dialog
        with dpg.window(
            label="All Faces in Cluster",
            tag=self.TAG_ALL_FACES_DIALOG,
            modal=True,
            show=False,
            width=920,
            height=600,
            pos=[120, 80],
        ):
            dpg.add_text("All faces in this cluster (up to 200):")
            dpg.add_spacer(height=8)
            with dpg.child_window(width=-1, height=500, border=True, tag=self.TAG_ALL_FACES_CONTAINER):
                pass
            dpg.add_spacer(height=8)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Close", callback=lambda: dpg.configure_item(self.TAG_ALL_FACES_DIALOG, show=False))

        # Person Photo Gallery dialog
        with dpg.window(
            label="Photo Gallery",
            tag=self.TAG_PERSON_GALLERY_DIALOG,
            modal=True,
            show=False,
            width=950,
            height=700,
            pos=[80, 50],
        ):
            # Header with person name and info
            dpg.add_text("", tag=self.TAG_PERSON_GALLERY_TITLE, color=get_accent_color())
            dpg.add_text("", tag=self.TAG_PERSON_GALLERY_INFO, color=get_text_color("disabled"))
            dpg.add_separator()
            dpg.add_spacer(height=5)

            # Controls row
            with dpg.group(horizontal=True):
                dpg.add_text("Sort by:")
                dpg.add_combo(
                    tag=self.TAG_PERSON_GALLERY_SORT,
                    items=["Date (Newest)", "Date (Oldest)", "File Name", "Similarity (Best First)", "Similarity (Worst First)"],
                    default_value="Date (Newest)",
                    width=160,
                    callback=self._on_gallery_sort_change,
                )
                dpg.add_spacer(width=10)
                dpg.add_button(label="Select All", callback=self._gallery_select_all, small=True)
                dpg.add_button(label="Deselect All", callback=self._gallery_deselect_all, small=True)
                dpg.add_button(label="Remove Selected", callback=self._gallery_remove_selected, small=True)
                dpg.add_spacer(width=10)
                dpg.add_button(label="Refresh All Thumbnails", callback=self._gallery_refresh_all_thumbnails, small=True)

            dpg.add_spacer(height=8)

            # Photo grid container
            with dpg.child_window(
                width=-1,
                height=540,
                border=True,
                tag=self.TAG_PERSON_GALLERY_CONTAINER,
            ):
                dpg.add_text("Loading photos...", color=get_text_color("disabled"))

            dpg.add_spacer(height=8)

            # Footer buttons
            with dpg.group(horizontal=True):
                dpg.add_button(label="Find More Photos", callback=self._gallery_find_more, width=120)
                dpg.add_button(label="View Timeline", callback=self._gallery_view_timeline, width=100)
                dpg.add_spacer(width=400)
                dpg.add_button(label="Close", callback=self._close_person_gallery, width=80)

        # Photo Preview dialog (for viewing individual photos from gallery)
        with dpg.window(
            label="Photo Preview",
            tag=self.TAG_PHOTO_PREVIEW_DIALOG,
            modal=False,  # Not modal so it can appear on top of gallery
            show=False,
            width=700,
            height=680,
            pos=[200, 100],  # Offset from gallery position
            no_resize=False,
            no_move=False,
        ):
            dpg.add_text("", tag=self.TAG_PHOTO_PREVIEW_INFO)
            dpg.add_separator()
            dpg.add_spacer(height=5)

            # Preview image container
            with dpg.child_window(
                width=-1,
                height=540,
                border=True,
                tag=self.TAG_PHOTO_PREVIEW_CONTAINER,
            ):
                dpg.add_text("Loading preview...", color=get_text_color("disabled"))

            dpg.add_spacer(height=8)

            # Action buttons
            with dpg.group(horizontal=True):
                dpg.add_button(label="Open File", callback=self._photo_preview_open, width=90)
                dpg.add_button(label="Show in Explorer", callback=self._photo_preview_explorer, width=120)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Choose Face", callback=self._show_choose_face_dialog, width=100)
                dpg.add_button(label="Refresh Thumbnail", callback=self._refresh_face_thumbnail, width=120)
                dpg.add_button(label="Remove from Person", callback=self._photo_preview_remove, width=130)
                dpg.add_spacer(width=150)
                dpg.add_button(label="Close", callback=self._close_photo_preview, width=80)

        # Choose Face dialog (for selecting which face in a multi-person photo)
        with dpg.window(
            label="Choose Face in Photo",
            tag=self.TAG_CHOOSE_FACE_DIALOG,
            modal=True,
            show=False,
            width=700,
            height=500,
            pos=[250, 150],
        ):
            dpg.add_text("Select which face to assign to this person:")
            dpg.add_separator()
            dpg.add_spacer(height=5)

            # Container for face thumbnails
            with dpg.child_window(
                width=-1,
                height=380,
                border=True,
                tag=self.TAG_CHOOSE_FACE_CONTAINER,
            ):
                dpg.add_text("Loading faces...", color=get_text_color("disabled"))

            dpg.add_spacer(height=8)

            # Action buttons
            with dpg.group(horizontal=True):
                dpg.add_spacer(width=500)
                dpg.add_button(label="Cancel", callback=self._close_choose_face_dialog, width=80)

    def _update_stats(self) -> None:
        """Update statistics display."""
        try:
            face_count = self.db.get_face_count(min_confidence=self.config.ai.face_detection_threshold)
            person_count = len(self.db.get_all_persons(named_only=True))
            unassigned_faces = len(
                self.db.get_unassigned_faces(
                    limit=1000,
                    min_confidence=self.config.ai.face_detection_threshold,
                )
            )

            pet_count = self.db.get_pet_detection_count()
            named_pets = len(self.db.get_all_pets())
            len(self.db.get_unassigned_pet_detections(limit=1000))

            stats = (
                f"Faces: {face_count:,} total | {person_count} people named | {unassigned_faces:,} unassigned | "
                f"Pets: {pet_count:,} detected | {named_pets} named"
            )
            dpg.set_value("faces_stats_text", stats)

        except Exception as e:
            logger.error(f"Error updating stats: {e}")

    def _on_face_view_change(self, sender, app_data, user_data) -> None:
        """Handle face view toggle."""
        if app_data == "Unknown Clusters":
            dpg.configure_item(self.TAG_CLUSTER_VIEW, show=True)
            dpg.configure_item(self.TAG_PEOPLE_VIEW, show=False)
            if dpg.does_item_exist("min_photos_filter_group"):
                dpg.configure_item("min_photos_filter_group", show=True)
            if dpg.does_item_exist("cluster_sort_group"):
                dpg.configure_item("cluster_sort_group", show=True)
            self._current_view = "clusters"
            # Refresh clusters display when switching to this view
            if self._face_clusters:
                self._display_face_clusters()
        else:
            dpg.configure_item(self.TAG_CLUSTER_VIEW, show=False)
            dpg.configure_item(self.TAG_PEOPLE_VIEW, show=True)
            if dpg.does_item_exist("min_photos_filter_group"):
                dpg.configure_item("min_photos_filter_group", show=False)
            if dpg.does_item_exist("cluster_sort_group"):
                dpg.configure_item("cluster_sort_group", show=False)
            self._current_view = "people"
            self._refresh_people_list()

    def _on_pet_view_change(self, sender, app_data, user_data) -> None:
        """Handle pet view toggle."""
        if app_data == "Unknown Clusters":
            dpg.configure_item(self.TAG_PET_CLUSTER_VIEW, show=True)
            dpg.configure_item(self.TAG_PETS_VIEW, show=False)
        else:
            dpg.configure_item(self.TAG_PET_CLUSTER_VIEW, show=False)
            dpg.configure_item(self.TAG_PETS_VIEW, show=True)
            self._refresh_pets_list()

    def _on_pet_settings_changed(self, sender, app_data, user_data) -> None:
        """Handle changes to pet detection settings."""
        if sender == "pet_detection_threshold":
            self.config.ai.pet_detection_threshold = app_data
        elif sender == "pets_only_mode":
            self.config.ai.pets_only_mode = app_data

        save_config(self.config)

        # Reset the pet analyzer so it uses new settings
        with self._analyzer_lock:
            self._pet_analyzer = None

        self._notify_status("Pet detection settings updated. Re-run Pet Analysis to apply.", level="info")

    def _on_retry_failed_face_analysis(self) -> None:
        """Clear face analysis status for files with 0 faces so they get retried."""
        try:
            cleared = self.db.clear_failed_face_analysis()
            logger.info(f"Cleared face analysis status for {cleared} files")
            self._notify_status(
                f"Cleared analysis status for {cleared} files. Run Face Analysis again to retry them.",
                level="info"
            )
            self._pending_stats_refresh = True
            self._refresh()
        except Exception as e:
            logger.error(f"Error clearing failed face analysis: {e}")
            self._notify_status(f"Error: {e}", level="error")

    def _set_analysis_buttons_enabled(self, enabled: bool) -> None:
        """Enable or disable analysis action buttons during operations."""
        buttons = [
            self.TAG_RUN_FACE_BUTTON,
            "run_pet_analysis_btn",
            "cluster_faces_btn",
            "cluster_pets_btn",
            "rematch_known_btn",
            self.TAG_CELEBRITY_BUTTON,
        ]
        for btn in buttons:
            if dpg.does_item_exist(btn):
                dpg.configure_item(btn, enabled=enabled)

    def _on_run_face_analysis(self) -> None:
        """Start face analysis in background."""
        if self._background_face_analysis:
            self._notify_status("Background face analysis is running.", level="warning")
            return
        if self._is_analyzing:
            logger.warning("Analysis already in progress")
            self._notify_status("Analysis already in progress.", level="warning")
            return

        # Get image and PDF files
        files = self.db.get_files_by_type([".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp", ".tiff", ".tif", ".bmp", ".pdf"])
        if not files:
            logger.info("No image files to analyze")
            self._notify_status("No image or PDF files to analyze.", level="warning")
            return

        self._is_analyzing = True
        self._set_analysis_buttons_enabled(False)
        dpg.configure_item(self.TAG_RUN_FACE_BUTTON, label="Face analysis running...")
        dpg.set_value(self.TAG_FACE_ANALYSIS_STATUS, "Face analysis running")
        dpg.configure_item(self.TAG_PROGRESS_DIALOG, show=True)
        self._notify_status("Running face analysis...")

        def run_analysis():
            try:
                self._start_auto_refresh()
                self.face_analyzer.set_progress_callback(self._update_progress)
                self.face_analyzer.analyze_batch(files)
            except Exception as e:
                logger.error(f"Face analysis error: {e}")
            finally:
                self._is_analyzing = False
                if not self._background_face_analysis:
                    self._set_analysis_buttons_enabled(True)
                    dpg.configure_item(self.TAG_RUN_FACE_BUTTON, label="Run Face Analysis")
                    dpg.set_value(self.TAG_FACE_ANALYSIS_STATUS, "")
                self._stop_auto_refresh()
                dpg.configure_item(self.TAG_PROGRESS_DIALOG, show=False)
                self._refresh()
                self._notify_status("Face analysis complete.")

        self._analysis_thread = threading.Thread(target=run_analysis, daemon=True)
        self._analysis_thread.start()

    def _on_run_pet_analysis(self) -> None:
        """Start pet analysis in background."""
        if self._is_analyzing:
            logger.warning("Analysis already in progress")
            self._notify_status("Analysis already in progress.", level="warning")
            return

        files = self.db.get_files_by_type([".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp", ".tiff", ".tif", ".bmp"])
        if not files:
            logger.info("No image files to analyze")
            self._notify_status("No image files to analyze.", level="warning")
            return

        self._is_analyzing = True
        self._set_analysis_buttons_enabled(False)
        dpg.configure_item(self.TAG_PROGRESS_DIALOG, show=True)
        self._notify_status("Running pet analysis...")

        def run_analysis():
            try:
                self.pet_analyzer.set_progress_callback(self._update_pet_progress)
                self.pet_analyzer.analyze_batch(files)
            except Exception as e:
                logger.error(f"Pet analysis error: {e}")
            finally:
                self._is_analyzing = False
                self._set_analysis_buttons_enabled(True)
                dpg.configure_item(self.TAG_PROGRESS_DIALOG, show=False)
                self._refresh()
                self._notify_status("Pet analysis complete.")
        self._analysis_thread = threading.Thread(target=run_analysis, daemon=True)
        self._analysis_thread.start()

    def _notify_status(self, message: str, level: str = "info") -> None:
        """Send status update if callback provided."""
        if not self.on_status_update:
            return
        try:
            self.on_status_update(message, level=level)
        except TypeError:
            self.on_status_update(message)

    def _update_progress(self, progress: FaceAnalysisProgress) -> None:
        """Update progress dialog from face analysis."""
        try:
            dpg.set_value("progress_phase_text", f"Phase: {progress.phase}")
            dpg.set_value("progress_bar", progress.percent_complete / 100.0)
            dpg.set_value(
                "progress_detail_text",
                f"Files: {progress.processed_files}/{progress.total_files} | "
                f"Faces: {progress.faces_detected}"
            )
        except Exception:
            pass

    def _update_pet_progress(self, progress: PetAnalysisProgress) -> None:
        """Update progress dialog from pet analysis."""
        try:
            dpg.set_value("progress_phase_text", f"Phase: {progress.phase}")
            dpg.set_value("progress_bar", progress.percent_complete / 100.0)
            dpg.set_value(
                "progress_detail_text",
                f"Files: {progress.processed_files}/{progress.total_files} | "
                f"Pets: {progress.pets_detected}"
            )
        except Exception:
            pass

    def _cancel_analysis(self) -> None:
        """Cancel ongoing analysis."""
        if self._face_analyzer:
            self._face_analyzer.cancel()
        if self._pet_analyzer:
            self._pet_analyzer.cancel()

    def _run_in_background(self) -> None:
        """Hide progress dialog but continue analysis."""
        dpg.configure_item(self.TAG_PROGRESS_DIALOG, show=False)

    def _on_cluster_faces(self) -> None:
        """Run face clustering."""
        if self._is_clustering:
            return
        self._is_clustering = True
        self._set_analysis_buttons_enabled(False)
        if dpg.does_item_exist(self.TAG_FACE_ANALYSIS_STATUS):
            dpg.set_value(self.TAG_FACE_ANALYSIS_STATUS, "Clustering faces...")

        def run_clustering():
            try:
                clusters = self.face_analyzer.cluster_faces()
                run_id = self.db.create_face_cluster_run(method="auto")
                cluster_face_ids = [c.face_ids for c in clusters]
                self.db.save_face_clusters(run_id, cluster_face_ids, method="auto")
                self._cluster_run_id = run_id
                self._pending_cluster_refresh = True
                self._pending_stats_refresh = True
            except Exception as e:
                logger.error(f"Face clustering error: {e}")
            finally:
                self._is_clustering = False
                self._pending_cluster_done = True

        threading.Thread(target=run_clustering, daemon=True).start()

    def _on_rematch_known(self) -> None:
        """Re-match all unassigned faces against known people."""
        if self._is_clustering:
            return
        self._is_clustering = True
        self._set_analysis_buttons_enabled(False)
        if dpg.does_item_exist(self.TAG_FACE_ANALYSIS_STATUS):
            dpg.set_value(self.TAG_FACE_ANALYSIS_STATUS, "Re-matching faces to known people...")

        def run_rematch():
            try:
                auto_count, suggestions = self.face_analyzer.rematch_all_faces()
                self._pending_rematch_results = (auto_count, suggestions)
                self._pending_cluster_refresh = True
                self._pending_stats_refresh = True
            except Exception as e:
                logger.error(f"Re-match error: {e}")
            finally:
                self._is_clustering = False
                self._pending_cluster_done = True

        threading.Thread(target=run_rematch, daemon=True).start()

    def _on_cluster_pets(self) -> None:
        """Run pet clustering."""
        try:
            self._pet_clusters = self.pet_analyzer.cluster_detections()
            self._display_pet_clusters()
            self._update_stats()
        except Exception as e:
            logger.error(f"Pet clustering error: {e}")

    def _display_face_clusters(self) -> None:
        """Display face clusters in the UI."""
        # logger.info(f"_display_face_clusters called with {len(self._face_clusters)} clusters, {len(self._face_textures)} textures available")

        # Calculate visible cluster range based on scroll position
        scroll_y = 0
        if dpg.does_item_exist(self.TAG_CLUSTER_VIEW):
            try:
                scroll_y = dpg.get_y_scroll(self.TAG_CLUSTER_VIEW)
                self._last_scroll_y = scroll_y  # Update tracked scroll position
            except Exception:
                scroll_y = 0

        # Each cluster is roughly 150 pixels tall (5 faces + buttons + separator)
        cluster_height = 150
        window_height = 400  # Child window height

        # Calculate visible range with buffer for smooth scrolling
        first_visible_cluster = max(0, int(scroll_y / cluster_height) - 5)  # 5 cluster buffer before
        visible_cluster_count = int(window_height / cluster_height) + 12  # +2 for partial + 10 buffer
        last_visible_cluster = min(len(self._face_clusters), first_visible_cluster + visible_cluster_count)

        # Clean up cluster handler registries before re-rendering
        for reg in self._cluster_handler_registries:
            try:
                if dpg.does_item_exist(reg):
                    dpg.delete_item(reg)
            except Exception:
                pass
        self._cluster_handler_registries.clear()

        # Clear existing (safely handle items that may not exist)
        children = dpg.get_item_children("face_clusters_container", 1)
        if children:
            for child in children:
                try:
                    if dpg.does_item_exist(child):
                        dpg.delete_item(child)
                except Exception as e:
                    logger.warning(f"Failed to delete cluster child item {child}: {e}")

        if not self._face_clusters:
            dpg.configure_item("cluster_placeholder", show=True)
            dpg.configure_item("cluster_count_text", show=False)
            return

        dpg.configure_item("cluster_placeholder", show=False)

        # Update cluster count display
        if dpg.does_item_exist("cluster_count_text"):
            if self._filtered_clusters > 0:
                count_text = f"Showing {len(self._face_clusters)} of {self._total_clusters} clusters ({self._filtered_clusters} filtered)"
            else:
                count_text = f"Showing {len(self._face_clusters)} clusters"
            dpg.set_value("cluster_count_text", count_text)
            dpg.configure_item("cluster_count_text", show=True)

        textures_found = 0
        textures_missing = 0

        # Virtual scrolling: Add spacer for clusters before visible range
        if first_visible_cluster > 0:
            top_spacer_height = first_visible_cluster * cluster_height
            dpg.add_spacer(parent="face_clusters_container", height=top_spacer_height)

        # Only render visible clusters (virtual scrolling for performance)
        for cluster_idx in range(first_visible_cluster, last_visible_cluster):
            cluster = self._face_clusters[cluster_idx]
            with dpg.group(parent="face_clusters_container", horizontal=False):
                with dpg.group(horizontal=True):
                    cluster_label = dpg.add_selectable(
                        label=f"Cluster {cluster.cluster_id + 1}: {len(cluster.face_ids)} photos",
                        span_columns=False,
                    )
                    with dpg.item_handler_registry() as cluster_hr:
                        dpg.add_item_clicked_handler(
                            button=dpg.mvMouseButton_Right,
                            callback=self._show_cluster_context_menu,
                            user_data=(cluster.cluster_id, cluster.face_ids),
                        )
                    dpg.bind_item_handler_registry(cluster_label, cluster_hr)
                    self._cluster_handler_registries.append(cluster_hr)
                    dpg.add_button(
                        label="Assign",
                        callback=lambda s, a, u: self._show_assign_dialog(u),
                        user_data=cluster.cluster_id,
                        small=True,
                    )
                    dpg.add_button(
                        label="Split",
                        callback=lambda s, a, u: self._show_split_dialog(u),
                        user_data=cluster.cluster_id,
                        small=True,
                    )
                    dpg.add_button(
                        label="View Photos",
                        callback=lambda s, a, u: self._view_cluster_photos(u),
                        user_data=cluster.cluster_id,
                        small=True,
                    )
                    dpg.add_button(
                        label="View All",
                        callback=lambda s, a, u: self._show_all_faces_dialog(u[0], u[1]),
                        user_data=(cluster.cluster_id, cluster.face_ids),
                        small=True,
                    )
                    dpg.add_button(
                        label="Ignore",
                        callback=lambda s, a, u: self._ignore_cluster(u[0], u[1]),
                        user_data=(cluster.cluster_id, cluster.face_ids),
                        small=True,
                    )

                # Show sample face info
                if cluster.sample_faces:
                    with dpg.group(horizontal=True):
                        for face in cluster.sample_faces[:5]:
                            with dpg.group(horizontal=False):
                                conf = face.confidence if face.confidence is not None else 0.0
                                sim = self._compute_face_similarity(face, cluster)
                                if sim is None:
                                    dpg.add_text(f"conf {conf:.2f}", color=get_text_color("disabled"))
                                else:
                                    dpg.add_text(f"conf {conf:.2f} sim {sim:.2f}", color=get_text_color("disabled"))

                                # Load textures for visible clusters
                                tex_tag = self._get_face_texture(face)
                                if tex_tag:
                                    textures_found += 1
                                    face_id = face.id
                                    if face_id is not None:
                                        dpg.add_image_button(
                                            tex_tag,
                                            width=64,
                                            height=64,
                                            callback=lambda s, a, u: self._show_face_preview(u),
                                            user_data=face_id,
                                        )
                                    else:
                                        dpg.add_image(tex_tag, width=64, height=64)
                                else:
                                    textures_missing += 1
                                    dpg.add_text("[image]", color=get_text_color("disabled"))

                                if face.id is not None:
                                    dpg.add_button(
                                        label="Exclude",
                                        small=True,
                                        callback=lambda s, a, u: self._exclude_face(u),
                                        user_data=face.id,
                                    )
                    ages = [f.estimated_age for f in cluster.sample_faces if f.estimated_age]
                    if ages:
                        avg_age = sum(ages) / len(ages)
                        dpg.add_text(f"  Estimated age: ~{int(avg_age)} years", color=get_text_color("disabled"))

                dpg.add_separator()

        # Virtual scrolling: Add spacer for clusters after visible range
        if last_visible_cluster < len(self._face_clusters):
            bottom_spacer_height = (len(self._face_clusters) - last_visible_cluster) * cluster_height
            dpg.add_spacer(parent="face_clusters_container", height=bottom_spacer_height)

        # Track if we're stuck on missing textures (prevent infinite refresh loop)
        if textures_missing > 0 and textures_missing == self._last_missing_texture_count:
            self._stuck_refresh_count += 1
            # If stuck for 3+ refreshes, stop auto-refreshing (textures likely failed to load)
            if self._stuck_refresh_count >= 3:
                logger.info(f"Stopping auto-refresh: stuck at {textures_missing} missing textures")
                self._pending_face_ui_refresh = False
        else:
            # Reset stuck counter if progress is being made
            self._stuck_refresh_count = 0
        self._last_missing_texture_count = textures_missing

        logger.info(f"_display_face_clusters complete: {textures_found} textures rendered, {textures_missing} missing (showing clusters {first_visible_cluster}-{last_visible_cluster} of {len(self._face_clusters)})")

    def _display_pet_clusters(self) -> None:
        """Display pet clusters in the UI."""
        for child in dpg.get_item_children("pet_clusters_container", 1):
            dpg.delete_item(child)

        if not self._pet_clusters:
            dpg.configure_item("pet_cluster_placeholder", show=True)
            return

        dpg.configure_item("pet_cluster_placeholder", show=False)

        for cluster in self._pet_clusters:
            with dpg.group(parent="pet_clusters_container", horizontal=False):
                with dpg.group(horizontal=True):
                    dpg.add_text(
                        f"Cluster {cluster.cluster_id + 1}: {len(cluster.detection_ids)} photos ({cluster.species})"
                    )
                    dpg.add_button(
                        label="Name Pet",
                        callback=lambda s, a, u: self._show_pet_name_dialog(u),
                        user_data=cluster.cluster_id,
                        small=True,
                    )
                    dpg.add_button(
                        label="View Photos",
                        callback=lambda s, a, u: self._view_pet_cluster_photos(u),
                        user_data=cluster.cluster_id,
                        small=True,
                    )

                # Show sample pet detection thumbnails
                if cluster.sample_detections:
                    with dpg.group(horizontal=True):
                        for detection in cluster.sample_detections[:5]:  # Show up to 5 samples
                            with dpg.group():
                                tex_tag = self._get_pet_texture(detection)
                                if tex_tag:
                                    dpg.add_image(tex_tag, width=64, height=64)
                                else:
                                    dpg.add_text("[image]", color=get_text_color("disabled"))

                dpg.add_separator()

    def _show_name_dialog(self, cluster_id: int) -> None:
        """Show dialog to name a person from cluster."""
        self._show_assign_dialog(cluster_id)

    def _populate_name_dialog_faces(self, faces: list) -> None:
        """Populate face thumbnails in the name dialog."""
        if not dpg.does_item_exist(self.TAG_NAME_DIALOG_FACES):
            return

        # Clear existing thumbnails
        for child in dpg.get_item_children(self.TAG_NAME_DIALOG_FACES, 1) or []:
            dpg.delete_item(child)

        if not faces:
            dpg.add_text("(No sample faces)", parent=self.TAG_NAME_DIALOG_FACES, color=get_text_color("disabled"))
            return

        for face in faces:
            tex_tag = self._get_face_texture(face)
            if tex_tag:
                dpg.add_image(tex_tag, width=72, height=72, parent=self.TAG_NAME_DIALOG_FACES)
            else:
                dpg.add_text("[img]", parent=self.TAG_NAME_DIALOG_FACES, color=get_text_color("disabled"))

    def _show_name_dialog_for_split(self) -> None:
        """Show dialog to name a person from split selection."""
        self._show_assign_dialog_for_split()

    def _show_assign_dialog(self, cluster_id: int) -> None:
        """Show dialog to assign a cluster to an existing person."""
        cluster = next((c for c in self._face_clusters if c.cluster_id == cluster_id), None)
        if not cluster:
            self._notify_status("Cluster not found (refreshing).", level="warning")
            self._refresh()
            return
        self._assign_mode = "cluster"
        self._name_mode = "cluster"
        reference_embedding = self._get_cluster_reference_embedding(cluster)
        self._assign_person_map = self._build_assign_person_map(reference_embedding)
        dpg.configure_item(self.TAG_ASSIGN_LIST, items=[name for name, _ in self._assign_person_map])
        if self._assign_person_map:
            dpg.set_value(self.TAG_ASSIGN_LIST, self._assign_person_map[0][0])
        self._selected_cluster_id = cluster_id
        self._selected_cluster_snapshot = cluster
        self._pause_auto_refresh = True
        self._stop_auto_refresh()
        dpg.set_value("person_name_input", "")
        dpg.set_value("enable_age_tracking", False)
        dpg.set_value("birth_year_input", 2000)
        self._populate_name_dialog_faces(cluster.sample_faces[:6] if cluster.sample_faces else [])
        if dpg.does_item_exist(self.TAG_ASSIGN_BUTTON):
            dpg.configure_item(self.TAG_ASSIGN_BUTTON, enabled=bool(self._assign_person_map))
        dpg.configure_item(self.TAG_ASSIGN_DIALOG, show=True)

    def _show_assign_dialog_for_split(self) -> None:
        """Show dialog to assign split selection to an existing person."""
        if not self._split_selected:
            self._notify_status("Select faces to assign first.", level="warning")
            return
        self._assign_mode = "split"
        self._name_mode = "split"
        reference_embedding = self._get_split_reference_embedding()
        self._assign_person_map = self._build_assign_person_map(reference_embedding)
        dpg.configure_item(self.TAG_ASSIGN_LIST, items=[name for name, _ in self._assign_person_map])
        if self._assign_person_map:
            dpg.set_value(self.TAG_ASSIGN_LIST, self._assign_person_map[0][0])
        self._pause_auto_refresh = True
        self._stop_auto_refresh()
        dpg.set_value("person_name_input", "")
        dpg.set_value("enable_age_tracking", False)
        dpg.set_value("birth_year_input", 2000)
        self._populate_name_dialog_faces([])
        if dpg.does_item_exist(self.TAG_ASSIGN_BUTTON):
            dpg.configure_item(self.TAG_ASSIGN_BUTTON, enabled=bool(self._assign_person_map))
        dpg.configure_item(self.TAG_ASSIGN_DIALOG, show=True)

    def _show_pet_name_dialog(self, cluster_id: int) -> None:
        """Show dialog to name a pet from cluster."""
        self._selected_cluster_id = cluster_id

        # Find cluster
        cluster = next((c for c in self._pet_clusters if c.cluster_id == cluster_id), None)
        if not cluster:
            return

        dpg.set_value("pet_name_input", "")
        dpg.set_value("pet_species_input", cluster.species)
        dpg.set_value("pet_breed_input", "")
        dpg.set_value("pet_birth_year_input", 2020)
        dpg.set_value("pet_color_input", "")
        dpg.configure_item(self.TAG_PET_NAME_DIALOG, show=True)

    def _save_person_name(self) -> None:
        """Save person name from dialog."""
        dpg.configure_item(self.TAG_ASSIGN_DIALOG, show=False)

        name = dpg.get_value("person_name_input").strip()
        if not name:
            self._resume_auto_refresh()
            return

        enable_age = dpg.get_value("enable_age_tracking")
        birth_year = dpg.get_value("birth_year_input") if enable_age else None

        if self._name_mode == "split":
            if not self._split_selected:
                self._resume_auto_refresh()
                return
            person = Person(
                name=name,
                birth_year=birth_year,
                photo_count=len(self._split_selected),
            )
            person_id = self.db.add_person(person)
            for face_id in list(self._split_selected):
                self.db.assign_face_to_person(face_id, person_id)
            self.face_analyzer.load_person_embeddings()
            logger.info(f"Created person '{name}' with {len(self._split_selected)} faces")
            self._split_selected.clear()
            self._render_split_faces()
            dpg.configure_item(self.TAG_SPLIT_DIALOG, show=False)
        else:
            # Find cluster
            cluster = self._selected_cluster_snapshot or next(
                (c for c in self._face_clusters if c.cluster_id == self._selected_cluster_id),
                None,
            )
            if not cluster:
                self._resume_auto_refresh()
                return

            # Create person
            person_id = self.face_analyzer.create_person_from_cluster(cluster, name, birth_year)
        if person_id:
            logger.info(f"Created person: {name}")
            if self._name_mode == "cluster":
                if cluster in self._face_clusters:
                    self._face_clusters.remove(cluster)
                self._display_face_clusters()
            self._pending_stats_refresh = True
            threading.Thread(target=self._auto_refine_matches, daemon=True).start()
        self._resume_auto_refresh()

    def _assign_cluster_to_person(self) -> None:
        """Assign current cluster to selected person."""
        dpg.configure_item(self.TAG_ASSIGN_DIALOG, show=False)
        selected_name = dpg.get_value(self.TAG_ASSIGN_LIST)
        person_id = None
        for name, pid in self._assign_person_map:
            if name == selected_name:
                person_id = pid
                break
        if person_id is None:
            self._resume_auto_refresh()
            return
        if self._assign_mode == "split":
            for face_id in list(self._split_selected):
                self.db.assign_face_to_person(face_id, person_id)
            self.face_analyzer.load_person_embeddings()
            self._split_selected.clear()
            self._render_split_faces()
            dpg.configure_item(self.TAG_SPLIT_DIALOG, show=False)
        else:
            cluster = self._selected_cluster_snapshot or next(
                (c for c in self._face_clusters if c.cluster_id == self._selected_cluster_id),
                None,
            )
            if not cluster:
                self._resume_auto_refresh()
                return
            self.face_analyzer.assign_cluster_to_person(cluster, person_id)
            if cluster in self._face_clusters:
                self._face_clusters.remove(cluster)
        self._display_face_clusters()
        self._pending_stats_refresh = True
        threading.Thread(target=self._auto_refine_matches, daemon=True).start()
        self._resume_auto_refresh()

    def _cancel_assign_dialog(self) -> None:
        """Cancel assigning a cluster to a person."""
        dpg.configure_item(self.TAG_ASSIGN_DIALOG, show=False)
        self._resume_auto_refresh()

    def _cancel_person_naming(self) -> None:
        """Cancel naming a person."""
        dpg.configure_item(self.TAG_ASSIGN_DIALOG, show=False)
        self._resume_auto_refresh()

    def _get_cluster_reference_embedding(self, cluster: FaceCluster) -> np.ndarray | None:
        """Return an average embedding for a cluster."""
        if cluster.avg_embedding is not None and len(cluster.avg_embedding) > 0:
            return np.asarray(cluster.avg_embedding, dtype=np.float32)
        faces = self.db.get_faces_by_ids(cluster.face_ids)
        embeddings = [np.frombuffer(face.embedding, dtype=np.float32) for face in faces if face.embedding]
        if not embeddings:
            return None
        return np.mean(embeddings, axis=0)

    def _get_split_reference_embedding(self) -> np.ndarray | None:
        """Return an average embedding for selected split faces."""
        if not self._split_selected:
            return None
        faces = self.db.get_faces_by_ids(list(self._split_selected))
        embeddings = [np.frombuffer(face.embedding, dtype=np.float32) for face in faces if face.embedding]
        if not embeddings:
            return None
        return np.mean(embeddings, axis=0)

    def _build_assign_person_map(self, reference_embedding: np.ndarray | None) -> list[tuple[str, int]]:
        """Build and sort assign list by similarity to the reference embedding."""
        persons = [p for p in self.db.get_all_persons(named_only=True) if p.id is not None]
        if not persons:
            return []

        scored: list[tuple[float | None, str, int]] = []
        if reference_embedding is not None:
            try:
                self.face_analyzer.load_person_embeddings()
            except Exception:
                reference_embedding = None

        for person in persons:
            name = person.name or f"Person {person.id}"
            score = None
            if reference_embedding is not None:
                embeddings = self.face_analyzer._person_embeddings.get(person.id, [])
                if embeddings:
                    score = max(
                        self.face_analyzer.compute_similarity(reference_embedding, emb)
                        for _stage, emb in embeddings
                    )
            label = f"{name} ({score:.2f})" if score is not None else f"{name} (n/a)"
            scored.append((score, label, person.id))

        scored.sort(key=lambda item: (-item[0] if item[0] is not None else 1.0, item[1].lower()))
        return [(label, pid) for _score, label, pid in scored]

    def _on_face_settings_changed(self, sender, app_data, user_data) -> None:
        """Persist face analysis settings and update analyzer."""
        self.config.ai.face_detection_threshold = dpg.get_value(self.TAG_FACE_DET_THRESHOLD)
        self.config.ai.face_recognition_threshold = dpg.get_value(self.TAG_FACE_MATCH_THRESHOLD)
        self.config.ai.face_clustering_threshold = dpg.get_value(self.TAG_FACE_CLUSTER_THRESHOLD)
        save_config()
        if self._face_analyzer:
            self._face_analyzer.det_conf_threshold = self.config.ai.face_detection_threshold
            self._face_analyzer.match_threshold = self.config.ai.face_recognition_threshold
            self._face_analyzer.cluster_similarity_threshold = self.config.ai.face_clustering_threshold

    # ------------------------------------------------------------------ #
    #  Celebrity Identification                                            #
    # ------------------------------------------------------------------ #

    def _get_celebrity_identifier(self):
        """Get or create the CelebrityIdentifier instance."""
        if self._celebrity_identifier is None:
            from duplicleaner.ai.celebrities import CelebrityIdentifier
            self._celebrity_identifier = CelebrityIdentifier(self.db)
        return self._celebrity_identifier

    def _on_celebrity_settings_changed(self, sender=None, app_data=None, user_data=None) -> None:
        """Save changed celebrity identification settings to config."""
        self.config.ai.celebrity_enabled = dpg.get_value(self.TAG_CELEBRITY_ENABLED)
        self.config.ai.celebrity_provider = dpg.get_value(self.TAG_CELEBRITY_PROVIDER)
        self.config.ai.celebrity_auto_confirm_threshold = dpg.get_value(self.TAG_CELEBRITY_AUTO_THRESHOLD)
        self.config.ai.celebrity_min_confidence = dpg.get_value(self.TAG_CELEBRITY_MIN_CONFIDENCE)
        save_config()
        # Reset the identifier so it picks up new settings
        self._celebrity_identifier = None

    def _on_identify_celebrities(self, sender=None, app_data=None) -> None:
        """Launch celebrity identification on unassigned faces in a background thread."""
        if self._celebrity_thread and self._celebrity_thread.is_alive():
            self._notify_status("Celebrity identification already running", level="warning")
            return

        identifier = self._get_celebrity_identifier()
        if not identifier.is_available():
            status = identifier.get_provider_status()
            self._notify_status(f"Celebrity identification not available: {status}", level="error")
            return

        # Get unassigned faces
        unassigned = self.db.get_unassigned_faces(limit=10000)
        if not unassigned:
            self._notify_status("No unassigned faces to identify", level="info")
            return

        self._notify_status(f"Starting celebrity identification on {len(unassigned)} faces...")
        self._celebrity_cancel_event.clear()
        self._set_analysis_buttons_enabled(False)
        dpg.configure_item(self.TAG_CELEBRITY_BUTTON, label="Identifying...")

        # Show progress dialog
        self._show_celebrity_progress_dialog(len(unassigned))

        def run_identification():
            try:
                results = identifier.identify_faces(
                    faces=unassigned,
                    progress_callback=self._on_celebrity_progress,
                    cancel_event=self._celebrity_cancel_event,
                )
                self._celebrity_pending_results = results
            except Exception as exc:
                logger.error("Celebrity identification failed: %s", exc)
                self._notify_status(f"Celebrity identification failed: {exc}", level="error")
            finally:
                self._set_analysis_buttons_enabled(True)
                dpg.configure_item(self.TAG_CELEBRITY_BUTTON, label="Identify Celebrities")
                if dpg.does_item_exist(self.TAG_CELEBRITY_PROGRESS_DIALOG):
                    dpg.configure_item(self.TAG_CELEBRITY_PROGRESS_DIALOG, show=False)

                # Update pending count and show results
                pending_count = self.db.get_celebrity_match_count(status="pending")
                if pending_count > 0:
                    self._update_celebrity_pending_count()
                    self._notify_status(
                        f"Celebrity identification complete. {pending_count} pending matches to review.",
                        level="info",
                    )
                else:
                    auto_confirmed = sum(
                        1 for r in (self._celebrity_pending_results or []) if r.status == "confirmed"
                    )
                    if auto_confirmed:
                        self._notify_status(
                            f"Celebrity identification complete. {auto_confirmed} auto-confirmed.",
                            level="info",
                        )
                        self._pending_people_refresh = True
                    else:
                        self._notify_status("Celebrity identification complete. No matches found.", level="info")

        self._celebrity_thread = threading.Thread(target=run_identification, daemon=True)
        self._celebrity_thread.start()

    def _on_celebrity_progress(self, progress) -> None:
        """Update celebrity identification progress UI."""
        if dpg.does_item_exist(self.TAG_CELEBRITY_PROGRESS_TEXT):
            pct = progress.percent_complete
            text = f"{progress.processed_faces}/{progress.total_faces} faces ({pct:.0f}%)"
            if progress.identified_faces > 0:
                text += f" - {progress.identified_faces} identified"
            dpg.set_value(self.TAG_CELEBRITY_PROGRESS_TEXT, text)
        if dpg.does_item_exist(self.TAG_CELEBRITY_PROGRESS_BAR):
            dpg.set_value(self.TAG_CELEBRITY_PROGRESS_BAR, progress.percent_complete / 100.0)

    def _show_celebrity_progress_dialog(self, total_faces: int) -> None:
        """Show a progress dialog for celebrity identification."""
        if dpg.does_item_exist(self.TAG_CELEBRITY_PROGRESS_DIALOG):
            dpg.delete_item(self.TAG_CELEBRITY_PROGRESS_DIALOG)

        with dpg.window(
            label="Celebrity Identification",
            tag=self.TAG_CELEBRITY_PROGRESS_DIALOG,
            modal=True,
            width=400,
            height=150,
            no_resize=True,
            no_close=True,
            pos=[400, 300],
        ):
            dpg.add_text(f"Identifying celebrities in {total_faces} unassigned faces...")
            dpg.add_progress_bar(
                tag=self.TAG_CELEBRITY_PROGRESS_BAR,
                default_value=0.0,
                width=-1,
            )
            dpg.add_text("Starting...", tag=self.TAG_CELEBRITY_PROGRESS_TEXT)
            dpg.add_spacer(height=5)
            dpg.add_button(
                label="Cancel",
                callback=lambda: self._celebrity_cancel_event.set(),
                width=-1,
            )

    def _show_celebrity_review_dialog(self, sender=None, app_data=None) -> None:
        """Show pending celebrity matches for user review."""
        pending = self.db.get_pending_celebrity_matches(limit=200)

        if dpg.does_item_exist(self.TAG_CELEBRITY_REVIEW_DIALOG):
            dpg.delete_item(self.TAG_CELEBRITY_REVIEW_DIALOG)

        # Clean up old handler registries
        for reg in self._celebrity_review_handler_registries:
            if dpg.does_item_exist(reg):
                dpg.delete_item(reg)
        self._celebrity_review_handler_registries = []

        with dpg.window(
            label="Celebrity Match Review",
            tag=self.TAG_CELEBRITY_REVIEW_DIALOG,
            modal=True,
            width=650,
            height=500,
            no_resize=False,
            pos=[250, 150],
            on_close=lambda: dpg.configure_item(self.TAG_CELEBRITY_REVIEW_DIALOG, show=False),
        ):
            dpg.add_text(
                f"Pending celebrity matches: {len(pending)}",
                tag=self.TAG_CELEBRITY_REVIEW_STATUS,
            )

            if not pending:
                dpg.add_text("No pending matches to review.")
                return

            # Batch action buttons
            with dpg.group(horizontal=True):
                dpg.add_button(
                    label="Confirm All High-Confidence",
                    callback=self._on_confirm_all_above_threshold,
                )
                dpg.add_button(
                    label="Reject All Low-Confidence",
                    callback=self._on_reject_all_below_threshold,
                )

            dpg.add_separator()

            # Scrollable list of pending matches
            with dpg.child_window(
                tag=self.TAG_CELEBRITY_REVIEW_CONTAINER,
                autosize_x=True,
                height=-1,
            ):
                for match in pending:
                    with dpg.group(horizontal=True):
                        # Face thumbnail placeholder
                        with dpg.group():
                            face = self.db.get_face(match.face_id) if match.face_id else None
                            if face:
                                file_rec = self.db.get_file(face.file_id) if face else None
                                path_text = os.path.basename(file_rec.path) if file_rec else f"face {match.face_id}"
                            else:
                                path_text = f"face {match.face_id}"
                            dpg.add_text(f"[Face #{match.face_id}]", color=get_text_color("disabled"))
                            dpg.add_text(path_text, color=get_text_color("disabled"), wrap=150)

                        # Celebrity info
                        with dpg.group():
                            dpg.add_text(match.celebrity_name, color=get_accent_color())
                            conf_color = (100, 255, 100) if match.confidence >= 0.9 else (255, 200, 80) if match.confidence >= 0.7 else (255, 100, 100)
                            dpg.add_text(f"Confidence: {match.confidence:.1%}", color=conf_color)
                            dpg.add_text(f"Provider: {match.provider}", color=get_text_color("disabled"))
                            if match.known_for:
                                dpg.add_text(f"Known for: {match.known_for}", color=get_text_color("disabled"), wrap=250)

                        # Action buttons
                        with dpg.group():
                            dpg.add_spacer(height=5)
                            match_id = match.id

                            dpg.add_button(
                                label="Confirm",
                                callback=lambda s, a, u=match_id: self._on_confirm_celebrity_match(u),
                                small=True,
                            )
                            dpg.add_button(
                                label="Reject",
                                callback=lambda s, a, u=match_id: self._on_reject_celebrity_match(u),
                                small=True,
                            )

                    dpg.add_separator()

    def _on_confirm_celebrity_match(self, match_id: int) -> None:
        """Confirm a single celebrity match."""
        identifier = self._get_celebrity_identifier()
        person_id = identifier.confirm_match(match_id)
        if person_id:
            self._notify_status("Celebrity match confirmed", level="info")
            self._pending_people_refresh = True
        else:
            self._notify_status("Failed to confirm match", level="error")
        self._update_celebrity_pending_count()
        # Refresh the review dialog
        self._show_celebrity_review_dialog()

    def _on_reject_celebrity_match(self, match_id: int) -> None:
        """Reject a single celebrity match."""
        identifier = self._get_celebrity_identifier()
        identifier.reject_match(match_id)
        self._notify_status("Celebrity match rejected", level="info")
        self._update_celebrity_pending_count()
        # Refresh the review dialog
        self._show_celebrity_review_dialog()

    def _on_confirm_all_above_threshold(self, sender=None, app_data=None) -> None:
        """Confirm all pending matches above the auto-confirm threshold."""
        threshold = self.config.ai.celebrity_auto_confirm_threshold
        pending = self.db.get_pending_celebrity_matches(limit=1000)
        identifier = self._get_celebrity_identifier()

        confirmed = 0
        for match in pending:
            if match.confidence >= threshold:
                person_id = identifier.confirm_match(match.id)
                if person_id:
                    confirmed += 1

        self._notify_status(f"Auto-confirmed {confirmed} celebrity matches", level="info")
        self._update_celebrity_pending_count()
        self._pending_people_refresh = True
        self._show_celebrity_review_dialog()

    def _on_reject_all_below_threshold(self, sender=None, app_data=None) -> None:
        """Reject all pending matches below the minimum confidence threshold."""
        threshold = self.config.ai.celebrity_min_confidence
        pending = self.db.get_pending_celebrity_matches(limit=1000)
        identifier = self._get_celebrity_identifier()

        rejected = 0
        for match in pending:
            if match.confidence < threshold:
                identifier.reject_match(match.id)
                rejected += 1

        self._notify_status(f"Rejected {rejected} low-confidence matches", level="info")
        self._update_celebrity_pending_count()
        self._show_celebrity_review_dialog()

    def _update_celebrity_pending_count(self) -> None:
        """Update the pending celebrity match count badge in the toolbar."""
        if not dpg.does_item_exist(self.TAG_CELEBRITY_PENDING_COUNT):
            return
        count = self.db.get_celebrity_match_count(status="pending")
        if count > 0:
            dpg.configure_item(
                self.TAG_CELEBRITY_PENDING_COUNT,
                label=f"Review {count} Pending",
                show=True,
            )
        else:
            dpg.configure_item(self.TAG_CELEBRITY_PENDING_COUNT, show=False)

    def _on_reset_faces_clicked(self) -> None:
        """Show confirmation dialog before clearing face detections."""
        mode = dpg.get_value(self.TAG_FACE_RESET_MODE)
        scope = dpg.get_value(self.TAG_FACE_RESET_SCOPE)
        drive_id = None
        for label, did in self._drive_scope_map:
            if label == scope:
                drive_id = did
                break

        # Store pending reset info
        self._pending_reset_mode = mode
        self._pending_reset_scope = scope
        self._pending_reset_drive_id = drive_id

        # Count faces that will be affected
        if mode == "Clear all faces":
            count = self.db.get_face_count() if drive_id is None else self.db.get_face_count_for_drive(drive_id)
            severity = "high"
            color = (255, 80, 80)
        elif mode == "Clear unassigned faces":
            count = len(self.db.get_unassigned_faces(limit=100000))
            severity = "medium"
            color = (255, 200, 80)
        else:
            count = self.db.get_low_confidence_face_count(
                self.config.ai.face_detection_threshold,
                drive_id,
            )
            severity = "low"
            color = (100, 200, 100)

        # Show confirmation dialog
        self._show_reset_confirm_dialog(mode, scope, count, severity, color)

    def _show_reset_confirm_dialog(
        self,
        mode: str,
        scope: str,
        count: int,
        severity: str,
        color: tuple[int, int, int],
    ) -> None:
        """Show the reset confirmation dialog with severity indicator."""
        if not dpg.does_item_exist(self.TAG_RESET_CONFIRM_DIALOG):
            return

        # Update dialog text
        scope_text = f"from {scope}" if scope != "All Drives" else "from all drives"
        dpg.set_value(
            self.TAG_RESET_CONFIRM_TEXT,
            f"This will {mode.lower()} {scope_text}."
        )
        dpg.set_value(self.TAG_RESET_CONFIRM_COUNT, f"{count:,} faces will be deleted")
        dpg.configure_item(self.TAG_RESET_CONFIRM_COUNT, color=color)
        dpg.configure_item(self.TAG_RESET_CONFIRM_DIALOG, show=True)

    def _confirm_reset(self) -> None:
        """Execute the pending reset operation after confirmation."""
        dpg.configure_item(self.TAG_RESET_CONFIRM_DIALOG, show=False)

        mode = self._pending_reset_mode
        drive_id = self._pending_reset_drive_id

        if mode == "Clear all faces":
            deleted = self.db.delete_all_faces() if drive_id is None else self.db.delete_faces_for_drive(drive_id)
        elif mode == "Clear unassigned faces":
            deleted = self.db.delete_unassigned_faces(drive_id)
        else:
            deleted = self.db.delete_low_confidence_faces(
                self.config.ai.face_detection_threshold,
                drive_id,
            )

        self._pending_reset_mode = None
        self._pending_reset_scope = None
        self._pending_reset_drive_id = None

        self._refresh()
        self._notify_status(f"Cleared {deleted} faces.", level="info")

    def _cancel_reset(self) -> None:
        """Cancel the pending reset operation."""
        dpg.configure_item(self.TAG_RESET_CONFIRM_DIALOG, show=False)
        self._pending_reset_mode = None
        self._pending_reset_scope = None
        self._pending_reset_drive_id = None

    def _refresh_drive_scopes(self) -> None:
        """Refresh drive scope list for reset operations."""
        drives = self.db.get_all_drives()
        self._drive_scope_map = [("All Drives", None)]
        for drive in drives:
            label = drive.label or drive.path or drive.id
            self._drive_scope_map.append((label, drive.id))
        if dpg.does_item_exist(self.TAG_FACE_RESET_SCOPE):
            dpg.configure_item(
                self.TAG_FACE_RESET_SCOPE,
                items=[label for label, _ in self._drive_scope_map],
            )

    def _save_pet_name(self) -> None:
        """Save pet name from dialog."""
        dpg.configure_item(self.TAG_PET_NAME_DIALOG, show=False)

        name = dpg.get_value("pet_name_input").strip()
        if not name:
            return

        breed = dpg.get_value("pet_breed_input").strip() or None
        birth_year = dpg.get_value("pet_birth_year_input") or None
        color_pattern = dpg.get_value("pet_color_input").strip() or None

        # Find cluster
        cluster = next((c for c in self._pet_clusters if c.cluster_id == self._selected_cluster_id), None)
        if not cluster:
            return

        # Create pet
        pet_id = self.pet_analyzer.create_pet_from_cluster(
            cluster, name, breed, birth_year, color_pattern
        )
        if pet_id:
            logger.info(f"Created pet: {name}")
            self._pet_clusters.remove(cluster)
            self._display_pet_clusters()
            self._update_stats()

    def _view_cluster_photos(self, cluster_id: int) -> None:
        """View photos in a face cluster."""
        cluster = next((c for c in self._face_clusters if c.cluster_id == cluster_id), None)
        if cluster and cluster.sample_faces:
            # Get file IDs
            file_ids = [f.file_id for f in cluster.sample_faces]
            if not file_ids:
                return
            if self.on_photo_selected:
                self.on_photo_selected(file_ids[0])
            else:
                self._open_file_by_id(file_ids[0])

    def _view_pet_cluster_photos(self, cluster_id: int) -> None:
        """View photos in a pet cluster."""
        cluster = next((c for c in self._pet_clusters if c.cluster_id == cluster_id), None)
        if cluster and cluster.sample_detections:
            file_ids = [d.file_id for d in cluster.sample_detections]
            if not file_ids:
                return
            if self.on_photo_selected:
                self.on_photo_selected(file_ids[0])
            else:
                self._open_file_by_id(file_ids[0])

    def _refresh_people_list(self) -> None:
        """Refresh the people list view."""
        # Clean up handler registries
        for reg in self._people_row_handler_registries:
            try:
                if dpg.does_item_exist(reg):
                    dpg.delete_item(reg)
            except Exception:
                pass
        self._people_row_handler_registries.clear()

        # Clear existing rows
        for child in dpg.get_item_children("people_table", 1):
            dpg.delete_item(child)

        # Get people based on hidden filter
        people = self.db.get_all_persons(named_only=False, include_hidden=self._show_hidden_people)

        # Filter by search term
        if self._people_search_filter:
            people = [
                p for p in people
                if p.name and self._people_search_filter in p.name.lower()
            ]

        # Filter out unnamed unless showing hidden
        if not self._show_hidden_people:
            people = [p for p in people if p.name and not p.is_hidden]

        # Update hidden count in checkbox label
        hidden_count = self.db.get_hidden_person_count()
        if dpg.does_item_exist(self.TAG_SHOW_HIDDEN_CHECKBOX):
            dpg.configure_item(self.TAG_SHOW_HIDDEN_CHECKBOX, label=f"Show Hidden ({hidden_count})")

        for person in people:
            is_hidden = person.is_hidden

            with dpg.table_row(parent="people_table"):
                # Name - selectable for right-click context menu
                # Build name label with relationship hints
                name_label = person.name or "Unknown"
                if not is_hidden and person.id is not None:
                    rels = self.db.get_relationships(person.id)
                    if rels:
                        rel_names = [f"{r['relationship_type']}: {r['other_person_name']}" for r in rels[:3]]
                        if len(rels) > 3:
                            rel_names.append(f"+{len(rels) - 3} more")
                        name_label += "  [" + ", ".join(rel_names) + "]"

                name_color = (120, 120, 120) if is_hidden else (255, 255, 255)
                name_sel = dpg.add_selectable(
                    label=name_label,
                    span_columns=False,
                )
                with dpg.item_handler_registry() as person_hr:
                    dpg.add_item_clicked_handler(
                        button=dpg.mvMouseButton_Right,
                        callback=self._show_people_context_menu,
                        user_data=person.id,
                    )
                dpg.bind_item_handler_registry(name_sel, person_hr)
                self._people_row_handler_registries.append(person_hr)
                dpg.add_text(str(person.photo_count), color=name_color if is_hidden else None)

                # Age range
                if person.birth_year:
                    current_age = person.estimated_age or 0
                    dpg.add_text(f"~{current_age} years", color=name_color if is_hidden else None)
                else:
                    dpg.add_text("-", color=name_color if is_hidden else None)

                # Actions differ for hidden vs regular people
                with dpg.group(horizontal=True):
                    if is_hidden:
                        # Hidden person actions
                        dpg.add_button(
                            label="Restore",
                            callback=lambda s, a, u: self._restore_hidden_person(u),
                            user_data=person.id,
                            small=True,
                        )
                        dpg.add_button(
                            label="Delete",
                            callback=lambda s, a, u: self._delete_hidden_person(u),
                            user_data=person.id,
                            small=True,
                        )
                    else:
                        # Regular person actions
                        dpg.add_button(
                            label="Photos",
                            callback=lambda s, a, u: self._show_person_gallery(u),
                            user_data=person.id,
                            small=True,
                        )
                        dpg.add_button(
                            label="Timeline",
                            callback=lambda s, a, u: self._show_timeline(u),
                            user_data=person.id,
                            small=True,
                        )
                        dpg.add_button(
                            label="Find More",
                            callback=lambda s, a, u: self._find_person_photos(u),
                            user_data=person.id,
                            small=True,
                        )
                        dpg.add_button(
                            label="Edit",
                            callback=lambda s, a, u: self._show_edit_person_dialog(u),
                            user_data=person.id,
                            small=True,
                        )
                        dpg.add_button(
                            label="Delete",
                            callback=lambda s, a, u: self._show_delete_person_dialog(u),
                            user_data=person.id,
                            small=True,
                        )

        # Also refresh family groups section
        self._refresh_family_groups()

    def _refresh_pets_list(self) -> None:
        """Refresh the pets list view with breed info and life stage summary."""
        for child in dpg.get_item_children("pets_table", 1):
            dpg.delete_item(child)

        pets = self.db.get_all_pets()

        for pet in pets:
            with dpg.table_row(parent="pets_table"):
                dpg.add_text(pet.name or "Unknown")
                dpg.add_text(pet.species or "-")
                dpg.add_text(pet.breed or "-")
                dpg.add_text(str(pet.photo_count))

                with dpg.group(horizontal=True):
                    dpg.add_button(
                        label="Photos",
                        callback=lambda s, a, u: self._show_pet_gallery(u),
                        user_data=pet.id,
                        small=True,
                    )
                    dpg.add_button(
                        label="Timeline",
                        callback=lambda s, a, u: self._show_pet_timeline(u),
                        user_data=pet.id,
                        small=True,
                    )
                    dpg.add_button(
                        label="Find More",
                        callback=lambda s, a, u: self._find_pet_photos(u),
                        user_data=pet.id,
                        small=True,
                    )
                    dpg.add_button(
                        label="Bridge Gaps",
                        callback=lambda s, a, u: self._bridge_pet_gaps(u),
                        user_data=pet.id,
                        small=True,
                    )

    def _open_file_by_id(self, file_id: int) -> None:
        """Open a file using the OS default handler."""
        logger.info(f"_open_file_by_id called with file_id={file_id}")

        # Don't open externally if preview dialog is showing
        if dpg.does_item_exist(self.TAG_PHOTO_PREVIEW_DIALOG) and dpg.is_item_shown(self.TAG_PHOTO_PREVIEW_DIALOG):
            logger.info("Preview dialog is already showing, skipping external open")
            return

        file_record = self.db.get_file(file_id)
        if not file_record or not file_record.path:
            logger.warning(f"File {file_id} not found or has no path")
            self._notify_status("File not found for preview.", level="warning")
            return
        try:
            logger.info(f"Opening file with os.startfile: {file_record.path}")
            os.startfile(file_record.path)
        except Exception as e:
            logger.error(f"Failed to open file {file_record.path}: {e}")
            self._notify_status("Failed to open file.", level="warning")

    def _show_timeline(self, person_id: int) -> None:
        """Show age timeline for a person with photo thumbnails and chain data."""
        self._selected_person_id = person_id
        self._gallery_person_id = person_id  # For gallery integration
        person = self.db.get_person(person_id)
        if not person:
            return

        dpg.set_value("timeline_title", f"Timeline: {person.name}")

        # Clear all tab contents
        for tag in (
            self.TAG_TIMELINE_PHOTOS_CONTENT,
            self.TAG_CHAIN_CONTENT,
            self.TAG_GAPS_CONTENT,
        ):
            for child in dpg.get_item_children(tag, 1):
                dpg.delete_item(child)

        # Gather all data
        chain_data = self._build_timeline_chain_data(person_id)

        # --- Timeline tab ---
        self._populate_timeline_photos_tab(person, chain_data)

        # --- Chain Analysis tab ---
        self._populate_chain_analysis_tab(person, chain_data)

        # --- Gap Alerts tab ---
        self._populate_gap_alerts_tab(person, chain_data)

        dpg.configure_item(self.TAG_TIMELINE_DIALOG, show=True)

    def _build_timeline_chain_data(self, person_id: int) -> dict:
        """Aggregate data for the timeline dialog tabs.

        Returns dict with keys: timeline, links, gaps, accuracy.
        """
        timeline = self.face_analyzer.get_person_timeline(person_id)
        links = self.db.get_temporal_links(person_id)
        gaps = self.face_analyzer.find_chain_gaps(person_id)
        accuracy = self.face_analyzer.get_age_estimation_accuracy(person_id)
        return {
            "timeline": timeline,
            "links": links,
            "gaps": gaps,
            "accuracy": accuracy,
        }

    def _populate_timeline_photos_tab(self, person: Person, chain_data: dict) -> None:
        """Populate the Timeline photos tab with year-by-year thumbnails."""
        parent = self.TAG_TIMELINE_PHOTOS_CONTENT
        timeline = chain_data["timeline"]
        links = chain_data["links"]

        if not timeline:
            dpg.add_text(
                "No photos found with date information.",
                parent=parent,
                color=get_text_color("disabled"),
            )
            return

        # Build a lookup: (year_a, year_b) -> link_type for inter-year indicators
        link_lookup: dict[tuple[int, int], str] = {}
        for link in links:
            # Get years from the faces in the link
            face_a = self.db.get_face(link["face_id_a"])
            face_b = self.db.get_face(link["face_id_b"])
            if face_a and face_b:
                date_a = self.db.get_photo_date_for_face(link["face_id_a"])
                date_b = self.db.get_photo_date_for_face(link["face_id_b"])
                if date_a and date_b:
                    key = (date_a.year, date_b.year)
                    # Keep the weakest link type between years
                    existing = link_lookup.get(key)
                    priority = {"break": 0, "weak": 1, "auto": 2, "confirmed": 3}
                    lt = link.get("link_type", "auto")
                    if existing is None or priority.get(lt, 0) < priority.get(existing, 0):
                        link_lookup[key] = lt

        prev_year = None
        for year, faces in timeline:
            # Show link indicator between years
            if prev_year is not None:
                lt = link_lookup.get((prev_year, year))
                if lt is None:
                    # Check reverse
                    lt = link_lookup.get((year, prev_year))
                indicator_color = {
                    "auto": (0, 200, 0, 255),       # green
                    "confirmed": (0, 200, 0, 255),   # green
                    "weak": (230, 200, 0, 255),      # yellow
                    "break": (220, 50, 50, 255),     # red
                }.get(lt, (128, 128, 128, 255))      # gray for no link
                indicator_text = {
                    "auto": "--- strong link ---",
                    "confirmed": "--- confirmed link ---",
                    "weak": "--- weak link ---",
                    "break": "--- BREAK ---",
                }.get(lt, f"--- gap ({year - prev_year - 1} years) ---")
                dpg.add_text(
                    f"  {indicator_text}",
                    parent=parent,
                    color=indicator_color,
                )

            with dpg.group(parent=parent, horizontal=False):
                age = year - person.birth_year if person.birth_year else None
                age_text = f" (Age ~{age})" if age is not None else ""
                dpg.add_text(
                    f"{year}{age_text} - {len(faces)} photos",
                    color=get_accent_color(),
                )
                dpg.add_separator()
                dpg.add_spacer(height=5)

                row_group = None
                photos_per_row = 8
                max_photos = 24

                for i, face in enumerate(faces[:max_photos]):
                    if i % photos_per_row == 0:
                        row_group = dpg.add_group(horizontal=True, parent=parent)
                        dpg.add_spacer(width=5, parent=row_group)

                    thumb = self._get_face_thumbnail(face)
                    if thumb and row_group:
                        dpg.add_image_button(
                            thumb,
                            width=72,
                            height=72,
                            parent=row_group,
                            user_data=face.id,
                            callback=lambda s, a, u: self._show_photo_preview(u),
                        )

                if len(faces) > max_photos:
                    overflow_count = len(faces) - max_photos
                    dpg.add_text(
                        f"  +{overflow_count} more photos",
                        parent=parent,
                        color=get_text_color("disabled"),
                    )

                dpg.add_spacer(height=10)
            prev_year = year

    def _populate_chain_analysis_tab(self, person: Person, chain_data: dict) -> None:
        """Populate the Chain Analysis tab with embedding drift and accuracy."""
        parent = self.TAG_CHAIN_CONTENT
        links = chain_data["links"]
        accuracy = chain_data["accuracy"]

        # Embedding drift between consecutive faces
        dpg.add_text("Embedding Drift (consecutive links):", parent=parent, color=get_accent_color())
        dpg.add_separator(parent=parent)
        dpg.add_spacer(height=5, parent=parent)

        if not links:
            dpg.add_text(
                "No temporal chain built yet. Click 'Build Chain' below.",
                parent=parent,
                color=get_text_color("disabled"),
            )
        else:
            for link in links:
                sim = link.get("similarity", 0.0)
                threshold = link.get("threshold_used", 0.0)
                lt = link.get("link_type", "unknown")
                gap = link.get("temporal_distance_days", 0)
                age_a = link.get("age_a")
                age_b = link.get("age_b")

                age_str = ""
                if age_a is not None and age_b is not None:
                    age_str = f"  age ~{age_a} -> ~{age_b}"

                color = {
                    "auto": (0, 200, 0, 255),
                    "confirmed": (0, 200, 0, 255),
                    "weak": (230, 200, 0, 255),
                    "break": (220, 50, 50, 255),
                }.get(lt, (180, 180, 180, 255))

                gap_str = f"{gap}d" if gap < 365 else f"{gap // 365}y {gap % 365}d"
                dpg.add_text(
                    f"  Face {link['face_id_a']} -> {link['face_id_b']}:  "
                    f"sim={sim:.3f}  thresh={threshold:.3f}  "
                    f"[{lt}]  gap={gap_str}{age_str}",
                    parent=parent,
                    color=color,
                )

        # Age estimation accuracy
        dpg.add_spacer(height=15, parent=parent)
        dpg.add_text("Age Estimation Accuracy:", parent=parent, color=get_accent_color())
        dpg.add_separator(parent=parent)
        dpg.add_spacer(height=5, parent=parent)

        if not accuracy:
            dpg.add_text(
                "No accuracy data (requires birth_year and AI age estimates).",
                parent=parent,
                color=get_text_color("disabled"),
            )
        else:
            dpg.add_text(
                "  Face ID  | Year  | Est.Age | Actual | Error",
                parent=parent,
                color=get_text_color("disabled"),
            )
            for entry in accuracy:
                err = entry["error"]
                color = (0, 200, 0, 255) if abs(err) <= 3 else (
                    (230, 200, 0, 255) if abs(err) <= 6 else (220, 50, 50, 255)
                )
                dpg.add_text(
                    f"  {entry['face_id']:>7}  | {entry['photo_year']}  | "
                    f"{entry['estimated_age']:>7} | {entry['actual_age']:>6} | "
                    f"{err:+d}",
                    parent=parent,
                    color=color,
                )

    def _populate_gap_alerts_tab(self, person: Person, chain_data: dict) -> None:
        """Populate the Gap Alerts tab with missing year information."""
        parent = self.TAG_GAPS_CONTENT
        gaps = chain_data["gaps"]

        dpg.add_text("Missing Year Ranges:", parent=parent, color=get_accent_color())
        dpg.add_separator(parent=parent)
        dpg.add_spacer(height=5, parent=parent)

        if not gaps:
            dpg.add_text(
                "No gaps detected in the timeline.",
                parent=parent,
                color=(0, 200, 0, 255),
            )
            return

        for gap_start, gap_end, gap_size in gaps:
            if person.birth_year:
                age_start = gap_start - person.birth_year
                age_end = gap_end - person.birth_year
                dpg.add_text(
                    f"  No photos of {person.name} between ages "
                    f"{age_start}-{age_end} ({gap_start}-{gap_end})",
                    parent=parent,
                    color=(230, 200, 0, 255),
                )
            else:
                dpg.add_text(
                    f"  No photos between {gap_start}-{gap_end} "
                    f"({int(gap_size)} year gap)",
                    parent=parent,
                    color=(230, 200, 0, 255),
                )

    def _on_build_chain(self, sender=None, app_data=None) -> None:
        """Build/rebuild temporal chain for the selected person."""
        if not self._selected_person_id:
            return
        result = self.face_analyzer.build_temporal_chain(
            self._selected_person_id, _rebuild=True
        )
        self._notify_status(
            f"Chain built: {result.total_links} links "
            f"({result.strong_links} strong, {result.weak_links} weak, "
            f"{result.breaks} breaks)"
        )
        # Refresh the timeline dialog
        self._show_timeline(self._selected_person_id)

    def _on_review_chain_links(self, sender=None, app_data=None) -> None:
        """Open the cross-age linking dialog for the selected person."""
        if not self._selected_person_id:
            return
        self._show_cross_age_dialog(self._selected_person_id)

    def _show_pet_timeline(self, pet_id: int) -> None:
        """Show timeline for a pet with life stage info."""
        self._selected_pet_id = pet_id
        pet = self.db.get_pet(pet_id)
        if not pet:
            return

        breed_str = f" - {pet.breed}" if pet.breed else ""
        dpg.set_value("timeline_title", f"Timeline: {pet.name} ({pet.species}{breed_str})")

        # Clear all tab contents (reuse timeline dialog for pets)
        for tag in (
            self.TAG_TIMELINE_PHOTOS_CONTENT,
            self.TAG_CHAIN_CONTENT,
            self.TAG_GAPS_CONTENT,
        ):
            for child in dpg.get_item_children(tag, 1):
                dpg.delete_item(child)

        timeline = self.pet_analyzer.get_pet_timeline(pet_id)

        # Timeline photos tab
        for year, detections in timeline:
            # Count life stages for this year
            stages = {}
            for det in detections:
                s = det.estimated_age_stage.value if det.estimated_age_stage else "unknown"
                stages[s] = stages.get(s, 0) + 1
            stage_str = ", ".join(f"{k}: {v}" for k, v in sorted(stages.items()))

            with dpg.group(parent=self.TAG_TIMELINE_PHOTOS_CONTENT, horizontal=False):
                dpg.add_text(
                    f"{year}: {len(detections)} photos ({stage_str})",
                    color=get_accent_color(),
                )

        # Life stages summary tab
        stage_summary = self.pet_analyzer.get_life_stage_summary(pet_id)
        if stage_summary:
            with dpg.group(parent=self.TAG_CHAIN_CONTENT, horizontal=False):
                dpg.add_text("Life Stage Distribution", color=get_accent_color())
                dpg.add_separator()
                for stage, count in sorted(stage_summary.items()):
                    dpg.add_text(f"  {stage.capitalize()}: {count} photos")

        # Gap detection tab
        if len(timeline) >= 2:
            years = [y for y, _ in timeline]
            with dpg.group(parent=self.TAG_GAPS_CONTENT, horizontal=False):
                dpg.add_text("Timeline Coverage", color=get_accent_color())
                dpg.add_separator()
                for i in range(len(years) - 1):
                    gap = years[i + 1] - years[i]
                    if gap >= 2:
                        color = (255, 100, 100, 255) if gap >= 3 else (255, 200, 100, 255)
                        dpg.add_text(
                            f"  Gap: {years[i]} -> {years[i+1]} ({gap} years)",
                            color=color,
                        )
                if all(years[i + 1] - years[i] <= 1 for i in range(len(years) - 1)):
                    dpg.add_text("  No gaps found", color=(0, 200, 0, 255))

        dpg.configure_item(self.TAG_TIMELINE_DIALOG, show=True)

    def _show_cross_age_dialog(self, person_id: int) -> None:
        """Show the cross-age linking dialog for reviewing weak/transitive links."""
        person = self.db.get_person(person_id)
        if not person:
            return

        dpg.set_value("cross_age_title", f"Chain Links: {person.name}")

        # Clear container
        for child in dpg.get_item_children(self.TAG_CROSS_AGE_CONTAINER, 1):
            dpg.delete_item(child)

        container = self.TAG_CROSS_AGE_CONTAINER

        # Section 1: Weak temporal links for review
        weak_links = self.db.get_weak_temporal_links(person_id)
        # Also include "break" links
        all_links = self.db.get_temporal_links(person_id)
        break_links = [l for l in all_links if l.get("link_type") == "break"]
        review_links = weak_links + break_links

        # Deduplicate by (face_id_a, face_id_b)
        seen: set[tuple[int, int]] = set()
        unique_review: list[dict] = []
        for link in review_links:
            key = (link["face_id_a"], link["face_id_b"])
            if key not in seen:
                seen.add(key)
                unique_review.append(link)

        dpg.add_text(
            f"Weak / Broken Links ({len(unique_review)}):",
            parent=container,
            color=get_accent_color(),
        )
        dpg.add_separator(parent=container)
        dpg.add_spacer(height=5, parent=container)

        summary_parts = []
        if not unique_review:
            dpg.add_text(
                "No weak or broken links to review.",
                parent=container,
                color=(0, 200, 0, 255),
            )
        else:
            for link in unique_review:
                fid_a = link["face_id_a"]
                fid_b = link["face_id_b"]
                sim = link.get("similarity", 0.0)
                gap = link.get("temporal_distance_days", 0)
                lt = link.get("link_type", "unknown")

                with dpg.group(parent=container, horizontal=False):
                    with dpg.group(horizontal=True):
                        # Face A thumbnail
                        face_a = self.db.get_face(fid_a)
                        if face_a:
                            thumb_a = self._get_face_thumbnail(face_a)
                            if thumb_a:
                                dpg.add_image(thumb_a, width=64, height=64)

                        # Info text
                        gap_str = f"{gap}d" if gap < 365 else f"{gap // 365}y"
                        color = (230, 200, 0, 255) if lt == "weak" else (220, 50, 50, 255)
                        dpg.add_text(
                            f" [{lt}] sim={sim:.3f} gap={gap_str} ",
                            color=color,
                        )

                        # Face B thumbnail
                        face_b = self.db.get_face(fid_b)
                        if face_b:
                            thumb_b = self._get_face_thumbnail(face_b)
                            if thumb_b:
                                dpg.add_image(thumb_b, width=64, height=64)

                    # Action buttons
                    with dpg.group(horizontal=True):
                        dpg.add_spacer(width=10)
                        dpg.add_button(
                            label="Confirm",
                            user_data=(fid_a, fid_b, person_id),
                            callback=self._on_confirm_link,
                            small=True,
                        )
                        dpg.add_button(
                            label="Reject",
                            user_data=(fid_a, fid_b, person_id),
                            callback=self._on_reject_link,
                            small=True,
                        )
                        dpg.add_button(
                            label="Split (unassign later face)",
                            user_data=(fid_b, person_id),
                            callback=self._on_split_link,
                            small=True,
                        )

                    dpg.add_separator(parent=container)

        # Section 2: Transitive match suggestions
        dpg.add_spacer(height=10, parent=container)
        dpg.add_text(
            "Transitive Match Suggestions:",
            parent=container,
            color=get_accent_color(),
        )
        dpg.add_separator(parent=container)
        dpg.add_spacer(height=5, parent=container)

        # Get unassigned faces to check for transitive matches
        unassigned_faces = self.db.get_unassigned_faces()
        transitive_found = 0

        # Check a sample of unassigned faces for transitive reachability
        for uf in unassigned_faces[:50]:
            matches = self.face_analyzer.find_transitive_matches(uf, max_hops=3)
            for pid, pname, confidence, hops in matches:
                if pid != person_id:
                    continue
                if confidence < 0.3:
                    continue
                transitive_found += 1

                with dpg.group(parent=container, horizontal=True):
                    thumb = self._get_face_thumbnail(uf)
                    if thumb:
                        dpg.add_image(thumb, width=64, height=64)
                    dpg.add_text(
                        f" Face {uf.id} -> {pname} via {hops} hop(s), "
                        f"confidence={confidence:.3f}",
                        color=(180, 180, 255, 255),
                    )
                    dpg.add_button(
                        label=f"Assign to {pname}",
                        user_data=(uf.id, person_id),
                        callback=self._on_assign_transitive,
                        small=True,
                    )
                    dpg.add_button(
                        label="Not This Person",
                        small=True,
                    )

        if transitive_found == 0:
            dpg.add_text(
                "No transitive matches found for unassigned faces.",
                parent=container,
                color=get_text_color("disabled"),
            )

        summary_parts.append(f"{len(unique_review)} links to review")
        summary_parts.append(f"{transitive_found} transitive suggestions")
        dpg.set_value("cross_age_summary", ", ".join(summary_parts))

        dpg.configure_item(self.TAG_CROSS_AGE_DIALOG, show=True)

    def _on_confirm_link(self, sender, app_data, user_data) -> None:
        """Confirm a weak temporal link (upgrade to 'confirmed')."""
        fid_a, fid_b, person_id = user_data
        self.db.update_temporal_link_type(fid_a, fid_b, "confirmed")
        self._notify_status(f"Link {fid_a}->{fid_b} confirmed.")
        # Refresh dialog
        self._show_cross_age_dialog(person_id)

    def _on_reject_link(self, sender, app_data, user_data) -> None:
        """Reject a temporal link (delete it)."""
        fid_a, fid_b, person_id = user_data
        self.db.delete_temporal_link(fid_a, fid_b)
        self._notify_status(f"Link {fid_a}->{fid_b} removed.")
        self._show_cross_age_dialog(person_id)

    def _on_split_link(self, sender, app_data, user_data) -> None:
        """Split: unassign the later face from the person."""
        face_id, person_id = user_data
        self.db.unassign_face_from_person(face_id)
        self.face_analyzer.refresh_person_embeddings(person_id)
        # Rebuild chain without the split face
        self.face_analyzer.build_temporal_chain(person_id, _rebuild=True)
        self._notify_status(f"Face {face_id} unassigned from person.")
        self._show_cross_age_dialog(person_id)

    def _on_assign_transitive(self, sender, app_data, user_data) -> None:
        """Assign a transitive match to a person."""
        face_id, person_id = user_data
        self.db.assign_face_to_person(face_id, person_id)
        self.db.update_person_photo_count(person_id)
        self.face_analyzer.refresh_person_embeddings(person_id)
        self.face_analyzer.build_temporal_chain(person_id, _rebuild=True)
        self._notify_status(f"Face {face_id} assigned to person via transitive match.")
        self._show_cross_age_dialog(person_id)

    def _find_more_photos(self) -> None:
        """Find more photos for selected person/pet."""
        if self._selected_person_id:
            self._find_person_photos(self._selected_person_id)
        elif self._selected_pet_id:
            self._find_pet_photos(self._selected_pet_id)

    def _find_person_photos(self, person_id: int) -> None:
        """Find more photos of a specific person.

        First does direct embedding matching against ALL unassigned faces,
        then shows cluster-based suggestions if a cluster run exists.

        Args:
            person_id: ID of the person to find more photos for
        """
        person = self.db.get_person(person_id)
        person_name = person.name if person else f"Person {person_id}"

        self._notify_status(f"Finding more photos for {person_name}...")

        try:
            # Direct embedding match against ALL unassigned faces
            matches, assigned = self.face_analyzer.find_more_faces_for_person(
                person_id=person_id, auto_assign=True,
            )
            if assigned:
                logger.info(
                    "Direct match for %s: %d matches, %d auto-assigned",
                    person_name, matches, assigned,
                )
                self._notify_status(
                    f"Auto-assigned {assigned} photos to {person_name}"
                )
                self._update_stats()
                self._refresh_people_list()

            # Also show cluster-based suggestions for lower-confidence matches
            if self.db.get_latest_face_cluster_run():
                self._show_intermediate_clusters_dialog(person_id)
            elif not assigned:
                self._notify_status(f"No new photos found for {person_name}")
        except Exception as e:
            logger.error(f"Error finding photos for person {person_id}: {e}")
            self._notify_status(f"Error searching for {person_name}", level="error")

    def _find_pet_photos(self, pet_id: int) -> None:
        """Find more photos of a specific pet.

        Args:
            pet_id: ID of the pet to find more photos for
        """
        pet = self.db.get_pet(pet_id)
        pet_name = pet.name if pet else f"Pet {pet_id}"

        self._notify_status(f"Searching for more photos of {pet_name}...")

        try:
            matches, assigned = self.pet_analyzer.find_more_detections_for_pet(
                pet_id=pet_id,
                threshold=0.65,
                auto_assign=True
            )
            if assigned > 0:
                self._notify_status(f"Found {assigned} new photos of {pet_name}")
            else:
                self._notify_status(f"No new photos found for {pet_name}")
            logger.info(f"Find more for {pet_name}: {matches} matches, {assigned} assigned")
            self._update_stats()
            self._refresh_pets_list()
        except Exception as e:
            logger.error(f"Error finding photos for pet {pet_id}: {e}")
            self._notify_status(f"Error searching for {pet_name}", level="error")

    def _bridge_pet_gaps(self, pet_id: int) -> None:
        """Bridge temporal gaps in a pet's timeline.

        Uses relaxed thresholds to find photos from years where the pet
        has no photos, connecting puppy->young->adult progressions.

        Args:
            pet_id: ID of the pet to bridge gaps for
        """
        pet = self.db.get_pet(pet_id)
        pet_name = pet.name if pet else f"Pet {pet_id}"

        self._notify_status(f"Bridging timeline gaps for {pet_name}...")

        try:
            gaps, assigned = self.pet_analyzer.bridge_temporal_gaps(
                pet_id=pet_id,
                max_gap_years=3,
                threshold=0.45,
            )
            if gaps == 0:
                self._notify_status(f"No timeline gaps found for {pet_name}")
            elif assigned > 0:
                self._notify_status(
                    f"Bridged {assigned} photos across {gaps} gaps for {pet_name}"
                )
            else:
                self._notify_status(
                    f"Found {gaps} gaps but no matching photos for {pet_name}"
                )
            self._update_stats()
            self._refresh_pets_list()
        except Exception as e:
            logger.error(f"Error bridging gaps for pet {pet_id}: {e}")
            self._notify_status(f"Error bridging gaps for {pet_name}", level="error")

    def _show_intermediate_clusters_dialog(self, person_id: int) -> None:
        person = self.db.get_person(person_id)
        if not person:
            self._notify_status("Person not found.", level="warning")
            return

        run = self.db.get_latest_face_cluster_run()
        if not run:
            self._notify_status("No cluster run available. Run 'Cluster Faces' first.", level="warning")
            return

        run_id, _method = run
        clusters = []
        for cluster_id, face_ids in self.db.get_face_clusters_for_run(run_id):
            faces = self.db.get_faces_by_ids(face_ids)
            if not faces:
                continue
            unassigned = [face for face in faces if face.person_id is None]
            if not unassigned:
                continue
            embeddings = []
            for face in unassigned:
                if face.embedding:
                    embeddings.append(np.frombuffer(face.embedding, dtype=np.float32))
            avg_embedding = np.mean(embeddings, axis=0) if embeddings else None
            sample_faces = self._select_cluster_sample_faces(unassigned, avg_embedding, limit=8)
            clusters.append(
                FaceCluster(
                    cluster_id=cluster_id,
                    face_ids=[face.id for face in unassigned if face.id is not None],
                    sample_faces=sample_faces,
                    avg_embedding=avg_embedding,
                )
            )

        auto_assigned, suggestions = self.face_analyzer.find_intermediate_clusters(person_id, clusters)

        auto_count = 0
        for cluster in auto_assigned:
            for face_id in cluster.face_ids:
                self.db.assign_face_to_person(face_id, person_id)
                auto_count += 1
            self.db.update_person_photo_count(person_id)

        self._intermediate_person_id = person_id
        self._intermediate_auto_assigned = auto_count
        self._intermediate_suggestions = [
            {
                "cluster_id": c.cluster_id,
                "score": score,
                "face_ids": c.face_ids,
                "sample_faces": c.sample_faces or [],
            }
            for c, score in suggestions
        ]

        dpg.set_value("intermediate_title", f"Suggested Clusters for {person.name}")
        summary = f"Auto-assigned: {auto_count} faces | Suggestions: {len(self._intermediate_suggestions)} clusters"
        dpg.set_value("intermediate_summary", summary)
        self._render_intermediate_clusters()
        dpg.configure_item(self.TAG_INTERMEDIATE_CLUSTERS_DIALOG, show=True)

        self._update_stats()
        self._refresh_people_list()

    def _render_intermediate_clusters(self) -> None:
        if not dpg.does_item_exist(self.TAG_INTERMEDIATE_CONTAINER):
            return
        for child in dpg.get_item_children(self.TAG_INTERMEDIATE_CONTAINER, 1) or []:
            dpg.delete_item(child)

        if not self._intermediate_suggestions:
            dpg.add_text("No suggested clusters found.", parent=self.TAG_INTERMEDIATE_CONTAINER)
            return

        person_embeddings = self._get_person_embedding_vectors(self._intermediate_person_id)

        for item in self._intermediate_suggestions:
            cluster_id = item["cluster_id"]
            score = item["score"]
            face_ids = item["face_ids"]
            sample_faces = item["sample_faces"]

            with dpg.group(parent=self.TAG_INTERMEDIATE_CONTAINER, horizontal=False):
                # Header with color-coded similarity score
                score_percent = int(score * 100)
                score_color = get_status_color("success") if score >= 0.7 else get_status_color("warning") if score >= 0.5 else get_status_color("error")
                with dpg.group(horizontal=True):
                    dpg.add_text(f"Cluster {cluster_id + 1} |")
                    dpg.add_text(f"{score_percent}% match", color=score_color)
                    dpg.add_text(f"| {len(face_ids)} faces")
                dpg.add_spacer(height=5)
                row = dpg.add_group(horizontal=True, parent=self.TAG_INTERMEDIATE_CONTAINER)

                # Order thumbnails by similarity to this person if possible
                if person_embeddings and sample_faces:
                    scored_faces = []
                    for face in sample_faces:
                        sim = self._score_face_for_person(face, person_embeddings)
                        scored_faces.append((sim, face))
                    scored_faces.sort(key=lambda s: s[0], reverse=True)
                    sample_faces = [s[1] for s in scored_faces]

                for face in sample_faces[:8]:
                    thumb = self._get_face_thumbnail(face)
                    if thumb:
                        dpg.add_image_button(
                            thumb,
                            width=72,
                            height=72,
                            parent=row,
                            user_data=face.id,
                            callback=lambda s, a, u: self._show_face_preview(u),
                        )
                    else:
                        # Show placeholder while thumbnail loads
                        dpg.add_button(
                            label="[Face]",
                            width=72,
                            height=72,
                            parent=row,
                            user_data=face.id,
                            callback=lambda s, a, u: self._show_face_preview(u),
                        )
                with dpg.group(horizontal=True, parent=self.TAG_INTERMEDIATE_CONTAINER):
                    dpg.add_button(
                        label="Approve",
                        small=True,
                        callback=lambda s, a, u: self._approve_intermediate_cluster(u),
                        user_data=cluster_id,
                    )
                    dpg.add_button(
                        label="Reject",
                        small=True,
                        callback=lambda s, a, u: self._reject_intermediate_cluster(u),
                        user_data=cluster_id,
                    )
                    dpg.add_button(
                        label="View All",
                        small=True,
                        callback=lambda s, a, u: self._show_all_faces_dialog(u[0], u[1]),
                        user_data=(cluster_id, face_ids),
                    )
                dpg.add_separator(parent=self.TAG_INTERMEDIATE_CONTAINER)

    def _approve_intermediate_cluster(self, cluster_id: int) -> None:
        if not self._intermediate_person_id:
            return
        item = next((s for s in self._intermediate_suggestions if s["cluster_id"] == cluster_id), None)
        if not item:
            return
        for face_id in item["face_ids"]:
            self.db.assign_face_to_person(face_id, self._intermediate_person_id)
        self.db.update_person_photo_count(self._intermediate_person_id)
        self._intermediate_suggestions = [s for s in self._intermediate_suggestions if s["cluster_id"] != cluster_id]
        self._update_intermediate_summary()
        self._render_intermediate_clusters()
        self._update_stats()
        self._refresh_people_list()

    def _reject_intermediate_cluster(self, cluster_id: int) -> None:
        self._intermediate_suggestions = [s for s in self._intermediate_suggestions if s["cluster_id"] != cluster_id]
        self._update_intermediate_summary()
        self._render_intermediate_clusters()

    def _update_intermediate_summary(self) -> None:
        if not dpg.does_item_exist("intermediate_summary"):
            return
        summary = f"Auto-assigned: {self._intermediate_auto_assigned} faces | Suggestions: {len(self._intermediate_suggestions)} clusters"
        dpg.set_value("intermediate_summary", summary)

    def _get_person_embedding_vectors(self, person_id: int | None) -> list[np.ndarray]:
        if not person_id:
            return []
        self.face_analyzer.load_person_embeddings()
        entries = self.face_analyzer._person_embeddings.get(person_id, [])
        return [emb for _stage, emb in entries]

    def _score_face_for_person(self, face: Face, person_embeddings: list[np.ndarray]) -> float:
        if not face.embedding or not person_embeddings:
            return -1.0
        try:
            emb = np.frombuffer(face.embedding, dtype=np.float32)
            best = -1.0
            for p_emb in person_embeddings:
                sim = self.face_analyzer.compute_similarity(emb, p_emb)
                if sim > best:
                    best = sim
            return best
        except Exception:
            return -1.0

    def _refresh(self) -> None:
        """Refresh all views."""
        self._refresh_drive_scopes()
        self._update_stats()
        self._update_celebrity_pending_count()
        if self._current_view == "people":
            self._refresh_people_list()
        # Skip cluster rendering if gallery dialog is open to avoid blocking gallery textures
        gallery_open = dpg.does_item_exist(self.TAG_PERSON_GALLERY_DIALOG) and dpg.is_item_shown(self.TAG_PERSON_GALLERY_DIALOG)
        if not gallery_open:
            self._display_face_clusters()
            self._display_pet_clusters()

    def refresh(self) -> None:
        """Public method to refresh the panel."""
        self._refresh()

    def on_tab_activated(self) -> None:
        """Reload clusters from DB when the Faces tab becomes visible.

        Always reloads to pick up face assignments made on other tabs
        (e.g. Files tab). The DB query is cheap (no ML).
        """
        logger.info("Faces tab activated")
        self._faces_tab_active = True
        self._load_clusters_from_db(render=True)

    def set_background_face_analysis_active(self, active: bool) -> None:
        """Update UI state when background face analysis is running."""
        self._background_face_analysis = active
        if active:
            dpg.configure_item(self.TAG_RUN_FACE_BUTTON, enabled=False, label="Face analysis running...")
            dpg.set_value(self.TAG_FACE_ANALYSIS_STATUS, "Background face analysis running")
            self._start_auto_refresh()
        else:
            dpg.configure_item(self.TAG_RUN_FACE_BUTTON, enabled=True, label="Run Face Analysis")
            dpg.set_value(self.TAG_FACE_ANALYSIS_STATUS, "")
            self._stop_auto_refresh()

    def _start_auto_refresh(self) -> None:
        if self._auto_refresh_active:
            return
        self._auto_refresh_active = True
        self._auto_refresh_thread = threading.Thread(target=self._auto_refresh_loop, daemon=True)
        self._auto_refresh_thread.start()

    def _stop_auto_refresh(self, force: bool = False) -> None:
        """Stop the auto-refresh thread.

        Args:
            force: If True, stop even if background analysis is running.
        """
        if not force and (self._background_face_analysis or self._pause_auto_refresh):
            return
        self._auto_refresh_active = False
        if self._auto_refresh_thread and self._auto_refresh_thread.is_alive():
            self._auto_refresh_thread.join(timeout=2.0)
            self._auto_refresh_thread = None

    def _auto_refresh_loop(self) -> None:
        while self._auto_refresh_active:
            with contextlib.suppress(Exception):
                self._refresh_stats_and_clusters()
            time.sleep(self._auto_refresh_interval)

    def _refresh_stats_and_clusters(self) -> None:
        """Refresh stats and optionally re-cluster when new faces appear."""
        if self._pause_auto_refresh:
            return
        try:
            face_count = self.db.get_face_count(min_confidence=self.config.ai.face_detection_threshold)
            unassigned = len(
                self.db.get_unassigned_faces(
                    limit=5000,
                    min_confidence=self.config.ai.face_detection_threshold,
                )
            )
            if face_count != self._last_face_count or unassigned != self._last_unassigned_faces:
                self._last_face_count = face_count
                self._last_unassigned_faces = unassigned
                self._pending_stats_refresh = True
                if self._current_view == "clusters" and (self._background_face_analysis or self._is_analyzing):
                    now = time.time()
                    if not self._is_clustering and (now - self._last_cluster_time) >= self._auto_cluster_interval:
                        self._last_cluster_time = now
                        self._pending_auto_cluster = True
        except Exception:
            pass

    def _resume_auto_refresh(self) -> None:
        self._pause_auto_refresh = False
        if self._background_face_analysis or self._is_analyzing:
            self._start_auto_refresh()

    def _get_face_texture(self, face: Face) -> str | None:
        if face.file_id is None:
            logger.warning(f"Face {face.id} has no file_id, cannot load texture")
            return None
        key = f"{face.file_id}:{face.bbox_x}:{face.bbox_y}:{face.bbox_w}:{face.bbox_h}"
        if key in self._face_textures:
            return self._face_textures[key]
        self._queue_texture_load(
            kind="face",
            key=key,
            face=face,
            size=64,
        )
        return None

    def _get_pet_texture(self, pet_detection: PetDetection) -> str | None:
        """Get or queue texture for a pet detection."""
        if pet_detection.file_id is None:
            logger.warning(f"Pet detection {pet_detection.id} has no file_id, cannot load texture")
            return None
        key = f"{pet_detection.file_id}:{pet_detection.bbox_x}:{pet_detection.bbox_y}:{pet_detection.bbox_w}:{pet_detection.bbox_h}"
        if key in self._pet_textures:
            return self._pet_textures[key]
        self._queue_texture_load(
            kind="pet",
            key=key,
            pet_detection=pet_detection,
            size=64,
        )
        return None

    def _create_face_texture(self, image_path: str, face: Face) -> str | None:
        try:
            raw_image = Image.open(image_path)
            image = ImageOps.exif_transpose(raw_image).convert("RGB")
            width, height = image.size

            # OpenCV auto-rotates JPEGs so bboxes are already in oriented coords
            x, y, bw, bh = face.bbox_x, face.bbox_y, face.bbox_w, face.bbox_h
            left, top, right, bottom = self._square_crop_bounds(
                x,
                y,
                bw,
                bh,
                width,
                height,
            )
            if right <= left or bottom <= top:
                return None
            cropped = image.crop((left, top, right, bottom)).resize((64, 64), Image.BILINEAR)
            rgba = cropped.convert("RGBA")
            data = np.asarray(rgba).astype(np.float32) / 255.0
            tex_tag = f"face_tex_{self._texture_counter}"
            self._texture_counter += 1
            dpg.add_static_texture(
                64,
                64,
                data.flatten().tolist(),
                tag=tex_tag,
                parent=self.TAG_TEXTURE_REGISTRY,
            )
            return tex_tag
        except Exception as exc:
            logger.warning(f"Failed to create face texture for {image_path}: {exc}")
            return None

    def _prune_textures(self, limit: int = 200) -> None:
        if len(self._face_textures) <= limit:
            return
        to_remove = list(self._face_textures.items())[: len(self._face_textures) - limit]
        for key, tex_tag in to_remove:
            with contextlib.suppress(Exception):
                dpg.delete_item(tex_tag)
            self._face_textures.pop(key, None)

    def _prune_pet_textures(self, limit: int = 200) -> None:
        """Prune old pet textures to conserve memory."""
        if len(self._pet_textures) <= limit:
            return
        to_remove = list(self._pet_textures.items())[: len(self._pet_textures) - limit]
        for key, tex_tag in to_remove:
            with contextlib.suppress(Exception):
                dpg.delete_item(tex_tag)
            self._pet_textures.pop(key, None)

    def _get_face_thumbnail(self, face: Face, size: int | None = None) -> str | None:
        """Return a cached thumbnail texture for a face crop."""
        if face.id is None or face.file_id is None:
            logger.warning(f"Face thumbnail request failed: face.id={face.id}, face.file_id={face.file_id}")
            return None
        thumb_size = size or self.GALLERY_THUMB_SIZE
        key = f"{face.id}:{thumb_size}"
        if key in self._gallery_photo_textures:
            return self._gallery_photo_textures[key]
        self._queue_texture_load(
            kind="gallery",
            key=key,
            face=face,
            size=thumb_size,
        )
        return None

    def _square_crop_bounds(
        self,
        x: float,
        y: float,
        bw: float,
        bh: float,
        width: int,
        height: int,
        pad: float = 0.35,
    ) -> tuple[int, int, int, int]:
        """Return a square crop centered on the bbox, with padding, clamped to image bounds."""
        cx = x + (bw / 2.0)
        cy = y + (bh / 2.0)
        size = max(bw, bh) * (1.0 + 2.0 * pad)
        size = max(1.0, size)
        half = size / 2.0
        left = cx - half
        top = cy - half
        right = cx + half
        bottom = cy + half

        # Shift to stay within bounds.
        if left < 0:
            right -= left
            left = 0
        if top < 0:
            bottom -= top
            top = 0
        if right > width:
            left -= (right - width)
            right = width
        if bottom > height:
            top -= (bottom - height)
            bottom = height

        left = max(0, min(left, width))
        top = max(0, min(top, height))
        right = max(left + 1, min(right, width))
        bottom = max(top + 1, min(bottom, height))

        return int(left), int(top), int(right), int(bottom)

    def _prune_gallery_textures(self, limit: int = 300) -> None:
        if len(self._gallery_photo_textures) <= limit:
            return
        to_remove = list(self._gallery_photo_textures.items())[: len(self._gallery_photo_textures) - limit]
        for key, tex_tag in to_remove:
            try:
                if dpg.does_item_exist(tex_tag):
                    dpg.delete_item(tex_tag)
            except Exception:
                pass
            self._gallery_photo_textures.pop(key, None)

    def _compute_face_similarity(self, face: Face, cluster: FaceCluster) -> float | None:
        """Compute cosine similarity between face and cluster average embedding."""
        try:
            if not face.embedding or cluster.avg_embedding is None:
                return None
            face_emb = np.frombuffer(face.embedding, dtype=np.float32)
            cluster_emb = np.asarray(cluster.avg_embedding, dtype=np.float32)
            if face_emb.size == 0 or cluster_emb.size == 0:
                return None
            face_norm = np.linalg.norm(face_emb)
            cluster_norm = np.linalg.norm(cluster_emb)
            if face_norm == 0 or cluster_norm == 0:
                return None
            sim = float(np.dot(face_emb, cluster_emb) / (face_norm * cluster_norm))
            return sim
        except Exception:
            return None

    def _select_cluster_sample_faces(
        self,
        faces: list[Face],
        avg_embedding: np.ndarray | None,
        limit: int = 5,
    ) -> list[Face]:
        if not faces:
            return []
        scored = []
        avg_norm = 0.0
        avg_vec = None
        if avg_embedding is not None:
            avg_vec = np.asarray(avg_embedding, dtype=np.float32)
            avg_norm = np.linalg.norm(avg_vec)
        for face in faces:
            sim = -1.0
            if avg_vec is not None and avg_norm > 0 and face.embedding:
                emb = np.frombuffer(face.embedding, dtype=np.float32)
                emb_norm = np.linalg.norm(emb)
                if emb_norm > 0:
                    sim = float(np.dot(emb, avg_vec) / (emb_norm * avg_norm))
            conf = face.confidence or 0.0
            area = (face.bbox_w or 0) * (face.bbox_h or 0)
            scored.append((sim, conf, area, face))
        scored.sort(reverse=True, key=lambda s: (s[0], s[1], s[2]))
        return [s[3] for s in scored[:limit]]

    def _get_preview_texture_tag(self) -> str:
        if self._preview_texture_tag and dpg.does_item_exist(self._preview_texture_tag):
            return self._preview_texture_tag
        tex_tag = "face_preview_tex"
        if not dpg.does_item_exist(tex_tag):
            data = [0.0, 0.0, 0.0, 1.0]
            dpg.add_static_texture(1, 1, data, tag=tex_tag, parent=self.TAG_TEXTURE_REGISTRY)
        self._preview_texture_tag = tex_tag
        return tex_tag

    def _show_face_preview(self, face_id: int) -> None:
        """Open a preview dialog for a face's source image."""
        face = self.db.get_face(face_id)
        if not face:
            self._notify_status("Face not found for preview.", level="warning")
            return
        file_record = self.db.get_file(face.file_id)
        if not file_record or not file_record.path:
            self._notify_status("File not found for preview.", level="warning")
            return
        try:
            raw_image = Image.open(file_record.path)
            self._preview_orientation = int(raw_image.getexif().get(274, 1))
            self._preview_raw_size = raw_image.size
            image = ImageOps.exif_transpose(raw_image).convert("RGB")
            max_w, max_h = 880, 620
            width, height = image.size
            scale = min(max_w / max(width, 1), max_h / max(height, 1), 1.0)
            if scale < 1.0:
                image = image.resize((int(width * scale), int(height * scale)), Image.BILINEAR)
            self._preview_scale = scale
            self._preview_display_size = (image.width, image.height)
            rgba = image.convert("RGBA")
            data = np.asarray(rgba).astype(np.float32) / 255.0
            new_tex = f"face_preview_tex_{int(time.time() * 1000)}"
            dpg.add_static_texture(
                rgba.width,
                rgba.height,
                data.flatten().tolist(),
                tag=new_tex,
                parent=self.TAG_TEXTURE_REGISTRY,
            )
            if (
                self._preview_texture_tag
                and dpg.does_item_exist(self._preview_texture_tag)
                and self._preview_texture_tag.startswith("face_preview_tex_")
            ):
                with contextlib.suppress(Exception):
                    dpg.delete_item(self._preview_texture_tag)
            self._preview_texture_tag = new_tex
            self._preview_file_id = file_record.id
            self._preview_face_id = face.id
            self._preview_bbox = (face.bbox_x, face.bbox_y, face.bbox_w, face.bbox_h)
            dpg.set_value(self.TAG_FACE_PREVIEW_TEXT, file_record.path)
            self._render_face_preview()
            dpg.configure_item(self.TAG_FACE_PREVIEW_DIALOG, show=True)
            # Bring dialog to front
            with contextlib.suppress(Exception):
                dpg.focus_item(self.TAG_FACE_PREVIEW_DIALOG)
        except Exception:
            self._notify_status("Failed to open preview.", level="warning")

    def _exclude_preview_file(self) -> None:
        """Blacklist the preview file from face detection."""
        if not self._preview_file_id:
            return
        self.db.add_face_blacklist(self._preview_file_id, reason="user_excluded")
        self.db.delete_faces_for_file(self._preview_file_id)
        self._preview_file_id = None
        dpg.configure_item(self.TAG_FACE_PREVIEW_DIALOG, show=False)
        self._refresh()
        self._notify_status("Excluded file from face detection.", level="info")

    def _exclude_face(self, face_id: int) -> None:
        """Blacklist a file based on a face detection."""
        face = self.db.get_face(face_id)
        if not face:
            return
        self.db.add_face_blacklist(face.file_id, reason="user_excluded")
        self.db.delete_faces_for_file(face.file_id)
        self._refresh()
        self._notify_status("Excluded file from face detection.", level="info")

    def _show_split_dialog(self, cluster_id: int) -> None:
        """Open split dialog for a cluster."""
        cluster = next((c for c in self._face_clusters if c.cluster_id == cluster_id), None)
        if not cluster:
            self._notify_status("Cluster not found (refreshing).", level="warning")
            self._refresh()
            return
        if not self._cluster_run_id:
            self._notify_status("No cluster run available. Please re-cluster.", level="warning")
            return
        self._split_cluster_id = cluster_id
        self._split_face_ids = [fid for fid in cluster.face_ids if fid is not None]
        self._split_selected.clear()
        self._pause_auto_refresh = True
        self._stop_auto_refresh()
        self._render_split_faces()
        dpg.configure_item(self.TAG_SPLIT_DIALOG, show=True)

    def _render_split_faces(self) -> None:
        """Render faces for split selection in a grid layout."""
        if not dpg.does_item_exist(self.TAG_SPLIT_CONTAINER):
            return
        for child in dpg.get_item_children(self.TAG_SPLIT_CONTAINER, 1) or []:
            dpg.delete_item(child)
        faces = self.db.get_faces_by_ids(self._split_face_ids[:120])
        dpg.set_value(
            self.TAG_SPLIT_STATUS,
            f"Selected: {len(self._split_selected)} / {len(self._split_face_ids)}",
        )
        if not faces:
            dpg.add_text("No faces to show.", parent=self.TAG_SPLIT_CONTAINER)
            return

        # Grid layout: 10 faces per row, 72px thumbnails
        row_group = None
        for i, face in enumerate(faces):
            if i % 10 == 0:
                row_group = dpg.add_group(horizontal=True, parent=self.TAG_SPLIT_CONTAINER)

            is_selected = face.id in self._split_selected
            with dpg.group(horizontal=False, parent=row_group):
                # Selection indicator
                indicator = "[*]" if is_selected else "[ ]"
                indicator_color = (100, 255, 100) if is_selected else (140, 140, 140)
                dpg.add_text(indicator, color=indicator_color)

                tex_tag = self._get_face_texture(face)
                if tex_tag:
                    dpg.add_image_button(
                        tex_tag,
                        width=72,
                        height=72,
                        callback=lambda s, a, u: self._toggle_split_face(u),
                        user_data=face.id,
                    )
                else:
                    dpg.add_text("[img]", color=get_text_color("disabled"))

    def _toggle_split_face(self, face_id: int) -> None:
        if face_id in self._split_selected:
            self._split_selected.remove(face_id)
        else:
            self._split_selected.add(face_id)
        self._render_split_faces()

    def _on_split_assign(self) -> None:
        """Assign selected faces to existing person."""
        self._commit_split()
        self._show_assign_dialog_for_split()

    def _on_split_name(self) -> None:
        """Name selected faces as a new person."""
        self._commit_split()
        self._show_name_dialog_for_split()

    def _auto_refine_matches(self) -> None:
        """Try to auto-assign similar faces after manual labeling."""
        try:
            self.face_analyzer.match_and_assign_faces(
                threshold=self.config.ai.face_recognition_threshold,
                auto_assign=True,
            )
            self._pending_stats_refresh = True
            if self._current_view == "people":
                self._pending_people_refresh = True
        except Exception:
            pass

    def _commit_split(self) -> None:
        """Persist split selection into a new cluster."""
        if not self._cluster_run_id or not self._split_cluster_id:
            return
        if not self._split_selected:
            return
        new_cluster_id = self.db.move_faces_to_new_cluster(
            self._cluster_run_id,
            list(self._split_selected),
            self._split_cluster_id,
            method="manual",
        )
        if new_cluster_id:
            self._load_clusters_from_db()

    def _load_clusters_from_db(self, render: bool = True) -> None:
        """Load latest clusters from the database."""
        latest = self.db.get_latest_face_cluster_run()
        if not latest:
            return
        run_id, _method = latest
        self._cluster_run_id = run_id
        clusters = []
        total_count = 0
        filtered_count = 0

        for cluster_id, face_ids in self.db.get_face_clusters_for_run(run_id):
            faces = self.db.get_faces_by_ids(face_ids)
            if not faces:
                continue
            unassigned = [face for face in faces if face.person_id is None]
            if not unassigned:
                continue

            total_count += 1

            # Apply min photos filter if enabled
            if self.config.ai.filter_by_min_photos and len(unassigned) < self.config.ai.min_cluster_photos:
                filtered_count += 1
                continue

            embeddings = []
            for face in unassigned:
                if face.embedding:
                    embeddings.append(np.frombuffer(face.embedding, dtype=np.float32))
            avg_embedding = np.mean(embeddings, axis=0) if embeddings else None
            sample_faces = self._select_cluster_sample_faces(unassigned, avg_embedding, limit=5)
            clusters.append(
                FaceCluster(
                    cluster_id=cluster_id,
                    face_ids=[face.id for face in unassigned if face.id is not None],
                    sample_faces=sample_faces,
                    avg_embedding=avg_embedding,
                )
            )
        self._face_clusters = clusters
        self._total_clusters = total_count
        self._filtered_clusters = filtered_count
        self._clusters_loaded = True

        # Apply sorting
        self._sort_clusters()

        # Reset cluster loading limit to prioritize visible clusters at top
        self._max_clusters_to_load = 40
        if render and self._faces_tab_active:
            self._display_face_clusters()

    def _sort_clusters(self) -> None:
        """Sort clusters based on current sort mode."""
        if not self._face_clusters:
            return

        if self._cluster_sort_mode == "default":
            # Sort by cluster_id (default)
            self._face_clusters.sort(key=lambda c: c.cluster_id)

        elif self._cluster_sort_mode in ("closest", "furthest"):
            # Sort by similarity to known people
            try:
                # Load person embeddings
                self.face_analyzer.load_person_embeddings()
                person_embeddings = self.face_analyzer._person_embeddings

                if not person_embeddings:
                    # No known people, fall back to default sort
                    logger.info("No known people found, using default sort")
                    self._face_clusters.sort(key=lambda c: c.cluster_id)
                    return

                # Compute max similarity for each cluster to any known person
                cluster_similarities = []
                for _cluster_idx, cluster in enumerate(self._face_clusters):
                    if cluster.avg_embedding is None:
                        cluster_similarities.append((cluster, 0.0))
                        continue

                    try:
                        # Ensure cluster embedding is a proper numpy array
                        if isinstance(cluster.avg_embedding, (list, tuple)):
                            cluster_emb = np.array(cluster.avg_embedding, dtype=np.float32)
                        else:
                            cluster_emb = np.asarray(cluster.avg_embedding, dtype=np.float32)

                        if cluster_emb.ndim != 1:
                            cluster_emb = cluster_emb.flatten()

                        max_similarity = 0.0
                        for person_id, person_embs in person_embeddings.items():
                            for person_emb_tuple in person_embs:
                                try:
                                    # Person embeddings are stored as (age_stage, embedding) tuples
                                    if isinstance(person_emb_tuple, tuple) and len(person_emb_tuple) == 2:
                                        _, person_emb = person_emb_tuple  # Unpack (age_stage, embedding)
                                    else:
                                        person_emb = person_emb_tuple

                                    # Ensure person embedding is a proper numpy array
                                    if isinstance(person_emb, (list, tuple)):
                                        person_emb_arr = np.array(person_emb, dtype=np.float32)
                                    else:
                                        person_emb_arr = np.asarray(person_emb, dtype=np.float32)

                                    if person_emb_arr.ndim != 1:
                                        person_emb_arr = person_emb_arr.flatten()

                                    similarity = self.face_analyzer.compute_similarity(
                                        cluster_emb, person_emb_arr
                                    )
                                    max_similarity = max(max_similarity, similarity)
                                except Exception as e:
                                    logger.debug(f"Error comparing cluster {cluster.cluster_id} to person {person_id}: {e}")
                                    continue

                        cluster_similarities.append((cluster, max_similarity))
                    except Exception as e:
                        logger.debug(f"Error processing cluster {cluster.cluster_id} embedding: {e}")
                        cluster_similarities.append((cluster, 0.0))

                # Sort by similarity
                reverse = (self._cluster_sort_mode == "closest")
                cluster_similarities.sort(key=lambda x: x[1], reverse=reverse)
                self._face_clusters = [c for c, _ in cluster_similarities]
                logger.info(f"Successfully sorted {len(self._face_clusters)} clusters by similarity to known people")

            except Exception as e:
                logger.warning(f"Error sorting clusters by similarity to people: {e}")
                import traceback
                logger.debug(traceback.format_exc())
                self._face_clusters.sort(key=lambda c: c.cluster_id)

        elif self._cluster_sort_mode == "similar":
            # Sort by inter-cluster similarity (similar clusters together)
            try:
                # Filter clusters with embeddings
                clusters_with_emb = [c for c in self._face_clusters if c.avg_embedding is not None]
                clusters_without_emb = [c for c in self._face_clusters if c.avg_embedding is None]

                if not clusters_with_emb:
                    return

                # Compute pairwise similarity matrix
                n = len(clusters_with_emb)
                similarity_matrix = np.zeros((n, n))

                for i in range(n):
                    for j in range(i + 1, n):
                        # Ensure embeddings are proper numpy arrays
                        emb_i = np.asarray(clusters_with_emb[i].avg_embedding, dtype=np.float32)
                        emb_j = np.asarray(clusters_with_emb[j].avg_embedding, dtype=np.float32)
                        if emb_i.ndim != 1:
                            emb_i = emb_i.flatten()
                        if emb_j.ndim != 1:
                            emb_j = emb_j.flatten()

                        sim = self.face_analyzer.compute_similarity(emb_i, emb_j)
                        similarity_matrix[i, j] = sim
                        similarity_matrix[j, i] = sim

                # Use hierarchical clustering-like approach: start with random cluster,
                # always add the most similar unvisited cluster
                visited = [False] * n
                sorted_indices = []
                current = 0  # Start with first cluster
                sorted_indices.append(current)
                visited[current] = True

                while len(sorted_indices) < n:
                    # Find most similar unvisited cluster to current
                    max_sim = -1
                    next_idx = -1
                    for i in range(n):
                        if not visited[i] and similarity_matrix[current, i] > max_sim:
                            max_sim = similarity_matrix[current, i]
                            next_idx = i

                    if next_idx == -1:
                        # No more similar clusters, pick first unvisited
                        for i in range(n):
                            if not visited[i]:
                                next_idx = i
                                break

                    sorted_indices.append(next_idx)
                    visited[next_idx] = True
                    current = next_idx

                # Reorder clusters
                sorted_clusters = [clusters_with_emb[i] for i in sorted_indices]
                sorted_clusters.extend(clusters_without_emb)
                self._face_clusters = sorted_clusters

            except Exception as e:
                logger.warning(f"Error sorting clusters by similarity: {e}")
                self._face_clusters.sort(key=lambda c: c.cluster_id)

    def on_frame(self) -> None:
        """Process UI updates on the main thread."""
        # Process more textures when gallery/view-all dialogs are open (user is actively waiting)
        gallery_open = dpg.does_item_exist(self.TAG_PERSON_GALLERY_DIALOG) and dpg.is_item_shown(self.TAG_PERSON_GALLERY_DIALOG)
        all_faces_open = dpg.does_item_exist(self.TAG_ALL_FACES_DIALOG) and dpg.is_item_shown(self.TAG_ALL_FACES_DIALOG)
        rematch_dialog_open = dpg.does_item_exist(self.TAG_REMATCH_DIALOG) and dpg.is_item_shown(self.TAG_REMATCH_DIALOG)
        max_textures = 128 if (gallery_open or all_faces_open or rematch_dialog_open) else 64
        self._process_texture_results(max_per_frame=max_textures)

        if self._pending_cluster_refresh:
            self._pending_cluster_refresh = False
            self._load_clusters_from_db()

        if self._pending_stats_refresh:
            self._pending_stats_refresh = False
            self._update_stats()

        if self._pending_cluster_done:
            self._pending_cluster_done = False
            if dpg.does_item_exist(self.TAG_FACE_ANALYSIS_STATUS):
                dpg.set_value(self.TAG_FACE_ANALYSIS_STATUS, "")
            if not self._background_face_analysis and not self._is_analyzing:
                self._set_analysis_buttons_enabled(True)

        if self._pending_rematch_results is not None:
            auto_count, suggestions = self._pending_rematch_results
            self._pending_rematch_results = None
            self._show_rematch_results(auto_count, suggestions)

        if self._pending_people_refresh:
            self._pending_people_refresh = False
            if self._current_view == "people":
                self._refresh_people_list()

        if self._pending_auto_cluster and not self._is_clustering:
            self._pending_auto_cluster = False
            self._on_cluster_faces()

        # Refresh "View All" dialog when textures are loaded
        if self._all_faces_needs_refresh and all_faces_open:
            self._all_faces_needs_refresh = False
            self._refresh_all_faces_dialog()

        # Check if scroll position changed (for virtual scrolling)
        if self._faces_tab_active and self._current_view == "clusters" and dpg.does_item_exist(self.TAG_CLUSTER_VIEW):
            try:
                current_scroll_y = dpg.get_y_scroll(self.TAG_CLUSTER_VIEW)
                # If scrolled more than 100 pixels, refresh to show new clusters
                if abs(current_scroll_y - self._last_scroll_y) > 100:
                    self._last_scroll_y = current_scroll_y
                    self._display_face_clusters()
            except Exception:
                pass

        if self._pending_face_ui_refresh and self._faces_tab_active:
            current_time = time.time()
            # Only refresh clusters at most every 0.2 seconds to batch texture loads
            if current_time - self._last_cluster_refresh_time >= 0.2:
                self._pending_face_ui_refresh = False
                self._last_cluster_refresh_time = current_time
                # Only refresh clusters if we're viewing the clusters screen
                if self._current_view == "clusters":
                    logger.info("Refreshing face clusters UI to show new textures")
                    self._display_face_clusters()
        elif self._pending_face_ui_refresh and not self._faces_tab_active:
            logger.info(f"UI refresh pending but Faces tab not active (active={self._faces_tab_active})")

        # Batch refresh gallery when textures load (at most once per second)
        if self._gallery_needs_refresh and gallery_open:
            current_time = time.time()
            if current_time - self._last_gallery_refresh_time >= 1.0:
                self._gallery_needs_refresh = False
                self._last_gallery_refresh_time = current_time
                logger.info("Batched gallery refresh to show newly loaded thumbnails")
                self._render_person_gallery()

        # Gallery refresh is separate - only refresh when gallery textures load
        if self._pending_gallery_refresh and self._faces_tab_active:
            self._pending_gallery_refresh = False
            if dpg.does_item_exist(self.TAG_PERSON_GALLERY_DIALOG) and dpg.is_item_shown(self.TAG_PERSON_GALLERY_DIALOG):
                # logger.info("Refreshing person gallery to show new gallery textures")
                self._render_person_gallery()

        # Batch refresh intermediate suggestions when thumbnails load (at most once per second)
        intermediate_open = dpg.does_item_exist(self.TAG_INTERMEDIATE_CLUSTERS_DIALOG) and dpg.is_item_shown(self.TAG_INTERMEDIATE_CLUSTERS_DIALOG)
        if self._intermediate_needs_refresh and intermediate_open:
            current_time = time.time()
            if current_time - self._last_intermediate_refresh_time >= 1.0:
                self._intermediate_needs_refresh = False
                self._last_intermediate_refresh_time = current_time
                logger.info("Batched intermediate suggestions refresh to show newly loaded thumbnails")
                self._render_intermediate_clusters()

        # Batch refresh rematch suggestions when thumbnails load (at most once per second)
        rematch_open = dpg.does_item_exist(self.TAG_REMATCH_DIALOG) and dpg.is_item_shown(self.TAG_REMATCH_DIALOG)
        if self._rematch_needs_refresh and rematch_open and self._rematch_suggestions:
            current_time = time.time()
            if current_time - self._last_rematch_refresh_time >= 1.0:
                self._rematch_needs_refresh = False
                self._last_rematch_refresh_time = current_time
                self._render_rematch_suggestions()

    def _cancel_split_dialog(self) -> None:
        """Cancel split dialog."""
        dpg.configure_item(self.TAG_SPLIT_DIALOG, show=False)
        self._split_selected.clear()
        self._resume_auto_refresh()

    def _split_select_all(self) -> None:
        """Select all faces in split dialog."""
        self._split_selected = set(self._split_face_ids)
        self._render_split_faces()

    def _split_deselect_all(self) -> None:
        """Deselect all faces in split dialog."""
        self._split_selected.clear()
        self._render_split_faces()

    # =========================================================================
    # Person Edit/Delete Methods
    # =========================================================================

    def _show_edit_person_dialog(self, person_id: int) -> None:
        """Show dialog to edit a person's details."""
        person = self.db.get_person(person_id)
        if not person:
            return

        self._edit_person_id = person_id
        dpg.set_value("edit_person_name", person.name or "")
        dpg.set_value("edit_person_birth_year", person.birth_year or 0)
        dpg.configure_item(self.TAG_EDIT_PERSON_DIALOG, show=True)

    def _save_person_edit(self) -> None:
        """Save changes to the person being edited."""
        if self._edit_person_id is None:
            return

        name = dpg.get_value("edit_person_name").strip()
        birth_year = dpg.get_value("edit_person_birth_year")

        if not name:
            self._notify_status("Name cannot be empty.", level="warning")
            return

        person = self.db.get_person(self._edit_person_id)
        if person:
            person.name = name
            person.birth_year = birth_year if birth_year > 0 else None
            self.db.update_person(person)
            self._notify_status(f"Updated person: {name}", level="info")

        dpg.configure_item(self.TAG_EDIT_PERSON_DIALOG, show=False)
        self._edit_person_id = None
        self._refresh_people_list()

    def _show_delete_person_dialog(self, person_id: int) -> None:
        """Show confirmation dialog before deleting a person."""
        person = self.db.get_person(person_id)
        if not person:
            return

        self._delete_person_id = person_id
        face_count = self.db.get_face_count(person_id=person_id)
        dpg.set_value("delete_person_info", f'"{person.name}" has {face_count} faces.')
        dpg.configure_item(self.TAG_DELETE_PERSON_DIALOG, show=True)

    def _confirm_delete_person(self) -> None:
        """Delete the person after confirmation."""
        if self._delete_person_id is None:
            return

        person = self.db.get_person(self._delete_person_id)
        name = person.name if person else "Unknown"

        faces_unassigned = self.db.delete_person(self._delete_person_id)

        dpg.configure_item(self.TAG_DELETE_PERSON_DIALOG, show=False)
        self._delete_person_id = None

        self._notify_status(f"Deleted {name}. {faces_unassigned} faces returned to clusters.", level="info")
        self._refresh_people_list()
        self._refresh()

    # =========================================================================
    # Relationships & Family Groups
    # =========================================================================

    def _show_add_relationship_dialog(self, person_id: int) -> None:
        """Show dialog to add a relationship for a person."""
        self._relationship_person_id = person_id
        person = self.db.get_person(person_id)
        if not person:
            return

        # Populate person combo with all named persons except this one
        all_persons = self.db.get_all_persons(named_only=True)
        names = [p.name for p in all_persons if p.id != person_id and p.name]
        dpg.configure_item(self.TAG_RELATIONSHIP_PERSON_COMBO, items=names)
        if names:
            dpg.set_value(self.TAG_RELATIONSHIP_PERSON_COMBO, names[0])
        dpg.set_value(self.TAG_RELATIONSHIP_TYPE_COMBO, "sibling")
        dpg.configure_item(
            self.TAG_RELATIONSHIP_DIALOG,
            label=f"Add Relationship for {person.name}",
            show=True,
        )

    def _save_relationship(self) -> None:
        """Save the relationship from the dialog."""
        if self._relationship_person_id is None:
            return

        selected_name = dpg.get_value(self.TAG_RELATIONSHIP_PERSON_COMBO)
        rel_type = dpg.get_value(self.TAG_RELATIONSHIP_TYPE_COMBO)

        if not selected_name or not rel_type:
            self._notify_status("Select a person and relationship type.", level="warning")
            return

        # Find the person by name
        all_persons = self.db.get_all_persons(named_only=True)
        other = next((p for p in all_persons if p.name == selected_name), None)
        if not other or other.id is None:
            self._notify_status(f"Person '{selected_name}' not found.", level="warning")
            return

        from duplicleaner.db.models import PersonRelationship

        rel = PersonRelationship(
            person_a_id=self._relationship_person_id,
            person_b_id=other.id,
            relationship_type=rel_type,
            confidence="confirmed",
        )
        try:
            self.db.add_relationship(rel)
            self._notify_status(
                f"Added {rel_type} relationship with {selected_name}.", level="info"
            )
        except Exception as e:
            self._notify_status(f"Failed to add relationship: {e}", level="error")

        dpg.configure_item(self.TAG_RELATIONSHIP_DIALOG, show=False)
        self._relationship_person_id = None
        self._refresh_people_list()

    def _show_suggest_relationships_dialog(self, person_id: int) -> None:
        """Show co-occurrence based relationship suggestions."""
        person = self.db.get_person(person_id)
        if not person:
            return

        suggestions = self.db.suggest_relationships(person_id)

        # Clear container
        if dpg.does_item_exist(self.TAG_COOCCURRENCE_CONTAINER):
            for child in dpg.get_item_children(self.TAG_COOCCURRENCE_CONTAINER, 1):
                dpg.delete_item(child)

        if not suggestions:
            dpg.add_text(
                "No relationship suggestions found. Need more photos with multiple people.",
                parent=self.TAG_COOCCURRENCE_CONTAINER,
                color=get_text_color("secondary"),
            )
        else:
            for s in suggestions:
                with dpg.group(parent=self.TAG_COOCCURRENCE_CONTAINER):
                    with dpg.group(horizontal=True):
                        dpg.add_text(
                            f"{s['name']} - {s['shared_photos']} shared photos",
                            color=get_accent_color(),
                        )
                        dpg.add_text(f"  [{s['suggested_type']}]")
                    dpg.add_text(f"  {s['reason']}", color=get_text_color("secondary"))
                    with dpg.group(horizontal=True):
                        dpg.add_button(
                            label=f"Add as {s['suggested_type']}",
                            callback=self._accept_relationship_suggestion,
                            user_data=(person_id, s["person_id"], s["suggested_type"]),
                            small=True,
                        )
                        dpg.add_button(
                            label="Skip",
                            small=True,
                        )
                    dpg.add_separator()

        dpg.configure_item(
            self.TAG_COOCCURRENCE_DIALOG,
            label=f"Suggest Relationships for {person.name}",
            show=True,
        )

    def _accept_relationship_suggestion(self, sender, app_data, user_data) -> None:
        """Accept a suggested relationship."""
        person_a_id, person_b_id, rel_type = user_data
        from duplicleaner.db.models import PersonRelationship

        rel = PersonRelationship(
            person_a_id=person_a_id,
            person_b_id=person_b_id,
            relationship_type=rel_type,
            confidence="confirmed",
        )
        try:
            self.db.add_relationship(rel)
            other = self.db.get_person(person_b_id)
            name = other.name if other else "Unknown"
            self._notify_status(f"Added {rel_type} relationship with {name}.", level="info")
        except Exception as e:
            self._notify_status(f"Relationship already exists or error: {e}", level="warning")

        # Refresh the suggestions dialog
        self._show_suggest_relationships_dialog(person_a_id)

    def _show_create_family_group_dialog(self, sender=None, app_data=None) -> None:
        """Show dialog to create a new family group."""
        dpg.set_value(self.TAG_FAMILY_GROUP_NAME_INPUT, "")
        dpg.configure_item(self.TAG_FAMILY_GROUP_DIALOG, show=True)

    def _save_family_group(self) -> None:
        """Save a new family group."""
        name = dpg.get_value(self.TAG_FAMILY_GROUP_NAME_INPUT).strip()
        if not name:
            self._notify_status("Family group name cannot be empty.", level="warning")
            return

        from duplicleaner.db.models import FamilyGroup

        group = FamilyGroup(name=name)
        group_id = self.db.add_family_group(group)
        self._notify_status(f"Created family group: {name}", level="info")
        dpg.configure_item(self.TAG_FAMILY_GROUP_DIALOG, show=False)
        self._refresh_family_groups()

    def _show_add_family_member_dialog(self, group_id: int) -> None:
        """Show dialog to add a member to a family group."""
        self._add_member_group_id = group_id
        group = self.db.get_family_group(group_id)
        if not group:
            return

        # Get existing member IDs to exclude
        existing = self.db.get_family_group_members(group_id)
        existing_ids = {m["person_id"] for m in existing}

        all_persons = self.db.get_all_persons(named_only=True)
        names = [p.name for p in all_persons if p.id not in existing_ids and p.name]
        dpg.configure_item(self.TAG_FAMILY_MEMBER_COMBO, items=names)
        if names:
            dpg.set_value(self.TAG_FAMILY_MEMBER_COMBO, names[0])
        dpg.set_value(self.TAG_FAMILY_MEMBER_ROLE_INPUT, "")
        dpg.configure_item(
            self.TAG_FAMILY_MEMBER_DIALOG,
            label=f"Add Member to {group.name}",
            show=True,
        )

    def _save_family_member(self) -> None:
        """Save a new family group member."""
        if self._add_member_group_id is None:
            return

        selected_name = dpg.get_value(self.TAG_FAMILY_MEMBER_COMBO)
        role = dpg.get_value(self.TAG_FAMILY_MEMBER_ROLE_INPUT).strip() or None

        if not selected_name:
            self._notify_status("Select a person to add.", level="warning")
            return

        all_persons = self.db.get_all_persons(named_only=True)
        person = next((p for p in all_persons if p.name == selected_name), None)
        if not person or person.id is None:
            self._notify_status(f"Person '{selected_name}' not found.", level="warning")
            return

        self.db.add_family_group_member(self._add_member_group_id, person.id, role)
        self._notify_status(f"Added {selected_name} to family group.", level="info")
        dpg.configure_item(self.TAG_FAMILY_MEMBER_DIALOG, show=False)
        self._add_member_group_id = None
        self._refresh_family_groups()

    def _remove_family_member(self, sender, app_data, user_data) -> None:
        """Remove a member from a family group."""
        group_id, person_id = user_data
        self.db.remove_family_group_member(group_id, person_id)
        self._notify_status("Removed member from family group.", level="info")
        self._refresh_family_groups()

    def _delete_family_group(self, sender, app_data, user_data) -> None:
        """Delete a family group."""
        group_id = user_data
        group = self.db.get_family_group(group_id)
        name = group.name if group else "Unknown"
        self.db.delete_family_group(group_id)
        self._notify_status(f"Deleted family group: {name}", level="info")
        self._refresh_family_groups()

    def _delete_relationship_by_id(self, sender, app_data, user_data) -> None:
        """Delete a relationship."""
        rel_id, person_id = user_data
        self.db.delete_relationship(rel_id)
        self._notify_status("Removed relationship.", level="info")
        self._refresh_people_list()

    def _refresh_family_groups(self) -> None:
        """Refresh the family groups section."""
        # Clean up old handler registries
        for reg in self._family_handler_registries:
            try:
                if dpg.does_item_exist(reg):
                    dpg.delete_item(reg)
            except Exception:
                pass
        self._family_handler_registries.clear()

        if not dpg.does_item_exist(self.TAG_FAMILY_VIEW_CONTAINER):
            return

        # Clear container
        for child in dpg.get_item_children(self.TAG_FAMILY_VIEW_CONTAINER, 1):
            dpg.delete_item(child)

        groups = self.db.get_all_family_groups()
        if not groups:
            dpg.add_text(
                "No family groups yet. Click 'Create Family Group' to start.",
                parent=self.TAG_FAMILY_VIEW_CONTAINER,
                color=get_text_color("secondary"),
            )
            return

        for group in groups:
            members = self.db.get_family_group_members(group.id)
            with dpg.collapsing_header(
                label=f"{group.name} ({len(members)} members)",
                parent=self.TAG_FAMILY_VIEW_CONTAINER,
                default_open=True,
            ):
                for m in members:
                    with dpg.group(horizontal=True):
                        role_text = f" ({m['role']})" if m.get("role") else ""
                        photos_text = f" - {m['photo_count']} photos" if m.get("photo_count") else ""
                        dpg.add_text(f"  {m['name']}{role_text}{photos_text}")
                        dpg.add_button(
                            label="X",
                            callback=self._remove_family_member,
                            user_data=(group.id, m["person_id"]),
                            small=True,
                        )

                with dpg.group(horizontal=True):
                    dpg.add_button(
                        label="Add Member",
                        callback=lambda s, a, u: self._show_add_family_member_dialog(u),
                        user_data=group.id,
                        small=True,
                    )
                    dpg.add_button(
                        label="Delete Group",
                        callback=self._delete_family_group,
                        user_data=group.id,
                        small=True,
                    )

    # =========================================================================
    # Ignore/Hidden Person Methods
    # =========================================================================

    def _ignore_cluster(self, cluster_id: int, face_ids: list[int]) -> None:
        """Create a hidden person from a cluster (ignore unknown faces)."""
        if not face_ids:
            return

        person_id = self.db.create_hidden_person_from_cluster(face_ids)
        person = self.db.get_person(person_id)
        name = person.name if person else f"Unknown #{person_id}"

        # Remove cluster from in-memory list immediately
        cluster = next((c for c in self._face_clusters if c.cluster_id == cluster_id), None)
        if cluster and cluster in self._face_clusters:
            self._face_clusters.remove(cluster)

        self._notify_status(f"Ignored cluster as '{name}'.", level="info")
        self._display_face_clusters()
        self._pending_stats_refresh = True

    def _on_show_hidden_change(self, sender, app_data, user_data) -> None:
        """Toggle visibility of hidden people."""
        self._show_hidden_people = app_data
        self._refresh_people_list()

    def _on_min_photos_filter_toggle(self, sender, app_data, user_data) -> None:
        """Toggle min photos filter on/off."""
        self.config.ai.filter_by_min_photos = app_data
        save_config(self.config)

        # Enable/disable the input field
        if dpg.does_item_exist(self.TAG_MIN_PHOTOS_INPUT):
            dpg.configure_item(self.TAG_MIN_PHOTOS_INPUT, enabled=app_data)

        # Reload clusters with new filter
        self._pending_cluster_refresh = True
        self._refresh()

    def _on_min_photos_change(self, sender, app_data, user_data) -> None:
        """Update min photos threshold."""
        if app_data >= 1:
            self.config.ai.min_cluster_photos = app_data
            save_config(self.config)

            # Reload clusters with new filter
            if self.config.ai.filter_by_min_photos:
                self._pending_cluster_refresh = True
                self._refresh()

    def _on_cluster_sort_change(self, sender, app_data, user_data) -> None:
        """Handle cluster sort mode change."""
        sort_map = {
            "Cluster ID (default)": "default",
            "Closest to Known People First": "closest",
            "Furthest from Known People First": "furthest",
            "Similar Clusters Together": "similar",
        }
        self._cluster_sort_mode = sort_map.get(app_data, "default")
        logger.info(f"Cluster sort mode changed to: {self._cluster_sort_mode}")

        # Re-sort and display clusters
        if self._face_clusters:
            logger.info(f"Sorting {len(self._face_clusters)} clusters...")
            self._sort_clusters()
            logger.info("Sort complete, refreshing display")

            # Reset scroll position to top so user can see the newly sorted order
            if dpg.does_item_exist(self.TAG_CLUSTER_VIEW):
                try:
                    dpg.set_y_scroll(self.TAG_CLUSTER_VIEW, 0)
                    self._last_scroll_y = 0
                except Exception:
                    pass

            # Always refresh display when sort changes (user is actively interacting)
            if self._current_view == "clusters":
                self._display_face_clusters()
            else:
                logger.warning(f"Not in clusters view (current view: {self._current_view})")
        else:
            logger.warning("No clusters to sort")

    def _restore_hidden_person(self, person_id: int) -> None:
        """Unhide a hidden person."""
        self.db.set_person_hidden(person_id, False)
        self._notify_status("Person restored and will appear in People list.", level="info")
        self._refresh_people_list()

    def _delete_hidden_person(self, person_id: int) -> None:
        """Permanently delete a hidden person."""
        self._show_delete_person_dialog(person_id)

    # =========================================================================
    # People Search Methods
    # =========================================================================

    def _on_people_search_change(self, sender, app_data, user_data) -> None:
        """Filter people list by search term."""
        self._people_search_filter = app_data.lower().strip()
        self._refresh_people_list()

    def _clear_people_search(self) -> None:
        """Clear the people search filter."""
        self._people_search_filter = ""
        if dpg.does_item_exist(self.TAG_PEOPLE_SEARCH):
            dpg.set_value(self.TAG_PEOPLE_SEARCH, "")
        self._refresh_people_list()

    # =========================================================================
    # Person Photo Gallery Methods
    # =========================================================================

    def _show_person_gallery(self, person_id: int) -> None:
        """Show photo gallery for a person."""
        self._gallery_person_id = person_id
        person = self.db.get_person(person_id)
        if not person:
            self._notify_status("Person not found.", level="warning")
            return

        # Set title and info
        dpg.set_value(self.TAG_PERSON_GALLERY_TITLE, f"Photos of {person.name}")

        # Get all faces for this person
        faces = self.db.get_faces_for_person(person_id, limit=500)
        self._gallery_faces = faces

        # Load person embeddings once for similarity calculations
        self._gallery_person_embeddings = self._get_person_embedding_vectors(person_id)
        self._gallery_similarity_cache.clear()

        # Build info text
        photo_count = len(faces)
        if person.birth_year:
            age = person.estimated_age or 0
            info = f"{photo_count} photos | Age ~{age} | Born ~{person.birth_year}"
        else:
            info = f"{photo_count} photos"
        dpg.set_value(self.TAG_PERSON_GALLERY_INFO, info)

        # Reset sort to default and clear selections/removals
        dpg.set_value(self.TAG_PERSON_GALLERY_SORT, "Date (Newest)")
        self._gallery_sort = "date_desc"
        self._gallery_selected_faces.clear()
        self._gallery_removed_faces.clear()

        # Render the gallery
        self._render_person_gallery()

        dpg.configure_item(self.TAG_PERSON_GALLERY_DIALOG, show=True)

    def _show_pet_gallery(self, pet_id: int) -> None:
        """Show photo gallery for a pet using the timeline dialog."""
        pet = self.db.get_pet(pet_id)
        if not pet:
            self._notify_status("Pet not found.", level="warning")
            return

        # Use the timeline dialog to show pet photos organized by year
        self._show_pet_timeline(pet_id)

    def _render_person_gallery(self) -> None:
        """Render the photo grid in the gallery dialog."""
        # logger.info(f"_render_person_gallery called, gallery_textures available: {len(self._gallery_photo_textures)}")
        if not dpg.does_item_exist(self.TAG_PERSON_GALLERY_CONTAINER):
            logger.warning("Gallery container does not exist, skipping render")
            return

        # Verify container is actually valid
        try:
            dpg.get_item_type(self.TAG_PERSON_GALLERY_CONTAINER)
        except Exception as e:
            logger.error(f"Gallery container is invalid: {e}")
            return

        # Clean up gallery handler registries before re-rendering
        for reg in self._gallery_card_handler_registries:
            try:
                if dpg.does_item_exist(reg):
                    dpg.delete_item(reg)
            except Exception:
                pass
        self._gallery_card_handler_registries.clear()

        # Clear existing content (safely handle items that may not exist)
        children = dpg.get_item_children(self.TAG_PERSON_GALLERY_CONTAINER, 1)
        if children:
            for child in children:
                try:
                    if dpg.does_item_exist(child):
                        dpg.delete_item(child)
                except Exception as e:
                    logger.warning(f"Failed to delete child item {child}: {e}")

        if not self._gallery_faces:
            dpg.add_text(
                "No photos found for this person.",
                parent=self.TAG_PERSON_GALLERY_CONTAINER,
                color=get_text_color("disabled")
            )
            return

        # Sort faces based on current sort setting
        sorted_faces = self._sort_gallery_faces(self._gallery_faces)

        # Render grid - 6 photos per row at 120px each
        row_group = None
        photos_per_row = 6

        for i, face in enumerate(sorted_faces):
            if i % photos_per_row == 0:
                try:
                    row_group = dpg.add_group(
                        horizontal=True,
                        parent=self.TAG_PERSON_GALLERY_CONTAINER
                    )
                    dpg.add_spacer(width=5, parent=row_group)
                except Exception as e:
                    logger.error(f"Failed to create row group: {e}")
                    continue

            # Skip if row_group is invalid
            if not row_group or not dpg.does_item_exist(row_group):
                logger.warning(f"Invalid row_group, skipping face {face.id}")
                continue

            try:
                self._render_gallery_photo_card(face, row_group)
            except Exception as e:
                logger.error(f"Failed to render photo card for face {face.id}: {e}")

    def _sort_gallery_faces(self, faces: list) -> list:
        """Sort faces based on current sort setting."""
        if self._gallery_sort == "date_desc":
            return sorted(
                faces,
                key=lambda f: self._get_face_photo_date(f) or "",
                reverse=True
            )
        elif self._gallery_sort == "date_asc":
            return sorted(
                faces,
                key=lambda f: self._get_face_photo_date(f) or ""
            )
        elif self._gallery_sort == "name":
            return sorted(
                faces,
                key=lambda f: self._get_face_filename(f).lower()
            )
        elif self._gallery_sort == "similarity_desc":
            # Best matches first
            return sorted(
                faces,
                key=lambda f: self._get_face_similarity_to_person(f),
                reverse=True
            )
        elif self._gallery_sort == "similarity_asc":
            # Worst matches first (easier to spot mismatches)
            return sorted(
                faces,
                key=lambda f: self._get_face_similarity_to_person(f)
            )
        return faces

    def _get_face_photo_date(self, face: Face) -> str | None:
        """Get the photo date for a face."""
        if face.file_id:
            file_record = self.db.get_file(face.file_id)
            if file_record and file_record.modified:
                return file_record.modified.isoformat()
        return None

    def _get_face_filename(self, face: Face) -> str:
        """Get the filename for a face's photo."""
        if face.file_id:
            file_record = self.db.get_file(face.file_id)
            if file_record:
                return file_record.filename or ""
        return ""

    def _get_face_similarity_to_person(self, face: Face) -> float:
        """Calculate similarity of a face to its assigned person (cached)."""
        # Check cache first
        if face.id in self._gallery_similarity_cache:
            return self._gallery_similarity_cache[face.id]

        if not face.embedding or not self._gallery_person_embeddings:
            return 0.0

        # Convert face embedding
        face_emb = np.frombuffer(face.embedding, dtype=np.float32)

        # Calculate cosine similarity to each person embedding
        similarities = []
        for person_emb in self._gallery_person_embeddings:
            sim = np.dot(face_emb, person_emb) / (np.linalg.norm(face_emb) * np.linalg.norm(person_emb))
            similarities.append(float(sim))

        # Calculate average similarity
        result = sum(similarities) / len(similarities) if similarities else 0.0

        # Cache the result
        if face.id:
            self._gallery_similarity_cache[face.id] = result

        return result

    def _render_gallery_photo_card(self, face: Face, parent) -> None:
        """Render a single photo card in the gallery."""
        # Get file info
        file_record = self.db.get_file(face.file_id) if face.file_id else None
        if not file_record:
            logger.warning(f"No file record found for face {face.id}")
            return

        logger.debug(f"Rendering gallery card for face {face.id}, file {file_record.filename}")

        # Create card container with a tag so we can update it in-place
        card_tag = f"gallery_card_{face.id}" if face.id else None
        with dpg.group(parent=parent, tag=card_tag):
            # Check if this face has been removed
            is_removed = face.id in self._gallery_removed_faces if face.id else False
            logger.debug(f"Face {face.id} is_removed={is_removed}")

            if is_removed:
                # Show "Removed" placeholder instead of image
                with dpg.group():
                    dpg.add_text(
                        "REMOVED",
                        color=get_status_color("error")
                    )
                    dpg.add_spacer(height=self.GALLERY_THUMB_SIZE - 40)
            else:
                # Checkbox for selection
                is_selected = face.id in self._gallery_selected_faces if face.id else False
                dpg.add_checkbox(
                    default_value=is_selected,
                    user_data=face.id,
                    callback=lambda s, a, u: self._on_gallery_photo_select(u, a),
                )

                # Try to get thumbnail
                thumb = self._get_face_thumbnail(face)
                if thumb:
                    img_btn = dpg.add_image_button(
                        thumb,
                        width=self.GALLERY_THUMB_SIZE,
                        height=self.GALLERY_THUMB_SIZE,
                        user_data=(face.id, face.file_id),
                        callback=lambda s, a, u: self._on_gallery_photo_click(u),
                    )
                    with dpg.item_handler_registry() as gallery_hr:
                        dpg.add_item_clicked_handler(
                            button=dpg.mvMouseButton_Right,
                            callback=self._show_gallery_context_menu,
                            user_data=(face.id, face.file_id),
                        )
                    dpg.bind_item_handler_registry(img_btn, gallery_hr)
                    self._gallery_card_handler_registries.append(gallery_hr)
                else:
                    # Fallback button without image
                    fallback_btn = dpg.add_button(
                        label="[Photo]",
                        width=self.GALLERY_THUMB_SIZE,
                        height=self.GALLERY_THUMB_SIZE,
                        user_data=(face.id, face.file_id),
                        callback=lambda s, a, u: self._on_gallery_photo_click(u),
                    )
                    with dpg.item_handler_registry() as gallery_hr:
                        dpg.add_item_clicked_handler(
                            button=dpg.mvMouseButton_Right,
                            callback=self._show_gallery_context_menu,
                            user_data=(face.id, face.file_id),
                        )
                    dpg.bind_item_handler_registry(fallback_btn, gallery_hr)
                    self._gallery_card_handler_registries.append(gallery_hr)

            if not is_removed:
                # Filename label (truncated)
                filename = file_record.filename or "Unknown"
                display_name = filename[:12] + "..." if len(filename) > 12 else filename
                dpg.add_text(display_name, color=get_text_color("secondary"))

                # Similarity score (only show when sorting by similarity)
                if self._gallery_sort in ("similarity_desc", "similarity_asc"):
                    similarity = self._get_face_similarity_to_person(face)
                    sim_color = get_status_color("success") if similarity > 0.6 else get_status_color("warning") if similarity > 0.4 else get_status_color("error")
                    dpg.add_text(f"Match: {similarity:.0%}", color=sim_color)

                # Date label
                if file_record.modified:
                    date_str = file_record.modified.strftime("%Y-%m-%d")
                    dpg.add_text(date_str, color=get_text_color("disabled"))

                # Actions
                with dpg.group(horizontal=True):
                    dpg.add_button(
                        label="Open",
                        small=True,
                        user_data=file_record.id,
                        callback=lambda s, a, u: self._open_file_by_id(u),
                    )
                    dpg.add_button(
                        label="Unassign",
                        small=True,
                        user_data=face.id,
                        callback=lambda s, a, u: self._unassign_person_photo(u),
                    )
                    logger.debug(f"Created Open and Unassign buttons for face {face.id}, file {file_record.id}")
            else:
                # For removed photos, just show "Will appear in Unknown Clusters"
                dpg.add_text("Will appear in", color=get_text_color("disabled"))
                dpg.add_text("Unknown Clusters", color=get_text_color("disabled"))

            dpg.add_spacer(height=8)

    def _on_gallery_photo_click(self, payload) -> None:
        """Handle click on a photo in the gallery."""
        logger.info(f"_on_gallery_photo_click called with payload: {payload}")

        face_id = None
        file_id = None
        if isinstance(payload, tuple) and len(payload) >= 2:
            face_id, file_id = payload[0], payload[1]
            logger.info(f"Extracted from tuple: face_id={face_id}, file_id={file_id}")
        else:
            face_id = payload
            logger.info(f"Using payload directly as face_id: {face_id}")

        if face_id is None and file_id and self._gallery_person_id:
            logger.info(f"Looking up face for file_id={file_id}, person_id={self._gallery_person_id}")
            faces = self.db.get_faces_for_file(file_id)
            match = next((f for f in faces if f.person_id == self._gallery_person_id), None)
            if match:
                face_id = match.id
                logger.info(f"Found matching face: {face_id}")

        if face_id is None:
            logger.warning(f"Gallery click has no face_id (file_id={file_id})")
            self._notify_status("No face record found for this photo.", level="warning")
            return

        logger.info(f"Calling _show_photo_preview with face_id={face_id}")
        self._show_photo_preview(face_id)

    def _unassign_person_photo(self, face_id: int | None) -> None:
        logger.info(f"_unassign_person_photo called with face_id={face_id}")

        if not face_id:
            self._notify_status("No face record found for this photo.", level="warning")
            return

        # Unassign in database
        self.db.unassign_face_from_person(face_id)

        # Mark as removed for visual feedback (don't remove from list to avoid layout shift)
        self._gallery_removed_faces.add(face_id)

        # Also unselect it if it was selected
        self._gallery_selected_faces.discard(face_id)

        # Update photo count display
        if self._gallery_person_id:
            person = self.db.get_person(self._gallery_person_id)
            if person:
                # Count only non-removed photos
                photo_count = len([f for f in self._gallery_faces if f.id not in self._gallery_removed_faces])
                if person.birth_year:
                    age = person.estimated_age or 0
                    info = f"{photo_count} photos | Age ~{age} | Born ~{person.birth_year}"
                else:
                    info = f"{photo_count} photos"
                if dpg.does_item_exist(self.TAG_PERSON_GALLERY_INFO):
                    dpg.set_value(self.TAG_PERSON_GALLERY_INFO, info)

            # Update person photo count in database
            self.db.update_person_photo_count(self._gallery_person_id)

        # Update just the card in-place instead of re-rendering entire gallery
        card_tag = f"gallery_card_{face_id}"
        if dpg.does_item_exist(card_tag):
            for child in dpg.get_item_children(card_tag, 1) or []:
                dpg.delete_item(child)
            dpg.add_text("REMOVED", parent=card_tag, color=get_status_color("error"))
            dpg.add_spacer(height=self.GALLERY_THUMB_SIZE - 40, parent=card_tag)
            dpg.add_text("Will appear in", parent=card_tag, color=get_text_color("disabled"))
            dpg.add_text("Unknown Clusters", parent=card_tag, color=get_text_color("disabled"))
            dpg.add_spacer(height=8, parent=card_tag)
        self._notify_status("Photo unassigned from person.", level="info")

    def _on_gallery_sort_change(self, sender, app_data, user_data) -> None:
        """Handle sort dropdown change in gallery."""
        if app_data == "Date (Newest)":
            self._gallery_sort = "date_desc"
        elif app_data == "Date (Oldest)":
            self._gallery_sort = "date_asc"
        elif app_data == "File Name":
            self._gallery_sort = "name"
        elif app_data == "Similarity (Best First)":
            self._gallery_sort = "similarity_desc"
        elif app_data == "Similarity (Worst First)":
            self._gallery_sort = "similarity_asc"

        self._render_person_gallery()

    def _on_gallery_photo_select(self, face_id: int, checked: bool) -> None:
        """Handle checkbox selection for a gallery photo."""
        if not face_id:
            return
        if checked:
            self._gallery_selected_faces.add(face_id)
        else:
            self._gallery_selected_faces.discard(face_id)

    def _gallery_select_all(self) -> None:
        """Select all photos in the gallery."""
        self._gallery_selected_faces = {f.id for f in self._gallery_faces if f.id is not None}
        self._render_person_gallery()
        self._notify_status(f"Selected all {len(self._gallery_faces)} photos.", level="info")

    def _gallery_deselect_all(self) -> None:
        """Deselect all photos in the gallery."""
        self._gallery_selected_faces.clear()
        self._render_person_gallery()
        self._notify_status("Deselected all photos.", level="info")

    def _gallery_remove_selected(self) -> None:
        """Remove all selected photos from the person."""
        if not self._gallery_selected_faces:
            self._notify_status("No photos selected.", level="warning")
            return

        count = len(self._gallery_selected_faces)

        # Unassign all selected faces
        for face_id in self._gallery_selected_faces:
            self.db.unassign_face_from_person(face_id)
            self._gallery_removed_faces.add(face_id)

        # Clear selection
        self._gallery_selected_faces.clear()

        # Update person photo count
        if self._gallery_person_id:
            self.db.update_person_photo_count(self._gallery_person_id)

            # Update photo count display
            person = self.db.get_person(self._gallery_person_id)
            if person:
                # Count only non-removed photos
                photo_count = len([f for f in self._gallery_faces if f.id not in self._gallery_removed_faces])
                if person.birth_year:
                    age = person.estimated_age or 0
                    info = f"{photo_count} photos | Age ~{age} | Born ~{person.birth_year}"
                else:
                    info = f"{photo_count} photos"
                if dpg.does_item_exist(self.TAG_PERSON_GALLERY_INFO):
                    dpg.set_value(self.TAG_PERSON_GALLERY_INFO, info)

        # Update each removed card in-place instead of re-rendering entire gallery
        for face_id in self._gallery_removed_faces:
            card_tag = f"gallery_card_{face_id}"
            if dpg.does_item_exist(card_tag):
                for child in dpg.get_item_children(card_tag, 1) or []:
                    dpg.delete_item(child)
                dpg.add_text("REMOVED", parent=card_tag, color=get_status_color("error"))
                dpg.add_spacer(height=self.GALLERY_THUMB_SIZE - 40, parent=card_tag)
                dpg.add_text("Will appear in", parent=card_tag, color=get_text_color("disabled"))
                dpg.add_text("Unknown Clusters", parent=card_tag, color=get_text_color("disabled"))
                dpg.add_spacer(height=8, parent=card_tag)
        self._notify_status(f"Removed {count} photos from person. They will appear in Unknown Clusters.", level="info")

    def _gallery_refresh_all_thumbnails(self) -> None:
        """Refresh all thumbnails in the gallery by clearing cache and reloading."""
        if not self._gallery_faces:
            self._notify_status("No photos to refresh.", level="warning")
            return

        count = 0
        for face in self._gallery_faces:
            if face.id:
                # Clear cached thumbnail
                cache_key = f"{face.id}:{self.GALLERY_THUMB_SIZE}"
                if cache_key in self._gallery_photo_textures:
                    old_tex = self._gallery_photo_textures[cache_key]
                    if dpg.does_item_exist(old_tex):
                        with contextlib.suppress(Exception):
                            dpg.delete_item(old_tex)
                    del self._gallery_photo_textures[cache_key]

                # Also clear from face textures cache
                if cache_key in self._face_textures:
                    old_tex = self._face_textures[cache_key]
                    if dpg.does_item_exist(old_tex):
                        with contextlib.suppress(Exception):
                            dpg.delete_item(old_tex)
                    del self._face_textures[cache_key]

                # Clear from pending requests
                self._texture_requests.discard(cache_key)
                count += 1

        logger.info(f"Cleared {count} thumbnail caches")

        # Re-render gallery to trigger reload
        self._render_person_gallery()

        self._notify_status(f"Refreshing {count} thumbnails...", level="info")

    def _gallery_find_more(self) -> None:
        """Find more photos of the current person."""
        if self._gallery_person_id:
            self._find_person_photos(self._gallery_person_id)
            # Refresh gallery after finding more
            self._show_person_gallery(self._gallery_person_id)

    def _gallery_view_timeline(self) -> None:
        """Switch to timeline view for current person."""
        if self._gallery_person_id:
            dpg.configure_item(self.TAG_PERSON_GALLERY_DIALOG, show=False)
            self._show_timeline(self._gallery_person_id)

    def _close_person_gallery(self) -> None:
        """Close the person gallery dialog."""
        logger.info("_close_person_gallery called")
        dpg.configure_item(self.TAG_PERSON_GALLERY_DIALOG, show=False)
        self._gallery_person_id = None
        self._gallery_faces = []
        self._gallery_selected_faces.clear()
        self._gallery_removed_faces.clear()
        self._gallery_person_embeddings = []
        self._gallery_similarity_cache.clear()

    # =========================================================================
    # Photo Preview Methods (for individual photos from gallery)
    # =========================================================================

    def _show_photo_preview(self, face_id: int) -> None:
        """Show preview dialog for a specific photo."""
        logger.info(f"_show_photo_preview called for face_id={face_id}")

        face = self.db.get_face(face_id)
        if not face or not face.file_id:
            logger.warning(f"Face {face_id} not found or has no file_id")
            self._notify_status("Photo not found.", level="warning")
            return

        file_record = self.db.get_file(face.file_id)
        if not file_record:
            logger.warning(f"File record not found for file_id={face.file_id}")
            self._notify_status("File not found.", level="warning")
            return

        logger.info(f"Opening preview for: {file_record.path}")
        self._photo_preview_face_id = face_id
        self._photo_preview_file_path = file_record.path

        # Build info text
        filename = file_record.filename or "Unknown"
        size_str = self._format_file_size(file_record.size)
        date_str = file_record.modified.strftime("%Y-%m-%d %H:%M") if file_record.modified else "Unknown"
        info = f"{filename} | {size_str} | {date_str}"
        dpg.set_value(self.TAG_PHOTO_PREVIEW_INFO, info)

        # Render preview image
        self._render_photo_preview(file_record.path, face)

        logger.info("Configuring photo preview dialog to show=True")
        dpg.configure_item(self.TAG_PHOTO_PREVIEW_DIALOG, show=True)

        # Bring dialog to front
        try:
            dpg.focus_item(self.TAG_PHOTO_PREVIEW_DIALOG)
            logger.info("Focused photo preview dialog")
        except Exception as e:
            logger.warning(f"Failed to focus dialog: {e}")

        # Verify dialog is actually showing
        is_shown = dpg.is_item_shown(self.TAG_PHOTO_PREVIEW_DIALOG)
        logger.info(f"Photo preview dialog is_shown={is_shown}")

    def _render_photo_preview(self, file_path: str, face: Face | None = None) -> None:
        """Render the preview image in the dialog."""
        logger.info(f"_render_photo_preview called for: {file_path}")

        if not dpg.does_item_exist(self.TAG_PHOTO_PREVIEW_CONTAINER):
            logger.warning("Preview container does not exist")
            return

        # Clear existing content
        for child in dpg.get_item_children(self.TAG_PHOTO_PREVIEW_CONTAINER, 1) or []:
            dpg.delete_item(child)

        # Clean up previous texture
        if self._photo_preview_texture and dpg.does_item_exist(self._photo_preview_texture):
            with contextlib.suppress(Exception):
                dpg.delete_item(self._photo_preview_texture)
            self._photo_preview_texture = None

        if not os.path.exists(file_path):
            logger.error(f"File not found on disk: {file_path}")
            dpg.add_text(
                "File not found on disk.",
                parent=self.TAG_PHOTO_PREVIEW_CONTAINER,
                color=get_status_color("error")
            )
            return

        # Load and display image
        try:
            logger.info(f"Loading image from: {file_path}")
            img = Image.open(file_path)

            # Handle EXIF orientation
            with contextlib.suppress(Exception):
                img = ImageOps.exif_transpose(img)

            # Store original size before resizing (for bounding box scaling)
            original_width, original_height = img.size

            # Resize to fit preview area
            img.thumbnail((self.PHOTO_PREVIEW_SIZE, self.PHOTO_PREVIEW_SIZE), Image.Resampling.LANCZOS)

            # Convert to RGBA
            if img.mode != 'RGBA':
                img = img.convert('RGBA')

            width, height = img.size
            data = np.array(img).astype(np.float32) / 255.0
            data = data.flatten().tolist()

            # Create texture
            self._gallery_texture_counter += 1
            texture_tag = f"photo_preview_tex_{self._gallery_texture_counter}"

            dpg.add_static_texture(
                width=width,
                height=height,
                default_value=data,
                tag=texture_tag,
                parent=self.TAG_TEXTURE_REGISTRY
            )

            self._photo_preview_texture = texture_tag

            # Create drawlist for image with bounding box overlay
            with dpg.drawlist(width=width, height=height, parent=self.TAG_PHOTO_PREVIEW_CONTAINER):
                # Draw background
                dpg.draw_rectangle(
                    (0, 0),
                    (width, height),
                    color=(20, 20, 20, 255),
                    fill=(20, 20, 20, 255),
                )
                # Draw image
                dpg.draw_image(texture_tag, (0, 0), (width, height))

                # Draw face bounding box if available
                if face and face.bbox_x is not None:
                    # Calculate bounding box position on resized image
                    scale_x = width / original_width
                    scale_y = height / original_height

                    bbox_x = face.bbox_x * scale_x
                    bbox_y = face.bbox_y * scale_y
                    bbox_w = face.bbox_w * scale_x
                    bbox_h = face.bbox_h * scale_y

                    # Draw red rectangle around detected face
                    dpg.draw_rectangle(
                        (bbox_x, bbox_y),
                        (bbox_x + bbox_w, bbox_y + bbox_h),
                        color=(255, 80, 80, 255),
                        thickness=3,
                    )

                    # Add label
                    dpg.draw_text(
                        (bbox_x + 5, bbox_y - 20),
                        "Detected Face",
                        color=(255, 80, 80, 255),
                        size=14,
                    )

            logger.info(f"Successfully added preview image {width}x{height} with bounding box")

            # Add path info
            dpg.add_spacer(height=10, parent=self.TAG_PHOTO_PREVIEW_CONTAINER)
            dpg.add_text(
                f"Path: {file_path}",
                parent=self.TAG_PHOTO_PREVIEW_CONTAINER,
                color=get_text_color("disabled"),
                wrap=650
            )
            logger.info("Preview image rendering complete")

        except Exception as e:
            logger.error(f"Failed to load preview image: {e}", exc_info=True)
            dpg.add_text(
                f"Failed to load image: {e}",
                parent=self.TAG_PHOTO_PREVIEW_CONTAINER,
                color=get_status_color("error")
            )

    def _show_choose_face_dialog(self) -> None:
        """Show dialog to choose which face in the photo to assign."""
        if not self._photo_preview_face_id:
            self._notify_status("No photo selected.", level="warning")
            return

        # Get the current face to find its file_id
        current_face = self.db.get_face(self._photo_preview_face_id)
        if not current_face or not current_face.file_id:
            self._notify_status("Photo not found.", level="warning")
            return

        # Get all faces detected in this photo
        all_faces = self.db.get_faces_for_file(current_face.file_id)
        if not all_faces:
            self._notify_status("No faces found in this photo.", level="warning")
            return

        logger.info(f"Found {len(all_faces)} faces in photo")

        # Clear container
        if not dpg.does_item_exist(self.TAG_CHOOSE_FACE_CONTAINER):
            return

        children = dpg.get_item_children(self.TAG_CHOOSE_FACE_CONTAINER, 1)
        if children:
            for child in children:
                try:
                    if dpg.does_item_exist(child):
                        dpg.delete_item(child)
                except Exception:
                    pass

        # Render face options in a grid
        row_group = None
        faces_per_row = 4

        for i, face in enumerate(all_faces):
            if i % faces_per_row == 0:
                row_group = dpg.add_group(
                    horizontal=True,
                    parent=self.TAG_CHOOSE_FACE_CONTAINER
                )
                dpg.add_spacer(width=10, parent=row_group)

            # Create face card
            with dpg.group(parent=row_group):
                # Get thumbnail
                thumb = self._get_face_thumbnail(face)
                is_current = face.id == self._photo_preview_face_id

                # Show thumbnail or placeholder
                if thumb:
                    dpg.add_image_button(
                        thumb,
                        width=120,
                        height=120,
                        user_data=face.id,
                        callback=lambda s, a, u: self._select_face_for_person(u),
                    )
                else:
                    dpg.add_button(
                        label="[Face]",
                        width=120,
                        height=120,
                        user_data=face.id,
                        callback=lambda s, a, u: self._select_face_for_person(u),
                    )

                # Show status
                if is_current:
                    dpg.add_text("(Current)", color=get_accent_color())
                elif face.person_id:
                    person = self.db.get_person(face.person_id)
                    if person:
                        dpg.add_text(f"Assigned to:\n{person.name}", color=get_text_color("disabled"))
                    else:
                        dpg.add_text("Assigned", color=get_text_color("disabled"))
                else:
                    dpg.add_text("Unassigned", color=get_text_color("disabled"))

                # Confidence
                if face.confidence:
                    dpg.add_text(f"Conf: {face.confidence:.2f}", color=get_text_color("disabled"))

                dpg.add_spacer(width=15)

        # Show dialog
        dpg.configure_item(self.TAG_CHOOSE_FACE_DIALOG, show=True)
        dpg.focus_item(self.TAG_CHOOSE_FACE_DIALOG)

    def _select_face_for_person(self, selected_face_id: int) -> None:
        """Assign the selected face to the current person."""
        if not selected_face_id or not self._gallery_person_id:
            return

        logger.info(f"Selecting face {selected_face_id} for person {self._gallery_person_id}")

        # Clear cached thumbnails for both old and new faces
        if self._photo_preview_face_id:
            old_key = f"{self._photo_preview_face_id}:{self.GALLERY_THUMB_SIZE}"
            if old_key in self._gallery_photo_textures:
                old_tex = self._gallery_photo_textures[old_key]
                if dpg.does_item_exist(old_tex):
                    with contextlib.suppress(Exception):
                        dpg.delete_item(old_tex)
                del self._gallery_photo_textures[old_key]
            self._texture_requests.discard(old_key)
            logger.info(f"Cleared cache for old face {self._photo_preview_face_id}")

        new_key = f"{selected_face_id}:{self.GALLERY_THUMB_SIZE}"
        if new_key in self._gallery_photo_textures:
            new_tex = self._gallery_photo_textures[new_key]
            if dpg.does_item_exist(new_tex):
                with contextlib.suppress(Exception):
                    dpg.delete_item(new_tex)
            del self._gallery_photo_textures[new_key]
        self._texture_requests.discard(new_key)
        logger.info(f"Cleared cache for new face {selected_face_id}")

        # Unassign the old face
        if self._photo_preview_face_id:
            self.db.unassign_face_from_person(self._photo_preview_face_id)
            logger.info(f"Unassigned old face {self._photo_preview_face_id}")

        # Assign the new face
        self.db.assign_face_to_person(selected_face_id, self._gallery_person_id)
        logger.info(f"Assigned new face {selected_face_id} to person {self._gallery_person_id}")

        # Update person photo count
        self.db.update_person_photo_count(self._gallery_person_id)

        # Update the current face ID
        self._photo_preview_face_id = selected_face_id

        # Close choose face dialog
        self._close_choose_face_dialog()

        # Reload faces from database to get updated assignments
        faces = self.db.get_faces_for_person(self._gallery_person_id, limit=500)
        self._gallery_faces = faces
        logger.info(f"Reloaded {len(faces)} faces from database after face selection")

        # Refresh the gallery to show updated thumbnail
        self._render_person_gallery()

        # Close the preview and reopen with new face
        self._close_photo_preview()

        self._notify_status("Face assignment updated!", level="info")

    def _close_choose_face_dialog(self) -> None:
        """Close the choose face dialog."""
        dpg.configure_item(self.TAG_CHOOSE_FACE_DIALOG, show=False)

    def _refresh_face_thumbnail(self) -> None:
        """Regenerate thumbnail for current face from its bounding box."""
        if not self._photo_preview_face_id:
            self._notify_status("No face selected.", level="warning")
            return

        face = self.db.get_face(self._photo_preview_face_id)
        if not face:
            self._notify_status("Face not found.", level="warning")
            return

        logger.info(f"Refreshing thumbnail for face {face.id}")

        # Clear cached thumbnail texture
        cache_key = f"{face.id}:{self.GALLERY_THUMB_SIZE}"
        if cache_key in self._gallery_photo_textures:
            old_texture = self._gallery_photo_textures[cache_key]
            if dpg.does_item_exist(old_texture):
                try:
                    dpg.delete_item(old_texture)
                    logger.info(f"Deleted old texture {old_texture}")
                except Exception as e:
                    logger.warning(f"Failed to delete texture: {e}")
            del self._gallery_photo_textures[cache_key]

        # Also clear from face textures cache
        if cache_key in self._face_textures:
            old_texture = self._face_textures[cache_key]
            if dpg.does_item_exist(old_texture):
                with contextlib.suppress(Exception):
                    dpg.delete_item(old_texture)
            del self._face_textures[cache_key]

        # Remove from pending requests so it can be queued again
        self._texture_requests.discard(cache_key)
        logger.info(f"Cleared texture request key: {cache_key}")

        # Regenerate thumbnail (next render will create it)
        logger.info("Thumbnail cache cleared, will regenerate on next render")

        # Refresh the gallery to show new thumbnail
        self._render_person_gallery()

        self._notify_status("Thumbnail refreshed!", level="info")

    def _format_file_size(self, size: int) -> str:
        """Format file size in human-readable form."""
        if size >= 1024 * 1024 * 1024:
            return f"{size / (1024 * 1024 * 1024):.1f} GB"
        elif size >= 1024 * 1024:
            return f"{size / (1024 * 1024):.1f} MB"
        elif size >= 1024:
            return f"{size / 1024:.0f} KB"
        return f"{size} B"

    def _photo_preview_open(self) -> None:
        """Open the current preview photo with default application."""
        if self._photo_preview_file_path:
            try:
                os.startfile(self._photo_preview_file_path)
            except Exception as e:
                logger.error(f"Failed to open file: {e}")
                self._notify_status("Failed to open file.", level="error")

    def _photo_preview_explorer(self) -> None:
        """Show the current preview photo in Windows Explorer."""
        if self._photo_preview_file_path and os.path.exists(self._photo_preview_file_path):
            try:
                subprocess.run(['explorer', '/select,', self._photo_preview_file_path], check=False)
            except Exception as e:
                logger.error(f"Failed to open Explorer: {e}")
                self._notify_status("Failed to open Explorer.", level="error")

    def _photo_preview_remove(self) -> None:
        """Remove the current photo from the person (unassign face)."""
        if not self._photo_preview_face_id:
            return

        face = self.db.get_face(self._photo_preview_face_id)
        if not face:
            return

        # Unassign the face from the person
        self.db.unassign_face_from_person(self._photo_preview_face_id)

        # Mark as removed for visual feedback (don't remove from list to avoid layout shift)
        self._gallery_removed_faces.add(self._photo_preview_face_id)

        # Update person photo count in database
        if self._gallery_person_id:
            self.db.update_person_photo_count(self._gallery_person_id)

            # Update photo count display
            person = self.db.get_person(self._gallery_person_id)
            if person:
                # Count only non-removed photos
                photo_count = len([f for f in self._gallery_faces if f.id not in self._gallery_removed_faces])
                if person.birth_year:
                    age = person.estimated_age or 0
                    info = f"{photo_count} photos | Age ~{age} | Born ~{person.birth_year}"
                else:
                    info = f"{photo_count} photos"
                if dpg.does_item_exist(self.TAG_PERSON_GALLERY_INFO):
                    dpg.set_value(self.TAG_PERSON_GALLERY_INFO, info)

        self._notify_status("Photo removed from person. It will appear in Unknown Clusters.", level="info")

        # Close preview and update the card in-place
        self._close_photo_preview()
        card_tag = f"gallery_card_{self._photo_preview_face_id}"
        if dpg.does_item_exist(card_tag):
            for child in dpg.get_item_children(card_tag, 1) or []:
                dpg.delete_item(child)
            dpg.add_text("REMOVED", parent=card_tag, color=get_status_color("error"))
            dpg.add_spacer(height=self.GALLERY_THUMB_SIZE - 40, parent=card_tag)
            dpg.add_text("Will appear in", parent=card_tag, color=get_text_color("disabled"))
            dpg.add_text("Unknown Clusters", parent=card_tag, color=get_text_color("disabled"))
            dpg.add_spacer(height=8, parent=card_tag)

    def _close_photo_preview(self) -> None:
        """Close the photo preview dialog."""
        logger.info("_close_photo_preview called")
        dpg.configure_item(self.TAG_PHOTO_PREVIEW_DIALOG, show=False)

        # Ensure gallery dialog remains visible
        if dpg.does_item_exist(self.TAG_PERSON_GALLERY_DIALOG):
            gallery_shown = dpg.is_item_shown(self.TAG_PERSON_GALLERY_DIALOG)
            logger.info(f"Gallery dialog is_shown={gallery_shown} after closing preview")
            if not gallery_shown:
                logger.warning("Gallery was hidden, re-showing it")
                dpg.configure_item(self.TAG_PERSON_GALLERY_DIALOG, show=True)
                dpg.focus_item(self.TAG_PERSON_GALLERY_DIALOG)

        # Clean up texture
        if self._photo_preview_texture and dpg.does_item_exist(self._photo_preview_texture):
            with contextlib.suppress(Exception):
                dpg.delete_item(self._photo_preview_texture)
            self._photo_preview_texture = None

        self._photo_preview_face_id = None
        self._photo_preview_file_path = None

    def _start_texture_worker(self) -> None:
        # Check if workers are already running
        if self._texture_worker_threads and any(t.is_alive() for t in self._texture_worker_threads):
            return
        self._texture_worker_stop.clear()
        self._texture_worker_threads = []
        # Start multiple worker threads for parallel loading
        for i in range(self._num_texture_workers):
            thread = threading.Thread(target=self._texture_worker_loop, daemon=True, name=f"TextureWorker-{i}")
            thread.start()
            self._texture_worker_threads.append(thread)
        logger.info(f"Started {self._num_texture_workers} texture worker threads")

    def _texture_worker_loop(self) -> None:
        while not self._texture_worker_stop.is_set():
            try:
                task = self._texture_queue.get(timeout=0.2)
            except queue.Empty:
                continue
            if task is None:
                continue
            # logger.info(f"Worker processing {task.get('kind')} task: key={task.get('key')}")
            try:
                result = self._build_texture_data(task)
            except Exception as exc:
                logger.warning(f"Texture worker failed for {task.get('path')}: {exc}")
                result = {"key": task.get("key"), "kind": task.get("kind"), "success": False}
            with self._texture_results_lock:
                self._texture_results.append(result)
            self._texture_queue.task_done()

    def _queue_texture_load(
        self,
        kind: str,
        key: str,
        size: int,
        face: Face | None = None,
        pet_detection: PetDetection | None = None,
    ) -> None:
        if key in self._texture_requests:
            return

        # Get file_id and bbox from either face or pet_detection
        if face:
            file_id = face.file_id
            bbox = (face.bbox_x, face.bbox_y, face.bbox_w, face.bbox_h)
            entity_id = face.id
        elif pet_detection:
            file_id = pet_detection.file_id
            bbox = (pet_detection.bbox_x, pet_detection.bbox_y, pet_detection.bbox_w, pet_detection.bbox_h)
            entity_id = pet_detection.id
        else:
            logger.warning("_queue_texture_load called without face or pet_detection")
            return

        file_record = self.db.get_file(file_id) if file_id else None
        if not file_record:
            logger.warning(f"Cannot load texture for {kind} {entity_id}: file_id={file_id} not found in database")
            return
        if not file_record.path:
            logger.warning(f"Cannot load texture for {kind} {entity_id}: file record {file_record.id} has no path")
            return

        self._texture_requests.add(key)
        page_number = None
        if face and face.page_number is not None:
            page_number = face.page_number
        task = {
            "kind": kind,
            "key": key,
            "path": file_record.path,
            "bbox": bbox,
            "size": int(size),
            "page_number": page_number,
        }
        self._texture_queue.put(task)

    def _build_texture_data(self, task: dict) -> dict:
        image_path = task.get("path")
        bbox = task.get("bbox")
        size = int(task.get("size", 64))
        kind = task.get("kind")
        key = task.get("key")
        if not image_path or not bbox:
            return {"key": key, "kind": kind, "success": False}
        if not os.path.exists(image_path):
            logger.warning(f"Image file does not exist: {image_path}")
            return {"key": key, "kind": kind, "success": False}
        if image_path.lower().endswith('.pdf'):
            from duplicleaner.ui.files_panel import _render_pdf_page
            page_num = task.get("page_number") or 0
            image = _render_pdf_page(image_path, page_num=page_num)
            if image is None:
                return {"key": key, "kind": kind, "success": False}
            image = image.convert("RGB")
        else:
            raw_image = Image.open(image_path)
            # Apply EXIF transpose to get correctly oriented image
            image = ImageOps.exif_transpose(raw_image).convert("RGB")
        width, height = image.size
        # OpenCV auto-rotates JPEGs so bboxes are already in oriented coords
        x, y, bw, bh = bbox[0], bbox[1], bbox[2], bbox[3]
        left, top, right, bottom = self._square_crop_bounds(
            x,
            y,
            bw,
            bh,
            width,
            height,
        )
        if right <= left or bottom <= top:
            return {"key": key, "kind": kind, "success": False}
        cropped = image.crop((left, top, right, bottom)).resize((size, size), Image.BILINEAR)
        rgba = cropped.convert("RGBA")
        data = np.asarray(rgba).astype(np.float32) / 255.0
        return {
            "key": key,
            "kind": kind,
            "size": size,
            "data": data.flatten().tolist(),
            "success": True,
        }

    def _process_texture_results(self, max_per_frame: int = 4) -> None:
        created = 0
        with self._texture_results_lock:
            while self._texture_results and created < max_per_frame:
                # Prioritize gallery textures over face textures
                result = None
                # First, look for gallery textures
                gallery_result = None
                for r in self._texture_results:
                    if r.get("kind") == "gallery":
                        gallery_result = r
                        break
                if gallery_result:
                    result = gallery_result
                    self._texture_results.remove(gallery_result)
                # If no gallery textures, take next face texture
                elif self._texture_results:
                    result = self._texture_results.popleft()
                if result is None:
                    break
                created += 1
                key = result.get("key")
                kind = result.get("kind")
                success = result.get("success")
                self._texture_requests.discard(key)
                if not success:
                    logger.info(f"Texture load failed for key={key}, kind={kind}")
                    continue
                size = int(result.get("size", 64))
                data = result.get("data")
                if not data:
                    logger.warning(f"Texture result has no data for key={key}")
                    continue
                if kind == "face":
                    tex_tag = f"face_tex_{self._texture_counter}"
                    self._texture_counter += 1
                    dpg.add_static_texture(
                        size,
                        size,
                        data,
                        tag=tex_tag,
                        parent=self.TAG_TEXTURE_REGISTRY,
                    )
                    self._face_textures[key] = tex_tag
                    self._prune_textures(limit=2000)
                    self._pending_face_ui_refresh = True
                elif kind == "pet":
                    tex_tag = f"pet_tex_{self._texture_counter}"
                    self._texture_counter += 1
                    dpg.add_static_texture(
                        size,
                        size,
                        data,
                        tag=tex_tag,
                        parent=self.TAG_TEXTURE_REGISTRY,
                    )
                    self._pet_textures[key] = tex_tag
                    self._prune_pet_textures(limit=2000)
                    self._pending_face_ui_refresh = True
                else:
                    tex_tag = f"gallery_face_tex_{self._gallery_texture_counter}"
                    self._gallery_texture_counter += 1
                    dpg.add_static_texture(
                        size,
                        size,
                        data,
                        tag=tex_tag,
                        parent=self.TAG_TEXTURE_REGISTRY,
                    )
                    self._gallery_photo_textures[key] = tex_tag
                    self._prune_gallery_textures(limit=300)
                    # Mark that gallery/dialog views need refresh (will be batched in on_frame)
                    self._gallery_needs_refresh = True
                    self._intermediate_needs_refresh = True
                    self._all_faces_needs_refresh = True
                    self._rematch_needs_refresh = True

    # =========================================================================
    # View All Faces Methods
    # =========================================================================

    def _show_all_faces_dialog(self, cluster_id: int, face_ids: list[int]) -> None:
        """Show dialog with all faces from a cluster."""
        if not dpg.does_item_exist(self.TAG_ALL_FACES_CONTAINER):
            return

        logger.info(f"Opening View All dialog for cluster {cluster_id} with {len(face_ids)} faces")

        # Save state for refreshes
        self._all_faces_cluster_id = cluster_id
        self._all_faces_face_ids = face_ids[:200]
        self._all_faces_needs_refresh = True
        self._all_faces_last_loaded = 0
        self._all_faces_stuck_count = 0

        # Clear existing
        for child in dpg.get_item_children(self.TAG_ALL_FACES_CONTAINER, 1) or []:
            dpg.delete_item(child)

        faces = self.db.get_faces_by_ids(self._all_faces_face_ids)
        if not faces:
            dpg.add_text("No faces found", parent=self.TAG_ALL_FACES_CONTAINER)
            dpg.configure_item(self.TAG_ALL_FACES_DIALOG, show=True)
            return

        # Render grid (10 per row, 72px thumbnails)
        row_group = None
        thumbs_loaded = 0
        for i, face in enumerate(faces):
            if i % 10 == 0:
                row_group = dpg.add_group(horizontal=True, parent=self.TAG_ALL_FACES_CONTAINER)

            thumb = self._get_face_thumbnail(face)
            if thumb and row_group:
                dpg.add_image_button(
                    thumb,
                    width=72,
                    height=72,
                    parent=row_group,
                    user_data=face.id,
                    callback=lambda s, a, u: self._on_face_preview_click(u),
                )
                thumbs_loaded += 1

        # Show loading message if no thumbnails loaded yet
        if thumbs_loaded == 0:
            dpg.add_text(
                f"Loading thumbnails for {len(faces)} faces...",
                parent=self.TAG_ALL_FACES_CONTAINER,
                color=(200, 200, 100),
            )

        dpg.configure_item(self.TAG_ALL_FACES_DIALOG, show=True)

    def _refresh_all_faces_dialog(self) -> None:
        """Refresh the View All dialog to show newly loaded thumbnails."""
        if not dpg.does_item_exist(self.TAG_ALL_FACES_CONTAINER):
            logger.warning("View All refresh: container doesn't exist")
            return
        if not self._all_faces_face_ids:
            logger.warning("View All refresh: no face IDs")
            return

        logger.info(f"Refreshing View All dialog ({len(self._all_faces_face_ids)} faces)")

        # Clear existing
        for child in dpg.get_item_children(self.TAG_ALL_FACES_CONTAINER, 1) or []:
            dpg.delete_item(child)

        faces = self.db.get_faces_by_ids(self._all_faces_face_ids)
        if not faces:
            dpg.add_text("No faces found", parent=self.TAG_ALL_FACES_CONTAINER)
            return

        # Render grid (10 per row, 72px thumbnails)
        row_group = None
        thumbs_loaded = 0
        for i, face in enumerate(faces):
            if i % 10 == 0:
                row_group = dpg.add_group(horizontal=True, parent=self.TAG_ALL_FACES_CONTAINER)

            thumb = self._get_face_thumbnail(face)
            if thumb and row_group:
                dpg.add_image_button(
                    thumb,
                    width=72,
                    height=72,
                    parent=row_group,
                    user_data=face.id,
                    callback=lambda s, a, u: self._on_face_preview_click(u),
                )
                thumbs_loaded += 1

        # Stuck detection: stop refreshing if no progress for 5 attempts
        if thumbs_loaded == self._all_faces_last_loaded:
            self._all_faces_stuck_count += 1
            if self._all_faces_stuck_count >= 5:
                logger.info(f"View All: stopping refresh, stuck at {thumbs_loaded}/{len(faces)} loaded")
                self._all_faces_needs_refresh = False
                return
        else:
            self._all_faces_stuck_count = 0

        self._all_faces_last_loaded = thumbs_loaded

        # Keep refreshing if there are missing thumbnails
        if thumbs_loaded < len(faces):
            self._all_faces_needs_refresh = True
        else:
            logger.info(f"View All: all {thumbs_loaded} thumbnails loaded!")
            self._all_faces_needs_refresh = False

    def _on_face_preview_click(self, face_id: int) -> None:
        """Handle clicking on a face thumbnail in the View All dialog."""
        self._show_face_preview(face_id)

    def _render_face_preview(self) -> None:
        if not dpg.does_item_exist(self.TAG_FACE_PREVIEW_DRAW):
            return
        # Clear drawlist
        for child in dpg.get_item_children(self.TAG_FACE_PREVIEW_DRAW, 1) or []:
            dpg.delete_item(child)
        if not self._preview_texture_tag:
            return
        w, h = self._preview_display_size
        dpg.configure_item(self.TAG_FACE_PREVIEW_DRAW, width=int(w), height=int(h))
        dpg.draw_rectangle(
            (0, 0),
            (w, h),
            color=(20, 20, 20, 255),
            fill=(20, 20, 20, 255),
            parent=self.TAG_FACE_PREVIEW_DRAW,
        )
        dpg.draw_image(
            self._preview_texture_tag,
            (0, 0),
            (w, h),
            parent=self.TAG_FACE_PREVIEW_DRAW,
        )
        if self._preview_bbox:
            x, y, bw, bh = self._preview_bbox
            px = x * self._preview_scale
            py = y * self._preview_scale
            pw = bw * self._preview_scale
            ph = bh * self._preview_scale
            dpg.draw_rectangle(
                (px, py),
                (px + pw, py + ph),
                color=(255, 80, 80, 255),
                thickness=2,
                parent=self.TAG_FACE_PREVIEW_DRAW,
            )

    def _preview_local_pos(self) -> tuple[float, float] | None:
        if not dpg.does_item_exist(self.TAG_FACE_PREVIEW_DRAW):
            return None
        mouse_x, mouse_y = dpg.get_mouse_pos()
        rect_min = dpg.get_item_rect_min(self.TAG_FACE_PREVIEW_DRAW)
        rect_max = dpg.get_item_rect_max(self.TAG_FACE_PREVIEW_DRAW)
        if mouse_x < rect_min[0] or mouse_y < rect_min[1]:
            return None
        if mouse_x > rect_max[0] or mouse_y > rect_max[1]:
            return None
        return (mouse_x - rect_min[0], mouse_y - rect_min[1])

    def _on_preview_mouse_move(self, sender, app_data, user_data) -> None:
        if not self._preview_bbox:
            return
        pos = self._preview_local_pos()
        if not pos:
            if self._preview_hover_handle is not None:
                self._preview_hover_handle = None
                self._render_face_preview()
            return
        x, y, bw, bh = self._preview_bbox
        px = x * self._preview_scale
        py = y * self._preview_scale
        pw = bw * self._preview_scale
        ph = bh * self._preview_scale
        hit_size = 24
        corners = {
            "tl": (px, py),
            "tr": (px + pw, py),
            "bl": (px, py + ph),
            "br": (px + pw, py + ph),
        }
        hover = None
        pos_x, pos_y = pos
        for key, (hx, hy) in corners.items():
            if abs(pos_x - hx) <= hit_size and abs(pos_y - hy) <= hit_size:
                hover = key
                break
        if hover != self._preview_hover_handle:
            self._preview_hover_handle = hover
            self._render_face_preview()

    def _on_preview_mouse_down(self, sender, app_data, user_data) -> None:
        if not self._preview_bbox:
            return
        pos = self._preview_local_pos()
        if not pos:
            return
        x, y, bw, bh = self._preview_bbox
        px = x * self._preview_scale
        py = y * self._preview_scale
        pw = bw * self._preview_scale
        ph = bh * self._preview_scale
        hit_size = 24
        corners = {
            "tl": (px, py),
            "tr": (px + pw, py),
            "bl": (px, py + ph),
            "br": (px + pw, py + ph),
        }
        # Compensate for any drawlist padding/offset in the child window
        pos_x, pos_y = pos
        for key, (hx, hy) in corners.items():
            if abs(pos_x - hx) <= hit_size and abs(pos_y - hy) <= hit_size:
                self._preview_resize_handle = key
                self._preview_resize_start = pos
                self._preview_bbox_start = self._preview_bbox
                self._preview_dragging = False
                return
        if px <= pos[0] <= px + pw and py <= pos[1] <= py + ph:
            self._preview_dragging = True
            self._preview_drag_offset = (pos[0] - px, pos[1] - py)

    def _on_preview_mouse_drag(self, sender, app_data, user_data) -> None:
        if not self._preview_bbox:
            return
        pos = self._preview_local_pos()
        if not pos:
            return
        if self._preview_resize_handle and self._preview_bbox_start:
            x, y, bw, bh = self._preview_bbox_start
            px = x * self._preview_scale
            py = y * self._preview_scale
            pw = bw * self._preview_scale
            ph = bh * self._preview_scale
            if self._preview_resize_handle == "tl":
                new_px = pos[0]
                new_py = pos[1]
                new_pw = (px + pw) - new_px
                new_ph = (py + ph) - new_py
            elif self._preview_resize_handle == "tr":
                new_px = px
                new_py = pos[1]
                new_pw = pos[0] - px
                new_ph = (py + ph) - new_py
            elif self._preview_resize_handle == "bl":
                new_px = pos[0]
                new_py = py
                new_pw = (px + pw) - new_px
                new_ph = pos[1] - py
            else:
                new_px = px
                new_py = py
                new_pw = pos[0] - px
                new_ph = pos[1] - py
            min_size = 10
            new_pw = max(min_size, new_pw)
            new_ph = max(min_size, new_ph)
            disp_w, disp_h = self._preview_display_size
            new_px = max(0.0, min(new_px, disp_w - new_pw))
            new_py = max(0.0, min(new_py, disp_h - new_ph))
            new_x = float(new_px / self._preview_scale)
            new_y = float(new_py / self._preview_scale)
            new_w = float(new_pw / self._preview_scale)
            new_h = float(new_ph / self._preview_scale)
            self._preview_bbox = (int(new_x), int(new_y), int(new_w), int(new_h))
            self._render_face_preview()
            return
        if not self._preview_dragging:
            return
        dx, dy = self._preview_drag_offset
        new_px = max(0.0, pos[0] - dx)
        new_py = max(0.0, pos[1] - dy)
        disp_w, disp_h = self._preview_display_size
        x, y, bw, bh = self._preview_bbox
        max_px = max(0.0, disp_w - bw * self._preview_scale)
        max_py = max(0.0, disp_h - bh * self._preview_scale)
        new_px = min(new_px, max_px)
        new_py = min(new_py, max_py)
        new_x = float(new_px / self._preview_scale)
        new_y = float(new_py / self._preview_scale)
        self._preview_bbox = (int(new_x), int(new_y), int(bw), int(bh))
        self._render_face_preview()

    def _on_preview_mouse_up(self, sender, app_data, user_data) -> None:
        self._preview_dragging = False
        self._preview_resize_handle = None
        self._preview_bbox_start = None

    def _save_face_bbox(self) -> None:
        if not self._preview_face_id or not self._preview_bbox:
            return
        x, y, w, h = self._preview_bbox
        self.db.update_face_bbox(self._preview_face_id, x, y, w, h)
        self._notify_status("Face box updated.", level="info")
        self._refresh()

    def _apply_orientation_to_bbox(
        self,
        bbox: tuple[int, int, int, int],
    ) -> tuple[float, float, float, float] | None:
        """Map a raw bbox into oriented image coordinates."""
        w, h = self._preview_raw_size
        x, y, bw, bh = bbox
        corners = [
            (x, y),
            (x + bw, y),
            (x, y + bh),
            (x + bw, y + bh),
        ]
        mapped = [self._transform_point(pt, self._preview_orientation, w, h, inverse=False) for pt in corners]
        xs = [p[0] for p in mapped]
        ys = [p[1] for p in mapped]
        if not xs or not ys:
            return None
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        return (min_x, min_y, max_x - min_x, max_y - min_y)

    def _apply_orientation_to_bbox_with_size(
        self,
        bbox: tuple[int, int, int, int],
        orientation: int,
        width: int,
        height: int,
    ) -> tuple[float, float, float, float] | None:
        """Map a raw bbox into oriented image coordinates using explicit size."""
        x, y, bw, bh = bbox
        corners = [
            (x, y),
            (x + bw, y),
            (x, y + bh),
            (x + bw, y + bh),
        ]
        mapped = [self._transform_point(pt, orientation, width, height, inverse=False) for pt in corners]
        xs = [p[0] for p in mapped]
        ys = [p[1] for p in mapped]
        if not xs or not ys:
            return None
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        return (min_x, min_y, max_x - min_x, max_y - min_y)

    def _invert_orientation_from_bbox(
        self,
        bbox: tuple[float, float, float, float],
    ) -> tuple[int, int, int, int]:
        """Map an oriented bbox back to raw image coordinates."""
        w, h = self._preview_raw_size
        x, y, bw, bh = bbox
        corners = [
            (x, y),
            (x + bw, y),
            (x, y + bh),
            (x + bw, y + bh),
        ]
        mapped = [self._transform_point(pt, self._preview_orientation, w, h, inverse=True) for pt in corners]
        xs = [p[0] for p in mapped]
        ys = [p[1] for p in mapped]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        min_x = max(0, min(int(min_x), w - 1))
        min_y = max(0, min(int(min_y), h - 1))
        max_x = max(min_x + 1, min(int(max_x), w))
        max_y = max(min_y + 1, min(int(max_y), h))
        return (min_x, min_y, max_x - min_x, max_y - min_y)

    def _transform_point(
        self,
        pt: tuple[float, float],
        orientation: int,
        width: int,
        height: int,
        inverse: bool,
    ) -> tuple[float, float]:
        x, y = pt
        if not inverse:
            if orientation == 1:
                return (x, y)
            if orientation == 2:
                return (width - x, y)
            if orientation == 3:
                return (width - x, height - y)
            if orientation == 4:
                return (x, height - y)
            if orientation == 5:
                return (y, x)
            if orientation == 6:
                return (height - y, x)
            if orientation == 7:
                return (height - y, width - x)
            if orientation == 8:
                return (y, width - x)
            return (x, y)
        # inverse mapping
        if orientation == 1:
            return (x, y)
        if orientation == 2:
            return (width - x, y)
        if orientation == 3:
            return (width - x, height - y)
        if orientation == 4:
            return (x, height - y)
        if orientation == 5:
            return (y, x)
        if orientation == 6:
            return (y, width - x)
        if orientation == 7:
            return (height - y, width - x)
        if orientation == 8:
            return (height - y, x)
        return (x, y)

    def _rotate_preview(self, angle: int) -> None:
        """Rotate the preview image and update face boxes."""
        if not self._preview_file_id or not self._preview_face_id:
            return
        file_record = self.db.get_file(self._preview_file_id)
        if not file_record or not file_record.path:
            return
        try:
            raw_image = Image.open(file_record.path)
            # Apply EXIF orientation first so we rotate the visual image
            oriented = ImageOps.exif_transpose(raw_image)
            orient_w, orient_h = oriented.size
            rotated = oriented.rotate(angle, expand=True)
            # Save with EXIF orientation 1 since pixels are now correctly oriented
            exif = raw_image.getexif()
            if exif is not None:
                exif[274] = 1
            if exif is not None and len(exif):
                rotated.save(file_record.path, exif=exif.tobytes())
            else:
                rotated.save(file_record.path)

            # Update all face boxes using oriented dimensions (bboxes are in oriented coords)
            faces = self.db.get_faces_for_file(self._preview_file_id)
            for face in faces:
                if angle == 90:
                    # rotate left (CCW)
                    new_x = face.bbox_y
                    new_y = orient_w - (face.bbox_x + face.bbox_w)
                    new_w = face.bbox_h
                    new_h = face.bbox_w
                elif angle == -90:
                    # rotate right (CW)
                    new_x = orient_h - (face.bbox_y + face.bbox_h)
                    new_y = face.bbox_x
                    new_w = face.bbox_h
                    new_h = face.bbox_w
                else:
                    new_x = orient_w - (face.bbox_x + face.bbox_w)
                    new_y = orient_h - (face.bbox_y + face.bbox_h)
                    new_w = face.bbox_w
                    new_h = face.bbox_h
                self.db.update_face_bbox(face.id, int(new_x), int(new_y), int(new_w), int(new_h))

            # Reload preview
            self._show_face_preview(self._preview_face_id)
            self._refresh()
        except Exception:
            self._notify_status("Failed to rotate image.", level="warning")

    # ------------------------------------------------------------------
    # Re-match results dialog
    # ------------------------------------------------------------------

    def _show_rematch_results(self, auto_count: int, suggestions: list) -> None:
        """Show re-match results: auto-assigned count and suggestion cards."""
        if not suggestions:
            msg = f"Re-matched {auto_count} faces to known people." if auto_count else "No matches found."
            self._notify_status(msg)
            return

        # Store suggestions for the dialog lifetime
        self._rematch_suggestions = list(suggestions)

        # Update header - include demotion count if any
        conflict_count = sum(1 for s in suggestions if len(s) >= 5 and s[4] is not None)
        if dpg.does_item_exist(self.TAG_REMATCH_HEADER):
            header = f"Auto-assigned {auto_count} faces. {len(suggestions)} faces need review"
            if conflict_count:
                header += f" ({conflict_count} had conflicts)"
            header += ":"
            dpg.set_value(self.TAG_REMATCH_HEADER, header)

        self._render_rematch_suggestions()
        dpg.configure_item(self.TAG_REMATCH_DIALOG, show=True)

    # Max faces to render per person in rematch dialog (avoids exceeding gallery texture cache)
    REMATCH_PER_PERSON_LIMIT = 20

    def _render_rematch_suggestions(self) -> None:
        """Render suggestion cards in the rematch dialog, grouped by person."""
        if not dpg.does_item_exist(self.TAG_REMATCH_CONTAINER):
            return
        for child in dpg.get_item_children(self.TAG_REMATCH_CONTAINER, 1) or []:
            dpg.delete_item(child)

        if not self._rematch_suggestions:
            dpg.add_text("All suggestions processed.", parent=self.TAG_REMATCH_CONTAINER)
            return

        # Group suggestions by person (5-element tuples: person_id, name, face, similarity, reason)
        by_person: dict[int, list[tuple]] = {}
        for suggestion in self._rematch_suggestions:
            person_id = suggestion[0]
            by_person.setdefault(person_id, []).append(suggestion)

        for person_id, items in by_person.items():
            person_name = items[0][1]
            dpg.add_text(
                f"{person_name} ({len(items)} suggested):",
                parent=self.TAG_REMATCH_CONTAINER,
                color=get_accent_color(),
            )
            dpg.add_spacer(height=4, parent=self.TAG_REMATCH_CONTAINER)

            # Cap displayed faces per person to stay within gallery texture cache
            visible = items[:self.REMATCH_PER_PERSON_LIMIT]
            remaining = len(items) - len(visible)

            for suggestion in visible:
                face = suggestion[2]
                similarity = suggestion[3]
                reason = suggestion[4] if len(suggestion) >= 5 else None
                with dpg.group(horizontal=True, parent=self.TAG_REMATCH_CONTAINER):
                    thumb = self._get_face_thumbnail(face, size=64)
                    if thumb:
                        dpg.add_image_button(
                            thumb,
                            width=64,
                            height=64,
                            user_data=face.id,
                            callback=lambda s, a, u: self._show_face_preview(u),
                        )
                    else:
                        dpg.add_button(
                            label="[Face]",
                            width=64,
                            height=64,
                            user_data=face.id,
                            callback=lambda s, a, u: self._show_face_preview(u),
                        )

                    score_pct = int(similarity * 100)
                    score_color = (
                        get_status_color("success") if similarity >= 0.7
                        else get_status_color("warning") if similarity >= 0.5
                        else get_status_color("error")
                    )
                    with dpg.group(horizontal=False):
                        with dpg.group(horizontal=True):
                            dpg.add_text(f"{person_name}")
                            dpg.add_text(f"({score_pct}%)", color=score_color)

                        if reason:
                            dpg.add_text(
                                reason,
                                color=get_status_color("warning"),
                                wrap=300,
                            )

                        with dpg.group(horizontal=True):
                            dpg.add_button(
                                label="Assign",
                                small=True,
                                callback=lambda s, a, u: self._assign_rematch_suggestion(u),
                                user_data=(face.id, person_id),
                            )
                            dpg.add_button(
                                label="Skip",
                                small=True,
                                callback=lambda s, a, u: self._skip_rematch_suggestion(u),
                                user_data=face.id,
                            )

            if remaining > 0:
                dpg.add_text(
                    f"  +{remaining} more -- assign or skip above to see next batch",
                    parent=self.TAG_REMATCH_CONTAINER,
                    color=get_text_color("disabled"),
                )

            dpg.add_separator(parent=self.TAG_REMATCH_CONTAINER)

    def _assign_rematch_suggestion(self, data: tuple[int, int]) -> None:
        """Assign a suggested face to a person."""
        face_id, person_id = data
        self.db.assign_face_to_person(face_id, person_id)
        self.db.update_person_photo_count(person_id)
        self._rematch_suggestions = [
            s for s in self._rematch_suggestions if s[2].id != face_id
        ]
        self._render_rematch_suggestions()
        self._pending_stats_refresh = True

    def _skip_rematch_suggestion(self, face_id: int) -> None:
        """Skip a suggested face (remove from list without assigning)."""
        self._rematch_suggestions = [
            s for s in self._rematch_suggestions if s[2].id != face_id
        ]
        self._render_rematch_suggestions()

    def _close_rematch_dialog(self) -> None:
        """Close the rematch results dialog and refresh."""
        dpg.configure_item(self.TAG_REMATCH_DIALOG, show=False)
        self._rematch_suggestions = []
        self._load_clusters_from_db(render=True)
        self._update_stats()
        if self._current_view == "people":
            self._refresh_people_list()

    # ------------------------------------------------------------------
    # Context menus
    # ------------------------------------------------------------------

    def _create_context_menus(self) -> None:
        """Create right-click context menu popup windows."""
        # Cluster context menu (cluster header right-click)
        with dpg.window(
            tag=self.TAG_CLUSTER_CONTEXT_MENU,
            show=False,
            no_title_bar=True,
            no_resize=True,
            no_move=True,
            no_scrollbar=True,
            autosize=True,
        ):
            dpg.add_selectable(label="View All Faces", callback=self._ctx_cluster_view_all)
            dpg.add_selectable(label="Name This Person", callback=self._ctx_cluster_assign)
            dpg.add_separator()
            dpg.add_selectable(label="Split Cluster", callback=self._ctx_cluster_split)
            dpg.add_selectable(label="Ignore Cluster", callback=self._ctx_cluster_ignore)

        # People table context menu (people row right-click)
        with dpg.window(
            tag=self.TAG_PEOPLE_CONTEXT_MENU,
            show=False,
            no_title_bar=True,
            no_resize=True,
            no_move=True,
            no_scrollbar=True,
            autosize=True,
        ):
            dpg.add_selectable(label="View Photo Gallery", callback=self._ctx_person_gallery)
            dpg.add_selectable(label="View Timeline", callback=self._ctx_person_timeline)
            dpg.add_selectable(label="Review Chain Links", callback=self._ctx_person_review_chain)
            dpg.add_separator()
            dpg.add_selectable(label="Add Relationship", callback=self._ctx_person_add_relationship)
            dpg.add_selectable(label="Suggest Relationships", callback=self._ctx_person_suggest_relationships)
            dpg.add_separator()
            dpg.add_selectable(label="Edit Person", callback=self._ctx_person_edit)
            dpg.add_selectable(label="Find More Photos", callback=self._ctx_person_find_more)
            dpg.add_separator()
            dpg.add_selectable(label="Delete Person", callback=self._ctx_person_delete)

        # Gallery photo context menu (photo card right-click)
        with dpg.window(
            tag=self.TAG_GALLERY_CONTEXT_MENU,
            show=False,
            no_title_bar=True,
            no_resize=True,
            no_move=True,
            no_scrollbar=True,
            autosize=True,
        ):
            dpg.add_selectable(label="View Photo", callback=self._ctx_gallery_preview)
            dpg.add_selectable(label="Open File", callback=self._ctx_gallery_open)
            dpg.add_selectable(label="Show in Explorer", callback=self._ctx_gallery_explorer)
            dpg.add_separator()
            dpg.add_selectable(label="Remove from Person", callback=self._ctx_gallery_unassign)
            dpg.add_selectable(label="Copy Path", callback=self._ctx_gallery_copy_path)

        # Dismiss handler
        with dpg.handler_registry():
            dpg.add_mouse_click_handler(callback=self._on_dismiss_context_menu)

    def _show_cluster_context_menu(self, sender=None, app_data=None, user_data=None) -> None:
        """Show cluster context menu on right-click."""
        if user_data is not None:
            self._ctx_cluster_id, self._ctx_cluster_face_ids = user_data
        mouse_pos = dpg.get_mouse_pos(local=False)
        dpg.configure_item(
            self.TAG_CLUSTER_CONTEXT_MENU,
            show=True,
            pos=[int(mouse_pos[0]), int(mouse_pos[1])],
        )
        dpg.configure_item(self.TAG_PEOPLE_CONTEXT_MENU, show=False)
        dpg.configure_item(self.TAG_GALLERY_CONTEXT_MENU, show=False)
        self._ctx_menu_shown = True
        self._ctx_menu_open_time = time.time()

    def _show_people_context_menu(self, sender=None, app_data=None, user_data=None) -> None:
        """Show people table context menu on right-click."""
        if user_data is not None:
            self._ctx_person_id = user_data
        mouse_pos = dpg.get_mouse_pos(local=False)
        dpg.configure_item(
            self.TAG_PEOPLE_CONTEXT_MENU,
            show=True,
            pos=[int(mouse_pos[0]), int(mouse_pos[1])],
        )
        dpg.configure_item(self.TAG_CLUSTER_CONTEXT_MENU, show=False)
        dpg.configure_item(self.TAG_GALLERY_CONTEXT_MENU, show=False)
        self._ctx_menu_shown = True
        self._ctx_menu_open_time = time.time()

    def _show_gallery_context_menu(self, sender=None, app_data=None, user_data=None) -> None:
        """Show gallery photo context menu on right-click."""
        if user_data is not None:
            self._ctx_face_id, self._ctx_file_id = user_data
            # Resolve file path
            file_record = self.db.get_file(self._ctx_file_id) if self._ctx_file_id else None
            self._ctx_file_path = file_record.path if file_record else None
        mouse_pos = dpg.get_mouse_pos(local=False)
        dpg.configure_item(
            self.TAG_GALLERY_CONTEXT_MENU,
            show=True,
            pos=[int(mouse_pos[0]), int(mouse_pos[1])],
        )
        dpg.configure_item(self.TAG_CLUSTER_CONTEXT_MENU, show=False)
        dpg.configure_item(self.TAG_PEOPLE_CONTEXT_MENU, show=False)
        self._ctx_menu_shown = True
        self._ctx_menu_open_time = time.time()

    def _hide_context_menus(self) -> None:
        """Hide all context menus."""
        dpg.configure_item(self.TAG_CLUSTER_CONTEXT_MENU, show=False)
        dpg.configure_item(self.TAG_PEOPLE_CONTEXT_MENU, show=False)
        dpg.configure_item(self.TAG_GALLERY_CONTEXT_MENU, show=False)
        self._ctx_menu_shown = False

    def _on_dismiss_context_menu(self, sender=None, app_data=None) -> None:
        """Hide context menus on left-click outside."""
        if not self._ctx_menu_shown:
            return
        if time.time() - self._ctx_menu_open_time < 0.15:
            return
        # Check if mouse is over any context menu
        for tag in (self.TAG_CLUSTER_CONTEXT_MENU, self.TAG_PEOPLE_CONTEXT_MENU, self.TAG_GALLERY_CONTEXT_MENU):
            if dpg.does_item_exist(tag) and dpg.is_item_hovered(tag):
                return
        self._hide_context_menus()

    # Cluster context menu callbacks

    def _ctx_cluster_view_all(self, sender=None, app_data=None) -> None:
        self._hide_context_menus()
        if self._ctx_cluster_id is not None:
            self._show_all_faces_dialog(self._ctx_cluster_id, self._ctx_cluster_face_ids)

    def _ctx_cluster_assign(self, sender=None, app_data=None) -> None:
        self._hide_context_menus()
        if self._ctx_cluster_id is not None:
            self._show_assign_dialog(self._ctx_cluster_id)

    def _ctx_cluster_split(self, sender=None, app_data=None) -> None:
        self._hide_context_menus()
        if self._ctx_cluster_id is not None:
            self._show_split_dialog(self._ctx_cluster_id)

    def _ctx_cluster_ignore(self, sender=None, app_data=None) -> None:
        self._hide_context_menus()
        if self._ctx_cluster_id is not None:
            self._ignore_cluster(self._ctx_cluster_id, self._ctx_cluster_face_ids)

    # People context menu callbacks

    def _ctx_person_gallery(self, sender=None, app_data=None) -> None:
        self._hide_context_menus()
        if self._ctx_person_id is not None:
            self._show_person_gallery(self._ctx_person_id)

    def _ctx_person_timeline(self, sender=None, app_data=None) -> None:
        self._hide_context_menus()
        if self._ctx_person_id is not None:
            self._show_timeline(self._ctx_person_id)

    def _ctx_person_review_chain(self, sender=None, app_data=None) -> None:
        self._hide_context_menus()
        if self._ctx_person_id is not None:
            self._show_cross_age_dialog(self._ctx_person_id)

    def _ctx_person_edit(self, sender=None, app_data=None) -> None:
        self._hide_context_menus()
        if self._ctx_person_id is not None:
            self._show_edit_person_dialog(self._ctx_person_id)

    def _ctx_person_find_more(self, sender=None, app_data=None) -> None:
        self._hide_context_menus()
        if self._ctx_person_id is not None:
            self._find_person_photos(self._ctx_person_id)

    def _ctx_person_delete(self, sender=None, app_data=None) -> None:
        self._hide_context_menus()
        if self._ctx_person_id is not None:
            self._show_delete_person_dialog(self._ctx_person_id)

    def _ctx_person_add_relationship(self, sender=None, app_data=None) -> None:
        self._hide_context_menus()
        if self._ctx_person_id is not None:
            self._show_add_relationship_dialog(self._ctx_person_id)

    def _ctx_person_suggest_relationships(self, sender=None, app_data=None) -> None:
        self._hide_context_menus()
        if self._ctx_person_id is not None:
            self._show_suggest_relationships_dialog(self._ctx_person_id)

    # Gallery photo context menu callbacks

    def _ctx_gallery_preview(self, sender=None, app_data=None) -> None:
        self._hide_context_menus()
        if self._ctx_face_id is not None:
            self._show_photo_preview(self._ctx_face_id)

    def _ctx_gallery_open(self, sender=None, app_data=None) -> None:
        self._hide_context_menus()
        if self._ctx_file_id is not None:
            self._open_file_by_id(self._ctx_file_id)

    def _ctx_gallery_explorer(self, sender=None, app_data=None) -> None:
        self._hide_context_menus()
        if self._ctx_file_path:
            try:
                subprocess.run(
                    ["explorer", "/select,", self._ctx_file_path],
                    check=False,
                )
            except Exception as e:
                logger.error(f"Failed to show in explorer: {e}")

    def _ctx_gallery_unassign(self, sender=None, app_data=None) -> None:
        self._hide_context_menus()
        if self._ctx_face_id is not None:
            self._unassign_person_photo(self._ctx_face_id)

    def _ctx_gallery_copy_path(self, sender=None, app_data=None) -> None:
        self._hide_context_menus()
        if not self._ctx_file_path:
            return
        try:
            subprocess.run(["clip"], input=self._ctx_file_path.encode(), check=True)
            self._notify_status("Path copied to clipboard.")
        except Exception as e:
            logger.error(f"Failed to copy path: {e}")

    def cleanup(self) -> None:
        """Clean up resources before panel destruction."""
        # Clean up context menu handler registries
        for reg_list in (self._cluster_handler_registries, self._people_row_handler_registries, self._gallery_card_handler_registries):
            for reg in reg_list:
                try:
                    if dpg.does_item_exist(reg):
                        dpg.delete_item(reg)
                except Exception:
                    pass
            reg_list.clear()

        # Stop auto-refresh thread
        self._stop_auto_refresh(force=True)

        # Cancel any running analysis
        if self._face_analyzer:
            self._face_analyzer.cancel()
        if self._pet_analyzer:
            self._pet_analyzer.cancel()

        # Wait for analysis thread to finish
        if self._analysis_thread and self._analysis_thread.is_alive():
            self._analysis_thread.join(timeout=3.0)
            self._analysis_thread = None

        # Clear analysis state
        self._is_analyzing = False
        self._is_clustering = False
        self._background_face_analysis = False

        # Clean up face textures
        for tex_tag in list(self._face_textures.values()):
            try:
                if dpg.does_item_exist(tex_tag):
                    dpg.delete_item(tex_tag)
            except Exception:
                pass
        self._face_textures.clear()

        # Clean up gallery photo textures
        for tex_tag in list(self._gallery_photo_textures.values()):
            try:
                if dpg.does_item_exist(tex_tag):
                    dpg.delete_item(tex_tag)
            except Exception:
                pass
        self._gallery_photo_textures.clear()

        # Clean up pet textures
        for tex_tag in list(self._pet_textures.values()):
            try:
                if dpg.does_item_exist(tex_tag):
                    dpg.delete_item(tex_tag)
            except Exception:
                pass
        self._pet_textures.clear()

        self._texture_worker_stop.set()
        for thread in self._texture_worker_threads:
            if thread and thread.is_alive():
                thread.join(timeout=1.0)
        self._texture_worker_threads = []

        # Clean up preview texture
        if self._preview_texture_tag and dpg.does_item_exist(self._preview_texture_tag):
            with contextlib.suppress(Exception):
                dpg.delete_item(self._preview_texture_tag)
            self._preview_texture_tag = None

        # Clean up photo preview texture
        if self._photo_preview_texture and dpg.does_item_exist(self._photo_preview_texture):
            with contextlib.suppress(Exception):
                dpg.delete_item(self._photo_preview_texture)
            self._photo_preview_texture = None

        # Clean up texture registry
        if dpg.does_item_exist(self.TAG_TEXTURE_REGISTRY):
            with contextlib.suppress(Exception):
                dpg.delete_item(self.TAG_TEXTURE_REGISTRY)

        logger.info("FacesPanel cleanup complete")

    # --- Export ---

    def _on_export_persons(self) -> None:
        """Export person roster and pet data to CSV."""
        from duplicleaner.utils.export_manager import (
            export_csv,
            format_size,
            get_default_export_dir,
            get_timestamped_filename,
        )

        persons = self.db.get_all_persons(include_hidden=True)
        if not persons:
            if self.on_status_update:
                self.on_status_update("No persons to export.")
            return

        export_dir = get_default_export_dir()
        filepath = export_dir / get_timestamped_filename("persons", "csv")

        rows = []
        for p in persons:
            faces = self.db.get_faces_for_person(p.id) if p.id else []
            file_paths = []
            for face in faces[:50]:  # Limit to prevent huge exports
                fr = self.db.get_file(face.file_id)
                if fr:
                    file_paths.append(fr.path)
            rows.append({
                "person_id": p.id,
                "name": p.name or "(unnamed)",
                "birth_year": p.birth_year or "",
                "estimated_age": p.estimated_age or "",
                "photo_count": p.photo_count,
                "is_favorite": p.is_favorite,
                "is_hidden": p.is_hidden,
                "identification_source": p.identification_source,
                "notes": p.notes or "",
                "sample_photos": "; ".join(file_paths[:5]),
            })

        count = export_csv(rows, filepath)
        msg = f"Exported {count} persons to {filepath}"
        logger.info(msg)
        if self.on_status_update:
            self.on_status_update(msg)
