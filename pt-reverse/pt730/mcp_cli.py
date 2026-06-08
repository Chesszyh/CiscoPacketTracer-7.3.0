#!/usr/bin/env python3
"""Minimal MCP stdio server exposing offline Packet Tracer 7.3.0 CLI tools."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any


PROTOCOL_VERSION = "2025-06-18"
SERVER_INFO = {"name": "pt730-mcp", "version": "0.1.0"}


class ToolError(ValueError):
    pass


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def bin_path(root: Path, name: str) -> Path:
    path = root / "pt-reverse" / "bin" / name
    if not path.exists():
        raise ToolError(f"missing CLI tool: {path}")
    return path


def str_arg(args: dict[str, Any], name: str, *, required: bool = True, default: str = "") -> str:
    value = args.get(name, default)
    if value is None or value == "":
        if required:
            raise ToolError(f"missing required argument: {name}")
        return default
    if not isinstance(value, str):
        raise ToolError(f"{name} must be a string")
    return value


def int_arg(args: dict[str, Any], name: str, *, default: int) -> int:
    value = args.get(name, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ToolError(f"{name} must be an integer")
    return value


def bool_arg(args: dict[str, Any], name: str, *, default: bool = False) -> bool:
    value = args.get(name, default)
    if not isinstance(value, bool):
        raise ToolError(f"{name} must be a boolean")
    return value


def enum_arg(args: dict[str, Any], name: str, allowed: set[str], *, default: str | None = None) -> str:
    value = str_arg(args, name, required=default is None, default=default or "")
    if value not in allowed:
        raise ToolError(f"{name} must be one of: {', '.join(sorted(allowed))}")
    return value


def run_cli(root: Path, command: list[str]) -> dict[str, Any]:
    result = subprocess.run(
        command,
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=120,
        check=False,
    )
    return {
        "command": [str(part) for part in command],
        "exitCode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def require_live(args: dict[str, Any], tool_name: str) -> None:
    if not bool_arg(args, "allow_live", default=False):
        raise ToolError(f"{tool_name} requires allow_live=true because it can contact live Packet Tracer")


def content_result(result: dict[str, Any]) -> dict[str, Any]:
    text = result["stdout"] if result["stdout"] else result["stderr"]
    if not text:
        text = f"exitCode={result['exitCode']}"
    return {
        "content": [{"type": "text", "text": text}],
        "structuredContent": result,
        "isError": result["exitCode"] != 0,
    }


def tool_capabilities(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    command = [str(bin_path(root, "pt730-capabilities"))]
    if bool_arg(args, "table", default=False):
        command.append("--table")
    return run_cli(root, command)


def tool_render(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    fmt = enum_arg(args, "format", {"mermaid", "markdown", "summary", "svg", "drawio", "html", "course-audit"})
    command = [str(bin_path(root, "pt730-render"))]
    if bool_arg(args, "strict_safety", default=False):
        command.append("--strict-safety")
    if bool_arg(args, "allow_risky", default=False):
        command.append("--allow-risky")
    command.extend([fmt, str_arg(args, "plan")])
    output = str_arg(args, "output", required=False)
    if output:
        command.extend(["--output", output])
    if fmt == "mermaid":
        direction = enum_arg(args, "direction", {"LR", "TD", "TB", "RL", "BT"}, default="LR")
        command.extend(["--direction", direction])
    return run_cli(root, command)


def tool_safety_plan(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    command = [str(bin_path(root, "pt730-safety")), "plan", str_arg(args, "plan")]
    if bool_arg(args, "strict", default=False):
        command.append("--strict")
    return run_cli(root, command)


def tool_template_lan_star(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    command = [
        str(bin_path(root, "pt730-template")),
        "lan-star",
        "--pcs",
        str(int_arg(args, "pcs", default=4)),
        "--servers",
        str(int_arg(args, "servers", default=0)),
        "--network",
        str_arg(args, "network", required=False, default="192.168.10.0/24"),
    ]
    for key, flag in (("name", "--name"), ("gateway", "--gateway"), ("output", "--output")):
        value = str_arg(args, key, required=False)
        if value:
            command.extend([flag, value])
    return run_cli(root, command)


def tool_template_router_ring(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    command = [
        str(bin_path(root, "pt730-template")),
        "router-ring",
        "--routers",
        str(int_arg(args, "routers", default=4)),
        "--interconnect-pool",
        str_arg(args, "interconnect_pool", required=False, default="10.20.0.0/28"),
    ]
    output = str_arg(args, "output", required=False)
    if output:
        command.extend(["--output", output])
    return run_cli(root, command)


def tool_ip_plan_campus(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    command = [str(bin_path(root, "pt730-ip-plan")), "campus", str_arg(args, "spec")]
    output = str_arg(args, "output", required=False)
    if output:
        command.extend(["--output", output])
    return run_cli(root, command)


def tool_compose_campus(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    command = [str(bin_path(root, "pt730-compose")), "campus", str_arg(args, "spec")]
    ip_plan = str_arg(args, "segments_from_ip_plan", required=False)
    if ip_plan:
        command.extend(["--segments-from-ip-plan", ip_plan])
    if bool_arg(args, "no_layout", default=False):
        command.append("--no-layout")
    layout_style = str_arg(args, "layout_style", required=False)
    if layout_style:
        command.extend(["--layout-style", layout_style])
    output = str_arg(args, "output", required=False)
    if output:
        command.extend(["--output", output])
    return run_cli(root, command)


def tool_config_plan_campus(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    command = [str(bin_path(root, "pt730-config-plan")), "campus", str_arg(args, "plan")]
    if bool_arg(args, "l3", default=False):
        command.append("--l3")
    routing = enum_arg(args, "routing", {"none", "rip", "static"}, default="none")
    command.extend(["--routing", routing])
    output = str_arg(args, "output", required=False)
    if output:
        command.extend(["--output", output])
    return run_cli(root, command)


def tool_export_configs(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    command = [
        str(bin_path(root, "pt730-config-plan")),
        "export-configs",
        str_arg(args, "plan"),
        "--output-dir",
        str_arg(args, "output_dir"),
    ]
    return run_cli(root, command)


def tool_layout(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    command = [str(bin_path(root, "pt730-layout")), str_arg(args, "plan")]
    style = str_arg(args, "style", required=False)
    if style:
        command.extend(["--style", style])
    if bool_arg(args, "preserve_existing", default=False):
        command.append("--preserve-existing")
    output = str_arg(args, "output", required=False)
    if output:
        command.extend(["--output", output])
    return run_cli(root, command)


def tool_ios_template_render(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    command = [str(bin_path(root, "pt730-ios-template")), "render", str_arg(args, "spec")]
    if bool_arg(args, "topology_json", default=False):
        command.append("--topology-json")
    output = str_arg(args, "output", required=False)
    if output:
        command.extend(["--output", output])
    return run_cli(root, command)


def tool_pipeline_campus(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    command = [
        str(bin_path(root, "pt730-pipeline")),
        "campus",
        "--compose-spec",
        str_arg(args, "compose_spec"),
        "--output-dir",
        str_arg(args, "output_dir"),
        "--routing",
        enum_arg(args, "routing", {"none", "rip", "static"}, default="rip"),
    ]
    ip_plan = str_arg(args, "ip_plan", required=False)
    if ip_plan:
        command.extend(["--ip-plan", ip_plan])
    layout_style = str_arg(args, "layout_style", required=False)
    if layout_style:
        command.extend(["--layout-style", layout_style])
    if bool_arg(args, "strict_safety", default=False):
        command.append("--strict-safety")
    if bool_arg(args, "course_audit", default=False):
        command.append("--course-audit")
    return run_cli(root, command)


def tool_live_count(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    require_live(args, "pt730_live_count")
    command = [str(bin_path(root, "pt730-app")), "--timeout", str(int_arg(args, "timeout", default=15)), "count"]
    return run_cli(root, command)


def tool_live_query(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    require_live(args, "pt730_live_query")
    command = [str(bin_path(root, "pt730-topo")), "--timeout", str(int_arg(args, "timeout", default=20)), "query"]
    if bool_arg(args, "summary", default=True):
        command.append("--summary")
    return run_cli(root, command)


def tool_live_apply(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    dry_run = bool_arg(args, "dry_run", default=False)
    if not dry_run:
        require_live(args, "pt730_live_apply")
    command = [str(bin_path(root, "pt730-topo")), "--timeout", str(int_arg(args, "timeout", default=20)), "apply", str_arg(args, "plan")]
    if bool_arg(args, "replace", default=False):
        command.append("--replace")
    batch_size = int_arg(args, "batch_size", default=0)
    if batch_size:
        command.extend(["--batch-size", str(batch_size)])
    if bool_arg(args, "allow_risky", default=False):
        command.append("--allow-risky")
    if bool_arg(args, "strict_safety", default=False):
        command.append("--strict-safety")
    if dry_run:
        command.append("--dry-run")
    return run_cli(root, command)


def tool_live_save_as(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    require_live(args, "pt730_live_save_as")
    command = [str(bin_path(root, "pt730-app")), "--timeout", str(int_arg(args, "timeout", default=15)), "save-as", str_arg(args, "path")]
    if bool_arg(args, "direct", default=False):
        command.append("--direct")
    return run_cli(root, command)


def schema(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required or [], "additionalProperties": False}


def tool(name: str, description: str, input_schema: dict[str, Any], handler: Callable[[Path, dict[str, Any]], dict[str, Any]]) -> dict[str, Any]:
    return {"name": name, "description": description, "inputSchema": input_schema, "handler": handler}


def tools() -> list[dict[str, Any]]:
    string = {"type": "string"}
    boolean = {"type": "boolean"}
    integer = {"type": "integer", "minimum": 0}
    return [
        tool("pt730_capabilities", "Print PT 7.3 automation capabilities.", schema({"table": boolean}), tool_capabilities),
        tool("pt730_render", "Render a topology plan as mermaid, markdown, summary, svg, drawio, html, or course-audit.", schema({"format": {"type": "string", "enum": ["mermaid", "markdown", "summary", "svg", "drawio", "html", "course-audit"]}, "plan": string, "output": string, "direction": {"type": "string", "enum": ["LR", "TD", "TB", "RL", "BT"]}, "strict_safety": boolean, "allow_risky": boolean}, ["format", "plan"]), tool_render),
        tool("pt730_safety_plan", "Check a topology JSON plan offline before live Packet Tracer use.", schema({"plan": string, "strict": boolean}, ["plan"]), tool_safety_plan),
        tool("pt730_template_lan_star", "Generate a router-switch-PC/server star LAN topology JSON.", schema({"name": string, "pcs": integer, "servers": integer, "network": string, "gateway": string, "output": string}), tool_template_lan_star),
        tool("pt730_template_router_ring", "Generate a serial router ring topology JSON with RIP configs.", schema({"routers": integer, "interconnect_pool": string, "output": string}), tool_template_router_ring),
        tool("pt730_ip_plan_campus", "Plan VLSM campus subnets from a compact IP planning spec.", schema({"spec": string, "output": string}, ["spec"]), tool_ip_plan_campus),
        tool("pt730_compose_campus", "Compose a high-level campus topology spec into topology JSON.", schema({"spec": string, "segments_from_ip_plan": string, "no_layout": boolean, "layout_style": string, "output": string}, ["spec"]), tool_compose_campus),
        tool("pt730_config_plan_campus", "Generate IOS config records from topology VLAN/L3 metadata.", schema({"plan": string, "l3": boolean, "routing": {"type": "string", "enum": ["none", "rip", "static"]}, "output": string}, ["plan"]), tool_config_plan_campus),
        tool("pt730_export_configs", "Export topology ios_configs into per-device .cfg files.", schema({"plan": string, "output_dir": string}, ["plan", "output_dir"]), tool_export_configs),
        tool("pt730_layout", "Assign deterministic coordinates to a topology plan.", schema({"plan": string, "style": string, "preserve_existing": boolean, "output": string}, ["plan"]), tool_layout),
        tool("pt730_ios_template_render", "Render high-level IOS template JSON into commands or topology ios_configs.", schema({"spec": string, "topology_json": boolean, "output": string}, ["spec"]), tool_ios_template_render),
        tool("pt730_pipeline_campus", "Run IP plan, compose, config planning, layout, safety, rendering, and config export offline.", schema({"compose_spec": string, "ip_plan": string, "output_dir": string, "routing": {"type": "string", "enum": ["none", "rip", "static"]}, "layout_style": string, "strict_safety": boolean, "course_audit": boolean}, ["compose_spec", "output_dir"]), tool_pipeline_campus),
        tool("pt730_live_count", "Count devices/links on a live Packet Tracer canvas. Requires allow_live=true.", schema({"allow_live": boolean, "timeout": integer}, ["allow_live"]), tool_live_count),
        tool("pt730_live_query", "Query the live Packet Tracer canvas. Requires allow_live=true.", schema({"allow_live": boolean, "summary": boolean, "timeout": integer}, ["allow_live"]), tool_live_query),
        tool("pt730_live_apply", "Apply a topology plan to live Packet Tracer, or run offline dry_run without live access.", schema({"plan": string, "dry_run": boolean, "allow_live": boolean, "replace": boolean, "batch_size": integer, "allow_risky": boolean, "strict_safety": boolean, "timeout": integer}, ["plan"]), tool_live_apply),
        tool("pt730_live_save_as", "Save the current live Packet Tracer file to a Linux path. Requires allow_live=true.", schema({"allow_live": boolean, "path": string, "direct": boolean, "timeout": integer}, ["allow_live", "path"]), tool_live_save_as),
    ]


TOOLS = tools()
TOOLS_BY_NAME = {item["name"]: item for item in TOOLS}


def public_tool(tool_def: dict[str, Any]) -> dict[str, Any]:
    return {key: tool_def[key] for key in ("name", "description", "inputSchema")}


def response(request_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def error_response(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def handle(root: Path, message: dict[str, Any]) -> dict[str, Any] | None:
    request_id = message.get("id")
    method = message.get("method")
    params = message.get("params") if isinstance(message.get("params"), dict) else {}
    if request_id is None:
        return None
    if method == "initialize":
        requested = params.get("protocolVersion")
        return response(
            request_id,
            {
                "protocolVersion": requested if isinstance(requested, str) else PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": SERVER_INFO,
            },
        )
    if method == "tools/list":
        return response(request_id, {"tools": [public_tool(item) for item in TOOLS]})
    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
        if not isinstance(name, str) or name not in TOOLS_BY_NAME:
            return error_response(request_id, -32602, f"Unknown tool: {name}")
        try:
            result = TOOLS_BY_NAME[name]["handler"](root, arguments)
        except ToolError as exc:
            return error_response(request_id, -32602, str(exc))
        return response(request_id, content_result(result))
    return error_response(request_id, -32601, f"Method not found: {method}")


def serve(stdin: Any = sys.stdin, stdout: Any = sys.stdout) -> int:
    root = repo_root()
    for line in stdin:
        if not line.strip():
            continue
        try:
            message = json.loads(line)
            if not isinstance(message, dict):
                raise ValueError("message must be an object")
            result = handle(root, message)
        except json.JSONDecodeError as exc:
            result = error_response(None, -32700, f"Parse error: {exc}")
        except ValueError as exc:
            result = error_response(None, -32600, str(exc))
        if result is not None:
            stdout.write(json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n")
            stdout.flush()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list-tools", action="store_true", help="print public tool definitions and exit")
    args = parser.parse_args(argv)
    if args.list_tools:
        print(json.dumps({"tools": [public_tool(item) for item in TOOLS]}, ensure_ascii=False, indent=2))
        return 0
    return serve()


if __name__ == "__main__":
    raise SystemExit(main())
