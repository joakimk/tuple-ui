"""Contacts panel — parses `tuple ls`, renders rows with Call + favorite toggle."""

import random
import re
import subprocess

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout,
    QWidget,
)

from tuple_ui_theme import SUCCESS, TEXT_MUTED, TEXT_SUBTLE, WARN

# Example line from `tuple ls`:
#   123 Jane Doe <jane@example.com> [unavailable] (favorite)
CONTACT_RE = re.compile(
    r"^\s*(?P<id>\d+)\s+(?P<name>.+?)\s+<(?P<email>[^>]+)>\s+\[(?P<status>\w+)\]"
    r"(?P<fav>\s+\(favorite\))?\s*$"
)

# Example line from `tuple call` (the numbered favorites list the CLI prints
# before prompting for a number):
#     1) John Smith <john.smith@example.com>
CALL_ITEM_RE = re.compile(
    r"^\s*(?P<num>\d+)\)\s+(?P<name>.+?)\s+<(?P<email>[^>]+)>\s*$"
)

STATUS_COLOR = {
    "available": SUCCESS,
    "unavailable": WARN,
    "offline": TEXT_SUBTLE,
}


def parse_contacts(text):
    """Parse `tuple ls` output into list of dicts."""
    contacts = []
    for line in text.splitlines():
        m = CONTACT_RE.match(line)
        if not m:
            continue
        contacts.append({
            "id": m.group("id"),
            "name": m.group("name").strip(),
            "email": m.group("email"),
            "status": m.group("status"),
            "favorite": bool(m.group("fav")),
            "call_number": None,  # filled in from parse_call_list()
        })
    return contacts


def parse_call_list(text):
    """Parse the numbered favorites list printed by `tuple call`.

    Returns a dict mapping lowercased email → call number (int).
    """
    mapping = {}
    for line in text.splitlines():
        m = CALL_ITEM_RE.match(line)
        if not m:
            continue
        mapping[m.group("email").lower()] = int(m.group("num"))
    return mapping


def fetch_contacts():
    """Run `tuple ls` and return (contacts, error_or_none)."""
    try:
        result = subprocess.run(
            ["tuple", "ls"], capture_output=True, text=True, timeout=10,
        )
    except FileNotFoundError:
        return [], "`tuple` CLI not found on PATH"
    except subprocess.TimeoutExpired:
        return [], "Timed out calling `tuple ls`"
    except Exception as e:  # pragma: no cover
        return [], f"Error: {e}"

    if result.returncode != 0:
        return [], (result.stderr or result.stdout or "unknown error").strip()
    return parse_contacts(result.stdout), None


def fetch_call_numbers():
    """Run `tuple call` to read the numbered favorites list, then abort.

    The CLI prints the list to stdout and then blocks on `enter a number to
    call:`. We feed a single newline so the prompt gets an empty answer,
    which aborts the call without dialing anyone. Returns dict of
    lowercase-email → number (empty dict on any failure — calling is
    non-critical).
    """
    try:
        result = subprocess.run(
            ["tuple", "call"],
            capture_output=True, text=True, timeout=5,
            input="\n",
        )
    except Exception:
        return {}
    return parse_call_list((result.stdout or "") + (result.stderr or ""))


def sort_contacts(contacts):
    """Favorites first, then available > unavailable > offline, then by name."""
    status_rank = {"available": 0, "unavailable": 1, "offline": 2}
    return sorted(
        contacts,
        key=lambda c: (
            0 if c["favorite"] else 1,
            status_rank.get(c["status"], 3),
            c["name"].lower(),
        ),
    )


