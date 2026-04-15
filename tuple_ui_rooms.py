"""Rooms: persisted shortcut buttons for `tuple join <URL>` calls.

Only the config model lives here now — the add/remove UI moved into the
Settings dialog (see `tuple_ui_settings.SettingsDialog`).
"""

import json
from pathlib import Path


class FastButtonConfig:
    """Manages room shortcut configuration (name -> URL)."""

    def __init__(self):
        self.config_path = Path.home() / ".tuple_ui_buttons.json"
        self.buttons = self.load()

    def load(self):
        if self.config_path.exists():
            try:
                with open(self.config_path, "r") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def save(self):
        try:
            with open(self.config_path, "w") as f:
                json.dump(self.buttons, f, indent=2)
        except Exception as e:
            print(f"Error saving config: {e}")

    def add_button(self, name, url):
        self.buttons[name] = url
        self.save()

    def remove_button(self, name):
        if name in self.buttons:
            del self.buttons[name]
            self.save()

    def get_buttons(self):
        return [(name, url) for name, url in self.buttons.items()]
