"""App-level UI preferences — separate from `tuple settings` (CLI config).

Persisted as JSON at ~/.tuple_ui_prefs.json so the user can toggle UI-only
behaviors (e.g. "show window on start") without touching Tuple CLI config.
"""

import json
from pathlib import Path


PREFS_PATH = Path.home() / ".tuple_ui_prefs.json"

DEFAULTS = {
    "show_on_start": True,
}


class UIPrefs:
    def __init__(self, path=PREFS_PATH):
        self.path = Path(path)
        self._data = dict(DEFAULTS)
        self.load()

    def load(self):
        if not self.path.exists():
            return
        try:
            loaded = json.loads(self.path.read_text())
            if isinstance(loaded, dict):
                self._data.update(loaded)
        except Exception as e:
            print(f"Could not read UI prefs ({self.path}): {e}")

    def save(self):
        try:
            self.path.write_text(json.dumps(self._data, indent=2))
        except Exception as e:
            print(f"Could not save UI prefs ({self.path}): {e}")

    def get(self, key):
        return self._data.get(key, DEFAULTS.get(key))

    def set(self, key, value):
        self._data[key] = value

    @property
    def show_on_start(self):
        return bool(self.get("show_on_start"))
