"""Overview page: live health and system facts."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QApplication,
    QGridLayout,
    QLabel,
    QStyle,
)

from ...core.commands import CommandRunner
from ...core.parsers import format_bytes, format_duration, format_rate
from ...core.stats import Stats
from ...core.sysinfo import collect_system_info
from ..theme import Palette
from ..widgets import (
    BasePage,
    Card,
    KeyValueGrid,
    ProgressRow,
    Sparkline,
    StatCard,
)


class OverviewPage(BasePage):
    title = "Overview"
    subtitle = "Live system health, hardware and quick facts"
    icon_name = "computer-symbolic"
    fallback_icon = QStyle.StandardPixmap.SP_ComputerIcon

    def __init__(
        self,
        runner: CommandRunner,
        settings,
        *,
        palette: Palette,
        mono_font: str = "Monospace",
        parent=None,
    ) -> None:
        super().__init__(runner, settings, mono_font=mono_font, parent=parent)
        self.palette = palette
        self._info_loaded = False
        self._info: dict[str, str] = {}

        self.cpu_card = StatCard(
            "CPU", "—%", icon="cpu", fallback=QStyle.StandardPixmap.SP_ComputerIcon
        )
        self.mem_card = StatCard(
            "Memory", "—", icon="media-flash", fallback=QStyle.StandardPixmap.SP_DriveHDIcon
        )
        self.disk_card = StatCard(
            "Disk /", "—", icon="drive-harddisk", fallback=QStyle.StandardPixmap.SP_DriveHDIcon
        )
        self.temp_card = StatCard(
            "Temperature",
            "—",
            icon="temperature-normal",
            fallback=QStyle.StandardPixmap.SP_ComputerIcon,
        )
        self.net_card = StatCard(
            "Network", "—", icon="network-wireless", fallback=QStyle.StandardPixmap.SP_DriveNetIcon
        )
        self.battery_card = StatCard(
            "Battery", "—", icon="battery-good", fallback=QStyle.StandardPixmap.SP_DialogApplyButton
        )
        self.add_flow(
            [
                self.cpu_card,
                self.mem_card,
                self.disk_card,
                self.temp_card,
                self.net_card,
                self.battery_card,
            ]
        )
        self.battery_card.setVisible(False)

        self.add_section("Live Usage")
        usage = Card("Current load")
        self.cpu_row = ProgressRow("CPU", value_width=140)
        self.mem_row = ProgressRow("Memory", value_width=170)
        self.swap_row = ProgressRow("Swap", value_width=140)
        self.disk_row = ProgressRow("Disk /", value_width=170)
        for row in (self.cpu_row, self.mem_row, self.swap_row, self.disk_row):
            usage.add(row)
        self.add(usage)

        activity = Card("History")
        self.cpu_spark = Sparkline(ceiling=100)
        self.net_spark = Sparkline()
        self.cpu_spark.set_colour(palette.accent)
        self.net_spark.set_colour(palette.info)
        spark_grid = QGridLayout()
        spark_grid.setHorizontalSpacing(18)
        spark_grid.setVerticalSpacing(2)
        spark_grid.addWidget(QLabel("CPU"), 0, 0)
        spark_grid.addWidget(QLabel("Network"), 1, 0)
        spark_grid.addWidget(self.cpu_spark, 0, 1)
        spark_grid.addWidget(self.net_spark, 1, 1)
        spark_grid.setColumnStretch(1, 1)
        activity.add_layout(spark_grid)
        self.add(activity)

        self.add_section(
            "System Info",
            self.add_action_button(
                "Refresh",
                self.refresh_info,
                icon="view-refresh",
                style="Ghost",
                tooltip="Refresh static system information",
            ),
        )
        self.info_card = Card()
        self.info_grid = KeyValueGrid()
        self.info_card.add(self.info_grid)
        self.add(self.info_card)
        self.add_stretch()

        self._copy_button = self.add_action_button(
            "Copy info",
            self.copy_info,
            icon="edit-copy",
            style="Ghost",
            tooltip="Copy the system information to the clipboard",
        )

    def set_palette(self, palette: Palette) -> None:
        self.palette = palette
        self.cpu_spark.set_colour(palette.accent)
        self.net_spark.set_colour(palette.info)

    # ------------------------------------------------------------------
    def on_show(self) -> None:
        if not self._info_loaded:
            self.refresh_info()

    def refresh_info(self) -> None:
        self._info_loaded = True
        self.call(collect_system_info, self._apply_info)

    def _apply_info(self, info: dict[str, str]) -> None:
        self._info = info
        if self.info_grid.row_count:
            for key, value in info.items():
                self.info_grid.set(key, value)
            return
        for key, value in info.items():
            self.info_grid.add(key, value)

    def copy_info(self) -> None:
        if not self._info:
            self.notify("System information is still loading.", "info")
            return
        text = "\n".join(f"{key}: {value}" for key, value in self._info.items())
        QApplication.clipboard().setText(text)
        self.notify("System information copied to the clipboard.", "success")

    # ------------------------------------------------------------------
    def update_stats(self, stats: Stats) -> None:
        self.cpu_card.set_value(f"{stats.cpu:.0f}%", f"Load {stats.load[0]:.2f}")
        self.mem_card.set_value(
            f"{stats.mem_percent:.0f}%",
            f"{format_bytes(stats.mem_used)} of {format_bytes(stats.mem_total)}",
        )
        self.disk_card.set_value(
            f"{stats.disk_percent:.0f}%",
            f"{format_bytes(stats.disk_used)} of {format_bytes(stats.disk_total)}",
        )
        if stats.temps:
            sensor, value = max(stats.temps.items(), key=lambda pair: pair[1])
            self.temp_card.set_value(f"{value:.0f}°C", sensor.replace("_", " "))
        else:
            self.temp_card.set_value("—", "No sensor")
        self.net_card.set_value(
            f"↓ {format_rate(stats.net_down)}",
            f"↑ {format_rate(stats.net_up)}",
        )
        if stats.battery is not None:
            self.battery_card.setVisible(True)
            battery = stats.battery
            subtitle = battery.status
            if battery.seconds_left:
                subtitle += f" · {format_duration(battery.seconds_left)} left"
            self.battery_card.set_value(f"{battery.percent}%", subtitle)
        else:
            self.battery_card.setVisible(False)

        self.cpu_row.set(stats.cpu, f"{stats.cpu:.0f}%")
        self.mem_row.set(
            stats.mem_percent,
            f"{format_bytes(stats.mem_used)} / {format_bytes(stats.mem_total)}",
        )
        if stats.swap_total:
            self.swap_row.set(
                stats.swap_percent,
                f"{format_bytes(stats.swap_used)} / {format_bytes(stats.swap_total)}",
            )
            self.swap_row.setVisible(True)
        else:
            self.swap_row.setVisible(False)
        self.disk_row.set(
            stats.disk_percent,
            f"{format_bytes(stats.disk_used)} / {format_bytes(stats.disk_total)}",
        )

        self.cpu_spark.append(stats.cpu)
        self.net_spark.append(stats.net_down + stats.net_up)
