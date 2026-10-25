import asyncio
import json
from datetime import datetime
import unittest

from mcptui.models import CallRecord, ServerConfig
from mcptui.ui.app import MCPTuiApp
from mcptui.ui.views.history_view import HistoryView
from mcptui.ui.views.tools_view import ToolsView
from textual.widgets import DataTable, Input, TextArea


class TestHistoryReplayAndSearch(unittest.IsolatedAsyncioTestCase):
    async def test_history_search_and_replay(self):
        config = ServerConfig(
            name="demo-history-test",
            transport="inmemory",
            source="built-in demo",
        )
        app = MCPTuiApp(initial_config=config)

        async with app.run_test() as pilot:
            await pilot.pause(0.5)
            self.assertTrue(app.client.is_connected)

            # Populate client history with synthetic records
            now = datetime.now()
            rec1 = CallRecord(
                id="rec-1",
                timestamp=now,
                kind="tool",
                name="calculate",
                input_data={"expression": "99 + 1"},
                output_data={"result": 100},
                is_error=False,
                duration_ms=12.5,
            )
            rec2 = CallRecord(
                id="rec-2",
                timestamp=now,
                kind="tool",
                name="weather",
                input_data={"city": "Tokyo"},
                output_data={},
                is_error=True,
                duration_ms=45.0,
                error_message="City not found",
            )
            app.client.history.extend([rec1, rec2])

            # Switch to History tab
            tabs = app.query_one("#tabs")
            tabs.active = "tab-history"
            await pilot.pause(0.3)

            history_view = app.query_one("#history-view", HistoryView)
            table = history_view.query_one("#history-table", DataTable)
            self.assertEqual(table.row_count, 2)

            # Test live filtering by tool name 'Tokyo' in arguments
            search_input = history_view.query_one("#history-search", Input)
            search_input.value = "Tokyo"
            await pilot.pause(0.2)
            self.assertEqual(table.row_count, 1)

            # Test filtering by status 'ok'
            search_input.value = "ok"
            await pilot.pause(0.2)
            self.assertEqual(table.row_count, 1)

            # Clear search
            search_input.value = ""
            await pilot.pause(0.2)
            self.assertEqual(table.row_count, 2)

            # Replay rec1 (calculate with expression "99 + 1")
            history_view.selected_record_id = "rec-1"
            history_view.action_replay_current()
            await pilot.pause(0.3)

            # Check that tab switched to tab-tools
            self.assertEqual(tabs.active, "tab-tools")
            tools_view = app.query_one("#tools-view", ToolsView)
            editor = tools_view.query_one("#tool-params-editor", TextArea)
            loaded_json = json.loads(editor.text)
            self.assertEqual(loaded_json.get("expression"), "99 + 1")
            self.assertEqual(tools_view.current_tool_name, "calculate")

            await app.client.disconnect()


if __name__ == "__main__":
    unittest.main()
