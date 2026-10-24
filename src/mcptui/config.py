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
            if name not in discovered:
                discovered[name] = cfg

    # 3. Cursor global
    for cursor_path in get_cursor_mcp_paths():
        if cursor_path.is_file():
            for name, cfg in load_from_file(cursor_path, "Cursor").items():
                if name not in discovered:
                    discovered[name] = cfg

    return discovered


def save_to_local_mcp_json(config: ServerConfig, path: Optional[Path] = None) -> Path:
    """Save or update an MCP server definition in a local mcp.json file."""
    target_path = path or (Path.cwd() / "mcp.json")
    data: dict = {}
    if target_path.is_file():
        try:
            data = json.loads(target_path.read_text(encoding="utf-8"))
        except Exception:
            data = {}

    if "mcpServers" not in data or not isinstance(data["mcpServers"], dict):
        data["mcpServers"] = {}

    server_entry: dict = {}
    if config.transport == "sse":
        server_entry["url"] = config.url
    else:
        server_entry["command"] = config.command
        if config.args:
            server_entry["args"] = config.args
        if config.env:
            server_entry["env"] = config.env

    data["mcpServers"][config.name] = server_entry
    target_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return target_path


def remove_from_local_mcp_json(name: str, path: Optional[Path] = None) -> bool:
    """Remove an MCP server from local mcp.json file."""
    target_path = path or (Path.cwd() / "mcp.json")
    if not target_path.is_file():
        return False
    try:
        data = json.loads(target_path.read_text(encoding="utf-8"))
        if "mcpServers" in data and name in data["mcpServers"]:
            del data["mcpServers"][name]
            target_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            return True
    except Exception:
        pass
    return False


def save_to_claude_desktop(config: ServerConfig) -> Path:
    """Save or update an MCP server definition in Claude Desktop configuration."""
    target_path = get_claude_desktop_config_path()
    if not target_path:
        raise RuntimeError("Unable to determine Claude Desktop configuration path on this operating system.")

    target_path.parent.mkdir(parents=True, exist_ok=True)
    return save_to_local_mcp_json(config, path=target_path)


def save_to_cursor(config: ServerConfig, path: Optional[Path] = None) -> Path:
    """Save or update an MCP server definition in Cursor mcp.json configuration."""
    if path:
        target_path = path
    else:
        cursor_dir = Path.cwd() / ".cursor"
        cursor_dir.mkdir(parents=True, exist_ok=True)
        target_path = cursor_dir / "mcp.json"

    return save_to_local_mcp_json(config, path=target_path)
