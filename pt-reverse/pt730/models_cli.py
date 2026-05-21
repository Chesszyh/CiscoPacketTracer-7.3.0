#!/usr/bin/env python3
"""Manage PT 7.3.0 common-model safety validation metadata."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from model_registry import MODEL_REGISTRY, models_by_status, record_to_dict, status_notes


def print_json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def manifest() -> dict[str, Any]:
    grouped = models_by_status()
    return {
        status: [str(record["model"]) for record in records]
        for status, records in grouped.items()
    } | {
        "records": grouped,
        "status_notes": {status: status_notes(status) for status in grouped},
    }


def probe_plan(model: str, *, allow_risky: bool, allow_blocked: bool) -> tuple[dict[str, Any], int]:
    record = MODEL_REGISTRY.get(model)
    if record is None:
        record = MODEL_REGISTRY.get(model.upper()) or MODEL_REGISTRY.get(model.lower())
    if record is None:
        return {"error": f"unknown model in PT 7.3 registry: {model}"}, 1
    if record.status == "blocked" and not allow_blocked:
        return {"error": f"{record.model} is blocked: {record.note}"}, 1
    if record.status == "risky" and not allow_risky:
        return {"error": f"{record.model} is risky: {record.note}"}, 1
    plan = {
        "devices": [
            {
                "name": f"VERIFY-{record.model.replace(' ', '-')}",
                "category": record.category,
                "model": record.model,
                "x": 200,
                "y": 200,
                "pt730_validation": {
                    "status_before_probe": record.status,
                    "manual_steps": [
                        "save the current Packet Tracer workspace first",
                        "apply this plan with --replace and --batch-size 1",
                        "if Packet Tracer crashes or refuses the model, keep it risky/blocked",
                        "if create/query/save/reopen all work, promote it to safe with evidence",
                    ],
                },
            }
        ],
        "links": [],
        "pc_configs": [],
        "server_configs": [],
        "ios_configs": [],
    }
    return {
        **record_to_dict(record),
        "plan": plan,
        "recommended_command": f"pt-reverse/bin/pt730-topo apply --replace --batch-size 1 <this-plan.json>",
    }, 0


def validation_steps(model: str, plan_path: str) -> list[dict[str, str]]:
    return [
        {
            "name": "apply_one_model",
            "command": f"pt-reverse/bin/pt730-topo apply --replace --batch-size 1 {plan_path}",
            "purpose": "create only the candidate model after the safety gate",
        },
        {
            "name": "query_summary",
            "command": "pt-reverse/bin/pt730-topo query --summary",
            "purpose": "confirm Packet Tracer can still enumerate the canvas",
        },
        {
            "name": "manual_assessment",
            "command": "record result in pt-reverse/pt730/model_registry.py",
            "purpose": "promote to safe only after create/query/save/reopen succeeds; demote to risky/blocked after crash/refusal",
        },
    ]


def validate_model(model: str, *, dry_run: bool, live: bool, allow_risky: bool, allow_blocked: bool, bridge: str, timeout: float) -> tuple[dict[str, Any], int]:
    data, code = probe_plan(model, allow_risky=allow_risky, allow_blocked=allow_blocked)
    if code:
        return data, code
    if dry_run:
        return {**{k: data[k] for k in ("model", "status", "note", "unattended_safe")}, "dry_run": True, "steps": validation_steps(str(data["model"]), "<probe-plan.json>"), "plan": data["plan"]}, 0
    if not live:
        return {"error": "live validation is guarded; pass --dry-run to inspect steps or --live to contact Packet Tracer"}, 1

    root = Path(__file__).resolve().parents[2]
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as f:
        json.dump(data["plan"], f)
        plan_path = f.name
    try:
        apply_cmd = [str(root / "pt-reverse" / "bin" / "pt730-topo"), "--bridge", bridge, "--timeout", str(timeout), "apply", "--replace", "--batch-size", "1", plan_path]
        query_cmd = [str(root / "pt-reverse" / "bin" / "pt730-topo"), "--bridge", bridge, "--timeout", str(timeout), "query", "--summary"]
        apply_result = subprocess.run(apply_cmd, cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=max(timeout + 10, 30), check=False)
        query_result = subprocess.run(query_cmd, cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=max(timeout + 10, 30), check=False) if apply_result.returncode == 0 else None
        ok = apply_result.returncode == 0 and query_result is not None and query_result.returncode == 0
        return {
            "model": data["model"],
            "status_before_validation": data["status"],
            "ok": ok,
            "apply": {"returncode": apply_result.returncode, "stdout": apply_result.stdout, "stderr": apply_result.stderr},
            "query_summary": None if query_result is None else {"returncode": query_result.returncode, "stdout": query_result.stdout, "stderr": query_result.stderr},
            "next_step": "promote to safe only after save/reopen also succeeds" if ok else "keep or demote to risky/blocked with failure evidence",
        }, 0 if ok else 1
    finally:
        Path(plan_path).unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("manifest", help="print grouped safety registry")
    probe_p = sub.add_parser("probe-plan", help="generate a guarded one-model live validation plan")
    probe_p.add_argument("model")
    probe_p.add_argument("--allow-risky", action="store_true")
    probe_p.add_argument("--allow-blocked", action="store_true")

    validate_p = sub.add_parser("validate", help="guarded one-model validation workflow")
    validate_p.add_argument("model")
    validate_p.add_argument("--dry-run", action="store_true")
    validate_p.add_argument("--live", action="store_true", help="contact Packet Tracer through pt730-topo")
    validate_p.add_argument("--allow-risky", action="store_true")
    validate_p.add_argument("--allow-blocked", action="store_true")
    validate_p.add_argument("--bridge", default="http://127.0.0.1:54321")
    validate_p.add_argument("--timeout", type=float, default=20.0)

    args = parser.parse_args(argv)
    if args.cmd == "manifest":
        print_json(manifest())
        return 0
    if args.cmd == "probe-plan":
        data, code = probe_plan(args.model, allow_risky=args.allow_risky, allow_blocked=args.allow_blocked)
        if code:
            print(f"pt730-models: {data['error']}", file=sys.stderr)
        else:
            print_json(data)
        return code
    if args.cmd == "validate":
        data, code = validate_model(args.model, dry_run=args.dry_run, live=args.live, allow_risky=args.allow_risky, allow_blocked=args.allow_blocked, bridge=args.bridge, timeout=args.timeout)
        if code and "error" in data:
            print(f"pt730-models: {data['error']}", file=sys.stderr)
        else:
            print_json(data)
        return code
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
