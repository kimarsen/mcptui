"""
MCP client manager handling connection, capabilities, call execution, and protocol tracing.
"""

from __future__ import annotations

import asyncio
import sys
import time
import uuid
from contextlib import AsyncExitStack
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

import anyio
from mcp.client.session import ClientSession
from mcp.client.sse import sse_client
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.types import Prompt, Resource, ResourceTemplate, Tool

from mcptui.models import CallRecord, ProtocolMessage, ServerConfig


class InterceptedReadStream:
    """Read stream wrapper that intercepts messages for logging."""

    def __init__(self, inner: Any, on_message: Callable[[str, Any], None]):
        self._inner = inner
        self._on_message = on_message

    async def receive(self) -> Any:
        msg = await self._inner.receive()
        if hasattr(msg, "message"):
            self._on_message("received", msg.message)
        return msg

    async def aclose(self) -> None:
        await self._inner.aclose()

    async def __aenter__(self) -> "InterceptedReadStream":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.aclose()

    async def __aiter__(self):
        while True:
            try:
                yield await self.receive()
            except (anyio.EndOfStream, anyio.ClosedResourceError):
                break

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


class InterceptedWriteStream:
    """Write stream wrapper that intercepts messages for logging."""

    def __init__(self, inner: Any, on_message: Callable[[str, Any], None]):
        self._inner = inner
        self._on_message = on_message

    async def send(self, item: Any) -> None:
        if hasattr(item, "message"):
            self._on_message("sent", item.message)
        await self._inner.send(item)

    async def aclose(self) -> None:
        await self._inner.aclose()

    async def __aenter__(self) -> "InterceptedWriteStream":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.aclose()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


