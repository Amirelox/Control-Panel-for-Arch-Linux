"""Security page: firewall, SSH, logins and listening ports."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStyle,
    QTextEdit,
    QTreeWidgetItem,
)

from ...core import security
from ...core.commands import CommandRunner
from ...core.config import Settings
from ...core.parsers import PortInfo
from ..widgets import BasePage, Card, DataTable


class SecurityPage(BasePage):
    title = "Security"
    subtitle = "Firewall, SSH, login history and open ports"
    icon_name = "security-high-symbolic"
    fallback_icon = QStyle.StandardPixmap.SP_MessageBoxWarning

    def __init__(
        self,
        runner: CommandRunner,
        settings: Settings,
        *,
        mono_font: str = "Monospace",
        palette=None,
        parent=None,
    ) -> None:
        super().__init__(runner, settings, mono_font=mono_font, parent=parent)
        self._loaded = False
        self._ports: list[PortInfo] = []

        self.add_action_button(
            "Refresh",
            self.refresh,
            icon="view-refresh",
            style="Ghost",
            tooltip="Re-read firewall, SSH and port information",
        )

        self.add_section("Overview")
        checks_card = Card("Security checklist")
        self.checks_box = QGridLayout()
        self.checks_box.setHorizontalSpacing(12)
        self.checks_box.setVerticalSpacing(6)
        checks_card.add_layout(self.checks_box)
        self.add(checks_card)

        # Firewall -------------------------------------------------------
        self.add_section("Firewall")
        firewall_card = Card("Packet filter")
        self.firewall_status = QLabel("Checking…")
        self.firewall_status.setObjectName("Muted")
        self.firewall_status.setWordWrap(True)
        firewall_card.add(self.firewall_status)
        row = QHBoxLayout()
        row.setSpacing(8)
        for label, action, style in (
            ("Enable", "enable", "Success"),
            ("Disable", "disable", "Danger"),
            ("Allow SSH", "allow-ssh", ""),
            ("Show status", "status", "Ghost"),
        ):
            button = QPushButton(label)
            if style:
                button.setObjectName(style)
            button.clicked.connect(
                lambda _checked=False, a=action, name=label: self.firewall_action(a, name)
            )
            row.addWidget(button)
        row.addStretch()
        firewall_card.add_layout(row)
        self.firewall_output = QTextEdit()
        self.firewall_output.setReadOnly(True)
        self.firewall_output.setMaximumHeight(130)
        self.firewall_output.setFont(QFont(self.mono_font, 10))
        firewall_card.add(self.firewall_output)
        self.add(firewall_card)

        # SSH ------------------------------------------------------------
        self.add_section("SSH")
        ssh_card = Card("SSH service")
        self.ssh_status = QLabel("Checking…")
        self.ssh_status.setObjectName("Muted")
        ssh_card.add(self.ssh_status)
        self.ssh_config_label = QLabel("")
        self.ssh_config_label.setObjectName("Hint")
        self.ssh_config_label.setWordWrap(True)
        self.ssh_config_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        ssh_card.add(self.ssh_config_label)
        ssh_row = QHBoxLayout()
        ssh_row.setSpacing(8)
        start = QPushButton("Start")
        start.clicked.connect(lambda: self.ssh_action("start"))
        stop = QPushButton("Stop")
        stop.setObjectName("Danger")
        stop.clicked.connect(lambda: self.ssh_action("stop"))
        restart = QPushButton("Restart")
        restart.clicked.connect(lambda: self.ssh_action("restart"))
        ssh_row.addWidget(start)
        ssh_row.addWidget(stop)
        ssh_row.addWidget(restart)
        ssh_row.addStretch()
        ssh_card.add_layout(ssh_row)
        self.keys_table = DataTable(
            ["File", "Permissions", "Type"], stretch_column=0, min_height=120
        )
        ssh_card.add(self.keys_table)
        self.keys_hint = QLabel("")
        self.keys_hint.setObjectName("Hint")
        ssh_card.add(self.keys_hint)
        self.add(ssh_card)

        # Logins ---------------------------------------------------------
        self.add_section("Login history")
        login_card = Card("Recent sessions")
        self.logins_label = QLabel("Loading…")
        self.logins_label.setObjectName("Hint")
        self.logins_label.setWordWrap(True)
        self.logins_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        login_card.add(self.logins_label)
        self.failed_label = QLabel("")
        self.failed_label.setObjectName("Danger")
        self.failed_label.setWordWrap(True)
        self.failed_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        login_card.add(self.failed_label)
        self.add(login_card)

        # Ports ----------------------------------------------------------
        self.add_section("Listening ports")
        ports_card = Card("Exposed services")
        self.ports_table = DataTable(
            ["Protocol", "Bind address", "Port", "Exposure", "Process"],
            stretch_column=4,
            min_height=200,
        )
        ports_card.add(self.ports_table)
        self.ports_hint = QLabel("")
        self.ports_hint.setObjectName("Hint")
        ports_card.add(self.ports_hint)
        self.add(ports_card)
        self.add_stretch()

    # ------------------------------------------------------------------
    def on_show(self) -> None:
        if not self._loaded:
            self._loaded = True
            self.refresh()

    def refresh(self) -> None:
        def work():
            return {
                "checks": security.security_checks(),
                "firewall": security.firewall_status(),
                "ssh": security.ssh_status(),
                "config": security.ssh_config(),
                "keys": security.ssh_keys(),
                "authorized": security.ssh_authorized_keys_count(),
                "permissions": security.home_ssh_permissions(),
                "logins": security.login_history(),
                "ports": security.listening_ports(),
            }

        self.call(work, self._apply)

    def _apply(self, data) -> None:
        self._apply_checks(data["checks"])
        firewall = data["firewall"]
        state = (
            "active" if firewall.active else ("inactive" if firewall.active is False else "unknown")
        )
        self.firewall_status.setText(
            f"{firewall.backend or 'No firewall'} · {state} · "
            f"{firewall.detail.splitlines()[0] if firewall.detail else 'no details'}"
        )
        self.firewall_output.setPlainText(firewall.detail)

        self.ssh_status.setText(f"SSH status: {data['ssh']}")
        config = data["config"]
        self.ssh_config_label.setText(
            f"Port {config.port} · root login: {config.permit_root_login} · "
            f"password authentication: {config.password_authentication} · {config.files}"
        )

        self.keys_table.clear_rows()
        for name, mode, kind in data["keys"]:
            self.keys_table.addTopLevelItem(QTreeWidgetItem([name, mode, kind]))
        self.keys_hint.setText(
            f"{data['authorized']} authorized key(s) · ~/.ssh permissions {data['permissions']}"
        )

        logins, failed = data["logins"]
        if logins:
            self.logins_label.setText(
                "\n".join(
                    f"{record.user} · {record.terminal} · {record.host} · {record.date}"
                    for record in logins[:8]
                )
            )
        else:
            self.logins_label.setText("No login records available.")
        self.failed_label.setText("Failed attempts:\n" + "\n".join(failed[:6]) if failed else "")

        self._ports = data["ports"]
        self.ports_table.clear_rows()
        exposed = 0
        for port in self._ports:
            if port.exposed:
                exposed += 1
            self.ports_table.addTopLevelItem(
                QTreeWidgetItem(
                    [
                        port.protocol,
                        port.address,
                        str(port.port) if port.port is not None else "—",
                        "Public" if port.exposed else "Local",
                        port.process or "—",
                    ]
                )
            )
        self.ports_hint.setText(
            f"{len(self._ports)} listening socket(s) · {exposed} bound to a public address"
        )

    def _apply_checks(self, checks: list[tuple[str, str, str]]) -> None:
        while self.checks_box.count():
            item = self.checks_box.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        colours = {"ok": "#a6e3a1", "warn": "#f9e2af", "info": "#89b4fa"}
        for row, (label, level, detail) in enumerate(checks):
            colour = colours.get(level, colours["info"])
            dot = QLabel("●")
            dot.setStyleSheet(f"color: {colour}; font-size: 13px;")
            name = QLabel(label)
            name.setStyleSheet("font-weight: 600;")
            detail_label = QLabel(detail)
            detail_label.setObjectName("Hint")
            detail_label.setWordWrap(True)
            self.checks_box.addWidget(dot, row, 0, Qt.AlignmentFlag.AlignTop)
            self.checks_box.addWidget(name, row, 1)
            self.checks_box.addWidget(detail_label, row, 2)
            self.checks_box.setColumnStretch(2, 1)

    # ------------------------------------------------------------------
    def firewall_action(self, action: str, label: str) -> None:
        if action in {"enable", "disable"} and not self.confirm(
            f"{label} firewall",
            f"{label} the firewall now?",
            danger=action == "disable",
            ok_text=label,
        ):
            return

        def done(result) -> None:
            text = result.output or result.summary()
            self.firewall_output.setPlainText(text)
            if result.ok:
                self.notify(f"Firewall: {label.lower()} requested.", "success")
            else:
                self.notify(result.summary(), "error")
            self.refresh()

        self.call(lambda: security.firewall_action(action), done)

    def ssh_action(self, action: str) -> None:
        def done(result) -> None:
            self.notify(
                f"SSH {action} requested." if result.ok else result.summary(),
                "success" if result.ok else "error",
            )
            self.refresh()

        self.call(lambda: security.ssh_service_action(action), done)
