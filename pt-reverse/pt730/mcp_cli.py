#!/usr/bin/env python3
"""Minimal MCP stdio server exposing offline Packet Tracer 7.3.0 CLI tools."""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any


PROTOCOL_VERSION = "2025-06-18"
SERVER_INFO = {"name": "pt730-mcp", "version": "0.1.0"}
LAYOUT_STYLES = {"auto", "hierarchical", "campus", "lan", "ring", "grid"}
RENDER_THEMES = {"light", "dark", "paper"}
VISUAL_RENDER_FORMATS = {"svg", "drawio", "html"}
RENDER_OPTION_FORMATS = VISUAL_RENDER_FORMATS | {"diagram-audit"}
RENDER_GROUP_BY = {"none", "auto", "network", "vlan", "site", "category"}
RENDER_PRESETS = {"manual", "report"}
BUNDLE_RENDER_FORMATS = {
    "mermaid",
    "svg",
    "drawio",
    "html",
    "markdown",
    "summary",
    "course-audit",
    "diagram-audit",
    "verification-json",
    "verification-md",
}


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


def required_bool_arg(args: dict[str, Any], name: str) -> bool:
    if name not in args:
        raise ToolError(f"missing required argument: {name}")
    return bool_arg(args, name)


def optional_int_arg(args: dict[str, Any], name: str) -> int | None:
    if name not in args or args.get(name) is None:
        return None
    return int_arg(args, name, default=0)


def optional_bool_arg(args: dict[str, Any], name: str) -> bool | None:
    if name not in args or args.get(name) is None:
        return None
    return bool_arg(args, name)


def enum_arg(args: dict[str, Any], name: str, allowed: set[str], *, default: str | None = None) -> str:
    value = str_arg(args, name, required=default is None, default=default or "")
    if value not in allowed:
        raise ToolError(f"{name} must be one of: {', '.join(sorted(allowed))}")
    return value


def list_str_arg(args: dict[str, Any], name: str, *, required: bool = True) -> list[str]:
    value = args.get(name, [])
    if value is None:
        value = []
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ToolError(f"{name} must be an array of strings")
    if required and not value:
        raise ToolError(f"missing required argument: {name}")
    return value


def optional_render_formats_arg(args: dict[str, Any], name: str) -> list[str]:
    if name not in args or args.get(name) is None:
        return []
    value = args.get(name)
    if isinstance(value, str):
        formats = [item.strip() for item in value.split(",") if item.strip()]
    elif isinstance(value, list) and all(isinstance(item, str) for item in value):
        formats = value
    else:
        raise ToolError(f"{name} must be an array of strings or a comma-separated string")
    if not formats:
        raise ToolError(f"{name} cannot be empty")
    unknown = [fmt for fmt in formats if fmt not in BUNDLE_RENDER_FORMATS]
    if unknown:
        raise ToolError(f"{name} contains unsupported formats: {', '.join(unknown)}")
    deduped: list[str] = []
    for fmt in formats:
        if fmt not in deduped:
            deduped.append(fmt)
    return deduped


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


def dry_run_result(command: list[str]) -> dict[str, Any]:
    command_strings = [str(part) for part in command]
    return {
        "command": command_strings,
        "exitCode": 0,
        "stdout": "dry-run command preview:\n" + shlex.join(command_strings) + "\n",
        "stderr": "",
        "dryRun": True,
    }


def require_live(args: dict[str, Any], tool_name: str) -> None:
    if not bool_arg(args, "allow_live", default=False):
        raise ToolError(f"{tool_name} requires allow_live=true because it can contact live Packet Tracer")


def run_live_cli(root: Path, args: dict[str, Any], tool_name: str, command: list[str]) -> dict[str, Any]:
    if bool_arg(args, "dry_run", default=False):
        return dry_run_result(command)
    require_live(args, tool_name)
    return run_cli(root, command)


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
    if bool_arg(args, "compact", default=False):
        command.append("--compact")
    return run_cli(root, command)


