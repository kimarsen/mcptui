import os
import tempfile
import unittest
from pathlib import Path

from mcptui.env import (
    apply_env_to_config,
    find_dotenv,
    load_env_file,
    parse_cli_env_args,
    parse_env_text,
)
from mcptui.models import ServerConfig


class TestEnvParser(unittest.TestCase):
    def test_parse_basic_and_comments(self):
        env_content = """
        # Global settings
        PORT=8080
        HOST=localhost
        DEBUG=true
        
        # Inline comment
        TIMEOUT=30 # seconds
        """
        parsed = parse_env_text(env_content)
        self.assertEqual(parsed.get("PORT"), "8080")
        self.assertEqual(parsed.get("HOST"), "localhost")
        self.assertEqual(parsed.get("DEBUG"), "true")
        self.assertEqual(parsed.get("TIMEOUT"), "30")

    def test_parse_export_prefix(self):
        env_content = """
        export API_KEY=secret_token_123
        export DB_USER=admin
        """
        parsed = parse_env_text(env_content)
        self.assertEqual(parsed.get("API_KEY"), "secret_token_123")
        self.assertEqual(parsed.get("DB_USER"), "admin")

    def test_parse_quotes_and_escapes(self):
        env_content = r'''
        DOUBLE_QUOTED="hello world"
        WITH_HASH="value # not comment"
        WITH_ESCAPES="line1\nline2\ttab\"quoted\""
        SINGLE_QUOTED='literal \n string # not comment'
        '''
        parsed = parse_env_text(env_content)
        self.assertEqual(parsed.get("DOUBLE_QUOTED"), "hello world")
        self.assertEqual(parsed.get("WITH_HASH"), "value # not comment")
        self.assertEqual(parsed.get("WITH_ESCAPES"), "line1\nline2\ttab\"quoted\"")
        self.assertEqual(parsed.get("SINGLE_QUOTED"), r"literal \n string # not comment")

    def test_parse_multiline_quotes(self):
        env_content = """
        MULTI_DOUBLE="first line
second line
third line"
        MULTI_SINGLE='part a
part b'
        """
        parsed = parse_env_text(env_content)
        self.assertEqual(parsed.get("MULTI_DOUBLE"), "first line\nsecond line\nthird line")
        self.assertEqual(parsed.get("MULTI_SINGLE"), "part a\npart b")

    def test_parse_cli_env_args(self):
        cli_args = ["FOO=bar", "NUM=42", "TEST_KEY=hello=world"]
        parsed = parse_cli_env_args(cli_args)
        self.assertEqual(parsed, {"FOO": "bar", "NUM": "42", "TEST_KEY": "hello=world"})

        # Test key without '=' inheriting from os.environ
        os.environ["SYS_VAR_TEST"] = "present"
        try:
            parsed_inherited = parse_cli_env_args(["SYS_VAR_TEST", "MISSING_VAR"])
            self.assertEqual(parsed_inherited.get("SYS_VAR_TEST"), "present")
            self.assertEqual(parsed_inherited.get("MISSING_VAR"), "")
        finally:
            os.environ.pop("SYS_VAR_TEST", None)

    def test_load_env_file_and_apply(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            env_file = Path(tmp_dir) / ".env"
            env_file.write_text("ENV_FILE_KEY=from_file\nOVERRIDE_ME=old\n", encoding="utf-8")

            # Load directly
            loaded = load_env_file(env_file)
            self.assertEqual(loaded.get("ENV_FILE_KEY"), "from_file")

            # Apply to ServerConfig
            cfg = ServerConfig(
                name="test",
                transport="stdio",
                command="python",
                env={"EXISTING": "base", "OVERRIDE_ME": "base_val"},
            )

            apply_env_to_config(
                cfg,
                env_file=env_file,
                cli_env=["OVERRIDE_ME=cli_winner", "NEW_CLI=1"],
            )

            self.assertEqual(cfg.env["EXISTING"], "base")
            self.assertEqual(cfg.env["ENV_FILE_KEY"], "from_file")
            # CLI has highest priority over file and existing
            self.assertEqual(cfg.env["OVERRIDE_ME"], "cli_winner")
            self.assertEqual(cfg.env["NEW_CLI"], "1")


if __name__ == "__main__":
    unittest.main()
