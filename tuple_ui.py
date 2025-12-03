#!/usr/bin/env python3
"""
Tuple UI - A graphical interface for the Tuple CLI
"""

import sys
import subprocess
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLineEdit, QTextEdit, QLabel, QGroupBox, QMessageBox,
    QFrame
)
from PyQt6.QtCore import QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QFont


class TupleState:
    """Parses and stores Tuple state from log file"""
    def __init__(self, log_path):
        self.log_path = Path(log_path).expanduser()
        self.is_logged_in = False
        self.daemon_running = False
        self.signaler_state = "unknown"
        self.personal_url = None
        self.in_call = False
        self.last_command = None
        self.is_muted = False
        self.is_sharing = False

    def update(self):
        """Read and parse the log file"""
        if not self.log_path.exists():
            return

        try:
            with open(self.log_path, 'r') as f:
                lines = f.readlines()

            # Reset state before parsing
            self.in_call = False
            daemon_started = False
            daemon_stopped = False

            for line in lines:
                # Check for auth token
                if "saved auth token: yes" in line:
                    self.is_logged_in = True
                elif "saved auth token: no" in line:
                    self.is_logged_in = False

                # Check for daemon start/stop
                if "daemon loop started" in line:
                    daemon_started = True
                    daemon_stopped = False

                # Check signaler state
                if "signaler state changed:" in line:
                    parts = line.split("signaler state changed:")
                    if len(parts) > 1:
                        states = parts[1].strip().split("->")
                        if len(states) > 1:
                            self.signaler_state = states[1].strip()

                # Check for personal URL
                if "personal URL slug" in line and "added" in line:
                    parts = line.split("'")
                    if len(parts) >= 2:
                        self.personal_url = f"https://tuple.app/{parts[1]}"

                # Check for commands
                if "command '" in line:
                    parts = line.split("command '")
                    if len(parts) > 1:
                        cmd = parts[1].split("'")[0]
                        self.last_command = cmd
                        if cmd in ["new", "join"]:
                            self.in_call = True
                            self.is_muted = False  # Reset mute state when joining
                            self.is_sharing = False  # Reset sharing state when joining
                        elif cmd == "end":
                            self.in_call = False
                            self.is_muted = False  # Reset mute state when leaving
                            self.is_sharing = False  # Reset sharing state when leaving
                        elif cmd == "mute":
                            self.is_muted = True
                        elif cmd == "unmute":
                            self.is_muted = False
                        elif cmd == "share":
                            self.is_sharing = True
                        elif cmd == "unshare":
                            self.is_sharing = False
                        elif cmd == "off":
                            # Daemon stopped - reset connection state
                            daemon_stopped = True
                            daemon_started = False
                            self.signaler_state = "disconnected"
                            self.in_call = False

            # Set daemon running state based on most recent events
            if daemon_stopped:
                self.daemon_running = False
            elif daemon_started:
                self.daemon_running = True

        except Exception as e:
            print(f"Error reading log: {e}")


class CommandThread(QThread):
    """Thread for running tuple commands asynchronously"""
    output_ready = pyqtSignal(str, bool)  # output, is_error

    def __init__(self, command):
        super().__init__()
        self.command = command

    def run(self):
        try:
            result = subprocess.run(
                self.command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30
            )
            output = result.stdout + result.stderr
            self.output_ready.emit(output, result.returncode != 0)
        except subprocess.TimeoutExpired:
            self.output_ready.emit("Command timed out after 30 seconds", True)
        except Exception as e:
            self.output_ready.emit(f"Error: {str(e)}", True)


class TupleUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.current_thread = None
        self.state = TupleState("~/.local/share/tuple/0/log.txt")
        self.init_ui()

        # Set up timer to refresh state every 2 seconds
        self.state_timer = QTimer()
        self.state_timer.timeout.connect(self.update_state)
        self.state_timer.start(2000)

        # Initial state update
        self.update_state()

    def init_ui(self):
        self.setWindowTitle("Tuple")
        self.setMinimumSize(100, 400)
        self.resize(200, 500)

        # Create central widget and main layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(5)

        # Create status panel
        status_frame = QFrame()
        status_frame.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Raised)
        status_layout = QHBoxLayout(status_frame)
        status_layout.setContentsMargins(5, 3, 5, 3)
        status_layout.setSpacing(8)

        # Create vertical layout for status items
        status_vertical = QVBoxLayout()
        status_vertical.setSpacing(2)

        # Status labels
        self.login_status_label = QLabel("Login: Unknown")
        self.login_status_label.setFont(QFont("", 8))
        status_vertical.addWidget(self.login_status_label)

        self.daemon_status_label = QLabel("Daemon: Unknown")
        self.daemon_status_label.setFont(QFont("", 8))
        status_vertical.addWidget(self.daemon_status_label)

        self.connection_status_label = QLabel("Connection: Unknown")
        self.connection_status_label.setFont(QFont("", 8))
        status_vertical.addWidget(self.connection_status_label)

        self.call_status_label = QLabel("Call: None")
        self.call_status_label.setFont(QFont("", 8))
        status_vertical.addWidget(self.call_status_label)

        self.mute_status_label = QLabel("Mic: Unknown")
        self.mute_status_label.setFont(QFont("", 8))
        status_vertical.addWidget(self.mute_status_label)

        # Personal URL with copy button
        url_layout = QHBoxLayout()
        url_layout.setSpacing(3)

        self.personal_url_label = QLineEdit()
        self.personal_url_label.setReadOnly(True)
        self.personal_url_label.setFont(QFont("", 7))
        self.personal_url_label.setMaximumHeight(20)
        self.personal_url_label.setFrame(False)
        self.personal_url_label.setStyleSheet("background: transparent;")
        url_layout.addWidget(self.personal_url_label)

        self.copy_url_btn = QPushButton("Copy")
        self.copy_url_btn.setMaximumHeight(18)
        self.copy_url_btn.setMaximumWidth(40)
        self.copy_url_btn.setStyleSheet("font-size: 7pt; padding: 2px;")
        self.copy_url_btn.clicked.connect(self.copy_personal_url)
        url_layout.addWidget(self.copy_url_btn)

        status_vertical.addLayout(url_layout)

        status_layout.addLayout(status_vertical)

        main_layout.addWidget(status_frame)

        # Dynamic action area - shows only relevant buttons
        self.action_widget = QWidget()
        self.action_layout = QVBoxLayout(self.action_widget)
        self.action_layout.setContentsMargins(5, 5, 5, 5)
        self.action_layout.setSpacing(5)

        self.create_all_buttons()

        main_layout.addWidget(self.action_widget)

        # Output area
        output_group = QGroupBox("Output")
        output_layout = QVBoxLayout()
        output_layout.setContentsMargins(5, 5, 5, 5)
        output_layout.setSpacing(3)

        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setMinimumHeight(100)
        self.output_text.setMaximumHeight(120)
        font = QFont("Monospace", 8)
        self.output_text.setFont(font)
        output_layout.addWidget(self.output_text)

        clear_button = QPushButton("Clear")
        clear_button.setMaximumHeight(20)
        clear_button.setStyleSheet("font-size: 8pt;")
        clear_button.clicked.connect(self.output_text.clear)
        output_layout.addWidget(clear_button)

        output_group.setLayout(output_layout)
        main_layout.addWidget(output_group)

    def create_all_buttons(self):
        """Create all action buttons (will be shown/hidden based on state)"""
        # Daemon start button
        self.daemon_start_btn = QPushButton("Start Daemon")
        self.daemon_start_btn.setMinimumHeight(32)
        self.daemon_start_btn.setStyleSheet("background-color: #51cf66; font-size: 10pt; color: white; font-weight: bold;")
        self.daemon_start_btn.clicked.connect(lambda: self.run_command("tuple on"))

        # Daemon stop button
        self.daemon_stop_btn = QPushButton("Stop Daemon")
        self.daemon_stop_btn.setMinimumHeight(28)
        self.daemon_stop_btn.setStyleSheet("background-color: #ff6b6b; font-size: 9pt; color: white;")
        self.daemon_stop_btn.clicked.connect(lambda: self.run_command("tuple off"))

        # Join call input and button
        self.call_url_input = QLineEdit()
        self.call_url_input.setPlaceholderText("Enter call URL...")
        self.call_url_input.setMinimumHeight(24)
        self.call_url_input.setStyleSheet("font-size: 9pt;")

        self.join_btn = QPushButton("Join Call")
        self.join_btn.setMinimumHeight(28)
        self.join_btn.setStyleSheet("font-size: 10pt; background-color: #3498db; color: white;")
        self.join_btn.clicked.connect(self.join_call)

        self.new_btn = QPushButton("New Call")
        self.new_btn.setMinimumHeight(28)
        self.new_btn.setStyleSheet("font-size: 10pt; background-color: #3498db; color: white;")
        self.new_btn.clicked.connect(lambda: self.run_command("tuple new"))

        # In-call controls
        self.end_btn = QPushButton("End Call")
        self.end_btn.setMinimumHeight(32)
        self.end_btn.setStyleSheet("background-color: #ff6b6b; font-size: 10pt; color: white; font-weight: bold;")
        self.end_btn.clicked.connect(lambda: self.run_command("tuple end"))

        # Screen sharing toggle button
        self.share_toggle_btn = QPushButton("Share Screen")
        self.share_toggle_btn.setMinimumHeight(28)
        self.share_toggle_btn.setStyleSheet("font-size: 9pt;")

        # Mute toggle button
        self.mute_toggle_btn = QPushButton("Mute")
        self.mute_toggle_btn.setMinimumHeight(28)
        self.mute_toggle_btn.setStyleSheet("font-size: 9pt;")

    def copy_personal_url(self):
        """Copy personal URL to clipboard"""
        url = self.personal_url_label.text()
        if url:
            clipboard = QApplication.clipboard()
            clipboard.setText(url)
            self.log_output("URL copied to clipboard!\n", False)

    def join_call(self):
        """Join a call with the provided URL"""
        call_url = self.call_url_input.text().strip()
        if not call_url:
            QMessageBox.warning(self, "Input Required", "Please enter a call URL.")
            return
        self.run_command(f"tuple join {call_url}")

    def run_command(self, command):
        """Run a tuple command in a separate thread"""
        if self.current_thread and self.current_thread.isRunning():
            QMessageBox.warning(
                self,
                "Command Running",
                "A command is already running. Please wait for it to complete."
            )
            return

        self.log_output(f"$ {command}\n", False)

        self.current_thread = CommandThread(command)
        self.current_thread.output_ready.connect(self.handle_output)
        self.current_thread.start()

    def handle_output(self, output, is_error):
        """Handle command output"""
        self.log_output(output, is_error)
        # Update state immediately after command completes
        QTimer.singleShot(500, self.update_state)

    def log_output(self, text, is_error=False):
        """Log output to the text area"""
        if is_error:
            self.output_text.append(f'<span style="color: red;">{text}</span>')
        else:
            self.output_text.append(text)
        self.output_text.ensureCursorVisible()

    def update_state(self):
        """Update state from log file and refresh UI"""
        self.state.update()

        # Update login status
        if self.state.is_logged_in:
            self.login_status_label.setText("✓ Logged In")
            self.login_status_label.setStyleSheet("color: green;")
        else:
            self.login_status_label.setText("✗ Not Logged In")
            self.login_status_label.setStyleSheet("color: red;")

        # Update daemon status
        if self.state.daemon_running:
            self.daemon_status_label.setText("✓ Daemon Running")
            self.daemon_status_label.setStyleSheet("color: green;")
        else:
            self.daemon_status_label.setText("✗ Daemon Off")
            self.daemon_status_label.setStyleSheet("color: gray;")

        # Update connection status
        if self.state.signaler_state == "connected":
            self.connection_status_label.setText("✓ Connected")
            self.connection_status_label.setStyleSheet("color: green;")
        elif self.state.signaler_state in ["connecting", "synchronizing"]:
            self.connection_status_label.setText(f"{self.state.signaler_state.title()}")
            self.connection_status_label.setStyleSheet("color: orange;")
        else:
            self.connection_status_label.setText(f"{self.state.signaler_state.title()}")
            self.connection_status_label.setStyleSheet("color: gray;")

        # Update call status
        if self.state.in_call:
            self.call_status_label.setText("✓ In Call")
            self.call_status_label.setStyleSheet("color: green;")
        else:
            self.call_status_label.setText("No Call")
            self.call_status_label.setStyleSheet("color: gray;")

        # Update mute status (only when in call)
        if self.state.in_call:
            if self.state.is_muted:
                self.mute_status_label.setText("🔇 Muted")
                self.mute_status_label.setStyleSheet("color: red;")
            else:
                self.mute_status_label.setText("🎤 Unmuted")
                self.mute_status_label.setStyleSheet("color: green;")
        else:
            self.mute_status_label.setText("Mic: N/A")
            self.mute_status_label.setStyleSheet("color: gray;")

        # Update personal URL and copy button
        if self.state.personal_url:
            self.personal_url_label.setText(self.state.personal_url)
            self.personal_url_label.setPlaceholderText("Personal URL")
            self.copy_url_btn.setVisible(True)
        else:
            self.personal_url_label.setText("")
            self.personal_url_label.setPlaceholderText("No URL")
            self.copy_url_btn.setVisible(False)

        # Rebuild action area based on state
        self.rebuild_actions()

    def rebuild_actions(self):
        """Rebuild the action area to show only relevant buttons"""
        # Clear current layout
        while self.action_layout.count():
            item = self.action_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
            elif item.layout():
                # Remove sublayout items
                while item.layout().count():
                    subitem = item.layout().takeAt(0)
                    if subitem.widget():
                        subitem.widget().setParent(None)

        daemon_running = self.state.daemon_running
        in_call = self.state.in_call

        # State 1: Daemon not running - only show start button
        if not daemon_running:
            self.action_layout.addWidget(self.daemon_start_btn)
            self.action_layout.addStretch()
            return

        # State 2: Daemon running but not in call - show call options
        if daemon_running and not in_call:
            self.action_layout.addWidget(self.call_url_input)
            self.action_layout.addWidget(self.join_btn)
            self.action_layout.addWidget(self.new_btn)
            self.action_layout.addWidget(self.daemon_stop_btn)
            self.action_layout.addStretch()
            return

        # State 3: In a call - show call controls
        if in_call:
            self.action_layout.addWidget(self.end_btn)

            # Update share button text and action based on state
            if self.state.is_sharing:
                self.share_toggle_btn.setText("Unshare Screen")
                try:
                    self.share_toggle_btn.clicked.disconnect()
                except:
                    pass
                self.share_toggle_btn.clicked.connect(lambda: self.run_command("tuple unshare"))
            else:
                self.share_toggle_btn.setText("Share Screen")
                try:
                    self.share_toggle_btn.clicked.disconnect()
                except:
                    pass
                self.share_toggle_btn.clicked.connect(lambda: self.run_command("tuple share"))
            self.action_layout.addWidget(self.share_toggle_btn)

            # Update mute button text and action based on state
            if self.state.is_muted:
                self.mute_toggle_btn.setText("Unmute")
                try:
                    self.mute_toggle_btn.clicked.disconnect()
                except:
                    pass
                self.mute_toggle_btn.clicked.connect(lambda: self.run_command("tuple unmute"))
            else:
                self.mute_toggle_btn.setText("Mute")
                try:
                    self.mute_toggle_btn.clicked.disconnect()
                except:
                    pass
                self.mute_toggle_btn.clicked.connect(lambda: self.run_command("tuple mute"))
            self.action_layout.addWidget(self.mute_toggle_btn)

            self.action_layout.addWidget(self.daemon_stop_btn)
            self.action_layout.addStretch()
            return


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Tuple UI")

    window = TupleUI()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
