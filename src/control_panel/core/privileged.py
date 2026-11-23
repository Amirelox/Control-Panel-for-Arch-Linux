"""Privilege escalation and terminal launching.

Graphical applications have no TTY, so ``sudo`` must never be called in a way
that waits for a password on a non-existent terminal. We prefer ``pkexec``
(which talks to the desktop polkit agent) and, for long interactive jobs such
as package updates, open a real terminal window.
"""

from __future__ import annotations

import os
import shlex
from collections.abc import Sequence

from .commands import CommandResult, run, spawn, which

__all__ = [
    "TERMINALS",
    "build_terminal_argv",
    "is_hyprland",
    "is_root",
    "launch_in_terminal",
    "run_privileged",
    "terminal_available",
]

# Ordered by preference. Values are builders rather than format strings so
# arguments are never passed through a shell.
TERMINALS = (
    "kitty",
    "alacritty",
    "foot",
    "wezterm",
    "konsole",
    "gnome-terminal",
    "ptyxis",
    "kgx",
    "xfce4-terminal",
    "tilix",
    "urxvt",
    "xterm",
)


def is_root() -> bool:
    return hasattr(os, "geteuid") and os.geteuid() == 0


def is_hyprland() -> bool:
    return bool(
        os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")
        or "hyprland" in os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
    )


def terminal_available(preferred: str = "") -> str | None:
    if preferred:
        path = which(preferred)
        if path:
            return path
    for name in TERMINALS:
        path = which(name)
        if path:
            return path
    return None


def build_terminal_argv(
    command: Sequence[str],
    *,
    title: str = "Control Panel",
    hold: bool = True,
    terminal: str = "",
) -> list[str] | None:
    """Build an argv that runs *command* inside a terminal emulator."""
    path = terminal_available(terminal)
    if path is None:
        return None

    name = os.path.basename(path)
    shell_command = shlex.join([str(part) for part in command])
    if hold:
        shell_command += (
            '; __status=$?; printf "\\n[exit code: %s]\\n" "$__status";'
            ' read -r -p "Press Enter to close this window…" _'
        )
    inner = ["bash", "-lc", shell_command]

    if name == "kitty":
        return [path, "--title", title, *inner]
    if name == "alacritty":
        return [path, "--title", title, "-e", *inner]
    if name == "foot":
        return [path, "--title", title, *inner]
    if name == "wezterm":
        return [path, "start", "--", *inner]
    if name == "konsole":
        return [path, "-p", f"tabtitle={title}", "-e", *inner]
    if name in {"gnome-terminal", "kgx", "ptyxis"}:
        return [path, "--title", title, "--", *inner]
    if name in {"xfce4-terminal", "tilix"}:
        return [path, "--title", title, "-x", *inner]
    if name == "urxvt":
        return [path, "-title", title, "-e", *inner]
    if name == "xterm":
        return [path, "-T", title, "-e", *inner]
    return [path, "-e", *inner]


def launch_in_terminal(
    command: Sequence[str],
    *,
    title: str = "Control Panel",
    hold: bool = True,
    terminal: str = "",
) -> tuple[bool, str]:
    argv = build_terminal_argv(command, title=title, hold=hold, terminal=terminal)
    if argv is None:
        return False, (
            "No terminal emulator found. Install kitty, alacritty, foot or xterm, "
            "or run the command manually in a terminal."
        )
    process = spawn(argv)
    if process is None:
        return False, f"Could not start {os.path.basename(argv[0])}."
    return True, ""


def run_privileged(
    argv: Sequence[str],
    *,
    timeout: float = 120.0,
    allow_prompt: bool = True,
    input_text: str | None = None,
) -> CommandResult:
    """Run a command as root using pkexec (or sudo when already authorised).

    ``allow_prompt=False`` is for read-only status checks on page load: it
    never opens an authentication dialog.
    """
    args = tuple(str(part) for part in argv)
    if is_root():
        return run(args, timeout=timeout, input_text=input_text)

    pkexec = which("pkexec")
    if pkexec and allow_prompt:
        return run([pkexec, *args], timeout=timeout, input_text=input_text)

    sudo = which("sudo")
    if sudo:
        result = run([sudo, "-n", *args], timeout=timeout, input_text=input_text)
        if result.ok:
            return result
        if not allow_prompt:
            return result
        return CommandResult(
            args,
            1,
            result.stdout,
            result.stderr,
            error=(
                "This action needs administrator rights. Start it from a terminal, "
                "or install polkit (pkexec) so the desktop can ask for your password."
            ),
        )

    return CommandResult(
        args,
        127,
        error=(
            "Neither polkit (pkexec) nor sudo is available. "
            "Install polkit and a polkit authentication agent."
        ),
    )
