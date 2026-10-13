"""
Prompts explorer and tester for MCP.
"""

from __future__ import annotations

import json
from typing import List, Optional

import pyperclip
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Button, Input, Label, OptionList, Static, TextArea
from textual.widgets.option_list import Option

from mcptui.client import MCPClientManager


class PromptsView(Widget):
    """Prompts view for testing MCP server prompt templates."""

    DEFAULT_CLASSES = "split-view"

    current_prompt_name: reactive[Optional[str]] = reactive(None)

    def __init__(self, client: MCPClientManager, **kwargs):
        super().__init__(**kwargs)
        self.client = client
        self._all_prompts: List[str] = []

    def compose(self) -> ComposeResult:
        with Container(classes="sidebar"):
            yield Input(placeholder="Filter prompts...", id="prompt-search", classes="sidebar-search")
            yield OptionList(id="prompt-list", classes="item-list")

        with Vertical(classes="main-content"):
            with Container(classes="item-meta-box"):
                yield Label("Select a prompt template from the left", id="prompt-title", classes="item-title")
                yield Static("", id="prompt-desc", classes="item-desc")

            yield Label("Arguments (JSON)", classes="input-section-title")
            yield TextArea(
                text="{}",
                language="json",
                id="prompt-params-editor",
                classes="param-editor",
            )

            with Horizontal(classes="action-bar"):
                yield Button("Get Prompt", variant="success", id="btn-get-prompt")
                yield Button("Copy Messages", variant="default", id="btn-copy-prompt")
                yield Label("Status: Ready", id="prompt-status-pill")

            yield Label("Rendered Messages", classes="input-section-title")
            yield TextArea(
                text="",
                language="markdown",
                read_only=True,
                id="prompt-response-viewer",
                classes="response-box",
            )

    def on_mount(self) -> None:
        self.refresh_prompts()

    def refresh_prompts(self, filter_text: str = "") -> None:
        """Populate prompts list from client."""
        p_list = self.query_one("#prompt-list", OptionList)
        p_list.clear_options()

        self._all_prompts = [p.name for p in self.client.prompts]
        filtered = [
            p for p in self.client.prompts
            if not filter_text or filter_text.lower() in p.name.lower() or filter_text.lower() in (p.description or "").lower()
        ]

        for p in filtered:
            label = Text()
            label.append("> ", style="bold magenta")
            label.append(p.name, style="bold white")
            p_list.add_option(Option(prompt=label, id=p.name))

        if filtered and (self.current_prompt_name is None or self.current_prompt_name not in [p.name for p in filtered]):
            p_list.highlighted = 0
            self.select_prompt(filtered[0].name)

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "prompt-search":
            self.refresh_prompts(event.value)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_id:
            self.select_prompt(event.option_id)

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if event.option_id:
            self.select_prompt(event.option_id)

    def select_prompt(self, name: str) -> None:
        """Select prompt and display template info."""
        self.current_prompt_name = name
        prompt = next((p for p in self.client.prompts if p.name == name), None)
        if not prompt:
            return

        title_label = self.query_one("#prompt-title", Label)
        title_label.update(f"PROMPT: {prompt.name}")

        desc_label = self.query_one("#prompt-desc", Static)
        desc_label.update(prompt.description or "No description provided.")

        # Build template from arguments list
        template = {}
        if hasattr(prompt, "arguments") and prompt.arguments:
            for arg in prompt.arguments:
                arg_name = arg.name if hasattr(arg, "name") else str(arg)
                template[arg_name] = ""

        editor = self.query_one("#prompt-params-editor", TextArea)
        editor.text = json.dumps(template, indent=2)

        status = self.query_one("#prompt-status-pill", Label)
        status.update("Status: Ready")
        status.remove_class("success", "error", "running")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-get-prompt":
            await self.get_current_prompt()
        elif event.button.id == "btn-copy-prompt":
            self.copy_prompt()

    def copy_prompt(self) -> None:
        viewer = self.query_one("#prompt-response-viewer", TextArea)
        if viewer.text:
            try:
                pyperclip.copy(viewer.text)
                self.app.notify("Prompt messages copied!", severity="information")
            except Exception as exc:
                self.app.notify(f"Copy failed: {exc}", severity="warning")

    async def get_current_prompt(self) -> None:
        """Fetch rendered prompt from client."""
        if not self.current_prompt_name:
            self.app.notify("No prompt selected", severity="warning")
            return

        editor = self.query_one("#prompt-params-editor", TextArea)
        params_str = editor.text.strip()
        try:
            params = json.loads(params_str) if params_str else {}
        except Exception as exc:
            self.app.notify(f"Invalid JSON: {exc}", severity="error")
            return

        status = self.query_one("#prompt-status-pill", Label)
        status.update("Status: Fetching...")
        status.remove_class("success", "error")
        status.add_class("running")

        viewer = self.query_one("#prompt-response-viewer", TextArea)

        try:
            record = await self.client.get_prompt(self.current_prompt_name, params)
            if record.is_error:
                status.update(f"Status: ERROR ({record.duration_ms}ms)")
                status.remove_class("running", "success")
                status.add_class("error")
                viewer.text = record.error_message or json.dumps(record.output_data, indent=2)
            else:
                status.update(f"Status: FETCHED ({record.duration_ms}ms)")
                status.remove_class("running", "error")
                status.add_class("success")

                output_str = ""
                messages = record.output_data.get("messages", [])
                for msg in messages:
                    role = msg.get("role", "unknown").upper()
                    content = msg.get("content", {})
                    if isinstance(content, dict) and "text" in content:
                        text_part = content["text"]
                    elif isinstance(content, str):
                        text_part = content
                    else:
                        text_part = json.dumps(content, indent=2)

                    output_str += f"### Role: {role}\n\n{text_part}\n\n---\n\n"

                viewer.text = output_str.strip() or json.dumps(record.output_data, indent=2)
        except Exception as exc:
            status.update("Status: FAILED")
            status.remove_class("running", "success")
            status.add_class("error")
            viewer.text = f"Error fetching prompt:\n{exc}"
