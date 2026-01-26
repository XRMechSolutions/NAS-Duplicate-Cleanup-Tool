"""Standardized tooltip support for DupliCleaner UI.

This module provides consistent tooltip functionality across all UI panels.
Tooltips help users understand features without cluttering the interface.

Usage:
    from duplicleaner.ui.tooltips import add_tooltip, DRIVE_TOOLTIPS

    # After creating a widget:
    btn = dpg.add_button(label="Quick Scan", callback=...)
    add_tooltip(btn, DRIVE_TOOLTIPS["quick_scan"])

    # Or with custom text:
    add_tooltip(some_widget, "Custom tooltip explaining this feature.")
"""

import dearpygui.dearpygui as dpg
from typing import Union

from duplicleaner.ui.theme import get_text_color

# Default tooltip text width for wrapping
DEFAULT_TOOLTIP_WIDTH = 320


def add_tooltip(
    parent: Union[int, str],
    text: str,
    width: int = DEFAULT_TOOLTIP_WIDTH,
) -> int:
    """Add a styled tooltip to a UI element.

    Creates a tooltip that appears when the user hovers over the parent widget.
    Text automatically wraps at the specified width.

    Args:
        parent: The widget tag/id to attach the tooltip to.
        text: Tooltip text. Use newlines for paragraph breaks.
        width: Maximum width before text wraps. Default 320px.

    Returns:
        The tooltip container tag/id.

    Example:
        btn = dpg.add_button(label="Generate Hashes")
        add_tooltip(btn, "Compute content hashes for duplicate detection.")
    """
    with dpg.tooltip(parent=parent) as tooltip_id:
        dpg.add_text(text, wrap=width, color=get_text_color("primary"))
    return tooltip_id


def add_tooltip_to_table_header(
    table_tag: Union[int, str],
    column_index: int,
    text: str,
    width: int = DEFAULT_TOOLTIP_WIDTH,
) -> None:
    """Add tooltip to a table column header.

    Note: Dear PyGui table columns don't directly support tooltips.
    This is a placeholder for future implementation using overlay techniques.

    Args:
        table_tag: The table widget tag.
        column_index: Zero-based column index.
        text: Tooltip text.
        width: Maximum width before text wraps.
    """
    # Table header tooltips require custom overlay implementation
    # For now, this is documented as a limitation
    pass


# =============================================================================
# DRIVES PANEL TOOLTIPS
# =============================================================================

