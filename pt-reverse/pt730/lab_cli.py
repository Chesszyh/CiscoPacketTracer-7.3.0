#!/usr/bin/env python3
"""Generate complete offline Packet Tracer 7.3.0 lab bundles and reports."""

from __future__ import annotations

import argparse
import copy
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
RENDER_KEYS = {"basename", "formats", "direction", "theme", "link_labels", "model_labels", "group_by", "title", "legend"}


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


def markdown_cell(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", "<br>")


def markdown_table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    lines.extend("| " + " | ".join(markdown_cell(value) for value in row) + " |" for row in rows)
    return lines


def manifest_base_dir(manifest: dict[str, Any], manifest_path: Path) -> Path:
    output_dir = manifest.get("output_dir")
    if isinstance(output_dir, str) and output_dir:
        path = Path(output_dir)
        if path.is_absolute():
            return path
        return (manifest_path.parent / path).resolve()
    return manifest_path.parent.resolve()


def resolve_manifest_path(base_dir: Path, value: Any) -> Path | None:
    if not isinstance(value, str) or not value:
        return None
    path = Path(value)
    return path if path.is_absolute() else base_dir / path


def display_manifest_path(base_dir: Path, value: Any) -> str:
    path = resolve_manifest_path(base_dir, value)
    if path is None:
        return ""
    return rel(base_dir, path)


def path_status(path: Path | None) -> str:
    return "present" if path is not None and path.exists() else "missing"


def _title_from_manifest(manifest: dict[str, Any], title: str) -> str:
    if title:
        return title
    name = manifest.get("name")
    template = manifest.get("template")
    if isinstance(name, str) and name:
        return f"{name} Packet Tracer lab bundle"
    if isinstance(template, str) and template:
        return f"{template} Packet Tracer lab bundle"
    return "Packet Tracer lab bundle"


def lab_report_markdown(manifest: dict[str, Any], *, manifest_path: Path, title: str = "") -> str:
    base_dir = manifest_base_dir(manifest, manifest_path)
    render_bundle = manifest.get("render_bundle") if isinstance(manifest.get("render_bundle"), dict) else {}
    safety = manifest.get("safety") if isinstance(manifest.get("safety"), dict) else {}
    config_files = manifest.get("config_files") if isinstance(manifest.get("config_files"), dict) else {}
    artifacts = manifest.get("artifacts") if isinstance(manifest.get("artifacts"), dict) else {}

    lines: list[str] = [f"# {_title_from_manifest(manifest, title)}", ""]

    lines.extend(["## Bundle Summary", ""])
    summary_rows = [
        ["Kind", manifest.get("kind", "")],
        ["Name", manifest.get("name", "")],
        ["Template", manifest.get("template", "")],
        ["Packet Tracer", manifest.get("packet_tracer_version", "7.3.0")],
        ["Output directory", str(base_dir)],
        ["Safety", "ok" if safety.get("ok") is True else "failed" if safety.get("ok") is False else "unknown"],
        ["Render formats", ", ".join(render_bundle.get("formats", [])) if isinstance(render_bundle.get("formats"), list) else ""],
        ["Config files", config_files.get("count", 0)],
    ]
    lines.extend(markdown_table(["Field", "Value"], summary_rows))
    lines.append("")

    artifact_rows = []
    for key in ("topology", "safety", "render", "render_manifest", "configs", "manifest"):
        if key not in artifacts:
            continue
        artifact_path = resolve_manifest_path(base_dir, artifacts[key])
        artifact_rows.append([key, display_manifest_path(base_dir, artifacts[key]), path_status(artifact_path)])
    if artifact_rows:
        lines.extend(["## Artifact Checklist", ""])
        lines.extend(markdown_table(["Artifact", "Path", "Status"], artifact_rows))
        lines.append("")

    render_rows = []
    render_paths = render_bundle.get("paths") if isinstance(render_bundle.get("paths"), dict) else {}
    render_bytes = render_bundle.get("bytes") if isinstance(render_bundle.get("bytes"), dict) else {}
    render_exit_codes = render_bundle.get("exit_codes") if isinstance(render_bundle.get("exit_codes"), dict) else {}
    for fmt in render_bundle.get("formats", []) if isinstance(render_bundle.get("formats"), list) else []:
        value = render_paths.get(fmt)
        path = resolve_manifest_path(base_dir, value)
        render_rows.append([fmt, display_manifest_path(base_dir, value), render_bytes.get(fmt, ""), render_exit_codes.get(fmt, ""), path_status(path)])
    if render_rows:
        lines.extend(["## Render Outputs", ""])
        lines.extend(markdown_table(["Format", "Path", "Bytes", "Exit Code", "Status"], render_rows))
        lines.append("")

    counts = render_bundle.get("counts") if isinstance(render_bundle.get("counts"), dict) else {}
    if counts:
        count_order = [
            "devices",
            "modules",
            "links",
            "pc_configs",
            "ap_configs",
            "vlan_configs",
            "dhcp_pools",
            "server_configs",
            "security_policies",
            "ios_configs",
        ]
        count_rows = [[key, counts[key]] for key in count_order if key in counts]
        count_rows.extend([[key, value] for key, value in counts.items() if key not in count_order])
        lines.extend(["## Topology Counts", ""])
        lines.extend(markdown_table(["Item", "Count"], count_rows))
        lines.append("")

    lines.extend(["## Safety Report", ""])
    lines.extend(markdown_table(["Field", "Value"], [["OK", safety.get("ok", "")], ["Strict", safety.get("strict", "")], ["Errors", len(safety.get("errors", [])) if isinstance(safety.get("errors"), list) else ""], ["Warnings", len(safety.get("warnings", [])) if isinstance(safety.get("warnings"), list) else ""]]))
    for label_name, items in (("Errors", safety.get("errors")), ("Warnings", safety.get("warnings"))):
        if isinstance(items, list) and items:
            lines.append("")
            lines.append(f"### {label_name}")
            lines.append("")
            for item in items:
                lines.append(f"- {item}")
    lines.append("")

    config_rows = []
    for item in config_files.get("files", []) if isinstance(config_files.get("files"), list) else []:
        if not isinstance(item, dict):
            continue
        path = resolve_manifest_path(base_dir, item.get("path"))
        config_rows.append([item.get("device", ""), item.get("source", ""), display_manifest_path(base_dir, item.get("path")), item.get("bytes", ""), path_status(path)])
    if config_rows:
        lines.extend(["## Config Files", ""])
        lines.extend(markdown_table(["Device", "Source", "Path", "Bytes", "Status"], config_rows))
        lines.append("")

    options = render_bundle.get("options") if isinstance(render_bundle.get("options"), dict) else {}
    if options:
        option_rows = [[key, value] for key, value in options.items()]
        lines.extend(["## Render Options", ""])
        lines.extend(markdown_table(["Option", "Value"], option_rows))
        lines.append("")

    video_rows = [
        ["Topology", "Open or show topology.json / SVG / draw.io and explain core, access, server, WAN, or DMZ areas."],
        ["Safety", "Show safety.json and explain any warnings before live Packet Tracer work."],
        ["Configs", "Paste or inspect generated .cfg files on matching routers/switches."],
        ["Routing", "Run show ip interface brief and show ip route on L3 devices when IOS configs exist."],
        ["Connectivity", "Ping gateways and servers from representative hosts; test DNS/HTTP/FTP/email when configured."],
    ]
    if counts.get("vlan_configs"):
        video_rows.append(["VLAN", "Run show vlan brief and show interfaces trunk on switches."])
    if counts.get("dhcp_pools"):
        video_rows.append(["DHCP", "Show DHCP pool configuration and verify one DHCP client lease."])
    if render_bundle.get("diagram_audit"):
        audit = render_bundle.get("diagram_audit")
        video_rows.append(["Diagram audit", f"Review diagram-audit result: ok={audit.get('ok') if isinstance(audit, dict) else audit}."])
    if render_bundle.get("course_audit"):
        audit = render_bundle.get("course_audit")
        video_rows.append(["Course audit", f"Review course-audit result: ok={audit.get('ok') if isinstance(audit, dict) else audit}."])
    lines.extend(["## Suggested Recording Checklist", ""])
    lines.extend(markdown_table(["Step", "What To Show"], video_rows))
    lines.append("")

    return "\n".join(lines).rstrip() + "\n"


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


def _render_settings_from_values(
    *,
    basename: str,
    formats: Any,
    direction: str,
    theme: str,
    link_labels: bool,
    model_labels: bool,
    group_by: str,
    title: str,
    legend: bool,
) -> dict[str, Any]:
    safe_basename = _safe_basename(basename)
    if direction not in {"LR", "TD", "TB", "RL", "BT"}:
        raise ValueError("render.direction must be one of: LR, TD, TB, RL, BT")
    if theme not in RENDER_THEMES:
        raise ValueError(f"render.theme must be one of: {', '.join(RENDER_THEMES)}")
    if group_by not in RENDER_GROUP_BY:
        raise ValueError(f"render.group_by must be one of: {', '.join(RENDER_GROUP_BY)}")
    return {
        "basename": safe_basename,
        "formats": _parse_formats(formats),
        "direction": direction,
        "options": RenderOptions(theme=theme, link_labels=link_labels, model_labels=model_labels, group_by=group_by, title=title, legend=legend),
    }


def _render_settings(spec: dict[str, Any], *, lab_name: str, template_name: str) -> dict[str, Any]:
    raw = spec.get("render", {})
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError("render must be an object when provided")
    render = _normalize_object_keys(raw, RENDER_KEYS, section="render")
    return _render_settings_from_values(
        basename=_string_value(render, "basename", default=lab_name or template_name),
        formats=render.get("formats"),
        direction=_string_value(render, "direction", default="LR"),
        theme=_string_value(render, "theme", default="light"),
        link_labels=_bool_value(render, "link_labels", default=True),
        model_labels=_bool_value(render, "model_labels", default=True),
        group_by=_string_value(render, "group_by", default="none"),
        title=_string_value(render, "title", default=""),
        legend=_bool_value(render, "legend", default=False),
    )


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
        "commands": ["schema", "template", "plan", "report"],
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
                "title": "visible diagram title for SVG/draw.io/HTML",
                "legend": False,
            },
            "outputs": ["topology.json", "safety.json", "render/<basename>.*", "configs/*.cfg", "manifest.json"],
        },
        "plan": {
            "description": "Generate the same offline lab bundle from an existing topology plan JSON.",
            "required": ["plan", "--output-dir"],
            "optional": ["--name", "--basename", "--formats", "--direction", "--theme", "--no-link-labels", "--no-model-labels", "--group-by", "--title", "--legend", "--strict-safety", "--no-configs", "--config-source", "--compact"],
            "outputs": ["topology.json", "safety.json", "render/<basename>.*", "configs/*.cfg", "manifest.json"],
        },
        "report": {
            "description": "Generate a Markdown coursework/deliverable index from a lab bundle manifest.json.",
            "required": ["manifest"],
            "optional": ["--output", "--title"],
            "outputs": ["Markdown report to stdout or --output"],
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


def _write_lab_bundle(
    plan: dict[str, Any],
    *,
    output_dir: Path,
    topology_source: Path,
    render: dict[str, Any],
    strict: bool,
    compact: bool,
    export_configs: bool,
    config_source: str,
    kind: str,
    inputs: dict[str, Any],
    metadata_bundle: dict[str, Any],
    manifest_fields: dict[str, Any],
) -> tuple[dict[str, Any], int]:
    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts: dict[str, str] = {}

    metadata = plan.setdefault("metadata", {})
    if isinstance(metadata, dict):
        metadata["lab_bundle"] = metadata_bundle

    topology_out = output_dir / "topology.json"
    write_json(topology_out, plan, compact=compact)
    artifacts["topology"] = rel(output_dir, topology_out)

    safety_report = summarize("plan", check_plan(plan), strict=strict)
    safety_out = output_dir / "safety.json"
    write_json(safety_out, safety_report, compact=compact)
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
        "kind": kind,
        **manifest_fields,
        "packet_tracer_version": "7.3.0",
        "output_dir": str(output_dir),
        "inputs": {
            **inputs,
            "topology_source": str(topology_source),
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
    write_json(manifest_out, manifest, compact=compact)

    code = 0 if safety_report["ok"] and render_code == 0 else 1
    return manifest, code


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

    plan = TEMPLATES[template_name].function(**kwargs)
    return _write_lab_bundle(
        plan,
        output_dir=output_dir,
        topology_source=spec_path,
        render=render,
        strict=strict,
        compact=compact_output,
        export_configs=export_configs,
        config_source=config_source,
        kind="pt730-lab-template-bundle",
        inputs={
            "spec": str(spec_path),
            "template_options": kwargs,
        },
        metadata_bundle={"name": lab_name, "template": template_name},
        manifest_fields={"name": lab_name, "template": template_name},
    )


def lab_plan(
    plan_path: Path,
    *,
    output_dir: Path,
    name: str,
    basename: str,
    formats: str,
    direction: str,
    theme: str,
    link_labels: bool,
    model_labels: bool,
    group_by: str,
    title: str,
    legend: bool,
    strict_safety: bool,
    export_configs: bool,
    config_source: str,
    compact: bool,
) -> tuple[dict[str, Any], int]:
    plan = copy.deepcopy(load_json(plan_path))
    lab_name = name or plan_path.stem
    render = _render_settings_from_values(
        basename=basename or lab_name,
        formats=formats,
        direction=direction,
        theme=theme,
        link_labels=link_labels,
        model_labels=model_labels,
        group_by=group_by,
        title=title,
        legend=legend,
    )
    return _write_lab_bundle(
        plan,
        output_dir=output_dir,
        topology_source=plan_path,
        render=render,
        strict=strict_safety,
        compact=compact,
        export_configs=export_configs,
        config_source=config_source,
        kind="pt730-lab-plan-bundle",
        inputs={"plan": str(plan_path)},
        metadata_bundle={"name": lab_name, "plan": str(plan_path)},
        manifest_fields={"name": lab_name},
    )


def lab_report(manifest_path: Path, *, output: Path | None, title: str) -> str:
    manifest = load_json(manifest_path)
    report = lab_report_markdown(manifest, manifest_path=manifest_path, title=title)
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(report, encoding="utf-8")
    return report


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

    plan_p = sub.add_parser("plan", help="generate a complete offline lab bundle from an existing topology plan")
    plan_p.add_argument("plan", type=Path)
    plan_p.add_argument("--output-dir", type=Path, required=True)
    plan_p.add_argument("--name", default="", help="logical lab name; defaults to the plan filename stem")
    plan_p.add_argument("--basename", default="", help="render artifact filename stem; defaults to --name or the plan filename stem")
    plan_p.add_argument("--formats", default=",".join(BUNDLE_DEFAULT_FORMATS), help="comma-separated formats: mermaid,svg,drawio,html,markdown,summary,course-audit,diagram-audit")
    plan_p.add_argument("--direction", choices=("LR", "TD", "TB", "RL", "BT"), default="LR", help="Mermaid direction when mermaid is included")
    plan_p.add_argument("--theme", choices=RENDER_THEMES, default="light", help="diagram color theme")
    plan_p.add_argument("--no-link-labels", action="store_false", dest="link_labels", default=True, help="hide link port/cable/VLAN labels")
    plan_p.add_argument("--no-model-labels", action="store_false", dest="model_labels", default=True, help="hide device model labels")
    plan_p.add_argument("--group-by", choices=RENDER_GROUP_BY, default="none", help="draw visual group boxes by network, VLAN, site, category, or auto detection")
    plan_p.add_argument("--title", default="", help="visible diagram title for SVG, draw.io, and HTML renders")
    plan_p.add_argument("--legend", action="store_true", help="include a visible device/link legend in SVG, draw.io, and HTML renders")
    plan_p.add_argument("--strict-safety", action="store_true", help="treat plan safety warnings as failures")
    plan_p.add_argument("--no-configs", action="store_false", dest="export_configs", default=True, help="skip per-device .cfg export")
    plan_p.add_argument("--config-source", default="", help="only export ios_configs matching this source")

    report_p = sub.add_parser("report", help="generate a Markdown deliverable index from a lab bundle manifest")
    report_p.add_argument("manifest", type=Path)
    report_p.add_argument("--output", type=Path, help="write Markdown to this path instead of stdout")
    report_p.add_argument("--title", default="", help="override the report H1")

    args = parser.parse_args(argv)
    try:
        if args.cmd == "schema":
            emit_json(schema(), compact=args.compact)
            return 0
        if args.cmd == "template":
            manifest, code = lab_template(args.spec, output_dir=args.output_dir, strict_safety=args.strict_safety, compact=args.compact)
            emit_json(manifest, compact=args.compact)
            return code
        if args.cmd == "plan":
            manifest, code = lab_plan(
                args.plan,
                output_dir=args.output_dir,
                name=args.name,
                basename=args.basename,
                formats=args.formats,
                direction=args.direction,
                theme=args.theme,
                link_labels=args.link_labels,
                model_labels=args.model_labels,
                group_by=args.group_by,
                title=args.title,
                legend=args.legend,
                strict_safety=args.strict_safety,
                export_configs=args.export_configs,
                config_source=args.config_source,
                compact=args.compact,
            )
            emit_json(manifest, compact=args.compact)
            return code
        if args.cmd == "report":
            report = lab_report(args.manifest, output=args.output, title=args.title)
            if args.output is None:
                print(report, end="")
            else:
                emit_json({"kind": "pt730-lab-report", "manifest": str(args.manifest), "output": str(args.output)}, compact=args.compact)
            return 0
        raise ValueError(f"unknown command: {args.cmd}")
    except Exception as exc:  # noqa: BLE001
        print(f"pt730-lab: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
