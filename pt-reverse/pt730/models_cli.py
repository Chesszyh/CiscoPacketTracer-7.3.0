#!/usr/bin/env python3
"""Manage PT 7.3.0 common-model safety validation metadata."""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from model_registry import (
    VALID_STATUSES,
    effective_registry,
    load_validation_store,
    models_by_status,
    record_to_dict,
    save_validation_store,
    status_notes,
    validation_store_path,
)


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


def validation_queue(*, include_risky: bool, include_blocked: bool) -> dict[str, Any]:
    grouped = models_by_status()
    statuses = ["unverified"]
    if include_risky:
        statuses.append("risky")
    if include_blocked:
        statuses.append("blocked")
    items: list[dict[str, Any]] = []
    for status in statuses:
        for record in grouped.get(status, []):
            model = str(record["model"])
            quoted_model = shlex.quote(model)
            item = dict(record)
            extra_flags = ""
            if status == "risky":
                extra_flags = " --allow-risky"
            elif status == "blocked":
                extra_flags = " --allow-blocked"
            item["dry_run_command"] = f"pt-reverse/bin/pt730-models validate {quoted_model}{extra_flags} --dry-run"
            item["live_command"] = f"pt-reverse/bin/pt730-models validate {quoted_model}{extra_flags} --live"
            item["record_rule"] = "safe only after create/query/save/reopen; risky or blocked after crash/refusal"
            items.append(item)
    return {
        "counts": {status: len(grouped.get(status, [])) for status in grouped},
        "items": items,
    }


def validation_batch_plan(*, limit: int, include_risky: bool, include_blocked: bool) -> list[dict[str, Any]]:
    items = validation_queue(include_risky=include_risky, include_blocked=include_blocked)["items"]
    selected = items if limit <= 0 else items[:limit]
    plan = []
    for item in selected:
        model = str(item["model"])
        quoted_model = shlex.quote(model)
        plan.append(
            {
                "model": model,
                "status": item["status"],
                "command": str(item["live_command"]),
                "dry_run_command": str(item["dry_run_command"]),
                "after_success": f"pt-reverse/bin/pt730-models record {quoted_model} --status safe --reason 'create/query/save/reopen passed' --save-reopen",
                "after_failure": f"pt-reverse/bin/pt730-models record {quoted_model} --status risky --reason '<failure evidence>' --evidence '<path-or-note>'",
            }
        )
    return plan


def probe_plan(model: str, *, allow_risky: bool, allow_blocked: bool) -> tuple[dict[str, Any], int]:
    registry = effective_registry()
    record = registry.get(model)
    if record is None:
        record = registry.get(model.upper()) or registry.get(model.lower())
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


