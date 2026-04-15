"""Dark theme for Tuple UI — QSS stylesheet + shared color constants."""

# Palette — tuned to match the official Tuple UI (dark slate, saturated red,
# tuple-purple accent, warm orange for state sidecars).
BG          = "#1f2125"
BG_ELEVATED = "#31353d"   # neutral buttons (Mute, Share) — more visible
BG_HOVER    = "#3d4149"
BORDER      = "#45494f"
TEXT        = "#ececec"
TEXT_MUTED  = "#9aa0a6"
TEXT_SUBTLE = "#6b7078"

ACCENT      = "#8b5fbf"   # Tuple purple-ish
ACCENT_HOV  = "#9d73cc"
DANGER      = "#d9362e"   # Hang Up red — brighter, more saturated
DANGER_HOV  = "#e84a41"
SUCCESS     = "#5cb85c"
WARN        = "#e0a03c"   # "mic on" orange from screenshot


QSS = f"""
QWidget {{
    background-color: {BG};
    color: {TEXT};
    font-family: "Segoe UI", "Helvetica Neue", "Cantarell", sans-serif;
    font-size: 10pt;
}}

QMainWindow, QDialog {{
    background-color: {BG};
}}

/* --- State header (big bold label at top of main window) --- */
QLabel#stateHeader {{
    font-size: 14pt;
    font-weight: 600;
    color: {TEXT};
    padding: 6px 2px 10px 2px;
}}

/* --- Footer (signaler status) --- */
QLabel#footer {{
    font-size: 8pt;
    color: {TEXT_SUBTLE};
    padding: 8px 2px 2px 2px;
}}

/* --- Sidecar text (mic on / auto(portal) etc.) --- */
QLabel[role="sidecar"] {{
    color: {WARN};
    font-size: 9pt;
    padding-left: 6px;
}}
QLabel[role="sidecar-ok"] {{
    color: {SUCCESS};
    font-size: 9pt;
    padding-left: 6px;
}}
QLabel[role="sidecar-muted"] {{
    color: {TEXT_MUTED};
    font-size: 9pt;
    padding-left: 6px;
}}
QLabel[role="sidecar-alert"] {{
    color: {DANGER};
    font-size: 9pt;
    font-weight: 700;
    padding-left: 6px;
}}

/* --- Buttons: default --- */
QPushButton {{
    background-color: {BG_ELEVATED};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 6px 12px;
    min-height: 20px;
}}
QPushButton:hover {{
    background-color: {BG_HOVER};
}}
QPushButton:pressed {{
    background-color: {BORDER};
}}
QPushButton:disabled {{
    color: {TEXT_SUBTLE};
    background-color: {BG};
    border: 1px solid {BORDER};
}}

/* --- Buttons: primary (accent-filled) --- */
QPushButton[kind="primary"] {{
    background-color: {ACCENT};
    color: white;
    border: 1px solid {ACCENT};
    font-weight: 600;
}}
QPushButton[kind="primary"]:hover {{
    background-color: {ACCENT_HOV};
    border: 1px solid {ACCENT_HOV};
}}

/* --- Buttons: danger (hang-up / end call) --- */
QPushButton[kind="danger"] {{
    background-color: {DANGER};
    color: white;
    border: 1px solid {DANGER};
    font-weight: 600;
}}
QPushButton[kind="danger"]:hover {{
    background-color: {DANGER_HOV};
    border: 1px solid {DANGER_HOV};
}}

/* --- Buttons: success (start daemon) --- */
QPushButton[kind="success"] {{
    background-color: {SUCCESS};
    color: white;
    border: 1px solid {SUCCESS};
    font-weight: 600;
}}
QPushButton[kind="success"]:hover {{
    background-color: #6dc26d;
    border: 1px solid #6dc26d;
}}

/* --- Buttons: icon (header cog / account) --- */
QPushButton[kind="icon"] {{
    background-color: transparent;
    border: none;
    padding: 2px 6px;
    font-size: 13pt;
    min-width: 24px;
    min-height: 24px;
}}
QPushButton[kind="icon"]:hover {{
    background-color: {BG_ELEVATED};
    border-radius: 4px;
}}
QPushButton[kind="icon"]:checked {{
    background-color: {ACCENT};
    color: white;
    border-radius: 4px;
}}

/* --- Inputs --- */
QLineEdit {{
    background-color: {BG_ELEVATED};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 5px 8px;
    selection-background-color: {ACCENT};
}}
QLineEdit:focus {{
    border: 1px solid {ACCENT};
}}
QLineEdit:read-only {{
    background-color: {BG};
    color: {TEXT_MUTED};
}}

QTextEdit {{
    background-color: {BG_ELEVATED};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 4px;
    selection-background-color: {ACCENT};
}}

QComboBox {{
    background-color: {BG_ELEVATED};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 2px 8px;
    min-height: 20px;
}}
QComboBox:hover {{
    background-color: {BG_HOVER};
}}
QComboBox::drop-down {{
    border: none;
    width: 18px;
}}
QComboBox QAbstractItemView {{
    background-color: {BG_ELEVATED};
    color: {TEXT};
    border: 1px solid {BORDER};
    selection-background-color: {ACCENT};
    selection-color: white;
}}

/* --- GroupBox (Rooms, Contacts, Output) --- */
QGroupBox {{
    border: 1px solid {BORDER};
    border-radius: 4px;
    margin-top: 10px;
    padding-top: 8px;
    font-size: 9pt;
    color: {TEXT_MUTED};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding: 0 4px;
    background-color: {BG};
}}

/* --- Frames used as separators / panels --- */
QFrame[role="panel"] {{
    background-color: {BG_ELEVATED};
    border: 1px solid {BORDER};
    border-radius: 4px;
}}

/* --- Contact rows: subtle box so each name + its Call button group
      visually together, making it obvious which button belongs to whom. --- */
QFrame#contactRow {{
    background-color: {BG_ELEVATED};
    border: 1px solid {BORDER};
    border-radius: 4px;
}}
QFrame#contactRow:hover {{
    background-color: {BG_HOVER};
    border: 1px solid {TEXT_SUBTLE};
}}
QFrame#contactRow QLabel {{
    background-color: transparent;
}}

/* --- Scroll areas --- */
QScrollArea {{
    border: none;
    background-color: transparent;
}}
QScrollBar:vertical {{
    background: {BG};
    width: 10px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {BORDER};
    min-height: 20px;
    border-radius: 5px;
}}
QScrollBar::handle:vertical:hover {{
    background: {TEXT_SUBTLE};
}}
QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {{
    height: 0;
}}

/* --- Menu (tray context menu) --- */
QMenu {{
    background-color: {BG_ELEVATED};
    color: {TEXT};
    border: 1px solid {BORDER};
    padding: 4px 0;
}}
QMenu::item {{
    padding: 5px 18px 5px 18px;
}}
QMenu::item:selected {{
    background-color: {ACCENT};
    color: white;
}}
QMenu::item:disabled {{
    color: {TEXT_SUBTLE};
}}
QMenu::separator {{
    height: 1px;
    background: {BORDER};
    margin: 4px 8px;
}}

/* --- Tooltips --- */
QToolTip {{
    background-color: {BG_ELEVATED};
    color: {TEXT};
    border: 1px solid {BORDER};
    padding: 4px 6px;
}}
"""


def apply_dark_theme(app):
    """Apply the dark theme stylesheet globally to the QApplication."""
    app.setStyle("Fusion")
    app.setStyleSheet(QSS)
