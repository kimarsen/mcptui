"""
Main Textual Application for mcptui.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widgets import Button, Footer, Label, TabbedContent, TabPane

from mcptui.client import MCPClientManager
from mcptui.models import ServerConfig
from mcptui.ui.server_modal import ServerSwitcherModal
from mcptui.ui.views.history_view import HistoryView
from mcptui.ui.views.logs_view import ProtocolLogsView
from mcptui.ui.views.prompts_view import PromptsView
from mcptui.ui.views.resources_view import ResourcesView
from mcptui.ui.views.tools_view import ToolsView

CSS_PATH = Path(__file__).parent / "styles.tcss"


class MCPTuiApp(App):
    """mcptui: The Postman for Model Context Protocol."""

    TITLE = "mcptui"
    SUB_TITLE = "Postman for MCP"
    CSS_PATH = CSS_PATH

    BINDINGS = [
        Binding("1", "goto_tab_1", "Tools", show=False),
        Binding("2", "goto_tab_2", "Resources", show=False),
        Binding("3", "goto_tab_3", "Prompts", show=False),
        Binding("4", "goto_tab_4", "Logs", show=False),
        Binding("5", "goto_tab_5", "History", show=False),
        Binding("f2", "switch_server", "Switch Server", show=True),
        Binding("f5", "refresh_all", "Refresh", show=True),
        Binding("ctrl+r", "refresh_all", "Refresh", show=False),
        Binding("ctrl+q", "quit", "Quit", show=True),
        Binding("q", "quit", "Quit", show=False),
    ]

    def __init__(self, initial_config: Optional[ServerConfig] = None, **kwargs):
        super().__init__(**kwargs)
        self.initial_config = initial_config
        self.client = MCPClientManager()

    def compose(self) -> ComposeResult:
        with Horizontal(id="top-header"):
            yield Label("mcptui | Postman for MCP", id="brand-label")
            yield Label("[CONNECTING...]", id="server-pill")
            with Horizontal(id="header-buttons"):
                yield Button("Switch Server (F2)", id="btn-hdr-switch")
                yield Button("Reload (F5)", id="btn-hdr-refresh")

        with TabbedContent(id="tabs"):
            with TabPane("[1] Tools", id="tab-tools"):
                yield ToolsView(self.client, id="tools-view")
            with TabPane("[2] Resources", id="tab-resources"):
                yield ResourcesView(self.client, id="resources-view")
            with TabPane("[3] Prompts", id="tab-prompts"):
                yield PromptsView(self.client, id="prompts-view")
            with TabPane("[4] Protocol Logs", id="tab-logs"):
                yield ProtocolLogsView(self.client, id="logs-view")
            with TabPane("[5] History", id="tab-history"):
                yield HistoryView(self.client, id="history-view")

        yield Footer()

    def on_mount(self) -> None:
        target_config = self.initial_config or ServerConfig(
            name="mcptui-demo",
            transport="stdio",
            command=sys.executable,
            args=["-m", "mcptui.demo_server"],
            source="built-in demo",
        )
        self.connect_to_server(target_config)

    async def on_unmount(self) -> None:
        """Ensure client disconnects when app exits."""
        await self.client.disconnect()

    @work(exclusive=True)
    async def connect_to_server(self, config: ServerConfig) -> None:
        """Connect to an MCP server in the background and update UI."""
        pill = self.query_one("#server-pill", Label)
        pill.update(f"[CONNECTING: {config.name}]")
        pill.remove_class("disconnected")

        try:
            await self.client.connect(config)
            pill.update(f"[* {self.client.server_name}]")
            pill.remove_class("disconnected")
            self.notify(f"Connected to {self.client.server_name}!", severity="information")
            self.update_child_views()
        except Exception as exc:
            pill.update(f"[ERR: {config.name}]")
            pill.add_class("disconnected")
            self.notify(f"Connection failed: {exc}", severity="error")

    def update_child_views(self) -> None:
        """Tell child views to refresh their lists."""
        try:
            self.query_one("#tools-view", ToolsView).refresh_tools()
        except Exception:
            pass
        try:
            self.query_one("#resources-view", ResourcesView).refresh_resources()
        except Exception:
            pass
        try:
            self.query_one("#prompts-view", PromptsView).refresh_prompts()
        except Exception:
            pass

    def action_goto_tab_1(self) -> None:
        self.query_one("#tabs", TabbedContent).active = "tab-tools"

    def action_goto_tab_2(self) -> None:
        self.query_one("#tabs", TabbedContent).active = "tab-resources"

    def action_goto_tab_3(self) -> None:
        self.query_one("#tabs", TabbedContent).active = "tab-prompts"

    def action_goto_tab_4(self) -> None:
        self.query_one("#tabs", TabbedContent).active = "tab-logs"

    def action_goto_tab_5(self) -> None:
        self.query_one("#tabs", TabbedContent).active = "tab-history"

    def action_switch_server(self) -> None:
        """Open Server Switcher modal."""
        def on_modal_result(selected_cfg: Optional[ServerConfig]) -> None:
            if selected_cfg:
                self.connect_to_server(selected_cfg)

        self.push_screen(ServerSwitcherModal(), on_modal_result)

    @work(exclusive=True)
    async def action_refresh_all(self) -> None:
        """Refresh server capabilities."""
        if not self.client.is_connected:
            self.notify("Not connected to any server", severity="warning")
            return
        try:
            await self.client.refresh_capabilities()
            self.update_child_views()
            self.notify("Capabilities refreshed!", severity="information")
        except Exception as exc:
            self.notify(f"Refresh failed: {exc}", severity="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-hdr-switch":
            self.action_switch_server()
        elif event.button.id == "btn-hdr-refresh":
            self.action_refresh_all()

    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        """Update active view when tab changes."""
        if event.tab.id == "tab-history":
            try:
                self.query_one("#history-view", HistoryView).refresh_history()
            except Exception:
                pass


def run_tui(config: Optional[ServerConfig] = None) -> None:
    """Launch the TUI application."""
    app = MCPTuiApp(initial_config=config)
    app.run()
