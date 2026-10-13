"""
Built-in demo MCP server for mcptui.
Provides rich tools, resources, and prompts to test drive mcptui instantly.
"""

from __future__ import annotations

import asyncio
import json
import math
import platform
import sys
from datetime import datetime
from typing import Any, Dict

from mcp.server.mcpserver import MCPServer

server = MCPServer(
    name="mcptui-demo",
    instructions="Demo MCP server with sample tools, resources, and prompts for testing mcptui.",
)


@server.tool(
    name="calculate",
    description="Evaluates a mathematical expression safely (e.g. '2 + 2 * 10' or 'math.sqrt(144)').",
)
def calculate(expression: str) -> str:
    """Safe arithmetic calculation."""
    allowed_names = {
        "abs": abs,
        "round": round,
        "min": min,
        "max": max,
        "pow": pow,
        "math": math,
        "pi": math.pi,
        "e": math.e,
        "sqrt": math.sqrt,
        "sin": math.sin,
        "cos": math.cos,
        "tan": math.tan,
    }
    try:
        # Strip dangerous tokens
        if any(w in expression for w in ["__", "import", "exec", "eval", "open", "os", "sys"]):
            return json.dumps({"error": "Expression contains prohibited tokens."})
        result = eval(expression, {"__builtins__": {}}, allowed_names)  # pylint: disable=eval-used
        return json.dumps({"expression": expression, "result": result, "status": "success"}, indent=2)
    except Exception as exc:
        return json.dumps({"expression": expression, "error": str(exc), "status": "error"}, indent=2)


@server.tool(
    name="weather",
    description="Get current weather and 3-day forecast for a given city.",
)
def weather(city: str, units: str = "celsius") -> str:
    """Mock weather lookup."""
    temp_c = 18 + (hash(city.lower()) % 15)
    temp = temp_c if units.lower() == "celsius" else round(temp_c * 9 / 5 + 32, 1)
    symbol = "C" if units.lower() == "celsius" else "F"
    conditions = ["Sunny", "Partly Cloudy", "Rainy", "Overcast", "Windy"]
    condition = conditions[abs(hash(city)) % len(conditions)]

    report = {
        "city": city.title(),
        "temperature": f"{temp}{symbol}",
        "condition": condition,
        "humidity": f"{45 + abs(hash(city)) % 40}%",
        "wind_speed": f"{8 + abs(hash(city)) % 25} km/h",
        "units": units,
        "updated_at": datetime.now().isoformat(),
    }
    return json.dumps(report, indent=2)


@server.tool(
    name="system_info",
    description="Returns platform, Python runtime, and host system information.",
)
def system_info() -> str:
    """Get host system information."""
    info = {
        "platform": platform.platform(),
        "python_version": sys.version.split()[0],
        "processor": platform.processor() or "Unknown",
        "architecture": platform.architecture()[0],
        "node": platform.node(),
        "timestamp": datetime.now().isoformat(),
    }
    return json.dumps(info, indent=2)


@server.tool(
    name="text_analyzer",
    description="Analyze text statistics: word count, character count, estimated reading time, and complexity.",
)
def text_analyzer(text: str) -> str:
    """Analyze text statistics."""
    words = text.split()
    word_count = len(words)
    char_count = len(text)
    char_no_spaces = len(text.replace(" ", ""))
    sentence_count = max(1, text.count(".") + text.count("!") + text.count("?"))
    reading_time_sec = round((word_count / 200) * 60, 1)

    analysis = {
        "word_count": word_count,
        "character_count": char_count,
        "characters_no_spaces": char_no_spaces,
        "sentences": sentence_count,
        "avg_words_per_sentence": round(word_count / sentence_count, 1),
        "estimated_reading_time_seconds": reading_time_sec,
    }
    return json.dumps(analysis, indent=2)


