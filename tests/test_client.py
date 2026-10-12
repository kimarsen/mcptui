import asyncio
import sys
import unittest
from mcptui.client import MCPClientManager
from mcptui.models import ServerConfig


class TestMCPClient(unittest.TestCase):
    def test_client_with_demo_server(self):
        async def run_test():
            client = MCPClientManager()
            config = ServerConfig(
                name="demo-test",
                transport="stdio",
                command=sys.executable,
                args=["-m", "mcptui.demo_server"],
            )

            captured_logs = []
            client.set_log_callback(lambda msg: captured_logs.append(msg))

            try:
                await client.connect(config)
                self.assertTrue(client.is_connected)
                self.assertEqual(client.server_name, "mcptui-demo")

                # Test tools discovery
                tool_names = [t.name for t in client.tools]
                self.assertIn("calculate", tool_names)
                self.assertIn("weather", tool_names)
                self.assertIn("system_info", tool_names)

                # Test tool execution
                call_rec = await client.call_tool("calculate", {"expression": "100 * 2 + 42"})
                self.assertFalse(call_rec.is_error)
                self.assertGreater(call_rec.duration_ms, 0)
                output = call_rec.output_data["content"][0]["text"]
                self.assertIn("242", output)

                # Test resources discovery and reading
                resource_uris = [r.uri for r in client.resources]
                self.assertIn("help://quickstart.md", resource_uris)
                res_rec = await client.read_resource("help://quickstart.md")
                self.assertFalse(res_rec.is_error)
                self.assertIn("mcptui", res_rec.output_data["contents"][0]["text"])

                # Test prompts
                prompt_names = [p.name for p in client.prompts]
                self.assertIn("code_review", prompt_names)
                prompt_rec = await client.get_prompt("code_review", {"language": "python", "code": "def foo(): pass"})
                self.assertFalse(prompt_rec.is_error)

                # Check intercepted JSON-RPC protocol logs
                self.assertGreater(len(captured_logs), 0)
                self.assertGreater(len(client.protocol_logs), 0)
                self.assertGreater(len(client.history), 0)

            finally:
                await client.disconnect()
                self.assertFalse(client.is_connected)

        asyncio.run(run_test())


if __name__ == "__main__":
    unittest.main()