def record_validation(model: str, *, status: str, reason: str, evidence: list[str], save_reopen: bool) -> tuple[dict[str, Any], int]:
    if status not in VALID_STATUSES:
        return {"error": f"invalid status: {status}"}, 1
    registry = effective_registry()
    record = registry.get(model)
    if record is None:
        record = registry.get(model.upper()) or registry.get(model.lower())
    if record is None:
        return {"error": f"unknown model in PT 7.3 registry: {model}"}, 1
    if status == "safe" and not save_reopen:
        return {"error": "safe status requires save/reopen evidence via --save-reopen; create/query alone is not enough"}, 1
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    note = reason or f"recorded as {status} on {now}"
    store = load_validation_store()
    validations = store.setdefault("validations", {})
    validations[record.model] = {
        "status": status,
        "note": note,
        "reason": reason,
        "evidence": evidence,
        "save_reopen": save_reopen,
        "updated_at": now,
    }
    save_validation_store(store)
    updated = effective_registry().get(record.model)
    return {
        "model": record.model,
        "status": status,
        "store": str(validation_store_path()),
        "record": record_to_dict(updated or record),
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


def _failure_evidence(result: dict[str, Any]) -> list[str]:
    evidence: list[str] = []
    apply_result = result.get("apply")
    if isinstance(apply_result, dict):
        evidence.append(f"apply.returncode={apply_result.get('returncode')}")
        stderr = str(apply_result.get("stderr", "")).strip()
        if stderr:
            evidence.append(f"apply.stderr={stderr[:500]}")
    query_result = result.get("query_summary")
    if isinstance(query_result, dict):
        evidence.append(f"query.returncode={query_result.get('returncode')}")
        stderr = str(query_result.get("stderr", "")).strip()
        if stderr:
            evidence.append(f"query.stderr={stderr[:500]}")
    return evidence or ["validation failed without structured subprocess evidence"]


def _record_failed_result(model: str, result: dict[str, Any], status: str) -> dict[str, Any]:
    reason = f"auto-recorded failed validation: {result.get('next_step', 'validation failed')}"
    data, code = record_validation(model, status=status, reason=reason, evidence=_failure_evidence(result), save_reopen=False)
    if code:
        return {"status": "record_failed", "error": data.get("error", "unknown record failure")}
    return {"status": status, "record": data.get("record"), "store": data.get("store")}


def validate_batch(*, dry_run: bool, live: bool, limit: int, include_risky: bool, include_blocked: bool, bridge: str, timeout: float, stop_on_failure: bool, record_failures: str | None) -> tuple[dict[str, Any], int]:
    plan = validation_batch_plan(limit=limit, include_risky=include_risky, include_blocked=include_blocked)
    if dry_run:
        return {"dry_run": True, "count": len(plan), "items": plan}, 0
    if not live:
        return {"error": "batch validation is guarded; pass --dry-run to inspect steps or --live to contact Packet Tracer"}, 1
    results = []
    ok = True
    for item in plan:
        model = str(item["model"])
        result, code = validate_model(model, dry_run=False, live=True, allow_risky=include_risky, allow_blocked=include_blocked, bridge=bridge, timeout=timeout)
        if code and record_failures:
            result["recorded_failure"] = _record_failed_result(model, result, record_failures)
        results.append(result)
        if code:
            ok = False
            if stop_on_failure:
                break
    return {"dry_run": False, "count": len(results), "ok": ok, "results": results}, 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("manifest", help="print grouped safety registry")
    queue_p = sub.add_parser("queue", help="print the guarded common-model validation queue")
    queue_p.add_argument("--include-risky", action="store_true")
    queue_p.add_argument("--include-blocked", action="store_true")
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
    validate_p.add_argument("--record-failure-status", choices=["risky", "blocked"], help="record a failed live validation with this status")
    batch_p = sub.add_parser("validate-batch", help="validate queued models one at a time")
    batch_p.add_argument("--dry-run", action="store_true")
    batch_p.add_argument("--live", action="store_true", help="contact Packet Tracer through pt730-topo")
    batch_p.add_argument("--limit", type=int, default=0, help="limit number of queued models; 0 means all")
    batch_p.add_argument("--include-risky", action="store_true")
    batch_p.add_argument("--include-blocked", action="store_true")
    batch_p.add_argument("--bridge", default="http://127.0.0.1:54321")
    batch_p.add_argument("--timeout", type=float, default=20.0)
    batch_p.add_argument("--keep-going", action="store_true", help="continue after a live validation failure")
    batch_p.add_argument("--record-failures", choices=["risky", "blocked"], help="record failed live validations with this status")
    record_p = sub.add_parser("record", help="record one model validation result in the local overlay")
    record_p.add_argument("model")
    record_p.add_argument("--status", choices=sorted(VALID_STATUSES), required=True)
    record_p.add_argument("--reason", default="")
    record_p.add_argument("--evidence", action="append", default=[])
    record_p.add_argument("--save-reopen", action="store_true", help="required before promoting a model to safe")

    args = parser.parse_args(argv)
    if args.cmd == "manifest":
        print_json(manifest())
        return 0
    if args.cmd == "queue":
        print_json(validation_queue(include_risky=args.include_risky, include_blocked=args.include_blocked))
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
        if code and args.record_failure_status and "model" in data:
            data["recorded_failure"] = _record_failed_result(str(data["model"]), data, args.record_failure_status)
        if code and "error" in data:
            print(f"pt730-models: {data['error']}", file=sys.stderr)
        else:
            print_json(data)
        return code
    if args.cmd == "validate-batch":
        data, code = validate_batch(
            dry_run=args.dry_run,
            live=args.live,
            limit=args.limit,
            include_risky=args.include_risky,
            include_blocked=args.include_blocked,
            bridge=args.bridge,
            timeout=args.timeout,
            stop_on_failure=not args.keep_going,
            record_failures=args.record_failures,
        )
        if code and "error" in data:
            print(f"pt730-models: {data['error']}", file=sys.stderr)
        else:
            print_json(data)
        return code
    if args.cmd == "record":
        data, code = record_validation(args.model, status=args.status, reason=args.reason, evidence=args.evidence, save_reopen=args.save_reopen)
        if code and "error" in data:
            print(f"pt730-models: {data['error']}", file=sys.stderr)
        else:
            print_json(data)
        return code
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