@server.tool(
    name="mock_query",
    description="Run a mock SQL query against a simulated customer & orders database.",
)
def mock_query(query: str, limit: int = 3) -> str:
    """Simulated database query runner."""
    sample_records = [
        {"id": 101, "customer": "Alice Smith", "plan": "Enterprise", "amount": 499.0, "status": "active"},
        {"id": 102, "customer": "Bob Jones", "plan": "Pro", "amount": 99.0, "status": "active"},
        {"id": 103, "customer": "Charlie Day", "plan": "Free", "amount": 0.0, "status": "inactive"},
        {"id": 104, "customer": "Dana Scully", "plan": "Enterprise", "amount": 499.0, "status": "active"},
        {"id": 105, "customer": "Fox Mulder", "plan": "Pro", "amount": 99.0, "status": "pending"},
    ]
    records = sample_records[: max(1, min(limit, len(sample_records)))]
    return json.dumps({
        "query": query,
        "row_count": len(records),
        "columns": ["id", "customer", "plan", "amount", "status"],
        "data": records,
    }, indent=2)


# Resources
@server.resource(uri="system://info", name="System Specs", mime_type="application/json")
def get_system_specs() -> str:
    """System specifications resource."""
    return json.dumps({
        "os": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "machine": platform.machine(),
        "python": sys.version,
    }, indent=2)


@server.resource(uri="help://quickstart.md", name="MCP Quickstart Guide", mime_type="text/markdown")
def get_quickstart_guide() -> str:
    """Markdown quickstart guide resource."""
    return """# Welcome to mcptui!

`mcptui` is the **Postman for Model Context Protocol (MCP)**.

## How to use:
1. **Tools Tab**: Select any tool from the sidebar, fill in arguments, and hit `Ctrl+Enter` (or click Execute) to test it live!
2. **Resources Tab**: Browse and view data resources provided by the server.
3. **Prompts Tab**: Test prompt templates with parameters.
4. **Logs Tab**: Inspect real-time JSON-RPC 2.0 messages exchanged with the server.

Happy debugging!
"""


@server.resource(uri="help://build-server.md", name="How to Build Your Own MCP Server", mime_type="text/markdown")
def get_build_server_guide() -> str:
    """Complete guide on creating custom MCP servers."""
    return """# How to Build Your Own MCP Server (in 2 Minutes)

MCP (Model Context Protocol) connects AI assistants (Claude, Cursor) to your code, APIs, and data.

## 1. Install dependencies
```bash
pip install mcp
# or with uv:
uv add mcp
```

## 2. Write your server (my_server.py)
```python
import asyncio
from mcp.server.mcpserver import MCPServer

# Create server instance
server = MCPServer("my-service")

# Define a tool (function AI can execute)
@server.tool(name="greet", description="Send a friendly greeting")
def greet(name: str) -> str:
    return f"Hello, {name}! Your MCP server is working."

# Run the server over stdio
if __name__ == "__main__":
    asyncio.run(server.run_stdio_async())
```

## 3. Test and debug it instantly in mcptui
```bash
mcptui run "python my_server.py"
```

## 4. Connect to Claude Desktop or Cursor
Add it to your `mcp.json` or `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "my-service": {
      "command": "python",
      "args": ["path/to/my_server.py"]
    }
  }
}
```
"""


# Prompts
@server.prompt(
    name="code_review",
    description="Generate a comprehensive code review with improvements and security checks.",
)
def code_review(language: str, code: str) -> list[dict[str, Any]]:
    """Prompt template for code review."""
    return [
        {
            "role": "user",
            "content": {
                "type": "text",
                "text": f"Please review the following {language} code for bugs, performance optimizations, and best practices:\n\n```{language}\n{code}\n```",
            },
        }
    ]


@server.prompt(
    name="explain_concept",
    description="Explain a complex technical concept with simple analogies.",
)
def explain_concept(concept: str, target_audience: str = "junior developer") -> list[dict[str, Any]]:
    """Prompt template for explaining concepts."""
    return [
        {
            "role": "user",
            "content": {
                "type": "text",
                "text": f"Explain the concept '{concept}' suitable for a {target_audience}. Use intuitive analogies and a concrete code example.",
            },
        }
    ]


def main():
    """Run the demo server over stdio."""
    asyncio.run(server.run_stdio_async())


if __name__ == "__main__":
    main()
