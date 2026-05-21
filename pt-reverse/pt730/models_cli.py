#!/usr/bin/env python3
"""Manage PT 7.3.0 common-model safety validation metadata."""

from __future__ import annotations

import argparse
import json
import sys
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("manifest", help="print grouped safety registry")
    probe_p = sub.add_parser("probe-plan", help="generate a guarded one-model live validation plan")
    probe_p.add_argument("model")
    probe_p.add_argument("--allow-risky", action="store_true")
    probe_p.add_argument("--allow-blocked", action="store_true")

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
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
