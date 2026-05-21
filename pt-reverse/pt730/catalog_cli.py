#!/usr/bin/env python3
"""Offline Packet Tracer 7.3.0 catalog helper.

The base catalog comes from the bundled upstream MCP-Packet-Tracer project,
which mostly targets newer Packet Tracer builds.  This wrapper adds a small
local PT 7.3.0 safety overlay so automation can prefer models that were
actually exercised in this Wine/PT 7.3.0 environment.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
UPSTREAM_SRC = ROOT / "pt-reverse" / "upstream" / "MCP-Packet-Tracer" / "src"
if str(UPSTREAM_SRC) not in sys.path:
    sys.path.insert(0, str(UPSTREAM_SRC))

try:
    from packet_tracer_mcp.infrastructure.catalog.aliases import MODEL_ALIASES
    from packet_tracer_mcp.infrastructure.catalog.cables import ALL_LINK_TYPES, CABLE_RULES, CABLE_TYPES, infer_cable
    from packet_tracer_mcp.infrastructure.catalog.devices import ALL_MODELS, resolve_model
    from packet_tracer_mcp.infrastructure.catalog.modules import ALL_MODULES, resolve_module
except ImportError as exc:  # pragma: no cover - should only happen if upstream files are moved
    raise SystemExit(f"pt730-catalog: cannot import bundled upstream catalog: {exc}") from exc

from topology_cli import CABLE_CODES, DEVICE_TYPES
from model_registry import risky_model_notes, safe_model_notes


SOURCE_NOTE = "upstream MCP-Packet-Tracer catalog plus local PT 7.3.0 safety overlay"

SAFE_MODELS: dict[str, str] = safe_model_notes()
RISKY_MODELS: dict[str, str] = risky_model_notes()

VERIFIED_MODULES: dict[str, str] = {
    "HWIC-2T": "live verified on 2911 slot 0/0; adds Serial0/0/0 and Serial0/0/1",
}

VERIFIED_CABLE_CODES: dict[int, str] = {
    8100: "live verified for Ethernet straight-through links",
    8101: "live verified for Ethernet crossover/router-router links",
    8106: "live verified for 2911 serial links",
}


def _json_default(obj: Any) -> str:
    return str(obj)


def print_json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, default=_json_default))


def port_to_dict(port: Any) -> dict[str, Any]:
    speed = getattr(port, "speed", "")
    return {
        "name": getattr(port, "full_name", ""),
        "speed": getattr(speed, "value", str(speed)),
        "slot": getattr(port, "slot", ""),
    }


def model_status(model_name: str) -> tuple[str, str]:
    if model_name in SAFE_MODELS:
        return "safe", SAFE_MODELS[model_name]
    if model_name in RISKY_MODELS:
        return "risky", RISKY_MODELS[model_name]
    return "unverified", "present in upstream catalog, not live-verified on local PT 7.3.0"


def module_status(module_name: str) -> tuple[str, str]:
    if module_name in VERIFIED_MODULES:
        return "verified", VERIFIED_MODULES[module_name]
    return "unverified", "present in upstream catalog, not live-verified on local PT 7.3.0"


def resolved_model(query: str) -> tuple[str | None, Any | None]:
    direct = ALL_MODELS.get(query)
    if direct:
        return None, direct
    alias = MODEL_ALIASES.get(query.lower())
    if alias:
        return alias, ALL_MODELS.get(alias)
    model = resolve_model(query)
    return None, model


def device_record(model: Any, *, include_ports: bool) -> dict[str, Any]:
    status, note = model_status(model.pt_type)
    record: dict[str, Any] = {
        "model": model.pt_type,
        "display_name": model.display_name,
        "category": model.category,
        "type_id": DEVICE_TYPES.get(model.category),
        "port_count": len(model.ports),
        "pt730_status": status,
        "safe_to_create": status == "safe",
        "note": note,
        "source": SOURCE_NOTE,
    }
    if include_ports:
        record["ports"] = [port_to_dict(port) for port in model.ports]
    return record


def module_record(module: Any) -> dict[str, Any]:
    status, note = module_status(module.name)
    return {
        "name": module.name,
        "module_type": module.module_type,
        "category": module.category,
        "ports_added": list(module.ports_added),
        "description": module.description,
        "compatible_with": list(module.compatible_with),
        "pt730_status": status,
        "safe_to_use": status == "verified",
        "note": note,
        "source": SOURCE_NOTE,
    }


def cable_records() -> list[dict[str, Any]]:
    by_code: dict[int, set[str]] = {}
    for name, code in {**ALL_LINK_TYPES, **CABLE_CODES}.items():
        by_code.setdefault(int(code), set()).add(name)

    records: list[dict[str, Any]] = []
    for code, aliases in sorted(by_code.items()):
        preferred = sorted(aliases, key=lambda name: (0 if name in CABLE_TYPES else 1, len(name), name))[0]
        status = "verified" if code in VERIFIED_CABLE_CODES else "mapped"
        records.append(
            {
                "name": preferred,
                "code": code,
                "aliases": sorted(aliases),
                "display_name": CABLE_TYPES.get(preferred, CABLE_TYPES.get(preferred.replace("ethernet-", ""), "")),
                "pt730_status": status,
                "note": VERIFIED_CABLE_CODES.get(code, "known Packet Tracer link code; not live-verified locally"),
            }
        )
    return records


def matches_status(record: dict[str, Any], status: str) -> bool:
    return status == "all" or record.get("pt730_status") == status


def table(rows: list[dict[str, Any]], columns: list[tuple[str, str]]) -> None:
    if not rows:
        return
    widths = []
    for key, title in columns:
        width = len(title)
        for row in rows:
            value = row.get(key, "")
            if isinstance(value, list):
                value = ",".join(str(item) for item in value)
            width = max(width, len(str(value)))
        widths.append(min(width, 64))
    print("  ".join(title.ljust(widths[i]) for i, (_, title) in enumerate(columns)))
    print("  ".join("-" * width for width in widths))
    for row in rows:
        cells = []
        for i, (key, _) in enumerate(columns):
            value = row.get(key, "")
            if isinstance(value, list):
                value = ",".join(str(item) for item in value)
            text = str(value)
            if len(text) > widths[i]:
                text = text[: max(0, widths[i] - 1)] + "…"
            cells.append(text.ljust(widths[i]))
        print("  ".join(cells))


def output(value: Any, *, table_format: bool, kind: str) -> None:
    if not table_format:
        print_json(value)
        return
    rows = value if isinstance(value, list) else [value]
    if kind == "devices":
        table(
            rows,
            [
                ("pt730_status", "status"),
                ("model", "model"),
                ("category", "category"),
                ("type_id", "type"),
                ("port_count", "ports"),
                ("display_name", "display"),
                ("note", "note"),
            ],
        )
    elif kind == "modules":
        table(
            rows,
            [
                ("pt730_status", "status"),
                ("name", "module"),
                ("module_type", "type"),
                ("category", "category"),
                ("ports_added", "ports_added"),
                ("compatible_with", "compatible"),
                ("description", "description"),
            ],
        )
    elif kind == "cables":
        table(rows, [("pt730_status", "status"), ("name", "name"), ("code", "code"), ("aliases", "aliases"), ("note", "note")])
    elif kind == "ports":
        table(rows, [("name", "port"), ("speed", "speed"), ("slot", "slot")])
    elif kind == "aliases":
        table(rows, [("alias", "alias"), ("model", "model")])
    else:
        print_json(value)


def add_common_output(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--table", action="store_true", help="print a compact human table instead of JSON")


def list_devices(args: argparse.Namespace) -> int:
    records = [device_record(model, include_ports=args.include_ports) for model in ALL_MODELS.values()]
    if args.category:
        records = [record for record in records if record["category"] == args.category]
    records = [record for record in records if matches_status(record, args.status)]
    records.sort(key=lambda item: (item["category"], item["pt730_status"], item["model"]))
    output(records, table_format=args.table, kind="devices")
    return 0


def show_device(args: argparse.Namespace) -> int:
    alias, model = resolved_model(args.model)
    if not model:
        print(f"pt730-catalog: unknown device model or alias: {args.model}", file=sys.stderr)
        return 1
    record = device_record(model, include_ports=True)
    if alias:
        record["resolved_from_alias"] = args.model
    output(record, table_format=args.table, kind="devices")
    return 0


def show_ports(args: argparse.Namespace) -> int:
    alias, model = resolved_model(args.model)
    if not model:
        print(f"pt730-catalog: unknown device model or alias: {args.model}", file=sys.stderr)
        return 1
    ports = [port_to_dict(port) for port in model.ports]
    payload: Any = ports
    if not args.table:
        payload = {
            "query": args.model,
            "model": model.pt_type,
            "resolved_from_alias": alias,
            "ports": ports,
            "source": SOURCE_NOTE,
        }
    output(payload, table_format=args.table, kind="ports")
    return 0


def list_modules(args: argparse.Namespace) -> int:
    records = [module_record(module) for module in ALL_MODULES.values()]
    if args.category:
        records = [record for record in records if record["category"] == args.category]
    if args.model:
        alias, model = resolved_model(args.model)
        if not model:
            print(f"pt730-catalog: unknown device model or alias: {args.model}", file=sys.stderr)
            return 1
        model_name = model.pt_type
        records = [
            record
            for record in records
            if not record["compatible_with"] or model_name in record["compatible_with"]
        ]
        for record in records:
            record["queried_model"] = model_name
            if alias:
                record["queried_model_resolved_from_alias"] = args.model
    records = [record for record in records if matches_status(record, args.status)]
    records.sort(key=lambda item: (item["pt730_status"], item["category"], item["name"]))
    output(records, table_format=args.table, kind="modules")
    return 0


def show_module(args: argparse.Namespace) -> int:
    module = resolve_module(args.module)
    if not module:
        print(f"pt730-catalog: unknown module: {args.module}", file=sys.stderr)
        return 1
    output(module_record(module), table_format=args.table, kind="modules")
    return 0


def list_cables(args: argparse.Namespace) -> int:
    records = cable_records()
    if args.status != "all":
        records = [record for record in records if record["pt730_status"] == args.status]
    output(records, table_format=args.table, kind="cables")
    return 0


def infer_cable_cmd(args: argparse.Namespace) -> int:
    name = infer_cable(args.category_a, args.category_b)
    code = CABLE_CODES.get(name, ALL_LINK_TYPES.get(name))
    payload = {
        "category_a": args.category_a,
        "category_b": args.category_b,
        "cable": name,
        "code": code,
        "rule_source": "upstream CABLE_RULES",
        "pt730_note": "pt730-topo maps cable names to numeric createLink codes",
    }
    output(payload, table_format=False, kind="other")
    return 0


def list_aliases(args: argparse.Namespace) -> int:
    records = [{"alias": alias, "model": model} for alias, model in sorted(MODEL_ALIASES.items())]
    output(records, table_format=args.table, kind="aliases")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    devices_p = sub.add_parser("devices", help="list device models with PT 7.3.0 safety status")
    devices_p.add_argument("--category", help="filter by upstream category, e.g. router, switch, pc, server")
    devices_p.add_argument("--status", choices=["all", "safe", "risky", "unverified"], default="all")
    devices_p.add_argument("--include-ports", action="store_true", help="include full port lists in JSON output")
    add_common_output(devices_p)

    device_p = sub.add_parser("device", help="show one model/alias with ports")
    device_p.add_argument("model")
    add_common_output(device_p)

    ports_p = sub.add_parser("ports", help="list valid physical ports for one model/alias")
    ports_p.add_argument("model")
    add_common_output(ports_p)

    modules_p = sub.add_parser("modules", help="list modules with compatibility and PT 7.3.0 status")
    modules_p.add_argument("--model", help="filter to modules compatible with a device model/alias")
    modules_p.add_argument("--category", help="filter by module category")
    modules_p.add_argument("--status", choices=["all", "verified", "unverified"], default="all")
    add_common_output(modules_p)

    module_p = sub.add_parser("module", help="show one module")
    module_p.add_argument("module")
    add_common_output(module_p)

    cables_p = sub.add_parser("cables", help="list cable names and PT 7.3.0 numeric createLink codes")
    cables_p.add_argument("--status", choices=["all", "verified", "mapped"], default="all")
    add_common_output(cables_p)

    infer_p = sub.add_parser("infer-cable", help="infer cable type from two device categories")
    infer_p.add_argument("category_a")
    infer_p.add_argument("category_b")

    aliases_p = sub.add_parser("aliases", help="list model aliases")
    add_common_output(aliases_p)

    args = parser.parse_args(argv)
    if args.cmd == "devices":
        return list_devices(args)
    if args.cmd == "device":
        return show_device(args)
    if args.cmd == "ports":
        return show_ports(args)
    if args.cmd == "modules":
        return list_modules(args)
    if args.cmd == "module":
        return show_module(args)
    if args.cmd == "cables":
        return list_cables(args)
    if args.cmd == "infer-cable":
        return infer_cable_cmd(args)
    if args.cmd == "aliases":
        return list_aliases(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
