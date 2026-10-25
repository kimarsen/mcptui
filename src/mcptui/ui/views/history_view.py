"""
Execution History view for past tool calls, resource reads, and prompt fetches.
Supports live search filtering and 1-click replaying into editors.
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
from textual.widgets import Button, DataTable, Input, Label, TextArea

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
            yield Input(placeholder="Filter history...", id="history-search", classes="sidebar-search")
            yield DataTable(id="history-table", classes="item-list")

        with Vertical(classes="main-content"):
            with Horizontal(classes="action-bar"):
                yield Button("Re-run in Editor", variant="success", id="btn-replay-history")
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

    def refresh_history(self, filter_text: Optional[str] = None) -> None:
        """Reload records into table matching filter_text."""
        if filter_text is None:
            try:
                filter_text = self.query_one("#history-search", Input).value
            except Exception:
                filter_text = ""

        table = self.query_one("#history-table", DataTable)
        table.clear()

        filter_lower = filter_text.lower().strip()
        filtered = []
        for rec in self.client.history:
            if not filter_lower:
                filtered.append(rec)
            elif filter_lower.startswith("status:"):
                st = filter_lower.split(":", 1)[1].strip()
                if st in ("ok", "success") and not rec.is_error:
                    filtered.append(rec)
                elif st in ("error", "err", "failed", "fail") and rec.is_error:
                    filtered.append(rec)
            elif filter_lower in ("ok", "success"):
                if not rec.is_error:
                    filtered.append(rec)
            else:
                matches_kind = filter_lower in rec.kind.lower()
                matches_name = filter_lower in rec.name.lower()

                # Status matches explicit error token keywords
                tokens = filter_lower.split()
                matches_status = rec.is_error and any(t in ("err", "error", "failed", "fail") for t in tokens)

                matches_args = False
                try:
                    if isinstance(rec.input_data, (dict, list)):
                        matches_args = filter_lower in json.dumps(rec.input_data).lower()
                    elif isinstance(rec.input_data, str):
                        matches_args = filter_lower in rec.input_data.lower()
                except Exception:
                    pass

                matches_output = False
                try:
                    if isinstance(rec.output_data, (dict, list)):
                        matches_output = filter_lower in json.dumps(rec.output_data).lower()
                    elif isinstance(rec.output_data, str):
                        matches_output = filter_lower in rec.output_data.lower()
                except Exception:
                    pass

                matches_err_msg = bool(rec.error_message and filter_lower in rec.error_message.lower())

                if matches_kind or matches_name or matches_status or matches_args or matches_output or matches_err_msg:
                    filtered.append(rec)

        for rec in filtered:
            time_str = rec.timestamp.strftime("%H:%M:%S")
            kind_badge = Text(rec.kind.upper(), style="cyan" if rec.kind == "tool" else "magenta")
            target_str = rec.name[:16]

            if rec.is_error:
                status_badge = Text("ERROR", style="bold red")
            else:
                status_badge = Text("OK", style="bold green")

            duration_str = f"{rec.duration_ms}ms"
            table.add_row(time_str, kind_badge, target_str, status_badge, duration_str, key=rec.id)

        if filtered:
            if self.selected_record_id and any(r.id == self.selected_record_id for r in filtered):
                self.select_record(self.selected_record_id)
            else:
                self.select_record(filtered[0].id)
        else:
            self.selected_record_id = None
            try:
                self.query_one("#history-req-viewer", TextArea).text = ""
                self.query_one("#history-resp-viewer", TextArea).text = ""
                self.query_one("#history-status-pill", Label).update("No matching invocations")
            except Exception:
                pass

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "history-search":
            self.refresh_history(event.value)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.row_key and event.row_key.value:
            self.select_record(str(event.row_key.value))
            self.action_replay_current()

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

    def action_replay_current(self) -> None:
        """Trigger replay of the currently selected history record."""
        if not self.selected_record_id:
            self.app.notify("Select an invocation first to replay", severity="warning")
            return
        rec = next((r for r in self.client.history if r.id == self.selected_record_id), None)
        if rec and hasattr(self.app, "replay_call_record"):
            self.app.replay_call_record(rec)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-replay-history":
            self.action_replay_current()
        elif event.button.id == "btn-copy-req":
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
