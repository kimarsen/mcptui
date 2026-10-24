"""
Interactive Tools explorer and executor view.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import pyperclip
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Button, Input, Label, OptionList, Static, TextArea
from textual.widgets.option_list import Option

from mcptui.client import MCPClientManager


def generate_template_from_schema(schema: Dict[str, Any]) -> str:
    """Generate a clean sample JSON payload based on JSON Schema properties."""
    properties = schema.get("properties") or {}
    template = {}
    for prop_name, prop_meta in properties.items():
        if not isinstance(prop_meta, dict):
            template[prop_name] = ""
            continue

        if "default" in prop_meta:
            template[prop_name] = prop_meta["default"]
        else:
            p_type = prop_meta.get("type", "string")
            if p_type == "string":
                template[prop_name] = ""
            elif p_type in ("integer", "number"):
                template[prop_name] = 0
            elif p_type == "boolean":
                template[prop_name] = False
            elif p_type == "array":
                template[prop_name] = []
            elif p_type == "object":
                template[prop_name] = {}
            else:
                template[prop_name] = None
    return json.dumps(template, indent=2)


class ToolsView(Widget):
    """Tools view with explorer list, schema inspector, argument editor, and output runner."""

    DEFAULT_CLASSES = "split-view"

    current_tool_name: reactive[Optional[str]] = reactive(None)

    def __init__(self, client: MCPClientManager, **kwargs):
        super().__init__(**kwargs)
        self.client = client
        self._all_tool_names: List[str] = []

    def compose(self) -> ComposeResult:
        with Container(classes="sidebar"):
            yield Input(placeholder="Filter tools...", id="tool-search", classes="sidebar-search")
            yield OptionList(id="tool-list", classes="item-list")

        with Vertical(classes="main-content"):
            with Container(classes="item-meta-box"):
                yield Label("Select a tool from the left to inspect and run", id="tool-title", classes="item-title")
                yield Static("", id="tool-desc", classes="item-desc")

            yield Label("Arguments (JSON)", classes="input-section-title")
            yield TextArea(
                text="{}",
                language="json",
                id="tool-params-editor",
                classes="param-editor",
            )

            with Horizontal(classes="action-bar"):
                yield Button("Execute (Ctrl+Enter)", variant="success", id="btn-execute")
                yield Button("Copy Result", variant="default", id="btn-copy")
                yield Label("Status: Ready", id="status-pill")

            yield Label("Response", classes="input-section-title")
            yield TextArea(
                text="",
                language="json",
                read_only=True,
                id="tool-response-viewer",
                classes="response-box",
            )

    def on_mount(self) -> None:
        self.refresh_tools()

    def refresh_tools(self, filter_text: str = "") -> None:
        """Populate tools list from client."""
        tool_list = self.query_one("#tool-list", OptionList)
        tool_list.clear_options()

        self._all_tool_names = [t.name for t in self.client.tools]
        filtered = [
            t for t in self.client.tools
            if not filter_text or filter_text.lower() in t.name.lower() or filter_text.lower() in (t.description or "").lower()
        ]

        for tool in filtered:
            label = Text()
            label.append("> ", style="bold cyan")
            label.append(tool.name, style="bold white")
            tool_list.add_option(Option(prompt=label, id=tool.name))

        if filtered and (self.current_tool_name is None or self.current_tool_name not in [t.name for t in filtered]):
            tool_list.highlighted = 0
            self.select_tool(filtered[0].name)

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "tool-search":
            self.refresh_tools(event.value)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_id:
            self.select_tool(event.option_id)

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if event.option_id:
            self.select_tool(event.option_id)

    def select_tool(self, tool_name: str) -> None:
        """Select a tool and populate info + template."""
        self.current_tool_name = tool_name
        tool = next((t for t in self.client.tools if t.name == tool_name), None)
        if not tool:
            return

        title_label = self.query_one("#tool-title", Label)
        title_label.update(f"TOOL: {tool.name}")

        desc_label = self.query_one("#tool-desc", Static)
        desc_label.update(tool.description or "No description provided.")

        # Generate sample template
        editor = self.query_one("#tool-params-editor", TextArea)
        raw_schema = getattr(tool, "input_schema", None) or getattr(tool, "inputSchema", None)
        schema = raw_schema if isinstance(raw_schema, dict) else {}
        template = generate_template_from_schema(schema)
        editor.text = template

        # Reset status
        status = self.query_one("#status-pill", Label)
        status.update("Status: Ready")
        status.remove_class("success", "error", "running")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-execute":
            await self.execute_current_tool()
        elif event.button.id == "btn-copy":
            self.copy_result()

    def copy_result(self) -> None:
        """Copy response to system clipboard."""
        viewer = self.query_one("#tool-response-viewer", TextArea)
        if viewer.text:
            try:
                pyperclip.copy(viewer.text)
                self.app.notify("Response copied to clipboard!", severity="information")
            except Exception as exc:
                self.app.notify(f"Clipboard copy failed: {exc}", severity="warning")

    async def execute_current_tool(self) -> None:
        """Parse arguments and call the tool through the MCP client."""
        if not self.current_tool_name:
            self.app.notify("No tool selected", severity="warning")
            return

        editor = self.query_one("#tool-params-editor", TextArea)
        params_str = editor.text.strip()
        try:
            params = json.loads(params_str) if params_str else {}
            if not isinstance(params, dict):
                raise ValueError("Arguments must be a JSON object (dictionary)")
        except Exception as exc:
            self.app.notify(f"Invalid JSON: {exc}", severity="error")
            return

        status = self.query_one("#status-pill", Label)
        status.update("Status: Executing...")
        status.remove_class("success", "error")
        status.add_class("running")

        viewer = self.query_one("#tool-response-viewer", TextArea)

        try:
            record = await self.client.call_tool(self.current_tool_name, params)
            if record.is_error:
                status.update(f"Status: ERROR ({record.duration_ms}ms)")
                status.remove_class("running", "success")
                status.add_class("error")
                err_text = record.error_message or json.dumps(record.output_data, indent=2)
                viewer.text = err_text
            else:
                status.update(f"Status: SUCCESS ({record.duration_ms}ms)")
                status.remove_class("running", "error")
                status.add_class("success")

                # Format response nicely
                if record.output_data and "content" in record.output_data:
                    content_list = record.output_data["content"]
                    # If single text result that is JSON, format as JSON
                    if len(content_list) == 1 and content_list[0].get("type") == "text":
                        text_val = content_list[0]["text"]
                        try:
                            parsed_json = json.loads(text_val)
                            viewer.text = json.dumps(parsed_json, indent=2)
                        except Exception:
                            viewer.text = text_val
                    else:
                        viewer.text = json.dumps(record.output_data, indent=2)
                else:
                    viewer.text = json.dumps(record.output_data, indent=2)
        except Exception as exc:
            status.update("Status: FAILED")
            status.remove_class("running", "success")
            status.add_class("error")
            viewer.text = f"Error executing tool:\n{exc}"
