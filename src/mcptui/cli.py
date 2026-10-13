"""
CLI entrypoint for mcptui.
Supports interactive TUI launching, server discovery, management, and headless operations.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import List, Optional

# Ensure UTF-8 on Windows consoles to prevent cp1251/charmap crashes
if sys.platform == "win32":
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleOutputCP(65001)
        kernel32.SetConsoleCP(65001)
    except Exception:
        pass
    try:
        if sys.stdout and hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if sys.stderr and hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import typer
from rich import print as rprint
from rich.console import Console
from rich.table import Table

from mcptui.config import (
    discover_all_servers,
    remove_from_local_mcp_json,
    save_to_local_mcp_json,
)
from mcptui.models import ServerConfig

app = typer.Typer(
    name="mcptui",
    help="mcptui: The Postman for Model Context Protocol (MCP).\nInteractive TUI & playground for inspecting, testing, and debugging MCP servers.",
    add_completion=False,
)
console = Console()


def get_demo_config() -> ServerConfig:
    return ServerConfig(
        name="mcptui-demo",
        transport="inmemory",
        command=sys.executable,
        args=["-m", "mcptui.demo_server"],
        source="built-in demo",
    )


@app.callback(invoke_without_command=True)
def main_callback(
    ctx: typer.Context,
    server: Optional[str] = typer.Option(None, "--server", "-s", help="Name of an MCP server to connect to"),
    cmd: Optional[str] = typer.Option(None, "--cmd", "-c", help="Command to run via stdio (e.g. 'python server.py')"),
    sse: Optional[str] = typer.Option(None, "--sse", help="SSE URL to connect to (e.g. 'http://localhost:8000/sse')"),
    demo: bool = typer.Option(False, "--demo", "-d", help="Launch directly into demo mode"),
):
    """
    Launch mcptui interactive Terminal UI.
    """
    if ctx.invoked_subcommand is not None:
        return

    target_config: Optional[ServerConfig] = None

    if demo:
        target_config = get_demo_config()
    elif sse:
        target_config = ServerConfig(name="remote-sse", transport="sse", url=sse, source="cli")
    elif cmd:
        target_config = _parse_cmd_to_config("stdio-server", cmd)
    elif server:
        all_servers = discover_all_servers()
        if server in all_servers:
            target_config = all_servers[server]
        elif server.lower() == "demo":
            target_config = get_demo_config()
        else:
            rprint(f"[bold red]Error:[/bold red] Server '{server}' not found among discovered servers.")
            rprint("Run [bold cyan]mcptui servers[/bold cyan] to see available servers or [bold cyan]mcptui demo[/bold cyan] for demo.")
            raise typer.Exit(code=1)
    else:
        # Auto-detect servers
        all_servers = discover_all_servers()
        if all_servers:
            first_name = next(iter(all_servers))
            target_config = all_servers[first_name]
        else:
            target_config = get_demo_config()

    from mcptui.ui.app import run_tui
    run_tui(target_config)


@app.command(name="demo")
def cmd_demo():
    """
    Launch mcptui with the built-in rich demo MCP server.
    """
    from mcptui.ui.app import run_tui
    run_tui(get_demo_config())


@app.command(name="run")
def cmd_run(
    command: str = typer.Argument(..., help="The command to run as an MCP server via stdio"),
    args: List[str] = typer.Argument(None, help="Optional arguments for the command"),
):
    """
    Launch an MCP server via stdio and open mcptui connected to it.
    Example: mcptui run "python my_server.py"
    Example: mcptui run "npx -y @modelcontextprotocol/server-everything"
    """
    full_args = list(args) if args else []
    if not full_args and " " in command:
        parts = command.split()
        cmd = parts[0]
        full_args = parts[1:]
    else:
        cmd = command

    name = _derive_friendly_name(cmd, full_args)

    cfg = ServerConfig(
        name=name,
        transport="stdio",
        command=cmd,
        args=full_args,
        source="cli:run",
    )
    from mcptui.ui.app import run_tui
    run_tui(cfg)


@app.command(name="connect")
def cmd_connect(
    url: str = typer.Argument(..., help="SSE URL of the MCP server (e.g. http://localhost:8000/sse)"),
):
    """
    Connect to a remote MCP server via SSE and open mcptui.
    """
    cfg = ServerConfig(name="remote-mcp", transport="sse", url=url, source="cli:connect")
    from mcptui.ui.app import run_tui
    run_tui(cfg)


@app.command(name="servers")
def cmd_servers():
    """
    List all discovered MCP servers (from Claude Desktop, Cursor, local mcp.json).
    """
    discovered = discover_all_servers()
    if not discovered:
        rprint("[yellow]No MCP servers found in Claude Desktop, Cursor, or local mcp.json.[/yellow]")
        rprint("Try [bold cyan]mcptui demo[/bold cyan] to test drive mcptui with a built-in server,")
        rprint("or [bold cyan]mcptui add <name> <command>[/bold cyan] to register one locally.")
        return

    table = Table(title="Discovered MCP Servers", show_header=True, header_style="bold cyan")
    table.add_column("Name", style="bold white")
    table.add_column("Transport", style="magenta")
    table.add_column("Target / Command", style="green")
    table.add_column("Source", style="dim")

    for name, cfg in discovered.items():
        table.add_row(name, cfg.transport, cfg.display_target(), cfg.source)

    console.print(table)


@app.command(name="add")
def cmd_add(
    name: str = typer.Argument(..., help="Friendly name for the server"),
    target: str = typer.Argument(..., help="Command (e.g. 'python server.py') or SSE URL"),
):
    """
    Register an MCP server into local mcp.json so it is recognized permanently.
    Example: mcptui add notes "python my_notes_server.py"
    Example: mcptui add remote "http://localhost:8000/sse"
    """
    if target.startswith("http://") or target.startswith("https://"):
        cfg = ServerConfig(name=name, transport="sse", url=target, source="local:mcp.json")
    else:
        parts = target.split()
        cmd = parts[0]
        args = parts[1:] if len(parts) > 1 else []
        cfg = ServerConfig(name=name, transport="stdio", command=cmd, args=args, source="local:mcp.json")

    file_path = save_to_local_mcp_json(cfg)
    rprint(f"[bold green]Saved server '{name}' to {file_path.name}![/bold green]")
    rprint(f"You can now run [bold cyan]mcptui --server {name}[/bold cyan] or inspect with [bold cyan]mcptui list {name}[/bold cyan].")


@app.command(name="remove")
def cmd_remove(
    name: str = typer.Argument(..., help="Name of server to remove from local mcp.json"),
):
    """
    Remove an MCP server from local mcp.json.
    """
    if remove_from_local_mcp_json(name):
        rprint(f"[bold green]Server '{name}' removed from mcp.json.[/bold green]")
    else:
        rprint(f"[bold yellow]Server '{name}' not found in local mcp.json.[/bold yellow]")


@app.command(name="list")
def cmd_list(
    server_name: Optional[str] = typer.Argument(None, help="Name of server to inspect (or 'demo')"),
    cmd: Optional[str] = typer.Option(None, "--cmd", "-c", help="Direct command to inspect on the fly"),
):
    """
    Headless listing of tools, resources, and prompts for a server.
    Example: mcptui list demo
    Example: mcptui list --cmd "python my_server.py"
    """
    if cmd:
        cfg = _parse_cmd_to_config("stdio-inspect", cmd)
    else:
        cfg = _resolve_server(server_name)

    from mcptui.client import MCPClientManager
    client = MCPClientManager()

    async def _inspect():
        with console.status(f"[cyan]Connecting to {cfg.name}...[/cyan]"):
            await client.connect(cfg)

        try:
            # Tools
            rprint(f"\n[bold green]Tools ({len(client.tools)}):[/bold green]")
            for t in client.tools:
                rprint(f"  * [bold white]{t.name}[/bold white]: {t.description or 'No description'}")

            # Resources
            rprint(f"\n[bold blue]Resources ({len(client.resources)}):[/bold blue]")
            for r in client.resources:
                rprint(f"  * [bold white]{r.name or str(r.uri)}[/bold white] ([dim]{r.uri}[/dim])")

            # Prompts
            rprint(f"\n[bold magenta]Prompts ({len(client.prompts)}):[/bold magenta]")
            for p in client.prompts:
                rprint(f"  * [bold white]{p.name}[/bold white]: {p.description or 'No description'}")
        finally:
            await client.disconnect()

    asyncio.run(_inspect())


@app.command(name="call")
def cmd_call(
    tool_name: str = typer.Argument(..., help="Tool name to execute"),
    arguments: str = typer.Argument("{}", help="JSON string of arguments"),
    server: Optional[str] = typer.Option(None, "--server", "-s", help="Server name (or 'demo')"),
    cmd: Optional[str] = typer.Option(None, "--cmd", "-c", help="Direct command to execute on the fly"),
):
    """
    Execute a tool headlessly and output the JSON response.
    Example: mcptui call calculate '{"expression": "2 + 2"}' --server demo
    """
    try:
        args_dict = json.loads(arguments) if arguments else {}
    except Exception as exc:
        rprint(f"[bold red]Invalid JSON arguments:[/bold red] {exc}")
        raise typer.Exit(code=1)

    if cmd:
        cfg = _parse_cmd_to_config("stdio-call", cmd)
    else:
        cfg = _resolve_server(server)

    from mcptui.client import MCPClientManager
    client = MCPClientManager()

    async def _execute():
        await client.connect(cfg)
        try:
            rec = await client.call_tool(tool_name, args_dict)
            if rec.is_error:
                rprint(f"[bold red]Execution error ({rec.duration_ms}ms):[/bold red]")
                print(json.dumps(rec.output_data or {"error": rec.error_message}, indent=2))
                sys.exit(1)
            else:
                print(json.dumps(rec.output_data, indent=2))
        finally:
            await client.disconnect()

    asyncio.run(_execute())


def _derive_friendly_name(cmd: str, args: List[str]) -> str:
    """Create an intuitive server label based on command or target script."""
    for arg in args:
        if arg.endswith(".py") or arg.endswith(".js") or arg.endswith(".ts"):
            return os.path.basename(arg)
    base = os.path.basename(cmd)
    return base or "custom-server"


def _parse_cmd_to_config(default_name: str, cmd_string: str) -> ServerConfig:
    parts = cmd_string.split()
    cmd = parts[0]
    args = parts[1:] if len(parts) > 1 else []
    name = _derive_friendly_name(cmd, args) or default_name
    return ServerConfig(name=name, transport="stdio", command=cmd, args=args, source="cli")


def _resolve_server(server_name: Optional[str]) -> ServerConfig:
    if not server_name or server_name.lower() == "demo":
        return get_demo_config()

    all_servers = discover_all_servers()
    if server_name in all_servers:
        return all_servers[server_name]

    rprint(f"[bold red]Error:[/bold red] Server '{server_name}' not found.")
    rprint("Run [bold cyan]mcptui servers[/bold cyan] to see available servers.")
    raise typer.Exit(code=1)


def main():
    app()


if __name__ == "__main__":
    main()
