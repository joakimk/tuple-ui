"""Settings dialog — reads `tuple settings`, writes via `tuple set NAME VALUE`."""

import re
import subprocess

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QFrame,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)


SETTING_LINE_RE = re.compile(r"^\s*(?P<name>\S+)\s*\|\s*(?P<value>[^|]*?)\s*\|\s*(?P<desc>.*)$")
ENUM_RE = re.compile(r"\(([^()]*\|[^()]*)\)")


def parse_settings(text):
    """Parse `tuple settings` output into a list of (name, value, description, options)."""
    settings = []
    for line in text.splitlines():
        m = SETTING_LINE_RE.match(line)
        if not m:
            continue
        name = m.group("name").strip()
        value = m.group("value").strip()
        desc = m.group("desc").strip()

        options = None
        enum_match = ENUM_RE.search(desc)
        if enum_match:
            raw_options = [o.strip() for o in enum_match.group(1).split("|")]
            # Only treat as enum if every option looks like a short token.
            if all(raw_options) and all(len(o) <= 30 for o in raw_options):
                options = raw_options

        settings.append({
            "name": name,
            "value": value,
            "desc": desc,
            "options": options,
        })
    return settings


def fetch_settings():
    """Run `tuple settings` and parse it. Returns (list, error_str_or_none)."""
    try:
        result = subprocess.run(
            ["tuple", "settings"],
            capture_output=True, text=True, timeout=10,
        )
    except FileNotFoundError:
        return [], "`tuple` CLI not found on PATH"
    except subprocess.TimeoutExpired:
        return [], "Timed out calling `tuple settings`"
    except Exception as e:  # pragma: no cover - defensive
        return [], f"Error: {e}"

    if result.returncode != 0:
        return [], (result.stderr or result.stdout or "unknown error").strip()

    return parse_settings(result.stdout), None


