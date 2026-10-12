"""
Sample custom MCP server for testing mcptui workflows.
"""

import asyncio
import json
from mcp.server.mcpserver import MCPServer

server = MCPServer(
    name="my-custom-notes",
    instructions="A simple personal notes and utility server.",
)

NOTES_DB = [
    {"id": 1, "title": "Buy groceries", "text": "Apples, Milk, Bread, Coffee"},
    {"id": 2, "title": "Deploy project", "text": "Run tests and push to GitHub"},
]


@server.tool(name="add_note", description="Add a new note to the personal notes list.")
def add_note(title: str, text: str) -> str:
    new_id = len(NOTES_DB) + 1
    note = {"id": new_id, "title": title, "text": text}
    NOTES_DB.append(note)
    return json.dumps({"status": "created", "note": note}, indent=2)


@server.tool(name="list_notes", description="List all saved notes.")
def list_notes() -> str:
    return json.dumps({"count": len(NOTES_DB), "notes": NOTES_DB}, indent=2)


@server.tool(name="convert_temperature", description="Convert temperature between Celsius and Fahrenheit.")
def convert_temperature(value: float, from_scale: str = "C", to_scale: str = "F") -> str:
    from_scale = from_scale.upper()
    to_scale = to_scale.upper()
    if from_scale == to_scale:
        converted = value
    elif from_scale == "C" and to_scale == "F":
        converted = (value * 9 / 5) + 32
    elif from_scale == "F" and to_scale == "C":
        converted = (value - 32) * 5 / 9
    else:
        return json.dumps({"error": f"Unsupported conversion: {from_scale} to {to_scale}"})

    return json.dumps({"original": f"{value}°{from_scale}", "converted": f"{round(converted, 2)}°{to_scale}"}, indent=2)


@server.resource(uri="notes://all", name="All Notes", mime_type="application/json")
def get_all_notes() -> str:
    return json.dumps(NOTES_DB, indent=2)


if __name__ == "__main__":
    asyncio.run(server.run_stdio_async())
