"""Wallpaper discovery and application (awww/swww/hyprpaper/swaybg)."""

from __future__ import annotations

import os
from pathlib import Path

from .commands import run, spawn, which
from .config import cache_dir, wallpaper_cache_file, wallpaper_dirs
from .fs import read_text, write_text_atomic
from .hyprland import hyprctl

__all__ = [
    "apply_wallpaper",
    "current_wallpaper",
    "directories",
    "find_wallpapers",
    "regenerate_colours",
    "wallpaper_backend",
]

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".avif"}


def find_wallpapers(directories: list[Path] | None = None, *, limit: int = 800) -> list[Path]:
    roots = directories or wallpaper_dirs()
    result: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        if not root.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [name for name in dirnames if not name.startswith(".")]
            for name in filenames:
                path = Path(dirpath) / name
                if path.suffix.lower() not in IMAGE_SUFFIXES:
                    continue
                try:
                    resolved = path.resolve()
                except OSError:
                    continue
                if resolved in seen:
                    continue
                seen.add(resolved)
                result.append(path)
                if len(result) >= limit:
                    return sorted(result, key=lambda item: item.name.lower())
    return sorted(result, key=lambda item: item.name.lower())


def directories() -> list[Path]:
    return wallpaper_dirs()


def current_wallpaper() -> Path | None:
    cached = read_text(wallpaper_cache_file()).strip()
    if cached and Path(cached).is_file():
        return Path(cached)
    return None


def wallpaper_backend() -> str:
    for name in ("awww", "swww", "hyprpaper", "swaybg"):
        if which(name):
            return name
    return ""


def _make_avatar(path: Path) -> None:
    magick = which("magick")
    if magick is None:
        return
    target = Path.home() / ".config" / "hypr" / "avatar.png"
    target.parent.mkdir(parents=True, exist_ok=True)
    run(
        [
            magick,
            str(path),
            "-resize",
            "512x512^",
            "-gravity",
            "center",
            "-extent",
            "512x512",
            str(target),
        ],
        timeout=20,
    )


def apply_wallpaper(path: str | Path, *, regenerate_colours: bool = True) -> tuple[bool, str]:
    """Apply a wallpaper and optionally regenerate the Matugen palette."""
    image = Path(path).expanduser()
    if not image.is_file():
        return False, f"Wallpaper not found: {image}"
    if image.suffix.lower() not in IMAGE_SUFFIXES:
        return False, f"Unsupported image format: {image.suffix}"

    backend = wallpaper_backend()
    if backend in {"awww", "swww"}:
        result = run(
            [
                backend,
                "img",
                str(image),
                "--transition-type",
                "grow",
                "--transition-pos",
                "center",
                "--transition-duration",
                "1.1",
                "--transition-fps",
                "60",
            ],
            timeout=20,
        )
        if not result.ok:
            return False, result.summary()
    elif backend == "hyprpaper":
        hyprctl("hyprpaper", "unload", "all", timeout=8)
        hyprctl("hyprpaper", "preload", str(image), timeout=8)
        result = hyprctl("hyprpaper", "wallpaper", f",{image}", timeout=8)
        if not result.ok:
            return False, result.summary()
    elif backend == "swaybg":
        run(["pkill", "-x", "swaybg"], timeout=4)
        if spawn(["swaybg", "-i", str(image)]) is None:
            return False, "Could not start swaybg"
    else:
        return False, ("No wallpaper backend found. Install awww, swww, hyprpaper or swaybg.")

    try:
        wallpaper_cache_file().parent.mkdir(parents=True, exist_ok=True)
        write_text_atomic(wallpaper_cache_file(), str(image) + "\n", backup=False)
    except OSError:
        pass

    _make_avatar(image)

    if regenerate_colours:
        matugen = which("matugen")
        if matugen:
            run([matugen, "image", str(image), "--source-color-index", "0"], timeout=90)

    if which("hyprctl"):
        hyprctl("reload", timeout=10)
    if which("qs"):
        run(["qs", "ipc", "-c", "amir", "call", "amir", "reload"], timeout=6)

    return True, f"Wallpaper applied: {image.name}"


def regenerate_colours(path: str | Path | None = None) -> tuple[bool, str]:
    """Run Matugen for *path* (or the current wallpaper) and reload clients."""
    image = Path(path).expanduser() if path else current_wallpaper()
    if image is None or not image.is_file():
        return False, "No wallpaper selected."
    matugen = which("matugen")
    if matugen is None:
        return False, "matugen is not installed."
    result = run([matugen, "image", str(image), "--source-color-index", "0"], timeout=90)
    if not result.ok:
        return False, result.summary()
    if which("hyprctl"):
        hyprctl("reload", timeout=10)
    if which("qs"):
        run(["qs", "ipc", "-c", "amir", "call", "amir", "reload"], timeout=6)
    return True, f"Colours regenerated from {image.name}."


def cache_dir_path() -> Path:
    return cache_dir()
