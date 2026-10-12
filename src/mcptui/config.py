"""
Configuration loading and auto-discovery of MCP servers.
Supports Claude Desktop, Cursor, Cline, Zed, and local mcp.json files.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Dict, Optional

from mcptui.models import ServerConfig


def get_claude_desktop_config_path() -> Optional[Path]:
    """Find the Claude Desktop configuration file based on the OS."""
    if sys.platform == "win32":
        app_data = os.environ.get("APPDATA")
        if app_data:
            return Path(app_data) / "Claude" / "claude_desktop_config.json"
    elif sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    else:  # Linux & BSD
        config_home = os.environ.get("XDG_CONFIG_HOME")
        if config_home:
            return Path(config_home) / "Claude" / "claude_desktop_config.json"
        return Path.home() / ".config" / "Claude" / "claude_desktop_config.json"
    return None


def get_cursor_mcp_paths() -> list[Path]:
    """Find potential Cursor MCP configuration files."""
    paths: list[Path] = [
        Path.cwd() / ".cursor" / "mcp.json",
    ]
    if sys.platform == "win32":
        app_data = os.environ.get("APPDATA")
        if app_data:
            paths.append(Path(app_data) / "Cursor" / "mcp.json")
    elif sys.platform == "darwin":
        paths.append(Path.home() / "Library" / "Application Support" / "Cursor" / "mcp.json")
    else:
        paths.append(Path.home() / ".config" / "Cursor" / "mcp.json")
    return paths


def parse_mcp_servers_dict(data: dict, source_label: str) -> Dict[str, ServerConfig]:
    """Extract ServerConfig objects from a dictionary containing 'mcpServers'."""
    servers: Dict[str, ServerConfig] = {}
    mcp_servers = data.get("mcpServers") or data.get("servers") or {}
    if not isinstance(mcp_servers, dict):
        return servers

    for name, spec in mcp_servers.items():
        if not isinstance(spec, dict):
            continue

        # Check if SSE or HTTP
        url = spec.get("url") or spec.get("sseUrl")
        transport = "sse" if url else "stdio"

        command = spec.get("command")
        args = spec.get("args") or []
        env = spec.get("env") or {}
        cwd = spec.get("cwd")

        if not command and not url:
            continue

        servers[name] = ServerConfig(
            name=name,
            transport=transport,
            command=command,
            args=[str(a) for a in args],
            env={str(k): str(v) for k, v in env.items()},
            url=url,
            cwd=cwd,
            source=source_label,
        )
    return servers


def load_from_file(path: Path, source_label: str) -> Dict[str, ServerConfig]:
    """Safely load and parse a JSON configuration file."""
    if not path.is_file():
        return {}
    try:
        content = path.read_text(encoding="utf-8")
        data = json.loads(content)
        if isinstance(data, dict):
            return parse_mcp_servers_dict(data, source_label)
    except Exception:
        pass
    return {}


def discover_all_servers() -> Dict[str, ServerConfig]:
    """
    Auto-discover all MCP servers from all known local and system configurations.
    Returns a mapping of server_name -> ServerConfig.
    """
    discovered: Dict[str, ServerConfig] = {}

    # 1. Local directory files (mcp.json, .mcp.json, .cursor/mcp.json)
    local_candidates = [
        (Path.cwd() / "mcp.json", "local:mcp.json"),
        (Path.cwd() / ".mcp.json", "local:.mcp.json"),
        (Path.cwd() / ".cursor" / "mcp.json", "local:.cursor/mcp.json"),
    ]
    for path, label in local_candidates:
        for name, cfg in load_from_file(path, label).items():
            discovered[name] = cfg

    # 2. Claude Desktop
    claude_path = get_claude_desktop_config_path()
    if claude_path and claude_path.is_file():
        for name, cfg in load_from_file(claude_path, "Claude Desktop").items():
            # Don't overwrite local project configs with the same name
            if name not in discovered:
                discovered[name] = cfg

    # 3. Cursor global
    for cursor_path in get_cursor_mcp_paths():
        if cursor_path.is_file():
            for name, cfg in load_from_file(cursor_path, "Cursor").items():
                if name not in discovered:
                    discovered[name] = cfg

    return discovered
