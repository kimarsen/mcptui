"""
Modal dialog for generating and exporting code snippets and client configurations.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

import pyperclip
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, RadioButton, RadioSet, TextArea

from mcptui.codegen import (
    generate_claude_config_snippet,
    generate_cli_snippet,
    generate_cursor_config_snippet,
    generate_jsonrpc_snippet,
    generate_python_snippet,
    generate_typescript_snippet,
)
from mcptui.config import save_to_claude_desktop, save_to_cursor
from mcptui.models import ServerConfig


class ExportModal(ModalScreen[None]):
    """Modal allowing the user to view, copy, and install integration code snippets."""

    BINDINGS = [
        ("escape", "dismiss_modal", "Close"),
        ("q", "dismiss_modal", "Close"),
    ]

    def __init__(
        self,
        config: ServerConfig,
        tool_name: Optional[str] = None,
        arguments: Optional[Dict[str, Any]] = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.config = config
        self.tool_name = tool_name or "my_tool"
        self.arguments = arguments or {}
        self.current_format: str = "python"

    def compose(self) -> ComposeResult:
        with Container(id="export-modal-container"):
            yield Label(f"📦 Export Integration: {self.config.name} / {self.tool_name}", id="export-modal-title")

            with Horizontal(id="export-format-bar"):
                yield Label("Format:", classes="export-bar-label")
                with RadioSet(id="export-radio-set"):
                    yield RadioButton("Python SDK", value=True, id="radio-python")
                    yield RadioButton("TypeScript SDK", id="radio-typescript")
                    yield RadioButton("Claude Desktop", id="radio-claude")
                    yield RadioButton("Cursor", id="radio-cursor")
                    yield RadioButton("CLI Call", id="radio-cli")
                    yield RadioButton("Raw JSON-RPC", id="radio-jsonrpc")

            yield TextArea(
                text="",
                read_only=True,
                id="export-code-viewer",
                classes="export-code-box",
            )

            with Horizontal(classes="modal-buttons"):
                yield Button("Copy Snippet", variant="success", id="btn-export-copy")
                yield Button("Install to Claude Desktop", id="btn-install-claude")
                yield Button("Install to Cursor", id="btn-install-cursor")
                yield Button("Close (Esc)", variant="default", id="btn-export-close")

    def on_mount(self) -> None:
        self.update_code_preview("python")

    def action_dismiss_modal(self) -> None:
        self.dismiss(None)

    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        btn_id = event.pressed.id or ""
        fmt_map = {
            "radio-python": "python",
            "radio-typescript": "typescript",
            "radio-claude": "claude",
            "radio-cursor": "cursor",
            "radio-cli": "cli",
            "radio-jsonrpc": "jsonrpc",
        }
        fmt = fmt_map.get(btn_id, "python")
        self.update_code_preview(fmt)

    def update_code_preview(self, fmt: str) -> None:
        self.current_format = fmt
        viewer = self.query_one("#export-code-viewer", TextArea)

        if fmt == "python":
            viewer.language = "python"
            viewer.text = generate_python_snippet(self.config, self.tool_name, self.arguments)
        elif fmt == "typescript":
            viewer.language = "javascript"
            viewer.text = generate_typescript_snippet(self.config, self.tool_name, self.arguments)
        elif fmt == "claude":
            viewer.language = "json"
            viewer.text = generate_claude_config_snippet(self.config)
        elif fmt == "cursor":
            viewer.language = "json"
            viewer.text = generate_cursor_config_snippet(self.config)
        elif fmt == "cli":
            viewer.language = "bash"
            viewer.text = generate_cli_snippet(self.config, self.tool_name, self.arguments)
        elif fmt == "jsonrpc":
            viewer.language = "json"
            viewer.text = generate_jsonrpc_snippet(self.tool_name, self.arguments)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-export-close":
            self.dismiss(None)
        elif event.button.id == "btn-export-copy":
            viewer = self.query_one("#export-code-viewer", TextArea)
            try:
                pyperclip.copy(viewer.text)
                self.app.notify("Code snippet copied to clipboard!", severity="information")
            except Exception as exc:
                self.app.notify(f"Copy failed: {exc}", severity="warning")
        elif event.button.id == "btn-install-claude":
            self._install_to_claude()
        elif event.button.id == "btn-install-cursor":
            self._install_to_cursor()

    def _install_to_claude(self) -> None:
        try:
            cfg_to_save = ServerConfig(
                name=self.config.name,
                transport=self.config.transport,
                command=self.config.command,
                args=self.config.args,
                env=self.config.env,
                url=self.config.url,
            )
            if cfg_to_save.transport == "inmemory":
                cfg_to_save.transport = "stdio"

            path = save_to_claude_desktop(cfg_to_save)
            self.app.notify(
                f"Installed '{cfg_to_save.name}' to Claude Desktop!\nSaved to: {path.name}",
                severity="information",
            )
        except Exception as exc:
            self.app.notify(f"Failed to install to Claude: {exc}", severity="error")

    def _install_to_cursor(self) -> None:
        try:
            cfg_to_save = ServerConfig(
                name=self.config.name,
                transport=self.config.transport,
                command=self.config.command,
                args=self.config.args,
                env=self.config.env,
                url=self.config.url,
            )
            if cfg_to_save.transport == "inmemory":
                cfg_to_save.transport = "stdio"

            path = save_to_cursor(cfg_to_save)
            self.app.notify(
                f"Installed '{cfg_to_save.name}' to Cursor!\nSaved to: {path}",
                severity="information",
            )
        except Exception as exc:
            self.app.notify(f"Failed to install to Cursor: {exc}", severity="error")
