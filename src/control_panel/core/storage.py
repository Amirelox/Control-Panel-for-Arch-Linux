"""Filesystem information, large-file scanning and cache maintenance."""

from __future__ import annotations

import heapq
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import psutil

from .fs import is_under, remove_directory_contents

__all__ = [
    "FileSystem",
    "clear_user_cache",
    "filesystems",
    "scan_large_files",
    "user_cache",
]


@dataclass(frozen=True, slots=True)
class FileSystem:
    device: str
    mount: str
    fstype: str
    total: int
    used: int
    free: int
    percent: float


_PSEUDO_TYPES = {
    "tmpfs",
    "devtmpfs",
    "devfs",
    "proc",
    "sysfs",
    "cgroup",
    "cgroup2",
    "overlay",
    "squashfs",
    "ramfs",
    "autofs",
    "mqueue",
    "debugfs",
    "tracefs",
    "securityfs",
    "pstore",
    "bpf",
    "configfs",
    "fusectl",
    "hugetlbfs",
    "binfmt_misc",
    "efivarfs",
}


def filesystems() -> list[FileSystem]:
    result: list[FileSystem] = []
    seen_mounts: set[str] = set()
    for partition in psutil.disk_partitions(all=False):
        if partition.fstype in _PSEUDO_TYPES or partition.mountpoint in seen_mounts:
            continue
        try:
            usage = psutil.disk_usage(partition.mountpoint)
        except (PermissionError, OSError):
            continue
        seen_mounts.add(partition.mountpoint)
        result.append(
            FileSystem(
                device=partition.device,
                mount=partition.mountpoint,
                fstype=partition.fstype,
                total=usage.total,
                used=usage.used,
                free=usage.free,
                percent=usage.percent,
            )
        )
    result.sort(key=lambda entry: (entry.mount != "/", entry.mount))
    return result


def user_cache() -> Path:
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")).expanduser()


def clear_user_cache() -> tuple[int, int]:
    cache = user_cache().resolve()
    # Never wipe the home directory or a filesystem root because of a bad
    # XDG_CACHE_HOME value.
    if cache in {Path("/"), Path.home().resolve()}:
        return 0, 0
    if not is_under(cache, Path.home()):
        return 0, 0
    return remove_directory_contents(cache)


def scan_large_files(
    root: Path | None = None,
    *,
    limit: int = 40,
    max_files: int = 250_000,
    progress: Callable[[int, str], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> tuple[list[tuple[int, Path]], int, bool]:
    """Return the largest files under *root*.

    The scan is bounded by ``max_files`` so it cannot run forever on very large
    home directories. Symlinks are not followed.
    """
    base = (root or Path.home()).expanduser()
    heap: list[tuple[int, str]] = []
    scanned = 0
    truncated = False
    for dirpath, dirnames, filenames in os.walk(base, followlinks=False, onerror=lambda _e: None):
        dirnames[:] = [name for name in dirnames if name not in {".git", "node_modules"}]
        if should_stop is not None and should_stop():
            break
        for name in filenames:
            path = Path(dirpath) / name
            try:
                if path.is_symlink():
                    continue
                size = path.stat().st_size
            except OSError:
                continue
            scanned += 1
            if len(heap) < limit:
                heapq.heappush(heap, (size, str(path)))
            elif size > heap[0][0]:
                heapq.heapreplace(heap, (size, str(path)))
            if progress is not None and scanned % 2000 == 0:
                progress(scanned, str(path))
            if scanned >= max_files:
                truncated = True
                break
        if truncated:
            break
    result = [(size, Path(path)) for size, path in sorted(heap, reverse=True)]
    if progress is not None:
        progress(scanned, "")
    return result, scanned, truncated