DRIVE_TOOLTIPS = {
    # --- Action Buttons ---
    "add_drive": (
        "Register a local drive or network share for scanning.\n"
        "Supports paths like C:\\Photos or \\\\NAS\\share"
    ),
    "remove_selected": (
        "Remove the selected drive from the list.\n"
        "Deletes scan data but does not delete actual files."
    ),
    "quick_scan": (
        "Index files and folders without computing hashes.\n"
        "Fast initial scan to catalog your files.\n"
        "Generate hashes afterward to find duplicates."
    ),
    "deep_scan": (
        "Index files AND compute content hashes.\n"
        "Finds exact duplicates by comparing file contents.\n"
        "Slower than Quick Scan but enables duplicate detection."
    ),
    "full_analysis": (
        "Run AI-powered analysis on scanned files.\n"
        "Includes: face detection, scene classification,\n"
        "object detection, OCR, and AI summaries.\n"
        "Configure options with checkboxes below."
    ),
    "scan_all": (
        "Scan all registered drives sequentially.\n"
        "Choose scan mode in the dialog that appears."
    ),
    "hash_now": (
        "Compute content hashes for files on the selected drive.\n"
        "Required for duplicate detection and redundancy reports.\n"
        "Only hashes files that haven't been hashed yet\n"
        "(unless Force rehash is checked)."
    ),
    "resume_scan": (
        "Continue an interrupted scan from where it left off.\n"
        "Enabled when a paused or cancelled scan exists."
    ),
    "refresh": (
        "Refresh the drive list and status information.\n"
        "Updates connection status and space usage."
    ),
    "reset_deleted": (
        "Clear 'deleted' flags for files on this drive.\n"
        "Use after restoring files or if flags are out of sync.\n"
        "Files will be re-verified on next scan."
    ),

    # --- Scan Option Checkboxes ---
    "scan_before_full": (
        "Run a scan before Full Analysis.\n"
        "Uncheck to analyze already-scanned files\n"
        "without re-scanning the drive."
    ),
    "reanalyze_existing": (
        "Re-process files that already have analysis data.\n"
        "Normally only new/unanalyzed files are processed.\n"
        "Check this to refresh AI results for all files."
    ),
    "force_rehash": (
        "Recompute hashes even for already-hashed files.\n"
        "Use if files were modified outside the app,\n"
        "or to verify existing hash data."
    ),
    "bg_analysis": (
        "Run AI analysis in the background during scans.\n"
        "Processes files as they're discovered.\n"
        "May slow down scanning but saves time overall."
    ),
    "bg_hash": (
        "Compute hashes in the background during scans.\n"
        "Hashes files as they're indexed.\n"
        "May slow down scanning but saves time overall."
    ),

    # --- Analysis Type Checkboxes ---
    "analysis_metadata": (
        "Extract EXIF metadata from images.\n"
        "Includes: camera info, GPS coordinates,\n"
        "date taken, dimensions, etc."
    ),
    "analysis_scenes": (
        "Classify images by scene type.\n"
        "Examples: beach, mountain, city, indoor,\n"
        "food, portrait, landscape, etc."
    ),
    "analysis_objects": (
        "Detect objects in images using AI.\n"
        "Identifies: people, animals, vehicles,\n"
        "furniture, food, and more."
    ),
    "analysis_ocr": (
        "Extract text from images using OCR.\n"
        "Useful for screenshots, documents,\n"
        "signs, and text-heavy images."
    ),
    "analysis_summaries": (
        "Generate natural language descriptions.\n"
        "AI writes a sentence describing each image.\n"
        "Enables powerful search by description."
    ),
    "analysis_images": (
        "Include image files in analysis.\n"
        "Formats: JPG, PNG, HEIC, WebP, etc."
    ),
    "analysis_docs": (
        "Include document files in analysis.\n"
        "Uses extensions from the Doc extensions field."
    ),
    "analysis_data": (
        "Include data files in analysis.\n"
        "Uses extensions from the Data extensions field."
    ),

    # --- Extension Fields ---
    "doc_extensions": (
        "File extensions to treat as documents.\n"
        "Comma-separated, with or without dots.\n"
        "Example: .pdf, .docx, .txt"
    ),
    "data_extensions": (
        "File extensions to treat as data files.\n"
        "Comma-separated, with or without dots.\n"
        "Example: .csv, .json, .xml"
    ),

    # --- Redundancy & Backup Section ---
    "generate_redundancy": (
        "Analyze which files lack backup copies.\n"
        "'At-risk' files exist on only one drive.\n"
        "Requires hashed files (run Generate Hashes first)."
    ),
    "build_backup_plan": (
        "Generate a list of files to copy for redundancy.\n"
        "Copies at-risk files from source to target drives.\n"
        "Review the plan before executing."
    ),
    "execute_backup_plan": (
        "Copy files according to the backup plan.\n"
        "Creates redundant copies on target drives.\n"
        "Progress shown below; can pause or cancel."
    ),
    "export_plan": (
        "Save the backup plan as a CSV file.\n"
        "Exports to Desktop as backup_plan.csv"
    ),
    "open_targets": (
        "Open selected backup target folders\n"
        "in Windows Explorer."
    ),
    "backup_source": (
        "Folder containing files to back up.\n"
        "Files here will be copied to target drives\n"
        "if they don't already exist there."
    ),
    "backup_targets": (
        "Drives to copy files to for redundancy.\n"
        "Check the drives you want as backup destinations."
    ),
    "exclude_patterns": (
        "Patterns for files/folders to skip.\n"
        "One pattern per line. Supports glob syntax:\n"
        "  node_modules/    - folder name\n"
        "  *.tmp            - file extension\n"
        "  **/.git          - any .git folder"
    ),
    "analyze_exclusions": (
        "Show how many files each pattern matches.\n"
        "Helps verify exclusion patterns are correct\n"
        "before building the backup plan."
    ),

    # --- Tables ---
    "at_risk_table": (
        "Files that exist on only one drive.\n"
        "These have no backup and are vulnerable to data loss.\n"
        "Use Build Backup Plan to create redundant copies."
    ),
}


# =============================================================================
# DUPLICATES PANEL TOOLTIPS (for future use)
# =============================================================================