class MCPClientManager:
    """High-level async manager for an MCP server session."""

    def __init__(self):
        self.config: Optional[ServerConfig] = None
        self.session: Optional[ClientSession] = None
        self._exit_stack: Optional[AsyncExitStack] = None
        self.is_connected: bool = False

        # Server metadata
        self.server_name: str = ""
        self.server_version: str = ""
        self.instructions: str = ""

        # Discovered items
        self.tools: List[Tool] = []
        self.resources: List[Resource] = []
        self.resource_templates: List[ResourceTemplate] = []
        self.prompts: List[Prompt] = []

        # History and logs
        self.history: List[CallRecord] = []
        self.protocol_logs: List[ProtocolMessage] = []
        self._max_history: int = 100
        self._max_logs: int = 250

        # Callbacks
        self._on_log_callback: Optional[Callable[[ProtocolMessage], None]] = None

    def set_log_callback(self, callback: Optional[Callable[[ProtocolMessage], None]]) -> None:
        """Register a callback for new JSON-RPC messages."""
        self._on_log_callback = callback

    def _handle_raw_message(self, direction: str, raw_msg: Any) -> None:
        """Process and record an intercepted message."""
        try:
            if hasattr(raw_msg, "model_dump"):
                data = raw_msg.model_dump()
            elif isinstance(raw_msg, dict):
                data = raw_msg
            else:
                data = {"raw": str(raw_msg)}
        except Exception:
            data = {"raw": str(raw_msg)}

        method = data.get("method")
        msg = ProtocolMessage(
            timestamp=datetime.now(),
            direction="sent" if direction == "sent" else "received",
            method=method,
            data=data,
        )
        self.protocol_logs.append(msg)
        if len(self.protocol_logs) > self._max_logs:
            self.protocol_logs.pop(0)

        if self._on_log_callback:
            try:
                self._on_log_callback(msg)
            except Exception:
                pass

    async def connect(self, config: ServerConfig) -> None:
        """Establish a connection to the MCP server and initialize the session."""
        if self.is_connected:
            await self.disconnect()

        self.config = config
        self._exit_stack = AsyncExitStack()

        try:
            if config.transport == "stdio":
                cmd = config.command
                if not cmd:
                    raise ValueError("No command specified for stdio transport.")

                # If running demo or python module
                args = list(config.args)
                params = StdioServerParameters(
                    command=cmd,
                    args=args,
                    env=config.env or None,
                    cwd=config.cwd or None,
                )
                read_stream, write_stream = await self._exit_stack.enter_async_context(
                    stdio_client(params)
                )
            elif config.transport == "sse":
                if not config.url:
                    raise ValueError("No URL specified for SSE transport.")
                read_stream, write_stream = await self._exit_stack.enter_async_context(
                    sse_client(config.url)
                )
            elif config.transport == "inmemory":
                # In-process direct memory transport for instant demo connection
                from mcptui.demo_server import server as demo_server

                client_to_server_writer, client_to_server_reader = anyio.create_memory_object_stream(100)
                server_to_client_writer, server_to_client_reader = anyio.create_memory_object_stream(100)

                server_task = asyncio.create_task(
                    demo_server._lowlevel_server.run(
                        client_to_server_reader,
                        server_to_client_writer,
                        demo_server._lowlevel_server.create_initialization_options(),
                    )
                )

                async def _cleanup_inmemory() -> None:
                    client_to_server_writer.close()
                    server_to_client_writer.close()
                    server_task.cancel()
                    try:
                        await server_task
                    except BaseException:
                        pass

                self._exit_stack.push_async_callback(_cleanup_inmemory)
                read_stream = server_to_client_reader
                write_stream = client_to_server_writer
            else:
                raise ValueError(f"Unsupported transport: {config.transport}")

            logged_read = InterceptedReadStream(read_stream, self._handle_raw_message)
            logged_write = InterceptedWriteStream(write_stream, self._handle_raw_message)

            self.session = await self._exit_stack.enter_async_context(
                ClientSession(logged_read, logged_write)
            )

            init_result = await self.session.initialize()
            if hasattr(init_result, "server_info") and init_result.server_info:
                self.server_name = init_result.server_info.name or config.name
                self.server_version = init_result.server_info.version or ""
            else:
                self.server_name = config.name

            self.instructions = getattr(init_result, "instructions", "") or ""
            self.is_connected = True

            # Populate initial capabilities
            await self.refresh_capabilities()

        except Exception:
            await self.disconnect()
            raise

    async def disconnect(self) -> None:
        """Disconnect and clean up resources."""
        self.is_connected = False
        self.session = None
        if self._exit_stack:
            try:
                await self._exit_stack.aclose()
            except Exception:
                pass
            self._exit_stack = None

    async def refresh_capabilities(self) -> None:
        """Fetch all tools, resources, and prompts from the server."""
        if not self.session or not self.is_connected:
            return

        # Fetch tools
        try:
            tools_res = await self.session.list_tools()
            self.tools = tools_res.tools if tools_res and hasattr(tools_res, "tools") else []
        except Exception:
            self.tools = []

        # Fetch resources
        try:
            res_res = await self.session.list_resources()
            self.resources = res_res.resources if res_res and hasattr(res_res, "resources") else []
        except Exception:
            self.resources = []

        # Fetch resource templates
        try:
            tmpl_res = await self.session.list_resource_templates()
            self.resource_templates = (
                tmpl_res.resource_templates if tmpl_res and hasattr(tmpl_res, "resource_templates") else []
            )
        except Exception:
            self.resource_templates = []

        # Fetch prompts
        try:
            prompt_res = await self.session.list_prompts()
            self.prompts = prompt_res.prompts if prompt_res and hasattr(prompt_res, "prompts") else []
        except Exception:
            self.prompts = []

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> CallRecord:
        """Execute a tool and record the result and latency."""
        if not self.session or not self.is_connected:
            raise RuntimeError("MCP client is not connected.")

        start_time = time.perf_counter()
        call_id = uuid.uuid4().hex[:8]
        timestamp = datetime.now()

        try:
            result = await self.session.call_tool(name, arguments)
            duration_ms = (time.perf_counter() - start_time) * 1000.0

            # Parse content from result
            content_list: List[Dict[str, Any]] = []
            if hasattr(result, "content") and result.content:
                for item in result.content:
                    if hasattr(item, "text"):
                        content_list.append({"type": "text", "text": item.text})
                    elif hasattr(item, "data"):
                        content_list.append({"type": "binary", "mimeType": getattr(item, "mimeType", "")})
                    elif hasattr(item, "model_dump"):
                        content_list.append(item.model_dump())
                    else:
                        content_list.append({"raw": str(item)})

            record = CallRecord(
                id=call_id,
                timestamp=timestamp,
                kind="tool",
                name=name,
                input_data=arguments,
                output_data={"content": content_list, "is_error": getattr(result, "is_error", False)},
                is_error=getattr(result, "is_error", False),
                duration_ms=round(duration_ms, 2),
            )
        except Exception as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            record = CallRecord(
                id=call_id,
                timestamp=timestamp,
                kind="tool",
                name=name,
                input_data=arguments,
                output_data=None,
                is_error=True,
                duration_ms=round(duration_ms, 2),
                error_message=str(exc),
            )

        self._add_history(record)
        return record

    async def read_resource(self, uri: str) -> CallRecord:
        """Read a resource by URI and record the result."""
        if not self.session or not self.is_connected:
            raise RuntimeError("MCP client is not connected.")

        start_time = time.perf_counter()
        call_id = uuid.uuid4().hex[:8]
        timestamp = datetime.now()

        try:
            result = await self.session.read_resource(uri)
            duration_ms = (time.perf_counter() - start_time) * 1000.0

            contents: List[Dict[str, Any]] = []
            if hasattr(result, "contents") and result.contents:
                for c in result.contents:
                    if hasattr(c, "text"):
                        contents.append({"uri": str(c.uri), "mimeType": getattr(c, "mimeType", ""), "text": c.text})
                    elif hasattr(c, "blob"):
                        contents.append({"uri": str(c.uri), "mimeType": getattr(c, "mimeType", ""), "blob_bytes": len(c.blob)})
                    elif hasattr(c, "model_dump"):
                        contents.append(c.model_dump())

            record = CallRecord(
                id=call_id,
                timestamp=timestamp,
                kind="resource",
                name=uri,
                input_data={"uri": uri},
                output_data={"contents": contents},
                is_error=False,
                duration_ms=round(duration_ms, 2),
            )
        except Exception as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            record = CallRecord(
                id=call_id,
                timestamp=timestamp,
                kind="resource",
                name=uri,
                input_data={"uri": uri},
                output_data=None,
                is_error=True,
                duration_ms=round(duration_ms, 2),
                error_message=str(exc),
            )

        self._add_history(record)
        return record

    async def get_prompt(self, name: str, arguments: Dict[str, Any]) -> CallRecord:
        """Get prompt template rendered with arguments."""
        if not self.session or not self.is_connected:
            raise RuntimeError("MCP client is not connected.")

        start_time = time.perf_counter()
        call_id = uuid.uuid4().hex[:8]
        timestamp = datetime.now()

        try:
            result = await self.session.get_prompt(name, arguments)
            duration_ms = (time.perf_counter() - start_time) * 1000.0

            messages: List[Dict[str, Any]] = []
            if hasattr(result, "messages") and result.messages:
                for m in result.messages:
                    if hasattr(m, "model_dump"):
                        messages.append(m.model_dump())
                    else:
                        messages.append({"role": getattr(m, "role", ""), "content": str(getattr(m, "content", ""))})

            record = CallRecord(
                id=call_id,
                timestamp=timestamp,
                kind="prompt",
                name=name,
                input_data=arguments,
                output_data={"description": getattr(result, "description", ""), "messages": messages},
                is_error=False,
                duration_ms=round(duration_ms, 2),
            )
        except Exception as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            record = CallRecord(
                id=call_id,
                timestamp=timestamp,
                kind="prompt",
                name=name,
                input_data=arguments,
                output_data=None,
                is_error=True,
                duration_ms=round(duration_ms, 2),
                error_message=str(exc),
            )

        self._add_history(record)
        return record

    def _add_history(self, record: CallRecord) -> None:
        """Append record to history, evicting oldest if buffer is full."""
        self.history.insert(0, record)
        if len(self.history) > self._max_history:
            self.history.pop()