class ContactRow(QFrame):
    """A single contact line inside the ContactsPanel."""

    def __init__(self, contact, run_command, on_favorite_toggled, parent=None):
        super().__init__(parent)
        self.contact = contact
        self._run_command = run_command
        self._on_favorite_toggled = on_favorite_toggled
        self.setObjectName("contactRow")
        self._build()

    def _build(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        # Status dot
        dot = QLabel("●")
        color = STATUS_COLOR.get(self.contact["status"], TEXT_MUTED)
        dot.setStyleSheet(f"color: {color}; font-size: 11pt;")
        dot.setToolTip(self.contact["status"])
        layout.addWidget(dot)

        # Name + email tooltip
        name_label = QLabel(self.contact["name"])
        name_label.setToolTip(
            f'{self.contact["email"]} · id {self.contact["id"]} · {self.contact["status"]}'
        )
        layout.addWidget(name_label, 1)

        # Favorite star toggle
        star = QPushButton("★" if self.contact["favorite"] else "☆")
        star.setProperty("kind", "icon")
        star.setStyleSheet(
            f"color: {WARN};" if self.contact["favorite"] else f"color: {TEXT_MUTED};"
        )
        star.setToolTip("Unfavorite" if self.contact["favorite"] else "Favorite")
        star.setFixedWidth(28)
        star.clicked.connect(self._toggle_favorite)
        layout.addWidget(star)

        # Call button — `tuple call` only accepts a 1-based index into its
        # own numbered list, and that list only contains *available*
        # favorites. Three cases for the disabled state:
        #   - available favorite: button enabled, dials via piped index
        #   - favorite but unavailable/offline: disabled, explain status
        #   - not a favorite: disabled, suggest favoriting
        call = QPushButton("Call")
        call.setFixedWidth(60)
        call_number = self.contact.get("call_number")
        if call_number is not None:
            call.setToolTip(f"Call {self.contact['name']} (tuple favorite #{call_number})")
            call.clicked.connect(
                lambda: self._run_command(f"echo {call_number} | tuple call")
            )
        else:
            call.setEnabled(False)
            if self.contact["favorite"]:
                call.setToolTip(
                    f"{self.contact['name']} is {self.contact['status']} — "
                    "Tuple only lists available favorites as callable."
                )
            else:
                call.setToolTip(
                    "Only favorites can be dialed from here — the `tuple call` "
                    "CLI only knows how to call favorites. Click ☆ to favorite."
                )
        layout.addWidget(call)

    def _toggle_favorite(self):
        cmd = "unfavorite" if self.contact["favorite"] else "favorite"
        self._run_command(f"tuple {cmd} {self.contact['id']}")
        # Optimistic toggle — panel will refresh when parent pokes us.
        self._on_favorite_toggled(self.contact["id"])


class ContactsPanel(QWidget):
    """Scrollable list of contacts with a header + refresh button."""

    def __init__(self, run_command, parent=None):
        super().__init__(parent)
        self._run_command = run_command
        self._contacts = []
        self._demo_mode = False
        self._demo_contacts = []  # synthetic roster shown while in demo mode
        self._build_ui()

    def set_demo_mode(self, enabled):
        """Toggle screenshot-friendly mode.

        When enabled, replace the real roster with a synthetic one of a random
        size in [10, 40] so the visible list matches the displayed count. The
        synthetic list is generated once per enable so re-rebuilds stay stable.
        """
        if self._demo_mode == enabled:
            return
        self._demo_mode = enabled
        if enabled:
            count = random.randint(10, 40)
            self._demo_contacts = self._generate_fake_contacts(count)
        else:
            self._demo_contacts = []
        self._rebuild_rows()
        self._update_status_label()

    def _update_status_label(self):
        """Refresh the header text based on current mode + roster."""
        roster = self._displayed_contacts()
        if not roster:
            self.status_label.setText("No contacts loaded")
            return
        available = sum(1 for c in roster if c["status"] == "available")
        favs = sum(1 for c in roster if c["favorite"])
        suffix = " · demo mode" if self._demo_mode else ""
        self.status_label.setText(
            f"{len(roster)} contacts · {favs} favorites · {available} available{suffix}"
        )

    def _displayed_contacts(self):
        return self._demo_contacts if self._demo_mode else self._contacts

    @staticmethod
    def _generate_fake_contacts(count):
        """Build a plausible-looking fake roster: mix of statuses, a handful of
        favorites up top, call numbers only for available favorites."""
        statuses = ["available", "available", "unavailable", "offline"]
        fav_count = max(3, count // 5)
        contacts = []
        call_num = 0
        for i in range(count):
            n = i + 1
            status = statuses[i % len(statuses)]
            is_fav = i < fav_count
            call_number = None
            if is_fav and status == "available":
                call_num += 1
                call_number = call_num
            contacts.append({
                "id": str(9000 + n),
                "name": f"Person {n}",
                "email": f"person{n}@example.com",
                "status": status,
                "favorite": is_fav,
                "call_number": call_number,
            })
        return sort_contacts(contacts)

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)

        # Header row: status label + refresh button
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(6)

        self.status_label = QLabel("No contacts loaded")
        self.status_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 8pt;")
        header.addWidget(self.status_label, 1)

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setFixedWidth(72)
        self.refresh_btn.clicked.connect(self.refresh)
        header.addWidget(self.refresh_btn)
        outer.addLayout(header)

        # Scrollable list
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setMinimumHeight(120)
        self.list_container = QWidget()
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(4)
        self.list_layout.addStretch(1)
        self.scroll.setWidget(self.list_container)
        outer.addWidget(self.scroll, 1)

    def refresh(self):
        self.refresh_btn.setEnabled(False)
        self.status_label.setText("Refreshing…")
        try:
            contacts, error = fetch_contacts()
            if error:
                self.status_label.setText(f"Error: {error}")
                return
            # Join by email to attach `tuple call` favorite numbers — emails
            # are more stable than names (Cyrillic/whitespace/etc.).
            call_numbers = fetch_call_numbers()
            for c in contacts:
                c["call_number"] = call_numbers.get(c["email"].lower())
            self._contacts = sort_contacts(contacts)
            self._rebuild_rows()
            self._update_status_label()
        finally:
            self.refresh_btn.setEnabled(True)

    def _rebuild_rows(self):
        # Clear existing rows (keep trailing stretch)
        while self.list_layout.count() > 1:
            item = self.list_layout.takeAt(0)
            if item and item.widget():
                item.widget().setParent(None)

        for contact in self._displayed_contacts():
            row = ContactRow(
                contact,
                run_command=self._run_command,
                on_favorite_toggled=self._mark_favorite_toggled,
            )
            self.list_layout.insertWidget(self.list_layout.count() - 1, row)

    def _mark_favorite_toggled(self, contact_id):
        """Optimistic local flip so the star updates immediately; a Refresh click
        will reconcile with the CLI truth."""
        roster = self._demo_contacts if self._demo_mode else self._contacts
        for c in roster:
            if c["id"] == contact_id:
                c["favorite"] = not c["favorite"]
                break
        if self._demo_mode:
            self._demo_contacts = sort_contacts(roster)
        else:
            self._contacts = sort_contacts(roster)
        self._rebuild_rows()
