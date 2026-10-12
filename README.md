# ⚡ mcptui

<div align="center">

<h3><b>The Postman for Model Context Protocol (MCP)</b></h3>

*A modern, interactive Terminal UI and playground for testing, inspecting, and benchmarking MCP servers.*

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://python.org)
[![MCP Protocol](https://img.shields.io/badge/MCP-2024--11--05-8A2BE2.svg)](https://modelcontextprotocol.io)
[![Textual](https://img.shields.io/badge/Built%20With-Textual-green.svg)](https://textual.textualize.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

<br/>

```bash
# Try it right now with zero installation:
uvx mcptui demo
```

</div>

---

## 🎯 Why mcptui?

Building and debugging **MCP (Model Context Protocol)** servers is rapidly becoming a core task for AI developers. But today, inspecting servers is painful:
- You have to edit `claude_desktop_config.json` and restart Claude Desktop repeatedly.
- Or you have to write custom JSON-RPC scripts to test if a tool handles arguments properly.

**`mcptui` fixes this completely.** It gives you a dedicated, beautiful **Terminal UI (TUI)** playground to test tools, inspect schemas, browse resources, preview prompts, and watch live JSON-RPC 2.0 traffic in real time.

```
 ┌────────────────────────────────────────────────────────────────────────┐
 │ ⚡ mcptui — Postman for MCP             ● mcptui-demo [stdio] (24ms)   │
 ├────────────────────────────────────────────────────────────────────────┤
 │ [1] 🛠 Tools   [2] 📚 Resources   [3] 💬 Prompts   [4] ⚡ Logs   [5] 🕒 History  │
 ├─────────────────────────┬──────────────────────────────────────────────┤
 │ 🔍 Filter tools...      │ 🛠 calculate                                 │
 │ ─────────────────────── │ Safe arithmetic calculation                  │
 │ 🛠 calculate             │                                              │
 │ 🛠 weather               │ Arguments (JSON)                             │
 │ 🛠 system_info           │ ┌──────────────────────────────────────────┐ │
 │ 🛠 text_analyzer         │ │ { "expression": "100 * 2 + 42" }         │ │
 │ 🛠 mock_query            │ └──────────────────────────────────────────┘ │
 │                         │ [▶ Execute (Ctrl+Enter)] [📋 Copy]  ✅ 18ms  │
 │                         │                                              │
 │                         │ Response                                     │
 │                         │ ┌──────────────────────────────────────────┐ │
 │                         │ │ { "result": 242, "status": "success" }   │ │
 │                         │ └──────────────────────────────────────────┘ │
 └─────────────────────────┴──────────────────────────────────────────────┘
```

---

## 🚀 Quickstart

You don't need to install anything if you have [`uv`](https://docs.astral.sh/uv/):

### 1. Test Drive with Built-in Demo Server
```bash
uvx mcptui demo
```
*Launches an embedded mock server with tools (math, weather, system stats, mock SQL), resources, and prompt templates.*

### 2. Connect to Any Local Command (stdio)
```bash
# Node / NPX servers:
uvx mcptui run "npx -y @modelcontextprotocol/server-filesystem /path/to/dir"

# Python servers:
uvx mcptui run "python my_mcp_server.py"

# uv / pipx:
uvx mcptui run "uv run server.py"
```

### 3. Connect to Remote SSE Server
```bash
uvx mcptui connect http://localhost:8000/sse
```

### 4. Auto-Discovery Mode
```bash
uvx mcptui
```
*Automatically finds all MCP servers configured in **Claude Desktop**, **Cursor** (`.cursor/mcp.json`), **Cline**, and local `mcp.json`!*

---

## ✨ Features

- 🛠 **Interactive Tool Workspace**:
  - Auto-generates clean JSON parameter templates from tool `inputSchema`.
  - In-terminal JSON editor with error validation.
  - One-click execution (`Ctrl+Enter`) with live duration & latency measurement.
  - Pretty-printed, syntax-highlighted output with clipboard copying (`c`).

- 📚 **Resource Explorer**:
  - Browse available server resources and dynamic URI templates.
  - Read resources with automatic syntax detection (Markdown, JSON, Plain Text).

- 💬 **Prompt Inspector**:
  - Test prompt templates with dynamic argument substitution.
  - Preview generated message sequences (System, User, Assistant).

- 🕵️ **Live JSON-RPC 2.0 Traffic Inspector**:
  - Intercepts and logs all raw protocol packets (`--> SENT` and `<-- RECEIVED`).
  - Search and filter messages by method (`tools/call`, `initialize`, etc.).
  - Protocol latency, request/response matching, and packet export.

- 🕒 **Execution History & Replay**:
  - Stores recent invocations with timestamps, status, input parameters, and duration.
  - Easily copy previous requests or inspect errors.

- 🔍 **Auto-Discovery & Local Server Management**:
  - Scans system paths for:
    - **Claude Desktop** (`claude_desktop_config.json` on macOS, Windows, Linux)
    - **Cursor** (`.cursor/mcp.json` & global settings)
    - Local project `mcp.json` / `.mcp.json`
  - Register any server with `mcptui add <name> <command>`.
  - Switch between servers on the fly with `F2`.

---

## 🤖 Headless CLI & Automation

`mcptui` is also a powerful headless CLI for scripting and CI/CD testing:

```bash
# Register a server into local mcp.json permanently
mcptui add notes "python examples/sample_server.py"

# List all registered and discovered servers
mcptui servers

# Headless capabilities inspection
mcptui list notes
# Or on the fly without saving:
mcptui list --cmd "python examples/sample_server.py"

# Execute a tool headlessly and get clean JSON output
mcptui call convert_temperature '{"value": 100, "from_scale": "C", "to_scale": "F"}' --server notes

# Remove a server from local config
mcptui remove notes
```

---

## ⌨️ Keybindings

| Key | Action |
|-----|--------|
| `Ctrl + Enter` | Execute active tool / Read resource / Get prompt |
| `F2` | Open Server Switcher modal |
| `F5` / `Ctrl + R` | Reload server capabilities |
| `Tab` / `Shift + Tab` | Navigate between sidebar, editor, and response view |
| `1` – `5` | Switch tabs (Tools, Resources, Prompts, Logs, History) |
| `c` | Copy result to system clipboard |
| `Ctrl + Q` / `q` | Quit mcptui |

---

## 📦 Installation Options

### Using `uv` (Recommended)
```bash
uv tool install mcptui
```

### Using `pipx`
```bash
pipx install mcptui
```

### Using standard `pip`
```bash
pip install mcptui
```

---

## 🛠 Local Development

```bash
git clone https://github.com/<your-username>/mcptui.git
cd mcptui
uv sync
uv run pytest
uv run mcptui demo
```

---

## 📄 License

MIT License. Contributions, feedback, and stars are warmly welcome! ⭐