DUPLICATE_TOOLTIPS = {
    "filter_type": (
        "Filter duplicate groups by match type.\n"
        "Exact = identical bytes. Near = visually similar images."
    ),
    "filter_status": (
        "Show pending, resolved, or ignored groups.\n"
        "Pending groups are eligible for keeper selection and actions."
    ),
    "filter_scope": (
        "Limit results to groups that span drives or live on a single drive."
    ),
    "filter_drive": (
        "Show groups that include files from a specific drive."
    ),
    "refresh": (
        "Reload the duplicate groups list and statistics."
    ),
    "find_duplicates": (
        "Run duplicate detection using content and perceptual hashes.\n"
        "Run a deep scan or Generate Hashes first for best results."
    ),
    "select_all": (
        "Select all visible groups for bulk actions."
    ),
    "select_none": (
        "Clear group selections."
    ),
    "unignore_selected": (
        "Unignore the selected groups (only affects ignored groups)."
    ),
    "strategy": (
        "Choose how keepers are selected for each group."
    ),
    "strategy_drive": (
        "Used only for Keep on Drive strategy."
    ),
    "preview": (
        "Preview what the selected strategy would do.\n"
        "Uses selected groups if any, otherwise the current filtered view."
    ),
    "apply_selected": (
        "Apply the selected strategy to checked groups.\n"
        "Marks keepers but does not delete files."
    ),
    "apply_all": (
        "Apply the selected strategy to all pending groups in the current view."
    ),
    "quarantine": (
        "Move non-keeper files to a quarantine folder (recoverable)."
    ),
    "trash": (
        "Send non-keeper files to the recycle bin."
    ),
    "delete": (
        "Permanently delete non-keeper files. This cannot be undone."
    ),
    "ignore_group": (
        "Ignore the current group so it no longer appears in pending lists."
    ),
    "clear_selections": (
        "Clear keeper selections and reset groups to pending."
    ),
}


# =============================================================================
# FACES PANEL TOOLTIPS
# =============================================================================

FACE_TOOLTIPS = {
    # --- Cluster Actions ---
    "name_person": (
        "Create a new named person from this cluster.\n"
        "All faces in the cluster will be assigned to the new person."
    ),
    "assign_cluster": (
        "Assign this cluster to an existing person.\n"
        "Use when you recognize faces that belong to someone already named."
    ),
    "split_cluster": (
        "Split faces from this cluster into a separate group.\n"
        "Use when the AI grouped different people together by mistake."
    ),
    "view_photos": (
        "View photos containing faces from this cluster.\n"
        "Opens the photo viewer with all matching files."
    ),
    "view_all": (
        "View all faces in this cluster (up to 200).\n"
        "Useful for reviewing large clusters before naming."
    ),
    "ignore_cluster": (
        "Hide this cluster of unknown faces.\n"
        "Creates a hidden 'Unknown #N' person that won't appear in lists.\n"
        "Use for crowds, strangers, or faces you don't want to track."
    ),

    # --- People View ---
    "timeline": (
        "View this person's photos organized by date.\n"
        "Shows how they appear over time."
    ),
    "find_more": (
        "Search for more photos of this person.\n"
        "Looks through unassigned faces for matches."
    ),
    "edit_person": (
        "Edit this person's name and birth year.\n"
        "Birth year helps with age-based matching."
    ),
    "delete_person": (
        "Delete this person from the database.\n"
        "Their faces will return to Unknown Clusters."
    ),
    "show_hidden": (
        "Show or hide ignored/hidden people.\n"
        "Hidden people were created using 'Ignore' on clusters."
    ),
    "restore_hidden": (
        "Restore this hidden person to the regular list.\n"
        "They will appear in the People view again."
    ),

    # --- Settings ---
    "detection_threshold": (
        "Minimum confidence for face detection.\n"
        "Lower = more faces detected (may include false positives).\n"
        "Higher = fewer faces (may miss some real faces).\n"
        "Default: 0.5"
    ),
    "match_threshold": (
        "Similarity required to match a face to a known person.\n"
        "Lower = more matches (may have errors).\n"
        "Higher = stricter matching (may miss some).\n"
        "Default: 0.8"
    ),
    "cluster_threshold": (
        "Similarity for grouping unknown faces together.\n"
        "Lower = larger clusters (may mix people).\n"
        "Higher = smaller clusters (may split same person).\n"
        "Default: 0.6"
    ),
    "reset_faces": (
        "Clear face detection data.\n"
        "Choose scope: all faces, unassigned only, or low-confidence.\n"
        "WARNING: This cannot be undone."
    ),

    # --- Cross-Age Recognition ---
    "find_related": (
        "Find clusters that may be this person at other ages.\n"
        "Uses face embeddings to bridge across time.\n"
        "High-confidence matches are auto-assigned."
    ),
}