class SettingsDialog(QDialog):
    """Dialog for viewing and editing `tuple` settings plus UI preferences.

    `prefs` is an optional UIPrefs instance; when provided, a "UI Preferences"
    section is rendered. `button_config` is an optional FastButtonConfig; when
    provided, a "Rooms" section is rendered for managing room shortcuts.
    """

    def __init__(self, parent=None, prefs=None, button_config=None):
        super().__init__(parent)
        self.prefs = prefs
        self.button_config = button_config
        self.setWindowTitle("Tuple Settings")
        # UI prefs + Rooms + CLI settings list all want real estate. Default
        # to something comfortable so the user doesn't have to resize on
        # every open.
        self.setMinimumWidth(560)
        self.setMinimumHeight(620)
        self.resize(640, 720)

        self._editors = {}        # name -> QLineEdit | QComboBox
        self._original = {}       # name -> value str
        self._settings = []
        self._changed_names = []  # populated on accept
        self._room_row_widgets = {}  # room name -> container widget

        self._build_ui()
        self._load()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # --- UI Preferences (app-level, persisted to ~/.tuple_ui_prefs.json) ---
        if self.prefs is not None:
            prefs_group = QGroupBox("UI Preferences")
            prefs_layout = QVBoxLayout(prefs_group)
            prefs_layout.setContentsMargins(10, 14, 10, 10)
            prefs_layout.setSpacing(6)

            self.show_on_start_cb = QCheckBox("Show window on start")
            self.show_on_start_cb.setChecked(self.prefs.show_on_start)
            self.show_on_start_cb.setToolTip(
                "When enabled, the Tuple UI window is shown at launch. "
                "Otherwise it stays hidden in the tray."
            )
            prefs_layout.addWidget(self.show_on_start_cb)
            layout.addWidget(prefs_group)

        # --- Rooms (shortcuts for `tuple join <URL>`) ---
        if self.button_config is not None:
            rooms_group = QGroupBox("Rooms")
            rooms_outer = QVBoxLayout(rooms_group)
            rooms_outer.setContentsMargins(10, 14, 10, 10)
            rooms_outer.setSpacing(6)

            self._rooms_list_layout = QVBoxLayout()
            self._rooms_list_layout.setContentsMargins(0, 0, 0, 0)
            self._rooms_list_layout.setSpacing(4)
            rooms_outer.addLayout(self._rooms_list_layout)

            self._rooms_empty_label = QLabel("No rooms configured yet.")
            self._rooms_empty_label.setStyleSheet("color: #9aa0a6; font-size: 9pt;")
            rooms_outer.addWidget(self._rooms_empty_label)

            # Add-room row
            add_row = QHBoxLayout()
            add_row.setSpacing(6)
            self._new_room_name = QLineEdit()
            self._new_room_name.setPlaceholderText("Name (e.g. Dev)")
            self._new_room_name.setMaximumWidth(140)
            add_row.addWidget(self._new_room_name)
            self._new_room_url = QLineEdit()
            self._new_room_url.setPlaceholderText("https://tuple.app/c/…")
            add_row.addWidget(self._new_room_url, 1)
            add_btn = QPushButton("Add")
            add_btn.setProperty("kind", "primary")
            add_btn.setFixedWidth(72)
            add_btn.clicked.connect(self._add_room)
            add_row.addWidget(add_btn)
            rooms_outer.addLayout(add_row)

            layout.addWidget(rooms_group)
            self._refresh_rooms_list()

        # --- Tuple CLI settings ---
        cli_label = QLabel("Tuple CLI Settings")
        cli_label.setStyleSheet("font-weight: 600; margin-top: 4px;")
        layout.addWidget(cli_label)

        self.status_label = QLabel("Loading settings…")
        self.status_label.setStyleSheet("color: #9aa0a6;")
        layout.addWidget(self.status_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        self.form_layout = QFormLayout(container)
        self.form_layout.setContentsMargins(0, 0, 0, 0)
        self.form_layout.setSpacing(8)
        self.form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        scroll.setWidget(container)
        layout.addWidget(scroll, 1)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self._on_save)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def _load(self):
        settings, error = fetch_settings()
        if error:
            self.status_label.setText(f"Could not load settings: {error}")
            self.buttons.button(QDialogButtonBox.StandardButton.Save).setEnabled(False)
            return

        self._settings = settings
        self.status_label.setText(
            f"{len(settings)} setting{'s' if len(settings) != 1 else ''} · edits are applied with `tuple set` on Save"
        )

        for s in settings:
            label = QLabel(s["name"])
            label.setToolTip(s["desc"] or s["name"])

            if s["options"]:
                editor = QComboBox()
                editor.addItems(s["options"])
                if s["value"] in s["options"]:
                    editor.setCurrentText(s["value"])
                else:
                    editor.setEditable(True)
                    editor.setCurrentText(s["value"])
            else:
                editor = QLineEdit(s["value"])

            editor.setToolTip(s["desc"] or "")
            self._editors[s["name"]] = editor
            self._original[s["name"]] = s["value"]
            self.form_layout.addRow(label, editor)

    # ------------------------------------------------------------ Rooms

    def _refresh_rooms_list(self):
        """Redraw the rooms list from button_config."""
        # Clear existing rows
        while self._rooms_list_layout.count():
            item = self._rooms_list_layout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
        self._room_row_widgets.clear()

        rooms = self.button_config.get_buttons()
        self._rooms_empty_label.setVisible(not rooms)
        for name, url in rooms:
            row_widget = QWidget()
            row = QHBoxLayout(row_widget)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(6)
            name_label = QLabel(name)
            name_label.setMinimumWidth(100)
            row.addWidget(name_label)
            url_edit = QLineEdit(url)
            url_edit.setReadOnly(True)
            row.addWidget(url_edit, 1)
            del_btn = QPushButton("Delete")
            del_btn.setFixedWidth(72)
            del_btn.clicked.connect(lambda _=False, n=name: self._delete_room(n))
            row.addWidget(del_btn)
            self._rooms_list_layout.addWidget(row_widget)
            self._room_row_widgets[name] = row_widget

    def _add_room(self):
        name = self._new_room_name.text().strip()
        url = self._new_room_url.text().strip()
        if not name:
            QMessageBox.warning(self, "Input Error", "Please enter a room name.")
            return
        if not url:
            QMessageBox.warning(self, "Input Error", "Please enter a URL.")
            return
        if name in self.button_config.buttons:
            QMessageBox.warning(self, "Duplicate", f"Room '{name}' already exists.")
            return
        self.button_config.add_button(name, url)
        self._new_room_name.clear()
        self._new_room_url.clear()
        self._refresh_rooms_list()

    def _delete_room(self, name):
        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"Delete the '{name}' room?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.button_config.remove_button(name)
        self._refresh_rooms_list()

    # ------------------------------------------------------------ CLI settings

    def _current_value(self, name):
        editor = self._editors[name]
        if isinstance(editor, QComboBox):
            return editor.currentText().strip()
        return editor.text().strip()

    def changed(self):
        """Return list of (name, new_value) for modified settings."""
        changes = []
        for name, original in self._original.items():
            new_value = self._current_value(name)
            if new_value != original:
                changes.append((name, new_value))
        return changes

    def _on_save(self):
        # Persist UI preferences first (cheap, local file).
        if self.prefs is not None:
            self.prefs.set("show_on_start", self.show_on_start_cb.isChecked())
            self.prefs.save()

        changes = self.changed()
        if not changes:
            self.accept()
            return

        errors = []
        applied = []
        for name, value in changes:
            try:
                # `tuple set NAME VALUE` — pass VALUE as a single arg even when empty.
                result = subprocess.run(
                    ["tuple", "set", name, value],
                    capture_output=True, text=True, timeout=10,
                )
                if result.returncode != 0:
                    errors.append(f"{name}: {(result.stderr or result.stdout).strip()}")
                else:
                    applied.append(name)
            except Exception as e:  # pragma: no cover - defensive
                errors.append(f"{name}: {e}")

        self._changed_names = applied

        if errors:
            QMessageBox.warning(
                self, "Some settings failed",
                "Applied: " + (", ".join(applied) or "(none)")
                + "\n\nFailed:\n" + "\n".join(errors),
            )
            # Still close — user can reopen to see current state.
        self.accept()
