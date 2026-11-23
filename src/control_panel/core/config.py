"""Application paths and persisted settings."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

from .. import __app_id__, __app_name__, __version__
from .fs import read_text, write_text_atomic

__all__ = [
    "APP_ID",
    "APP_NAME",
    "VERSION",
    "Settings",
    "SettingsStore",
    "cache_dir",
    "config_dir",
    "hypr_colors_conf",
    "hypr_config_dir",
    "hyprland_conf",
    "modules_dir",
    "settings_path",
    "state_dir",
    "wallpaper_cache_file",
    "wallpaper_dirs",
]

APP_ID = __app_id__
APP_NAME = __app_name__
VERSION = __version__


def home() -> Path:
    return Path.home()


def _xdg(env_name: str, fallback: Path) -> Path:
    value = os.environ.get(env_name, "").strip()
    return Path(value).expanduser() if value else fallback


def config_dir() -> Path:
    return _xdg("XDG_CONFIG_HOME", home() / ".config")


def state_dir() -> Path:
    return _xdg("XDG_STATE_HOME", home() / ".local" / "state") / APP_ID


def cache_dir() -> Path:
    return _xdg("XDG_CACHE_HOME", home() / ".cache")


def runtime_dir() -> Path:
    return _xdg("XDG_RUNTIME_DIR", cache_dir())


def settings_path() -> Path:
    return config_dir() / APP_ID / "settings.json"


def hypr_config_dir() -> Path:
    return config_dir() / "hypr"


def hyprland_conf() -> Path:
    return hypr_config_dir() / "hyprland.conf"


def hypr_colors_conf() -> Path:
    return hypr_config_dir() / "colors.conf"


def modules_dir() -> Path:
    """Locate the Hyprland ``modules/`` directory used by the dotfiles."""
    candidates = [home() / "modules", hypr_config_dir() / "modules"]
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return candidates[0]


def wallpaper_cache_file() -> Path:
    return cache_dir() / "current_wallpaper"


def wallpaper_dirs(settings: Settings | None = None) -> list[Path]:
    configured = settings.wallpaper_dirs if settings else []
    candidates = [Path(p).expanduser() for p in configured if p.strip()]
    candidates += [
        home() / "wallpapers",
        home() / "Pictures" / "Wallpapers",
        home() / "Pictures",
    ]
    result: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved in seen or not candidate.is_dir():
            continue
        seen.add(resolved)
        result.append(candidate)
    return result


@dataclass(slots=True)
class Settings:
    """User preferences persisted as JSON.

    The file is deliberately forgiving: unknown keys are ignored and invalid
    values fall back to defaults instead of preventing the app from starting.
    """

    window_geometry: str = ""
    last_page: int = 0
    sidebar_collapsed: bool = False
    refresh_ms: int = 1000
    confirm_destructive: bool = True
    wallpaper_dirs: list[str] = field(
        default_factory=lambda: [
            str(home() / "wallpapers"),
            str(home() / "Pictures" / "Wallpapers"),
        ]
    )
    terminal: str = ""
    accent: str = "amber"
    hide_sensitive_env: bool = True
    scan_limit: int = 250_000

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


class SettingsStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or settings_path()

    def load(self) -> Settings:
        raw = read_text(self.path, "")
        if not raw.strip():
            return Settings()
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return Settings()
        if not isinstance(data, dict):
            return Settings()

        defaults = Settings()
        values: dict[str, Any] = {}
        for item in fields(Settings):
            if item.name not in data:
                continue
            value = data[item.name]
            default = getattr(defaults, item.name)
            if isinstance(default, bool):
                if isinstance(value, bool):
                    values[item.name] = value
            elif isinstance(default, int):
                if isinstance(value, int) and not isinstance(value, bool):
                    values[item.name] = value
            elif isinstance(default, str) and isinstance(value, str):
                values[item.name] = value
            elif isinstance(default, list) and isinstance(value, list):
                values[item.name] = [str(entry) for entry in value if isinstance(entry, str)]
        settings = Settings(**values)

        # Keep values inside sane bounds.
        settings.refresh_ms = max(500, min(settings.refresh_ms, 10_000))
        settings.scan_limit = max(10_000, min(settings.scan_limit, 5_000_000))
        settings.last_page = max(0, min(settings.last_page, 64))
        if settings.accent not in {"auto", "amber", "violet", "green", "blue", "rose"}:
            settings.accent = "amber"
        return settings

    def save(self, settings: Settings) -> None:
        write_text_atomic(
            self.path,
            json.dumps(settings.to_json(), indent=2, ensure_ascii=False) + "\n",
            backup=False,
        )
