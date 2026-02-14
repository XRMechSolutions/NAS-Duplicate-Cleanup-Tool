"""Document version tracking using Git.

Provides Git-backed history for tracked folders and files.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from duplicleaner.utils.logging import get_logger

logger = get_logger(__name__)

# Try to import GitPython
GIT_AVAILABLE = False

try:
    from git import GitCommandError, InvalidGitRepositoryError, NoSuchPathError, Repo
    GIT_AVAILABLE = True
except ImportError:
    logger.warning("GitPython not available. Version tracking disabled.")


DEFAULT_EXCLUDE_PATTERNS = [
    "*.tmp",
    "*.bak",
    "*.swp",
    "~*",
    "Thumbs.db",
    ".DS_Store",
    "*.lock",
    "*.log",
]


@dataclass
class VersionEntry:
    """Represents a file version entry from Git history."""
    commit_hash: str
    committed_at: datetime
    author: str
    message: str
    file_path: str
    size_bytes: int | None = None
    insertions: int | None = None
    deletions: int | None = None


@dataclass
class ChangeEntry:
    """Represents a recent change in a repository."""
    commit_hash: str
    committed_at: datetime
    author: str
    message: str
    file_path: str


class VersionTracker:
    """Git-backed version tracking for files and folders."""

    def __init__(
        self,
        root_path: str | Path,
        include_patterns: list[str] | None = None,
        exclude_patterns: list[str] | None = None,
        include_subfolders: bool = True,
        max_file_size_mb: float = 50.0,
    ) -> None:
        """Initialize version tracker.

        Args:
            root_path: Folder to track
            include_patterns: Glob patterns to include (None = all)
            exclude_patterns: Glob patterns to exclude
            include_subfolders: Track files in subfolders
            max_file_size_mb: Skip files larger than this
        """
        self.root_path = Path(root_path)
        self.include_patterns = include_patterns
        self.exclude_patterns = exclude_patterns or DEFAULT_EXCLUDE_PATTERNS
        self.include_subfolders = include_subfolders
        self.max_file_size_bytes = int(max_file_size_mb * 1024 * 1024)

        self._repo: Repo | None = None

    def is_available(self) -> bool:
        """Check if GitPython is available."""
        return GIT_AVAILABLE

    def _get_repo(self) -> Repo | None:
        if not self.is_available():
            return None

        if self._repo is not None:
            return self._repo

        try:
            self._repo = Repo(self.root_path)
            return self._repo
        except (InvalidGitRepositoryError, NoSuchPathError):
            return None

    def init_repository(self) -> bool:
        """Initialize a Git repository in the root path.

        Returns:
            True if initialized or already exists
        """
        if not self.is_available():
            return False

        if self._get_repo() is not None:
            self._ensure_gitignore()
            return True

        try:
            self.root_path.mkdir(parents=True, exist_ok=True)
            self._repo = Repo.init(self.root_path)
            self._ensure_gitignore()
            logger.info(f"Initialized version tracking repo at {self.root_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to init repository: {e}")
            return False

    def _iter_files(self) -> Iterable[Path]:
        """Iterate files in the tracked folder respecting filters."""
        if self.include_subfolders:
            iterator = self.root_path.rglob("*")
        else:
            iterator = self.root_path.glob("*")

        for path in iterator:
            if not path.is_file():
                continue
            if ".git" in path.parts:
                continue
            if not self._should_track(path):
                continue
            yield path

    def list_tracked_files(self) -> list[Path]:
        """Return a list of tracked files."""
        return list(self._iter_files())

    def _should_track(self, path: Path) -> bool:
        """Check if a file should be tracked."""
        try:
            if path.stat().st_size > self.max_file_size_bytes:
                return False
        except OSError:
            return False

        if self.include_patterns and not any(path.match(pattern) for pattern in self.include_patterns):
            return False

        return not (self.exclude_patterns and any(path.match(pattern) for pattern in self.exclude_patterns))

    def initial_commit(self, message: str = "Initial version tracking") -> bool:
        """Create initial commit for tracked files."""
        repo = self._get_repo()
        if repo is None:
            if not self.init_repository():
                return False
            repo = self._get_repo()
            if repo is None:
                return False

        files = [str(p.relative_to(self.root_path)) for p in self._iter_files()]
        if not files:
            logger.info("No files found for initial commit")
            return False

        try:
            repo.index.add(files)
            if repo.is_dirty():
                repo.index.commit(message)
                return True
            return False
        except GitCommandError as e:
            logger.error(f"Initial commit failed: {e}")
            return False

    def commit_all(self, message: str, allow_empty: bool = False) -> bool:
        """Commit all changes in the repo.

        Args:
            message: Commit message
            allow_empty: Allow empty commits
        """
        repo = self._get_repo()
        if repo is None:
            return False

        try:
            self._ensure_gitignore()

            tracked_files = [
                str(path.relative_to(self.root_path))
                for path in self.list_tracked_files()
            ]

            existing_tracked = repo.git.ls_files().splitlines()
            deleted = [path for path in existing_tracked if path not in tracked_files]

            if tracked_files:
                repo.index.add(tracked_files)
            if deleted:
                repo.index.remove(deleted, working_tree=True)

            if not repo.is_dirty() and not allow_empty:
                return False
            repo.index.commit(message)
            return True
        except GitCommandError as e:
            logger.error(f"Commit failed: {e}")
            return False

    def commit_files(self, paths: Iterable[str | Path], message: str) -> bool:
        """Commit specific files.

        Args:
            paths: File paths to commit (absolute or relative)
            message: Commit message
        """
        repo = self._get_repo()
        if repo is None:
            return False

        rel_paths: list[str] = []
        for item in paths:
            path = Path(item)
            if path.is_absolute():
                try:
                    path = path.relative_to(self.root_path)
                except ValueError:
                    continue
            if ".git" in path.parts:
                continue
            if self._should_track(self.root_path / path):
                rel_paths.append(str(path))

        if not rel_paths:
            return False

        try:
            self._ensure_gitignore()
            repo.index.add(rel_paths)
            if not repo.is_dirty():
                return False
            repo.index.commit(message)
            return True
        except GitCommandError as e:
            logger.error(f"Commit failed: {e}")
            return False

    def get_file_history(self, file_path: str | Path, limit: int = 50) -> list[VersionEntry]:
        """Get version history for a file."""
        repo = self._get_repo()
        if repo is None:
            return []

        rel_path = Path(file_path)
        if rel_path.is_absolute():
            try:
                rel_path = rel_path.relative_to(self.root_path)
            except ValueError:
                return []

        history: list[VersionEntry] = []
        try:
            commits = list(repo.iter_commits(paths=str(rel_path), max_count=limit))
            for commit in commits:
                stats = commit.stats.files.get(str(rel_path))
                size_bytes = None
                try:
                    blob = commit.tree / str(rel_path)
                    size_bytes = blob.size
                except Exception:
                    size_bytes = None

                history.append(
                    VersionEntry(
                        commit_hash=commit.hexsha,
                        committed_at=datetime.fromtimestamp(commit.committed_date),
                        author=str(commit.author),
                        message=commit.message.strip(),
                        file_path=str(rel_path),
                        size_bytes=size_bytes,
                        insertions=stats.get("insertions") if stats else None,
                        deletions=stats.get("deletions") if stats else None,
                    )
                )
        except GitCommandError as e:
            logger.error(f"Failed to read history: {e}")

        return history

    def get_recent_changes(self, limit: int = 100) -> list[ChangeEntry]:
        """Get recent changes across the repository."""
        repo = self._get_repo()
        if repo is None:
            return []

        changes: list[ChangeEntry] = []

        try:
            commits = list(repo.iter_commits(max_count=limit))
            for commit in commits:
                for file_path in commit.stats.files:
                    changes.append(
                        ChangeEntry(
                            commit_hash=commit.hexsha,
                            committed_at=datetime.fromtimestamp(commit.committed_date),
                            author=str(commit.author),
                            message=commit.message.strip(),
                            file_path=file_path,
                        )
                    )
        except GitCommandError as e:
            logger.error(f"Failed to read recent changes: {e}")

        return changes

    def diff_versions(
        self,
        file_path: str | Path,
        from_commit: str,
        to_commit: str,
    ) -> str:
        """Get diff between two versions of a file."""
        repo = self._get_repo()
        if repo is None:
            return ""

        rel_path = Path(file_path)
        if rel_path.is_absolute():
            try:
                rel_path = rel_path.relative_to(self.root_path)
            except ValueError:
                return ""

        try:
            return repo.git.diff(from_commit, to_commit, "--", str(rel_path))
        except GitCommandError as e:
            logger.error(f"Diff failed: {e}")
            return ""

    def restore_file(
        self,
        file_path: str | Path,
        commit_hash: str,
        message: str | None = None,
        allow_dirty: bool = False,
    ) -> bool:
        """Restore a file to a specific version and commit the restore.

        Args:
            file_path: File to restore
            commit_hash: Commit to restore from
            message: Commit message for the restore
            allow_dirty: Allow restore with dirty working tree
        """
        repo = self._get_repo()
        if repo is None:
            return False

        if repo.is_dirty(untracked_files=True) and not allow_dirty:
            logger.warning("Repo has uncommitted changes; aborting restore")
            return False

        rel_path = Path(file_path)
        if rel_path.is_absolute():
            try:
                rel_path = rel_path.relative_to(self.root_path)
            except ValueError:
                return False

        try:
            repo.git.checkout(commit_hash, "--", str(rel_path))
            repo.index.add([str(rel_path)])
            commit_message = message or f"Restore {rel_path} to {commit_hash[:8]}"
            repo.index.commit(commit_message)
            return True
        except GitCommandError as e:
            logger.error(f"Restore failed: {e}")
            return False

    def get_repository_size_bytes(self) -> int:
        """Get size of the .git directory in bytes."""
        git_dir = self.root_path / ".git"
        if not git_dir.exists():
            return 0

        total = 0
        for path in git_dir.rglob("*"):
            try:
                if path.is_file():
                    total += path.stat().st_size
            except OSError:
                continue
        return total

    def optimize_repository(self) -> bool:
        """Run git garbage collection to optimize storage."""
        repo = self._get_repo()
        if repo is None:
            return False

        try:
            repo.git.gc("--aggressive")
            return True
        except GitCommandError as e:
            logger.error(f"Git GC failed: {e}")
            return False

    def _ensure_gitignore(self) -> None:
        """Ensure .gitignore includes default exclude patterns."""
        try:
            gitignore = self.root_path / ".gitignore"
            existing: set[str] = set()
            if gitignore.exists():
                with open(gitignore, encoding="utf-8") as handle:
                    existing = {line.strip() for line in handle if line.strip()}

            lines: list[str] = []
            for pattern in self.exclude_patterns or []:
                if pattern not in existing:
                    lines.append(pattern)

            if lines:
                with open(gitignore, "a", encoding="utf-8") as handle:
                    if existing:
                        handle.write("\n")
                    handle.write("\n".join(lines))
                    handle.write("\n")
        except Exception as e:
            logger.warning(f"Failed to update .gitignore: {e}")