# =============================================================================
# PHOTO ORGANIZER PANEL TOOLTIPS
# =============================================================================

ORGANIZE_TOOLTIPS = {
    # --- Source/Destination ---
    "source_folder": (
        "Folder containing unorganized photos.\n"
        "Files here will be organized into the destination."
    ),
    "dest_folder": (
        "Folder where organized photos will be placed.\n"
        "Subfolders are created based on date/location settings."
    ),

    # --- Folder Structure ---
    "date_format": (
        "How to structure date-based folders.\n"
        "YYYY/MM = 2024/03\n"
        "YYYY/MM-Month = 2024/03-March\n"
        "YYYY/MM/DD = 2024/03/15"
    ),
    "include_location": (
        "Add location names to folder paths.\n"
        "Uses GPS coordinates from photo EXIF data.\n"
        "Example: 2024/03-March/New York/"
    ),
    "location_level": (
        "How much location detail to include.\n"
        "City Only: New York\n"
        "City + Country: New York, USA\n"
        "Full: New York, NY, USA"
    ),
    "event_clustering": (
        "Group photos taken close together into events.\n"
        "Creates subfolders like 'Event_001' for bursts\n"
        "of photos within the configured time gap."
    ),
    "event_gap": (
        "Hours between photos to consider them separate events.\n"
        "Photos within this gap are grouped together.\n"
        "Lower = more events, Higher = fewer larger events."
    ),

    # --- File Naming ---
    "rename_files": (
        "Rename files during organization.\n"
        "Uncheck to keep original filenames."
    ),
    "rename_pattern": (
        "Pattern for renamed files.\n"
        "{date} = capture date (2024-03-15)\n"
        "{time} = capture time (14-30-00)\n"
        "{location} = city name\n"
        "{seq} = sequence number (001, 002...)"
    ),
    "conflict_resolution": (
        "What to do when a file already exists.\n"
        "Add Sequence: photo_001.jpg, photo_002.jpg\n"
        "Add Timestamp: photo_143022.jpg\n"
        "Skip: Leave existing file, don't copy\n"
        "Overwrite if Identical: Replace only if same content"
    ),

    # --- Special Handling ---
    "screenshots": (
        "How to handle detected screenshots.\n"
        "Mix: Organize with regular photos\n"
        "Separate: Put in Screenshots subfolder"
    ),
    "bursts": (
        "How to handle burst photo sequences.\n"
        "Keep All: Treat as individual photos\n"
        "Subfolder: Group in Burst_001 subfolders\n"
        "Flag: Mark for manual review"
    ),
    "live_photos": (
        "How to handle Live Photos (photo + video pairs).\n"
        "Keep Together: Same folder as the photo\n"
        "Video Subfolder: Videos in separate subfolder"
    ),
    "undated": (
        "How to handle photos without date metadata.\n"
        "Undated Folder: Put in 'Undated' folder\n"
        "Use File Date: Use file modified date\n"
        "Skip: Don't organize these files"
    ),
    "move_files": (
        "Move files instead of copying.\n"
        "Move: Original files are relocated (faster)\n"
        "Copy: Original files remain in place (safer)"
    ),
    "dry_run": (
        "Preview changes without moving/copying files.\n"
        "Use to verify organization before committing."
    ),

    # --- Action Buttons ---
    "preview": (
        "Analyze source folder and show planned changes.\n"
        "No files are moved until you click Organize Now."
    ),
    "organize": (
        "Execute the organization plan.\n"
        "Files will be moved/copied based on settings.\n"
        "Run Preview first to see what will happen."
    ),
    "cancel": (
        "Stop the current organization operation.\n"
        "Files already processed will remain in place."
    ),
    "export_csv": (
        "Save the preview as a CSV file.\n"
        "Useful for reviewing changes before organizing."
    ),
}