def tool_schema(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    target = enum_arg(args, "target", {"template", "ip_plan", "compose", "config_plan", "pipeline", "ios_template", "lab"})
    cli_by_target = {
        "template": "pt730-template",
        "ip_plan": "pt730-ip-plan",
        "compose": "pt730-compose",
        "config_plan": "pt730-config-plan",
        "pipeline": "pt730-pipeline",
        "ios_template": "pt730-ios-template",
        "lab": "pt730-lab",
    }
    compact = bool_arg(args, "compact", default=False)
    command = [str(bin_path(root, cli_by_target[target]))]
    if compact and target != "ios_template":
        command.append("--compact")
    command.append("schema")
    result = run_cli(root, command)
    if compact and target == "ios_template" and result["exitCode"] == 0:
        try:
            result["stdout"] = json.dumps(json.loads(result["stdout"]), separators=(",", ":"), ensure_ascii=False) + "\n"
        except json.JSONDecodeError:
            pass
    return result


def tool_render(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    fmt = enum_arg(args, "format", {"mermaid", "markdown", "summary", "svg", "drawio", "html", "course-audit", "diagram-audit", "verification-json", "verification-md"})
    command = [str(bin_path(root, "pt730-render"))]
    if bool_arg(args, "strict_safety", default=False):
        command.append("--strict-safety")
    if bool_arg(args, "allow_risky", default=False):
        command.append("--allow-risky")
    if fmt in {"verification-json", "verification-md"}:
        command.extend(["verification-plan", str_arg(args, "plan"), "--format", "json" if fmt == "verification-json" else "markdown"])
        output = str_arg(args, "output", required=False)
        if output:
            command.extend(["--output", output])
        return run_cli(root, command)
    command.extend([fmt, str_arg(args, "plan")])
    output = str_arg(args, "output", required=False)
    if output:
        command.extend(["--output", output])
    if fmt == "mermaid":
        direction = enum_arg(args, "direction", {"LR", "TD", "TB", "RL", "BT"}, default="LR")
        command.extend(["--direction", direction])
    preset = str_arg(args, "preset", required=False)
    if preset:
        if fmt not in VISUAL_RENDER_FORMATS and fmt not in {"mermaid", "diagram-audit"}:
            raise ToolError("preset is supported only for mermaid, svg, drawio, html, or diagram-audit renders")
        if preset not in RENDER_PRESETS:
            raise ToolError("preset must be one of: manual, report")
        command.extend(["--preset", preset])
    theme = str_arg(args, "theme", required=False)
    if theme:
        if fmt not in RENDER_OPTION_FORMATS:
            raise ToolError("theme is supported only for svg, drawio, html, or diagram-audit renders")
        if theme not in RENDER_THEMES:
            raise ToolError("theme must be one of: dark, light, paper")
        command.extend(["--theme", theme])
    link_labels = optional_bool_arg(args, "link_labels")
    if link_labels is not None:
        if fmt not in RENDER_OPTION_FORMATS and fmt != "mermaid":
            raise ToolError("link_labels is supported only for mermaid, svg, drawio, html, or diagram-audit renders")
        if not link_labels:
            command.append("--no-link-labels")
    model_labels = optional_bool_arg(args, "model_labels")
    if model_labels is not None:
        if fmt not in RENDER_OPTION_FORMATS:
            raise ToolError("model_labels is supported only for svg, drawio, html, or diagram-audit renders")
        if not model_labels:
            command.append("--no-model-labels")
    group_by = str_arg(args, "group_by", required=False)
    if group_by:
        if fmt not in RENDER_OPTION_FORMATS:
            raise ToolError("group_by is supported only for svg, drawio, html, or diagram-audit renders")
        if group_by not in RENDER_GROUP_BY:
            raise ToolError("group_by must be one of: auto, category, network, none, site, vlan")
        command.extend(["--group-by", group_by])
    title = str_arg(args, "title", required=False)
    if title:
        if fmt not in RENDER_OPTION_FORMATS:
            raise ToolError("title is supported only for svg, drawio, html, or diagram-audit renders")
        command.extend(["--title", title])
    legend = optional_bool_arg(args, "legend")
    if legend is not None:
        if fmt not in RENDER_OPTION_FORMATS:
            raise ToolError("legend is supported only for svg, drawio, html, or diagram-audit renders")
        if legend:
            command.append("--legend")
    return run_cli(root, command)


def tool_render_bundle(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    command = [str(bin_path(root, "pt730-render"))]
    if bool_arg(args, "strict_safety", default=False):
        command.append("--strict-safety")
    if bool_arg(args, "allow_risky", default=False):
        command.append("--allow-risky")
    command.extend(["bundle", str_arg(args, "plan"), "--output-dir", str_arg(args, "output_dir")])
    basename = str_arg(args, "basename", required=False)
    if basename:
        command.extend(["--basename", basename])
    formats = optional_render_formats_arg(args, "formats")
    if formats:
        command.extend(["--formats", ",".join(formats)])
    direction = enum_arg(args, "direction", {"LR", "TD", "TB", "RL", "BT"}, default="LR")
    command.extend(["--direction", direction])
    preset = str_arg(args, "preset", required=False)
    if preset:
        if preset not in RENDER_PRESETS:
            raise ToolError("preset must be one of: manual, report")
        command.extend(["--preset", preset])
    theme = str_arg(args, "theme", required=False)
    if theme:
        if theme not in RENDER_THEMES:
            raise ToolError("theme must be one of: dark, light, paper")
        command.extend(["--theme", theme])
    link_labels = optional_bool_arg(args, "link_labels")
    if link_labels is not None and not link_labels:
        command.append("--no-link-labels")
    model_labels = optional_bool_arg(args, "model_labels")
    if model_labels is not None and not model_labels:
        command.append("--no-model-labels")
    group_by = str_arg(args, "group_by", required=False)
    if group_by:
        if group_by not in RENDER_GROUP_BY:
            raise ToolError("group_by must be one of: auto, category, network, none, site, vlan")
        command.extend(["--group-by", group_by])
    title = str_arg(args, "title", required=False)
    if title:
        command.extend(["--title", title])
    legend = optional_bool_arg(args, "legend")
    if legend:
        command.append("--legend")
    return run_cli(root, command)


def tool_verification_plan(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    command = [str(bin_path(root, "pt730-render"))]
    if bool_arg(args, "strict_safety", default=False):
        command.append("--strict-safety")
    if bool_arg(args, "allow_risky", default=False):
        command.append("--allow-risky")
    command.extend(["verification-plan", str_arg(args, "plan")])
    fmt = enum_arg(args, "format", {"json", "markdown"}, default="json")
    command.extend(["--format", fmt])
    output = str_arg(args, "output", required=False)
    if output:
        command.extend(["--output", output])
    if bool_arg(args, "compact", default=False):
        command.append("--compact")
    max_hosts = int_arg(args, "max_hosts", default=12)
    max_service_targets = int_arg(args, "max_service_targets", default=8)
    if max_hosts < 1:
        raise ToolError("max_hosts must be at least 1")
    if max_service_targets < 1:
        raise ToolError("max_service_targets must be at least 1")
    command.extend(["--max-hosts", str(max_hosts), "--max-service-targets", str(max_service_targets)])
    return run_cli(root, command)


def tool_lab_template(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    command = [str(bin_path(root, "pt730-lab"))]
    if bool_arg(args, "compact", default=False):
        command.append("--compact")
    command.extend(["template", str_arg(args, "spec"), "--output-dir", str_arg(args, "output_dir")])
    if bool_arg(args, "strict_safety", default=False):
        command.append("--strict-safety")
    return run_cli(root, command)


def tool_lab_plan(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    command = [str(bin_path(root, "pt730-lab"))]
    if bool_arg(args, "compact", default=False):
        command.append("--compact")
    command.extend(["plan", str_arg(args, "plan"), "--output-dir", str_arg(args, "output_dir")])
    for key, flag in (("name", "--name"), ("basename", "--basename"), ("config_source", "--config-source")):
        value = str_arg(args, key, required=False)
        if value:
            command.extend([flag, value])
    formats = optional_render_formats_arg(args, "formats")
    if formats:
        command.extend(["--formats", ",".join(formats)])
    direction = enum_arg(args, "direction", {"LR", "TD", "TB", "RL", "BT"}, default="LR")
    command.extend(["--direction", direction])
    preset = str_arg(args, "preset", required=False)
    if preset:
        if preset not in RENDER_PRESETS:
            raise ToolError("preset must be one of: manual, report")
        command.extend(["--preset", preset])
    theme = str_arg(args, "theme", required=False)
    if theme:
        if theme not in RENDER_THEMES:
            raise ToolError("theme must be one of: dark, light, paper")
        command.extend(["--theme", theme])
    link_labels = optional_bool_arg(args, "link_labels")
    if link_labels is not None and not link_labels:
        command.append("--no-link-labels")
    model_labels = optional_bool_arg(args, "model_labels")
    if model_labels is not None and not model_labels:
        command.append("--no-model-labels")
    group_by = str_arg(args, "group_by", required=False)
    if group_by:
        if group_by not in RENDER_GROUP_BY:
            raise ToolError("group_by must be one of: auto, category, network, none, site, vlan")
        command.extend(["--group-by", group_by])
    title = str_arg(args, "title", required=False)
    if title:
        command.extend(["--title", title])
    legend = optional_bool_arg(args, "legend")
    if legend:
        command.append("--legend")
    if bool_arg(args, "strict_safety", default=False):
        command.append("--strict-safety")
    export_configs = optional_bool_arg(args, "export_configs")
    if export_configs is not None and not export_configs:
        command.append("--no-configs")
    return run_cli(root, command)


def tool_lab_report(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    command = [str(bin_path(root, "pt730-lab"))]
    if bool_arg(args, "compact", default=False):
        command.append("--compact")
    command.extend(["report", str_arg(args, "manifest")])
    output = str_arg(args, "output", required=False)
    if output:
        command.extend(["--output", output])
    title = str_arg(args, "title", required=False)
    if title:
        command.extend(["--title", title])
    return run_cli(root, command)


def tool_safety_plan(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    command = [str(bin_path(root, "pt730-safety")), "plan", str_arg(args, "plan")]
    if bool_arg(args, "strict", default=False):
        command.append("--strict")
    return run_cli(root, command)


def tool_safety_js(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    command = [str(bin_path(root, "pt730-safety")), "js"]
    if bool_arg(args, "strict", default=False):
        command.append("--strict")
    file_path = str_arg(args, "file", required=False)
    code = str_arg(args, "code", required=False)
    if file_path and code:
        raise ToolError("pt730_safety_js requires exactly one of code or file")
    if file_path:
        command.extend(["--file", file_path])
    elif code:
        command.append(code)
    else:
        raise ToolError("pt730_safety_js requires code or file")
    return run_cli(root, command)


def tool_safety_policy(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    return run_cli(root, [str(bin_path(root, "pt730-safety")), "policy"])


def tool_catalog(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    action = enum_arg(args, "action", {"devices", "device", "ports", "modules", "module", "cables", "infer_cable", "aliases"})
    command = [str(bin_path(root, "pt730-catalog")), "infer-cable" if action == "infer_cable" else action]
    if action in {"device", "ports"}:
        command.append(str_arg(args, "model"))
    elif action == "module":
        command.append(str_arg(args, "module"))
    elif action == "infer_cable":
        command.extend([str_arg(args, "category_a"), str_arg(args, "category_b")])
    if action == "devices":
        category = str_arg(args, "category", required=False)
        if category:
            command.extend(["--category", category])
        status = enum_arg(args, "status", {"all", "safe", "risky", "unverified"}, default="all")
        command.extend(["--status", status])
        if bool_arg(args, "include_ports", default=False):
            command.append("--include-ports")
    elif action == "modules":
        model = str_arg(args, "model", required=False)
        if model:
            command.extend(["--model", model])
        category = str_arg(args, "category", required=False)
        if category:
            command.extend(["--category", category])
        status = enum_arg(args, "status", {"all", "verified", "unverified"}, default="all")
        command.extend(["--status", status])
    elif action == "cables":
        status = enum_arg(args, "status", {"all", "verified", "mapped"}, default="all")
        command.extend(["--status", status])
    if bool_arg(args, "table", default=False) and action != "infer_cable":
        command.append("--table")
    return run_cli(root, command)


def tool_template_lan_star(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    command = [str(bin_path(root, "pt730-template"))]
    if bool_arg(args, "compact", default=False):
        command.append("--compact")
    command.extend(
        [
            "lan-star",
            "--pcs",
            str(int_arg(args, "pcs", default=4)),
            "--servers",
            str(int_arg(args, "servers", default=0)),
            "--network",
            str_arg(args, "network", required=False, default="192.168.10.0/24"),
        ]
    )
    for key, flag in (("name", "--name"), ("gateway", "--gateway"), ("dns", "--dns"), ("output", "--output")):
        value = str_arg(args, key, required=False)
        if value:
            command.extend([flag, value])
    layout_style = str_arg(args, "layout_style", required=False)
    if layout_style:
        if layout_style not in LAYOUT_STYLES:
            raise ToolError("layout_style must be one of: auto, campus, grid, hierarchical, lan, ring")
        command.extend(["--layout-style", layout_style])
    if bool_arg(args, "no_layout", default=False):
        command.append("--no-layout")
    return run_cli(root, command)


def tool_template_wireless_lan(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    command = [str(bin_path(root, "pt730-template"))]
    if bool_arg(args, "compact", default=False):
        command.append("--compact")
    command.extend(
        [
            "wireless-lan",
            "--aps",
            str(int_arg(args, "aps", default=1)),
            "--laptops",
            str(int_arg(args, "laptops", default=3)),
            "--servers",
            str(int_arg(args, "servers", default=1)),
            "--network",
            str_arg(args, "network", required=False, default="192.168.80.0/24"),
        ]
    )
    for key, flag in (("name", "--name"), ("gateway", "--gateway"), ("dns", "--dns"), ("ssid", "--ssid"), ("output", "--output")):
        value = str_arg(args, key, required=False)
        if value:
            command.extend([flag, value])
    layout_style = str_arg(args, "layout_style", required=False)
    if layout_style:
        if layout_style not in LAYOUT_STYLES:
            raise ToolError("layout_style must be one of: auto, campus, grid, hierarchical, lan, ring")
        command.extend(["--layout-style", layout_style])
    if bool_arg(args, "no_layout", default=False):
        command.append("--no-layout")
    return run_cli(root, command)


def tool_template_vlan_router_on_stick(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    command = [str(bin_path(root, "pt730-template"))]
    if bool_arg(args, "compact", default=False):
        command.append("--compact")
    command.append("vlan-router-on-stick")
    for key, flag in (
        ("name", "--name"),
        ("address_pool", "--address-pool"),
        ("domain", "--domain"),
        ("output", "--output"),
    ):
        value = str_arg(args, key, required=False)
        if value:
            command.extend([flag, value])
    for key, flag, default in (
        ("vlans", "--vlans", 3),
        ("hosts_per_vlan", "--hosts-per-vlan", 2),
        ("servers_per_vlan", "--servers-per-vlan", 0),
        ("vlan_prefix", "--vlan-prefix", 24),
        ("vlan_base", "--vlan-base", 10),
    ):
        command.extend([flag, str(int_arg(args, key, default=default))])
    native_vlan = optional_int_arg(args, "native_vlan")
    if native_vlan is not None:
        command.extend(["--native-vlan", str(native_vlan)])
    client_addressing = str_arg(args, "client_addressing", required=False)
    if client_addressing:
        if client_addressing not in {"static", "dhcp"}:
            raise ToolError("client_addressing must be one of: static, dhcp")
        command.extend(["--client-addressing", client_addressing])
    layout_style = str_arg(args, "layout_style", required=False)
    if layout_style:
        if layout_style not in LAYOUT_STYLES:
            raise ToolError("layout_style must be one of: auto, campus, grid, hierarchical, lan, ring")
        command.extend(["--layout-style", layout_style])
    if bool_arg(args, "no_layout", default=False):
        command.append("--no-layout")
    return run_cli(root, command)


def tool_template_edge_security(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    command = [str(bin_path(root, "pt730-template"))]
    if bool_arg(args, "compact", default=False):
        command.append("--compact")
    command.append("edge-security")
    for key, flag in (
        ("name", "--name"),
        ("inside_network", "--inside-network"),
        ("dmz_network", "--dmz-network"),
        ("wan_network", "--wan-network"),
        ("internet_network", "--internet-network"),
        ("domain", "--domain"),
        ("output", "--output"),
    ):
        value = str_arg(args, key, required=False)
        if value:
            command.extend([flag, value])
    for key, flag, default in (
        ("inside_hosts", "--inside-hosts", 3),
        ("dmz_servers", "--dmz-servers", 2),
        ("internet_hosts", "--internet-hosts", 1),
    ):
        command.extend([flag, str(int_arg(args, key, default=default))])
    layout_style = str_arg(args, "layout_style", required=False)
    if layout_style:
        if layout_style not in LAYOUT_STYLES:
            raise ToolError("layout_style must be one of: auto, campus, grid, hierarchical, lan, ring")
        command.extend(["--layout-style", layout_style])
    if bool_arg(args, "no_layout", default=False):
        command.append("--no-layout")
    return run_cli(root, command)


def tool_template_router_ring(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    command = [str(bin_path(root, "pt730-template"))]
    if bool_arg(args, "compact", default=False):
        command.append("--compact")
    command.extend(
        [
            "router-ring",
            "--routers",
            str(int_arg(args, "routers", default=4)),
            "--interconnect-pool",
            str_arg(args, "interconnect_pool", required=False, default="10.20.0.0/28"),
        ]
    )
    for key, flag in (("name", "--name"), ("output", "--output")):
        value = str_arg(args, key, required=False)
        if value:
            command.extend([flag, value])
    layout_style = str_arg(args, "layout_style", required=False)
    if layout_style:
        if layout_style not in LAYOUT_STYLES:
            raise ToolError("layout_style must be one of: auto, campus, grid, hierarchical, lan, ring")
        command.extend(["--layout-style", layout_style])
    if bool_arg(args, "no_layout", default=False):
        command.append("--no-layout")
    return run_cli(root, command)


def tool_template_wan_ring(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    command = [str(bin_path(root, "pt730-template"))]
    if bool_arg(args, "compact", default=False):
        command.append("--compact")
    command.append("wan-ring")
    for key, flag in (
        ("name", "--name"),
        ("interconnect_pool", "--interconnect-pool"),
        ("lan_pool", "--lan-pool"),
        ("output", "--output"),
    ):
        value = str_arg(args, key, required=False)
        if value:
            command.extend([flag, value])
    for key, flag, default in (
        ("sites", "--sites", 3),
        ("hosts_per_site", "--hosts-per-site", 2),
        ("servers_per_site", "--servers-per-site", 1),
        ("lan_prefix", "--lan-prefix", 24),
    ):
        command.extend([flag, str(int_arg(args, key, default=default))])
    command.extend(["--routing", enum_arg(args, "routing", {"none", "rip", "ospf", "static"}, default="rip")])
    layout_style = str_arg(args, "layout_style", required=False)
    if layout_style:
        if layout_style not in LAYOUT_STYLES:
            raise ToolError("layout_style must be one of: auto, campus, grid, hierarchical, lan, ring")
        command.extend(["--layout-style", layout_style])
    if bool_arg(args, "no_layout", default=False):
        command.append("--no-layout")
    return run_cli(root, command)


def tool_template_campus(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    command = [str(bin_path(root, "pt730-template"))]
    if bool_arg(args, "compact", default=False):
        command.append("--compact")
    command.append("campus")
    for key, flag in (
        ("name", "--name"),
        ("address_pool", "--address-pool"),
        ("server_network", "--server-network"),
        ("interconnect_pool", "--interconnect-pool"),
        ("output", "--output"),
    ):
        value = str_arg(args, key, required=False)
        if value:
            command.extend([flag, value])
    for key, flag, default in (
        ("cores", "--cores", 2),
        ("segments", "--segments", 4),
        ("hosts_per_segment", "--hosts-per-segment", 2),
        ("access_switches_per_segment", "--access-switches-per-segment", 1),
        ("servers", "--servers", 2),
        ("segment_prefix", "--segment-prefix", 24),
        ("server_vlan", "--server-vlan", 10),
        ("vlan_base", "--vlan-base", 20),
    ):
        command.extend([flag, str(int_arg(args, key, default=default))])
    if bool_arg(args, "l3", default=False):
        command.append("--l3")
    command.extend(["--routing", enum_arg(args, "routing", {"none", "rip", "ospf", "static"}, default="none")])
    layout_style = str_arg(args, "layout_style", required=False)
    if layout_style:
        if layout_style not in LAYOUT_STYLES:
            raise ToolError("layout_style must be one of: auto, campus, grid, hierarchical, lan, ring")
        command.extend(["--layout-style", layout_style])
    if bool_arg(args, "no_layout", default=False):
        command.append("--no-layout")
    return run_cli(root, command)


def tool_template_redundant_campus(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    command = [str(bin_path(root, "pt730-template"))]
    if bool_arg(args, "compact", default=False):
        command.append("--compact")
    command.append("redundant-campus")
    for key, flag in (
        ("name", "--name"),
        ("address_pool", "--address-pool"),
        ("server_network", "--server-network"),
        ("output", "--output"),
    ):
        value = str_arg(args, key, required=False)
        if value:
            command.extend([flag, value])
    for key, flag, default in (
        ("segments", "--segments", 4),
        ("hosts_per_segment", "--hosts-per-segment", 2),
        ("access_switches_per_segment", "--access-switches-per-segment", 1),
        ("servers", "--servers", 4),
        ("segment_prefix", "--segment-prefix", 24),
        ("server_vlan", "--server-vlan", 10),
        ("vlan_base", "--vlan-base", 20),
    ):
        command.extend([flag, str(int_arg(args, key, default=default))])
    command.extend(["--routing", enum_arg(args, "routing", {"none", "rip", "ospf"}, default="ospf")])
    layout_style = str_arg(args, "layout_style", required=False)
    if layout_style:
        if layout_style not in LAYOUT_STYLES:
            raise ToolError("layout_style must be one of: auto, campus, grid, hierarchical, lan, ring")
        command.extend(["--layout-style", layout_style])
    if bool_arg(args, "no_layout", default=False):
        command.append("--no-layout")
    return run_cli(root, command)


def tool_template_enterprise_edge(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    command = [str(bin_path(root, "pt730-template"))]
    if bool_arg(args, "compact", default=False):
        command.append("--compact")
    command.append("enterprise-edge")
    for key, flag in (
        ("name", "--name"),
        ("campus_pool", "--campus-pool"),
        ("server_network", "--server-network"),
        ("branch_pool", "--branch-pool"),
        ("wan_pool", "--wan-pool"),
        ("dmz_network", "--dmz-network"),
        ("isp_wan_network", "--isp-wan-network"),
        ("internet_network", "--internet-network"),
        ("domain", "--domain"),
        ("output", "--output"),
    ):
        value = str_arg(args, key, required=False)
        if value:
            command.extend([flag, value])
    for key, flag, default in (
        ("campus_vlans", "--campus-vlans", 3),
        ("hosts_per_vlan", "--hosts-per-vlan", 2),
        ("campus_servers", "--campus-servers", 4),
        ("branches", "--branches", 2),
        ("branch_hosts", "--branch-hosts", 2),
        ("dmz_servers", "--dmz-servers", 2),
        ("internet_hosts", "--internet-hosts", 1),
        ("campus_prefix", "--campus-prefix", 24),
        ("server_vlan", "--server-vlan", 10),
        ("vlan_base", "--vlan-base", 20),
        ("branch_prefix", "--branch-prefix", 24),
    ):
        command.extend([flag, str(int_arg(args, key, default=default))])
    command.extend(["--routing", enum_arg(args, "routing", {"none", "rip", "ospf", "static"}, default="ospf")])
    layout_style = str_arg(args, "layout_style", required=False)
    if layout_style:
        if layout_style not in LAYOUT_STYLES:
            raise ToolError("layout_style must be one of: auto, campus, grid, hierarchical, lan, ring")
        command.extend(["--layout-style", layout_style])
    if bool_arg(args, "no_layout", default=False):
        command.append("--no-layout")
    return run_cli(root, command)


def tool_ip_plan_campus(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    command = [str(bin_path(root, "pt730-ip-plan"))]
    if bool_arg(args, "compact", default=False):
        command.append("--compact")
    command.extend(["campus", str_arg(args, "spec")])
    output = str_arg(args, "output", required=False)
    if output:
        command.extend(["--output", output])
    return run_cli(root, command)


def tool_compose_campus(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    command = [str(bin_path(root, "pt730-compose"))]
    if bool_arg(args, "compact", default=False):
        command.append("--compact")
    command.extend(["campus", str_arg(args, "spec")])
    ip_plan = str_arg(args, "segments_from_ip_plan", required=False)
    if ip_plan:
        command.extend(["--segments-from-ip-plan", ip_plan])
    if bool_arg(args, "no_layout", default=False):
        command.append("--no-layout")
    layout_style = str_arg(args, "layout_style", required=False)
    if layout_style:
        if layout_style not in LAYOUT_STYLES:
            raise ToolError("layout_style must be one of: auto, campus, grid, hierarchical, lan, ring")
        command.extend(["--layout-style", layout_style])
    output = str_arg(args, "output", required=False)
    if output:
        command.extend(["--output", output])
    return run_cli(root, command)


def tool_config_plan_campus(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    command = [str(bin_path(root, "pt730-config-plan"))]
    if bool_arg(args, "compact", default=False):
        command.append("--compact")
    command.extend(["campus", str_arg(args, "plan")])
    if bool_arg(args, "ios_only", default=False):
        command.append("--ios-only")
    if bool_arg(args, "l3", default=False):
        command.append("--l3")
    routing = enum_arg(args, "routing", {"none", "rip", "ospf", "static"}, default="none")
    command.extend(["--routing", routing])
    output = str_arg(args, "output", required=False)
    if output:
        command.extend(["--output", output])
    return run_cli(root, command)


def tool_export_configs(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    command = [str(bin_path(root, "pt730-config-plan"))]
    if bool_arg(args, "compact", default=False):
        command.append("--compact")
    command.extend(["export-configs", str_arg(args, "plan"), "--output-dir", str_arg(args, "output_dir")])
    source = str_arg(args, "source", required=False)
    if source:
        command.extend(["--source", source])
    return run_cli(root, command)


def tool_layout(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    command = [str(bin_path(root, "pt730-layout")), str_arg(args, "plan")]
    style = str_arg(args, "style", required=False)
    if style:
        if style not in LAYOUT_STYLES:
            raise ToolError("style must be one of: auto, campus, grid, hierarchical, lan, ring")
        command.extend(["--style", style])
    if bool_arg(args, "preserve_existing", default=False):
        command.append("--preserve-existing")
    for key, flag in (
        ("canvas_width", "--canvas-width"),
        ("canvas_height", "--canvas-height"),
        ("spacing_x", "--spacing-x"),
        ("spacing_y", "--spacing-y"),
        ("margin", "--margin"),
    ):
        value = optional_int_arg(args, key)
        if value is not None:
            if key != "margin" and value <= 0:
                raise ToolError(f"{key} must be a positive integer")
            if key == "margin" and value < 0:
                raise ToolError("margin must be a non-negative integer")
            command.extend([flag, str(value)])
    if bool_arg(args, "compact", default=False):
        command.append("--compact")
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
    command = [str(bin_path(root, "pt730-pipeline"))]
    if bool_arg(args, "compact", default=False):
        command.append("--compact")
    command.extend([
        "campus",
        "--compose-spec",
        str_arg(args, "compose_spec"),
        "--output-dir",
        str_arg(args, "output_dir"),
        "--routing",
        enum_arg(args, "routing", {"none", "rip", "ospf", "static"}, default="rip"),
    ])
    ip_plan = str_arg(args, "ip_plan", required=False)
    if ip_plan:
        command.extend(["--ip-plan", ip_plan])
    layout_style = str_arg(args, "layout_style", required=False)
    if layout_style:
        if layout_style not in LAYOUT_STYLES:
            raise ToolError("layout_style must be one of: auto, campus, grid, hierarchical, lan, ring")
        command.extend(["--layout-style", layout_style])
    if bool_arg(args, "strict_safety", default=False):
        command.append("--strict-safety")
    if bool_arg(args, "course_audit", default=False):
        command.append("--course-audit")
    return run_cli(root, command)


def tool_topo_summarize_query(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    command = [str(bin_path(root, "pt730-topo")), "summarize-query", str_arg(args, "query_json")]
    return run_cli(root, command)


def tool_topo_export(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    command = [
        str(bin_path(root, "pt730-topo")),
        "--timeout",
        str(int_arg(args, "timeout", default=20)),
        "export",
        "--raw-out",
        str_arg(args, "raw_out"),
        "--summary-out",
        str_arg(args, "summary_out"),
    ]
    bridge = str_arg(args, "bridge", required=False)
    if bridge:
        command[1:1] = ["--bridge", bridge]
    from_query = str_arg(args, "from_query", required=False)
    if from_query:
        command.extend(["--from-query", from_query])
    markdown_out = str_arg(args, "markdown_out", required=False)
    if markdown_out:
        command.extend(["--markdown-out", markdown_out])
    if from_query:
        return run_cli(root, command)
    return run_live_cli(root, args, "pt730_topo_export", command)


def tool_models_manifest(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    return run_cli(root, [str(bin_path(root, "pt730-models")), "manifest"])


def tool_models_queue(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    command = [str(bin_path(root, "pt730-models")), "queue"]
    if bool_arg(args, "include_risky", default=False):
        command.append("--include-risky")
    if bool_arg(args, "include_blocked", default=False):
        command.append("--include-blocked")
    return run_cli(root, command)


def tool_models_probe_plan(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    command = [str(bin_path(root, "pt730-models")), "probe-plan", str_arg(args, "model")]
    if bool_arg(args, "allow_risky", default=False):
        command.append("--allow-risky")
    if bool_arg(args, "allow_blocked", default=False):
        command.append("--allow-blocked")
    return run_cli(root, command)


def tool_models_validate(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    dry_run = bool_arg(args, "dry_run", default=False)
    live = bool_arg(args, "live", default=False)
    command = [str(bin_path(root, "pt730-models")), "validate", str_arg(args, "model")]
    if dry_run:
        command.append("--dry-run")
    if live:
        require_live(args, "pt730_models_validate")
        command.append("--live")
    elif not dry_run:
        raise ToolError("pt730_models_validate requires dry_run=true or live=true with allow_live=true")
    if bool_arg(args, "allow_risky", default=False):
        command.append("--allow-risky")
    if bool_arg(args, "allow_blocked", default=False):
        command.append("--allow-blocked")
    bridge = str_arg(args, "bridge", required=False)
    if bridge:
        command.extend(["--bridge", bridge])
    command.extend(["--timeout", str(int_arg(args, "timeout", default=20))])
    record_failure_status = str_arg(args, "record_failure_status", required=False)
    if record_failure_status:
        if record_failure_status not in {"risky", "blocked"}:
            raise ToolError("record_failure_status must be one of: blocked, risky")
        command.extend(["--record-failure-status", record_failure_status])
    return run_cli(root, command)


def tool_models_validate_batch(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    dry_run = bool_arg(args, "dry_run", default=False)
    live = bool_arg(args, "live", default=False)
    command = [str(bin_path(root, "pt730-models")), "validate-batch"]
    if dry_run:
        command.append("--dry-run")
    if live:
        require_live(args, "pt730_models_validate_batch")
        command.append("--live")
    elif not dry_run:
        raise ToolError("pt730_models_validate_batch requires dry_run=true or live=true with allow_live=true")
    limit = int_arg(args, "limit", default=0)
    if limit:
        command.extend(["--limit", str(limit)])
    if bool_arg(args, "include_risky", default=False):
        command.append("--include-risky")
    if bool_arg(args, "include_blocked", default=False):
        command.append("--include-blocked")
    bridge = str_arg(args, "bridge", required=False)
    if bridge:
        command.extend(["--bridge", bridge])
    command.extend(["--timeout", str(int_arg(args, "timeout", default=20))])
    if bool_arg(args, "keep_going", default=False):
        command.append("--keep-going")
    record_failures = str_arg(args, "record_failures", required=False)
    if record_failures:
        if record_failures not in {"risky", "blocked"}:
            raise ToolError("record_failures must be one of: blocked, risky")
        command.extend(["--record-failures", record_failures])
    return run_cli(root, command)


def tool_models_record(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    command = [str(bin_path(root, "pt730-models")), "record", str_arg(args, "model"), "--status", enum_arg(args, "status", {"safe", "risky", "blocked", "unverified"})]
    reason = str_arg(args, "reason", required=False)
    if reason:
        command.extend(["--reason", reason])
    for item in list_str_arg(args, "evidence", required=False):
        command.extend(["--evidence", item])
    if bool_arg(args, "save_reopen", default=False):
        command.append("--save-reopen")
    if bool_arg(args, "dry_run", default=False):
        return dry_run_result(command)
    if not bool_arg(args, "allow_write", default=False):
        raise ToolError("pt730_models_record requires allow_write=true because it changes model validation metadata")
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


def tool_live_app(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    action = enum_arg(args, "action", {"count", "save", "new", "save_as", "open", "screenshot"})
    command = [str(bin_path(root, "pt730-app")), "--timeout", str(int_arg(args, "timeout", default=15))]
    if action == "count":
        command.append("count")
    elif action == "save":
        command.append("save")
    elif action == "new":
        command.append("new")
    elif action == "save_as":
        command.extend(["save-as", str_arg(args, "path")])
        if bool_arg(args, "direct", default=False):
            command.append("--direct")
    elif action == "open":
        command.extend(["open", str_arg(args, "path")])
        if bool_arg(args, "direct", default=False):
            command.append("--direct")
    elif action == "screenshot":
        command.extend(["screenshot", str_arg(args, "path")])
    return run_live_cli(root, args, "pt730_live_app", command)


def tool_live_bridge(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    action = enum_arg(args, "action", {"start", "stop", "restart", "status", "bootstrap", "logs"})
    command = [str(bin_path(root, "pt730-bridge")), action]
    if action == "logs":
        lines = str_arg(args, "lines", required=False)
        if lines:
            command.append(lines)
    return run_live_cli(root, args, "pt730_live_bridge", command)


def tool_live_launch(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    action = enum_arg(args, "action", {"start", "stop", "restart", "status", "logs"})
    command = [str(bin_path(root, "pt730-launch")), action]
    if action == "logs":
        lines = str_arg(args, "lines", required=False)
        if lines:
            command.append(lines)
    return run_live_cli(root, args, "pt730_live_launch", command)


def tool_live_recover(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    command = [str(bin_path(root, "pt730-recover")), "--wait", str(int_arg(args, "wait", default=45))]
    if bool_arg(args, "notify", default=False):
        command.append("--notify")
    return run_live_cli(root, args, "pt730_live_recover", command)


def tool_live_eval(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    file_path = str_arg(args, "file", required=False)
    code = str_arg(args, "code", required=False)
    if file_path and code:
        raise ToolError("pt730_live_eval requires exactly one of code or file")
    if not file_path and not code:
        raise ToolError("pt730_live_eval requires code or file")
    command = [str(bin_path(root, "pt730-eval")), "--timeout", str(int_arg(args, "timeout", default=10))]
    bridge = str_arg(args, "bridge", required=False)
    if bridge:
        command.extend(["--bridge", bridge])
    if bool_arg(args, "expr", default=False):
        command.append("--expr")
    if bool_arg(args, "allow_risky", default=False):
        command.append("--allow-risky")
    if file_path:
        command.extend(["--file", file_path])
    else:
        command.append(code)
    return run_live_cli(root, args, "pt730_live_eval", command)


def tool_live_smoke(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    command = [str(bin_path(root, "pt730-smoke"))]
    if bool_arg(args, "new", default=False):
        command.append("--new")
    if bool_arg(args, "dhcp", default=False):
        command.append("--dhcp")
    if bool_arg(args, "strict_safety", default=False):
        command.append("--strict-safety")
    if bool_arg(args, "no_apply", default=False):
        command.append("--no-apply")
    plan = str_arg(args, "plan", required=False)
    if plan:
        command.extend(["--plan", plan])
    save_as = str_arg(args, "save_as", required=False)
    if save_as:
        command.extend(["--save-as", save_as])
    return run_live_cli(root, args, "pt730_live_smoke", command)


def tool_live_ios(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    commands = list_str_arg(args, "commands", required=False)
    file_path = str_arg(args, "file", required=False)
    init_dialog = bool_arg(args, "init_dialog", default=False)
    if not commands and not file_path and not init_dialog:
        raise ToolError("pt730_live_ios requires commands, file, or init_dialog")
    command = [str(bin_path(root, "pt730-ios")), str_arg(args, "device"), "--timeout", str(int_arg(args, "timeout", default=20))]
    for item in commands:
        command.extend(["--cmd", item])
    if file_path:
        command.extend(["--file", file_path])
    if init_dialog:
        command.append("--init-dialog")
    if bool_arg(args, "save", default=False):
        command.append("--save")
    if bool_arg(args, "keep_comments", default=False):
        command.append("--keep-comments")
    command.extend(["--output", enum_arg(args, "output", {"tail", "full", "none"}, default="tail")])
    command.extend(["--tail-lines", str(int_arg(args, "tail_lines", default=80))])
    return run_live_cli(root, args, "pt730_live_ios", command)


def tool_live_pc_static(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    command = [
        str(bin_path(root, "pt730-pc")),
        "--timeout",
        str(int_arg(args, "timeout", default=10)),
    ]
    bridge = str_arg(args, "bridge", required=False)
    if bridge:
        command.extend(["--bridge", bridge])
    command.extend(
        [
            "static",
            str_arg(args, "device"),
            "--port",
            str_arg(args, "port", required=False, default="FastEthernet0"),
            "--ip",
            str_arg(args, "ip"),
            "--mask",
            str_arg(args, "mask"),
        ]
    )
    gateway = str_arg(args, "gateway", required=False)
    if gateway:
        command.extend(["--gateway", gateway])
    dns = str_arg(args, "dns", required=False)
    if dns:
        command.extend(["--dns", dns])
    return run_live_cli(root, args, "pt730_live_pc_static", command)


def tool_live_pc_inspect(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    command = [str(bin_path(root, "pt730-pc")), "--timeout", str(int_arg(args, "timeout", default=10))]
    bridge = str_arg(args, "bridge", required=False)
    if bridge:
        command.extend(["--bridge", bridge])
    command.extend(["inspect", str_arg(args, "device"), "--port", str_arg(args, "port", required=False, default="FastEthernet0")])
    return run_live_cli(root, args, "pt730_live_pc_inspect", command)


def tool_live_pc_dhcp(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    command = [str(bin_path(root, "pt730-pc")), "--timeout", str(int_arg(args, "timeout", default=10))]
    bridge = str_arg(args, "bridge", required=False)
    if bridge:
        command.extend(["--bridge", bridge])
    command.extend(["dhcp", str_arg(args, "device"), "--port", str_arg(args, "port", required=False, default="FastEthernet0")])
    if bool_arg(args, "renew", default=False):
        command.append("--renew")
    wait = int_arg(args, "wait", default=0)
    if wait:
        command.extend(["--wait", str(wait)])
    expect_network = str_arg(args, "expect_network", required=False)
    if expect_network:
        command.extend(["--expect-network", expect_network])
    return run_live_cli(root, args, "pt730_live_pc_dhcp", command)


def tool_live_term(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    commands = list_str_arg(args, "commands", required=False)
    file_path = str_arg(args, "file", required=False)
    if not commands and not file_path:
        raise ToolError("pt730_live_term requires commands or file")
    command = [str(bin_path(root, "pt730-term")), str_arg(args, "device"), "--timeout", str(int_arg(args, "timeout", default=10))]
    bridge = str_arg(args, "bridge", required=False)
    if bridge:
        command.extend(["--bridge", bridge])
    for item in commands:
        command.extend(["--cmd", item])
    if file_path:
        command.extend(["--file", file_path])
    if bool_arg(args, "keep_blank", default=False):
        command.append("--keep-blank")
    wait = int_arg(args, "wait", default=0)
    if wait:
        command.extend(["--wait", str(wait)])
    expect = str_arg(args, "expect", required=False)
    if expect:
        command.extend(["--expect", expect])
    command.extend(["--output", enum_arg(args, "output", {"tail", "full", "none"}, default="tail")])
    command.extend(["--tail-lines", str(int_arg(args, "tail_lines", default=80))])
    if bool_arg(args, "all_output", default=False):
        command.append("--all-output")
    return run_live_cli(root, args, "pt730_live_term", command)


def tool_live_ping(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    command = [
        str(bin_path(root, "pt730-ping")),
        str_arg(args, "device"),
        str_arg(args, "target"),
        "--timeout",
        str(int_arg(args, "timeout", default=15)),
        "--wait",
        str(int_arg(args, "wait", default=3)),
        "--expect",
        str(int_arg(args, "expect", default=100)),
        "--tail-lines",
        str(int_arg(args, "tail_lines", default=30)),
    ]
    return run_live_cli(root, args, "pt730_live_ping", command)


def tool_live_server_inspect(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    command = [
        str(bin_path(root, "pt730-server")),
        "--timeout",
        str(int_arg(args, "timeout", default=15)),
    ]
    bridge = str_arg(args, "bridge", required=False)
    if bridge:
        command.extend(["--bridge", bridge])
    command.extend(["inspect", str_arg(args, "device"), "--port", str_arg(args, "port", required=False, default="FastEthernet0")])
    return run_live_cli(root, args, "pt730_live_server_inspect", command)


def tool_live_server_service(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    service = enum_arg(args, "service", {"http", "dns", "ftp", "tftp", "ntp", "syslog", "smtp", "pop3", "email", "dhcp"})
    enabled = required_bool_arg(args, "enabled")
    command = [str(bin_path(root, "pt730-server")), "--timeout", str(int_arg(args, "timeout", default=15))]
    bridge = str_arg(args, "bridge", required=False)
    if bridge:
        command.extend(["--bridge", bridge])
    command.extend([service, str_arg(args, "device")])
    if service == "dhcp":
        command.extend(["--port", str_arg(args, "port", required=False, default="FastEthernet0")])
    if enabled:
        command.append("--enable")
    else:
        command.append("--disable")
    if service == "email":
        domain = str_arg(args, "domain", required=False)
        if domain:
            command.extend(["--domain", domain])
    return run_live_cli(root, args, "pt730_live_server_service", command)


def tool_live_server_dns_add(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    command = [str(bin_path(root, "pt730-server")), "--timeout", str(int_arg(args, "timeout", default=15))]
    bridge = str_arg(args, "bridge", required=False)
    if bridge:
        command.extend(["--bridge", bridge])
    command.extend(["dns-add", str_arg(args, "device"), str_arg(args, "hostname"), str_arg(args, "ip")])
    if bool_arg(args, "no_enable", default=False):
        command.append("--no-enable")
    return run_live_cli(root, args, "pt730_live_server_dns_add", command)


def tool_live_server_ftp_add(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    command = [str(bin_path(root, "pt730-server")), "--timeout", str(int_arg(args, "timeout", default=15))]
    bridge = str_arg(args, "bridge", required=False)
    if bridge:
        command.extend(["--bridge", bridge])
    command.extend(["ftp-add", str_arg(args, "device"), str_arg(args, "username"), str_arg(args, "password")])
    command.extend(["--permissions", str_arg(args, "permissions", required=False, default="RWDNL")])
    if bool_arg(args, "no_enable", default=False):
        command.append("--no-enable")
    return run_live_cli(root, args, "pt730_live_server_ftp_add", command)


def tool_live_server_ftp_remove(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    command = [str(bin_path(root, "pt730-server")), "--timeout", str(int_arg(args, "timeout", default=15))]
    bridge = str_arg(args, "bridge", required=False)
    if bridge:
        command.extend(["--bridge", bridge])
    command.extend(["ftp-remove", str_arg(args, "device"), str_arg(args, "username")])
    return run_live_cli(root, args, "pt730_live_server_ftp_remove", command)


def tool_live_server_email_add(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    command = [str(bin_path(root, "pt730-server")), "--timeout", str(int_arg(args, "timeout", default=15))]
    bridge = str_arg(args, "bridge", required=False)
    if bridge:
        command.extend(["--bridge", bridge])
    command.extend(["email-add", str_arg(args, "device"), str_arg(args, "username"), str_arg(args, "password")])
    domain = str_arg(args, "domain", required=False)
    if domain:
        command.extend(["--domain", domain])
    if bool_arg(args, "no_enable", default=False):
        command.append("--no-enable")
    return run_live_cli(root, args, "pt730_live_server_email_add", command)


def tool_live_server_email_remove(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    command = [str(bin_path(root, "pt730-server")), "--timeout", str(int_arg(args, "timeout", default=15))]
    bridge = str_arg(args, "bridge", required=False)
    if bridge:
        command.extend(["--bridge", bridge])
    command.extend(["email-remove", str_arg(args, "device"), str_arg(args, "username")])
    return run_live_cli(root, args, "pt730_live_server_email_remove", command)


def tool_live_server_ntp_config(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    command = [str(bin_path(root, "pt730-server")), "--timeout", str(int_arg(args, "timeout", default=15))]
    bridge = str_arg(args, "bridge", required=False)
    if bridge:
        command.extend(["--bridge", bridge])
    command.extend(["ntp-config", str_arg(args, "device")])
    enabled = optional_bool_arg(args, "enabled")
    if enabled is True:
        command.append("--enable")
    elif enabled is False:
        command.append("--disable")
    auth = str_arg(args, "auth", required=False)
    if auth:
        if auth not in {"on", "off"}:
            raise ToolError("auth must be one of: off, on")
        command.extend(["--auth", auth])
    for key, flag in (("key_id", "--key-id"), ("md5", "--md5")):
        value = str_arg(args, key, required=False)
        if value:
            command.extend([flag, value])
    return run_live_cli(root, args, "pt730_live_server_ntp_config", command)


def tool_live_server_syslog_config(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    command = [str(bin_path(root, "pt730-server")), "--timeout", str(int_arg(args, "timeout", default=15))]
    bridge = str_arg(args, "bridge", required=False)
    if bridge:
        command.extend(["--bridge", bridge])
    command.extend(["syslog-config", str_arg(args, "device")])
    enabled = optional_bool_arg(args, "enabled")
    if enabled is True:
        command.append("--enable")
    elif enabled is False:
        command.append("--disable")
    port = optional_int_arg(args, "port")
    if port is not None:
        command.extend(["--port", str(port)])
    return run_live_cli(root, args, "pt730_live_server_syslog_config", command)


def tool_live_server_dhcp_config(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    command = [str(bin_path(root, "pt730-server")), "--timeout", str(int_arg(args, "timeout", default=15))]
    bridge = str_arg(args, "bridge", required=False)
    if bridge:
        command.extend(["--bridge", bridge])
    command.extend(["dhcp-config", str_arg(args, "device"), "--port", str_arg(args, "port", required=False, default="FastEthernet0")])
    pool_index = optional_int_arg(args, "pool_index")
    if pool_index is not None:
        command.extend(["--pool-index", str(pool_index)])
    for key, flag in (
        ("network", "--network"),
        ("mask", "--mask"),
        ("start", "--start"),
        ("end", "--end"),
        ("gateway", "--gateway"),
        ("dns", "--dns"),
    ):
        value = str_arg(args, key, required=False)
        if value:
            command.extend([flag, value])
    max_users = optional_int_arg(args, "max_users")
    if max_users is not None:
        command.extend(["--max-users", str(max_users)])
    if bool_arg(args, "enable", default=False):
        command.append("--enable")
    return run_live_cli(root, args, "pt730_live_server_dhcp_config", command)


def tool_live_ftp(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    command = [str(bin_path(root, "pt730-ftp")), str_arg(args, "client"), str_arg(args, "server")]
    command.extend(["--username", str_arg(args, "username", required=False, default="cisco")])
    command.extend(["--password", str_arg(args, "password", required=False, default="cisco")])
    for item in list_str_arg(args, "commands", required=False):
        command.extend(["--cmd", item])
    file_path = str_arg(args, "file", required=False)
    if file_path:
        command.extend(["--file", file_path])
    if bool_arg(args, "keep_blank", default=False):
        command.append("--keep-blank")
    expect = str_arg(args, "expect", required=False)
    if expect:
        command.extend(["--expect", expect])
    if bool_arg(args, "no_quit", default=False):
        command.append("--no-quit")
    bridge = str_arg(args, "bridge", required=False)
    if bridge:
        command.extend(["--bridge", bridge])
    command.extend(["--timeout", str(int_arg(args, "timeout", default=10))])
    command.extend(["--connect-wait", str(int_arg(args, "connect_wait", default=8))])
    command.extend(["--command-wait", str(int_arg(args, "command_wait", default=8))])
    command.extend(["--tail-lines", str(int_arg(args, "tail_lines", default=120))])
    return run_live_cli(root, args, "pt730_live_ftp", command)


def tool_live_sim(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    action = enum_arg(args, "action", {"status", "reset", "fast_forward", "event_list", "simple_pdu"})
    command = [str(bin_path(root, "pt730-sim")), "--timeout", str(int_arg(args, "timeout", default=10))]
    bridge = str_arg(args, "bridge", required=False)
    if bridge:
        command.extend(["--bridge", bridge])
    if action == "status":
        command.append("status")
    elif action == "reset":
        command.append("reset")
    elif action == "fast_forward":
        command.extend(["fast-forward", "--steps", str(int_arg(args, "steps", default=1))])
    elif action == "event_list":
        command.append("event-list")
        if required_bool_arg(args, "enabled"):
            command.append("--on")
        else:
            command.append("--off")
    elif action == "simple_pdu":
        command.extend(["simple-pdu", str_arg(args, "source"), str_arg(args, "target")])
    return run_live_cli(root, args, "pt730_live_sim", command)


def schema(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required or [], "additionalProperties": False}


def tool(name: str, description: str, input_schema: dict[str, Any], handler: Callable[[Path, dict[str, Any]], dict[str, Any]]) -> dict[str, Any]:
    return {"name": name, "description": description, "inputSchema": input_schema, "handler": handler}


def tools() -> list[dict[str, Any]]:
    string = {"type": "string"}
    string_array = {"type": "array", "items": string}
    boolean = {"type": "boolean"}
    integer = {"type": "integer", "minimum": 0}
    return [
        tool("pt730_capabilities", "Print PT 7.3 automation capabilities.", schema({"table": boolean, "compact": boolean}), tool_capabilities),
        tool("pt730_schema", "Print offline input schemas/examples for PT 7.3 template, IP plan, compose, config plan, pipeline, lab, or IOS template workflows.", schema({"target": {"type": "string", "enum": ["template", "ip_plan", "compose", "config_plan", "pipeline", "lab", "ios_template"]}, "compact": boolean}, ["target"]), tool_schema),
        tool("pt730_render", "Render a topology plan as mermaid, markdown, summary, svg, drawio, html, course-audit, diagram-audit, verification-json, or verification-md.", schema({"format": {"type": "string", "enum": ["mermaid", "markdown", "summary", "svg", "drawio", "html", "course-audit", "diagram-audit", "verification-json", "verification-md"]}, "plan": string, "output": string, "direction": {"type": "string", "enum": ["LR", "TD", "TB", "RL", "BT"]}, "preset": {"type": "string", "enum": ["manual", "report"]}, "theme": {"type": "string", "enum": ["light", "dark", "paper"]}, "link_labels": boolean, "model_labels": boolean, "group_by": {"type": "string", "enum": ["none", "auto", "network", "vlan", "site", "category"]}, "title": string, "legend": boolean, "strict_safety": boolean, "allow_risky": boolean}, ["format", "plan"]), tool_render),
        tool("pt730_render_bundle", "Render one topology plan into multiple offline artifacts plus a JSON manifest in one call.", schema({"plan": string, "output_dir": string, "basename": string, "formats": {"oneOf": [{"type": "array", "items": {"type": "string", "enum": ["mermaid", "svg", "drawio", "html", "markdown", "summary", "course-audit", "diagram-audit", "verification-json", "verification-md"]}}, {"type": "string"}]}, "direction": {"type": "string", "enum": ["LR", "TD", "TB", "RL", "BT"]}, "preset": {"type": "string", "enum": ["manual", "report"]}, "theme": {"type": "string", "enum": ["light", "dark", "paper"]}, "link_labels": boolean, "model_labels": boolean, "group_by": {"type": "string", "enum": ["none", "auto", "network", "vlan", "site", "category"]}, "title": string, "legend": boolean, "strict_safety": boolean, "allow_risky": boolean}, ["plan", "output_dir"]), tool_render_bundle),
        tool("pt730_verification_plan", "Generate an offline JSON or Markdown live/manual validation checklist for a topology plan.", schema({"plan": string, "format": {"type": "string", "enum": ["json", "markdown"]}, "output": string, "compact": boolean, "max_hosts": integer, "max_service_targets": integer, "strict_safety": boolean, "allow_risky": boolean}, ["plan"]), tool_verification_plan),
        tool("pt730_lab_template", "Generate a full offline lab bundle from one template spec JSON: topology, safety report, render bundle, configs, and manifest.", schema({"spec": string, "output_dir": string, "strict_safety": boolean, "compact": boolean}, ["spec", "output_dir"]), tool_lab_template),
        tool("pt730_lab_plan", "Generate a full offline lab bundle from an existing topology plan JSON: topology copy, safety report, render bundle, configs, and manifest.", schema({"plan": string, "output_dir": string, "name": string, "basename": string, "formats": {"oneOf": [{"type": "array", "items": {"type": "string", "enum": ["mermaid", "svg", "drawio", "html", "markdown", "summary", "course-audit", "diagram-audit", "verification-json", "verification-md"]}}, {"type": "string"}]}, "direction": {"type": "string", "enum": ["LR", "TD", "TB", "RL", "BT"]}, "preset": {"type": "string", "enum": ["manual", "report"]}, "theme": {"type": "string", "enum": ["light", "dark", "paper"]}, "link_labels": boolean, "model_labels": boolean, "group_by": {"type": "string", "enum": ["none", "auto", "network", "vlan", "site", "category"]}, "title": string, "legend": boolean, "strict_safety": boolean, "export_configs": boolean, "config_source": string, "compact": boolean}, ["plan", "output_dir"]), tool_lab_plan),
        tool("pt730_lab_report", "Generate a Markdown coursework/deliverable index from a pt730-lab manifest.json.", schema({"manifest": string, "output": string, "title": string, "compact": boolean}, ["manifest"]), tool_lab_report),
        tool("pt730_safety_plan", "Check a topology JSON plan offline before live Packet Tracer use.", schema({"plan": string, "strict": boolean}, ["plan"]), tool_safety_plan),
        tool("pt730_safety_js", "Check Packet Tracer JavaScript offline before passing it to pt730-eval.", schema({"code": string, "file": string, "strict": boolean}), tool_safety_js),
        tool("pt730_safety_policy", "Print the current PT 7.3 automation safety policy.", schema({}), tool_safety_policy),
        tool("pt730_catalog", "Query the offline Packet Tracer catalog with local PT 7.3 safety overlay.", schema({"action": {"type": "string", "enum": ["devices", "device", "ports", "modules", "module", "cables", "infer_cable", "aliases"]}, "model": string, "module": string, "category": string, "category_a": string, "category_b": string, "status": string, "include_ports": boolean, "table": boolean}, ["action"]), tool_catalog),
        tool("pt730_template_lan_star", "Generate a router-switch-PC/server star LAN topology JSON.", schema({"name": string, "pcs": integer, "servers": integer, "network": string, "gateway": string, "dns": string, "layout_style": {"type": "string", "enum": ["auto", "hierarchical", "campus", "lan", "ring", "grid"]}, "no_layout": boolean, "compact": boolean, "output": string}), tool_template_lan_star),
        tool("pt730_template_wireless_lan", "Generate a router-switch-AP-laptop wireless LAN topology JSON with safe PT 7.3 models.", schema({"name": string, "aps": integer, "laptops": integer, "servers": integer, "network": string, "gateway": string, "dns": string, "ssid": string, "layout_style": {"type": "string", "enum": ["auto", "hierarchical", "campus", "lan", "ring", "grid"]}, "no_layout": boolean, "compact": boolean, "output": string}), tool_template_wireless_lan),
        tool("pt730_template_vlan_router_on_stick", "Generate a router-on-a-stick VLAN trunk lab topology JSON with router subinterfaces.", schema({"name": string, "vlans": integer, "hosts_per_vlan": integer, "servers_per_vlan": integer, "address_pool": string, "vlan_prefix": integer, "vlan_base": integer, "native_vlan": integer, "domain": string, "client_addressing": {"type": "string", "enum": ["static", "dhcp"]}, "layout_style": {"type": "string", "enum": ["auto", "hierarchical", "campus", "lan", "ring", "grid"]}, "no_layout": boolean, "compact": boolean, "output": string}), tool_template_vlan_router_on_stick),
        tool("pt730_template_edge_security", "Generate an ISP edge NAT/ACL/DMZ security lab topology JSON.", schema({"name": string, "inside_hosts": integer, "dmz_servers": integer, "internet_hosts": integer, "inside_network": string, "dmz_network": string, "wan_network": string, "internet_network": string, "domain": string, "layout_style": {"type": "string", "enum": ["auto", "hierarchical", "campus", "lan", "ring", "grid"]}, "no_layout": boolean, "compact": boolean, "output": string}), tool_template_edge_security),
        tool("pt730_template_router_ring", "Generate a serial router ring topology JSON with RIP configs.", schema({"name": string, "routers": integer, "interconnect_pool": string, "layout_style": {"type": "string", "enum": ["auto", "hierarchical", "campus", "lan", "ring", "grid"]}, "no_layout": boolean, "compact": boolean, "output": string}), tool_template_router_ring),
        tool("pt730_template_wan_ring", "Generate a multi-site serial WAN ring with per-site LANs, services, and optional routing configs.", schema({"name": string, "sites": integer, "hosts_per_site": integer, "servers_per_site": integer, "interconnect_pool": string, "lan_pool": string, "lan_prefix": integer, "routing": {"type": "string", "enum": ["none", "rip", "ospf", "static"]}, "layout_style": {"type": "string", "enum": ["auto", "hierarchical", "campus", "lan", "ring", "grid"]}, "no_layout": boolean, "compact": boolean, "output": string}), tool_template_wan_ring),
        tool("pt730_template_campus", "Generate a representative core/access/server campus topology JSON with optional L3 configs.", schema({"name": string, "cores": integer, "segments": integer, "hosts_per_segment": integer, "access_switches_per_segment": integer, "servers": integer, "address_pool": string, "segment_prefix": integer, "server_network": string, "server_vlan": integer, "vlan_base": integer, "interconnect_pool": string, "l3": boolean, "routing": {"type": "string", "enum": ["none", "rip", "ospf", "static"]}, "layout_style": {"type": "string", "enum": ["auto", "hierarchical", "campus", "lan", "ring", "grid"]}, "no_layout": boolean, "compact": boolean, "output": string}), tool_template_campus),
        tool("pt730_template_redundant_campus", "Generate a dual-core redundant campus topology with dual-homed access, HSRP, STP, DHCP relay/pools, services, and optional RIP/OSPF configs.", schema({"name": string, "segments": integer, "hosts_per_segment": integer, "access_switches_per_segment": integer, "servers": integer, "address_pool": string, "segment_prefix": integer, "server_network": string, "server_vlan": integer, "vlan_base": integer, "routing": {"type": "string", "enum": ["none", "rip", "ospf"]}, "layout_style": {"type": "string", "enum": ["auto", "hierarchical", "campus", "lan", "ring", "grid"]}, "no_layout": boolean, "compact": boolean, "output": string}), tool_template_redundant_campus),
        tool("pt730_template_enterprise_edge", "Generate an integrated enterprise HQ VLAN/server/DMZ/ISP/branch WAN topology with NAT/ACL, services, and optional RIP/OSPF/static configs.", schema({"name": string, "campus_vlans": integer, "hosts_per_vlan": integer, "campus_servers": integer, "branches": integer, "branch_hosts": integer, "dmz_servers": integer, "internet_hosts": integer, "campus_pool": string, "campus_prefix": integer, "server_network": string, "server_vlan": integer, "vlan_base": integer, "branch_pool": string, "branch_prefix": integer, "wan_pool": string, "dmz_network": string, "isp_wan_network": string, "internet_network": string, "domain": string, "routing": {"type": "string", "enum": ["none", "rip", "ospf", "static"]}, "layout_style": {"type": "string", "enum": ["auto", "hierarchical", "campus", "lan", "ring", "grid"]}, "no_layout": boolean, "compact": boolean, "output": string}), tool_template_enterprise_edge),
        tool("pt730_ip_plan_campus", "Plan VLSM campus subnets from a compact IP planning spec.", schema({"spec": string, "compact": boolean, "output": string}, ["spec"]), tool_ip_plan_campus),
        tool("pt730_compose_campus", "Compose a high-level campus topology spec into topology JSON.", schema({"spec": string, "segments_from_ip_plan": string, "no_layout": boolean, "layout_style": {"type": "string", "enum": ["auto", "hierarchical", "campus", "lan", "ring", "grid"]}, "compact": boolean, "output": string}, ["spec"]), tool_compose_campus),
        tool("pt730_config_plan_campus", "Generate IOS config records from topology VLAN/L3 metadata.", schema({"plan": string, "ios_only": boolean, "l3": boolean, "routing": {"type": "string", "enum": ["none", "rip", "ospf", "static"]}, "compact": boolean, "output": string}, ["plan"]), tool_config_plan_campus),
        tool("pt730_export_configs", "Export topology ios_configs into per-device .cfg files.", schema({"plan": string, "output_dir": string, "source": string, "compact": boolean}, ["plan", "output_dir"]), tool_export_configs),
        tool("pt730_layout", "Assign deterministic coordinates to a topology plan.", schema({"plan": string, "style": {"type": "string", "enum": ["auto", "hierarchical", "campus", "lan", "ring", "grid"]}, "preserve_existing": boolean, "canvas_width": integer, "canvas_height": integer, "spacing_x": integer, "spacing_y": integer, "margin": integer, "compact": boolean, "output": string}, ["plan"]), tool_layout),
        tool("pt730_ios_template_render", "Render high-level IOS template JSON into commands or topology ios_configs.", schema({"spec": string, "topology_json": boolean, "output": string}, ["spec"]), tool_ios_template_render),
        tool("pt730_pipeline_campus", "Run IP plan, compose, config planning, layout, safety, rendering, and config export offline.", schema({"compose_spec": string, "ip_plan": string, "output_dir": string, "routing": {"type": "string", "enum": ["none", "rip", "ospf", "static"]}, "layout_style": {"type": "string", "enum": ["auto", "hierarchical", "campus", "lan", "ring", "grid"]}, "strict_safety": boolean, "course_audit": boolean, "compact": boolean}, ["compose_spec", "output_dir"]), tool_pipeline_campus),
        tool("pt730_topo_summarize_query", "Summarize a saved pt730-topo query JSON file offline.", schema({"query_json": string}, ["query_json"]), tool_topo_summarize_query),
        tool("pt730_topo_export", "Export raw and summarized topology query JSON; offline with from_query, live otherwise.", schema({"from_query": string, "raw_out": string, "summary_out": string, "markdown_out": string, "bridge": string, "dry_run": boolean, "allow_live": boolean, "timeout": integer}, ["raw_out", "summary_out"]), tool_topo_export),
        tool("pt730_models_manifest", "Print grouped PT 7.3 model safety registry.", schema({}), tool_models_manifest),
        tool("pt730_models_queue", "Print the guarded common-model validation queue.", schema({"include_risky": boolean, "include_blocked": boolean}), tool_models_queue),
        tool("pt730_models_probe_plan", "Generate a guarded one-model validation topology plan.", schema({"model": string, "allow_risky": boolean, "allow_blocked": boolean}, ["model"]), tool_models_probe_plan),
        tool("pt730_models_validate", "Run guarded model validation dry_run, or live validation with allow_live=true.", schema({"model": string, "dry_run": boolean, "live": boolean, "allow_live": boolean, "allow_risky": boolean, "allow_blocked": boolean, "bridge": string, "timeout": integer, "record_failure_status": {"type": "string", "enum": ["risky", "blocked"]}}, ["model"]), tool_models_validate),
        tool("pt730_models_validate_batch", "Run guarded batch model validation dry_run, or live validation with allow_live=true.", schema({"dry_run": boolean, "live": boolean, "allow_live": boolean, "limit": integer, "include_risky": boolean, "include_blocked": boolean, "bridge": string, "timeout": integer, "keep_going": boolean, "record_failures": {"type": "string", "enum": ["risky", "blocked"]}}), tool_models_validate_batch),
        tool("pt730_models_record", "Record model validation metadata; requires allow_write=true unless dry_run=true.", schema({"model": string, "status": {"type": "string", "enum": ["safe", "risky", "blocked", "unverified"]}, "reason": string, "evidence": string_array, "save_reopen": boolean, "dry_run": boolean, "allow_write": boolean}, ["model", "status"]), tool_models_record),
        tool("pt730_live_count", "Count devices/links on a live Packet Tracer canvas. Requires allow_live=true.", schema({"allow_live": boolean, "timeout": integer}, ["allow_live"]), tool_live_count),
        tool("pt730_live_query", "Query the live Packet Tracer canvas. Requires allow_live=true.", schema({"allow_live": boolean, "summary": boolean, "timeout": integer}, ["allow_live"]), tool_live_query),
        tool("pt730_live_apply", "Apply a topology plan to live Packet Tracer, or run offline dry_run without live access.", schema({"plan": string, "dry_run": boolean, "allow_live": boolean, "replace": boolean, "batch_size": integer, "allow_risky": boolean, "strict_safety": boolean, "timeout": integer}, ["plan"]), tool_live_apply),
        tool("pt730_live_save_as", "Save the current live Packet Tracer file to a Linux path. Requires allow_live=true.", schema({"allow_live": boolean, "path": string, "direct": boolean, "timeout": integer}, ["allow_live", "path"]), tool_live_save_as),
        tool("pt730_live_app", "Run guarded Packet Tracer appWindow helpers, or return a safe dry_run command preview.", schema({"action": {"type": "string", "enum": ["count", "save", "new", "save_as", "open", "screenshot"]}, "path": string, "direct": boolean, "dry_run": boolean, "allow_live": boolean, "timeout": integer}, ["action"]), tool_live_app),
        tool("pt730_live_bridge", "Run guarded localhost bridge lifecycle helpers, or return a safe dry_run command preview.", schema({"action": {"type": "string", "enum": ["start", "stop", "restart", "status", "bootstrap", "logs"]}, "lines": string, "dry_run": boolean, "allow_live": boolean}, ["action"]), tool_live_bridge),
        tool("pt730_live_launch", "Run guarded Packet Tracer tmux launcher helpers, or return a safe dry_run command preview.", schema({"action": {"type": "string", "enum": ["start", "stop", "restart", "status", "logs"]}, "lines": string, "dry_run": boolean, "allow_live": boolean}, ["action"]), tool_live_launch),
        tool("pt730_live_recover", "Run guarded Packet Tracer bridge recovery, or return a safe dry_run command preview.", schema({"wait": integer, "notify": boolean, "dry_run": boolean, "allow_live": boolean}), tool_live_recover),
        tool("pt730_live_eval", "Evaluate guarded JavaScript in live Packet Tracer, or return a safe dry_run command preview.", schema({"code": string, "file": string, "expr": boolean, "allow_risky": boolean, "bridge": string, "dry_run": boolean, "allow_live": boolean, "timeout": integer}), tool_live_eval),
        tool("pt730_live_smoke", "Run the PT 7.3 bridge smoke workflow, or return a safe dry_run command preview.", schema({"new": boolean, "dhcp": boolean, "strict_safety": boolean, "no_apply": boolean, "plan": string, "save_as": string, "dry_run": boolean, "allow_live": boolean}), tool_live_smoke),
        tool("pt730_live_ios", "Send IOS commands to a live router/switch, or return a safe dry_run command preview.", schema({"device": string, "commands": string_array, "file": string, "init_dialog": boolean, "save": boolean, "keep_comments": boolean, "output": {"type": "string", "enum": ["tail", "full", "none"]}, "tail_lines": integer, "dry_run": boolean, "allow_live": boolean, "timeout": integer}, ["device"]), tool_live_ios),
        tool("pt730_live_pc_inspect", "Inspect live PC/server/laptop port IP state, or return a safe dry_run command preview.", schema({"device": string, "port": string, "bridge": string, "dry_run": boolean, "allow_live": boolean, "timeout": integer}, ["device"]), tool_live_pc_inspect),
        tool("pt730_live_pc_static", "Set a static IPv4 address on a live PC/server port, or return a safe dry_run command preview.", schema({"device": string, "port": string, "ip": string, "mask": string, "gateway": string, "dns": string, "bridge": string, "dry_run": boolean, "allow_live": boolean, "timeout": integer}, ["device", "ip", "mask"]), tool_live_pc_static),
        tool("pt730_live_pc_dhcp", "Enable or renew DHCP client mode on a live PC/server/laptop port, or return a safe dry_run command preview.", schema({"device": string, "port": string, "renew": boolean, "wait": integer, "expect_network": string, "bridge": string, "dry_run": boolean, "allow_live": boolean, "timeout": integer}, ["device"]), tool_live_pc_dhcp),
        tool("pt730_live_term", "Send generic terminal commands to a live device, optionally waiting for expected output, or return a safe dry_run command preview.", schema({"device": string, "commands": string_array, "file": string, "keep_blank": boolean, "wait": integer, "expect": string, "output": {"type": "string", "enum": ["tail", "full", "none"]}, "tail_lines": integer, "all_output": boolean, "bridge": string, "dry_run": boolean, "allow_live": boolean, "timeout": integer}, ["device"]), tool_live_term),
        tool("pt730_live_ping", "Run an IOS ping from a live router/switch, or return a safe dry_run command preview.", schema({"device": string, "target": string, "wait": integer, "expect": integer, "tail_lines": integer, "dry_run": boolean, "allow_live": boolean, "timeout": integer}, ["device", "target"]), tool_live_ping),
        tool("pt730_live_server_inspect", "Inspect live Server-PT service state, or return a safe dry_run command preview.", schema({"device": string, "port": string, "bridge": string, "dry_run": boolean, "allow_live": boolean, "timeout": integer}, ["device"]), tool_live_server_inspect),
        tool("pt730_live_server_service", "Enable or disable a live Server-PT service, or return a safe dry_run command preview.", schema({"device": string, "service": {"type": "string", "enum": ["http", "dns", "ftp", "tftp", "ntp", "syslog", "smtp", "pop3", "email", "dhcp"]}, "enabled": boolean, "domain": string, "port": string, "bridge": string, "dry_run": boolean, "allow_live": boolean, "timeout": integer}, ["device", "service", "enabled"]), tool_live_server_service),
        tool("pt730_live_server_dns_add", "Add a live Server-PT DNS A record, or return a safe dry_run command preview.", schema({"device": string, "hostname": string, "ip": string, "no_enable": boolean, "bridge": string, "dry_run": boolean, "allow_live": boolean, "timeout": integer}, ["device", "hostname", "ip"]), tool_live_server_dns_add),
        tool("pt730_live_server_ftp_add", "Add or replace a live Server-PT FTP user, or return a safe dry_run command preview.", schema({"device": string, "username": string, "password": string, "permissions": string, "no_enable": boolean, "bridge": string, "dry_run": boolean, "allow_live": boolean, "timeout": integer}, ["device", "username", "password"]), tool_live_server_ftp_add),
        tool("pt730_live_server_ftp_remove", "Remove a live Server-PT FTP user, or return a safe dry_run command preview.", schema({"device": string, "username": string, "bridge": string, "dry_run": boolean, "allow_live": boolean, "timeout": integer}, ["device", "username"]), tool_live_server_ftp_remove),
        tool("pt730_live_server_email_add", "Add or replace a live Server-PT email user, or return a safe dry_run command preview.", schema({"device": string, "username": string, "password": string, "domain": string, "no_enable": boolean, "bridge": string, "dry_run": boolean, "allow_live": boolean, "timeout": integer}, ["device", "username", "password"]), tool_live_server_email_add),
        tool("pt730_live_server_email_remove", "Remove a live Server-PT email user, or return a safe dry_run command preview.", schema({"device": string, "username": string, "bridge": string, "dry_run": boolean, "allow_live": boolean, "timeout": integer}, ["device", "username"]), tool_live_server_email_remove),
        tool("pt730_live_server_ntp_config", "Configure live Server-PT NTP service/auth fields, or return a safe dry_run command preview.", schema({"device": string, "enabled": boolean, "auth": {"type": "string", "enum": ["on", "off"]}, "key_id": string, "md5": string, "bridge": string, "dry_run": boolean, "allow_live": boolean, "timeout": integer}, ["device"]), tool_live_server_ntp_config),
        tool("pt730_live_server_syslog_config", "Configure live Server-PT Syslog service/port, or return a safe dry_run command preview.", schema({"device": string, "enabled": boolean, "port": integer, "bridge": string, "dry_run": boolean, "allow_live": boolean, "timeout": integer}, ["device"]), tool_live_server_syslog_config),
        tool("pt730_live_server_dhcp_config", "Configure a live Server-PT DHCP pool, or return a safe dry_run command preview.", schema({"device": string, "port": string, "pool_index": integer, "network": string, "mask": string, "start": string, "end": string, "gateway": string, "dns": string, "max_users": integer, "enable": boolean, "bridge": string, "dry_run": boolean, "allow_live": boolean, "timeout": integer}, ["device"]), tool_live_server_dhcp_config),
        tool("pt730_live_ftp", "Run a Packet Tracer PC FTP client session, or return a safe dry_run command preview.", schema({"client": string, "server": string, "username": string, "password": string, "commands": string_array, "file": string, "keep_blank": boolean, "expect": string, "no_quit": boolean, "bridge": string, "connect_wait": integer, "command_wait": integer, "tail_lines": integer, "dry_run": boolean, "allow_live": boolean, "timeout": integer}, ["client", "server"]), tool_live_ftp),
        tool("pt730_live_sim", "Control limited Packet Tracer simulation/PDU surfaces, or return a safe dry_run command preview.", schema({"action": {"type": "string", "enum": ["status", "reset", "fast_forward", "event_list", "simple_pdu"]}, "source": string, "target": string, "enabled": boolean, "steps": integer, "bridge": string, "dry_run": boolean, "allow_live": boolean, "timeout": integer}, ["action"]), tool_live_sim),
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
