# Tuple UI

This is made using Claude with very little manual editing.

A lightweight system tray application for controlling [Tuple](https://tuple.app) (pair programming tool) with visual status indicators.

## Features

**Visual status indicators** - The tray icon changes color to show your status:
- Gray: Daemon off
- Blue: Daemon on, no call
- Green: In call, unmuted
- Red with "M": In call, muted
- Orange dot: Screen sharing

**Quick controls:**
- Left-click to toggle mute (when in call)
- Right-click for menu (start/stop daemon, join/new/end call, mute, share screen)
- Double-click to show/hide window

## Installation

**Debian/Ubuntu:**
```bash
sudo apt install python3-pyqt6
python3 tuple_ui.py
```

**Other systems:**
```bash
pip3 install PyQt6
python3 tuple_ui.py
```

Requires Tuple CLI installed and in PATH.
