# Packet Tracer 7.3.0 Automation Toolkit

Local tooling for controlling and auditing Cisco Packet Tracer 7.3.0 through a
Script Module bridge.  The repository focuses on reproducible offline checks,
offline IP/VLAN planning, built-in topology templates, high-level topology
composition, end-to-end offline pipeline generation, deterministic topology
auto-layout, IOS config planning, safe topology-plan rendering, and small
guarded live operations for the fixed 7.3.0 version used in the coursework.

This source release does **not** include Cisco Packet Tracer binaries, DLLs,
crash dumps, or extracted Cisco application documentation.  Install Packet
Tracer separately and keep the application files outside Git.

## Contents

- `pt-reverse/bin/`: command wrappers for launch, bridge, topology, templates,
  MCP, IP planning, pipeline, compose, config planning, layout, render, safety,
  app, IOS, PC, server, FTP, and terminal helpers.
- `pt-reverse/pt730/`: Python implementations for offline validation, rendering,
  catalog lookup, and bridge helpers.
- `pt-reverse/examples/`: topology JSON examples and locally generated Packet
  Tracer lab files.
- `pt-reverse/course-design/`: college-network design plan, generated audit
  artifacts, and switch configuration snippets.
- `pt-reverse/skills/`: Codex skill wrappers for agent-friendly PT 7.3.0 CLI
  workflows.
- `pt-reverse/upstream/MCP-Packet-Tracer`: upstream catalog submodule used by
  `pt730-catalog`.

## Setup

```bash
git submodule update --init --recursive
pt-reverse/bin/pt730-selftest
pt-reverse/bin/pt730-mcp --list-tools
```

Optional Codex skill install:

```bash
ln -sfn "$PWD/pt-reverse/skills/cisco-packet-tracer-730" "$HOME/.codex/skills/cisco-packet-tracer-730"
```

Use the offline tools first:

```bash
pt-reverse/bin/pt730-template lan-star --pcs 4 --servers 1 --network 192.168.10.0/24
pt-reverse/bin/pt730-template wireless-lan --aps 2 --laptops 4 --servers 1 --ssid PT730-LAB --network 192.168.80.0/24
pt-reverse/bin/pt730-template vlan-router-on-stick --vlans 3 --hosts-per-vlan 2 --servers-per-vlan 1 --native-vlan 10
pt-reverse/bin/pt730-template edge-security --inside-hosts 3 --dmz-servers 2 --internet-hosts 1 --domain edge.local
pt-reverse/bin/pt730-template router-ring --routers 4 --interconnect-pool 10.20.0.0/28
pt-reverse/bin/pt730-template wan-ring --sites 3 --hosts-per-site 2 --servers-per-site 1 --routing ospf
pt-reverse/bin/pt730-template campus --cores 2 --segments 4 --hosts-per-segment 2 --servers 4 --l3 --routing rip
pt-reverse/bin/pt730-pipeline campus --ip-plan pt-reverse/examples/ip-plan-campus.json --compose-spec pt-reverse/examples/compose-campus.json --output-dir compose-campus-out --routing rip
pt-reverse/bin/pt730-ip-plan campus pt-reverse/examples/ip-plan-campus.json --output ip-plan-campus.json
pt-reverse/bin/pt730-compose campus pt-reverse/examples/compose-campus.json --segments-from-ip-plan ip-plan-campus.json --output compose-campus.layout.json
pt-reverse/bin/pt730-config-plan campus compose-campus.layout.json --l3 --routing rip --output compose-campus.configured.json
pt-reverse/bin/pt730-config-plan export-configs compose-campus.configured.json --output-dir compose-campus-configs
pt-reverse/bin/pt730-safety plan pt-reverse/course-design/college-network-topology-pt73-safe.json
pt-reverse/bin/pt730-layout pt-reverse/course-design/college-network-topology-pt73-safe.json --style campus --preserve-existing --output college-network-topology-pt73-safe.layout.json
pt-reverse/bin/pt730-render svg pt-reverse/course-design/college-network-topology-pt73-safe.json --output college-network-topology-pt73-safe.svg
pt-reverse/bin/pt730-render drawio pt-reverse/course-design/college-network-topology-pt73-safe.json --output college-network-topology-pt73-safe.drawio
pt-reverse/bin/pt730-render html pt-reverse/course-design/college-network-topology-pt73-safe.json --output college-network-topology-pt73-safe.html
pt-reverse/bin/pt730-render markdown pt-reverse/course-design/college-network-topology-pt73-safe.json
pt-reverse/bin/pt730-render course-audit pt-reverse/course-design/college-network-topology-pt73-safe.json
```

Run the MCP stdio wrapper for agent tool calls:

```bash
pt-reverse/bin/pt730-mcp
```

MCP live tools require `allow_live=true`; `pt730_live_apply`, `pt730_live_eval`,
`pt730_live_smoke`, IOS/terminal/ping tools, PC static/DHCP tools, Server-PT
service/account/config tools, FTP client tools, app/bridge/launch/recover
lifecycle tools, and simulation/PDU tools support `dry_run=true` previews that
return the underlying CLI command without contacting Packet Tracer. Catalog and
JavaScript safety checks are exposed offline through MCP, along with
`pt730_schema` for retrieving template, IP-plan, compose, config-plan, pipeline,
and IOS-template input schemas. Model registry reads are exposed through MCP;
model metadata writes require `allow_write=true` unless run as `dry_run=true`.
Built-in template MCP tools expose LAN-star, wireless-LAN, router-on-a-stick
VLAN, edge-security, router-ring, WAN-ring, and campus template options
including DNS, SSID, 802.1Q, NAT/ACL, DMZ, RIP/OSPF/static WAN routing, layout,
no-layout, compact, L3 routing, and naming controls from the underlying
`pt730-template` CLI.
Campus workflow MCP tools expose compact JSON and layout-style controls through
`pt730_ip_plan_campus`, `pt730_compose_campus`, and `pt730_pipeline_campus`.
Render MCP tools expose visual theme, label, and visual grouping controls
through `pt730_render` for SVG, draw.io, HTML, and Mermaid where supported.
The `pt730_layout` MCP tool exposes canvas size, spacing, margin, and compact
JSON controls for denser or cleaner topology diagrams.
Config planning MCP tools expose IOS-only output, source filtering, and compact
JSON controls through `pt730_config_plan_campus` and `pt730_export_configs`.

Read `pt-reverse/SAFETY.md` before running live Packet Tracer operations.

For a detailed Chinese workflow manual, read
[`pt-reverse/使用手册.md`](pt-reverse/使用手册.md).

## Legal Note

Cisco Packet Tracer is Cisco software.  This repository contains helper scripts,
coursework topology plans, and generated lab artifacts only; it is not a
redistribution of Packet Tracer itself.
