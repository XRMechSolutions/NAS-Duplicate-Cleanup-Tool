"""Documentation panel for in-app help content."""

import re
from pathlib import Path

import dearpygui.dearpygui as dpg

from duplicleaner.ui.theme import get_accent_color, get_text_color
from duplicleaner.utils.logging import get_logger

logger = get_logger(__name__)


class DocumentationPanel:
    """In-app documentation viewer with chapter selection."""

    TAG_CHAPTER_LIST = "doc_chapter_list"
    TAG_CONTENT = "doc_content"
    TAG_STATUS = "doc_status"
    TAG_CONTENT_CONTAINER = "doc_content_container"
    TAG_TEXTURE_REGISTRY = "doc_texture_registry"

    def __init__(
        self,
        parent: str,
        docs_dir: Path | None = None,
        fonts: dict[str, str] | None = None,
    ) -> None:
        self.parent = parent
        self.docs_dir = docs_dir or self._resolve_docs_dir()
        self._chapters = self._build_chapters()
        self._current_chapter: str | None = None
        self._current_markdown: str = ""
        self._image_textures: dict[str, str] = {}
        self._wrap_width = 900
        self._fonts = fonts or {}

    def _resolve_docs_dir(self) -> Path:
        current = Path(__file__).resolve()
        for parent in current.parents:
            if (parent / "pyproject.toml").exists():
                return parent / "docs"
        return current.parents[2] / "docs"

    def build(self) -> None:
        with dpg.group(horizontal=True, parent=self.parent):
            with dpg.child_window(width=220, height=-1, border=True):
                dpg.add_text("Chapters")
                dpg.add_listbox(
                    tag=self.TAG_CHAPTER_LIST,
                    items=list(self._chapters.keys()),
                    num_items=18,
                    callback=self._on_select,
                )
                dpg.add_spacer(height=6)
                dpg.add_text("", tag=self.TAG_STATUS, color=get_text_color("secondary"))

            with dpg.child_window(width=-1, height=-1, border=True):
                dpg.add_text("Documentation")
                dpg.add_separator()
                with dpg.child_window(
                    tag=self.TAG_CONTENT_CONTAINER,
                    width=-1,
                    height=-1,
                    border=False,
                    autosize_x=True,
                    autosize_y=True,
                ):
                    dpg.add_text("Select a chapter to view documentation.", tag=self.TAG_CONTENT)

        with dpg.texture_registry(tag=self.TAG_TEXTURE_REGISTRY):
            pass

        # Load default chapter (User Guide) if available
        if "User Guide" in self._chapters:
            dpg.set_value(self.TAG_CHAPTER_LIST, "User Guide")
            self._load_chapter("User Guide")

        # No extra status for renderer here; content renders inline.

    def _build_chapters(self) -> dict[str, Path]:
        return {
            "User Guide": self.docs_dir / "USER_GUIDE.md",
            "Drives & Scanning": self.docs_dir / "01-scanner.md",
            "Hashing": self.docs_dir / "02-hasher.md",
            "Duplicate Detection": self.docs_dir / "03-duplicate-detection.md",
            "Duplicate Resolution": self.docs_dir / "08-duplicate-resolution.md",
            "File Operations": self.docs_dir / "09-file-operations.md",
            "Photo Organization": self.docs_dir / "05-photo-organization.md",
            "Faces & Pets": self.docs_dir / "06-face-recognition.md",
            "AI Content Analysis": self.docs_dir / "07-ai-content-analysis.md",
            "Search": self.docs_dir / "11-user-interface.md",
            "Settings & UI": self.docs_dir / "11-user-interface.md",
            "Database": self.docs_dir / "10-database.md",
            "Versioning": self.docs_dir / "12-document-versioning.md",
        }

    def _on_select(self, sender, app_data) -> None:
        if not app_data:
            return
        self._load_chapter(app_data)

    def _load_chapter(self, chapter: str) -> None:
        path = self._chapters.get(chapter)
        if not path:
            self._set_status("Chapter not found.", error=True)
            return

        if not path.exists():
            self._set_status(f"Missing file: {path.name}", error=True)
            dpg.set_value(self.TAG_CONTENT, "")
            return

        try:
            content = path.read_text(encoding="utf-8")
        except Exception as exc:
            logger.warning("Failed to read documentation: %s", exc)
            self._set_status("Failed to read documentation.", error=True)
            dpg.set_value(self.TAG_CONTENT, "")
            return

        normalized = self._normalize_markdown(content)
        dpg.set_value(self.TAG_CONTENT, normalized)
        self._render_markdown_to_dpg(content)
        self._set_status(f"Loaded: {path.name}", error=False)
        self._current_chapter = chapter
        self._current_markdown = content

    def _normalize_markdown(self, content: str) -> str:
        # Replace markdown image tags with a readable placeholder line.
        lines = []
        for line in content.splitlines():
            if line.strip().startswith("!"):
                lines.append(f"[Image placeholder] {line.strip()}")
            else:
                lines.append(line)
        return "\n".join(lines)

    def _set_status(self, message: str, error: bool = False) -> None:
        color = (255, 120, 120) if error else (180, 180, 180)
        dpg.set_value(self.TAG_STATUS, message)
        dpg.configure_item(self.TAG_STATUS, color=color)

    def _render_markdown_to_dpg(self, content: str) -> None:
        # Clear previous content
        children = dpg.get_item_children(self.TAG_CONTENT_CONTAINER, slot=1)
        if children:
            for child in children:
                dpg.delete_item(child)

        in_code_block = False
        code_lines: list[str] = []

        list_number_re = re.compile(r"^(\d+)\.\s+(.*)")

        for line in content.splitlines():
            stripped = line.strip()

            if stripped.startswith("```"):
                if in_code_block:
                    dpg.add_input_text(
                        multiline=True,
                        readonly=True,
                        width=-1,
                        height=min(200, 20 * max(1, len(code_lines))),
                        default_value="\n".join(code_lines),
                        parent=self.TAG_CONTENT_CONTAINER,
                    )
                    code_lines = []
                in_code_block = not in_code_block
                continue

            if in_code_block:
                code_lines.append(line)
                continue

            if stripped.startswith("# "):
                dpg.add_spacer(height=6, parent=self.TAG_CONTENT_CONTAINER)
                dpg.add_text(
                    stripped[2:].upper(),
                    parent=self.TAG_CONTENT_CONTAINER,
                    color=get_accent_color(),
                )
                if self._fonts.get("h1"):
                    dpg.bind_item_font(dpg.last_item(), self._fonts["h1"])
                dpg.add_separator(parent=self.TAG_CONTENT_CONTAINER)
                dpg.add_spacer(height=4, parent=self.TAG_CONTENT_CONTAINER)
                continue

            if stripped.startswith("## "):
                dpg.add_spacer(height=4, parent=self.TAG_CONTENT_CONTAINER)
                dpg.add_text(
                    stripped[3:],
                    parent=self.TAG_CONTENT_CONTAINER,
                    color=get_accent_color(),
                )
                if self._fonts.get("h2"):
                    dpg.bind_item_font(dpg.last_item(), self._fonts["h2"])
                continue

            if stripped.startswith("### "):
                dpg.add_text(
                    stripped[4:],
                    parent=self.TAG_CONTENT_CONTAINER,
                    color=get_accent_color(),
                )
                if self._fonts.get("h3"):
                    dpg.bind_item_font(dpg.last_item(), self._fonts["h3"])
                continue

            img_match = re.match(r"!\[(.*?)\]\((.*?)\)", stripped)
            if img_match:
                alt, path_str = img_match.groups()
                self._render_image(alt, path_str)
                continue

            num_match = list_number_re.match(stripped)
            if num_match:
                idx, text = num_match.groups()
                dpg.add_text(
                    f"  {idx}. {text}",
                    parent=self.TAG_CONTENT_CONTAINER,
                    wrap=self._wrap_width,
                )
                if self._fonts.get("body"):
                    dpg.bind_item_font(dpg.last_item(), self._fonts["body"])
                continue

            if stripped.startswith("- ") or stripped.startswith("* "):
                dpg.add_text(
                    f"  * {stripped[2:]}",
                    parent=self.TAG_CONTENT_CONTAINER,
                    wrap=self._wrap_width,
                )
                if self._fonts.get("body"):
                    dpg.bind_item_font(dpg.last_item(), self._fonts["body"])
                continue

            if stripped.startswith(">"):
                quote = stripped.lstrip(">").strip()
                dpg.add_text(
                    f"\"{quote}\"",
                    parent=self.TAG_CONTENT_CONTAINER,
                    color=get_text_color("secondary"),
                    wrap=self._wrap_width,
                )
                if self._fonts.get("body"):
                    dpg.bind_item_font(dpg.last_item(), self._fonts["body"])
                continue

            if stripped == "---":
                dpg.add_separator(parent=self.TAG_CONTENT_CONTAINER)
                continue

            if stripped == "":
                dpg.add_spacer(height=4, parent=self.TAG_CONTENT_CONTAINER)
                continue

            dpg.add_text(line, parent=self.TAG_CONTENT_CONTAINER, wrap=self._wrap_width)
            if self._fonts.get("body"):
                dpg.bind_item_font(dpg.last_item(), self._fonts["body"])

        if code_lines:
            dpg.add_input_text(
                multiline=True,
                readonly=True,
                width=-1,
                height=min(200, 20 * max(1, len(code_lines))),
                default_value="\n".join(code_lines),
                parent=self.TAG_CONTENT_CONTAINER,
            )
            if self._fonts.get("body"):
                dpg.bind_item_font(dpg.last_item(), self._fonts["body"])

    def _render_image(self, alt: str, path_str: str) -> None:
        image_path = (self.docs_dir / path_str).resolve()
        if not image_path.exists():
            dpg.add_text(f"[Image missing] {alt} ({path_str})", parent=self.TAG_CONTENT_CONTAINER)
            return

        key = str(image_path)
        if key not in self._image_textures:
            try:
                width, height, channels, data = dpg.load_image(str(image_path))
                tex_tag = f"doc_tex_{len(self._image_textures)}"
                dpg.add_static_texture(
                    width,
                    height,
                    data,
                    tag=tex_tag,
                    parent=self.TAG_TEXTURE_REGISTRY,
                )
                self._image_textures[key] = tex_tag
            except Exception as exc:
                logger.warning("Failed to load image %s: %s", image_path, exc)
                dpg.add_text(f"[Image load failed] {alt}", parent=self.TAG_CONTENT_CONTAINER)
                return

        dpg.add_image(self._image_textures[key], parent=self.TAG_CONTENT_CONTAINER)
