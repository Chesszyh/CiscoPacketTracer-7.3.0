---
name: cisco-packet-tracer-730
description: Use Cisco Packet Tracer 7.3.0 automation CLI and MCP workflows for agent-friendly network topology planning, rendering, configuration generation, safety checks, and cautious live Packet Tracer bridge operations. Trigger when asked to draw Packet Tracer topologies, design campus/college networks, generate PT 7.3 topology JSON, render SVG/draw.io/HTML/Markdown reports, export IOS configs, run pt730-* CLI commands, expose PT 7.3.0 tools through MCP, or prepare Packet Tracer coursework deliverables.
---

# Cisco Packet Tracer 7.3 CLI

Use this skill to operate the local Packet Tracer 7.3.0 automation toolkit through `pt-reverse/bin/pt730-*` commands or the `pt730-mcp` stdio server.

## Default Workflow

1. Locate the repo:
   ```bash
   python3 pt-reverse/skills/cisco-packet-tracer-730/scripts/pt730_cli.py root
   ```
   If the skill is installed through a symlink, the script resolves back to the repo. If that fails, set `PT730_REPO=/path/to/CiscoPacketTracer-7.3.0`.

2. Prefer offline CLI first. Do not start live Packet Tracer unless the user explicitly asks or offline outputs must be applied to a `.pkt` file.

3. For MCP clients, start:
   ```bash
   pt-reverse/bin/pt730-mcp
   ```
   Use `pt-reverse/bin/pt730-mcp --list-tools` to inspect tools. Live MCP tools require `allow_live=true`; `pt730_live_apply`, `pt730_live_eval`, `pt730_live_smoke`, IOS/terminal/ping tools, PC static/DHCP tools, Server-PT service/account/config tools, FTP client tools, app/bridge/launch/recover lifecycle tools, and simulation/PDU tools support `dry_run=true` command previews without contacting Packet Tracer. Model metadata recording requires `allow_write=true` unless `dry_run=true`.

4. Before live apply, run:
   ```bash
   pt-reverse/bin/pt730-safety plan <plan.json>
   pt-reverse/bin/pt730-topo --timeout 1 apply --dry-run <plan.json>
   ```

5. For substantial changes to the toolkit, run:
   ```bash
   pt-reverse/bin/pt730-selftest
   python3 -m unittest discover -s pt-reverse/tests -p 'test_*.py'
   ```

## Common Tasks

- Generate a small or representative lab topology: use `pt730-template lan-star`, `wireless-lan`, `vlan-router-on-stick`, `edge-security`, `router-ring`, `wan-ring`, or `campus`; through MCP, `pt730_template_lan_star`, `pt730_template_wireless_lan`, `pt730_template_vlan_router_on_stick`, `pt730_template_edge_security`, `pt730_template_router_ring`, `pt730_template_wan_ring`, and `pt730_template_campus` expose layout, no-layout, compact JSON, and template-specific options.
- Generate VLAN DHCP labs with `pt730-template vlan-router-on-stick --client-addressing dhcp`; it emits router DHCP pools, DHCP client host configs, VLAN metadata, and report-renderable `dhcp_pools`.
- Generate a campus/course design: use `pt730-ip-plan`, then `pt730-compose`, then `pt730-config-plan`, or run `pt730-pipeline campus`; `pt730-template campus --l3 --routing ospf` and `pt730-config-plan campus --l3 --routing ospf` emit campus OSPF router IDs, passive SVI interfaces, and direct network statements. Through MCP, `pt730_ip_plan_campus`, `pt730_compose_campus`, and `pt730_pipeline_campus` expose compact JSON, routing, and layout-style controls where applicable.
- Generate WAN dynamic-routing labs with `pt730-template wan-ring --routing ospf` or `--routing rip`; OSPF output includes router IDs, passive LAN interfaces, and per-router network statements.
- Refine topology placement through MCP with `pt730_layout`; use canvas width/height, spacing, margin, style, and compact options when diagrams need clearer density or framing.
- Render outputs for review: use `pt730-render svg`, `drawio`, `html`, `markdown`, `summary`, and `course-audit`; visual renders support `--theme light|dark|paper`, `--no-link-labels`, `--no-model-labels`, and `--group-by auto|network|vlan|site|category`, exposed through MCP as `theme`, `link_labels`, `model_labels`, and `group_by`.
- Plan and export IOS configs: use `pt730-config-plan campus` and `pt730-config-plan export-configs`; through MCP, `pt730_config_plan_campus` exposes `ios_only`/`compact` plus `none|rip|ospf|static` routing, and `pt730_export_configs` exposes `source`/`compact`.
- Query input schemas through MCP with `pt730_schema` before generating unfamiliar template/IP-plan/compose/config/pipeline/IOS-template specs.
- Query catalog and JavaScript safety through MCP with `pt730_catalog`, `pt730_safety_js`, and `pt730_safety_policy`.
- Preview live IOS/PC DHCP/server service/account/config/FTP/simulation/lifecycle MCP calls with `dry_run=true` before any `allow_live=true` execution.
- Inspect model safety metadata through MCP with `pt730_models_manifest`, `pt730_models_queue`, and `pt730_models_validate` dry runs; write records only when explicitly allowed.
- Query or apply live Packet Tracer only after bridge recovery/safety checks.

For exact command patterns, read `references/workflows.md` only when needed.

## Safety Rules

- Fixed version is Cisco Packet Tracer 7.3.0. Do not switch to newer Packet Tracer behavior or docs.
- Treat live Script Module operations as crash-prone. Keep live mutations sequential and small.
- Avoid risky/blocked models unless the user explicitly asks to validate them.
- For unattended wireless templates, use the built-in `wireless-lan` template's verified `AccessPoint-PT` and `Laptop-PT` models; treat wireless cable code `8109` warnings as offline-only until live validation is explicitly requested.
- For VLAN/trunk labs, prefer the built-in `vlan-router-on-stick` template; it uses verified models and emits router 802.1Q subinterfaces, switch trunk/access ports, VLAN metadata, static hosts, and optional per-VLAN servers.
- For DHCP VLAN labs, use `vlan-router-on-stick --client-addressing dhcp` offline; live DHCP lease validation remains guarded, so keep dry-run previews before any live test.
- For WAN dynamic-routing labs, prefer the built-in `wan-ring` template with `--routing ospf`, `rip`, `static`, or `none` instead of hand-writing router serial modules and configs.
- For campus dynamic-routing labs, prefer `campus --l3 --routing ospf` or `pt730-pipeline campus --routing ospf` when the lab needs multi-core L3 routing; use RIP/static only when the assignment requires them.
- For edge-security labs, prefer the built-in `edge-security` template's verified router/switch/PC/server models over ASA/firewall models that are risky in PT 7.3.0.
- Do not use DHCP client live validation by default; prefer static IP smoke checks.
- In this repository, prefix shell commands with `rtk` when the local `AGENTS.md`/`RTK.md` rule is active.
