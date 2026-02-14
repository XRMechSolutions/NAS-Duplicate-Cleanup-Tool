"""Theme management for DupliCleaner.

Provides light and dark theme definitions with modern styling.
Themes can be switched at runtime.
"""

import contextlib
from dataclasses import dataclass

import dearpygui.dearpygui as dpg

from duplicleaner.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ThemeColors:
    """Color palette for a theme."""

    # Window backgrounds
    window_bg: tuple[int, int, int, int]
    child_bg: tuple[int, int, int, int]
    popup_bg: tuple[int, int, int, int]

    # Borders
    border: tuple[int, int, int, int]
    border_shadow: tuple[int, int, int, int]

    # Frame backgrounds (inputs, combos, etc.)
    frame_bg: tuple[int, int, int, int]
    frame_bg_hovered: tuple[int, int, int, int]
    frame_bg_active: tuple[int, int, int, int]

    # Title bar
    title_bg: tuple[int, int, int, int]
    title_bg_active: tuple[int, int, int, int]
    title_bg_collapsed: tuple[int, int, int, int]

    # Scrollbar
    scrollbar_bg: tuple[int, int, int, int]
    scrollbar_grab: tuple[int, int, int, int]
    scrollbar_grab_hovered: tuple[int, int, int, int]
    scrollbar_grab_active: tuple[int, int, int, int]

    # Buttons
    button: tuple[int, int, int, int]
    button_hovered: tuple[int, int, int, int]
    button_active: tuple[int, int, int, int]

    # Headers (collapsing headers, tree nodes)
    header: tuple[int, int, int, int]
    header_hovered: tuple[int, int, int, int]
    header_active: tuple[int, int, int, int]

    # Tabs
    tab: tuple[int, int, int, int]
    tab_hovered: tuple[int, int, int, int]
    tab_active: tuple[int, int, int, int]
    tab_unfocused: tuple[int, int, int, int]
    tab_unfocused_active: tuple[int, int, int, int]

    # Tables
    table_header_bg: tuple[int, int, int, int]
    table_row_bg: tuple[int, int, int, int]
    table_row_bg_alt: tuple[int, int, int, int]
    table_border_strong: tuple[int, int, int, int]
    table_border_light: tuple[int, int, int, int]

    # Text
    text: tuple[int, int, int, int]
    text_disabled: tuple[int, int, int, int]
    text_selected_bg: tuple[int, int, int, int]

    # Widgets
    check_mark: tuple[int, int, int, int]
    slider_grab: tuple[int, int, int, int]
    slider_grab_active: tuple[int, int, int, int]

    # Resize grip
    resize_grip: tuple[int, int, int, int]
    resize_grip_hovered: tuple[int, int, int, int]
    resize_grip_active: tuple[int, int, int, int]

    # Separator
    separator: tuple[int, int, int, int]
    separator_hovered: tuple[int, int, int, int]
    separator_active: tuple[int, int, int, int]

    # Plot colors (for any charts/graphs)
    plot_bg: tuple[int, int, int, int]
    plot_border: tuple[int, int, int, int]

    # Semantic colors for status/feedback
    accent: tuple[int, int, int, int]
    accent_hovered: tuple[int, int, int, int]
    accent_active: tuple[int, int, int, int]
    success: tuple[int, int, int, int]
    warning: tuple[int, int, int, int]
    error: tuple[int, int, int, int]
    info: tuple[int, int, int, int]


@dataclass
class ThemeStyles:
    """Style settings for a theme."""

    # Rounding
    window_rounding: float = 8.0
    child_rounding: float = 6.0
    frame_rounding: float = 6.0
    popup_rounding: float = 6.0
    scrollbar_rounding: float = 6.0
    grab_rounding: float = 4.0
    tab_rounding: float = 6.0

    # Padding
    window_padding: tuple[float, float] = (12.0, 12.0)
    frame_padding: tuple[float, float] = (10.0, 6.0)
    cell_padding: tuple[float, float] = (6.0, 4.0)
    item_spacing: tuple[float, float] = (10.0, 6.0)
    item_inner_spacing: tuple[float, float] = (6.0, 4.0)

    # Borders
    window_border_size: float = 1.0
    child_border_size: float = 1.0
    frame_border_size: float = 0.0
    popup_border_size: float = 1.0
    tab_border_size: float = 0.0

    # Sizes
    scrollbar_size: float = 14.0
    grab_min_size: float = 12.0
    indent_spacing: float = 20.0


