#!/usr/bin/env python3
"""Run offline Packet Tracer 7.3.0 agent workflows end to end."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any

from compose_cli import compose_campus
from config_plan_cli import configured_plan, export_config_files
from ip_plan_cli import plan_campus
from layout_cli import LayoutOptions, STYLES, layout_plan
from render_cli import course_audit, markdown, summary
from safety_cli import check_plan, summarize


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: JSON root must be an object")
    return data


def write_json(path: Path, value: Any, *, compact: bool = False) -> None:
    text = json.dumps(value, ensure_ascii=False, indent=None if compact else 2, separators=(",", ":") if compact else None) + "\n"
    path.write_text(text, encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def rel(base: Path, path: Path) -> str:
    try:
        return str(path.relative_to(base))
    except ValueError:
        return str(path)


def schema() -> dict[str, Any]:
    return {
        "commands": ["schema", "campus"],
        "campus": {
            "description": "Offline IP plan -> topology compose -> L3 config planning -> layout -> render -> cfg export.",
            "required": ["--compose-spec", "--output-dir"],
            "optional": ["--ip-plan", "--routing none|rip|static", "--layout-style", "--course-audit", "--strict-safety"],
            "outputs": [
                "ip-plan.json",
                "topology.composed.json",
                "topology.configured.json",
                "topology.layout.json",
                "topology.summary.json",
                "topology.md",
                "safety.json",
                "configs/*.cfg",
                "manifest.json",
            ],
        },
    }


def campus_pipeline(
    *,
    compose_spec_path: Path,
    ip_plan_path: Path | None,
    output_dir: Path,
    routing: str,
    layout_style: str,
    strict_safety: bool,
    include_course_audit: bool,
    compact: bool,
) -> tuple[dict[str, Any], int]:
    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts: dict[str, str] = {}

    compose_spec = load_json(compose_spec_path)
    if ip_plan_path is not None:
        planned = plan_campus(load_json(ip_plan_path))
        ip_out = output_dir / "ip-plan.json"
        write_json(ip_out, planned, compact=compact)
        artifacts["ip_plan"] = rel(output_dir, ip_out)
        compose_spec = copy.deepcopy(compose_spec)
        compose_spec["segments"] = planned["compose"]["segments"]

    composed = compose_campus(compose_spec, do_layout=False, layout_style=layout_style)
    composed_out = output_dir / "topology.composed.json"
    write_json(composed_out, composed, compact=compact)
    artifacts["composed_topology"] = rel(output_dir, composed_out)

    include_l3 = routing != "none"
    configured = configured_plan(composed, include_l3=include_l3, routing=routing)
    configured_out = output_dir / "topology.configured.json"
    write_json(configured_out, configured, compact=compact)
    artifacts["configured_topology"] = rel(output_dir, configured_out)

    laid_out = layout_plan(configured, LayoutOptions(style=layout_style))
    layout_out = output_dir / "topology.layout.json"
    write_json(layout_out, laid_out, compact=compact)
    artifacts["layout_topology"] = rel(output_dir, layout_out)

    safety_report = summarize("plan", check_plan(laid_out), strict=strict_safety)
    safety_out = output_dir / "safety.json"
    write_json(safety_out, safety_report, compact=compact)
    artifacts["safety"] = rel(output_dir, safety_out)

    summary_out = output_dir / "topology.summary.json"
    write_text(summary_out, summary(laid_out))
    artifacts["summary"] = rel(output_dir, summary_out)

    markdown_out = output_dir / "topology.md"
    write_text(markdown_out, markdown(laid_out))
    artifacts["markdown"] = rel(output_dir, markdown_out)

    configs_dir = output_dir / "configs"
    config_manifest = export_config_files(laid_out, configs_dir)
    artifacts["configs"] = rel(output_dir, configs_dir)

    audit_report: dict[str, Any] | None = None
    audit_code = 0
    if include_course_audit:
        audit_report, audit_code = course_audit(laid_out)
        audit_out = output_dir / "course-audit.json"
        write_json(audit_out, audit_report, compact=compact)
        artifacts["course_audit"] = rel(output_dir, audit_out)

    manifest = {
        "kind": "pt730-campus-pipeline",
        "packet_tracer_version": "7.3.0",
        "routing": routing,
        "layout_style": layout_style,
        "output_dir": str(output_dir),
        "inputs": {
            "compose_spec": str(compose_spec_path),
            "ip_plan": str(ip_plan_path) if ip_plan_path is not None else "",
        },
        "artifacts": artifacts,
        "safety": safety_report,
        "config_files": config_manifest,
    }
    if audit_report is not None:
        manifest["course_audit"] = audit_report

    manifest_out = output_dir / "manifest.json"
    write_json(manifest_out, manifest, compact=compact)
    artifacts["manifest"] = rel(output_dir, manifest_out)
    manifest["artifacts"] = artifacts
    write_json(manifest_out, manifest, compact=compact)

    code = 0 if safety_report["ok"] and audit_code == 0 else 1
    return manifest, code


def emit_json(value: Any, *, compact: bool) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=None if compact else 2, separators=(",", ":") if compact else None))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pt730-pipeline", description=__doc__)
    parser.add_argument("--compact", action="store_true", help="emit compact JSON to stdout and output files")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("schema", help="print pipeline schema")

    campus_p = sub.add_parser("campus", help="run the offline campus topology pipeline")
    campus_p.add_argument("--compose-spec", type=Path, required=True)
    campus_p.add_argument("--ip-plan", type=Path)
    campus_p.add_argument("--output-dir", type=Path, required=True)
    campus_p.add_argument("--routing", choices=("none", "rip", "static"), default="rip")
    campus_p.add_argument("--layout-style", choices=STYLES, default="campus")
    campus_p.add_argument("--strict-safety", action="store_true")
    campus_p.add_argument("--course-audit", action="store_true")

    args = parser.parse_args(argv)
    try:
        if args.cmd == "schema":
            emit_json(schema(), compact=args.compact)
            return 0
        if args.cmd == "campus":
            manifest, code = campus_pipeline(
                compose_spec_path=args.compose_spec,
                ip_plan_path=args.ip_plan,
                output_dir=args.output_dir,
                routing=args.routing,
                layout_style=args.layout_style,
                strict_safety=args.strict_safety,
                include_course_audit=args.course_audit,
                compact=args.compact,
            )
            emit_json(manifest, compact=args.compact)
            return code
        raise ValueError(f"unknown command: {args.cmd}")
    except Exception as exc:  # noqa: BLE001
        print(f"pt730-pipeline: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
