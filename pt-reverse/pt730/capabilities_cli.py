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
    "pt730-lab",
    "pt730-layout",
    "pt730-mcp",
    "pt730-models",
    "pt730-plan",
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
    "Generate pt730-render verification-plan before course/video validation.",
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
        "ios_template_features": ["schema", "ip_routing", "ipv6_unicast_routing", "ios_management_security", "local_users", "ssh", "line_console", "line_vty", "banners", "vlans", "access_interfaces", "trunks", "routed_interfaces", "interface_ipv6_addresses", "spanning_tree", "etherchannel", "dhcp_relay", "hsrp", "ios_dhcp_server", "ntp_client", "syslog_client", "snmp", "ripv2", "eigrp", "ospf", "ospfv3", "ripng", "bgp", "static_routes", "ipv6_static_routes", "standard_acls", "extended_acls", "interface_acl_bindings", "nat_overload"],
        "config_plan_features": ["schema", "campus", "vlan_declarations", "access_ports", "trunk_ports", "l3_svis", "routed_interlinks", "ripv2", "eigrp", "ospf", "static_routes", "config_file_export", "topology_ios_configs"],
        "layout_styles": ["auto", "hierarchical", "campus", "lan", "ring", "grid"],
        "compose_features": ["schema", "campus", "core_ring", "core_interconnect_pool", "server_block", "access_segments", "segments_from_ip_plan", "representative_hosts", "static_ip_configs", "server_services", "auto_layout"],
        "ip_plan_features": ["schema", "campus_vlsm", "gateway_reservation", "compose_segments", "unused_pool_summary"],
        "pipeline_features": ["schema", "campus", "ip_plan_to_compose", "l3_config_planning", "rip_routing", "eigrp_routing", "ospf_routing", "static_routing", "layout", "safety_report", "markdown_render", "summary_render", "svg_render", "drawio_render", "html_render", "config_file_export"],
        "plan_features": ["schema", "new", "set_metadata", "remove_device", "remove_module", "remove_link", "cascade_delete", "reversible_editing", "add_device", "add_module", "add_link", "add_ap_config", "add_annotation", "add_pc_config", "add_ipv6_config", "add_vlan_config", "add_dhcp_pool", "add_server_config", "add_ios_config", "add_security_policy", "ssid_metadata", "serial_modules", "json_object_inputs", "output_file", "compact_json", "mcp_wrappers"],
        "lab_features": ["schema", "template_lab_bundle", "plan_lab_bundle", "lab_report_markdown", "single_spec_input", "custom_plan_input", "template_option_validation", "safety_report", "render_bundle", "report_render_preset", "verification_plan_artifacts", "config_file_export", "manifest"],
        "render_features": ["render_schema", "mermaid", "markdown", "summary", "svg", "drawio", "html", "course_audit", "diagram_audit", "verification_plan_json", "verification_plan_markdown", "render_bundle", "bundle_manifest", "visual_themes", "report_render_preset", "visible_titles", "diagram_legends", "link_label_toggle", "model_label_toggle", "visual_group_boxes", "diagram_annotations", "render_time_annotations", "wireless_ap_icons", "wireless_link_styling", "ap_config_summary", "ipv6_config_summary", "vlan_config_summary", "router_dhcp_pool_summary", "security_policy_summary"],
        "template_features": ["schema", "lan_star", "dual_stack_lan", "wireless_lan", "vlan_router_on_stick", "switching_lab", "server_services", "edge_security", "router_ring", "wan_ring", "campus", "redundant_campus", "enterprise_edge", "hq_vlans", "server_zone", "branch_wan", "isp_internet", "campus_l3_configs", "dual_core", "dual_homed_access", "etherchannel", "portfast_bpduguard", "hsrp_gateways", "stp_root_roles", "static_host_ips", "ipv6_host_metadata", "ipv6_unicast_routing", "dhcp_client_hosts", "server_dhcp", "router_dhcp_pools", "dhcp_relay", "ios_dhcp_pools", "ntp_syslog_snmp", "wireless_access_points", "laptop_clients", "ssid_metadata", "dot1q_subinterfaces", "trunk_ports", "access_vlan_ports", "dmz_servers", "nat_overload", "outside_acl", "site_lans", "server_http", "server_dns", "server_ftp", "server_tftp", "server_email", "serial_modules", "ripv2", "eigrp", "ospf", "bgp_edge", "static_routes", "auto_layout"],
        "mcp_features": ["stdio_jsonrpc", "tools_list", "tools_call", "offline_cli_wrappers", "structured_content", "schema_wrappers", "plan_editor_wrappers", "render_bundle_wrapper", "verification_plan_wrapper", "lab_bundle_wrapper", "lab_plan_wrapper", "lab_report_wrapper", "template_option_wrappers", "workflow_option_wrappers", "layout_option_wrappers", "config_export_option_wrappers", "catalog_wrappers", "safety_js_wrappers", "allow_live_gated_live_tools", "allow_live_gated_device_tools", "write_gated_model_records", "topo_query_export_wrappers", "model_registry_wrappers", "live_lifecycle_dry_run", "live_eval_dry_run", "live_smoke_dry_run", "live_apply_dry_run", "live_device_dry_run", "live_pc_dhcp_dry_run", "live_server_service_dry_run", "live_server_account_config_dry_run", "live_ftp_dry_run", "live_sim_dry_run"],
        "query_summary_fields": ["devices", "links", "ip_configs", "ios_devices", "server_services", "config_summaries", "acl_applications", "spanning_tree", "etherchannel", "dhcp_helpers", "hsrp", "ios_dhcp_pools", "ntp", "syslog", "snmp", "management_access", "bgp", "interface_ipv6_addresses", "ospfv3", "ripng", "ipv6_static_routes"],
        "recommended_workflow": [
            "pt-reverse/bin/pt730-selftest",
            "pt-reverse/bin/pt730-mcp --list-tools",
            "pt-reverse/bin/pt730-mcp  # stdio MCP server; live tools require allow_live=true",
            "MCP pt730_schema exposes template/ip_plan/compose/config_plan/pipeline/lab/render/plan/ios_template input schemas",
            "MCP pt730_plan_new/pt730_plan_set_metadata/pt730_plan_add_device/pt730_plan_remove_device/pt730_plan_add_module/pt730_plan_remove_module/pt730_plan_add_link/pt730_plan_remove_link/pt730_plan_add_ap_config/pt730_plan_add_annotation/pt730_plan_add_pc_config/pt730_plan_add_ipv6_config/pt730_plan_add_vlan_config/pt730_plan_add_dhcp_pool/pt730_plan_add_server_config/pt730_plan_add_ios_config/pt730_plan_add_security_policy let agents build and revise custom topology JSON, modules, wireless metadata, and config metadata without hand-editing files",
            "MCP pt730_template_lan_star/pt730_template_dual_stack_lan/pt730_template_wireless_lan/pt730_template_vlan_router_on_stick/pt730_template_switching_lab/pt730_template_server_services/pt730_template_edge_security/pt730_template_router_ring/pt730_template_wan_ring/pt730_template_campus/pt730_template_redundant_campus/pt730_template_enterprise_edge expose full template CLI options including layout_style/no_layout/compact",
            "MCP pt730_ip_plan_campus/pt730_compose_campus/pt730_pipeline_campus expose compact and layout_style workflow controls",
            "MCP pt730_render exposes visual theme/title/legend/link label/model label/group_by controls and topology annotations for Mermaid, SVG, draw.io, and HTML",
            "CLI --annotation/--annotations and MCP annotations can append render-only callouts without modifying the source topology JSON",
            "MCP pt730_schema target=render and CLI pt730-render schema describe render formats, options, and annotation fields",
            "MCP pt730_render and pt730_render_bundle expose preset=report for paper theme, auto grouping, legend, hidden link labels, diagram-audit, and verification-plan bundle defaults",
            "MCP pt730_render_bundle creates multi-format SVG/draw.io/HTML/Markdown/summary/course-audit/diagram-audit/verification bundles with a manifest in one offline call",
            "MCP pt730_verification_plan creates JSON or Markdown live/manual validation checklists from topology JSON without contacting Packet Tracer",
            "MCP pt730_lab_template creates topology/safety/render/configs/manifest lab bundles from one template spec JSON",
            "MCP pt730_lab_plan creates topology/safety/render/configs/manifest lab bundles from an existing topology plan JSON",
            "MCP pt730_lab_report creates a Markdown coursework/deliverable index from a lab bundle manifest.json",
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
            "pt-reverse/bin/pt730-template dual-stack-lan --pcs 2 --servers 1 --ipv4-network 192.168.60.0/24 --ipv6-prefix 2001:db8:60::/64",
            "pt-reverse/bin/pt730-template wireless-lan --aps 2 --laptops 4 --servers 1 --ssid PT730-LAB --network 192.168.80.0/24",
            "pt-reverse/bin/pt730-template vlan-router-on-stick --vlans 3 --hosts-per-vlan 2 --servers-per-vlan 1 --native-vlan 10",
            "pt-reverse/bin/pt730-template vlan-router-on-stick --vlans 3 --hosts-per-vlan 2 --servers-per-vlan 1 --client-addressing dhcp",
            "pt-reverse/bin/pt730-template switching-lab --vlans 3 --hosts-per-vlan 2 --access-switches 2",
            "pt-reverse/bin/pt730-template server-services --clients 3 --services all --domain services.local",
            "pt-reverse/bin/pt730-template edge-security --inside-hosts 3 --dmz-servers 2 --internet-hosts 1 --domain edge.local",
            "pt-reverse/bin/pt730-template router-ring --routers 4 --interconnect-pool 10.20.0.0/28",
            "pt-reverse/bin/pt730-template wan-ring --sites 3 --hosts-per-site 2 --servers-per-site 1 --routing ospf",
            "pt-reverse/bin/pt730-template wan-ring --sites 3 --hosts-per-site 2 --servers-per-site 1 --routing eigrp",
            "pt-reverse/bin/pt730-template campus --cores 2 --segments 4 --hosts-per-segment 2 --servers 4 --l3 --routing ospf",
            "pt-reverse/bin/pt730-template campus --cores 2 --segments 4 --hosts-per-segment 2 --servers 4 --l3 --routing eigrp",
            "pt-reverse/bin/pt730-template redundant-campus --segments 4 --hosts-per-segment 2 --servers 4 --routing ospf",
            "pt-reverse/bin/pt730-template enterprise-edge --campus-vlans 3 --branches 2 --dmz-servers 2 --routing ospf",
            "pt-reverse/bin/pt730-template enterprise-edge --campus-vlans 3 --branches 2 --dmz-servers 2 --routing bgp",
            "pt-reverse/bin/pt730-lab template <lab-spec.json> --output-dir <out-dir>",
            "pt-reverse/bin/pt730-lab plan <plan.json> --output-dir <out-dir> --basename topology --formats svg,drawio,html,markdown,summary,diagram-audit --title <title> --legend",
            "pt-reverse/bin/pt730-lab plan <plan.json> --output-dir <out-dir> --basename topology --preset report",
            "pt-reverse/bin/pt730-lab report <out-dir>/manifest.json --output <out-dir>/deliverable.md",
            "pt-reverse/bin/pt730-plan new --name <lab-name> --output <plan.json>",
            "pt-reverse/bin/pt730-plan add-device <plan.json> --name R1 --category router --model 2911 --output <plan.json>",
            "pt-reverse/bin/pt730-plan add-module <plan.json> --device R1 --slot 0/0 --model HWIC-2T --output <plan.json>",
            "pt-reverse/bin/pt730-plan add-link <plan.json> --a R1 --b SW1 --pa GigabitEthernet0/0 --pb FastEthernet0/1 --output <plan.json>",
            "pt-reverse/bin/pt730-plan remove-device <plan.json> --name PC1 --cascade --output <plan.json>",
            "pt-reverse/bin/pt730-plan remove-link <plan.json> --a R1 --b SW1 --pa GigabitEthernet0/0 --pb FastEthernet0/1 --output <plan.json>",
            "pt-reverse/bin/pt730-plan add-ap-config <plan.json> --name AP1 --ssid CLASSROOM --channel 6 --auth wpa2-psk --output <plan.json>",
            "pt-reverse/bin/pt730-plan add-ios-config <plan.json> --device R1 --command 'enable' --command 'configure terminal' --command 'end' --output <plan.json>",
            "pt-reverse/bin/pt730-plan add-server-config <plan.json> --name SRV1 --http --dns-json '{\"enabled\":true,\"records\":[{\"name\":\"www.lab.local\",\"ip\":\"192.168.10.10\"}]}' --output <plan.json>",
            "pt-reverse/bin/pt730-pipeline campus --ip-plan <ip-plan.json> --compose-spec <campus-spec.json> --output-dir <out-dir> --routing ospf",
            "pt-reverse/bin/pt730-pipeline campus --ip-plan <ip-plan.json> --compose-spec <campus-spec.json> --output-dir <out-dir> --routing eigrp",
            "pt-reverse/bin/pt730-ip-plan schema",
            "pt-reverse/bin/pt730-ip-plan campus <ip-plan.json> --output <planned-segments.json>",
            "pt-reverse/bin/pt730-compose schema",
            "pt-reverse/bin/pt730-compose campus <campus-spec.json> --output <plan.json>",
            "pt-reverse/bin/pt730-config-plan campus <plan.json> --output <configured-plan.json>",
            "pt-reverse/bin/pt730-config-plan campus <plan.json> --l3 --routing rip --output <configured-plan.json>",
            "pt-reverse/bin/pt730-config-plan campus <plan.json> --l3 --routing eigrp --output <configured-plan.json>",
            "pt-reverse/bin/pt730-config-plan campus <plan.json> --l3 --routing ospf --output <configured-plan.json>",
            "pt-reverse/bin/pt730-config-plan campus <plan.json> --l3 --routing static --output <configured-plan.json>",
            "pt-reverse/bin/pt730-config-plan export-configs <configured-plan.json> --output-dir <configs-dir>",
            "pt-reverse/bin/pt730-layout <plan.json> --output <layout.json>",
            "pt-reverse/bin/pt730-layout <plan.json> --style campus --preserve-existing --output <layout.json>",
            "pt-reverse/bin/pt730-safety plan <plan.json>",
            "pt-reverse/bin/pt730-render svg <plan.json> --title <title> --legend --output <diagram.svg>",
            "pt-reverse/bin/pt730-render bundle <plan.json> --output-dir <render-dir> --basename topology --preset report",
            "pt-reverse/bin/pt730-render svg <plan.json> --group-by auto --output <diagram.svg>",
            "pt-reverse/bin/pt730-render drawio <plan.json> --output <diagram.drawio>",
            "pt-reverse/bin/pt730-render drawio <plan.json> --group-by vlan --output <diagram.drawio>",
            "pt-reverse/bin/pt730-render html <plan.json> --output <review.html>",
            "pt-reverse/bin/pt730-render html <plan.json> --group-by network --output <review.html>",
            "pt-reverse/bin/pt730-render markdown <plan.json> --output <review.md>",
            "pt-reverse/bin/pt730-render summary <plan.json> --output <review.json>",
            "pt-reverse/bin/pt730-render diagram-audit <plan.json> --output <diagram-audit.json>",
            "pt-reverse/bin/pt730-render verification-plan <plan.json> --format markdown --output <verification.md>",
            "pt-reverse/bin/pt730-render bundle <plan.json> --output-dir <render-dir> --basename topology --formats svg,drawio,html,markdown,summary,diagram-audit,verification-json,verification-md --title <title> --legend",
            "pt-reverse/bin/pt730-render course-audit pt-reverse/course-design/college-network-topology-pt73-safe.json --output pt-reverse/course-design/college-network-topology-pt73-safe.audit.json",
            "pt-reverse/bin/pt730-models manifest",
            "pt-reverse/bin/pt730-models queue",
            "pt-reverse/bin/pt730-models validate-batch --dry-run --limit 2",
            "pt-reverse/bin/pt730-models validate-batch --live --limit 2 --record-failures risky",
            "pt-reverse/bin/pt730-models record <model> --status risky --reason <reason> --evidence <path-or-note>",
            "pt-reverse/bin/pt730-ios-template schema",
            "pt-reverse/bin/pt730-ios-template render <ios-template.json> --topology-json",
            "pt-reverse/bin/pt730-ios-template render pt-reverse/examples/ios-template-fhrp-services.json --topology-json",
            "pt-reverse/bin/pt730-ios-template render pt-reverse/examples/ios-template-bgp-edge.json --topology-json",
            "pt-reverse/bin/pt730-ios-template render pt-reverse/examples/ios-template-ipv6-routing.json --topology-json",
            "pt-reverse/bin/pt730-ios-template render pt-reverse/examples/ios-template-management-security.json --topology-json",
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


def print_json(value: Any, *, compact: bool) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=None if compact else 2, separators=(",", ":") if compact else None))


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
    parser.add_argument("--compact", action="store_true", help="emit compact JSON when not using --table")
    args = parser.parse_args(argv)
    data = manifest()
    if args.table:
        print_table(data)
    else:
        print_json(data, compact=args.compact)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