# Dark theme colors - modern dark with blue accent
DARK_COLORS = ThemeColors(
    # Window backgrounds
    window_bg=(24, 26, 31, 255),
    child_bg=(30, 33, 39, 255),
    popup_bg=(35, 38, 45, 255),

    # Borders
    border=(55, 60, 70, 255),
    border_shadow=(0, 0, 0, 0),

    # Frame backgrounds
    frame_bg=(40, 44, 52, 255),
    frame_bg_hovered=(50, 55, 65, 255),
    frame_bg_active=(55, 60, 72, 255),

    # Title bar
    title_bg=(24, 26, 31, 255),
    title_bg_active=(35, 38, 45, 255),
    title_bg_collapsed=(24, 26, 31, 255),

    # Scrollbar
    scrollbar_bg=(24, 26, 31, 180),
    scrollbar_grab=(70, 75, 85, 255),
    scrollbar_grab_hovered=(90, 95, 110, 255),
    scrollbar_grab_active=(110, 115, 130, 255),

    # Buttons
    button=(55, 90, 140, 255),
    button_hovered=(65, 105, 160, 255),
    button_active=(75, 115, 175, 255),

    # Headers
    header=(55, 90, 140, 180),
    header_hovered=(65, 105, 160, 200),
    header_active=(75, 115, 175, 255),

    # Tabs
    tab=(40, 44, 52, 255),
    tab_hovered=(65, 105, 160, 255),
    tab_active=(55, 90, 140, 255),
    tab_unfocused=(35, 38, 45, 255),
    tab_unfocused_active=(45, 75, 115, 255),

    # Tables
    table_header_bg=(40, 44, 52, 255),
    table_row_bg=(0, 0, 0, 0),
    table_row_bg_alt=(35, 38, 45, 100),
    table_border_strong=(55, 60, 70, 255),
    table_border_light=(45, 50, 58, 255),

    # Text
    text=(225, 228, 235, 255),
    text_disabled=(120, 125, 135, 255),
    text_selected_bg=(55, 90, 140, 180),

    # Widgets
    check_mark=(100, 160, 230, 255),
    slider_grab=(55, 90, 140, 255),
    slider_grab_active=(75, 115, 175, 255),

    # Resize grip
    resize_grip=(55, 90, 140, 50),
    resize_grip_hovered=(55, 90, 140, 170),
    resize_grip_active=(55, 90, 140, 240),

    # Separator
    separator=(55, 60, 70, 255),
    separator_hovered=(100, 160, 230, 255),
    separator_active=(100, 160, 230, 255),

    # Plot
    plot_bg=(30, 33, 39, 255),
    plot_border=(55, 60, 70, 255),

    # Semantic colors
    accent=(100, 160, 230, 255),
    accent_hovered=(120, 175, 240, 255),
    accent_active=(140, 190, 250, 255),
    success=(95, 190, 125, 255),
    warning=(230, 175, 80, 255),
    error=(220, 95, 95, 255),
    info=(100, 160, 230, 255),
)


