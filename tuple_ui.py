#!/usr/bin/env python3
"""Tuple UI — dark-themed graphical interface for the Tuple CLI."""

import os
import signal
import subprocess
import sys
from pathlib import Path

from PyQt6.QtCore import QLockFile, QPoint, QSize, QTimer, Qt
from PyQt6.QtGui import QAction, QCloseEvent, QColor, QFont, QIcon, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QApplication, QComboBox, QFrame, QGroupBox, QHBoxLayout, QInputDialog,
    QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox, QPushButton,
    QSystemTrayIcon, QTextEdit, QVBoxLayout, QWidget,
)

from tuple_ui_contacts import ContactsPanel
from tuple_ui_core import CommandThread, TupleState
from tuple_ui_prefs import UIPrefs
from tuple_ui_rooms import FastButtonConfig
from tuple_ui_settings import SettingsDialog, fetch_settings
from tuple_ui_theme import (
    ACCENT, DANGER, SUCCESS, TEXT_MUTED, TEXT_SUBTLE, WARN, apply_dark_theme,
)

LOCK_FILE_PATH = Path.home() / ".cache" / "tuple-ui.lock"


def load_tuple_icon(size=48):
    """Return a QIcon for the Tuple brand.

    Prefers the installed hicolor theme icon (tuple.png, shipped with the
    Tuple desktop package). Falls back to a rendered purple rounded square
    if the file isn't present.
    """
    # Walk from largest down so window managers / taskbars that pick an
    # appropriate size get the crispest source available.
    candidate_sizes = [128, 48, 32, 16]
    icon_dir = Path.home() / ".local/share/icons/hicolor"
    icon = QIcon()
    any_found = False
    for s in candidate_sizes:
        path = icon_dir / f"{s}x{s}/apps/tuple.png"
        if path.exists():
            icon.addFile(str(path), QSize(s, s))
            any_found = True
    if any_found:
        return icon
    return QIcon(_make_tuple_icon_pixmap(size))


