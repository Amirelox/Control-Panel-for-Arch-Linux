# Changelog

## 2.0.0 — 2026-11-23

Complete rewrite of the original single-file prototype.

### Added

- Modular package layout (`core/` + `ui/pages/`), CLI and desktop entry.
- Background command runner with timeouts, process-group cleanup and Qt signals.
- Responsive shell: collapsible sidebar, flow-layout cards, lazy pages.
- Searchable, sortable process table with real CPU deltas and system/user
  systemd services.
- Background largest-file scanner with progress and cancellation.
- Wallpaper gallery with asynchronous thumbnails and awww/swww/hyprpaper/swaybg
  support.
- Hyprland editors that follow `source =` files, mark unsaved changes, create
  `.bak` copies and report `hyprctl configerrors`.
- Live Hyprland tweaks (rounding, gaps, opacity, blur).
- Matugen-aware accent palette and GTK/icon/cursor/font controls.
- Masked environment variables, PATH audit and shell rc editing.
- Security checklist, firewall/SSH actions, login history and listening ports.
- Preferences dialog, single-instance lock and crash log.
- Unit tests, Ruff configuration, CI workflow and documentation.

### Fixed

- No `shell=True` calls; user input is never interpolated into commands.
- No blocking system calls in page constructors or signal handlers.
- `sudo` no longer hangs without a TTY; `pkexec`/terminal helpers are used.
- Broken `find`/`numfmt` large-file scan replaced with bounded Python scan.
- Correct battery, Bluetooth address, firewall-unknown and monitor JSON parsing.
- Package search parsing (installed marker, descriptions), service parsing,
  WiFi deduplication and port parsing.
- Settings are validated and stored atomically; window state is restored.
