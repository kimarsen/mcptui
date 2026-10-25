"""
Zero-dependency .env parser and environment variable loader for mcptui.
Supports single & double quotes, escape sequences, inline comments, and export prefix.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Optional, Union

from mcptui.models import ServerConfig


def parse_env_text(text: str) -> Dict[str, str]:
    """
    Parse the contents of a .env file into a dictionary of key-value pairs.
    Handles:
      - Leading 'export '
      - Single and double quotes
      - Escaped characters (\\n, \\t, \\r, \\", \\\\) in double quotes
      - Inline comments after unquoted values
      - Full-line comments and empty lines
    """
    env: Dict[str, str] = {}
    lines = text.splitlines()
    i = 0
    n = len(lines)

    while i < n:
        raw_line = lines[i].strip()
        i += 1

        if not raw_line or raw_line.startswith("#"):
            continue

        if raw_line.startswith("export "):
            raw_line = raw_line[7:].strip()

        # Find separator '=' or ':'
        sep_idx = -1
        for idx, ch in enumerate(raw_line):
            if ch in ("=", ":"):
                sep_idx = idx
                break

        if sep_idx == -1:
            continue

        key = raw_line[:sep_idx].strip()
        val = raw_line[sep_idx + 1:].strip()

        if not key:
            continue

        # Handle quoted values
        if val.startswith('"'):
            # Double-quoted
            val_content = val[1:]
            closing_idx = -1
            escaped = False
            for c_idx, ch in enumerate(val_content):
                if escaped:
                    escaped = False
                    continue
                if ch == "\\":
                    escaped = True
                    continue
                if ch == '"':
                    closing_idx = c_idx
                    break

            if closing_idx != -1:
                inner = val_content[:closing_idx]
                inner = (
                    inner.replace('\\"', '"')
                    .replace("\\n", "\n")
                    .replace("\\t", "\t")
                    .replace("\\r", "\r")
                    .replace("\\\\", "\\")
                )
                env[key] = inner
            else:
                # Multiline double quote
                multiline_parts = [val_content]
                while i < n:
                    next_line = lines[i]
                    i += 1
                    closing_idx = -1
                    escaped = False
                    for c_idx, ch in enumerate(next_line):
                        if escaped:
                            escaped = False
                            continue
                        if ch == "\\":
                            escaped = True
                            continue
                        if ch == '"':
                            closing_idx = c_idx
                            break
                    if closing_idx != -1:
                        multiline_parts.append(next_line[:closing_idx])
                        break
                    else:
                        multiline_parts.append(next_line)

                inner = "\n".join(multiline_parts)
                inner = (
                    inner.replace('\\"', '"')
                    .replace("\\n", "\n")
                    .replace("\\t", "\t")
                    .replace("\\r", "\r")
                    .replace("\\\\", "\\")
                )
                env[key] = inner

        elif val.startswith("'"):
            # Single-quoted (literal, no escape processing)
            val_content = val[1:]
            closing_idx = val_content.find("'")
            if closing_idx != -1:
                env[key] = val_content[:closing_idx]
            else:
                # Multiline single quote
                multiline_parts = [val_content]
                while i < n:
                    next_line = lines[i]
                    i += 1
                    closing_idx = next_line.find("'")
                    if closing_idx != -1:
                        multiline_parts.append(next_line[:closing_idx])
                        break
                    else:
                        multiline_parts.append(next_line)
                env[key] = "\n".join(multiline_parts)
        else:
            # Unquoted: strip inline comments if any
            if " #" in val:
                val = val.split(" #", 1)[0].strip()
            elif "\t#" in val:
                val = val.split("\t#", 1)[0].strip()
            env[key] = val

    return env


def find_dotenv(start_dir: Optional[Union[str, Path]] = None) -> Optional[Path]:
    """Find a .env file starting at start_dir and walking up to parent directories."""
    curr = Path(start_dir or Path.cwd()).resolve()
    for directory in [curr, *curr.parents]:
        candidate = directory / ".env"
        if candidate.is_file():
            return candidate
        # Stop search at git root
        if (directory / ".git").exists():
            break
    return None


def load_env_file(
    path: Optional[Union[str, Path]] = None,
    override_environ: bool = False,
) -> Dict[str, str]:
    """
    Load environment variables from a .env file.
    If path is None, looks for a .env file in the current working directory or parents.
    If override_environ is True, also updates os.environ.
    Returns the parsed dictionary.
    """
    if path is not None:
        target_path = Path(path)
        if not target_path.is_file():
            return {}
    else:
        found = find_dotenv()
        if not found:
            return {}
        target_path = found

    try:
        content = target_path.read_text(encoding="utf-8")
        parsed = parse_env_text(content)
        if override_environ:
            for k, v in parsed.items():
                os.environ[k] = v
        return parsed
    except Exception:
        return {}


def parse_cli_env_args(cli_env_list: Optional[List[str]]) -> Dict[str, str]:
    """
    Parse a list of KEY=VALUE strings passed from the CLI (-e / --env).
    """
    res: Dict[str, str] = {}
    if not cli_env_list:
        return res
    for item in cli_env_list:
        if "=" in item:
            k, v = item.split("=", 1)
            res[k.strip()] = v
        else:
            # If only KEY is specified, inherit from existing os.environ if present
            val = os.environ.get(item, "")
            res[item.strip()] = val
    return res


def apply_env_to_config(
    config: ServerConfig,
    env_file: Optional[Union[str, Path]] = None,
    cli_env: Optional[List[str]] = None,
) -> None:
    """
    Merge .env file and CLI environment variables into a ServerConfig instance.
    Precedence: CLI args > .env file > server existing config.
    """
    file_vars = load_env_file(env_file)
    cli_vars = parse_cli_env_args(cli_env)
    config.env = {**config.env, **file_vars, **cli_vars}
