# Tuple UI

A graphical user interface for the Tuple CLI using Python and PyQt6 (KDE Qt bindings).

## Features

The UI provides a tabbed interface for all Tuple CLI commands:

- **Authentication**: Login, complete authentication, and logout
- **Calls**: Join calls, start new calls, and end calls
- **Controls**: Share/unshare screen and mute/unmute microphone
- **Daemon**: Start/stop the daemon for accepting incoming calls
- **Settings**: View and update Tuple settings

All commands run asynchronously with output displayed in a dedicated console area.

## Requirements

- Python 3.7+
- PyQt6
- Tuple CLI installed and available in PATH

## Installation

1. Install Python dependencies:

```bash
pip install -r requirements.txt
```

## Usage

Run the application:

```bash
python tuple_ui.py
```

Or make it executable and run directly:

```bash
chmod +x tuple_ui.py
./tuple_ui.py
```

## UI Overview

The application is organized into tabs:

1. **Authentication Tab**: Manage your Tuple login
   - Start Login Process: Initiates browser-based authentication
   - Complete Login: Enter the auth code from browser
   - Logout: Sign out of Tuple

2. **Calls Tab**: Manage your calls
   - Join Call: Enter a call URL to join
   - Start New Call: Create and join a new call with your personal URL
   - End/Leave Call: Exit the current call

3. **Controls Tab**: In-call controls
   - Screen Sharing: Share or unshare your screen
   - Microphone: Mute or unmute your mic

4. **Daemon Tab**: Daemon management
   - Start Daemon: Enable incoming calls
   - Stop Daemon: Disable incoming calls
   - Show Debug UI: Launch Tuple's debug interface

5. **Settings Tab**: View and modify settings
   - List All Settings: Display current configuration
   - Update Setting: Change a specific setting value

## Output Window

The bottom panel shows command output in real-time, with errors highlighted in red. Use the "Clear Output" button to clear the console.

## Notes

- Commands run asynchronously to prevent UI freezing
- Only one command can run at a time
- The status bar shows the current operation
- All Tuple CLI features are accessible through the UI
# tuple-ui
# tuple-ui
