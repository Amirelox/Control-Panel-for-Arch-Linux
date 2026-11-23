"""Command execution and background tasks.

Nothing in this module is allowed to block the GUI thread: pages use
:class:`CommandRunner` to execute work on a thread pool and receive results
through Qt signals.
"""

from __future__ import annotations

import os
import shlex
import shutil
import signal
import subprocess
import traceback
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal

__all__ = [
    "CommandResult",
    "CommandRunner",
    "Task",
    "TaskRunner",
    "TaskSignals",
    "run",
    "spawn",
    "which",
]

_MAX_CAPTURE = 4 * 1024 * 1024  # 4 MiB per stream


@dataclass(frozen=True, slots=True)
class CommandResult:
    """Outcome of a finished command."""

    argv: tuple[str, ...]
    returncode: int
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out and not self.error

    @property
    def output(self) -> str:
        return (self.stdout + ("\n" + self.stderr if self.stderr else "")).strip()

    def summary(self, limit: int = 500) -> str:
        text = self.error or self.stderr.strip() or self.stdout.strip()
        if not text:
            text = f"Command failed with exit code {self.returncode}"
        text = " ".join(text.split())
        return text if len(text) <= limit else text[: limit - 1] + "…"

    def with_fallback_error(self, message: str) -> CommandResult:
        if self.error or self.stderr:
            return self
        return CommandResult(
            self.argv,
            self.returncode,
            self.stdout,
            self.stderr,
            self.timed_out,
            message,
        )


def which(name: str) -> str | None:
    """Return the full path of an executable, or ``None``."""
    return shutil.which(name)


def run(
    argv: Sequence[str],
    *,
    timeout: float = 15.0,
    input_text: str | None = None,
    cwd: str | os.PathLike[str] | None = None,
    env: Mapping[str, str] | None = None,
    check: bool = False,
) -> CommandResult:
    """Run a command without a shell and capture its output.

    ``check=True`` raises :class:`RuntimeError` for a non-zero exit code;
    pages normally keep the result and decide what to show instead.
    """
    args = tuple(str(part) for part in argv)
    if not args:
        return CommandResult((), 127, error="empty command")

    full_env = None
    if env is not None:
        full_env = os.environ.copy()
        full_env.update({str(k): str(v) for k, v in env.items()})

    try:
        process = subprocess.Popen(
            args,
            stdin=subprocess.PIPE if input_text is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=os.fspath(cwd) if cwd is not None else None,
            env=full_env,
            start_new_session=True,
        )
    except FileNotFoundError:
        return CommandResult(args, 127, error=f"command not found: {args[0]}")
    except (OSError, ValueError) as exc:
        return CommandResult(args, 126, error=str(exc))

    try:
        stdout, stderr = process.communicate(input=input_text, timeout=timeout)
        return CommandResult(
            args,
            process.returncode if process.returncode is not None else 1,
            _limit(stdout),
            _limit(stderr),
        )
    except subprocess.TimeoutExpired:
        _kill_process_group(process)
        try:
            stdout, stderr = process.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            stdout, stderr = "", ""
        result = CommandResult(
            args,
            -9,
            _limit(stdout),
            _limit(stderr),
            timed_out=True,
            error=f"timed out after {timeout:g}s",
        )
        if check:
            raise RuntimeError(result.summary()) from None
        return result

    except Exception as exc:  # pragma: no cover - defensive
        _kill_process_group(process)
        result = CommandResult(args, 1, error=str(exc))
        if check:
            raise RuntimeError(result.summary()) from exc
        return result

    finally:
        if check and process.returncode not in (0, None):
            raise RuntimeError(f"command failed ({process.returncode}): {shlex.join(args)}")


def _limit(text: str | None) -> str:
    if not text:
        return ""
    if len(text) <= _MAX_CAPTURE:
        return text
    return text[:_MAX_CAPTURE] + "\n… output truncated …"


def _kill_process_group(process: subprocess.Popen[str]) -> None:
    try:
        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            process.kill()
        except OSError:
            pass


def spawn(
    argv: Sequence[str],
    *,
    cwd: str | os.PathLike[str] | None = None,
    env: Mapping[str, str] | None = None,
) -> subprocess.Popen[bytes] | None:
    """Start a detached background process and return it.

    Returns ``None`` when the executable is missing.
    """
    args = tuple(str(part) for part in argv)
    if not args:
        return None
    full_env = os.environ.copy() if env is not None else None
    if full_env is not None:
        full_env.update({str(k): str(v) for k, v in env.items()})
    try:
        return subprocess.Popen(
            args,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=os.fspath(cwd) if cwd is not None else None,
            env=full_env,
            start_new_session=True,
        )
    except (OSError, ValueError):
        return None


class TaskSignals(QObject):
    done = pyqtSignal(object)
    failed = pyqtSignal(str, str)


class Task(QRunnable):
    """Runnable wrapper that reports its result through Qt signals."""

    def __init__(self, function: Callable[[], Any]) -> None:
        super().__init__()
        self._function = function
        self.signals = TaskSignals()
        self.setAutoDelete(True)

    def run(self) -> None:
        try:
            value = self._function()
        except Exception as exc:
            try:
                self.signals.failed.emit(str(exc), traceback.format_exc())
            except RuntimeError:
                # The window (and its signal object) was destroyed during shutdown.
                pass
        else:
            try:
                self.signals.done.emit(value)
            except RuntimeError:
                pass


class TaskRunner(QObject):
    """Run Python callables on a small thread pool."""

    def __init__(self, parent: QObject | None = None, max_threads: int = 6) -> None:
        super().__init__(parent)
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(max(1, max_threads))
        self._active: set[Task] = set()
        self._error_log: Callable[[str], None] | None = None

    def set_error_handler(self, handler: Callable[[str], None] | None) -> None:
        self._error_log = handler

    def submit(
        self,
        function: Callable[[], Any],
        on_done: Callable[[Any], None] | None = None,
        on_error: Callable[[str, str], None] | None = None,
    ) -> Task:
        task = Task(function)
        self._active.add(task)

        def cleanup() -> None:
            self._active.discard(task)

        if on_done is not None:
            task.signals.done.connect(on_done)
        if on_error is not None:
            task.signals.failed.connect(on_error)
        elif self._error_log is not None:
            task.signals.failed.connect(lambda msg, _tb: self._error_log(msg))
        task.signals.done.connect(lambda _value: cleanup())
        task.signals.failed.connect(lambda _msg, _tb: cleanup())
        self._pool.start(task)
        return task

    def shutdown(self, timeout_ms: int = 2000) -> None:
        self._pool.clear()
        self._pool.waitForDone(timeout_ms)


class CommandRunner(TaskRunner):
    """TaskRunner specialised for :func:`run` calls."""

    def run(
        self,
        argv: Sequence[str],
        on_done: Callable[[CommandResult], None] | None = None,
        *,
        timeout: float = 15.0,
        input_text: str | None = None,
        on_error: Callable[[str, str], None] | None = None,
    ) -> Task:
        args = tuple(str(part) for part in argv)
        return self.submit(
            lambda: run(args, timeout=timeout, input_text=input_text),
            on_done=on_done,
            on_error=on_error,
        )
