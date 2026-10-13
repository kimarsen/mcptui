"""
Execution History view for past tool calls, resource reads, and prompt fetches.
"""

from __future__ import annotations

import json
from typing import Optional

import pyperclip
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Button, DataTable, Label, TextArea

from mcptui.client import MCPClientManager
from mcptui.models import CallRecord


class HistoryView(Widget):
    """View displaying recorded call history and details."""

    DEFAULT_CLASSES = "split-view"

    selected_record_id: reactive[Optional[str]] = reactive(None)

    def __init__(self, client: MCPClientManager, **kwargs):
        super().__init__(**kwargs)
        self.client = client

    def compose(self) -> ComposeResult:
        with Container(classes="sidebar"):
            yield Label("Recent Invocations", classes="input-section-title")
            yield DataTable(id="history-table", classes="item-list")

        with Vertical(classes="main-content"):
            with Horizontal(classes="action-bar"):
                yield Button("Copy Request", id="btn-copy-req")
                yield Button("Copy Response", id="btn-copy-resp")
                yield Button("Clear History", id="btn-clear-history")
                yield Label("Select an invocation to inspect details", id="history-status-pill")

            yield Label("Request Input", classes="input-section-title")
            yield TextArea(
                text="",
                language="json",
                read_only=True,
                id="history-req-viewer",
                classes="param-editor",
            )

            yield Label("Response Output", classes="input-section-title")
            yield TextArea(
                text="",
                language="json",
                read_only=True,
                id="history-resp-viewer",
                classes="response-box",
            )

    def on_mount(self) -> None:
        table = self.query_one("#history-table", DataTable)
        table.cursor_type = "row"
        table.add_columns("Time", "Kind", "Target", "Status", "Duration")
        self.refresh_history()

    def refresh_history(self) -> None:
        """Reload records into table."""
        table = self.query_one("#history-table", DataTable)
        table.clear()

        for rec in self.client.history:
            time_str = rec.timestamp.strftime("%H:%M:%S")
            kind_badge = Text(rec.kind.upper(), style="cyan" if rec.kind == "tool" else "magenta")
            target_str = rec.name[:16]

            if rec.is_error:
                status_badge = Text("ERROR", style="bold red")
            else:
                status_badge = Text("OK", style="bold green")

            duration_str = f"{rec.duration_ms}ms"
            table.add_row(time_str, kind_badge, target_str, status_badge, duration_str, key=rec.id)

        if self.client.history:
            self.select_record(self.client.history[0].id)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.row_key and event.row_key.value:
            self.select_record(str(event.row_key.value))

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.row_key and event.row_key.value:
            self.select_record(str(event.row_key.value))

    def select_record(self, record_id: str) -> None:
        """Display inputs and outputs for selected history record."""
        self.selected_record_id = record_id
        rec: Optional[CallRecord] = next((r for r in self.client.history if r.id == record_id), None)
        if not rec:
            return

        req_viewer = self.query_one("#history-req-viewer", TextArea)
        resp_viewer = self.query_one("#history-resp-viewer", TextArea)
        status_pill = self.query_one("#history-status-pill", Label)

        req_viewer.text = json.dumps(rec.input_data, indent=2)

        if rec.is_error:
            status_pill.update(f"ID: {rec.id} | ERROR ({rec.duration_ms}ms)")
            resp_viewer.text = rec.error_message or json.dumps(rec.output_data, indent=2)
        else:
            status_pill.update(f"ID: {rec.id} | SUCCESS ({rec.duration_ms}ms)")
            resp_viewer.text = json.dumps(rec.output_data, indent=2)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-copy-req":
            viewer = self.query_one("#history-req-viewer", TextArea)
            if viewer.text:
                pyperclip.copy(viewer.text)
                self.app.notify("Request copied to clipboard!", severity="information")
        elif event.button.id == "btn-copy-resp":
            viewer = self.query_one("#history-resp-viewer", TextArea)
            if viewer.text:
                pyperclip.copy(viewer.text)
                self.app.notify("Response copied to clipboard!", severity="information")
        elif event.button.id == "btn-clear-history":
            self.client.history.clear()
            self.refresh_history()
            self.query_one("#history-req-viewer", TextArea).text = ""
            self.query_one("#history-resp-viewer", TextArea).text = ""
