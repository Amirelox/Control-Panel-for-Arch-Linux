"""Pacman/AUR search and package actions."""

from __future__ import annotations

from dataclasses import dataclass

from .commands import run, which
from .parsers import (
    Package,
    UpdateInfo,
    parse_pacman_search,
    parse_pacman_updates,
    validate_package_name,
)
from .privileged import launch_in_terminal

__all__ = [
    "SearchResult",
    "install",
    "is_installed",
    "remove",
    "search",
    "updates",
    "upgrade",
]


@dataclass(frozen=True, slots=True)
class SearchResult:
    packages: list[Package]
    error: str = ""


def _run_search(command: list[str], timeout: float) -> SearchResult:
    result = run(command, timeout=timeout)
    if not result.ok:
        return SearchResult([], result.summary())
    return SearchResult(parse_pacman_search(result.stdout))


def search(query: str, *, aur: bool = False) -> SearchResult:
    query = query.strip()
    if not query:
        return SearchResult([])
    if aur:
        if which("yay") is None:
            return SearchResult([], "yay is not installed — AUR search is unavailable.")
        return _run_search(["yay", "-Ss", "--", query], timeout=45)
    if which("pacman") is None:
        return SearchResult([], "pacman is not installed.")
    return _run_search(["pacman", "-Ss", "--", query], timeout=30)


def search_both(query: str) -> SearchResult:
    official = search(query, aur=False)
    if not query.strip():
        return official
    aur = search(query, aur=True)
    packages = official.packages + aur.packages
    errors = [error for error in (official.error, aur.error) if error]
    return SearchResult(packages, "\n".join(errors))


def updates() -> tuple[list[UpdateInfo], str]:
    if which("checkupdates"):
        result = run(["checkupdates"], timeout=30, env={"LC_ALL": "C"})
        if result.ok:
            return parse_pacman_updates(result.stdout), ""
    if which("pacman"):
        result = run(["pacman", "-Qu"], timeout=20, env={"LC_ALL": "C"})
        if result.ok:
            return parse_pacman_updates(result.stdout), ""
        if result.returncode == 1 and not result.stdout.strip():
            return [], ""
        return [], result.summary()
    return [], "pacman is not installed."


def is_installed(name: str) -> bool:
    if not validate_package_name(name) or which("pacman") is None:
        return False
    return run(["pacman", "-Q", name], timeout=5).ok


def install(packages: list[str], *, aur: bool = False, terminal: str = "") -> tuple[bool, str]:
    names = [name for name in packages if validate_package_name(name)]
    if not names:
        return False, "No valid package names selected."
    if aur:
        if which("yay") is None:
            return False, "yay is not installed."
        command = ["yay", "-S", "--needed", *names]
    else:
        command = ["sudo", "pacman", "-S", "--needed", *names]
    return launch_in_terminal(command, title="Install packages", terminal=terminal)


def remove(packages: list[str], *, terminal: str = "") -> tuple[bool, str]:
    names = [name for name in packages if validate_package_name(name)]
    if not names:
        return False, "No valid package names selected."
    return launch_in_terminal(
        ["sudo", "pacman", "-Rns", *names],
        title="Remove packages",
        terminal=terminal,
    )


def upgrade(*, terminal: str = "") -> tuple[bool, str]:
    if which("yay"):
        command = ["yay", "-Syu"]
    elif which("pacman"):
        command = ["sudo", "pacman", "-Syu"]
    else:
        return False, "No package manager found."
    return launch_in_terminal(command, title="System upgrade", terminal=terminal)
