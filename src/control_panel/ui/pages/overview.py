"""Overview page: live health and system facts."""

from __future__ import annotations

from PyQt6.QtWidgets import QApplication, QLabel, QStyle

from ...core.commands import CommandRunner
from ...core.config import Settings
from ...core.parsers import format_bytes, format_duration, format_rate
from ...core.stats import Stats
from ...core.sysinfo import collect_system_info
from ..theme import Palette
from ..widgets import (
    ActivityChart,
    BasePage,
    Card,
    KeyValueGrid,
    StatCard,
    TwoColumn,
)


class OverviewPage(BasePage):
    title = "Overview"
    subtitle = "Live system health, hardware and recent activity"
    icon_name = "computer-symbolic"
    fallback_icon = QStyle.StandardPixmap.SP_ComputerIcon

    def __init__(
        self,
        runner: CommandRunner,
        settings: Settings,
        *,
        palette: Palette,
        mono_font: str = "Monospace",
        parent=None,
    ) -> None:
        super().__init__(runner, settings, mono_font=mono_font, parent=parent)
        self.palette = palette
        self._info_loaded = False
        self._info: dict[str, str] = {}
        self._last_stats: Stats | None = None

        self.add_action_button(
            "Copy info",
            self.copy_info,
            style="Ghost",
            tooltip="Copy the system information to the clipboard",
        )
        self.add_action_button(
            "Refresh",
            self.refresh_info,
            style="Ghost",
            tooltip="Refresh static system information",
        )

        self.add_section("Current state")
        self.cpu_card = StatCard("CPU", "—%", minimum_width=160)
        self.mem_card = StatCard("Memory", "—", minimum_width=200)
        self.disk_card = StatCard("Disk /", "—", minimum_width=180)
        self.net_card = StatCard("Network", "—", minimum_width=240)
        self.add_flow(
            [self.cpu_card, self.mem_card, self.disk_card, self.net_card],
            spacing=16,
        )

        activity_card = Card("Activity")
        self.activity_now = QLabel("—")
        self.activity_now.setObjectName("MonoHint")
        activity_card.add_action(self.activity_now)
        self.chart = ActivityChart()
        self.chart.configure(palette, mono_font)
        activity_card.add(self.chart)
        activity_hint = QLabel("CPU and memory · last 60 seconds · 1 s samples")
        activity_hint.setObjectName("Hint")
        activity_card.add(activity_hint)

        system_card = Card("System")
        self.info_grid = KeyValueGrid()
        for key in (
            "Hostname",
            "Operating system",
            "Kernel",
            "Desktop",
            "Uptime",
            "CPU",
            "Cores",
            "Memory",
            "GPU",
            "Temperature",
            "Battery",
        ):
            self.info_grid.add(key, "…" if key not in {"Temperature", "Battery"} else "—")
        system_card.add(self.info_grid)
        self.add(TwoColumn(activity_card, system_card, breakpoint=840))
        self.add_stretch()

    # ------------------------------------------------------------------
    def set_palette(self, palette: Palette) -> None:
        self.palette = palette
        self.chart.configure(palette, self.mono_font)

    def on_show(self) -> None:
        if not self._info_loaded:
            self.refresh_info()

    def refresh_info(self) -> None:
        self._info_loaded = True
        self.call(collect_system_info, self._apply_info)

    def _apply_info(self, info: dict[str, str]) -> None:
        self._info = info
        for key, value in info.items():
            self.info_grid.set(key, value)
        if self._last_stats is not None:
            self._apply_atmosphere(self._last_stats)

    def _apply_atmosphere(self, stats: Stats) -> None:
        if stats.temps:
            sensor, value = max(stats.temps.items(), key=lambda pair: pair[1])
            label = sensor.rsplit("/", 1)[-1].replace("_", " ")
            self.info_grid.set("Temperature", f"{value:.0f} °C · {label}")
        else:
            self.info_grid.set("Temperature", "No sensor")
        battery = stats.battery
        if battery is None:
            self.info_grid.set("Battery", "No battery")
            return
        detail = battery.status
        if battery.seconds_left:
            detail += f" · {format_duration(battery.seconds_left)} left"
        self.info_grid.set("Battery", f"{battery.percent}% · {detail}")

    def copy_info(self) -> None:
        if not self._info:
            self.notify("System information is still loading.", "info")
            return
        text = "\n".join(f"{key}: {value}" for key, value in self._info.items())
        QApplication.clipboard().setText(text)
        self.notify("System information copied to the clipboard.", "success")

    # ------------------------------------------------------------------
    def update_stats(self, stats: Stats) -> None:
        self._last_stats = stats
        self.cpu_card.set_value(f"{stats.cpu:.0f}%", f"Load {stats.load[0]:.2f}")
        self.mem_card.set_value(
            f"{stats.mem_percent:.0f}%",
            f"{format_bytes(stats.mem_used)} of {format_bytes(stats.mem_total)}",
        )
        self.disk_card.set_value(
            f"{stats.disk_percent:.0f}%",
            f"{format_bytes(stats.disk_used)} of {format_bytes(stats.disk_total)}",
        )
        self.net_card.set_value(
            format_rate(stats.net_down),
            f"Up {format_rate(stats.net_up)}",
        )
        self.chart.append(stats.cpu, stats.mem_percent)
        self.activity_now.setText(f"CPU {stats.cpu:.0f}%  MEM {stats.mem_percent:.0f}%")
        self._apply_atmosphere(stats)
