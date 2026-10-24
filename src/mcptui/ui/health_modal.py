"""
Modal dialog displaying real-time MCP server compliance and health check results.
"""

from __future__ import annotations

import json
from typing import Optional

import pyperclip
from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Label

from mcptui.models import ServerConfig
from mcptui.tester import SuiteReport, run_server_tests


class HealthCheckModal(ModalScreen[None]):
    """Modal displaying compliance and test runner results for the current MCP server."""

    BINDINGS = [
        ("escape", "dismiss_modal", "Close"),
        ("q", "dismiss_modal", "Close"),
    ]

    def __init__(self, config: ServerConfig, **kwargs):
        super().__init__(**kwargs)
        self.config = config
        self.report: Optional[SuiteReport] = None

    def compose(self) -> ComposeResult:
        with Container(id="health-modal-container"):
            yield Label("🧪 MCP Server Compliance & Health Check", id="health-title")
            yield Label("[RUNNING CHECKS... PLEASE WAIT]", id="health-summary-pill")
            yield DataTable(id="health-results-list")
            with Horizontal(classes="modal-buttons"):
                yield Button("Copy JSON", id="btn-health-copy-json", disabled=True)
                yield Button("Copy Summary", id="btn-health-copy-text", disabled=True)
                yield Button("Close (Esc)", variant="default", id="btn-health-close")

    def on_mount(self) -> None:
        table = self.query_one("#health-results-list", DataTable)
        table.cursor_type = "row"
        table.add_columns("Status", "Category", "Check Name", "Diagnostic")
        self.execute_checks()

    def action_dismiss_modal(self) -> None:
        self.dismiss(None)

    @work(exclusive=True)
    async def execute_checks(self) -> None:
        """Run health checks asynchronously and populate the view."""
        table = self.query_one("#health-results-list", DataTable)
        pill = self.query_one("#health-summary-pill", Label)

        try:
            report = await run_server_tests(self.config, pings=3, timeout_sec=12.0)
            self.report = report

            table.clear()
            for c in report.checks:
                if c.status == "pass":
                    status_badge = Text("✓ PASS", style="bold green")
                elif c.status == "fail":
                    status_badge = Text("✗ FAIL", style="bold red")
                elif c.status == "warn":
                    status_badge = Text("⚠ WARN", style="bold yellow")
                else:
                    status_badge = Text("ℹ INFO", style="bold blue")

                table.add_row(
                    status_badge,
                    c.category.upper(),
                    c.name,
                    c.message,
                )

            pill.remove_class("success", "failure")
            if report.is_success and report.failed == 0:
                pill.add_class("success")
                pill.update(
                    f"✓ PASSED: {report.passed}/{report.total_checks} checks  |  "
                    f"Handshake: {report.handshake_ms}ms  |  Avg Ping: {report.avg_ping_ms}ms"
                )
            else:
                pill.add_class("failure")
                pill.update(
                    f"✗ FAILED: {report.failed} error(s), {report.passed}/{report.total_checks} passed  |  "
                    f"Handshake: {report.handshake_ms}ms"
                )

            self.query_one("#btn-health-copy-json", Button).disabled = False
            self.query_one("#btn-health-copy-text", Button).disabled = False

        except Exception as exc:
            pill.add_class("failure")
            pill.update(f"✗ Execution error: {exc}")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-health-close":
            self.dismiss(None)
        elif event.button.id == "btn-health-copy-json":
            if self.report:
                try:
                    pyperclip.copy(json.dumps(self.report.to_dict(), indent=2))
                    self.app.notify("Test report JSON copied to clipboard!", severity="information")
                except Exception as exc:
                    self.app.notify(f"Copy failed: {exc}", severity="warning")
        elif event.button.id == "btn-health-copy-text":
            if self.report:
                try:
                    summary_lines = [
                        f"mcptui test report: {self.report.server_name}",
                        f"Target: {self.report.target}",
                        f"Result: {self.report.passed}/{self.report.total_checks} passed, {self.report.failed} failed, {self.report.warnings} warnings",
                        f"Handshake: {self.report.handshake_ms}ms, Avg Ping: {self.report.avg_ping_ms}ms",
                        f"Verdict: {self.report.summary_message}",
                    ]
                    pyperclip.copy("\n".join(summary_lines))
                    self.app.notify("Summary copied to clipboard!", severity="information")
                except Exception as exc:
                    self.app.notify(f"Copy failed: {exc}", severity="warning")
