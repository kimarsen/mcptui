"""
Automated Test Runner & Protocol Health Checker for Model Context Protocol (MCP) servers.
Validates protocol compliance, schema correctness, resource accessibility, and benchmark latency.
Usable both programmatically, in CI/CD pipelines, and inside the mcptui TUI.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from mcptui.client import MCPClientManager
from mcptui.models import ServerConfig

CheckStatus = Literal["pass", "fail", "warn", "info"]

TOOL_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_\.\-]+$")
VALID_JSON_SCHEMA_TYPES = {"string", "number", "integer", "boolean", "array", "object", "null"}


@dataclass
class CheckResult:
    """Result of an individual check."""
    category: str  # "protocol", "tools", "resources", "prompts", "benchmark"
    name: str
    status: CheckStatus
    message: str
    duration_ms: float = 0.0
    details: Optional[Dict[str, Any]] = None


@dataclass
class SuiteReport:
    """Overall test suite report."""
    server_name: str
    server_version: str
    protocol_version: str
    target: str
    timestamp: str
    total_checks: int
    passed: int
    failed: int
    warnings: int
    handshake_ms: float
    pings: List[float]
    avg_ping_ms: float
    min_ping_ms: float
    max_ping_ms: float
    checks: List[CheckResult]
    is_success: bool
    summary_message: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def validate_tool_schema(tool: Any) -> List[CheckResult]:
    """Validate tool name, description, and inputSchema against MCP standards."""
    results: List[CheckResult] = []
    name = getattr(tool, "name", "") or ""

    # 1. Name check
    if not name:
        results.append(CheckResult(
            category="tools",
            name="Tool Name",
            status="fail",
            message="Tool name is missing or empty.",
        ))
        return results

    if not TOOL_NAME_PATTERN.match(name):
        results.append(CheckResult(
            category="tools",
            name=f"Tool '{name}' Name Format",
            status="warn",
            message=f"Tool name '{name}' contains special characters outside [a-zA-Z0-9_.-].",
        ))
    else:
        results.append(CheckResult(
            category="tools",
            name=f"Tool '{name}' Identifier",
            status="pass",
            message="Valid tool name format.",
        ))

    # 2. Description check
    description = getattr(tool, "description", None)
    if not description or len(description.strip()) == 0:
        results.append(CheckResult(
            category="tools",
            name=f"Tool '{name}' Description",
            status="warn",
            message="Missing description. LLMs (Claude, Cursor) rely heavily on tool descriptions to decide when to invoke tools.",
        ))
    elif len(description.strip()) < 10:
        results.append(CheckResult(
            category="tools",
            name=f"Tool '{name}' Description",
            status="info",
            message=f"Very brief description ({len(description.strip())} chars). Detailed descriptions improve LLM tool usage.",
        ))
    else:
        results.append(CheckResult(
            category="tools",
            name=f"Tool '{name}' Description",
            status="pass",
            message=f"Description present ({len(description.strip())} chars).",
        ))

    # 3. inputSchema check
    raw_schema = getattr(tool, "input_schema", None) or getattr(tool, "inputSchema", None)
    if raw_schema is None:
        results.append(CheckResult(
            category="tools",
            name=f"Tool '{name}' inputSchema",
            status="fail",
            message="Tool inputSchema is missing.",
        ))
        return results

    if not isinstance(raw_schema, dict):
        results.append(CheckResult(
            category="tools",
            name=f"Tool '{name}' inputSchema",
            status="fail",
            message=f"inputSchema must be a dictionary/object, got {type(raw_schema).__name__}.",
        ))
        return results

    schema_type = raw_schema.get("type")
    if schema_type != "object":
        results.append(CheckResult(
            category="tools",
            name=f"Tool '{name}' Schema Root Type",
            status="fail",
            message=f"inputSchema.type must be 'object', got '{schema_type}'.",
        ))
    else:
        results.append(CheckResult(
            category="tools",
            name=f"Tool '{name}' Schema Root",
            status="pass",
            message="inputSchema.type is 'object'.",
        ))

    properties = raw_schema.get("properties")
    if properties is not None and not isinstance(properties, dict):
        results.append(CheckResult(
            category="tools",
            name=f"Tool '{name}' Schema Properties",
            status="fail",
            message="inputSchema.properties must be a dictionary of property definitions.",
        ))
    elif properties is not None:
        # Validate individual properties
        prop_errors = []
        for prop_name, prop_def in properties.items():
            if not isinstance(prop_def, dict):
                prop_errors.append(f"Property '{prop_name}' definition must be an object.")
                continue

            prop_type = prop_def.get("type")
            has_composite = any(k in prop_def for k in ("anyOf", "oneOf", "allOf", "$ref", "enum"))

            if not prop_type and not has_composite:
                prop_errors.append(f"Property '{prop_name}' specifies neither 'type' nor composite schema (anyOf/oneOf/enum).")
            elif prop_type and prop_type not in VALID_JSON_SCHEMA_TYPES:
                prop_errors.append(f"Property '{prop_name}' has unrecognized type '{prop_type}'.")

            if prop_type == "array" and "items" not in prop_def:
                results.append(CheckResult(
                    category="tools",
                    name=f"Tool '{name}' Array Property '{prop_name}'",
                    status="warn",
                    message=f"Array property '{prop_name}' should specify 'items' schema.",
                ))

        if prop_errors:
            results.append(CheckResult(
                category="tools",
                name=f"Tool '{name}' Properties Validation",
                status="fail",
                message="; ".join(prop_errors),
            ))
        else:
            results.append(CheckResult(
                category="tools",
                name=f"Tool '{name}' Properties Definition",
                status="pass",
                message=f"Validated {len(properties)} input properties.",
            ))

    # Required fields check
    required = raw_schema.get("required")
    if required is not None:
        if not isinstance(required, list) or not all(isinstance(r, str) for r in required):
            results.append(CheckResult(
                category="tools",
                name=f"Tool '{name}' Schema Required",
                status="fail",
                message="inputSchema.required must be an array of property name strings.",
            ))
        elif properties is not None and isinstance(properties, dict):
            missing_props = [r for r in required if r not in properties]
            if missing_props:
                results.append(CheckResult(
                    category="tools",
                    name=f"Tool '{name}' Required Mismatch",
                    status="fail",
                    message=f"Properties in 'required' not defined in 'properties': {missing_props}.",
                ))
            else:
                results.append(CheckResult(
                    category="tools",
                    name=f"Tool '{name}' Required Fields",
                    status="pass",
                    message=f"{len(required)} required field(s) verified.",
                ))

    return results


def validate_resource(res: Any) -> List[CheckResult]:
    """Validate resource URI and metadata."""
    results: List[CheckResult] = []
    uri = str(getattr(res, "uri", "")) or ""
    name = getattr(res, "name", None) or uri

    if not uri:
        results.append(CheckResult(
            category="resources",
            name="Resource URI",
            status="fail",
            message="Resource URI is missing or empty.",
        ))
        return results

    if "://" not in uri:
        results.append(CheckResult(
            category="resources",
            name=f"Resource '{name}' URI Scheme",
            status="warn",
            message=f"Resource URI '{uri}' does not contain standard scheme separator '://'.",
        ))
    else:
        results.append(CheckResult(
            category="resources",
            name=f"Resource '{name}' URI",
            status="pass",
            message=f"Valid URI: {uri}",
        ))

    mime_type = getattr(res, "mime_type", None) or getattr(res, "mimeType", None)
    if mime_type:
        results.append(CheckResult(
            category="resources",
            name=f"Resource '{name}' MIME",
            status="pass",
            message=f"MIME type declared: {mime_type}",
        ))
    else:
        results.append(CheckResult(
            category="resources",
            name=f"Resource '{name}' MIME",
            status="info",
            message="No explicit MIME type specified.",
        ))

    return results


def validate_resource_template(tmpl: Any) -> List[CheckResult]:
    """Validate resource template format."""
    results: List[CheckResult] = []
    uri_pattern = getattr(tmpl, "uri_template", None) or getattr(tmpl, "uriTemplate", None) or ""
    name = getattr(tmpl, "name", None) or uri_pattern

    if not uri_pattern:
        results.append(CheckResult(
            category="resources",
            name="Resource Template",
            status="fail",
            message="Resource template URI pattern is missing.",
        ))
        return results

    if "{" not in uri_pattern or "}" not in uri_pattern:
        results.append(CheckResult(
            category="resources",
            name=f"Template '{name}' Pattern",
            status="warn",
            message=f"Resource template '{uri_pattern}' does not contain variable placeholders like '{{param}}'.",
        ))
    else:
        results.append(CheckResult(
            category="resources",
            name=f"Template '{name}' Pattern",
            status="pass",
            message=f"Valid template pattern: {uri_pattern}",
        ))

    return results


def validate_prompt(prompt: Any) -> List[CheckResult]:
    """Validate prompt template definition."""
    results: List[CheckResult] = []
    name = getattr(prompt, "name", "") or ""

    if not name:
        results.append(CheckResult(
            category="prompts",
            name="Prompt Name",
            status="fail",
            message="Prompt name is missing or empty.",
        ))
        return results

    results.append(CheckResult(
        category="prompts",
        name=f"Prompt '{name}' Identifier",
        status="pass",
        message="Valid prompt identifier.",
    ))

    desc = getattr(prompt, "description", None)
    if not desc:
        results.append(CheckResult(
            category="prompts",
            name=f"Prompt '{name}' Description",
            status="warn",
            message="Missing description for prompt template.",
        ))
    else:
        results.append(CheckResult(
            category="prompts",
            name=f"Prompt '{name}' Description",
            status="pass",
            message="Description present.",
        ))

    arguments = getattr(prompt, "arguments", None)
    if arguments is not None and isinstance(arguments, list):
        for arg in arguments:
            arg_name = getattr(arg, "name", "") or ""
            if not arg_name:
                results.append(CheckResult(
                    category="prompts",
                    name=f"Prompt '{name}' Argument",
                    status="fail",
                    message="Prompt argument is missing 'name'.",
                ))

    return results


async def run_server_tests(
    config: ServerConfig,
    client: Optional[MCPClientManager] = None,
    pings: int = 3,
    timeout_sec: float = 12.0,
    strict: bool = False,
    smoke_read_resources: bool = True,
) -> SuiteReport:
    """
    Connect to an MCP server, run all compliance & health checks, benchmark latency, and return SuiteReport.
    """
    checks: List[CheckResult] = []
    target_str = config.display_target()
    timestamp_str = datetime.now().isoformat()

    owns_client = client is None
    m_client = client or MCPClientManager()

    handshake_ms = 0.0
    ping_latencies: List[float] = []

    try:
        t0 = time.perf_counter()
        # Connect with timeout
        connect_task = m_client.connect(config)
        await asyncio.wait_for(connect_task, timeout=timeout_sec)
        handshake_ms = (time.perf_counter() - t0) * 1000.0

        checks.append(CheckResult(
            category="protocol",
            name="Connection & Handshake",
            status="pass",
            message=f"Connected and initialized in {handshake_ms:.1f}ms.",
            duration_ms=round(handshake_ms, 2),
        ))

        # Check Server Info
        srv_name = m_client.server_name or config.name
        srv_ver = m_client.server_version or "unspecified"
        if m_client.server_name:
            checks.append(CheckResult(
                category="protocol",
                name="Server Info",
                status="pass",
                message=f"Server: '{srv_name}' (v{srv_ver}).",
            ))
        else:
            checks.append(CheckResult(
                category="protocol",
                name="Server Info",
                status="warn",
                message="Server did not advertise server_info.name in initialize result.",
            ))

        # Check Protocol Version
        proto_ver = getattr(m_client, "protocol_version", "") or "unspecified"
        checks.append(CheckResult(
            category="protocol",
            name="Protocol Version",
            status="pass",
            message=f"Negotiated protocol version: {proto_ver}.",
        ))

        # Check Instructions
        if m_client.instructions:
            checks.append(CheckResult(
                category="protocol",
                name="System Instructions",
                status="info",
                message=f"Server provided system instructions ({len(m_client.instructions)} chars).",
            ))

        # ----------------------------------------------------
        # Tools Verification
        # ----------------------------------------------------
        tools = m_client.tools
        checks.append(CheckResult(
            category="tools",
            name="Tools Capability",
            status="pass" if tools else "info",
            message=f"Discovered {len(tools)} tool(s).",
        ))
        for t in tools:
            checks.extend(validate_tool_schema(t))

        # ----------------------------------------------------
        # Resources Verification
        # ----------------------------------------------------
        resources = m_client.resources
        templates = m_client.resource_templates
        checks.append(CheckResult(
            category="resources",
            name="Resources Capability",
            status="pass" if (resources or templates) else "info",
            message=f"Discovered {len(resources)} static resource(s) and {len(templates)} template(s).",
        ))
        for r in resources:
            checks.extend(validate_resource(r))
        for tmpl in templates:
            checks.extend(validate_resource_template(tmpl))

        # Smoke check: Read first resource if available
        if smoke_read_resources and resources and m_client.session:
            first_res = resources[0]
            first_uri = str(first_res.uri)
            try:
                t_res_start = time.perf_counter()
                rec = await m_client.read_resource(first_uri)
                res_dur = (time.perf_counter() - t_res_start) * 1000.0
                if rec.is_error:
                    checks.append(CheckResult(
                        category="resources",
                        name=f"Smoke Read '{first_uri}'",
                        status="warn",
                        message=f"Read failed: {rec.error_message or 'Unknown error'}",
                        duration_ms=round(res_dur, 2),
                    ))
                else:
                    checks.append(CheckResult(
                        category="resources",
                        name=f"Smoke Read '{first_uri}'",
                        status="pass",
                        message=f"Successfully read resource in {res_dur:.1f}ms.",
                        duration_ms=round(res_dur, 2),
                    ))
            except Exception as read_exc:
                checks.append(CheckResult(
                    category="resources",
                    name=f"Smoke Read '{first_uri}'",
                    status="warn",
                    message=f"Read exception: {read_exc}",
                ))

        # ----------------------------------------------------
        # Prompts Verification
        # ----------------------------------------------------
        prompts = m_client.prompts
        checks.append(CheckResult(
            category="prompts",
            name="Prompts Capability",
            status="pass" if prompts else "info",
            message=f"Discovered {len(prompts)} prompt template(s).",
        ))
        for p in prompts:
            checks.extend(validate_prompt(p))

        # ----------------------------------------------------
        # Benchmark & Ping Latency
        # ----------------------------------------------------
        if m_client.session and pings > 0:
            for i in range(pings):
                t_ping = time.perf_counter()
                try:
                    # Prefer native ping if supported by session
                    if hasattr(m_client.session, "send_ping"):
                        await m_client.session.send_ping()
                    else:
                        await m_client.session.list_tools()
                    dur_ms = (time.perf_counter() - t_ping) * 1000.0
                    ping_latencies.append(dur_ms)
                except Exception:
                    pass

            if ping_latencies:
                avg_p = sum(ping_latencies) / len(ping_latencies)
                min_p = min(ping_latencies)
                max_p = max(ping_latencies)

                if avg_p < 10.0:
                    perf_desc = "⚡ Ultra Fast (<10ms)"
                elif avg_p < 50.0:
                    perf_desc = "Fast (<50ms)"
                elif avg_p < 200.0:
                    perf_desc = "Acceptable (<200ms)"
                else:
                    perf_desc = "High latency (>200ms)"

                checks.append(CheckResult(
                    category="benchmark",
                    name="Protocol Roundtrip Latency",
                    status="pass" if avg_p < 200.0 else "warn",
                    message=f"{pings} roundtrips: avg {avg_p:.2f}ms (min {min_p:.2f}ms, max {max_p:.2f}ms) — {perf_desc}.",
                    duration_ms=round(avg_p, 2),
                ))

    except asyncio.TimeoutError:
        checks.append(CheckResult(
            category="protocol",
            name="Connection Timeout",
            status="fail",
            message=f"Connection timed out after {timeout_sec:.1f}s. Server failed to complete initialize handshake.",
        ))
    except Exception as exc:
        checks.append(CheckResult(
            category="protocol",
            name="Connection Error",
            status="fail",
            message=f"Connection failed: {exc}",
        ))
    finally:
        if owns_client:
            await m_client.disconnect()

    # Summarize
    passed = sum(1 for c in checks if c.status == "pass")
    failed = sum(1 for c in checks if c.status == "fail")
    warnings = sum(1 for c in checks if c.status == "warn")
    total = len(checks)

    is_success = (failed == 0) if not strict else (failed == 0 and warnings == 0)

    avg_ping = round(sum(ping_latencies) / len(ping_latencies), 2) if ping_latencies else 0.0
    min_ping = round(min(ping_latencies), 2) if ping_latencies else 0.0
    max_ping = round(max(ping_latencies), 2) if ping_latencies else 0.0

    if is_success and failed == 0 and warnings == 0:
        summary_msg = "All checks passed! Server is 100% compliant and ready for Claude Desktop / Cursor / Cline."
    elif is_success and warnings > 0:
        summary_msg = f"Checks passed with {warnings} warning(s). Server is functional but has optimization opportunities."
    else:
        summary_msg = f"FAILED: {failed} check(s) failed. Fix reported errors before connecting to LLM clients."

    return SuiteReport(
        server_name=m_client.server_name or config.name,
        server_version=m_client.server_version or "",
        protocol_version=getattr(m_client, "protocol_version", "") or "unspecified",
        target=target_str,
        timestamp=timestamp_str,
        total_checks=total,
        passed=passed,
        failed=failed,
        warnings=warnings,
        handshake_ms=round(handshake_ms, 2),
        pings=[round(p, 2) for p in ping_latencies],
        avg_ping_ms=avg_ping,
        min_ping_ms=min_ping,
        max_ping_ms=max_ping,
        checks=checks,
        is_success=is_success,
        summary_message=summary_msg,
    )


def render_report_rich(report: SuiteReport, console: Console) -> None:
    """Print a polished test report table and summary banner to the console."""
    console.print()

    # Header Panel
    title_text = Text()
    title_text.append("🧪 mcptui test", style="bold cyan")
    title_text.append(" — MCP Server Compliance & Health Checker\n", style="bold white")
    title_text.append(f"Target: {report.target}  |  Server: {report.server_name} ({report.server_version or 'v?'})  |  Protocol: {report.protocol_version}", style="dim")

    console.print(Panel(title_text, border_style="cyan"))

    # Table of checks
    table = Table(show_header=True, header_style="bold cyan", border_style="dim", box=None)
    table.add_column("Status", width=10)
    table.add_column("Category", width=12, style="dim")
    table.add_column("Check", width=34, style="bold white")
    table.add_column("Message / Diagnostic")

    status_styles = {
        "pass": ("[bold green]✓ PASS[/bold green]", "green"),
        "fail": ("[bold red]✗ FAIL[/bold red]", "red"),
        "warn": ("[bold yellow]⚠ WARN[/bold yellow]", "yellow"),
        "info": ("[bold blue]ℹ INFO[/bold blue]", "blue"),
    }

    for c in report.checks:
        badge, color = status_styles.get(c.status, (c.status.upper(), "white"))
        table.add_row(badge, c.category.upper(), c.name, f"[{color}]{c.message}[/{color}]")

    console.print(table)
    console.print()

    # Summary bar
    summary_color = "bold green" if report.is_success and report.failed == 0 else "bold red"
    border_color = "green" if report.is_success and report.failed == 0 else "red"

    verdict_text = Text()
    verdict_text.append(f"Result: {report.passed}/{report.total_checks} passed", style=summary_color)
    if report.warnings:
        verdict_text.append(f", {report.warnings} warning(s)", style="yellow")
    if report.failed:
        verdict_text.append(f", {report.failed} failed", style="bold red")

    verdict_text.append(f"  |  Handshake: {report.handshake_ms}ms  |  Avg Ping: {report.avg_ping_ms}ms\n", style="dim")
    verdict_text.append(f"{report.summary_message}", style="bold white" if report.is_success else "bold red")

    console.print(Panel(verdict_text, border_style=border_color))
    console.print()


def render_report_json(report: SuiteReport) -> str:
    """Serialize report to JSON for CI/CD integration."""
    return json.dumps(report.to_dict(), indent=2, ensure_ascii=False)
