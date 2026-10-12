"""
Data models for mcptui.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class ServerConfig(BaseModel):
    """Configuration for an MCP server."""
    name: str
    transport: Literal["stdio", "sse"] = "stdio"
    command: Optional[str] = None
    args: List[str] = Field(default_factory=list)
    env: Dict[str, str] = Field(default_factory=dict)
    url: Optional[str] = None
    cwd: Optional[str] = None
    source: str = "custom"  # e.g., "claude_desktop", "cursor", "local", "cli"

    def display_target(self) -> str:
        """User-friendly target representation."""
        if self.transport == "sse":
            return self.url or "unknown URL"
        cmd = self.command or ""
        if self.args:
            cmd += " " + " ".join(self.args)
        return cmd or "unknown command"


@dataclass
class CallRecord:
    """Record of an executed tool call, prompt fetch, or resource read."""
    id: str
    timestamp: datetime
    kind: Literal["tool", "resource", "prompt"]
    name: str
    input_data: Any
    output_data: Any
    is_error: bool = False
    duration_ms: float = 0.0
    error_message: Optional[str] = None


@dataclass
class ProtocolMessage:
    """Raw JSON-RPC message captured over the transport."""
    timestamp: datetime
    direction: Literal["sent", "received"]
    method: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)