# Light theme colors - clean light with blue accent
LIGHT_COLORS = ThemeColors(
    # Window backgrounds
    window_bg=(248, 249, 252, 255),
    child_bg=(255, 255, 255, 255),
    popup_bg=(255, 255, 255, 255),

    # Borders
    border=(210, 215, 225, 255),
    border_shadow=(0, 0, 0, 0),

    # Frame backgrounds
    frame_bg=(235, 238, 245, 255),
    frame_bg_hovered=(225, 228, 238, 255),
    frame_bg_active=(215, 220, 232, 255),

    # Title bar
    title_bg=(235, 238, 245, 255),
    title_bg_active=(225, 228, 238, 255),
    title_bg_collapsed=(235, 238, 245, 255),

    # Scrollbar
    scrollbar_bg=(248, 249, 252, 180),
    scrollbar_grab=(195, 200, 212, 255),
    scrollbar_grab_hovered=(175, 180, 195, 255),
    scrollbar_grab_active=(155, 160, 178, 255),

    # Buttons
    button=(55, 115, 185, 255),
    button_hovered=(45, 100, 170, 255),
    button_active=(35, 85, 150, 255),

    # Headers
    header=(55, 115, 185, 180),
    header_hovered=(45, 100, 170, 200),
    header_active=(35, 85, 150, 255),

    # Tabs
    tab=(235, 238, 245, 255),
    tab_hovered=(45, 100, 170, 255),
    tab_active=(55, 115, 185, 255),
    tab_unfocused=(240, 242, 248, 255),
    tab_unfocused_active=(80, 135, 195, 255),

    # Tables
    table_header_bg=(235, 238, 245, 255),
    table_row_bg=(0, 0, 0, 0),
    table_row_bg_alt=(245, 247, 252, 100),
    table_border_strong=(210, 215, 225, 255),
    table_border_light=(225, 228, 238, 255),

    # Text
    text=(35, 40, 50, 255),
    text_disabled=(140, 145, 158, 255),
    text_selected_bg=(55, 115, 185, 100),

    # Widgets
    check_mark=(55, 115, 185, 255),
    slider_grab=(55, 115, 185, 255),
    slider_grab_active=(35, 85, 150, 255),

    # Resize grip
    resize_grip=(55, 115, 185, 50),
    resize_grip_hovered=(55, 115, 185, 170),
    resize_grip_active=(55, 115, 185, 240),

    # Separator
    separator=(210, 215, 225, 255),
    separator_hovered=(55, 115, 185, 255),
    separator_active=(55, 115, 185, 255),

    # Plot
    plot_bg=(255, 255, 255, 255),
    plot_border=(210, 215, 225, 255),

    # Semantic colors
    accent=(55, 115, 185, 255),
    accent_hovered=(45, 100, 170, 255),
    accent_active=(35, 85, 150, 255),
    success=(45, 160, 90, 255),
    warning=(210, 145, 35, 255),
    error=(200, 65, 65, 255),
    info=(55, 115, 185, 255),
)


# Default styles (same for both themes)
DEFAULT_STYLES = ThemeStyles()


