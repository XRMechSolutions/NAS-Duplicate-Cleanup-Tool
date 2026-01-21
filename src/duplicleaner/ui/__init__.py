"""UI modules for DupliCleaner.

Dear PyGui-based user interface components.
"""

from duplicleaner.ui.drives_panel import DrivesPanel
from duplicleaner.ui.duplicates_panel import DuplicatesPanel
from duplicleaner.ui.organize_panel import OrganizePanel
from duplicleaner.ui.action_log_panel import ActionLogPanel
from duplicleaner.ui.faces_panel import FacesPanel
from duplicleaner.ui.search_panel import SearchPanel
from duplicleaner.ui.status_log_panel import StatusLogPanel

__all__ = [
    "DrivesPanel",
    "DuplicatesPanel",
    "OrganizePanel",
    "ActionLogPanel",
    "FacesPanel",
    "SearchPanel",
    "StatusLogPanel",
]

# Modules to be imported as they are implemented
# from duplicleaner.ui.settings_panel import SettingsPanel
