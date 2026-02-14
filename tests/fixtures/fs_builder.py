from __future__ import annotations

import os
import random
import shutil
import stat
from dataclasses import dataclass
from pathlib import Path

from PIL import Image


@dataclass(frozen=True)
class FixturePaths:
    root: Path
    files: dict[str, Path]
    groups: dict[str, list[Path]]


def build_test_tree(
    root: Path,
    *,
    seed: int = 1337,
    include_long_paths: bool = False,
    include_permissions: bool = True,
    extra_files: int = 0,
    large_file_size: int = 5 * 1024 * 1024,
) -> FixturePaths:
    """
    Build a deterministic test tree under root and return key file/group paths.

    The tree includes:
    - exact duplicates (binary files)
    - near-duplicate images (1-pixel difference)
    - zero-byte file
    - large file (repeatable data)
    - same-name files in different dirs
    - EXIF-stamped image and non-EXIF image
    - optional long path and read-only file
    """
    rng = random.Random(seed)
    root.mkdir(parents=True, exist_ok=True)

    files: dict[str, Path] = {}
    groups: dict[str, list[Path]] = {}

    # Base directories
    a_dir = root / "alpha"
    b_dir = root / "beta"
    c_dir = root / "gamma"
    images_dir = root / "images"
    nested_dir = root / "nested" / "deep" / "path"
    for d in (a_dir, b_dir, c_dir, images_dir, nested_dir):
        d.mkdir(parents=True, exist_ok=True)

    # Exact duplicates (binary)
    blob = _deterministic_bytes(rng, 4096)
    dup1 = a_dir / "dup.bin"
    dup2 = b_dir / "dup_copy.bin"
    dup3 = nested_dir / "dup_nested.bin"
    for p in (dup1, dup2, dup3):
        _write_bytes(p, blob)
    groups["exact_dupes"] = [dup1, dup2, dup3]
    files["dup1"] = dup1
    files["dup2"] = dup2
    files["dup3"] = dup3

    # Same name different dirs (non-dupes)
    same_name_a = a_dir / "same_name.txt"
    same_name_b = b_dir / "same_name.txt"
    _write_text(same_name_a, "alpha")
    _write_text(same_name_b, "beta")
    files["same_name_a"] = same_name_a
    files["same_name_b"] = same_name_b

    # Zero-byte file
    zero = c_dir / "zero.dat"
    zero.touch()
    files["zero"] = zero

    # Large file
    large = c_dir / "large.bin"
    _write_repeatable_bytes(large, large_file_size)
    files["large"] = large

    # Images: exact duplicate + near-duplicate
    base_img = images_dir / "base.jpg"
    dup_img = images_dir / "base_copy.jpg"
    near_img = images_dir / "base_near.jpg"
    _write_image(base_img, size=(256, 256), color=(30, 140, 200), exif_dt="2022:08:09 10:11:12")
    shutil.copy2(base_img, dup_img)
    _write_image(
        near_img,
        size=(256, 256),
        color=(30, 140, 200),
        exif_dt=None,
        tweak_pixel=True,
    )
    groups["image_exact_dupes"] = [base_img, dup_img]
    groups["image_near_dupes"] = [base_img, near_img]
    files["base_img"] = base_img
    files["dup_img"] = dup_img
    files["near_img"] = near_img

    # Non-EXIF image
    no_exif = images_dir / "no_exif.png"
    _write_image(no_exif, size=(128, 128), color=(10, 10, 10), exif_dt=None)
    files["no_exif"] = no_exif

    # Read-only file (best-effort)
    if include_permissions:
        ro = a_dir / "readonly.txt"
        _write_text(ro, "read-only")
        _make_readonly(ro)
        files["readonly"] = ro

    # Optional long path
    if include_long_paths:
        long_dir = _make_long_path_dir(root)
        long_file = long_dir / "long_file.txt"
        _write_text(long_file, "long path file")
        files["long_path_file"] = long_file

    # Optional bulk files for performance testing
    if extra_files > 0:
        bulk_dir = root / "bulk"
        bulk_dir.mkdir(parents=True, exist_ok=True)
        for i in range(extra_files):
            data = _deterministic_bytes(rng, 256)
            path = bulk_dir / f"file_{i:05d}.bin"
            _write_bytes(path, data)

    return FixturePaths(root=root, files=files, groups=groups)


def _write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _deterministic_bytes(rng: random.Random, size: int) -> bytes:
    return bytes(rng.randrange(0, 256) for _ in range(size))


def _write_repeatable_bytes(path: Path, size: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    block = b"DUCLEAN" * 1024
    remaining = size
    with path.open("wb") as f:
        while remaining > 0:
            chunk = block[: min(len(block), remaining)]
            f.write(chunk)
            remaining -= len(chunk)


def _write_image(
    path: Path,
    *,
    size: tuple[int, int],
    color: tuple[int, int, int],
    exif_dt: str | None,
    tweak_pixel: bool = False,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", size, color)
    if tweak_pixel:
        img.putpixel((0, 0), (color[0] ^ 0x11, color[1], color[2]))
    exif = img.getexif()
    if exif_dt is not None:
        exif[36867] = exif_dt  # DateTimeOriginal
    img.save(path, exif=exif)


def _make_readonly(path: Path) -> None:
    try:
        os.chmod(path, stat.S_IREAD)
    except OSError:
        # Best-effort; on some systems/FS this may not apply.
        return


def _make_long_path_dir(root: Path) -> Path:
    # Aim for a path length near Windows default limits without requiring \\?\
    segment = "deep" * 6
    long_dir = root
    target_length = 230

    while len(str(long_dir)) < target_length:
        candidate = long_dir / segment
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            long_dir = candidate
        except OSError:
            break

    if not long_dir.exists():
        long_dir.mkdir(parents=True, exist_ok=True)

    return long_dir
