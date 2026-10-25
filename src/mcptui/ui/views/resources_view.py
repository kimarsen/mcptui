"""
Resources explorer and viewer for MCP.
"""

from __future__ import annotations

import json
import time
from typing import List, Optional

import pyperclip
from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Button, Input, Label, OptionList, Static, TextArea
from textual.widgets.option_list import Option

from mcptui.client import MCPClientManager


class ResourcesView(Widget):
    """Resources viewer for browsing and inspecting MCP server resources."""

    DEFAULT_CLASSES = "split-view"

    current_uri: reactive[Optional[str]] = reactive(None)

    def __init__(self, client: MCPClientManager, **kwargs):
        super().__init__(**kwargs)
        self.client = client
        self._all_uris: List[str] = []
        self._last_title_click_time: float = 0.0
        self._last_list_click_time: float = 0.0

    def compose(self) -> ComposeResult:
        with Container(classes="sidebar"):
            yield Input(placeholder="Filter resources...", id="resource-search", classes="sidebar-search")
            yield OptionList(id="resource-list", classes="item-list")

        with Vertical(classes="main-content"):
            with Container(classes="item-meta-box"):
                yield Label("Select a resource to inspect and read", id="res-title", classes="item-title")
                yield Static("", id="res-desc", classes="item-desc")

            with Horizontal(classes="action-bar"):
                yield Button("Read Resource", variant="success", id="btn-read-res")
                yield Button("Copy Content", variant="default", id="btn-copy-res")
                yield Label("Status: Ready", id="res-status-pill")

            yield Label("Resource Content", classes="input-section-title")
            yield TextArea(
                text="",
                read_only=True,
                id="res-content-viewer",
                classes="response-box",
            )

    def on_mount(self) -> None:
        self.refresh_resources()

    def refresh_resources(self, filter_text: str = "") -> None:
        """Populate resource list from client."""
        res_list = self.query_one("#resource-list", OptionList)
        res_list.clear_options()

        self._all_uris = [str(r.uri) for r in self.client.resources]
        filtered = [
            r for r in self.client.resources
            if not filter_text or filter_text.lower() in str(r.uri).lower() or filter_text.lower() in (r.name or "").lower()
        ]

        for res in filtered:
            label = Text()
            label.append("> ", style="bold green")
            label.append(res.name or str(res.uri), style="bold white")
            res_list.add_option(Option(prompt=label, id=str(res.uri)))

        # Also add templates if any
        for tmpl in self.client.resource_templates:
            uri_pattern = tmpl.uriTemplate if hasattr(tmpl, "uriTemplate") else getattr(tmpl, "uri_template", "")
            if not filter_text or filter_text.lower() in uri_pattern.lower() or filter_text.lower() in (tmpl.name or "").lower():
                label = Text()
                label.append("* ", style="bold yellow")
                label.append(tmpl.name or uri_pattern, style="italic yellow")
                res_list.add_option(Option(prompt=label, id=f"tmpl:{uri_pattern}"))

        if filtered and (self.current_uri is None or self.current_uri not in [str(r.uri) for r in filtered]):
            res_list.highlighted = 0
            self.select_resource(str(filtered[0].uri))

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "resource-search":
            self.refresh_resources(event.value)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_id:
            self.select_resource(event.option_id)

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if event.option_id:
            self.select_resource(event.option_id)

    def select_resource(self, uri: str) -> None:
        """Select resource and show metadata."""
        self.current_uri = uri
        title_label = self.query_one("#res-title", Label)
        desc_label = self.query_one("#res-desc", Static)

        if uri.startswith("tmpl:"):
            pattern = uri[5:]
            title_label.update(f"Template: {pattern}")
            title_label.tooltip = "Resource Template (dynamic URI pattern)"
            desc_label.update("Resource Template (dynamic URI pattern)")
            return

        res = next((r for r in self.client.resources if str(r.uri) == uri), None)
        if not res:
            return

        title_label.update(f"RESOURCE: {res.name or uri}")
        title_label.tooltip = f"Double-click to read: {res.name or uri}"
        mime = getattr(res, "mimeType", "") or "text/plain"
        desc = getattr(res, "description", "") or ""
        desc_label.update(f"URI: {uri} | MIME: {mime}\n{desc}")

        status = self.query_one("#res-status-pill", Label)
        status.update("Status: Ready")
        status.remove_class("success", "error", "running")

    def load_resource_call(self, uri: str) -> None:
        """Select a resource and highlight it in the list."""
        self.select_resource(uri)
        try:
            res_list = self.query_one("#resource-list", OptionList)
            for idx in range(res_list.option_count):
                opt = res_list.get_option_at_index(idx)
                if opt.id == uri:
                    res_list.highlighted = idx
                    break
        except Exception:
            pass

    async def on_click(self, event: events.Click) -> None:
        """Handle click events, triggering resource reading on double click."""
        target = event.widget
        if not target:
            return

        now = time.monotonic()
        # Double-click on resource title in the open tab
        if target.id == "res-title" or target.has_class("item-title") or target.id == "item-meta-box":
            if event.chain >= 2 or (now - self._last_title_click_time <= 0.8):
                await self.read_current_resource()
                self._last_title_click_time = 0.0
                return
            self._last_title_click_time = now
            return

        # Double-click on resource list in the sidebar
        if target.id == "resource-list" or any(getattr(a, "id", None) == "resource-list" for a in getattr(target, "ancestors", [])):
            if event.chain >= 2 or (now - self._last_list_click_time <= 0.8):
                await self.read_current_resource()
                self._last_list_click_time = 0.0
                return
            self._last_list_click_time = now

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-read-res":
            await self.read_current_resource()
        elif event.button.id == "btn-copy-res":
            self.copy_content()

    def copy_content(self) -> None:
        viewer = self.query_one("#res-content-viewer", TextArea)
        if viewer.text:
            try:
                pyperclip.copy(viewer.text)
                self.app.notify("Resource content copied!", severity="information")
            except Exception as exc:
                self.app.notify(f"Copy failed: {exc}", severity="warning")

    async def read_current_resource(self) -> None:
        """Read resource via client."""
        if not self.current_uri or self.current_uri.startswith("tmpl:"):
            self.app.notify("Select a concrete resource URI", severity="warning")
            return

        status = self.query_one("#res-status-pill", Label)
        status.update("Status: Reading...")
        status.remove_class("success", "error")
        status.add_class("running")

        viewer = self.query_one("#res-content-viewer", TextArea)

        try:
            record = await self.client.read_resource(self.current_uri)
            if record.is_error:
                status.update(f"Status: ERROR ({record.duration_ms}ms)")
                status.remove_class("running", "success")
                status.add_class("error")
                viewer.text = record.error_message or json.dumps(record.output_data, indent=2)
            else:
                status.update(f"Status: READ ({record.duration_ms}ms)")
                status.remove_class("running", "error")
                status.add_class("success")

                contents = record.output_data.get("contents", [])
                if contents and "text" in contents[0]:
                    text_content = contents[0]["text"]
                    mime = contents[0].get("mimeType", "")
                    if "json" in mime:
                        try:
                            viewer.language = "json"
                            viewer.text = json.dumps(json.loads(text_content), indent=2)
                        except Exception:
                            viewer.text = text_content
                    elif "markdown" in mime:
                        viewer.language = "markdown"
                        viewer.text = text_content
                    else:
                        viewer.language = "markdown"
                        viewer.text = text_content
                else:
                    viewer.text = json.dumps(record.output_data, indent=2)
        except Exception as exc:
            status.update("Status: FAILED")
            status.remove_class("running", "success")
            status.add_class("error")
            viewer.text = f"Error reading resource:\n{exc}"
