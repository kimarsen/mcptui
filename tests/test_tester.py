import json
import unittest
from typer.testing import CliRunner

from mcptui.cli import app, get_demo_config
from mcptui.tester import (
    CheckResult,
    run_server_tests,
    validate_prompt,
    validate_resource,
    validate_resource_template,
    validate_tool_schema,
)


class MockTool:
    def __init__(self, name, description, input_schema):
        self.name = name
        self.description = description
        self.input_schema = input_schema


class MockResource:
    def __init__(self, uri, name, mime_type=None):
        self.uri = uri
        self.name = name
        self.mime_type = mime_type


class MockResourceTemplate:
    def __init__(self, uri_template, name):
        self.uri_template = uri_template
        self.name = name


class MockPrompt:
    def __init__(self, name, description, arguments=None):
        self.name = name
        self.description = description
        self.arguments = arguments or []


class TestServerTester(unittest.IsolatedAsyncioTestCase):
    async def test_demo_server_compliance(self):
        cfg = get_demo_config()
        report = await run_server_tests(cfg, pings=2, timeout_sec=10.0)

        self.assertTrue(report.is_success)
        self.assertEqual(report.failed, 0)
        self.assertGreaterEqual(report.passed, 30)
        self.assertEqual(report.server_name, "mcptui-demo")
        self.assertGreater(report.avg_ping_ms, 0)
        self.assertGreater(len(report.checks), 0)

    def test_validate_tool_schema_valid(self):
        tool = MockTool(
            name="query_db",
            description="Execute SQL query against database safely.",
            input_schema={
                "type": "object",
                "properties": {
                    "sql": {"type": "string", "description": "SQL statement"},
                    "limit": {"type": "integer", "description": "Max rows"},
                },
                "required": ["sql"],
            },
        )
        checks = validate_tool_schema(tool)
        fails = [c for c in checks if c.status == "fail"]
        self.assertEqual(len(fails), 0)

    def test_validate_tool_schema_invalid_type(self):
        # inputSchema is not 'object'
        tool = MockTool(
            name="bad_tool",
            description="Does something",
            input_schema={"type": "string"},
        )
        checks = validate_tool_schema(tool)
        fails = [c for c in checks if c.status == "fail"]
        self.assertGreater(len(fails), 0)
        self.assertIn("must be 'object'", fails[0].message)

    def test_validate_tool_schema_missing_required(self):
        # 'required' refers to a non-existent property
        tool = MockTool(
            name="missing_req",
            description="Has nonexistent required field",
            input_schema={
                "type": "object",
                "properties": {"foo": {"type": "string"}},
                "required": ["bar"],
            },
        )
        checks = validate_tool_schema(tool)
        fails = [c for c in checks if c.status == "fail"]
        self.assertGreater(len(fails), 0)
        self.assertIn("not defined in 'properties'", fails[0].message)

    def test_validate_resource(self):
        valid_res = MockResource("system://info", "System Specs", "application/json")
        checks = validate_resource(valid_res)
        fails = [c for c in checks if c.status == "fail"]
        self.assertEqual(len(fails), 0)

        bad_res = MockResource("", "No URI")
        checks = validate_resource(bad_res)
        fails = [c for c in checks if c.status == "fail"]
        self.assertGreater(len(fails), 0)

    def test_validate_prompt(self):
        valid_prompt = MockPrompt("greet", "Generate greeting")
        checks = validate_prompt(valid_prompt)
        fails = [c for c in checks if c.status == "fail"]
        self.assertEqual(len(fails), 0)

    def test_cli_test_command_json(self):
        runner = CliRunner()
        result = runner.invoke(app, ["test", "demo", "--json"])
        self.assertEqual(result.exit_code, 0)
        data = json.loads(result.output)
        self.assertTrue(data["is_success"])
        self.assertEqual(data["server_name"], "mcptui-demo")
        self.assertGreater(data["passed"], 20)


if __name__ == "__main__":
    unittest.main()
