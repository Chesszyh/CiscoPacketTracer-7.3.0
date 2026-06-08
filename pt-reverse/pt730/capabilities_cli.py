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
    "pt730-config-plan",
    "pt730-compose",
    "pt730-ip-plan",
    "pt730-ios-template",
    "pt730-layout",
    "pt730-mcp",
    "pt730-models",
    "pt730-pipeline",
    "pt730-render",
    "pt730-safety",
    "pt730-selftest",
    "pt730-template",
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
        "ios_template_features": ["schema", "ip_routing", "vlans", "access_interfaces", "trunks", "routed_interfaces", "ripv2", "static_routes", "standard_acls", "extended_acls", "interface_acl_bindings", "nat_overload"],
        "config_plan_features": ["schema", "campus", "vlan_declarations", "access_ports", "trunk_ports", "l3_svis", "routed_interlinks", "ripv2", "static_routes", "config_file_export", "topology_ios_configs"],
        "layout_styles": ["auto", "hierarchical", "campus", "lan", "ring", "grid"],
        "compose_features": ["schema", "campus", "core_ring", "core_interconnect_pool", "server_block", "access_segments", "segments_from_ip_plan", "representative_hosts", "static_ip_configs", "server_services", "auto_layout"],
        "ip_plan_features": ["schema", "campus_vlsm", "gateway_reservation", "compose_segments", "unused_pool_summary"],
        "pipeline_features": ["schema", "campus", "ip_plan_to_compose", "l3_config_planning", "layout", "safety_report", "markdown_render", "summary_render", "svg_render", "drawio_render", "html_render", "config_file_export"],
        "render_features": ["mermaid", "markdown", "summary", "svg", "drawio", "html", "course_audit"],
        "template_features": ["schema", "lan_star", "router_ring", "static_host_ips", "server_http", "serial_modules", "ripv2", "auto_layout"],
        "mcp_features": ["stdio_jsonrpc", "tools_list", "tools_call", "offline_cli_wrappers", "structured_content", "schema_wrappers", "template_option_wrappers", "layout_option_wrappers", "config_export_option_wrappers", "catalog_wrappers", "safety_js_wrappers", "allow_live_gated_live_tools", "allow_live_gated_device_tools", "write_gated_model_records", "topo_query_export_wrappers", "model_registry_wrappers", "live_lifecycle_dry_run", "live_eval_dry_run", "live_smoke_dry_run", "live_apply_dry_run", "live_device_dry_run", "live_pc_dhcp_dry_run", "live_server_service_dry_run", "live_server_account_config_dry_run", "live_ftp_dry_run", "live_sim_dry_run"],
        "query_summary_fields": ["devices", "links", "ip_configs", "ios_devices", "server_services", "config_summaries", "acl_applications"],
        "recommended_workflow": [
            "pt-reverse/bin/pt730-selftest",
            "pt-reverse/bin/pt730-mcp --list-tools",
            "pt-reverse/bin/pt730-mcp  # stdio MCP server; live tools require allow_live=true",
            "MCP pt730_schema exposes template/ip_plan/compose/config_plan/pipeline/ios_template input schemas",
            "MCP pt730_template_lan_star/pt730_template_router_ring expose full template CLI options including layout_style/no_layout/compact",
            "MCP pt730_layout exposes canvas_width/canvas_height/spacing_x/spacing_y/margin/compact layout controls",
            "MCP pt730_config_plan_campus/pt730_export_configs expose ios_only/compact/source config export controls",
            "MCP pt730_catalog exposes devices/device/ports/modules/module/cables/infer_cable/aliases",
            "MCP pt730_safety_js and pt730_safety_policy expose JavaScript safety checks and policy",
            "MCP pt730_live_ios/pt730_live_pc_static/pt730_live_term/pt730_live_ping/pt730_live_server_inspect support dry_run=true command previews",
            "MCP pt730_live_pc_inspect/pt730_live_pc_dhcp/pt730_live_server_service/pt730_live_server_dns_add/pt730_live_server_ftp_add/pt730_live_server_ftp_remove/pt730_live_server_email_add/pt730_live_server_email_remove/pt730_live_server_ntp_config/pt730_live_server_syslog_config/pt730_live_server_dhcp_config/pt730_live_ftp/pt730_live_sim support dry_run=true command previews",
            "MCP pt730_topo_summarize_query/pt730_topo_export expose saved-query summarization/export; live export requires allow_live=true",
            "MCP pt730_models_manifest/pt730_models_queue/pt730_models_probe_plan/pt730_models_validate/pt730_models_validate_batch/pt730_models_record expose model validation workflows; record requires allow_write=true",
            "MCP pt730_live_app/pt730_live_bridge/pt730_live_launch/pt730_live_recover support dry_run=true command previews for lifecycle operations",
            "MCP pt730_live_eval/pt730_live_smoke support dry_run=true command previews and require allow_live=true for live execution",
            "pt-reverse/bin/pt730-template lan-star --pcs 4 --servers 1 --network 192.168.10.0/24",
            "pt-reverse/bin/pt730-template router-ring --routers 4 --interconnect-pool 10.20.0.0/28",
            "pt-reverse/bin/pt730-pipeline campus --ip-plan <ip-plan.json> --compose-spec <campus-spec.json> --output-dir <out-dir> --routing rip",
            "pt-reverse/bin/pt730-ip-plan schema",
            "pt-reverse/bin/pt730-ip-plan campus <ip-plan.json> --output <planned-segments.json>",
            "pt-reverse/bin/pt730-compose schema",
            "pt-reverse/bin/pt730-compose campus <campus-spec.json> --output <plan.json>",
            "pt-reverse/bin/pt730-config-plan campus <plan.json> --output <configured-plan.json>",
            "pt-reverse/bin/pt730-config-plan campus <plan.json> --l3 --routing rip --output <configured-plan.json>",
            "pt-reverse/bin/pt730-config-plan campus <plan.json> --l3 --routing static --output <configured-plan.json>",
            "pt-reverse/bin/pt730-config-plan export-configs <configured-plan.json> --output-dir <configs-dir>",
            "pt-reverse/bin/pt730-layout <plan.json> --output <layout.json>",
            "pt-reverse/bin/pt730-layout <plan.json> --style campus --preserve-existing --output <layout.json>",
            "pt-reverse/bin/pt730-safety plan <plan.json>",
            "pt-reverse/bin/pt730-render svg <plan.json> --output <diagram.svg>",
            "pt-reverse/bin/pt730-render drawio <plan.json> --output <diagram.drawio>",
            "pt-reverse/bin/pt730-render html <plan.json> --output <review.html>",
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
