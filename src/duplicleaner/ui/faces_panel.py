"""Faces and Pets Panel for DupliCleaner.

Dear PyGui UI component for face recognition and pet tracking.
"""

import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable, Optional

import dearpygui.dearpygui as dpg
import numpy as np
from PIL import Image, ImageOps

from duplicleaner.ai.faces import FaceAnalyzer, FaceCluster, FaceAnalysisProgress
from duplicleaner.ai.pets import PetAnalyzer, PetCluster, PetAnalysisProgress
from duplicleaner.db.database import get_database
from duplicleaner.db.models import Person, Pet, Face, PetDetection
from duplicleaner.utils.config import get_config, save_config
from duplicleaner.utils.logging import get_logger
from duplicleaner.ui.theme import get_status_color, get_accent_color, get_text_color

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

    # Image extensions for preview
    IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff', '.tif', '.heic'}

    # Thumbnail sizes
    GALLERY_THUMB_SIZE = 120
    PHOTO_PREVIEW_SIZE = 550

    def __init__(
        self,
        parent: int | str,
        on_photo_selected: Optional[Callable[[int], None]] = None,
        on_status_update: Optional[Callable[[str], None]] = None,
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
        self._face_analyzer: Optional[FaceAnalyzer] = None
        self._pet_analyzer: Optional[PetAnalyzer] = None
        self._analyzer_lock = threading.Lock()

        # Current state
        self._face_clusters: list[FaceCluster] = []
        self._pet_clusters: list[PetCluster] = []
        self._selected_cluster_id: Optional[int] = None
        self._selected_cluster_snapshot: Optional[FaceCluster] = None
        self._selected_person_id: Optional[int] = None
        self._selected_pet_id: Optional[int] = None
        self._current_view = "clusters"  # clusters, people, pets
        self._assign_person_map: list[tuple[str, int]] = []
        self._assign_mode: str = "cluster"
        self._name_mode: str = "cluster"
        self._drive_scope_map: list[tuple[str, Optional[str]]] = []

        # Analysis thread
        self._analysis_thread: Optional[threading.Thread] = None
        self._is_analyzing = False
        self._background_face_analysis = False
        self._auto_refresh_active = False
        self._auto_refresh_thread: Optional[threading.Thread] = None
        self._is_clustering = False
        self._last_face_count = 0
        self._last_unassigned_faces = 0
        self._last_cluster_time = 0.0
        self._auto_refresh_interval = 6.0
        self._auto_cluster_interval = 20.0
        self._pause_auto_refresh = False

        # Thumbnail cache
        self._face_textures: dict[str, str] = {}
        self._texture_counter = 0
        self._preview_texture_tag: Optional[str] = None
        self._preview_file_id: Optional[int] = None
        self._preview_face_id: Optional[int] = None
        self._preview_bbox: Optional[tuple[int, int, int, int]] = None
        self._preview_scale: float = 1.0
        self._preview_display_size: tuple[int, int] = (1, 1)
        self._preview_orientation: int = 1
        self._preview_raw_size: tuple[int, int] = (1, 1)
        self._preview_dragging = False
        self._preview_drag_offset: tuple[float, float] = (0.0, 0.0)
        self._preview_resize_handle: Optional[str] = None
        self._preview_resize_start: tuple[float, float] = (0.0, 0.0)
        self._preview_bbox_start: Optional[tuple[int, int, int, int]] = None
        self._split_cluster_id: Optional[int] = None
        self._split_face_ids: list[int] = []
        self._split_selected: set[int] = set()
        self._cluster_run_id: Optional[int] = None

        # New state for Phase 1-3 features
        self._pending_reset_mode: Optional[str] = None
        self._pending_reset_scope: Optional[str] = None
        self._pending_reset_drive_id: Optional[str] = None
        self._edit_person_id: Optional[int] = None
        self._delete_person_id: Optional[int] = None
        self._show_hidden_people: bool = False
        self._people_search_filter: str = ""

        # Person gallery state
        self._gallery_person_id: Optional[int] = None
        self._gallery_faces: list = []
        self._gallery_sort: str = "date_desc"
        self._gallery_photo_textures: dict[str, str] = {}
        self._gallery_texture_counter: int = 0
        self._photo_preview_texture: Optional[str] = None
        self._photo_preview_file_path: Optional[str] = None
        self._photo_preview_face_id: Optional[int] = None

        # Build UI
        self._build_ui()

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
                    self._pet_analyzer = PetAnalyzer(self.db)
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
                dpg.add_button(label="Refresh", callback=self._refresh)
                dpg.add_text("", tag=self.TAG_FACE_ANALYSIS_STATUS, color=get_status_color("warning"))

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
        self._load_clusters_from_db()

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

        dpg.add_spacer(height=10)

        # Cluster view (default)
        with dpg.child_window(tag=self.TAG_CLUSTER_VIEW, height=400, border=True):
            dpg.add_text("Face Clusters", color=get_accent_color())
            dpg.add_separator()
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
        # Name person dialog
        with dpg.window(
            label="Name This Person",
            tag=self.TAG_NAME_DIALOG,
            modal=True,
            show=False,
            width=500,
            height=350,
            no_resize=True,
            pos=[180, 120],
        ):
            dpg.add_text("Sample faces from this cluster:")
            with dpg.group(horizontal=True, tag=self.TAG_NAME_DIALOG_FACES):
                # Face thumbnails will be populated dynamically
                pass
            dpg.add_spacer(height=10)
            dpg.add_text("Enter a name for this person:")
            dpg.add_input_text(tag="person_name_input", width=400)
            dpg.add_spacer(height=10)
            dpg.add_checkbox(label="Enable age tracking (for children)", tag="enable_age_tracking")
            dpg.add_text("Birth year (approximate):")
            dpg.add_input_int(tag="birth_year_input", default_value=2000, width=100)
            dpg.add_spacer(height=20)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Save", callback=self._save_person_name)
                dpg.add_button(label="Cancel", callback=self._cancel_person_naming)

        # Assign cluster to existing person dialog
        with dpg.window(
            label="Assign to Existing Person",
            tag=self.TAG_ASSIGN_DIALOG,
            modal=True,
            show=False,
            width=400,
            height=240,
            no_resize=True,
            pos=[220, 160],
        ):
            dpg.add_text("Assign this cluster to:")
            dpg.add_listbox(tag=self.TAG_ASSIGN_LIST, items=[], num_items=6, width=300)
            dpg.add_spacer(height=10)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Assign", callback=self._assign_cluster_to_person)
                dpg.add_button(label="Cancel", callback=self._cancel_assign_dialog)

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

        # Timeline dialog
        with dpg.window(
            label="Age Timeline",
            tag=self.TAG_TIMELINE_DIALOG,
            modal=True,
            show=False,
            width=700,
            height=500,
            pos=[100, 100],
        ):
            dpg.add_text("", tag="timeline_title")
            dpg.add_separator()
            dpg.add_spacer(height=10)

            # Timeline will be populated dynamically
            with dpg.child_window(tag="timeline_content", height=400, border=False):
                pass

            with dpg.group(horizontal=True):
                dpg.add_button(label="Close", callback=lambda: dpg.configure_item(self.TAG_TIMELINE_DIALOG, show=False))
                dpg.add_button(label="Find More Photos", callback=self._find_more_photos)

        # Face preview dialog
        with dpg.window(
            label="Face Preview",
            tag=self.TAG_FACE_PREVIEW_DIALOG,
            modal=True,
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
                dpg.add_mouse_drag_handler(callback=self._on_preview_mouse_drag)
                dpg.add_mouse_release_handler(callback=self._on_preview_mouse_up)

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
                    items=["Date (Newest)", "Date (Oldest)", "File Name"],
                    default_value="Date (Newest)",
                    width=140,
                    callback=self._on_gallery_sort_change,
                )
                dpg.add_spacer(width=20)
                dpg.add_button(label="Select All", callback=self._gallery_select_all, small=True)
                dpg.add_button(label="Open Selected", callback=self._gallery_open_selected, small=True)

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
            modal=True,
            show=False,
            width=700,
            height=680,
            pos=[150, 60],
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
                dpg.add_button(label="Remove from Person", callback=self._photo_preview_remove, width=130)
                dpg.add_spacer(width=150)
                dpg.add_button(label="Close", callback=self._close_photo_preview, width=80)

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
            unassigned_pets = len(self.db.get_unassigned_pet_detections(limit=1000))

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
            self._current_view = "clusters"
        else:
            dpg.configure_item(self.TAG_CLUSTER_VIEW, show=False)
            dpg.configure_item(self.TAG_PEOPLE_VIEW, show=True)
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

    def _set_analysis_buttons_enabled(self, enabled: bool) -> None:
        """Enable or disable analysis action buttons during operations."""
        buttons = [
            self.TAG_RUN_FACE_BUTTON,
            "run_pet_analysis_btn",
            "cluster_faces_btn",
            "cluster_pets_btn",
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

        # Get image files
        files = self.db.get_files_by_type([".jpg", ".jpeg", ".png", ".heic", ".webp"])
        if not files:
            logger.info("No image files to analyze")
            self._notify_status("No image files to analyze.", level="warning")
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

        files = self.db.get_files_by_type([".jpg", ".jpeg", ".png", ".heic", ".webp"])
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
        try:
            self._is_clustering = True
            clusters = self.face_analyzer.cluster_faces()
            run_id = self.db.create_face_cluster_run(method="auto")
            cluster_face_ids = [c.face_ids for c in clusters]
            self.db.save_face_clusters(run_id, cluster_face_ids, method="auto")
            self._cluster_run_id = run_id
            self._load_clusters_from_db()
            self._update_stats()
        except Exception as e:
            logger.error(f"Face clustering error: {e}")
        finally:
            self._is_clustering = False

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
        # Clear existing
        for child in dpg.get_item_children("face_clusters_container", 1):
            dpg.delete_item(child)

        if not self._face_clusters:
            dpg.configure_item("cluster_placeholder", show=True)
            return

        dpg.configure_item("cluster_placeholder", show=False)

        for cluster in self._face_clusters:
            with dpg.group(parent="face_clusters_container", horizontal=False):
                with dpg.group(horizontal=True):
                    dpg.add_text(f"Cluster {cluster.cluster_id + 1}: {len(cluster.face_ids)} photos")
                    dpg.add_button(
                        label="Name Person",
                        callback=lambda s, a, u: self._show_name_dialog(u),
                        user_data=cluster.cluster_id,
                        small=True,
                    )
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
                                tex_tag = self._get_face_texture(face)
                                if tex_tag:
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

                dpg.add_separator()

    def _show_name_dialog(self, cluster_id: int) -> None:
        """Show dialog to name a person from cluster."""
        cluster = next((c for c in self._face_clusters if c.cluster_id == cluster_id), None)
        if not cluster:
            self._notify_status("Cluster not found (refreshing).", level="warning")
            self._refresh()
            return
        self._name_mode = "cluster"
        self._selected_cluster_id = cluster_id
        self._selected_cluster_snapshot = cluster
        self._pause_auto_refresh = True
        self._stop_auto_refresh()
        dpg.set_value("person_name_input", "")
        dpg.set_value("enable_age_tracking", False)
        dpg.set_value("birth_year_input", 2000)

        # Populate face thumbnails (up to 6)
        self._populate_name_dialog_faces(cluster.sample_faces[:6] if cluster.sample_faces else [])

        dpg.configure_item(self.TAG_NAME_DIALOG, show=True)

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
        if not self._split_selected:
            self._notify_status("Select faces to name first.", level="warning")
            return
        self._name_mode = "split"
        self._pause_auto_refresh = True
        self._stop_auto_refresh()
        dpg.set_value("person_name_input", "")
        dpg.set_value("enable_age_tracking", False)
        dpg.set_value("birth_year_input", 2000)
        dpg.configure_item(self.TAG_NAME_DIALOG, show=True)

    def _show_assign_dialog(self, cluster_id: int) -> None:
        """Show dialog to assign a cluster to an existing person."""
        cluster = next((c for c in self._face_clusters if c.cluster_id == cluster_id), None)
        if not cluster:
            self._notify_status("Cluster not found (refreshing).", level="warning")
            self._refresh()
            return
        self._assign_mode = "cluster"
        persons = self.db.get_all_persons(named_only=True)
        self._assign_person_map = [(p.name or f"Person {p.id}", p.id) for p in persons if p.id is not None]
        if not self._assign_person_map:
            self._notify_status("No named people yet. Name a person first.", level="warning")
            return
        dpg.configure_item(self.TAG_ASSIGN_LIST, items=[name for name, _ in self._assign_person_map])
        dpg.set_value(self.TAG_ASSIGN_LIST, self._assign_person_map[0][0])
        self._selected_cluster_id = cluster_id
        self._selected_cluster_snapshot = cluster
        self._pause_auto_refresh = True
        self._stop_auto_refresh()
        dpg.configure_item(self.TAG_ASSIGN_DIALOG, show=True)

    def _show_assign_dialog_for_split(self) -> None:
        """Show dialog to assign split selection to an existing person."""
        if not self._split_selected:
            self._notify_status("Select faces to assign first.", level="warning")
            return
        self._assign_mode = "split"
        persons = self.db.get_all_persons(named_only=True)
        self._assign_person_map = [(p.name or f"Person {p.id}", p.id) for p in persons if p.id is not None]
        if not self._assign_person_map:
            self._notify_status("No named people yet. Name a person first.", level="warning")
            return
        dpg.configure_item(self.TAG_ASSIGN_LIST, items=[name for name, _ in self._assign_person_map])
        dpg.set_value(self.TAG_ASSIGN_LIST, self._assign_person_map[0][0])
        self._pause_auto_refresh = True
        self._stop_auto_refresh()
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
        dpg.configure_item(self.TAG_NAME_DIALOG, show=False)

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
            self._update_stats()
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
        self._update_stats()
        threading.Thread(target=self._auto_refine_matches, daemon=True).start()
        self._resume_auto_refresh()

    def _cancel_assign_dialog(self) -> None:
        """Cancel assigning a cluster to a person."""
        dpg.configure_item(self.TAG_ASSIGN_DIALOG, show=False)
        self._resume_auto_refresh()

    def _cancel_person_naming(self) -> None:
        """Cancel naming a person."""
        dpg.configure_item(self.TAG_NAME_DIALOG, show=False)
        self._resume_auto_refresh()

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
                # Name (dimmed if hidden)
                name_color = (120, 120, 120) if is_hidden else (255, 255, 255)
                dpg.add_text(person.name or "Unknown", color=name_color)
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

    def _refresh_pets_list(self) -> None:
        """Refresh the pets list view."""
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

    def _open_file_by_id(self, file_id: int) -> None:
        """Open a file using the OS default handler."""
        file_record = self.db.get_file(file_id)
        if not file_record or not file_record.path:
            self._notify_status("File not found for preview.", level="warning")
            return
        try:
            os.startfile(file_record.path)
        except Exception:
            self._notify_status("Failed to open file.", level="warning")

    def _show_timeline(self, person_id: int) -> None:
        """Show age timeline for a person with photo thumbnails."""
        self._selected_person_id = person_id
        self._gallery_person_id = person_id  # For gallery integration
        person = self.db.get_person(person_id)
        if not person:
            return

        dpg.set_value("timeline_title", f"Timeline: {person.name}")

        # Clear existing content
        for child in dpg.get_item_children("timeline_content", 1):
            dpg.delete_item(child)

        # Get timeline
        timeline = self.face_analyzer.get_person_timeline(person_id)

        if not timeline:
            dpg.add_text(
                "No photos found with date information.",
                parent="timeline_content",
                color=get_text_color("disabled")
            )
            dpg.configure_item(self.TAG_TIMELINE_DIALOG, show=True)
            return

        for year, faces in timeline:
            with dpg.group(parent="timeline_content", horizontal=False):
                # Year header with age and count
                age = year - person.birth_year if person.birth_year else None
                age_text = f" (Age ~{age})" if age is not None else ""
                dpg.add_text(f"{year}{age_text} - {len(faces)} photos", color=get_accent_color())
                dpg.add_separator()
                dpg.add_spacer(height=5)

                # Photo thumbnails for this year (max 8 per row, show up to 24)
                row_group = None
                photos_per_row = 8
                max_photos = 24

                for i, face in enumerate(faces[:max_photos]):
                    if i % photos_per_row == 0:
                        row_group = dpg.add_group(horizontal=True, parent="timeline_content")
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

                # Show overflow indicator
                if len(faces) > max_photos:
                    overflow_count = len(faces) - max_photos
                    dpg.add_text(
                        f"  +{overflow_count} more photos",
                        parent="timeline_content",
                        color=get_text_color("disabled")
                    )

                dpg.add_spacer(height=15)

        dpg.configure_item(self.TAG_TIMELINE_DIALOG, show=True)

    def _show_pet_timeline(self, pet_id: int) -> None:
        """Show timeline for a pet."""
        self._selected_pet_id = pet_id
        pet = self.db.get_pet(pet_id)
        if not pet:
            return

        dpg.set_value("timeline_title", f"Timeline: {pet.name} ({pet.species})")

        for child in dpg.get_item_children("timeline_content", 1):
            dpg.delete_item(child)

        timeline = self.pet_analyzer.get_pet_timeline(pet_id)

        for year, detections in timeline:
            with dpg.group(parent="timeline_content", horizontal=False):
                dpg.add_text(f"{year}: {len(detections)} photos", color=get_accent_color())

        dpg.configure_item(self.TAG_TIMELINE_DIALOG, show=True)

    def _find_more_photos(self) -> None:
        """Find more photos for selected person/pet."""
        if self._selected_person_id:
            self._find_person_photos(self._selected_person_id)
        elif self._selected_pet_id:
            self._find_pet_photos(self._selected_pet_id)

    def _find_person_photos(self, person_id: int) -> None:
        """Find more photos of a specific person.

        Args:
            person_id: ID of the person to find more photos for
        """
        person = self.db.get_person(person_id)
        person_name = person.name if person else f"Person {person_id}"

        self._notify_status(f"Searching for more photos of {person_name}...")

        try:
            matches, assigned = self.face_analyzer.find_more_faces_for_person(
                person_id=person_id,
                threshold=0.8,
                auto_assign=True
            )
            if assigned > 0:
                self._notify_status(f"Found {assigned} new photos of {person_name}")
            else:
                self._notify_status(f"No new photos found for {person_name}")
            logger.info(f"Find more for {person_name}: {matches} matches, {assigned} assigned")
            self._update_stats()
            self._refresh_people_list()
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
                threshold=0.75,
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

    def _refresh(self) -> None:
        """Refresh all views."""
        self._refresh_drive_scopes()
        self._update_stats()
        if self._current_view == "people":
            self._refresh_people_list()
        self._display_face_clusters()
        self._display_pet_clusters()

    def refresh(self) -> None:
        """Public method to refresh the panel."""
        self._refresh()

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
            try:
                self._refresh_stats_and_clusters()
            except Exception:
                pass
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
                self._update_stats()
                if self._current_view == "clusters":
                    now = time.time()
                    if not self._is_clustering and (now - self._last_cluster_time) >= self._auto_cluster_interval:
                        self._last_cluster_time = now
                        threading.Thread(target=self._on_cluster_faces, daemon=True).start()
        except Exception:
            pass

    def _resume_auto_refresh(self) -> None:
        self._pause_auto_refresh = False
        if self._background_face_analysis or self._is_analyzing:
            self._start_auto_refresh()

    def _get_face_texture(self, face: Face) -> Optional[str]:
        if face.file_id is None:
            return None
        key = f"{face.file_id}:{face.bbox_x}:{face.bbox_y}:{face.bbox_w}:{face.bbox_h}"
        if key in self._face_textures:
            return self._face_textures[key]
        file_record = self.db.get_file(face.file_id)
        if not file_record or not file_record.path:
            return None
        tex_tag = self._create_face_texture(file_record.path, face)
        if tex_tag:
            self._face_textures[key] = tex_tag
            self._prune_textures(limit=200)
        return tex_tag

    def _create_face_texture(self, image_path: str, face: Face) -> Optional[str]:
        try:
            raw_image = Image.open(image_path)
            orientation = int(raw_image.getexif().get(274, 1))
            raw_w, raw_h = raw_image.size
            image = ImageOps.exif_transpose(raw_image).convert("RGB")
            width, height = image.size

            obox = self._apply_orientation_to_bbox_with_size(
                (face.bbox_x, face.bbox_y, face.bbox_w, face.bbox_h),
                orientation,
                raw_w,
                raw_h,
            )
            if not obox:
                return None
            x, y, bw, bh = obox
            left = max(0, int(x))
            top = max(0, int(y))
            right = min(width, int(x + bw))
            bottom = min(height, int(y + bh))
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
        except Exception:
            return None

    def _prune_textures(self, limit: int = 200) -> None:
        if len(self._face_textures) <= limit:
            return
        to_remove = list(self._face_textures.items())[: len(self._face_textures) - limit]
        for key, tex_tag in to_remove:
            try:
                dpg.delete_item(tex_tag)
            except Exception:
                pass
            self._face_textures.pop(key, None)

    def _compute_face_similarity(self, face: Face, cluster: FaceCluster) -> Optional[float]:
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
            if self._preview_texture_tag and dpg.does_item_exist(self._preview_texture_tag):
                if self._preview_texture_tag.startswith("face_preview_tex_"):
                    try:
                        dpg.delete_item(self._preview_texture_tag)
                    except Exception:
                        pass
            self._preview_texture_tag = new_tex
            self._preview_file_id = file_record.id
            self._preview_face_id = face.id
            self._preview_bbox = (face.bbox_x, face.bbox_y, face.bbox_w, face.bbox_h)
            dpg.set_value(self.TAG_FACE_PREVIEW_TEXT, file_record.path)
            self._render_face_preview()
            dpg.configure_item(self.TAG_FACE_PREVIEW_DIALOG, show=True)
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
            self._update_stats()
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

    def _load_clusters_from_db(self) -> None:
        """Load latest clusters from the database."""
        latest = self.db.get_latest_face_cluster_run()
        if not latest:
            return
        run_id, _method = latest
        self._cluster_run_id = run_id
        clusters = []
        for cluster_id, face_ids in self.db.get_face_clusters_for_run(run_id):
            faces = self.db.get_faces_by_ids(face_ids)
            if not faces:
                continue
            sample_faces = faces[:5]
            embeddings = []
            for face in faces:
                if face.embedding:
                    embeddings.append(np.frombuffer(face.embedding, dtype=np.float32))
            avg_embedding = np.mean(embeddings, axis=0) if embeddings else None
            clusters.append(
                FaceCluster(
                    cluster_id=cluster_id,
                    face_ids=face_ids,
                    sample_faces=sample_faces,
                    avg_embedding=avg_embedding,
                )
            )
        self._face_clusters = clusters
        self._display_face_clusters()

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
    # Ignore/Hidden Person Methods
    # =========================================================================

    def _ignore_cluster(self, cluster_id: int, face_ids: list[int]) -> None:
        """Create a hidden person from a cluster (ignore unknown faces)."""
        if not face_ids:
            return

        person_id = self.db.create_hidden_person_from_cluster(face_ids)
        person = self.db.get_person(person_id)
        name = person.name if person else f"Unknown #{person_id}"

        self._notify_status(f"Ignored cluster as '{name}'.", level="info")
        self._refresh()

    def _on_show_hidden_change(self, sender, app_data, user_data) -> None:
        """Toggle visibility of hidden people."""
        self._show_hidden_people = app_data
        self._refresh_people_list()

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

        # Build info text
        photo_count = len(faces)
        if person.birth_year:
            age = person.estimated_age or 0
            info = f"{photo_count} photos | Age ~{age} | Born ~{person.birth_year}"
        else:
            info = f"{photo_count} photos"
        dpg.set_value(self.TAG_PERSON_GALLERY_INFO, info)

        # Reset sort to default
        dpg.set_value(self.TAG_PERSON_GALLERY_SORT, "Date (Newest)")
        self._gallery_sort = "date_desc"

        # Render the gallery
        self._render_person_gallery()

        dpg.configure_item(self.TAG_PERSON_GALLERY_DIALOG, show=True)

    def _show_pet_gallery(self, pet_id: int) -> None:
        """Show photo gallery for a pet."""
        pet = self.db.get_pet(pet_id)
        if not pet:
            self._notify_status("Pet not found.", level="warning")
            return

        # For now, redirect to timeline - pet gallery can be similar implementation
        self._show_pet_timeline(pet_id)

    def _render_person_gallery(self) -> None:
        """Render the photo grid in the gallery dialog."""
        if not dpg.does_item_exist(self.TAG_PERSON_GALLERY_CONTAINER):
            return

        # Clear existing content
        for child in dpg.get_item_children(self.TAG_PERSON_GALLERY_CONTAINER, 1) or []:
            dpg.delete_item(child)

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
                row_group = dpg.add_group(
                    horizontal=True,
                    parent=self.TAG_PERSON_GALLERY_CONTAINER
                )
                dpg.add_spacer(width=5, parent=row_group)

            self._render_gallery_photo_card(face, row_group)

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
        return faces

    def _get_face_photo_date(self, face: Face) -> Optional[str]:
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

    def _render_gallery_photo_card(self, face: Face, parent) -> None:
        """Render a single photo card in the gallery."""
        # Get file info
        file_record = self.db.get_file(face.file_id) if face.file_id else None
        if not file_record:
            return

        # Create card container
        with dpg.group(parent=parent):
            # Try to get thumbnail
            thumb = self._get_face_thumbnail(face)
            if thumb:
                dpg.add_image_button(
                    thumb,
                    width=self.GALLERY_THUMB_SIZE,
                    height=self.GALLERY_THUMB_SIZE,
                    user_data=face.id,
                    callback=lambda s, a, u: self._on_gallery_photo_click(u),
                )
            else:
                # Fallback button without image
                dpg.add_button(
                    label="[Photo]",
                    width=self.GALLERY_THUMB_SIZE,
                    height=self.GALLERY_THUMB_SIZE,
                    user_data=face.id,
                    callback=lambda s, a, u: self._on_gallery_photo_click(u),
                )

            # Filename label (truncated)
            filename = file_record.filename or "Unknown"
            display_name = filename[:14] + "..." if len(filename) > 14 else filename
            dpg.add_text(display_name, color=get_text_color("secondary"))

            # Date label
            if file_record.modified:
                date_str = file_record.modified.strftime("%Y-%m-%d")
                dpg.add_text(date_str, color=get_text_color("disabled"))

            dpg.add_spacer(height=8)

    def _on_gallery_photo_click(self, face_id: int) -> None:
        """Handle click on a photo in the gallery."""
        self._show_photo_preview(face_id)

    def _on_gallery_sort_change(self, sender, app_data, user_data) -> None:
        """Handle sort dropdown change in gallery."""
        if app_data == "Date (Newest)":
            self._gallery_sort = "date_desc"
        elif app_data == "Date (Oldest)":
            self._gallery_sort = "date_asc"
        elif app_data == "File Name":
            self._gallery_sort = "name"

        self._render_person_gallery()

    def _gallery_select_all(self) -> None:
        """Select all photos in the gallery (placeholder)."""
        self._notify_status(f"Selected all {len(self._gallery_faces)} photos.", level="info")

    def _gallery_open_selected(self) -> None:
        """Open all selected photos (placeholder - opens first 5)."""
        for face in self._gallery_faces[:5]:
            if face.file_id:
                self._open_file_by_id(face.file_id)
        if len(self._gallery_faces) > 5:
            self._notify_status("Opened first 5 photos. Select specific photos to open more.", level="info")

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
        dpg.configure_item(self.TAG_PERSON_GALLERY_DIALOG, show=False)
        self._gallery_person_id = None
        self._gallery_faces = []

    # =========================================================================
    # Photo Preview Methods (for individual photos from gallery)
    # =========================================================================

    def _show_photo_preview(self, face_id: int) -> None:
        """Show preview dialog for a specific photo."""
        face = self.db.get_face(face_id)
        if not face or not face.file_id:
            self._notify_status("Photo not found.", level="warning")
            return

        file_record = self.db.get_file(face.file_id)
        if not file_record:
            self._notify_status("File not found.", level="warning")
            return

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

        dpg.configure_item(self.TAG_PHOTO_PREVIEW_DIALOG, show=True)

    def _render_photo_preview(self, file_path: str, face: Optional[Face] = None) -> None:
        """Render the preview image in the dialog."""
        if not dpg.does_item_exist(self.TAG_PHOTO_PREVIEW_CONTAINER):
            return

        # Clear existing content
        for child in dpg.get_item_children(self.TAG_PHOTO_PREVIEW_CONTAINER, 1) or []:
            dpg.delete_item(child)

        # Clean up previous texture
        if self._photo_preview_texture and dpg.does_item_exist(self._photo_preview_texture):
            try:
                dpg.delete_item(self._photo_preview_texture)
            except Exception:
                pass
            self._photo_preview_texture = None

        if not os.path.exists(file_path):
            dpg.add_text(
                "File not found on disk.",
                parent=self.TAG_PHOTO_PREVIEW_CONTAINER,
                color=get_status_color("error")
            )
            return

        # Load and display image
        try:
            img = Image.open(file_path)

            # Handle EXIF orientation
            try:
                img = ImageOps.exif_transpose(img)
            except Exception:
                pass

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

            # Add image to container
            dpg.add_image(texture_tag, parent=self.TAG_PHOTO_PREVIEW_CONTAINER)

            # Add path info
            dpg.add_spacer(height=10, parent=self.TAG_PHOTO_PREVIEW_CONTAINER)
            dpg.add_text(
                f"Path: {file_path}",
                parent=self.TAG_PHOTO_PREVIEW_CONTAINER,
                color=get_text_color("disabled"),
                wrap=650
            )

        except Exception as e:
            logger.error(f"Failed to load preview image: {e}")
            dpg.add_text(
                f"Failed to load image: {e}",
                parent=self.TAG_PHOTO_PREVIEW_CONTAINER,
                color=get_status_color("error")
            )

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

        self._notify_status("Photo removed from person. It will appear in Unknown Clusters.", level="info")

        # Close preview and refresh gallery
        self._close_photo_preview()
        if self._gallery_person_id:
            self._show_person_gallery(self._gallery_person_id)

    def _close_photo_preview(self) -> None:
        """Close the photo preview dialog."""
        dpg.configure_item(self.TAG_PHOTO_PREVIEW_DIALOG, show=False)

        # Clean up texture
        if self._photo_preview_texture and dpg.does_item_exist(self._photo_preview_texture):
            try:
                dpg.delete_item(self._photo_preview_texture)
            except Exception:
                pass
            self._photo_preview_texture = None

        self._photo_preview_face_id = None
        self._photo_preview_file_path = None

    # =========================================================================
    # View All Faces Methods
    # =========================================================================

    def _show_all_faces_dialog(self, cluster_id: int, face_ids: list[int]) -> None:
        """Show dialog with all faces from a cluster."""
        if not dpg.does_item_exist(self.TAG_ALL_FACES_CONTAINER):
            return

        # Clear existing
        for child in dpg.get_item_children(self.TAG_ALL_FACES_CONTAINER, 1) or []:
            dpg.delete_item(child)

        faces = self.db.get_faces_by_ids(face_ids[:200])
        if not faces:
            dpg.add_text("No faces found", parent=self.TAG_ALL_FACES_CONTAINER)
            dpg.configure_item(self.TAG_ALL_FACES_DIALOG, show=True)
            return

        # Render grid (10 per row, 72px thumbnails)
        row_group = None
        for i, face in enumerate(faces):
            if i % 10 == 0:
                row_group = dpg.add_group(horizontal=True, parent=self.TAG_ALL_FACES_CONTAINER)

            thumb = self._get_face_thumbnail(face)
            if thumb and row_group:
                btn = dpg.add_image_button(
                    thumb,
                    width=72,
                    height=72,
                    parent=row_group,
                    user_data=face.id,
                    callback=lambda s, a, u: self._on_face_preview_click(u),
                )

        dpg.configure_item(self.TAG_ALL_FACES_DIALOG, show=True)

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
            obox = self._apply_orientation_to_bbox(self._preview_bbox)
            if not obox:
                return
            x, y, bw, bh = obox
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
            # Resize handles (corners)
            handle_size = 10
            handles = [
                (px, py),
                (px + pw, py),
                (px, py + ph),
                (px + pw, py + ph),
            ]
            for hx, hy in handles:
                dpg.draw_rectangle(
                    (hx - handle_size - 1, hy - handle_size - 1),
                    (hx + handle_size + 1, hy + handle_size + 1),
                    color=(60, 60, 60, 255),
                    fill=(60, 60, 60, 255),
                    parent=self.TAG_FACE_PREVIEW_DRAW,
                )
                dpg.draw_rectangle(
                    (hx - handle_size, hy - handle_size),
                    (hx + handle_size, hy + handle_size),
                    color=(255, 200, 80, 255),
                    fill=(255, 200, 80, 255),
                    parent=self.TAG_FACE_PREVIEW_DRAW,
                )

    def _preview_local_pos(self) -> Optional[tuple[float, float]]:
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

    def _on_preview_mouse_down(self, sender, app_data, user_data) -> None:
        if not self._preview_bbox:
            return
        pos = self._preview_local_pos()
        if not pos:
            return
        obox = self._apply_orientation_to_bbox(self._preview_bbox)
        if not obox:
            return
        x, y, bw, bh = obox
        px = x * self._preview_scale
        py = y * self._preview_scale
        pw = bw * self._preview_scale
        ph = bh * self._preview_scale
        handle_size = 10
        hit_size = 16
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
                self._preview_bbox_start = (x, y, bw, bh)
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
            obox = self._apply_orientation_to_bbox(self._preview_bbox_start)
            if not obox:
                return
            x, y, bw, bh = obox
            px = x * self._preview_scale
            py = y * self._preview_scale
            pw = bw * self._preview_scale
            ph = bh * self._preview_scale
            dx = pos[0] - px
            dy = pos[1] - py
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
            self._preview_bbox = self._invert_orientation_from_bbox((new_x, new_y, new_w, new_h))
            self._render_face_preview()
            return
        if not self._preview_dragging:
            return
        dx, dy = self._preview_drag_offset
        new_px = max(0.0, pos[0] - dx)
        new_py = max(0.0, pos[1] - dy)
        disp_w, disp_h = self._preview_display_size
        obox = self._apply_orientation_to_bbox(self._preview_bbox)
        if not obox:
            return
        x, y, bw, bh = obox
        max_px = max(0.0, disp_w - bw * self._preview_scale)
        max_py = max(0.0, disp_h - bh * self._preview_scale)
        new_px = min(new_px, max_px)
        new_py = min(new_py, max_py)
        new_x = float(new_px / self._preview_scale)
        new_y = float(new_py / self._preview_scale)
        self._preview_bbox = self._invert_orientation_from_bbox((new_x, new_y, bw, bh))
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
    ) -> Optional[tuple[float, float, float, float]]:
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
    ) -> Optional[tuple[float, float, float, float]]:
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
            image = Image.open(file_record.path)
            raw_w, raw_h = image.size
            rotated = image.rotate(angle, expand=True)
            exif = image.getexif()
            if exif is not None:
                exif[274] = 1
            if exif is not None and len(exif):
                rotated.save(file_record.path, exif=exif.tobytes())
            else:
                rotated.save(file_record.path)

            # Update all face boxes for this file
            faces = self.db.get_faces_for_file(self._preview_file_id)
            for face in faces:
                if angle == 90:
                    # rotate left (CCW)
                    new_x = face.bbox_y
                    new_y = raw_w - (face.bbox_x + face.bbox_w)
                    new_w = face.bbox_h
                    new_h = face.bbox_w
                elif angle == -90:
                    # rotate right (CW)
                    new_x = raw_h - (face.bbox_y + face.bbox_h)
                    new_y = face.bbox_x
                    new_w = face.bbox_h
                    new_h = face.bbox_w
                else:
                    new_x = raw_w - (face.bbox_x + face.bbox_w)
                    new_y = raw_h - (face.bbox_y + face.bbox_h)
                    new_w = face.bbox_w
                    new_h = face.bbox_h
                self.db.update_face_bbox(face.id, int(new_x), int(new_y), int(new_w), int(new_h))

            # Reload preview
            self._show_face_preview(self._preview_face_id)
            self._refresh()
        except Exception:
            self._notify_status("Failed to rotate image.", level="warning")

    def cleanup(self) -> None:
        """Clean up resources before panel destruction."""
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

        # Clean up preview texture
        if self._preview_texture_tag and dpg.does_item_exist(self._preview_texture_tag):
            try:
                dpg.delete_item(self._preview_texture_tag)
            except Exception:
                pass
            self._preview_texture_tag = None

        # Clean up photo preview texture
        if self._photo_preview_texture and dpg.does_item_exist(self._photo_preview_texture):
            try:
                dpg.delete_item(self._photo_preview_texture)
            except Exception:
                pass
            self._photo_preview_texture = None

        # Clean up texture registry
        if dpg.does_item_exist(self.TAG_TEXTURE_REGISTRY):
            try:
                dpg.delete_item(self.TAG_TEXTURE_REGISTRY)
            except Exception:
                pass

        logger.info("FacesPanel cleanup complete")
