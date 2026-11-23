from __future__ import annotations

import sys

from control_panel.core.commands import run, which


def test_run_capture() -> None:
    result = run([sys.executable, "-c", "print('hello')"])
    assert result.ok
    assert result.stdout.strip() == "hello"


def test_no_shell_expansion() -> None:
    result = run(["echo", "$(id)"])
    assert result.stdout.strip() == "$(id)"


def test_missing_command() -> None:
    result = run(["definitely-not-a-real-command-acc"])
    assert not result.ok
    assert result.returncode == 127
    assert "not found" in result.error


def test_stdin_input() -> None:
    result = run(["cat"], input_text="hello\n")
    assert result.ok
    assert result.stdout == "hello\n"


def test_timeout() -> None:
    result = run(["sleep", "5"], timeout=0.2)
    assert result.timed_out
    assert result.returncode == -9


def test_which() -> None:
    assert which("sh")
    assert which("definitely-not-a-real-command-acc") is None
