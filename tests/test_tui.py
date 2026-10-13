import asyncio
import sys
import unittest
from mcptui.models import ServerConfig
from mcptui.ui.app import MCPTuiApp
from mcptui.ui.views.resources_view import ResourcesView
from mcptui.ui.views.tools_view import ToolsView
from textual.widgets import TextArea


class TestTUIApp(unittest.IsolatedAsyncioTestCase):
    async def test_tui_app_lifecycle(self):
        config = ServerConfig(
            name="demo-tui-test",
            transport="stdio",
            command=sys.executable,
            args=["-m", "mcptui.demo_server"],
        )
        app = MCPTuiApp(initial_config=config)

        async with app.run_test() as pilot:
            # Wait for connection worker
            await pilot.pause(1.5)

            # Check that client is connected
            self.assertTrue(app.client.is_connected)
            self.assertEqual(app.client.server_name, "mcptui-demo")

            # Check tools view
            tools_view = app.query_one("#tools-view", ToolsView)
            self.assertGreater(len(tools_view._all_tool_names), 0)

            # Provide valid expression
            editor = tools_view.query_one("#tool-params-editor", TextArea)
            editor.text = '{"expression": "10 * 5"}'
            await tools_view.execute_current_tool()
            await pilot.pause(0.5)

            # Verify history has 1 record
            self.assertGreater(len(app.client.history), 0)

            # Switch tabs to Resources
            tabs = app.query_one("#tabs")
            tabs.active = "tab-resources"
            await pilot.pause(0.5)

            # Check resources view and test double-click on resource title
            resources_view = app.query_one("#resources-view", ResourcesView)
            self.assertGreater(len(resources_view._all_uris), 0)

            await pilot.double_click("#res-title")
            await pilot.pause(1.0)

            res_viewer = resources_view.query_one("#res-content-viewer", TextArea)
            self.assertIn("python", res_viewer.text)

            # Switch tabs to Protocol Logs
            tabs.active = "tab-logs"
            await pilot.pause(0.3)

            # Verify logs were captured
            self.assertGreater(len(app.client.protocol_logs), 0)

            # Disconnect
            await app.client.disconnect()


if __name__ == "__main__":
    unittest.main()
