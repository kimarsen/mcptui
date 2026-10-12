import json
import sys
import tempfile
import unittest
from pathlib import Path
from typer.testing import CliRunner

from mcptui.cli import app
from mcptui.config import save_to_local_mcp_json, remove_from_local_mcp_json
from mcptui.models import ServerConfig


class TestCLIAndConfig(unittest.TestCase):
    def setUp(self):
        self.runner = CliRunner()

    def test_cli_help(self):
        result = self.runner.invoke(app, ["--help"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Postman for Model Context Protocol", result.output)

    def test_cli_list_demo(self):
        result = self.runner.invoke(app, ["list", "demo"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("calculate", result.output)
        self.assertIn("weather", result.output)
        self.assertIn("system_info", result.output)

    def test_cli_call_demo_calculate(self):
        result = self.runner.invoke(app, ["call", "calculate", '{"expression": "7 * 6"}', "--server", "demo"])
        self.assertEqual(result.exit_code, 0)
        data = json.loads(result.output)
        self.assertIn("42", data["content"][0]["text"])

    def test_save_and_remove_local_config(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            cfg_path = Path(tmp_dir) / "mcp.json"
            cfg = ServerConfig(
                name="test-server",
                transport="stdio",
                command="python",
                args=["app.py"],
            )

            # Test save
            save_to_local_mcp_json(cfg, path=cfg_path)
            self.assertTrue(cfg_path.is_file())
            content = json.loads(cfg_path.read_text(encoding="utf-8"))
            self.assertIn("test-server", content["mcpServers"])
            self.assertEqual(content["mcpServers"]["test-server"]["command"], "python")

            # Test remove
            removed = remove_from_local_mcp_json("test-server", path=cfg_path)
            self.assertTrue(removed)
            content_after = json.loads(cfg_path.read_text(encoding="utf-8"))
            self.assertNotIn("test-server", content_after["mcpServers"])


if __name__ == "__main__":
    unittest.main()
