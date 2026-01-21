"""Faces and Pets Panel for DupliCleaner.

Dear PyGui UI component for face recognition and pet tracking.
"""

import os
import threading
from typing import Callable, Optional

import dearpygui.dearpygui as dpg

from duplicleaner.ai.faces import FaceAnalyzer, FaceCluster, FaceAnalysisProgress
from duplicleaner.ai.pets import PetAnalyzer, PetCluster, PetAnalysisProgress
from duplicleaner.db.database import get_database
from duplicleaner.db.models import Person, Pet, Face, PetDetection
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

        # Analyzers (created lazily)
        self._face_analyzer: Optional[FaceAnalyzer] = None
        self._pet_analyzer: Optional[PetAnalyzer] = None

        # Current state
        self._face_clusters: list[FaceCluster] = []
        self._pet_clusters: list[PetCluster] = []
        self._selected_cluster_id: Optional[int] = None
        self._selected_person_id: Optional[int] = None
        self._selected_pet_id: Optional[int] = None
        self._current_view = "clusters"  # clusters, people, pets

        # Analysis thread
        self._analysis_thread: Optional[threading.Thread] = None
        self._is_analyzing = False

        # Build UI
        self._build_ui()

    @property
    def face_analyzer(self) -> FaceAnalyzer:
        """Get or create face analyzer."""
        if self._face_analyzer is None:
            self._face_analyzer = FaceAnalyzer(self.db)
        return self._face_analyzer

    @property
    def pet_analyzer(self) -> PetAnalyzer:
        """Get or create pet analyzer."""
        if self._pet_analyzer is None:
            self._pet_analyzer = PetAnalyzer(self.db)
        return self._pet_analyzer

    def _build_ui(self) -> None:
        """Build the panel UI."""
        with dpg.child_window(parent=self.parent, tag=self.TAG_PANEL, autosize_x=True, autosize_y=True):
            # Header
            dpg.add_text("Faces & Pets", color=(150, 200, 255))
            dpg.add_separator()
            dpg.add_spacer(height=5)

            # Action buttons
            with dpg.group(horizontal=True):
                dpg.add_button(label="Run Face Analysis", callback=self._on_run_face_analysis)
                dpg.add_button(label="Run Pet Analysis", callback=self._on_run_pet_analysis)
                dpg.add_button(label="Cluster Faces", callback=self._on_cluster_faces)
                dpg.add_button(label="Cluster Pets", callback=self._on_cluster_pets)
                dpg.add_button(label="Refresh", callback=self._refresh)

            dpg.add_spacer(height=10)

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

        # Create dialogs
        self._create_dialogs()

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
            dpg.add_text("Face Clusters", color=(200, 200, 100))
            dpg.add_separator()
            dpg.add_text("No clusters found. Run 'Cluster Faces' to group similar faces.", tag="cluster_placeholder")

            # Clusters will be added dynamically
            with dpg.group(tag="face_clusters_container"):
                pass

        # People view (hidden initially)
        with dpg.child_window(tag=self.TAG_PEOPLE_VIEW, height=400, border=True, show=False):
            dpg.add_text("Named People", color=(200, 200, 100))
            dpg.add_separator()

            # People list
            with dpg.table(
                tag="people_table",
                header_row=True,
                borders_innerH=True,
                borders_outerH=True,
                resizable=True,
                policy=dpg.mvTable_SizingStretchProp,
                scrollY=True,
                height=350,
            ):
                dpg.add_table_column(label="Name", init_width_or_weight=150)
                dpg.add_table_column(label="Photos", init_width_or_weight=80)
                dpg.add_table_column(label="Age Range", init_width_or_weight=100)
                dpg.add_table_column(label="Actions", init_width_or_weight=150)

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
            dpg.add_text("Pet Clusters", color=(200, 200, 100))
            dpg.add_separator()
            dpg.add_text("No clusters found. Run 'Cluster Pets' to group similar pets.", tag="pet_cluster_placeholder")

            with dpg.group(tag="pet_clusters_container"):
                pass

        # Named pets view (hidden initially)
        with dpg.child_window(tag=self.TAG_PETS_VIEW, height=400, border=True, show=False):
            dpg.add_text("Named Pets", color=(200, 200, 100))
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
            width=400,
            height=250,
            no_resize=True,
            pos=[200, 150],
        ):
            dpg.add_text("Enter a name for this person:")
            dpg.add_input_text(tag="person_name_input", width=300)
            dpg.add_spacer(height=10)
            dpg.add_checkbox(label="Enable age tracking (for children)", tag="enable_age_tracking")
            dpg.add_text("Birth year (approximate):")
            dpg.add_input_int(tag="birth_year_input", default_value=2000, width=100)
            dpg.add_spacer(height=20)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Save", callback=self._save_person_name)
                dpg.add_button(label="Cancel", callback=lambda: dpg.configure_item(self.TAG_NAME_DIALOG, show=False))

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

    def _update_stats(self) -> None:
        """Update statistics display."""
        try:
            face_count = self.db.get_face_count()
            person_count = len(self.db.get_all_persons(named_only=True))
            unassigned_faces = len(self.db.get_unassigned_faces(limit=1000))

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

    def _on_run_face_analysis(self) -> None:
        """Start face analysis in background."""
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
        dpg.configure_item(self.TAG_PROGRESS_DIALOG, show=True)
        self._notify_status("Running face analysis...")

        def run_analysis():
            try:
                self.face_analyzer.set_progress_callback(self._update_progress)
                self.face_analyzer.analyze_batch(files)
            except Exception as e:
                logger.error(f"Face analysis error: {e}")
            finally:
                self._is_analyzing = False
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
                dpg.configure_item(self.TAG_PROGRESS_DIALOG, show=False)
                self._refresh()
                self._notify_status("Pet analysis complete.")

    def _notify_status(self, message: str, level: str = "info") -> None:
        """Send status update if callback provided."""
        if not self.on_status_update:
            return
        try:
            self.on_status_update(message, level=level)
        except TypeError:
            self.on_status_update(message)

        self._analysis_thread = threading.Thread(target=run_analysis, daemon=True)
        self._analysis_thread.start()

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
        try:
            self._face_clusters = self.face_analyzer.cluster_faces()
            self._display_face_clusters()
            self._update_stats()
        except Exception as e:
            logger.error(f"Face clustering error: {e}")

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
                        label="View Photos",
                        callback=lambda s, a, u: self._view_cluster_photos(u),
                        user_data=cluster.cluster_id,
                        small=True,
                    )

                # Show sample face info
                if cluster.sample_faces:
                    ages = [f.estimated_age for f in cluster.sample_faces if f.estimated_age]
                    if ages:
                        avg_age = sum(ages) / len(ages)
                        dpg.add_text(f"  Estimated age: ~{int(avg_age)} years", color=(150, 150, 150))

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
        self._selected_cluster_id = cluster_id
        dpg.set_value("person_name_input", "")
        dpg.set_value("enable_age_tracking", False)
        dpg.set_value("birth_year_input", 2000)
        dpg.configure_item(self.TAG_NAME_DIALOG, show=True)

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
            return

        enable_age = dpg.get_value("enable_age_tracking")
        birth_year = dpg.get_value("birth_year_input") if enable_age else None

        # Find cluster
        cluster = next((c for c in self._face_clusters if c.cluster_id == self._selected_cluster_id), None)
        if not cluster:
            return

        # Create person
        person_id = self.face_analyzer.create_person_from_cluster(cluster, name, birth_year)
        if person_id:
            logger.info(f"Created person: {name}")
            self._face_clusters.remove(cluster)
            self._display_face_clusters()
            self._update_stats()

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
            if self.on_photo_selected and file_ids:
                self.on_photo_selected(file_ids[0])

    def _view_pet_cluster_photos(self, cluster_id: int) -> None:
        """View photos in a pet cluster."""
        cluster = next((c for c in self._pet_clusters if c.cluster_id == cluster_id), None)
        if cluster and cluster.sample_detections:
            file_ids = [d.file_id for d in cluster.sample_detections]
            if self.on_photo_selected and file_ids:
                self.on_photo_selected(file_ids[0])

    def _refresh_people_list(self) -> None:
        """Refresh the people list view."""
        # Clear existing rows
        for child in dpg.get_item_children("people_table", 1):
            dpg.delete_item(child)

        people = self.db.get_all_persons(named_only=True)

        for person in people:
            with dpg.table_row(parent="people_table"):
                dpg.add_text(person.name or "Unknown")
                dpg.add_text(str(person.photo_count))

                # Age range
                if person.birth_year:
                    current_age = person.estimated_age or 0
                    dpg.add_text(f"~{current_age} years")
                else:
                    dpg.add_text("-")

                # Actions
                with dpg.group(horizontal=True):
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

    def _show_timeline(self, person_id: int) -> None:
        """Show age timeline for a person."""
        self._selected_person_id = person_id
        person = self.db.get_person(person_id)
        if not person:
            return

        dpg.set_value("timeline_title", f"Timeline: {person.name}")

        # Clear existing content
        for child in dpg.get_item_children("timeline_content", 1):
            dpg.delete_item(child)

        # Get timeline
        timeline = self.face_analyzer.get_person_timeline(person_id)

        for year, faces in timeline:
            with dpg.group(parent="timeline_content", horizontal=False):
                age = year - person.birth_year if person.birth_year else None
                age_text = f" (Age ~{age})" if age else ""
                dpg.add_text(f"{year}{age_text}: {len(faces)} photos", color=(150, 200, 255))

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
                dpg.add_text(f"{year}: {len(detections)} photos", color=(150, 200, 255))

        dpg.configure_item(self.TAG_TIMELINE_DIALOG, show=True)

    def _find_more_photos(self) -> None:
        """Find more photos for selected person/pet."""
        if self._selected_person_id:
            self._find_person_photos(self._selected_person_id)
        elif self._selected_pet_id:
            self._find_pet_photos(self._selected_pet_id)

    def _find_person_photos(self, person_id: int) -> None:
        """Find more photos of a person."""
        try:
            matches, assigned = self.face_analyzer.match_and_assign_faces(
                threshold=0.8, auto_assign=True
            )
            logger.info(f"Found {matches} potential matches, assigned {assigned}")
            self._update_stats()
            self._refresh_people_list()
        except Exception as e:
            logger.error(f"Error finding photos: {e}")

    def _find_pet_photos(self, pet_id: int) -> None:
        """Find more photos of a pet."""
        try:
            matches, assigned = self.pet_analyzer.match_and_assign_detections(
                threshold=0.75, auto_assign=True
            )
            logger.info(f"Found {matches} potential matches, assigned {assigned}")
            self._update_stats()
            self._refresh_pets_list()
        except Exception as e:
            logger.error(f"Error finding photos: {e}")

    def _refresh(self) -> None:
        """Refresh all views."""
        self._update_stats()
        if self._current_view == "people":
            self._refresh_people_list()
        self._display_face_clusters()
        self._display_pet_clusters()

    def refresh(self) -> None:
        """Public method to refresh the panel."""
        self._refresh()
