#!/usr/bin/env python3
"""Generate complete offline Packet Tracer 7.3.0 lab bundles from one JSON spec."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from config_plan_cli import export_config_files
from render_cli import BUNDLE_DEFAULT_FORMATS, RENDER_GROUP_BY, RENDER_THEMES, RenderOptions, parse_bundle_formats, render_bundle
from safety_cli import check_plan, summarize
from template_cli import (
    campus,
    edge_security,
    enterprise_edge,
    lan_star,
    redundant_campus,
    router_ring,
    schema as template_schema,
    vlan_router_on_stick,
    wan_ring,
    wireless_lan,
)


@dataclass(frozen=True)
class TemplateDefinition:
    function: Callable[..., dict[str, Any]]
    defaults: dict[str, Any]


TEMPLATES: dict[str, TemplateDefinition] = {
    "lan-star": TemplateDefinition(
        lan_star,
        {
            "name": "LAN",
            "pcs": 2,
            "servers": 0,
            "network": "192.168.10.0/24",
            "gateway": None,
            "dns": None,
            "layout_style": "lan",
            "no_layout": False,
        },
    ),
    "wireless-lan": TemplateDefinition(
        wireless_lan,
        {
            "name": "WIFI",
            "aps": 1,
            "laptops": 3,
            "servers": 1,
            "network": "192.168.80.0/24",
            "gateway": None,
            "dns": None,
            "ssid": "PT730-LAB",
            "layout_style": "lan",
            "no_layout": False,
        },
    ),
    "vlan-router-on-stick": TemplateDefinition(
        vlan_router_on_stick,
        {
            "name": "ROAS",
            "vlans": 3,
            "hosts_per_vlan": 2,
            "servers_per_vlan": 0,
            "address_pool": "192.168.20.0/22",
            "vlan_prefix": 24,
            "vlan_base": 10,
            "native_vlan": None,
            "domain": "roas.local",
            "client_addressing": "static",
            "layout_style": "hierarchical",
            "no_layout": False,
        },
    ),
    "edge-security": TemplateDefinition(
        edge_security,
        {
            "name": "EDGE",
            "inside_hosts": 3,
            "dmz_servers": 2,
            "internet_hosts": 1,
            "inside_network": "192.168.10.0/24",
            "dmz_network": "172.16.10.0/24",
            "wan_network": "203.0.113.0/30",
            "internet_network": "198.51.100.0/24",
            "domain": "edge.local",
            "layout_style": "hierarchical",
            "no_layout": False,
        },
    ),
    "router-ring": TemplateDefinition(
        router_ring,
        {
            "name": "RING",
            "routers": 4,
            "interconnect_pool": "10.20.0.0/28",
            "layout_style": "ring",
            "no_layout": False,
        },
    ),
    "wan-ring": TemplateDefinition(
        wan_ring,
        {
            "name": "WAN",
            "sites": 3,
            "hosts_per_site": 2,
            "servers_per_site": 1,
            "interconnect_pool": "10.30.0.0/28",
            "lan_pool": "192.168.100.0/22",
            "lan_prefix": 24,
            "routing": "rip",
            "layout_style": "ring",
            "no_layout": False,
        },
    ),
    "campus": TemplateDefinition(
        campus,
        {
            "name": "CAMPUS",
            "cores": 2,
            "segments": 4,
            "hosts_per_segment": 2,
            "access_switches_per_segment": 1,
            "servers": 2,
            "address_pool": "192.168.0.0/21",
            "segment_prefix": 24,
            "server_network": "172.16.1.0/26",
            "server_vlan": 10,
            "vlan_base": 20,
            "interconnect_pool": "10.10.0.0/24",
            "l3": False,
            "routing": "none",
            "layout_style": "campus",
            "no_layout": False,
        },
    ),
    "redundant-campus": TemplateDefinition(
        redundant_campus,
        {
            "name": "REDUNDANT",
            "segments": 4,
            "hosts_per_segment": 2,
            "access_switches_per_segment": 1,
            "servers": 4,
            "address_pool": "192.168.0.0/21",
            "segment_prefix": 24,
            "server_network": "172.16.1.0/26",
            "server_vlan": 10,
            "vlan_base": 20,
            "routing": "ospf",
            "layout_style": "campus",
            "no_layout": False,
        },
    ),
    "enterprise-edge": TemplateDefinition(
        enterprise_edge,
        {
            "name": "ENTERPRISE",
            "campus_vlans": 3,
            "hosts_per_vlan": 2,
            "campus_servers": 4,
            "branches": 2,
            "branch_hosts": 2,
            "dmz_servers": 2,
            "internet_hosts": 1,
            "campus_pool": "192.168.0.0/21",
            "campus_prefix": 24,
            "server_network": "172.16.1.0/26",
            "server_vlan": 10,
            "vlan_base": 20,
            "branch_pool": "10.40.0.0/22",
            "branch_prefix": 24,
            "wan_pool": "10.60.0.0/28",
            "dmz_network": "172.16.10.0/24",
            "isp_wan_network": "203.0.113.0/30",
            "internet_network": "198.51.100.0/24",
            "domain": "enterprise.local",
            "routing": "ospf",
            "layout_style": "campus",
            "no_layout": False,
        },
    ),
}

TOP_LEVEL_KEYS = {"name", "template", "template_options", "render", "strict_safety", "export_configs", "config_source", "compact"}
RENDER_KEYS = {"basename", "formats", "direction", "theme", "link_labels", "model_labels", "group_by"}


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: JSON root must be an object")
    return data


def write_json(path: Path, value: Any, *, compact: bool) -> None:
    text = json.dumps(value, ensure_ascii=False, indent=None if compact else 2, separators=(",", ":") if compact else None) + "\n"
    path.write_text(text, encoding="utf-8")


def rel(base: Path, path: Path) -> str:
    try:
        return str(path.relative_to(base))
    except ValueError:
        return str(path)


def _normalize_object_keys(raw: dict[str, Any], allowed: set[str], *, section: str) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in raw.items():
        if not isinstance(key, str):
            raise ValueError(f"{section}: option names must be strings")
        name = key.replace("-", "_")
        if name not in allowed:
            raise ValueError(f"{section}: unknown option {key!r}; allowed options: {', '.join(sorted(allowed))}")
        if name in normalized:
            raise ValueError(f"{section}: duplicate option after normalization: {key!r}")
        normalized[name] = value
    return normalized


def _bool_value(spec: dict[str, Any], key: str, *, default: bool) -> bool:
    if key not in spec:
        return default
    value = spec[key]
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be a boolean")
    return value


def _string_value(spec: dict[str, Any], key: str, *, default: str = "") -> str:
    if key not in spec or spec[key] is None:
        return default
    value = spec[key]
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value


def _safe_basename(value: str) -> str:
    basename = value.strip()
    if not basename or basename in {".", ".."} or "/" in basename or "\\" in basename:
        raise ValueError("render.basename must be a filename stem, not a path")
    return basename


def _parse_formats(value: Any) -> list[str]:
    if value is None:
        return list(BUNDLE_DEFAULT_FORMATS)
    if isinstance(value, str):
        return parse_bundle_formats(value)
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return parse_bundle_formats(",".join(value))
    raise ValueError("render.formats must be a comma-separated string or an array of strings")


def _render_settings(spec: dict[str, Any], *, lab_name: str, template_name: str) -> dict[str, Any]:
    raw = spec.get("render", {})
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError("render must be an object when provided")
    render = _normalize_object_keys(raw, RENDER_KEYS, section="render")

    basename = _safe_basename(_string_value(render, "basename", default=lab_name or template_name))
    direction = _string_value(render, "direction", default="LR")
    if direction not in {"LR", "TD", "TB", "RL", "BT"}:
        raise ValueError("render.direction must be one of: LR, TD, TB, RL, BT")
    theme = _string_value(render, "theme", default="light")
    if theme not in RENDER_THEMES:
        raise ValueError(f"render.theme must be one of: {', '.join(RENDER_THEMES)}")
    group_by = _string_value(render, "group_by", default="none")
    if group_by not in RENDER_GROUP_BY:
        raise ValueError(f"render.group_by must be one of: {', '.join(RENDER_GROUP_BY)}")
    link_labels = _bool_value(render, "link_labels", default=True)
    model_labels = _bool_value(render, "model_labels", default=True)
    return {
        "basename": basename,
        "formats": _parse_formats(render.get("formats")),
        "direction": direction,
        "options": RenderOptions(theme=theme, link_labels=link_labels, model_labels=model_labels, group_by=group_by),
    }


def _template_kwargs(spec: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    template_name = spec.get("template")
    if not isinstance(template_name, str) or not template_name:
        raise ValueError("template must be a non-empty string")
    if template_name not in TEMPLATES:
        raise ValueError(f"unknown template {template_name!r}; available templates: {', '.join(sorted(TEMPLATES))}")
    raw_options = spec.get("template_options", {})
    if raw_options is None:
        raw_options = {}
    if not isinstance(raw_options, dict):
        raise ValueError("template_options must be an object when provided")
    definition = TEMPLATES[template_name]
    overrides = _normalize_object_keys(raw_options, set(definition.defaults), section="template_options")
    kwargs = dict(definition.defaults)
    kwargs.update(overrides)
    return template_name, kwargs


def schema() -> dict[str, Any]:
    source_schema = template_schema()
    return {
        "commands": ["schema", "template"],
        "template": {
            "description": "Generate a full offline lab bundle from one compact JSON spec.",
            "required": ["template"],
            "optional": ["name", "template_options", "render", "strict_safety", "export_configs", "config_source", "compact"],
            "render_options": {
                "basename": "file stem for render artifacts; defaults to name or template",
                "formats": list(BUNDLE_DEFAULT_FORMATS),
                "direction": ["LR", "TD", "TB", "RL", "BT"],
                "theme": list(RENDER_THEMES),
                "link_labels": True,
                "model_labels": True,
                "group_by": list(RENDER_GROUP_BY),
            },
            "outputs": ["topology.json", "safety.json", "render/<basename>.*", "configs/*.cfg", "manifest.json"],
        },
        "templates": {
            name: {
                "description": source_schema["templates"].get(name, {}).get("description", ""),
                "options": sorted(definition.defaults),
                "defaults": definition.defaults,
            }
            for name, definition in TEMPLATES.items()
        },
        "example": {
            "name": "enterprise-demo",
            "template": "enterprise-edge",
            "template_options": {
                "name": "ENT",
                "campus_vlans": 3,
                "hosts_per_vlan": 2,
                "campus_servers": 4,
                "branches": 2,
                "branch_hosts": 2,
                "dmz_servers": 2,
                "routing": "ospf",
                "layout_style": "campus",
            },
            "render": {"basename": "enterprise-demo", "formats": ["svg", "drawio", "html", "markdown", "summary"], "theme": "paper", "group_by": "auto"},
            "strict_safety": False,
            "export_configs": True,
        },
    }


def lab_template(spec_path: Path, *, output_dir: Path, strict_safety: bool, compact: bool) -> tuple[dict[str, Any], int]:
    spec = load_json(spec_path)
    unknown = set(spec) - TOP_LEVEL_KEYS
    if unknown:
        raise ValueError(f"unknown top-level field(s): {', '.join(sorted(unknown))}")

    lab_name = _string_value(spec, "name")
    template_name, kwargs = _template_kwargs(spec)
    strict = strict_safety or _bool_value(spec, "strict_safety", default=False)
    compact_output = compact or _bool_value(spec, "compact", default=False)
    export_configs = _bool_value(spec, "export_configs", default=True)
    config_source = _string_value(spec, "config_source")
    render = _render_settings(spec, lab_name=lab_name, template_name=template_name)

    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts: dict[str, str] = {}

    plan = TEMPLATES[template_name].function(**kwargs)
    metadata = plan.setdefault("metadata", {})
    if isinstance(metadata, dict):
        metadata["lab_bundle"] = {"name": lab_name, "template": template_name}

    topology_out = output_dir / "topology.json"
    write_json(topology_out, plan, compact=compact_output)
    artifacts["topology"] = rel(output_dir, topology_out)

    safety_report = summarize("plan", check_plan(plan), strict=strict)
    safety_out = output_dir / "safety.json"
    write_json(safety_out, safety_report, compact=compact_output)
    artifacts["safety"] = rel(output_dir, safety_out)

    render_dir = output_dir / "render"
    render_manifest, render_code = render_bundle(
        plan,
        plan_path=topology_out,
        output_dir=render_dir,
        basename=render["basename"],
        formats=render["formats"],
        options=render["options"],
        direction=render["direction"],
    )
    artifacts["render"] = rel(output_dir, render_dir)
    artifacts["render_manifest"] = rel(output_dir, render_dir / f"{render['basename']}.manifest.json")

    config_manifest: dict[str, Any] = {"kind": "pt730-config-files", "count": 0, "files": []}
    if export_configs:
        configs_dir = output_dir / "configs"
        config_manifest = export_config_files(plan, configs_dir, source=config_source or None)
        artifacts["configs"] = rel(output_dir, configs_dir)

    manifest = {
        "kind": "pt730-lab-template-bundle",
        "packet_tracer_version": "7.3.0",
        "name": lab_name,
        "template": template_name,
        "output_dir": str(output_dir),
        "inputs": {
            "spec": str(spec_path),
            "template_options": kwargs,
            "strict_safety": strict,
            "export_configs": export_configs,
            "config_source": config_source,
        },
        "artifacts": artifacts,
        "safety": safety_report,
        "render_bundle": render_manifest,
        "config_files": config_manifest,
    }

    manifest_out = output_dir / "manifest.json"
    artifacts["manifest"] = rel(output_dir, manifest_out)
    manifest["artifacts"] = artifacts
    write_json(manifest_out, manifest, compact=compact_output)

    code = 0 if safety_report["ok"] and render_code == 0 else 1
    return manifest, code


def emit_json(value: Any, *, compact: bool) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=None if compact else 2, separators=(",", ":") if compact else None))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pt730-lab", description=__doc__)
    parser.add_argument("--compact", action="store_true", help="emit compact JSON to stdout and output files")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("schema", help="print lab bundle schema")

    template_p = sub.add_parser("template", help="generate a complete offline lab bundle from a template spec")
    template_p.add_argument("spec", type=Path)
    template_p.add_argument("--output-dir", type=Path, required=True)
    template_p.add_argument("--strict-safety", action="store_true", help="treat plan safety warnings as failures")

    args = parser.parse_args(argv)
    try:
        if args.cmd == "schema":
            emit_json(schema(), compact=args.compact)
            return 0
        if args.cmd == "template":
            manifest, code = lab_template(args.spec, output_dir=args.output_dir, strict_safety=args.strict_safety, compact=args.compact)
            emit_json(manifest, compact=args.compact)
            return code
        raise ValueError(f"unknown command: {args.cmd}")
    except Exception as exc:  # noqa: BLE001
        print(f"pt730-lab: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