def _make_tuple_icon_pixmap(size):
    """Fallback: render a rounded-square Tuple-purple icon."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(ACCENT))
    painter.setPen(Qt.PenStyle.NoPen)
    inset = max(1, size // 10)
    radius = max(2, size // 5)
    painter.drawRoundedRect(
        inset, inset, size - 2 * inset, size - 2 * inset, radius, radius,
    )
    painter.end()
    return pixmap


class TupleUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self._quitting = False
        self._awaiting_auth_code = False
        self._capture_setting = None   # cached `capture` setting value
        self._contacts_loaded = False  # first-visible auto-refresh guard
        self._pending_command = None   # last command dispatched via run_command
        self._demo_mode = False        # screenshot mode: anonymize + mask URL

        self.current_thread = None
        self.state = TupleState("~/.local/share/tuple/0/log.txt")
        self.button_config = FastButtonConfig()
        self.prefs = UIPrefs()

        self._build_ui()

        self.state_timer = QTimer(self)
        self.state_timer.timeout.connect(self.update_state)
        self.state_timer.start(500)

        self._setup_tray_icon()

        if self.isVisible():
            self.show_action.setText("Hide Window")
        else:
            self.show_action.setText("Show Window")

        self.update_state()
        self._install_signal_handlers()

    # ------------------------------------------------------------------ UI

    def _build_ui(self):
        self.setWindowTitle("Tuple")
        self.setWindowIcon(load_tuple_icon())
        self.setMinimumSize(640, 520)
        self.resize(760, 640)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(14, 10, 14, 10)
        root.setSpacing(10)

        # ---- Header strip: logo | state | stretch | demo | cog | account | native ----
        # State label ("Ready" / "In Call" / "Daemon Off" / "Signed Out") sits
        # right next to the Tuple wordmark, matching the official UI's
        # "Tuple · <state>" banner.
        header = QHBoxLayout()
        header.setSpacing(6)

        logo = QLabel("Tuple")
        logo.setStyleSheet(f"color: {ACCENT}; font-weight: 600; font-size: 10pt;")
        header.addWidget(logo)

        self.state_header = QLabel("")
        self.state_header.setObjectName("stateHeader")
        self.state_header.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header.addWidget(self.state_header)

        header.addStretch(1)

        # Demo / screenshot mode: anonymizes contacts, masks the personal URL,
        # clears output. Checkable so the button itself shows active state.
        self.demo_btn = QPushButton("🎭")
        self.demo_btn.setProperty("kind", "icon")
        self.demo_btn.setCheckable(True)
        self.demo_btn.setToolTip(
            "Demo / screenshot mode — anonymizes contact names and emails, "
            "masks the personal URL, and clears output. Toggle off to restore."
        )
        self.demo_btn.toggled.connect(self._toggle_demo_mode)
        header.addWidget(self.demo_btn)

        self.settings_btn = QPushButton("⚙")
        self.settings_btn.setProperty("kind", "icon")
        self.settings_btn.setToolTip("Settings")
        self.settings_btn.clicked.connect(self._open_settings)
        header.addWidget(self.settings_btn)

        self.account_btn = QPushButton("👤")
        self.account_btn.setProperty("kind", "icon")
        self.account_btn.setToolTip("Account")
        self.account_menu = QMenu(self)
        self._build_account_menu()
        self.account_btn.clicked.connect(self._show_account_menu)
        header.addWidget(self.account_btn)

        # Tuple icon button — opens the native Tuple debug UI (`tuple ui`).
        # Prefer the real tuple.png from the system icon theme; fall back to a
        # rendered purple rounded square if we can't find it.
        self.native_ui_btn = QPushButton()
        self.native_ui_btn.setProperty("kind", "icon")
        self.native_ui_btn.setToolTip("Open native Tuple UI")
        self.native_ui_btn.setIcon(self._load_tuple_icon(18))
        self.native_ui_btn.clicked.connect(lambda: self.run_command("tuple ui"))
        header.addWidget(self.native_ui_btn)

        root.addLayout(header)

        # ---- Two-column body: actions/output on left, rooms+contacts on right.
        body = QHBoxLayout()
        body.setSpacing(12)
        root.addLayout(body, 1)

        # === LEFT COLUMN ======================================================
        left = QVBoxLayout()
        left.setSpacing(10)
        body.addLayout(left, 1)

        # (State header lives in the top header strip, next to the Tuple
        # wordmark — see `_build_ui` above.)

        # Personal URL panel (only shown when we actually know the URL).
        self.url_panel = QFrame()
        self.url_panel.setProperty("role", "panel")
        url_layout = QHBoxLayout(self.url_panel)
        url_layout.setContentsMargins(8, 6, 8, 6)
        url_layout.setSpacing(6)

        self.personal_url_input = QLineEdit()
        self.personal_url_input.setReadOnly(True)
        self.personal_url_input.setPlaceholderText("Personal URL")
        url_layout.addWidget(self.personal_url_input, 1)

        self.copy_url_btn = QPushButton("Copy")
        self.copy_url_btn.setFixedWidth(64)
        self.copy_url_btn.clicked.connect(self._copy_personal_url)
        url_layout.addWidget(self.copy_url_btn)

        left.addWidget(self.url_panel)

        # Controls group box — wraps both the stable signed-in layout and a
        # transient area used for the signed-out / auth-code flows.
        self.controls_group = QGroupBox("Controls")
        controls_outer = QVBoxLayout(self.controls_group)
        controls_outer.setContentsMargins(12, 16, 12, 16)
        controls_outer.setSpacing(8)

        # Stable signed-in controls: built once with all widgets persistent
        # so the layout never shifts between Ready / In Call / Daemon Off —
        # state changes just flip enabled/label/color.
        self.signed_in_area = self._build_signed_in_controls()
        controls_outer.addWidget(self.signed_in_area)

        # Transient area: hosts signed-out / auth-code views, which *do*
        # rebuild on demand because their widget sets differ.
        self.transient_area = QWidget()
        self.transient_layout = QVBoxLayout(self.transient_area)
        self.transient_layout.setContentsMargins(0, 0, 0, 4)
        self.transient_layout.setSpacing(6)
        controls_outer.addWidget(self.transient_area)
        left.addWidget(self.controls_group)

        # Output (always visible per user preference).
        output_group = QGroupBox("Output")
        output_layout = QVBoxLayout(output_group)
        output_layout.setContentsMargins(10, 12, 10, 10)
        output_layout.setSpacing(6)

        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setMinimumHeight(90)
        self.output_text.setFont(QFont("Monospace", 9))
        output_layout.addWidget(self.output_text, 1)

        # Bottom row of the output area: daemon toggle on the left, Clear on
        # the right. Keeping the daemon button out of the main controls stack
        # avoids the cramped spacing under Share Screen and matches the user's
        # expectation of a low-traffic administrative action living at the
        # window's bottom-left.
        clear_row = QHBoxLayout()
        self.daemon_btn = QPushButton("Stop Daemon")
        self.daemon_btn.setMinimumHeight(26)
        # Wide enough for bold "Start Daemon" (success-kind font-weight is 600).
        self.daemon_btn.setMinimumWidth(130)
        self.daemon_btn.clicked.connect(self._on_daemon_clicked)
        clear_row.addWidget(self.daemon_btn)
        clear_row.addStretch(1)
        clear_btn = QPushButton("Clear")
        clear_btn.setFixedWidth(72)
        clear_btn.clicked.connect(self.output_text.clear)
        clear_row.addWidget(clear_btn)
        output_layout.addLayout(clear_row)

        left.addWidget(output_group, 1)

        # === RIGHT COLUMN =====================================================
        right = QVBoxLayout()
        right.setSpacing(10)
        body.addLayout(right, 1)

        # Rooms (top of right column). Configuration lives in the Settings
        # dialog now — no inline "Configure" button here.
        self.rooms_group = QGroupBox("Rooms")
        rooms_outer = QVBoxLayout(self.rooms_group)
        rooms_outer.setContentsMargins(10, 12, 10, 10)
        rooms_outer.setSpacing(6)

        self.rooms_container = QWidget()
        self.rooms_container_layout = QVBoxLayout(self.rooms_container)
        self.rooms_container_layout.setContentsMargins(0, 0, 0, 0)
        self.rooms_container_layout.setSpacing(4)
        rooms_outer.addWidget(self.rooms_container)

        right.addWidget(self.rooms_group)

        # Contacts (below rooms, expands to fill).
        self.contacts_group = QGroupBox("Contacts")
        contacts_outer = QVBoxLayout(self.contacts_group)
        contacts_outer.setContentsMargins(10, 12, 10, 10)
        self.contacts_panel = ContactsPanel(run_command=self.run_command)
        contacts_outer.addWidget(self.contacts_panel)
        right.addWidget(self.contacts_group, 1)

        # ---- Footer (full width) ----
        self.footer_label = QLabel("")
        self.footer_label.setObjectName("footer")
        root.addWidget(self.footer_label)

        self._load_rooms()

    def _build_account_menu(self):
        self.account_menu.clear()
        self.account_signin_action = QAction("Sign In", self)
        self.account_signin_action.triggered.connect(self._start_signin)
        self.account_menu.addAction(self.account_signin_action)

        self.account_signout_action = QAction("Sign Out", self)
        self.account_signout_action.triggered.connect(
            lambda: self.run_command("tuple logout")
        )
        self.account_menu.addAction(self.account_signout_action)

        self.account_menu.addSeparator()
        show_native = QAction("Show Native Tuple UI", self)
        show_native.triggered.connect(lambda: self.run_command("tuple ui"))
        self.account_menu.addAction(show_native)

    def _show_account_menu(self):
        self.account_menu.exec(
            self.account_btn.mapToGlobal(QPoint(0, self.account_btn.height()))
        )

    def _clear_transient_area(self):
        while self.transient_layout.count():
            item = self.transient_layout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                continue
            sub = item.layout()
            if sub:
                self._clear_sublayout(sub)
                sub.setParent(None)

    def _clear_sublayout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
            sub = item.layout()
            if sub:
                self._clear_sublayout(sub)

    def rebuild_actions(self):
        """Switch between the stable signed-in controls and transient views.

        Widgets inside `signed_in_area` are persistent — we only flip their
        enabled/label/colour in `_apply_signed_in_state`. The transient
        area is rebuilt on demand for sign-in flows.
        """
        if not self.state.is_logged_in:
            self.signed_in_area.setVisible(False)
            self.transient_area.setVisible(True)
            self._clear_transient_area()
            if self._awaiting_auth_code:
                self._build_auth_code_state()
            else:
                self._build_signed_out_state()
            return

        self.transient_area.setVisible(False)
        self._clear_transient_area()
        self.signed_in_area.setVisible(True)
        self._apply_signed_in_state()

    def _build_signed_out_state(self):
        msg = QLabel("You're not signed in to Tuple.")
        msg.setStyleSheet(f"color: {TEXT_MUTED};")
        msg.setWordWrap(True)
        self.transient_layout.addWidget(msg)

        sign_in = QPushButton("Sign In")
        sign_in.setProperty("kind", "primary")
        sign_in.setMinimumHeight(36)
        sign_in.clicked.connect(self._start_signin)
        self.transient_layout.addWidget(sign_in)
        self.transient_layout.addStretch(1)

    def _build_auth_code_state(self):
        msg = QLabel(
            "Complete sign-in in your browser, then paste the auth code below."
        )
        msg.setStyleSheet(f"color: {TEXT_MUTED};")
        msg.setWordWrap(True)
        self.transient_layout.addWidget(msg)

        self.auth_code_input = QLineEdit()
        self.auth_code_input.setPlaceholderText("Auth code")
        self.auth_code_input.returnPressed.connect(self._submit_auth_code)
        self.transient_layout.addWidget(self.auth_code_input)

        row = QHBoxLayout()
        submit = QPushButton("Submit")
        submit.setProperty("kind", "primary")
        submit.clicked.connect(self._submit_auth_code)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self._cancel_signin)
        row.addWidget(submit, 1)
        row.addWidget(cancel, 0)
        self.transient_layout.addLayout(row)
        self.transient_layout.addStretch(1)

    # ------------- Signed-in stable controls (persistent widgets) --------

    def _build_signed_in_controls(self):
        """Build the one fixed layout used for Daemon Off / Ready / In Call.

        Widgets are created once and stored on self; state changes only
        toggle `setEnabled`, labels and colours via `_apply_signed_in_state`.
        Nothing in here is ever rebuilt, so the button positions don't
        shift when the call state changes.
        """
        BTN_W = 140
        BTN_H = 26

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 4)
        layout.setSpacing(10)

        # --- URL input + Join Call row -----------------------------------
        join_row = QHBoxLayout()
        join_row.setContentsMargins(0, 0, 0, 0)
        join_row.setSpacing(6)
        self.call_url_input = QLineEdit()
        self.call_url_input.setPlaceholderText("Paste a call URL to join…")
        self.call_url_input.returnPressed.connect(self._join_call)
        join_row.addWidget(self.call_url_input, 1)

        self.join_btn = QPushButton("Join Call")
        self.join_btn.setMinimumHeight(BTN_H)
        self.join_btn.clicked.connect(self._join_call)
        join_row.addWidget(self.join_btn, 0)
        layout.addLayout(join_row)

        # --- Primary action: New Call ↔ Hang Up --------------------------
        # Single persistent button whose label / `kind` property swaps
        # between "New Call" (primary purple) and "Hang Up" (danger red).
        self.primary_btn = QPushButton("New Call")
        self.primary_btn.setMinimumHeight(36)
        self.primary_btn.clicked.connect(self._on_primary_clicked)
        layout.addWidget(self.primary_btn)

        # --- Mute row ----------------------------------------------------
        self.mute_btn = QPushButton("Mute")
        self.mute_btn.setFixedSize(BTN_W, BTN_H)
        self.mute_btn.clicked.connect(self._on_mute_clicked)
        self.mute_sidecar = QLabel("mic on")
        self.mute_sidecar.setProperty("role", "sidecar")
        self.mute_sidecar.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        mute_row = QHBoxLayout()
        mute_row.setContentsMargins(0, 0, 0, 0)
        mute_row.setSpacing(8)
        mute_row.addWidget(self.mute_btn, 0)
        mute_row.addWidget(self.mute_sidecar, 0)
        mute_row.addStretch(1)
        layout.addLayout(mute_row)

        # --- Share row (with capture combo) ------------------------------
        self.share_btn = QPushButton("Share Screen")
        self.share_btn.setFixedSize(BTN_W, BTN_H)
        self.share_btn.clicked.connect(self._on_share_clicked)
        self.capture_combo = QComboBox()
        self.capture_combo.addItems(["auto", "x11", "portal"])
        self.capture_combo.setFixedHeight(BTN_H)
        self.capture_combo.setMinimumWidth(90)
        self.capture_combo.setToolTip("Screen capture mechanism (tuple set capture)")
        self.capture_combo.currentTextChanged.connect(self._on_capture_changed)
        share_row = QHBoxLayout()
        share_row.setContentsMargins(0, 0, 0, 0)
        share_row.setSpacing(8)
        share_row.addWidget(self.share_btn, 0)
        share_row.addWidget(self.capture_combo, 0, Qt.AlignmentFlag.AlignVCenter)
        share_row.addStretch(1)
        layout.addLayout(share_row)

        # Daemon toggle lives in the Output area's bottom row, not here —
        # see `_build_ui` where `self.daemon_btn` is created next to Clear.

        layout.addStretch(1)
        return container

    def _apply_signed_in_state(self):
        """Flip enabled/label/kind on the persistent controls from state."""
        running = self.state.daemon_running
        in_call = self.state.in_call

        # URL input + Join: usable only when we have a live daemon and
        # aren't already on a call.
        can_join = running and not in_call
        self.call_url_input.setEnabled(can_join)
        self.join_btn.setEnabled(can_join)

        # Primary button: "Hang Up" (danger) while in call; "New Call"
        # (primary purple) otherwise. Disabled when the daemon is off.
        if in_call:
            self.primary_btn.setText("Hang Up")
            self._set_button_kind(self.primary_btn, "danger")
            self.primary_btn.setEnabled(True)
        else:
            self.primary_btn.setText("New Call")
            self._set_button_kind(self.primary_btn, "primary")
            self.primary_btn.setEnabled(running)

        # Mute — only meaningful in-call. Keep visible but disabled otherwise.
        self.mute_btn.setEnabled(in_call)
        if in_call and self.state.is_muted:
            self.mute_btn.setText("Unmute")
            self._set_sidecar(self.mute_sidecar, "MUTED", "sidecar-alert")
        elif in_call:
            self.mute_btn.setText("Mute")
            self._set_sidecar(self.mute_sidecar, "mic on", "sidecar")
        else:
            self.mute_btn.setText("Mute")
            self._set_sidecar(self.mute_sidecar, "—", "sidecar-muted")

        # Share + capture — same treatment.
        self.share_btn.setEnabled(in_call)
        self.capture_combo.setEnabled(in_call)
        self.share_btn.setText("Unshare Screen" if in_call and self.state.is_sharing else "Share Screen")
        # Sync capture combo without firing the change handler.
        desired_capture = (
            self._capture_setting if self._capture_setting in ("auto", "x11", "portal") else "auto"
        )
        if self.capture_combo.currentText() != desired_capture:
            self.capture_combo.blockSignals(True)
            self.capture_combo.setCurrentText(desired_capture)
            self.capture_combo.blockSignals(False)

        # Daemon toggle.
        if running:
            self.daemon_btn.setText("Stop Daemon")
            self._set_button_kind(self.daemon_btn, None)
        else:
            self.daemon_btn.setText("Start Daemon")
            self._set_button_kind(self.daemon_btn, "success")

    @staticmethod
    def _set_button_kind(btn, kind):
        """Swap a QPushButton's `kind` QSS property and re-polish."""
        current = btn.property("kind")
        if current == kind:
            return
        if kind is None:
            # Clearing: Qt has no delete-property API on stylesheet lookup,
            # so set an empty string (matches default QPushButton rule).
            btn.setProperty("kind", "")
        else:
            btn.setProperty("kind", kind)
        btn.style().unpolish(btn)
        btn.style().polish(btn)
        btn.update()

    @staticmethod
    def _set_sidecar(label, text, role):
        label.setText(text)
        if label.property("role") != role:
            label.setProperty("role", role)
            label.style().unpolish(label)
            label.style().polish(label)

    # ------------- Click dispatchers --------------------------------------

    def _on_primary_clicked(self):
        if self.state.in_call:
            self.run_command("tuple end")
        else:
            self.run_command("tuple new")

    def _on_mute_clicked(self):
        if self.state.is_muted:
            self.run_command("tuple unmute")
        else:
            self.run_command("tuple mute")

    def _on_share_clicked(self):
        if self.state.is_sharing:
            self.run_command("tuple unshare")
        else:
            self.run_command("tuple share")

    def _on_daemon_clicked(self):
        if self.state.daemon_running:
            self.run_command("tuple off")
        else:
            self.run_command("tuple on")

    def _on_capture_changed(self, value):
        """User picked a new `capture` mechanism from the in-call combo."""
        if value == self._capture_setting:
            return
        self._capture_setting = value
        self.run_command(f"tuple set capture {value}")

    # ---------------------------------------------------- Rooms & output

    def _load_rooms(self):
        # Clear existing room buttons
        while self.rooms_container_layout.count():
            item = self.rooms_container_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)

        rooms = self.button_config.get_buttons()
        if not rooms:
            empty = QLabel("No rooms configured.\nAdd some in ⚙ Settings → Rooms.")
            empty.setStyleSheet(f"color: {TEXT_SUBTLE}; font-size: 9pt;")
            empty.setWordWrap(True)
            self.rooms_container_layout.addWidget(empty)
            return

        for i, (name, url) in enumerate(rooms):
            if self._demo_mode:
                label = f"Room {i + 1}"
                tooltip = "Demo room"
            else:
                label = name
                tooltip = url
            btn = QPushButton(label)
            btn.setToolTip(tooltip)
            btn.setMinimumHeight(26)
            btn.clicked.connect(lambda checked=False, u=url: self.run_command(f"tuple join {u}"))
            self.rooms_container_layout.addWidget(btn)

    def _open_settings(self):
        dlg = SettingsDialog(self, prefs=self.prefs, button_config=self.button_config)
        dlg.exec()
        # Reload rooms — user may have added/removed some inside the dialog.
        self._load_rooms()
        # Invalidate cached capture setting so sidecar reflects any change.
        self._capture_setting = None
        self._maybe_fetch_capture_setting()

    def _toggle_demo_mode(self, enabled):
        """Screenshot-mode toggle: anonymize contacts + rooms, mask URL,
        clear output, fake contact count (10–40).

        URL masking is driven by `self._demo_mode` inside `update_state`
        (which runs every 500ms), so the mask survives state ticks.
        """
        self._demo_mode = enabled
        if enabled:
            self.output_text.clear()
        if hasattr(self, "contacts_panel"):
            self.contacts_panel.set_demo_mode(enabled)
        # Rooms: labels read `self._demo_mode` inside `_load_rooms`.
        self._load_rooms()
        # Re-run state logic so URL gets (un)masked immediately.
        self.update_state()

    # ------------------------------------------------------------ Login flow

    def _start_signin(self):
        self._awaiting_auth_code = True
        self.run_command("tuple login")
        self.rebuild_actions()

    def _cancel_signin(self):
        self._awaiting_auth_code = False
        self.rebuild_actions()

    def _submit_auth_code(self):
        code = self.auth_code_input.text().strip() if hasattr(self, "auth_code_input") else ""
        if not code:
            QMessageBox.warning(self, "Input Required", "Please paste the auth code.")
            return
        self._awaiting_auth_code = False
        # Basic shell-safety: quote the code
        self.run_command(f'tuple auth "{code}"')
        # The log file will flip is_logged_in on next tick.
        self.rebuild_actions()

    # --------------------------------------------------------- Commands

    def run_command(self, command):
        if self.current_thread and self.current_thread.isRunning():
            QMessageBox.warning(
                self, "Command Running",
                "A command is already running. Please wait for it to complete.",
            )
            return

        self._pending_command = command
        self._log_output(f"$ {command}\n", False)
        self.current_thread = CommandThread(command)
        self.current_thread.output_ready.connect(self._handle_output)
        self.current_thread.start()

    def _handle_output(self, output, is_error):
        self._log_output(output, is_error)
        self.state.ingest_command_output(output)
        # Track mute/share state from the CLI's own response. The log file
        # only records CLI invocations and the daemon has no query command,
        # so parsing the command output is the best confirmation we get.
        # After `tuple mute` the CLI prints a confirmation containing
        # "muted" (e.g. "muted your microphone"); likewise "unmuted",
        # "shared", "unshared". Belt-and-braces: also trust the command we
        # just dispatched (optimistic) since the daemon errors loudly on
        # failure.
        cmd = (self._pending_command or "").strip()
        if not is_error and cmd:
            text = (output or "").lower()
            if cmd == "tuple mute" and "unmuted" not in text:
                self.state.set_mute(True)
            elif cmd == "tuple unmute":
                self.state.set_mute(False)
            elif cmd == "tuple share" and "unshared" not in text:
                self.state.set_share(True)
            elif cmd == "tuple unshare":
                self.state.set_share(False)
        # If `tuple ui` reports the native UI is already shown, close that
        # existing process and re-invoke — user wants one click to bring it
        # up, whether or not it was already running.
        if cmd == "tuple ui" and "already shown" in (output or "").lower():
            self._close_native_ui_and_retry()
        self._pending_command = None
        # Re-render immediately so mute/share toggle reflects the new state
        # without a 500ms lag, then do the delayed re-read to catch any
        # subsequent daemon-side changes (call ended, signaler dropped, etc.).
        self.update_state()
        QTimer.singleShot(500, self.update_state)

    def _close_native_ui_and_retry(self):
        """Close Tuple's native UI window, then re-invoke `tuple ui`.

        The native UI window is owned by the `tuple on` daemon process
        itself — there is no separate `tuple ui` process to SIGTERM (I
        verified by running `tuple ui` and watching the process list —
        only the daemon appears). So we close the window via the session's
        window manager and ask the CLI to re-show it.

        Strategies, tried in order:
          - KDE/KWin (X11 or Wayland): load a short script via
            `org.kde.kwin.Scripting` that calls closeWindow() on any
            top-level whose caption is exactly "Tuple".
          - X11 fallback: `wmctrl -c Tuple` if wmctrl is installed.
        """
        closed = self._close_tuple_window_kwin()
        if not closed:
            closed = self._close_tuple_window_wmctrl()

        if closed:
            # Give the window a moment to tear down before re-invoking.
            QTimer.singleShot(500, lambda: self.run_command("tuple ui"))
        else:
            self._log_output(
                "Native UI already shown, but couldn't locate the window to "
                "close it. On KDE this requires KWin scripting via D-Bus; on "
                "other X11 sessions install `wmctrl`.\n",
                True,
            )

    def _close_tuple_window_kwin(self):
        """Close the Tuple window via KWin's scripting D-Bus API.

        Match by resourceClass rather than caption: live testing showed the
        Tuple window's caption is often empty ("") while resourceClass is
        reliably "Tuple" (and resourceName is "tuple-main").
        """
        if "KDE" not in os.environ.get("XDG_CURRENT_DESKTOP", ""):
            return False
        import tempfile
        script_path = None
        try:
            # KWin 5 exposes workspace.clientList(); KWin 6 renamed it to
            # workspace.windowList(). Try both so this keeps working across
            # Plasma upgrades.
            script = (
                "const wins = (typeof workspace.windowList === 'function'"
                "  ? workspace.windowList()"
                "  : workspace.clientList());"
                "for (const w of wins) {"
                "  if ((w.resourceClass || '').toString() === 'Tuple') {"
                "    w.closeWindow();"
                "  }"
                "}"
            )
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".js", delete=False,
            ) as f:
                f.write(script)
                script_path = f.name

            load = subprocess.run(
                ["gdbus", "call", "--session",
                 "--dest", "org.kde.KWin",
                 "--object-path", "/Scripting",
                 "--method", "org.kde.kwin.Scripting.loadScript", script_path],
                capture_output=True, text=True, timeout=3,
            )
            if load.returncode != 0:
                return False
            import re as _re
            m = _re.search(r"\d+", load.stdout or "")
            if not m:
                return False
            script_id = m.group(0)
            run = subprocess.run(
                ["gdbus", "call", "--session",
                 "--dest", "org.kde.KWin",
                 "--object-path", f"/Scripting/Script{script_id}",
                 "--method", "org.kde.kwin.Script.run"],
                capture_output=True, text=True, timeout=3,
            )
            return run.returncode == 0
        except FileNotFoundError:
            # gdbus not installed.
            return False
        except Exception as e:
            self._log_output(f"KWin close attempt failed: {e}\n", True)
            return False
        finally:
            if script_path:
                try:
                    os.unlink(script_path)
                except OSError:
                    pass

    def _close_tuple_window_wmctrl(self):
        """Fallback: close by caption via wmctrl (X11 sessions only)."""
        try:
            result = subprocess.run(
                ["wmctrl", "-c", "Tuple"],
                capture_output=True, text=True, timeout=3,
            )
            return result.returncode == 0
        except FileNotFoundError:
            return False
        except Exception:
            return False

    def _log_output(self, text, is_error=False):
        if is_error:
            self.output_text.append(f'<span style="color: {DANGER};">{text}</span>')
        else:
            self.output_text.append(text)
        # `ensureCursorVisible` only scrolls enough to reveal the cursor,
        # which can leave a gap below the last line. Pin to the scroll max
        # so the newest output is always flush with the bottom edge.
        sb = self.output_text.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _join_call(self):
        url = self.call_url_input.text().strip() if hasattr(self, "call_url_input") else ""
        if not url:
            QMessageBox.warning(self, "Input Required", "Please enter a call URL.")
            return
        self.run_command(f"tuple join {url}")

    def _copy_personal_url(self):
        url = self.personal_url_input.text()
        if url:
            QApplication.clipboard().setText(url)
            self._log_output("URL copied to clipboard!\n", False)

    # ------------------------------------------------------------ State sync

    def update_state(self):
        previous_in_call = self.state.in_call
        self.state.update()

        if not previous_in_call and self.state.in_call:
            self.show()
            self.activateWindow()
            if hasattr(self, "show_action"):
                self.show_action.setText("Hide Window")

        # Header text
        if not self.state.is_logged_in:
            header = "Signed Out"
        elif not self.state.daemon_running:
            header = "Daemon Off"
        elif self.state.in_call:
            header = "In Call"
        else:
            header = "Ready"
        self.state_header.setText(header)

        # Personal URL visibility — only show when we actually have one.
        # (Recent Tuple versions don't log the slug, so we may never capture it
        #  from the log file. In that case we keep the panel hidden rather than
        #  showing an empty box.)
        ready_not_in_call = (
            self.state.is_logged_in and self.state.daemon_running and not self.state.in_call
        )
        have_url = bool(self.state.personal_url)
        self.url_panel.setVisible(ready_not_in_call and have_url)
        if have_url:
            if self._demo_mode:
                self.personal_url_input.setText("https://tuple.app/j/••••••••")
            else:
                self.personal_url_input.setText(self.state.personal_url)

        # Rooms / contacts visibility
        ready = self.state.is_logged_in and self.state.daemon_running
        self.rooms_group.setVisible(ready)
        self.contacts_group.setVisible(ready)

        # Auto-populate contacts the first time they become viewable.
        if ready and not self._contacts_loaded:
            self._contacts_loaded = True
            QTimer.singleShot(0, self.contacts_panel.refresh)

        # Footer summary
        sig = self.state.signaler_state.title() if self.state.signaler_state != "unknown" else "—"
        if self.state.is_logged_in and self.state.daemon_running:
            footer = f"Signaler: {sig} · Daemon running"
        elif self.state.is_logged_in:
            footer = "Signaler: — · Daemon off"
        else:
            footer = "Not signed in"
        self.footer_label.setText(footer)

        # Header color hint
        if self.state.in_call:
            self.state_header.setStyleSheet(f"color: {SUCCESS};")
        elif not self.state.is_logged_in or not self.state.daemon_running:
            self.state_header.setStyleSheet(f"color: {TEXT_MUTED};")
        else:
            self.state_header.setStyleSheet("")

        # Account menu: Sign In/Out visibility
        self.account_signin_action.setVisible(not self.state.is_logged_in)
        self.account_signout_action.setVisible(self.state.is_logged_in)

        self.rebuild_actions()
        self._update_tray_icon()

        # Cache capture setting lazily so in-call share sidecar can use it.
        self._maybe_fetch_capture_setting()

    def _maybe_fetch_capture_setting(self):
        if self._capture_setting is not None:
            return
        if not (self.state.is_logged_in and self.state.daemon_running):
            return
        settings, error = fetch_settings()
        if error:
            return
        for s in settings:
            if s["name"] == "capture":
                self._capture_setting = s["value"]
                break

    def _load_tuple_icon(self, size):
        return load_tuple_icon(size)

    # --------------------------------------------------------- Tray icon

    def _create_tray_pixmap(self):
        size = 64
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if not self.state.daemon_running:
            color = QColor(128, 128, 128)
            text = ""
        elif self.state.in_call:
            if self.state.is_muted:
                color = QColor(220, 50, 50)
                text = "M"
            else:
                color = QColor(50, 200, 80)
                text = ""
        else:
            color = QColor(139, 95, 191)  # accent
            text = ""

        painter.setBrush(color)
        painter.setPen(QPen(QColor(255, 255, 255, 180), 2))
        painter.drawEllipse(8, 8, 48, 48)

        if text:
            painter.setPen(QColor(255, 255, 255))
            font = painter.font()
            font.setPointSize(24)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, text)

        if self.state.is_sharing:
            painter.setBrush(QColor(255, 140, 0))
            painter.setPen(QPen(QColor(255, 255, 255), 2))
            painter.drawEllipse(42, 42, 16, 16)

        painter.end()
        return QIcon(pixmap)

    def _setup_tray_icon(self):
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(self._create_tray_pixmap())

        self.tray_menu = QMenu()

        self.show_action = QAction("Show Window", self)
        self.show_action.triggered.connect(self._toggle_window)
        self.tray_menu.addAction(self.show_action)

        show_native = QAction("Show Native Tuple UI", self)
        show_native.triggered.connect(lambda: self.run_command("tuple ui"))
        self.tray_menu.addAction(show_native)

        self.tray_menu.addSeparator()

        self.status_action = QAction("Status: —", self)
        self.status_action.setEnabled(False)
        self.tray_menu.addAction(self.status_action)

        self.tray_menu.addSeparator()

        self.tray_daemon_action = QAction("Start Daemon", self)
        self.tray_daemon_action.triggered.connect(self._tray_toggle_daemon)
        self.tray_menu.addAction(self.tray_daemon_action)

        self.tray_join_call_action = QAction("Join Call…", self)
        self.tray_join_call_action.triggered.connect(self._tray_join_call)
        self.tray_menu.addAction(self.tray_join_call_action)

        self.tray_new_call_action = QAction("New Call", self)
        self.tray_new_call_action.triggered.connect(lambda: self.run_command("tuple new"))
        self.tray_menu.addAction(self.tray_new_call_action)

        self.tray_end_call_action = QAction("Hang Up", self)
        self.tray_end_call_action.triggered.connect(lambda: self.run_command("tuple end"))
        self.tray_menu.addAction(self.tray_end_call_action)

        self.tray_mute_action = QAction("Mute", self)
        self.tray_mute_action.triggered.connect(self._tray_toggle_mute)
        self.tray_menu.addAction(self.tray_mute_action)

        self.tray_share_action = QAction("Share Screen", self)
        self.tray_share_action.triggered.connect(self._tray_toggle_share)
        self.tray_menu.addAction(self.tray_share_action)

        self.tray_menu.addSeparator()
        # Rooms injected dynamically before Quit.

        self.tray_settings_action = QAction("Settings…", self)
        self.tray_settings_action.triggered.connect(self._open_settings)
        self.tray_menu.addAction(self.tray_settings_action)

        self.tray_quit_action = QAction("Quit", self)
        self.tray_quit_action.triggered.connect(self.quit_application)
        self.tray_menu.addAction(self.tray_quit_action)

        self.tray_icon.setContextMenu(self.tray_menu)
        self.tray_icon.activated.connect(self._tray_activated)
        self.tray_icon.show()

        self.tray_icon.showMessage(
            "Tuple UI",
            "Running in tray. Left-click to mute, right-click for menu.",
            QSystemTrayIcon.MessageIcon.Information, 3000,
        )

    def _update_tray_icon(self):
        self.tray_icon.setIcon(self._create_tray_pixmap())

        if self.isVisible():
            self.show_action.setText("Hide Window")
        else:
            self.show_action.setText("Show Window")

        parts = []
        parts.append("Signed In" if self.state.is_logged_in else "Signed Out")
        parts.append("Daemon ON" if self.state.daemon_running else "Daemon OFF")
        if self.state.in_call:
            parts.append("IN CALL")
            if self.state.is_muted:
                parts.append("(Muted)")
            if self.state.is_sharing:
                parts.append("(Sharing)")
        else:
            if self.state.signaler_state == "connected":
                parts.append("Connected")
            elif self.state.signaler_state in ["connecting", "synchronizing"]:
                parts.append(self.state.signaler_state.title())
        self.tray_icon.setToolTip("Tuple — " + " | ".join(parts))
        self.status_action.setText("Status: " + " | ".join(parts[:2]))

        # Daemon action
        if self.state.daemon_running:
            self.tray_daemon_action.setText("Stop Daemon")
        else:
            self.tray_daemon_action.setText("Start Daemon")

        if self.state.daemon_running and not self.state.in_call:
            self.tray_join_call_action.setVisible(True)
            self.tray_new_call_action.setVisible(True)
            self.tray_end_call_action.setVisible(False)
            self.tray_mute_action.setVisible(False)
            self.tray_share_action.setVisible(False)
        elif self.state.in_call:
            self.tray_join_call_action.setVisible(False)
            self.tray_new_call_action.setVisible(False)
            self.tray_end_call_action.setVisible(True)
            self.tray_mute_action.setVisible(True)
            self.tray_mute_action.setText("Unmute" if self.state.is_muted else "Mute")
            self.tray_share_action.setVisible(True)
            self.tray_share_action.setText(
                "Unshare Screen" if self.state.is_sharing else "Share Screen"
            )
        else:
            self.tray_join_call_action.setVisible(False)
            self.tray_new_call_action.setVisible(False)
            self.tray_end_call_action.setVisible(False)
            self.tray_mute_action.setVisible(False)
            self.tray_share_action.setVisible(False)

        # Rebuild room actions: they live between share_action and settings_action.
        actions = self.tray_menu.actions()
        try:
            start = actions.index(self.tray_share_action) + 1
            end = actions.index(self.tray_settings_action)
        except ValueError:
            return
        # Remove existing room entries (and their leading separator).
        for act in actions[start:end]:
            self.tray_menu.removeAction(act)
        rooms = self.button_config.get_buttons()
        if rooms:
            sep = self.tray_menu.insertSeparator(self.tray_settings_action)
            for name, url in rooms:
                a = QAction(name, self)
                a.triggered.connect(lambda checked=False, u=url: self.run_command(f"tuple join {u}"))
                self.tray_menu.insertAction(self.tray_settings_action, a)

    # --------------------------------------------------- Tray interactions

    def _tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.state.in_call:
                self._tray_toggle_mute()
            else:
                self.tray_icon.showMessage(
                    "Tuple UI", "Not in a call - cannot toggle mute",
                    QSystemTrayIcon.MessageIcon.Warning, 2000,
                )
        elif reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._toggle_window()

    def _toggle_window(self):
        if self.isVisible():
            self.hide()
            self.show_action.setText("Show Window")
        else:
            self.show()
            self.activateWindow()
            self.show_action.setText("Hide Window")

    def _tray_toggle_daemon(self):
        if self.state.daemon_running:
            self.run_command("tuple off")
        else:
            self.run_command("tuple on")

    def _tray_toggle_mute(self):
        if self.state.is_muted:
            self.run_command("tuple unmute")
        else:
            self.run_command("tuple mute")

    def _tray_toggle_share(self):
        if self.state.is_sharing:
            self.run_command("tuple unshare")
        else:
            self.run_command("tuple share")

    def _tray_join_call(self):
        url, ok = QInputDialog.getText(
            self, "Join Call", "Enter call URL:", QLineEdit.EchoMode.Normal, "",
        )
        if ok and url.strip():
            self.run_command(f"tuple join {url.strip()}")

    # ---------------------------------------------------- Signals & quit

    def _install_signal_handlers(self):
        # Existing: SIGUSR1 = refresh state (used by toggle-tuple-mute helper)
        signal.signal(signal.SIGUSR1, self._on_sigusr1)
        # New: SIGUSR2 = show/raise window (used by second-instance launcher)
        signal.signal(signal.SIGUSR2, self._on_sigusr2)
        # SIGINT / SIGTERM: clean quit
        signal.signal(signal.SIGINT, self._on_termination_signal)
        signal.signal(signal.SIGTERM, self._on_termination_signal)
        # Keep Python signals responsive while Qt event loop runs.
        self._signal_tick = QTimer(self)
        self._signal_tick.timeout.connect(lambda: None)
        self._signal_tick.start(250)

    def _on_sigusr1(self, signum, frame):
        QTimer.singleShot(0, self.update_state)

    def _on_sigusr2(self, signum, frame):
        QTimer.singleShot(0, self._raise_to_foreground)

    def _raise_to_foreground(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def _on_termination_signal(self, signum, frame):
        QTimer.singleShot(0, self.quit_application)

    def closeEvent(self, event: QCloseEvent):
        if self._quitting:
            event.accept()
            return
        if self.tray_icon.isVisible():
            self.hide()
            self.tray_icon.showMessage(
                "Tuple UI",
                "Minimized to tray. Right-click the tray icon and choose Quit to exit.",
                QSystemTrayIcon.MessageIcon.Information, 2000,
            )
            event.ignore()
        else:
            event.accept()

    def quit_application(self):
        if self._quitting:
            return
        self._quitting = True

        try:
            self.state_timer.stop()
        except Exception:
            pass
        try:
            self._signal_tick.stop()
        except Exception:
            pass

        thread = self.current_thread
        if thread is not None and thread.isRunning():
            try:
                thread.cancel()
            except Exception:
                pass
            thread.wait(2000)

        try:
            self.tray_icon.hide()
        except Exception:
            pass

        QApplication.quit()


# ---------------------------------------------------------------------- main

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Tuple UI")
    # Bind the Wayland app_id (and X11 WM_CLASS) to our desktop entry so the
    # task list / Alt-Tab / Plasma taskmanager look up `tuple-ui.desktop` and
    # use its `Icon=` for the task-list icon. Without this, the task list
    # shows a generic "?" while the titlebar icon we set below works fine.
    app.setDesktopFileName("tuple-ui")
    # Desktop environments (Wayland, X11 taskbars, Alt-Tab) pick up the
    # application-level icon; setting both it and each window's icon covers
    # the places they diverge.
    app.setWindowIcon(load_tuple_icon())
    app.setQuitOnLastWindowClosed(False)
    apply_dark_theme(app)

    # Single-instance guard. If the lock exists but its owning PID is dead
    # we treat it as stale and remove the file directly (Qt's own staleness
    # check can be flaky), then retry.
    LOCK_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(LOCK_FILE_PATH))
    lock.setStaleLockTime(0)

    if not lock.tryLock(100):
        ok, pid, hostname, appname = lock.getLockInfo()
        pid_alive = False
        if ok and pid:
            try:
                os.kill(int(pid), 0)  # signal 0 = liveness probe, no effect
                pid_alive = True
            except (ProcessLookupError, PermissionError, OSError):
                pid_alive = False

        if pid_alive:
            try:
                os.kill(int(pid), signal.SIGUSR2)
                print(f"Another tuple-ui is running (pid {pid}); raised its window.")
            except Exception as e:
                print(f"Another tuple-ui is running (pid {pid}); could not signal it: {e}")
            sys.exit(0)

        # No live holder — clear the lock file (Qt API first, then filesystem).
        try:
            lock.removeStaleLockFile()
        except Exception:
            pass
        try:
            LOCK_FILE_PATH.unlink()
        except FileNotFoundError:
            pass
        except Exception as e:
            print(f"Could not remove stale lock file {LOCK_FILE_PATH}: {e}")
        if not lock.tryLock(100):
            print("Could not acquire tuple-ui lock after clearing stale lock.")
            sys.exit(1)

    window = TupleUI()  # noqa: F841 — kept alive by Qt
    if window.prefs.show_on_start:
        window.show()
    app.aboutToQuit.connect(lambda: lock.unlock())

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
