"""
Modal dialog for switching between discovered or custom MCP servers.
"""

from __future__ import annotations

import sys
from typing import Dict, Optional

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, OptionList
from textual.widgets.option_list import Option

from mcptui.config import discover_all_servers
from mcptui.models import ServerConfig


class ServerSwitcherModal(ModalScreen[Optional[ServerConfig]]):
    """Modal allowing the user to select an MCP server or enter custom parameters."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.servers: Dict[str, ServerConfig] = {}

    def compose(self) -> ComposeResult:
        with Container(id="server-modal-container"):
            yield Label("Select an MCP Server", id="modal-title")
            yield OptionList(id="server-select-list")
            yield Label("Or enter custom command / SSE URL:", classes="input-section-title")
            yield Input(placeholder="e.g. npx -y @modelcontextprotocol/server-everything", id="custom-server-input")
            with Horizontal(classes="modal-buttons"):
                yield Button("Connect", variant="success", id="btn-modal-connect")
                yield Button("Cancel", variant="default", id="btn-modal-cancel")

    def on_mount(self) -> None:
        self.servers = discover_all_servers()
        if "demo" not in self.servers and "mcptui-demo" not in self.servers:
            from mcptui.cli import get_demo_config
            self.servers["mcptui-demo"] = get_demo_config()

        option_list = self.query_one("#server-select-list", OptionList)
        for name, cfg in self.servers.items():
            label = Text()
            label.append("* ", style="bold green" if cfg.source == "built-in demo" else "bold cyan")
            label.append(name, style="bold white")
            label.append(f" ({cfg.source})", style="dim italic")
            label.append(f" - {cfg.display_target()}", style="dim")
            option_list.add_option(Option(prompt=label, id=name))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-modal-cancel":
            self.dismiss(None)
        elif event.button.id == "btn-modal-connect":
            self._submit_selection()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_id and event.option_id in self.servers:
            self.dismiss(self.servers[event.option_id])

    def _submit_selection(self) -> None:
        custom_val = self.query_one("#custom-server-input", Input).value.strip()
        if custom_val:
            if custom_val.startswith("http://") or custom_val.startswith("https://"):
                cfg = ServerConfig(name="custom-sse", transport="sse", url=custom_val, source="custom")
            else:
                parts = custom_val.split()
                cfg = ServerConfig(
                    name="custom-cmd",
                    transport="stdio",
                    command=parts[0],
                    args=parts[1:] if len(parts) > 1 else [],
                    source="custom",
                )
            self.dismiss(cfg)
            return

        option_list = self.query_one("#server-select-list", OptionList)
        if option_list.highlighted is not None:
            opt = option_list.get_option_at_index(option_list.highlighted)
            if opt.id and opt.id in self.servers:
                self.dismiss(self.servers[opt.id])
                return

        self.dismiss(None)
