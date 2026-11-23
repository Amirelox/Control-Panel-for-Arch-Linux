# Architecture

## Goals

1. The window must stay interactive while a command runs.
2. User-controlled strings must never reach a shell.
3. Every optional dependency must fail gracefully.
4. The layout must work from a small tiled window to a large monitor.
5. Privileged work must use the desktop's authentication agent or a terminal.

## Layers

```text
app.py ──► MainWindow ──► pages ──► widgets
              │             │
              │             └──► core/*.py ──► commands.run(argv)
              └──► SettingsStore / theme / StatsWorker
```

`core/` never imports Qt widgets. The only Qt types in `core/` are in
`commands.py` (`TaskRunner`, `Task`), `stats.py` (`QThread`) and
`config.py` (no Qt at all, just paths/JSON). Everything else is plain Python and
is unit tested without a display.

## Command execution

`core/commands.py` exposes `run(argv)`:

- `subprocess.Popen` with an argument list, `shell=False` by default,
- a new session per child so a timeout can kill the whole process group,
- UTF-8 with replacement, a 4 MiB capture limit,
- a structured `CommandResult` (exit code, stdout, stderr, timeout, error).

`CommandRunner` is a `TaskRunner` backed by a local `QThreadPool` (6 threads).
Pages call:

```python
self.run_command(["nmcli", "device", "wifi", "connect", ssid], on_done, busy=button)
```

The callback is delivered on the GUI thread through a queued Qt signal. A
`BasePage` guard drops callbacks after the page/window is shutting down.
`Task.run` also catches `RuntimeError` when the signal object has already been
destroyed, which is important during shutdown.

## Privilege model

- Read-only checks use `run_privileged(..., allow_prompt=False)`, which only
  tries `sudo -n`. It never opens a polkit dialog during page load.
- Write actions use `pkexec` when available. polkit's authentication agent
  (usually started by the desktop session) shows the password dialog.
- Package operations, `yay`, and other interactive jobs are launched inside a
  terminal via `launch_in_terminal`. The terminal is detected from a fixed
  preference list. The command is passed as an argv list, never a shell string.
- If neither `pkexec` nor a terminal exists, the page shows an actionable error.

## Parsing

Command output is parsed by pure functions in `core/parsers.py`: nmcli,
pacman/yay, systemd, `ss`, `last`, Bluetooth, Hyprland JSON, `lspci`, `df`,
`/etc/os-release`. Each returns a small frozen dataclass or a plain value. This
keeps the UI free of brittle string handling and makes the format changes easy
to test.

Validation is deliberately narrow: package names (`[A-Za-z0-9@._+-]`, no leading
dash), Bluetooth MAC addresses, WiFi SSIDs (no control characters, ≤32 bytes),
and service unit names.

## Responsiveness

- `FlowLayout` wraps stat cards based on the available width.
- `Sidebar` has an expanded (224 px) and compact (68 px) mode. The window
  collapses it below 900 px and expands above 1120 px unless the user chose
  otherwise.
- Pages are created on first visit and cached; placeholders keep stack indices
  stable. A broken page becomes an error page with a Retry button instead of
  crashing the app.
- Sliders use 120 ms debounce timers; Hyprland options use 250 ms.
- Timers only run while their page is visible (`on_show` / `on_hide`).
- The process table refreshes every 3 s and computes CPU from per-process CPU
  time deltas, so percentages reflect the last interval instead of always 0.

## Configuration and backups

`core/fs.write_text_atomic` writes a temporary file in the destination
directory, preserves the original mode, optionally copies `<file>.bak`, then
uses `os.replace`. `core/hyprland.py` follows `source =` directives recursively
(with `~`, `$HOME`, relative paths and globs), so editors work on the real file
where each setting lives. After saving, `hyprctl reload` is followed by
`hyprctl configerrors -j`; errors are shown as a toast.

## Theme

`ui/theme.py` parses `~/.config/hypr/colors.conf` (Matugen output), accepts
`rgb(...)`, `rgba(...)`, `#rrggbb`, `0x...` forms, derives surface/border/muted
colours, and builds the QSS. Acrylic/transparency is intentionally not used:
the app should look consistent under any compositor and be readable on a
screenshot.

## Failure handling

- Missing executables return `returncode=127` with a readable message.
- Missing sensors return `None` or empty collections.
- `sys.excepthook` writes a crash log to
  `~/.local/state/control-panel/crash.log` and shows a dialog (disabled for
  `--self-test`/`--screenshot`).
- The single-instance lock uses `QLockFile` in `$XDG_RUNTIME_DIR`.
