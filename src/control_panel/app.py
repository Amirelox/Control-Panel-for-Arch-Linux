"""Application entry point."""

from __future__ import annotations

import argparse
import contextlib
import os
import sys
import tempfile
import traceback
from pathlib import Path

from PyQt6.QtCore import QLockFile, QTimer
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QMessageBox, QStyle

from . import __app_id__, __app_name__, __version__
from .core.commands import CommandRunner
from .core.config import APP_NAME, Settings, SettingsStore, runtime_dir, state_dir
from .ui.main_window import PAGE_SPECS, MainWindow
from .ui.theme import apply_theme, load_palette


class AppLock:
    """Prevent two copies from fighting over the same panel."""

    def __init__(self) -> None:
        directory = runtime_dir()
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError:
            directory = Path("/tmp")
        self._lock = QLockFile(str(directory / f"{__app_id__}.lock"))
        self._lock.setStaleLockTime(30_000)

    def acquire(self) -> bool:
        return self._lock.tryLock(150)

    def release(self) -> None:
        self._lock.unlock()


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="control-panel",
        description="A responsive control panel for Arch Linux and Hyprland.",
    )
    parser.add_argument("--version", action="version", version=f"{__app_name__} {__version__}")
    parser.add_argument(
        "--page",
        metavar="NAME_OR_NUMBER",
        help="open a specific page (1-based number or page name)",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="build every page, then exit (used by CI)",
    )
    parser.add_argument(
        "--screenshot",
        metavar="PATH",
        help="render the window to a PNG and exit",
    )
    parser.add_argument(
        "--reset-layout",
        action="store_true",
        help="forget the saved window geometry and page",
    )
    return parser.parse_args(argv)


def _resolve_page(value: str | None) -> int | None:
    if not value:
        return None
    if value.isdigit():
        index = int(value) - 1
        return index if 0 <= index < len(PAGE_SPECS) else None
    lowered = value.casefold()
    for index, spec in enumerate(PAGE_SPECS):
        if spec.title.casefold() == lowered:
            return index
    return None


def _write_crash_log(details: str) -> None:
    try:
        directory = state_dir()
        directory.mkdir(parents=True, exist_ok=True)
        with (directory / "crash.log").open("a", encoding="utf-8") as handle:
            handle.write(details + "\n")
    except OSError:
        pass


def _install_excepthook(*, quiet: bool) -> None:
    def handler(exc_type, exc_value, exc_traceback) -> None:
        details = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        sys.stderr.write(details)
        _write_crash_log(details)
        if not quiet:
            QMessageBox.critical(
                None,
                "Control Panel",
                "An unexpected error occurred. Details were written to the state directory.",
            )

    sys.excepthook = handler


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(list(argv if argv is not None else sys.argv[1:]))

    if args.self_test and not (os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY")):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    if args.screenshot:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"

    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "1")

    app = QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(__app_name__)
    app.setApplicationVersion(__version__)
    app.setOrganizationName("Control Panel")
    app.setDesktopFileName(__app_id__)
    app.setStyle("Fusion")
    icon = QIcon.fromTheme("preferences-system")
    if icon.isNull():
        icon = app.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
    app.setWindowIcon(icon)

    lock = AppLock()
    if not args.self_test and not args.screenshot and not lock.acquire():
        QMessageBox.information(
            None,
            __app_name__,
            "Control Panel is already running.",
        )
        return 0

    if args.self_test or args.screenshot:
        store = SettingsStore(Path(tempfile.mkdtemp(prefix="acc-")) / "settings.json")
        settings = Settings()
    else:
        store = SettingsStore()
        settings = store.load()
    if args.reset_layout:
        settings.window_geometry = ""
        settings.last_page = 0
        settings.sidebar_collapsed = False
        with contextlib.suppress(OSError):
            store.save(settings)
    page = _resolve_page(args.page)
    if page is not None:
        settings.last_page = page

    palette = load_palette(settings.accent)
    ui_font, mono_font = apply_theme(app, palette)
    _install_excepthook(quiet=args.self_test or bool(args.screenshot))

    runner = CommandRunner(app, max_threads=6)
    runner.set_error_handler(lambda message: print(f"[task] {message}", file=sys.stderr))
    window = MainWindow(
        store,
        settings,
        runner,
        palette,
        ui_font=ui_font,
        mono_font=mono_font,
    )
    window.show()

    if args.screenshot:
        target = Path(args.screenshot).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        window.resize(1280, 820)

        def capture() -> None:
            window.grab().save(str(target), "PNG")
            print(f"Screenshot saved to {target}")
            app.quit()

        delay_ms = int(os.environ.get("ACC_SCREENSHOT_DELAY_MS", "9000"))
        QTimer.singleShot(max(250, delay_ms), capture)
    elif args.self_test:
        pages = list(range(len(PAGE_SPECS)))
        delay = 120

        def step() -> None:
            if not pages:
                if window.panel_errors:
                    print(f"Self-test: {window.panel_errors} page(s) failed to build.")
                    app.exit(1)
                else:
                    print("Self-test: every page built successfully.")
                    app.quit()
                return
            window.switch_page(pages.pop(0))
            QTimer.singleShot(delay, step)

        QTimer.singleShot(250, step)

    app.aboutToQuit.connect(lambda: (runner.shutdown(1200), lock.release()))
    exit_code = app.exec()
    return int(exit_code)


if __name__ == "__main__":
    raise SystemExit(main())