class ThemeManager:
    """Manages application themes."""

    def __init__(self) -> None:
        self._current_theme: str = "dark"
        self._theme_id: int | None = None
        self._colors: ThemeColors = DARK_COLORS
        self._styles: ThemeStyles = DEFAULT_STYLES

    @property
    def current_theme(self) -> str:
        """Get current theme name."""
        return self._current_theme

    @property
    def colors(self) -> ThemeColors:
        """Get current theme colors for use in custom widgets."""
        return self._colors

    @property
    def styles(self) -> ThemeStyles:
        """Get current theme styles."""
        return self._styles

    def apply_theme(self, theme_name: str) -> None:
        """Apply a theme to the application.

        Args:
            theme_name: Theme name ('dark' or 'light')
        """
        if theme_name not in ("dark", "light"):
            logger.warning(f"Unknown theme '{theme_name}', defaulting to dark")
            theme_name = "dark"

        self._current_theme = theme_name
        self._colors = DARK_COLORS if theme_name == "dark" else LIGHT_COLORS

        # Delete old theme if it exists
        if self._theme_id is not None:
            with contextlib.suppress(Exception):
                dpg.delete_item(self._theme_id)

        # Create new theme
        with dpg.theme() as self._theme_id, dpg.theme_component(dpg.mvAll):
            self._apply_colors()
            self._apply_styles()

        dpg.bind_theme(self._theme_id)
        logger.info(f"Applied {theme_name} theme")

    def _apply_colors(self) -> None:
        """Apply color settings to the current theme component."""
        c = self._colors

        def safe_add_theme_color(name: str, color: tuple[int, int, int], category) -> None:
            if not hasattr(dpg, name):
                return
            theme_col = getattr(dpg, name)
            # Some DearPyGui versions may not support certain colors/categories.
            with contextlib.suppress(Exception):
                dpg.add_theme_color(theme_col, color, category=category)

        # Window backgrounds
        safe_add_theme_color("mvThemeCol_WindowBg", c.window_bg[:3], dpg.mvThemeCat_Core)
        safe_add_theme_color("mvThemeCol_ChildBg", c.child_bg[:3], dpg.mvThemeCat_Core)
        safe_add_theme_color("mvThemeCol_PopupBg", c.popup_bg[:3], dpg.mvThemeCat_Core)

        # Borders
        safe_add_theme_color("mvThemeCol_Border", c.border[:3], dpg.mvThemeCat_Core)
        safe_add_theme_color("mvThemeCol_BorderShadow", c.border_shadow[:3], dpg.mvThemeCat_Core)

        # Frame backgrounds
        safe_add_theme_color("mvThemeCol_FrameBg", c.frame_bg[:3], dpg.mvThemeCat_Core)
        safe_add_theme_color("mvThemeCol_FrameBgHovered", c.frame_bg_hovered[:3], dpg.mvThemeCat_Core)
        safe_add_theme_color("mvThemeCol_FrameBgActive", c.frame_bg_active[:3], dpg.mvThemeCat_Core)

        # Title bar
        safe_add_theme_color("mvThemeCol_TitleBg", c.title_bg[:3], dpg.mvThemeCat_Core)
        safe_add_theme_color("mvThemeCol_TitleBgActive", c.title_bg_active[:3], dpg.mvThemeCat_Core)
        safe_add_theme_color("mvThemeCol_TitleBgCollapsed", c.title_bg_collapsed[:3], dpg.mvThemeCat_Core)

        # Scrollbar
        safe_add_theme_color("mvThemeCol_ScrollbarBg", c.scrollbar_bg[:3], dpg.mvThemeCat_Core)
        safe_add_theme_color("mvThemeCol_ScrollbarGrab", c.scrollbar_grab[:3], dpg.mvThemeCat_Core)
        safe_add_theme_color("mvThemeCol_ScrollbarGrabHovered", c.scrollbar_grab_hovered[:3], dpg.mvThemeCat_Core)
        safe_add_theme_color("mvThemeCol_ScrollbarGrabActive", c.scrollbar_grab_active[:3], dpg.mvThemeCat_Core)

        # Buttons
        safe_add_theme_color("mvThemeCol_Button", c.button[:3], dpg.mvThemeCat_Core)
        safe_add_theme_color("mvThemeCol_ButtonHovered", c.button_hovered[:3], dpg.mvThemeCat_Core)
        safe_add_theme_color("mvThemeCol_ButtonActive", c.button_active[:3], dpg.mvThemeCat_Core)

        # Headers
        safe_add_theme_color("mvThemeCol_Header", c.header[:3], dpg.mvThemeCat_Core)
        safe_add_theme_color("mvThemeCol_HeaderHovered", c.header_hovered[:3], dpg.mvThemeCat_Core)
        safe_add_theme_color("mvThemeCol_HeaderActive", c.header_active[:3], dpg.mvThemeCat_Core)

        # Tabs
        safe_add_theme_color("mvThemeCol_Tab", c.tab[:3], dpg.mvThemeCat_Core)
        safe_add_theme_color("mvThemeCol_TabHovered", c.tab_hovered[:3], dpg.mvThemeCat_Core)
        safe_add_theme_color("mvThemeCol_TabActive", c.tab_active[:3], dpg.mvThemeCat_Core)
        safe_add_theme_color("mvThemeCol_TabUnfocused", c.tab_unfocused[:3], dpg.mvThemeCat_Core)
        safe_add_theme_color("mvThemeCol_TabUnfocusedActive", c.tab_unfocused_active[:3], dpg.mvThemeCat_Core)

        # Tables
        safe_add_theme_color("mvThemeCol_TableHeaderBg", c.table_header_bg[:3], dpg.mvThemeCat_Core)
        safe_add_theme_color("mvThemeCol_TableRowBg", c.table_row_bg[:3], dpg.mvThemeCat_Core)
        safe_add_theme_color("mvThemeCol_TableRowBgAlt", c.table_row_bg_alt[:3], dpg.mvThemeCat_Core)
        safe_add_theme_color("mvThemeCol_TableBorderStrong", c.table_border_strong[:3], dpg.mvThemeCat_Core)
        safe_add_theme_color("mvThemeCol_TableBorderLight", c.table_border_light[:3], dpg.mvThemeCat_Core)

        # Text
        safe_add_theme_color("mvThemeCol_Text", c.text[:3], dpg.mvThemeCat_Core)
        safe_add_theme_color("mvThemeCol_TextDisabled", c.text_disabled[:3], dpg.mvThemeCat_Core)
        safe_add_theme_color("mvThemeCol_TextSelectedBg", c.text_selected_bg[:3], dpg.mvThemeCat_Core)

        # Widgets
        safe_add_theme_color("mvThemeCol_CheckMark", c.check_mark[:3], dpg.mvThemeCat_Core)
        safe_add_theme_color("mvThemeCol_SliderGrab", c.slider_grab[:3], dpg.mvThemeCat_Core)
        safe_add_theme_color("mvThemeCol_SliderGrabActive", c.slider_grab_active[:3], dpg.mvThemeCat_Core)

        # Resize grip
        safe_add_theme_color("mvThemeCol_ResizeGrip", c.resize_grip[:3], dpg.mvThemeCat_Core)
        safe_add_theme_color("mvThemeCol_ResizeGripHovered", c.resize_grip_hovered[:3], dpg.mvThemeCat_Core)
        safe_add_theme_color("mvThemeCol_ResizeGripActive", c.resize_grip_active[:3], dpg.mvThemeCat_Core)

        # Separator
        safe_add_theme_color("mvThemeCol_Separator", c.separator[:3], dpg.mvThemeCat_Core)
        safe_add_theme_color("mvThemeCol_SeparatorHovered", c.separator_hovered[:3], dpg.mvThemeCat_Core)
        safe_add_theme_color("mvThemeCol_SeparatorActive", c.separator_active[:3], dpg.mvThemeCat_Core)

        # Plot
        plot_category = getattr(dpg, "mvThemeCat_Plots", dpg.mvThemeCat_Core)
        safe_add_theme_color("mvThemeCol_PlotBg", c.plot_bg[:3], plot_category)
        safe_add_theme_color("mvThemeCol_PlotBorder", c.plot_border[:3], plot_category)

    def _apply_styles(self) -> None:
        """Apply style settings to the current theme component."""
        s = self._styles

        # Rounding
        dpg.add_theme_style(dpg.mvStyleVar_WindowRounding, s.window_rounding, category=dpg.mvThemeCat_Core)
        dpg.add_theme_style(dpg.mvStyleVar_ChildRounding, s.child_rounding, category=dpg.mvThemeCat_Core)
        dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, s.frame_rounding, category=dpg.mvThemeCat_Core)
        dpg.add_theme_style(dpg.mvStyleVar_PopupRounding, s.popup_rounding, category=dpg.mvThemeCat_Core)
        dpg.add_theme_style(dpg.mvStyleVar_ScrollbarRounding, s.scrollbar_rounding, category=dpg.mvThemeCat_Core)
        dpg.add_theme_style(dpg.mvStyleVar_GrabRounding, s.grab_rounding, category=dpg.mvThemeCat_Core)
        dpg.add_theme_style(dpg.mvStyleVar_TabRounding, s.tab_rounding, category=dpg.mvThemeCat_Core)

        # Padding
        dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, s.window_padding[0], s.window_padding[1], category=dpg.mvThemeCat_Core)
        dpg.add_theme_style(dpg.mvStyleVar_FramePadding, s.frame_padding[0], s.frame_padding[1], category=dpg.mvThemeCat_Core)
        dpg.add_theme_style(dpg.mvStyleVar_CellPadding, s.cell_padding[0], s.cell_padding[1], category=dpg.mvThemeCat_Core)
        dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, s.item_spacing[0], s.item_spacing[1], category=dpg.mvThemeCat_Core)
        dpg.add_theme_style(dpg.mvStyleVar_ItemInnerSpacing, s.item_inner_spacing[0], s.item_inner_spacing[1], category=dpg.mvThemeCat_Core)

        # Borders
        dpg.add_theme_style(dpg.mvStyleVar_WindowBorderSize, s.window_border_size, category=dpg.mvThemeCat_Core)
        dpg.add_theme_style(dpg.mvStyleVar_ChildBorderSize, s.child_border_size, category=dpg.mvThemeCat_Core)
        dpg.add_theme_style(dpg.mvStyleVar_FrameBorderSize, s.frame_border_size, category=dpg.mvThemeCat_Core)
        dpg.add_theme_style(dpg.mvStyleVar_PopupBorderSize, s.popup_border_size, category=dpg.mvThemeCat_Core)
        dpg.add_theme_style(dpg.mvStyleVar_TabBorderSize, s.tab_border_size, category=dpg.mvThemeCat_Core)

        # Sizes
        dpg.add_theme_style(dpg.mvStyleVar_ScrollbarSize, s.scrollbar_size, category=dpg.mvThemeCat_Core)
        dpg.add_theme_style(dpg.mvStyleVar_GrabMinSize, s.grab_min_size, category=dpg.mvThemeCat_Core)
        dpg.add_theme_style(dpg.mvStyleVar_IndentSpacing, s.indent_spacing, category=dpg.mvThemeCat_Core)

    def get_status_color(self, level: str) -> tuple[int, int, int]:
        """Get color for a status level.

        Args:
            level: Status level ('info', 'success', 'warning', 'error')

        Returns:
            RGB color tuple
        """
        color_map = {
            "info": self._colors.info[:3],
            "success": self._colors.success[:3],
            "warning": self._colors.warning[:3],
            "error": self._colors.error[:3],
        }
        return color_map.get(level, self._colors.text[:3])

    def get_accent_color(self) -> tuple[int, int, int]:
        """Get the accent color for highlights."""
        return self._colors.accent[:3]

    def get_text_color(self, variant: str = "primary") -> tuple[int, int, int]:
        """Get text color variant.

        Args:
            variant: 'primary', 'secondary', or 'disabled'

        Returns:
            RGB color tuple
        """
        if variant == "disabled":
            return self._colors.text_disabled[:3]
        elif variant == "secondary":
            # Mix between primary and disabled
            p = self._colors.text
            d = self._colors.text_disabled
            return (
                (p[0] + d[0]) // 2,
                (p[1] + d[1]) // 2,
                (p[2] + d[2]) // 2,
            )
        else:
            return self._colors.text[:3]


# Global theme manager instance
_theme_manager: ThemeManager | None = None


def get_theme_manager() -> ThemeManager:
    """Get the global theme manager instance."""
    global _theme_manager
    if _theme_manager is None:
        _theme_manager = ThemeManager()
    return _theme_manager


def apply_theme(theme_name: str) -> None:
    """Apply a theme to the application.

    Args:
        theme_name: Theme name ('dark' or 'light')
    """
    get_theme_manager().apply_theme(theme_name)


def get_status_color(level: str) -> tuple[int, int, int]:
    """Get color for a status level.

    Args:
        level: Status level ('info', 'success', 'warning', 'error')

    Returns:
        RGB color tuple
    """
    return get_theme_manager().get_status_color(level)


def get_accent_color() -> tuple[int, int, int]:
    """Get the accent color for highlights."""
    return get_theme_manager().get_accent_color()


def get_text_color(variant: str = "primary") -> tuple[int, int, int]:
    """Get text color variant.

    Args:
        variant: 'primary', 'secondary', or 'disabled'

    Returns:
        RGB color tuple
    """
    return get_theme_manager().get_text_color(variant)


def get_current_theme() -> str:
    """Get current theme name."""
    return get_theme_manager().current_theme
