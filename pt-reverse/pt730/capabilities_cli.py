#!/usr/bin/env python3
"""Machine-readable PT 7.3.0 automation capabilities for agents."""

from __future__ import annotations

import argparse
import json
from typing import Any

from catalog_cli import RISKY_MODELS, SAFE_MODELS, VERIFIED_CABLE_CODES, VERIFIED_MODULES


OFFLINE_TOOLS = [
    "pt730-capabilities",
    "pt730-catalog",
    "pt730-compose",
    "pt730-ios-template",
    "pt730-layout",
    "pt730-models",
    "pt730-render",
    "pt730-safety",
    "pt730-selftest",
]

LIVE_TOOLS = [
    "pt730-app",
    "pt730-bridge",
    "pt730-eval",
    "pt730-ftp",
    "pt730-ios",
    "pt730-launch",
    "pt730-pc",
    "pt730-ping",
    "pt730-recover",
    "pt730-server",
    "pt730-sim",
    "pt730-smoke",
    "pt730-term",
    "pt730-topo",
]

SAFE_DEFAULTS = [
    "Run pt730-selftest before changing automation code.",
    "Run pt730-safety plan before unattended topology creation.",
    "Use static PC addressing for smoke checks.",
    "Use pt730-term ping or pt730-ping for automated pass/fail connectivity.",
    "Use only live-verified models for unattended topology creation.",
]

GUARDED_OPERATIONS = [
    "DHCP client lease validation: use only when explicitly requested.",
    "Simulation simple PDU creation: visual aid only, not a reliable automated pass/fail source.",
    "New model testing: save first and test one model at a time.",
    "fileNew: only when intentionally clearing the current workspace.",
]

BLOCKED_PATTERNS = [
    "dhcpRun(",
    "fileOpenFromBytes(",
]


def manifest() -> dict[str, Any]:
    return {
        "packet_tracer_version": "7.3.0",
        "runtime": "Wine/Fedora with Packet Tracer Script Module localhost bridge",
        "offline_tools": OFFLINE_TOOLS,
        "live_tools": LIVE_TOOLS,
        "safe_models": SAFE_MODELS,
        "risky_models": RISKY_MODELS,
        "verified_modules": VERIFIED_MODULES,
        "verified_cable_codes": VERIFIED_CABLE_CODES,
        "safe_defaults": SAFE_DEFAULTS,
        "guarded_operations": GUARDED_OPERATIONS,
        "blocked_patterns": BLOCKED_PATTERNS,
        "ios_template_features": ["schema", "vlans", "access_interfaces", "trunks", "ripv2", "static_routes", "standard_acls", "extended_acls", "interface_acl_bindings", "nat_overload"],
        "layout_styles": ["auto", "hierarchical", "campus", "lan", "ring", "grid"],
        "compose_features": ["schema", "campus", "core_ring", "server_block", "access_segments", "representative_hosts", "static_ip_configs", "server_services", "auto_layout"],
        "query_summary_fields": ["devices", "links", "ip_configs", "ios_devices", "server_services", "config_summaries", "acl_applications"],
        "recommended_workflow": [
            "pt-reverse/bin/pt730-selftest",
            "pt-reverse/bin/pt730-compose schema",
            "pt-reverse/bin/pt730-compose campus <campus-spec.json> --output <plan.json>",
            "pt-reverse/bin/pt730-layout <plan.json> --output <layout.json>",
            "pt-reverse/bin/pt730-layout <plan.json> --style campus --preserve-existing --output <layout.json>",
            "pt-reverse/bin/pt730-safety plan <plan.json>",
            "pt-reverse/bin/pt730-render markdown <plan.json> --output <review.md>",
            "pt-reverse/bin/pt730-render summary <plan.json> --output <review.json>",
            "pt-reverse/bin/pt730-render course-audit pt-reverse/course-design/college-network-topology-pt73-safe.json --output pt-reverse/course-design/college-network-topology-pt73-safe.audit.json",
            "pt-reverse/bin/pt730-models manifest",
            "pt-reverse/bin/pt730-models queue",
            "pt-reverse/bin/pt730-models validate-batch --dry-run --limit 2",
            "pt-reverse/bin/pt730-models validate-batch --live --limit 2 --record-failures risky",
            "pt-reverse/bin/pt730-models record <model> --status risky --reason <reason> --evidence <path-or-note>",
            "pt-reverse/bin/pt730-ios-template schema",
            "pt-reverse/bin/pt730-ios-template render <ios-template.json> --topology-json",
            "pt-reverse/bin/pt730-topo apply --batch-size 1 <plan.json>",
            "pt-reverse/bin/pt730-topo query --summary",
            "pt-reverse/bin/pt730-topo export --raw-out <query.json> --summary-out <summary.json>",
            "pt-reverse/bin/pt730-topo export --raw-out <query.json> --summary-out <summary.json> --markdown-out <summary.md>",
            "pt-reverse/bin/pt730-topo summarize-query <query.json>",
            "pt-reverse/bin/pt730-pc static <PC> --ip <ip> --mask <mask> --gateway <gw> --dns <dns>",
            "pt-reverse/bin/pt730-term <PC> --cmd 'ping <target>' --wait 8 --expect 'Lost = 0 \\\\(0% loss\\\\)'",
            "pt-reverse/bin/pt730-app save-as <out.pkt>",
        ],
        "recovery_workflow": [
            "pt-reverse/bin/pt730-recover --notify",
            "If connected:false persists, run the PT-MCP Builder bootstrap in Packet Tracer.",
        ],
        "reference_files": [
            "pt-reverse/SAFETY.md",
            "pt-reverse/README.md",
            "pt-reverse/examples/server-dhcp-lan.json",
            "pt-reverse/course-design/college-network-topology-pt73-safe.json",
        ],
    }


def print_json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def print_table(data: dict[str, Any]) -> None:
    print("Packet Tracer automation capabilities")
    print(f"Version: {data['packet_tracer_version']}")
    print()
    print("Offline tools")
    for item in data["offline_tools"]:
        print(f"  - {item}")
    print()
    print("Live tools")
    for item in data["live_tools"]:
        print(f"  - {item}")
    print()
    print("Safe models")
    for model, note in data["safe_models"].items():
        print(f"  - {model}: {note}")
    print()
    print("Blocked patterns")
    for pattern in data["blocked_patterns"]:
        print(f"  - {pattern}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--table", action="store_true", help="print a compact human-readable summary")
    args = parser.parse_args(argv)
    data = manifest()
    if args.table:
        print_table(data)
    else:
        print_json(data)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
