"""
Real-time JSON-RPC 2.0 protocol logs inspector.
"""

from __future__ import annotations

import json
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.widget import Widget
from textual.widgets import Button, Input, Label, RichLog
from rich.text import Text

from mcptui.client import MCPClientManager
from mcptui.models import ProtocolMessage


class ProtocolLogsView(Widget):
    """Live protocol logs inspector for debugging JSON-RPC messages."""

    DEFAULT_CLASSES = "log-view"

    def __init__(self, client: MCPClientManager, **kwargs):
        super().__init__(**kwargs)
        self.client = client
        self._filter_text: str = ""

    def compose(self) -> ComposeResult:
        with Horizontal(classes="action-bar"):
            yield Input(placeholder="🔍 Filter protocol logs (e.g. tools/call, initialize)...", id="log-search", classes="sidebar-search")
            yield Button("🧹 Clear Logs", id="btn-clear-logs")
            yield Button("📋 Copy All Logs", id="btn-copy-all-logs")
            yield Label(f"Total: {len(self.client.protocol_logs)} messages", id="log-count-pill")

        yield RichLog(highlight=True, markup=True, id="protocol-log", wrap=True)

    def on_mount(self) -> None:
        # Register live log callback
        self.client.set_log_callback(self.on_new_protocol_message)
        # Populate initial logs
        rich_log = self.query_one("#protocol-log", RichLog)
        rich_log.clear()
        for msg in self.client.protocol_logs:
            self._write_log_entry(msg)

    def on_new_protocol_message(self, msg: ProtocolMessage) -> None:
        """Handle incoming intercepted protocol message on the UI thread."""
        try:
            self.app.call_from_thread(self._write_log_entry, msg)
        except Exception:
            self._write_log_entry(msg)

    def _write_log_entry(self, msg: ProtocolMessage) -> None:
        """Format and write a single log entry to the RichLog."""
        time_str = msg.timestamp.strftime("%H:%M:%S.%f")[:-3]
        text_line = Text()

        # Timestamp
        text_line.append(f"[{time_str}] ", style="dim white")

        # Direction badge
        if msg.direction == "sent":
            text_line.append("--> SENT    ", style="bold cyan")
        else:
            text_line.append("<-- RECV    ", style="bold green")

        method = msg.method or msg.data.get("method")
        msg_id = msg.data.get("id")
        id_str = f" [id={msg_id}]" if msg_id is not None else ""

        if method:
            text_line.append(f"{method}{id_str}", style="bold yellow")
        elif "result" in msg.data:
            text_line.append(f"Result{id_str}", style="bold green")
        elif "error" in msg.data:
            text_line.append(f"Error{id_str}", style="bold red")
        else:
            text_line.append(f"Message{id_str}", style="white")

        # Check filter
        full_dump = json.dumps(msg.data, ensure_ascii=False)
        if self._filter_text and self._filter_text.lower() not in full_dump.lower():
            return

        try:
            rich_log = self.query_one("#protocol-log", RichLog)
            rich_log.write(text_line)
            # Indented JSON data
            formatted_json = json.dumps(msg.data, indent=2)
            rich_log.write(Text(formatted_json, style="dim"))
            rich_log.write(Text("─" * 60, style="dim #30363d"))

            # Update count
            count_label = self.query_one("#log-count-pill", Label)
            count_label.update(f"Total: {len(self.client.protocol_logs)} messages")
        except Exception:
            pass

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "log-search":
            self._filter_text = event.value
            rich_log = self.query_one("#protocol-log", RichLog)
            rich_log.clear()
            for msg in self.client.protocol_logs:
                self._write_log_entry(msg)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-clear-logs":
            self.client.protocol_logs.clear()
            rich_log = self.query_one("#protocol-log", RichLog)
            rich_log.clear()
            count_label = self.query_one("#log-count-pill", Label)
            count_label.update("Total: 0 messages")
        elif event.button.id == "btn-copy-all-logs":
            try:
                import pyperclip
                all_logs = [m.data for m in self.client.protocol_logs]
                pyperclip.copy(json.dumps(all_logs, indent=2))
                self.app.notify("All protocol logs copied!", severity="information")
            except Exception as exc:
                self.app.notify(f"Copy failed: {exc}", severity="warning")
