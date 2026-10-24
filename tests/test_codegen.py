import json
import tempfile
import unittest
from pathlib import Path
from typer.testing import CliRunner

from mcptui.cli import app
from mcptui.codegen import (
    generate_claude_config_snippet,
    generate_cli_snippet,
    generate_cursor_config_snippet,
    generate_jsonrpc_snippet,
    generate_python_snippet,
    generate_typescript_snippet,
)
from mcptui.config import save_to_claude_desktop, save_to_cursor
from mcptui.models import ServerConfig


class TestCodegen(unittest.TestCase):
    def setUp(self):
        self.stdio_cfg = ServerConfig(
            name="notes-server",
            transport="stdio",
            command="python",
            args=["notes.py", "--port", "9000"],
            env={"DEBUG": "1"},
        )
        self.sse_cfg = ServerConfig(
            name="remote-server",
            transport="sse",
            url="http://localhost:8000/sse",
        )

    def test_python_snippet_stdio(self):
        code = generate_python_snippet(self.stdio_cfg, "add_note", {"title": "Hello", "body": "World"})
        self.assertIn("StdioServerParameters", code)
        self.assertIn("notes.py", code)
        self.assertIn('"add_note"', code)
        self.assertIn('"title": "Hello"', code)
        self.assertIn("ClientSession", code)

    def test_python_snippet_sse(self):
        code = generate_python_snippet(self.sse_cfg, "fetch_data", {"query": "test"})
        self.assertIn("sse_client", code)
        self.assertIn("http://localhost:8000/sse", code)
        self.assertIn('"fetch_data"', code)

    def test_typescript_snippet_stdio(self):
        code = generate_typescript_snippet(self.stdio_cfg, "add_note", {"title": "Hi"})
        self.assertIn("StdioClientTransport", code)
        self.assertIn("@modelcontextprotocol/sdk", code)
        self.assertIn("add_note", code)

    def test_typescript_snippet_sse(self):
        code = generate_typescript_snippet(self.sse_cfg, "fetch", {})
        self.assertIn("SSEClientTransport", code)
        self.assertIn("http://localhost:8000/sse", code)

    def test_claude_config_snippet(self):
        snippet = generate_claude_config_snippet(self.stdio_cfg)
        data = json.loads(snippet)
        self.assertIn("mcpServers", data)
        self.assertIn("notes-server", data["mcpServers"])
        self.assertEqual(data["mcpServers"]["notes-server"]["command"], "python")

    def test_cursor_config_snippet(self):
        snippet = generate_cursor_config_snippet(self.stdio_cfg)
        data = json.loads(snippet)
        self.assertIn("mcpServers", data)
        self.assertIn("notes-server", data["mcpServers"])

    def test_cli_snippet(self):
        cmd_str = generate_cli_snippet(self.stdio_cfg, "add_note", {"title": "Test"})
        self.assertIn("mcptui call add_note", cmd_str)
        self.assertIn('"title": "Test"', cmd_str)

    def test_jsonrpc_snippet(self):
        snippet = generate_jsonrpc_snippet("calculate", {"expression": "2+2"}, msg_id=42)
        data = json.loads(snippet)
        self.assertEqual(data["jsonrpc"], "2.0")
        self.assertEqual(data["id"], 42)
        self.assertEqual(data["method"], "tools/call")
        self.assertEqual(data["params"]["name"], "calculate")

    def test_cli_export_command(self):
        runner = CliRunner()
        result = runner.invoke(app, ["export", "demo", "--format", "python", "--tool", "calculate"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("ClientSession", result.output)
        self.assertIn("calculate", result.output)

    def test_cli_export_claude_format(self):
        runner = CliRunner()
        result = runner.invoke(app, ["export", "demo", "--format", "claude"])
        self.assertEqual(result.exit_code, 0)
        data = json.loads(result.output)
        self.assertIn("mcpServers", data)

    def test_save_to_cursor_path(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            target_path = Path(tmp_dir) / ".cursor" / "mcp.json"
            target_path.parent.mkdir(parents=True, exist_ok=True)
            res_path = save_to_cursor(self.stdio_cfg, path=target_path)
            self.assertTrue(res_path.is_file())
            content = json.loads(res_path.read_text(encoding="utf-8"))
            self.assertIn("notes-server", content["mcpServers"])


if __name__ == "__main__":
    unittest.main()