# =============================================================================
# SETTINGS PANEL TOOLTIPS
# =============================================================================

SETTINGS_TOOLTIPS = {
    "confirm_destructive": (
        "Show a confirmation prompt before quarantine, trash, or delete actions."
    ),
    "audit_log": (
        "Record all file actions in the audit log for traceability."
    ),
    "run_wizard": (
        "Re-run the first-time setup wizard for drives and AI defaults."
    ),
    "near_duplicate_threshold": (
        "Controls how similar images must be to count as near-duplicates.\n"
        "Higher = stricter, fewer matches."
    ),
    "match_formats": (
        "Treat visually similar images as duplicates across formats."
    ),
    "min_image_size": (
        "Skip tiny images for near-duplicate checks."
    ),
    "max_file_size": (
        "Skip files larger than this size when scanning."
    ),
    "process_videos": (
        "Video near-duplicate detection is not implemented yet."
    ),
    "ai_enabled": (
        "Enable AI-powered features like summaries, tagging, and analysis."
    ),
    "ai_gpu": (
        "Use GPU acceleration when available."
    ),
    "key_storage": (
        "Indicates whether secure key storage is available."
    ),
    "openai_key": (
        "Store your OpenAI API key for cloud summaries."
    ),
    "anthropic_key": (
        "Store your Anthropic API key for cloud summaries."
    ),
    "summary_provider": (
        "Choose which provider to use for AI summaries."
    ),
    "summary_model_local": (
        "Local model name used for summaries."
    ),
    "summary_model_openai": (
        "OpenAI model name used for summaries."
    ),
    "summary_model_anthropic": (
        "Anthropic model name used for summaries."
    ),
    "summary_model_google": (
        "Google model name used for summaries."
    ),
    "summary_max_tokens": (
        "Maximum tokens for AI summaries."
    ),
    "summary_temperature": (
        "Lower = more deterministic, higher = more creative."
    ),
    "model_refresh": (
        "Refresh model download status."
    ),
    "model_verify": (
        "Validate installed models and report missing files."
    ),
    "deps_variant": (
        "Choose GPU or CPU dependencies to install."
    ),
    "deps_scope": (
        "Install dependencies for the current user or system-wide."
    ),
    "deps_install": (
        "Install AI dependencies for selected variant and scope."
    ),
    "metadata_location_lookup": (
        "Reverse-geocode GPS coordinates to location names.\n"
        "Requires internet access."
    ),
    "metadata_location_level": (
        "Controls how detailed location names are."
    ),
    "analysis_include_metadata": (
        "Extract EXIF metadata and file details."
    ),
    "analysis_include_scenes": (
        "Classify images by scene type."
    ),
    "analysis_include_objects": (
        "Detect objects in images."
    ),
    "analysis_include_ocr": (
        "Extract text from images."
    ),
    "analysis_include_summaries": (
        "Generate AI summaries using the selected provider."
    ),
    "analysis_include_images": (
        "Include image files during analysis."
    ),
    "analysis_include_docs": (
        "Include document/text files during analysis."
    ),
    "analysis_include_data": (
        "Include data files (csv/json/xml/yaml) during analysis."
    ),
    "analysis_doc_extensions": (
        "Comma-separated list of document extensions."
    ),
    "analysis_data_extensions": (
        "Comma-separated list of data extensions."
    ),
    "analysis_scan_before_full": (
        "Run a scan before analysis to pick up new files."
    ),
    "analysis_reanalyze_existing": (
        "Overwrite existing analysis results."
    ),
    "analysis_run": (
        "Start analysis with the current settings."
    ),
    "analysis_cancel": (
        "Cancel the current analysis run."
    ),
    "version_add_folder": (
        "Add a folder to version tracking."
    ),
    "version_remove_folder": (
        "Remove the selected tracked folder."
    ),
    "version_include_subfolders": (
        "Track files in subfolders as well."
    ),
    "version_auto_mode": (
        "Choose how often versions are saved automatically."
    ),
    "version_max_size": (
        "Skip files larger than this size for version tracking."
    ),
    "version_browse": (
        "Browse for a file to view history."
    ),
    "version_view_history": (
        "Open version history for the selected file."
    ),
    "version_save": (
        "Manually save a version of the selected file."
    ),
}
