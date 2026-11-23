"""GTK theme, icon, cursor and font helpers."""

from __future__ import annotations

from pathlib import Path

from .commands import CommandResult, run, which

__all__ = [
    "apply_cursor",
    "apply_font",
    "apply_gtk",
    "current_settings",
    "list_icon_themes",
    "list_themes",
]


def _theme_roots(kind: str) -> list[Path]:
    home = Path.home()
    if kind == "gtk":
        return [
            home / ".themes",
            home / ".local" / "share" / "themes",
            Path("/usr/share/themes"),
        ]
    roots = [
        home / ".icons",
        home / ".local" / "share" / "icons",
        Path("/usr/share/icons"),
    ]
    if kind == "cursor":
        roots.append(Path("/usr/share/X11/icons"))
    return roots


def _subdirectories(roots: list[Path], marker: str) -> list[str]:
    names: set[str] = set()
    for root in roots:
        if not root.is_dir():
            continue
        try:
            entries = list(root.iterdir())
        except OSError:
            continue
        for entry in entries:
            if entry.is_dir() and not entry.name.startswith(".") and (entry / marker).exists():
                names.add(entry.name)
    return sorted(names, key=str.lower)


def list_themes() -> list[str]:
    names = set(_subdirectories(_theme_roots("gtk"), "gtk-2.0"))
    names.update(_subdirectories(_theme_roots("gtk"), "gtk-3.0"))
    return sorted(names, key=str.lower)


def list_icon_themes() -> list[str]:
    names = _subdirectories(_theme_roots("icons"), "index.theme")
    # Some minimal icon themes lack index.theme; accept any directory as well.
    for root in _theme_roots("icons"):
        if root.is_dir():
            names += [
                entry.name
                for entry in root.iterdir()
                if entry.is_dir() and not entry.name.startswith(".")
            ]
    return sorted(set(names), key=str.lower)


def list_cursor_themes() -> list[str]:
    return sorted(set(_subdirectories(_theme_roots("cursor"), "cursors")), key=str.lower)


def _gsettings_get(key: str) -> str:
    if which("gsettings") is None:
        return ""
    result = run(["gsettings", "get", "org.gnome.desktop.interface", key], timeout=5)
    if not result.ok:
        return ""
    return result.stdout.strip().strip("'")


def current_settings() -> dict[str, str]:
    return {
        "gtk-theme": _gsettings_get("gtk-theme"),
        "icon-theme": _gsettings_get("icon-theme"),
        "cursor-theme": _gsettings_get("cursor-theme"),
        "font-name": _gsettings_get("font-name"),
    }


def _gsettings_set(key: str, value: str) -> CommandResult:
    if which("gsettings") is None:
        return CommandResult((), 127, error="gsettings is not installed")
    return run(["gsettings", "set", "org.gnome.desktop.interface", key, value], timeout=8)


def apply_gtk(theme: str, icons: str) -> CommandResult:
    first = _gsettings_set("gtk-theme", theme) if theme else CommandResult((), 0)
    if not first.ok:
        return first
    if icons:
        return _gsettings_set("icon-theme", icons)
    return first


def apply_cursor(theme: str) -> CommandResult:
    return _gsettings_set("cursor-theme", theme)


def apply_font(font: str) -> CommandResult:
    return _gsettings_set("font-name", font)
