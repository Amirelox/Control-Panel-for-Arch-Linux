"""Small, safe file-system helpers."""

from __future__ import annotations

import os
import shutil
import stat
import tempfile
from pathlib import Path


def read_text(path: str | Path, default: str = "") -> str:
    """Read a UTF-8 text file, returning *default* on any error."""
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except (OSError, ValueError):
        return default


def backup_file(path: str | Path) -> Path | None:
    """Keep a single ``<file>.bak`` copy next to *path*.

    Returns the backup path, or ``None`` if there was nothing to back up or
    the backup could not be created.
    """
    source = Path(path)
    if not source.is_file():
        return None
    target = source.with_name(source.name + ".bak")
    try:
        shutil.copy2(source, target)
        return target
    except OSError:
        return None


def write_text_atomic(
    path: str | Path,
    text: str,
    *,
    backup: bool = True,
    encoding: str = "utf-8",
) -> Path:
    """Write *text* atomically, optionally keeping a ``.bak`` copy.

    The temporary file lives in the destination directory so ``os.replace``
    stays on the same filesystem and is therefore atomic.
    """
    destination = Path(path).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)

    existing_mode: int | None = None
    try:
        existing_mode = stat.S_IMODE(destination.stat().st_mode)
    except OSError:
        pass

    if backup:
        backup_file(destination)

    fd, temp_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=str(destination.parent)
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        if existing_mode is not None:
            os.chmod(temp_path, existing_mode)
        os.replace(temp_path, destination)
    except BaseException:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    return destination


def is_under(path: str | Path, root: str | Path) -> bool:
    """Return True when *path* resolves to *root* or a descendant of it."""
    try:
        candidate = Path(path).expanduser().resolve()
        base = Path(root).expanduser().resolve()
    except OSError:
        return False
    return candidate == base or base in candidate.parents


def remove_directory_contents(path: str | Path) -> tuple[int, int]:
    """Delete the *contents* of a directory, never the directory itself.

    Symlinks are unlinked instead of followed. Returns ``(files, bytes)``.
    This is used by the cache cleaner and is intentionally conservative.
    """
    root = Path(path).expanduser()
    try:
        if root.resolve() == Path("/"):
            return 0, 0
    except OSError:
        return 0, 0
    if not root.is_dir() or root.is_symlink():
        return 0, 0

    removed_files = 0
    removed_bytes = 0
    for child in list(root.iterdir()):
        try:
            if child.is_symlink() or child.is_file():
                size = child.lstat().st_size
                child.unlink()
                removed_files += 1
                removed_bytes += size
            elif child.is_dir():
                for dirpath, _dirnames, filenames in os.walk(child, topdown=True):
                    for name in filenames:
                        file_path = Path(dirpath) / name
                        try:
                            if file_path.is_symlink():
                                size = file_path.lstat().st_size
                                file_path.unlink()
                            else:
                                size = file_path.stat().st_size
                                file_path.unlink()
                            removed_files += 1
                            removed_bytes += size
                        except OSError:
                            continue
                shutil.rmtree(child, ignore_errors=True)
        except OSError:
            continue
    return removed_files, removed_bytes


def directory_size(path: str | Path) -> int:
    """Return the apparent size of a directory tree, ignoring errors."""
    total = 0
    root = Path(path).expanduser()
    for dirpath, _dirnames, filenames in os.walk(root, onerror=lambda _e: None):
        for name in filenames:
            try:
                total += (Path(dirpath) / name).lstat().st_size
            except OSError:
                continue
    return total
