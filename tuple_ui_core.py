"""Core helpers for Tuple UI: log-file state parsing and subprocess thread."""

import re
import subprocess
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal


# Personal URL may show up in command output (e.g. `tuple new` prints it).
TUPLE_URL_RE = re.compile(r"https?://tuple\.app/[A-Za-z0-9._\-/]+")


class TupleState:
    """Parses and stores Tuple state from the CLI log file."""

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
        # User-intent overrides: set by the UI via set_mute/set_share after a
        # successful `tuple mute`/`tuple unmute`/`tuple share`/`tuple unshare`
        # command. These survive log re-parsing because recent Tuple CLI
        # versions don't always log `cli: mute`/`cli: unmute` entries, so the
        # log walk alone can't tell us the current mute state.
        self._mute_override = None    # None | True | False
        self._share_override = None   # None | True | False

    def set_mute(self, value):
        """Record user-intent mute state that overrides log-derived state."""
        self._mute_override = bool(value)
        self.is_muted = bool(value)

    def set_share(self, value):
        self._share_override = bool(value)
        self.is_sharing = bool(value)

    def update(self):
        """Read and parse the log file."""
        if not self.log_path.exists():
            return

        try:
            with open(self.log_path, "r") as f:
                lines = f.readlines()
        except Exception as e:
            print(f"Error reading log: {e}")
            return

        self.in_call = False
        daemon_started = False
        daemon_stopped = False
        daemon_quitting = False

        for line in lines:
            if "saved auth token: yes" in line:
                self.is_logged_in = True
            elif "saved auth token: no" in line:
                self.is_logged_in = False

            if "daemon loop started" in line:
                daemon_started = True
                daemon_stopped = False
                daemon_quitting = False
            elif "received 'off' message, quitting" in line or "tuple is no longer running" in line:
                daemon_quitting = True
                daemon_started = False

            if "signaler state changed:" in line:
                parts = line.split("signaler state changed:")
                if len(parts) > 1:
                    states = parts[1].strip().split("->")
                    if len(states) > 1:
                        self.signaler_state = states[1].strip()

            if "personal URL slug" in line and "added" in line:
                parts = line.split("'")
                if len(parts) >= 2:
                    self.personal_url = f"https://tuple.app/{parts[1]}"
            else:
                # Fallback: some Tuple versions print the personal URL in
                # plain log lines (e.g. after `tuple new`). Capture the first
                # slug-style tuple.app URL we see and keep it.
                if self.personal_url is None:
                    m = TUPLE_URL_RE.search(line)
                    if m and "/c/" not in m.group(0):
                        self.personal_url = m.group(0)

            # Call lifecycle: prefer the daemon's own signals over the CLI
            # invocation — the daemon logs "call connected" / "invalidating
            # call" / "sfu closed" regardless of whether the call started or
            # ended via our CLI or via the native UI. Tracking only `cli: new`
            # / `cli: end` misses non-CLI hang-ups (e.g. peer hangs up, native
            # UI end-call button) and leaves `in_call` stuck True.
            if "call connected" in line:
                self.in_call = True
                self.is_muted = False
                self.is_sharing = False
            elif "invalidating call" in line or "sfu closed" in line:
                self.in_call = False
                self.is_muted = False
                self.is_sharing = False

            cmd = self._extract_cli_command(line)
            if cmd:
                self.last_command = cmd
                if cmd == "mute":
                    self.is_muted = True
                elif cmd == "unmute":
                    self.is_muted = False
                elif cmd == "share":
                    self.is_sharing = True
                elif cmd == "unshare":
                    self.is_sharing = False
                elif cmd == "off":
                    daemon_stopped = True
                    daemon_started = False
                    self.signaler_state = "disconnected"
                    self.in_call = False

        if daemon_stopped or daemon_quitting:
            self.daemon_running = False
        elif daemon_started:
            self.daemon_running = True

        # Apply user-intent overrides on top of log-derived state so UI-driven
        # mute/share changes stick even when the CLI doesn't log them. Clear
        # overrides when we leave the call — next call starts clean.
        if self._mute_override is not None:
            self.is_muted = self._mute_override
        if self._share_override is not None:
            self.is_sharing = self._share_override
        if not self.in_call:
            self._mute_override = None
            self._share_override = None

    @staticmethod
    def _extract_cli_command(line):
        """Return the command name in a log line, for old or new log formats.

        Old: `... command 'mute'` → "mute"
        New: `... Engine.cpp:578|cli: mute` → "mute"
        """
        if "command '" in line:
            return line.split("command '", 1)[1].split("'", 1)[0] or None
        if "cli: " in line:
            rest = line.split("cli: ", 1)[1].strip()
            if rest:
                return rest.split()[0]
        return None

    def ingest_command_output(self, text):
        """Scan subprocess output (stdout+stderr) for a personal URL and cache it.

        Called by the UI when a `tuple` command completes. Useful because
        recent Tuple versions don't log the personal URL slug — but they do
        print the URL on stdout when starting a call via `tuple new`.
        """
        if self.personal_url is not None or not text:
            return
        for m in TUPLE_URL_RE.finditer(text):
            url = m.group(0)
            # Skip call URLs (paths like /c/<id>) so we only cache the
            # personal URL, not a call the user just joined.
            if "/c/" in url:
                continue
            self.personal_url = url
            return


class CommandThread(QThread):
    """Run a tuple CLI command in a worker thread, with cooperative cancel.

    Uses Popen directly so we can terminate/kill the child when the app is
    quitting — avoids the hang seen when `subprocess.run` blocks in
    communicate() during shutdown.
    """

    output_ready = pyqtSignal(str, bool)  # output, is_error

    TIMEOUT_SECONDS = 30

    def __init__(self, command):
        super().__init__()
        self.command = command
        self.process = None
        self._cancelled = False

    def run(self):
        try:
            self.process = subprocess.Popen(
                self.command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        except Exception as e:
            self.output_ready.emit(f"Error spawning command: {e}", True)
            return

        try:
            stdout, stderr = self.process.communicate(timeout=self.TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            self._kill_quietly()
            try:
                stdout, stderr = self.process.communicate(timeout=2)
            except Exception:
                stdout, stderr = "", ""
            if not self._cancelled:
                self.output_ready.emit(
                    (stdout or "") + (stderr or "")
                    + f"\nCommand timed out after {self.TIMEOUT_SECONDS}s — process killed.",
                    True,
                )
            return
        except Exception as e:
            if not self._cancelled:
                self.output_ready.emit(f"Error: {e}", True)
            return

        if self._cancelled:
            return
        self.output_ready.emit(
            (stdout or "") + (stderr or ""),
            self.process.returncode != 0,
        )

    def cancel(self):
        """Request cooperative cancellation and kill the child process."""
        self._cancelled = True
        self._kill_quietly()

    def _kill_quietly(self):
        proc = self.process
        if not proc or proc.poll() is not None:
            return
        try:
            proc.terminate()
        except Exception:
            pass
        try:
            proc.wait(timeout=0.5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
