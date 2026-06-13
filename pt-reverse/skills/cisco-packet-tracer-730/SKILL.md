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

- Generate a small or representative lab topology: use `pt730-template lan-star`, `dual-stack-lan`, `wireless-lan`, `vlan-router-on-stick`, `switching-lab`, `server-services`, `edge-security`, `router-ring`, `wan-ring`, `campus`, `redundant-campus`, `college-network`, or `enterprise-edge`; through MCP, `pt730_template_lan_star`, `pt730_template_dual_stack_lan`, `pt730_template_wireless_lan`, `pt730_template_vlan_router_on_stick`, `pt730_template_switching_lab`, `pt730_template_server_services`, `pt730_template_edge_security`, `pt730_template_router_ring`, `pt730_template_wan_ring`, `pt730_template_campus`, `pt730_template_redundant_campus`, `pt730_template_college_network`, and `pt730_template_enterprise_edge` expose layout, no-layout, compact JSON, and template-specific options.
- Generate dual-stack IPv4/IPv6 labs with `pt730-template dual-stack-lan`; it emits static IPv4 `pc_configs`, IPv6 `ipv6_configs`, IOS `ipv6 unicast-routing`, IPv6 address summaries, and IPv6 verification-plan checks. IPv6 PC/Server GUI writes remain manual metadata until live PT 7.3.0 JavaScript APIs are verified.
- Generate VLAN DHCP labs with `pt730-template vlan-router-on-stick --client-addressing dhcp`; it emits router DHCP pools, DHCP client host configs, VLAN metadata, and report-renderable `dhcp_pools`.
- Generate STP/EtherChannel switching labs with `pt730-template switching-lab`; it emits dual distribution switches, dual-homed access switches, VLAN trunk/access ports, STP root roles, Port-channel1 EtherChannel, PortFast/BPDU Guard, static representative PCs, and report-renderable `vlan_configs`/`ios_configs`.
- Generate Server-PT service labs with `pt730-template server-services`; it emits a router gateway, access switch, DHCP/static clients, HTTP/DNS/FTP/TFTP/Email/NTP/Syslog/DHCP service metadata, server verification checks, and report-renderable `server_configs`.
- Generate a campus/course design: for the specific college-network assignment shape, start with `pt730-template college-network --total-pcs 1900 --servers 50 --l3-switches 6 --routing ospf`; it emits a representative topology plus full `metadata.ip_plan`, `vlan_configs`, website sections, and IOS configs while avoiding risky `3560-24PS` automation. For custom campus designs, use `pt730-ip-plan`, then `pt730-compose`, then `pt730-config-plan`, or run `pt730-pipeline campus`; `pt730-template campus --l3 --routing ospf` and `pt730-config-plan campus --l3 --routing ospf` emit campus OSPF router IDs, passive SVI interfaces, and direct network statements. Use `--routing eigrp` when a Cisco EIGRP lab is required; it emits EIGRP AS 100, passive SVI/LAN interfaces, and wildcard network statements. Use `pt730-template redundant-campus --routing ospf` or `--routing eigrp` when the design needs dual cores, dual-homed access, HSRP, STP root roles, DHCP relay/pools, and NTP/Syslog/SNMP in one renderable plan. Through MCP, `pt730_ip_plan_campus`, `pt730_compose_campus`, `pt730_pipeline_campus`, `pt730_template_redundant_campus`, and `pt730_template_college_network` expose compact JSON, routing, and layout-style controls where applicable.
- Generate WAN dynamic-routing labs with `pt730-template wan-ring --routing ospf`, `--routing eigrp`, or `--routing rip`; OSPF output includes router IDs, passive LAN interfaces, and per-router network statements, while EIGRP output uses AS 100 and wildcard network statements.
- Generate integrated enterprise HQ/branch/DMZ/Internet labs with `pt730-template enterprise-edge --routing ospf`, `--routing eigrp`, or `--routing bgp`; BGP mode emits static branch reachability plus eBGP AS 65001 to ISP AS 65000 for enterprise edge peering.
- Build and revise custom topology JSON incrementally with `pt730-plan new`, `set-metadata`, add/remove device/module/link commands, and add/remove helpers for AP configs, annotations, IPv4/IPv6 host configs, VLANs, DHCP pools, Server-PT services, IOS commands, and security policies when a template is not a good fit; through MCP use the matching `pt730_plan_*` tools, then run `pt730_layout`, `pt730_render`, safety, config export, or lab-bundle tools.
- Generate complete offline deliverable bundles with `pt730-lab template <lab-spec.json> --output-dir <dir>` or `pt730-lab plan <plan.json> --output-dir <dir>` when an agent should write topology JSON, safety report, SVG/draw.io/HTML/Markdown/summary render bundle, optional diagram audit, verification checklist, per-device `.cfg` files, and a manifest. Use `--preset report` or `render.preset: report` for report-ready paper theme; use `--preset presentation` or `render.preset: presentation` for dark high-contrast screenshots/slides. Both presets enable auto grouping, legend, hidden link labels, and default `diagram-audit`, `verification-json`, and `verification-md`; use `render.annotations`, CLI `--annotation`/`--annotations`, or MCP `annotations` to include report callouts in the lab topology and render bundle; add `pt730-lab report <dir>/manifest.json --output <dir>/deliverable.md` for a Markdown coursework index with artifact status, config files, verification plan counts, and recording checks. Through MCP use `pt730_lab_template`, `pt730_lab_plan`, and `pt730_lab_report`.
- Refine topology placement through MCP with `pt730_layout`; use canvas width/height, spacing, margin, style, and compact options when diagrams need clearer density or framing.
- Render outputs for review: use `pt730-render bundle <plan.json> --output-dir <dir>` when an agent should create SVG, draw.io, HTML, Markdown, summary, optional course-audit/diagram-audit/verification output, and a manifest in one offline call; through MCP use `pt730_render_bundle`. Use `pt730-render views <plan.json> --output-dir <dir> --group-by auto` or MCP `pt730_render_views` when a complex topology needs an overview plus grouped detail SVG/draw.io/HTML/summary artifacts for report/PPT/video explanation. Prefer `--preset report` or MCP `preset=report` for paper report screenshots, and `--preset presentation` or MCP `preset=presentation` for dark high-contrast video/PPT visuals. For single outputs, use `pt730-render svg`, `drawio`, `html`, `markdown`, `summary`, `course-audit`, `diagram-audit`, and `verification-plan --format json|markdown`; visual renders support `--preset manual|report|presentation`, `--theme light|dark|paper`, `--title`, `--legend`, `--no-link-labels`, `--no-model-labels`, `--group-by auto|network|vlan|site|category`, plan-level `annotations` callouts, and render-only CLI `--annotation`/`--annotations` or MCP `annotations`, exposed through MCP as `preset`, `theme`, `title`, `legend`, `link_labels`, `model_labels`, `group_by`, and `annotations`. Markdown and summary renders expose assignment IP/VLAN and website-plan tables/fields when topology metadata contains `ip_plan` or `website_plan`. Through MCP, use `pt730_verification_plan` or `pt730_render` with `format=verification-json|verification-md` for offline validation checklists.
- Plan and export IOS configs: use `pt730-config-plan campus` and `pt730-config-plan export-configs`; through MCP, `pt730_config_plan_campus` exposes `ios_only`/`compact` plus `none|rip|eigrp|ospf|static` routing, and `pt730_export_configs` exposes `source`/`compact`.
- Render high-level IOS snippets with `pt730-ios-template`; use it for IOS management access/security, local users, SSH, console/VTY lines, banners, STP, EtherChannel/Port-channel, DHCP relay, HSRP/standby, IOS DHCP pools, NTP/Syslog/SNMP, VLAN/trunk/access/routed interfaces, interface IPv6 addresses, IPv6 unicast routing, RIP/EIGRP/OSPF/BGP/static routes, OSPFv3/RIPng/IPv6 static routes, ACLs, and NAT when a template or config-plan output needs extra switch/router features.
- Query input schemas through MCP with `pt730_schema` before generating unfamiliar template/IP-plan/compose/config/pipeline/lab/render/plan/IOS-template specs; use `target=render` or CLI `pt730-render schema` for render formats, options, and annotation fields, and `target=plan` or CLI `pt730-plan schema` for custom topology editing fields.
- Query catalog and JavaScript safety through MCP with `pt730_catalog`, `pt730_safety_js`, and `pt730_safety_policy`.
- Preview live IOS/PC DHCP/server service/account/config/FTP/simulation/lifecycle MCP calls with `dry_run=true` before any `allow_live=true` execution.
- Inspect model safety metadata through MCP with `pt730_models_manifest`, `pt730_models_queue`, and `pt730_models_validate` dry runs; write records only when explicitly allowed.
- Query or apply live Packet Tracer only after bridge recovery/safety checks.

For exact command patterns, read `references/workflows.md` only when needed.

## Safety Rules

- Fixed version is Cisco Packet Tracer 7.3.0. Do not switch to newer Packet Tracer behavior or docs.
- Treat live Script Module operations as crash-prone. Keep live mutations sequential and small.
- Avoid risky/blocked models unless the user explicitly asks to validate them.
- Before opening an existing `.pkt` through `pt730-app open` or MCP
  `pt730_live_app action=open`, run or rely on the built-in
  `pt730-app inspect-pkt` preflight. Known crash fingerprints and visible
  risky model strings such as `3560-24PS`/`3650-24PS` are blocked by default;
  pass `--allow-risky`/`allow_risky=true` only for supervised recovery attempts.
- For unattended wireless templates, use the built-in `wireless-lan` template's verified `AccessPoint-PT` and `Laptop-PT` models; treat wireless cable code `8109` warnings as offline-only until live validation is explicitly requested.
- For VLAN/trunk labs, prefer the built-in `vlan-router-on-stick` template; it uses verified models and emits router 802.1Q subinterfaces, switch trunk/access ports, VLAN metadata, static hosts, and optional per-VLAN servers.
- For STP/EtherChannel labs, prefer the built-in `switching-lab` template for complete safe topologies; use `pt730-ios-template` when adding custom switching snippets to another plan. Keep live paste/apply small because model support varies by IOS device.
- For HSRP, IOS DHCP, NTP/Syslog/SNMP, and DHCP relay labs, prefer `pt730-ios-template` offline first; treat live support as IOS-model-dependent and paste in small batches.
- For DHCP VLAN labs, use `vlan-router-on-stick --client-addressing dhcp` offline; live DHCP lease validation remains guarded, so keep dry-run previews before any live test.
- For Server-PT service labs, prefer `server-services` offline; live service toggles/accounts/DNS/DHCP remain guarded and should be previewed with `dry_run=true` before `allow_live=true`.
- For IPv6 labs, prefer `dual-stack-lan` offline for topology/host metadata and `pt730-ios-template` for router/L3-switch IPv6 CLI such as `ipv6 unicast-routing`, interface IPv6 addresses, OSPFv3, RIPng, and IPv6 static routes. Keep PC/Server IPv6 GUI writes as report/manual metadata unless the user explicitly asks to live-validate PT 7.3.0 host IPv6 APIs.
- For WAN dynamic-routing labs, prefer the built-in `wan-ring` template with `--routing ospf`, `eigrp`, `rip`, `static`, or `none` instead of hand-writing router serial modules and configs.
- For campus dynamic-routing labs, prefer `campus --l3 --routing ospf`, `campus --l3 --routing eigrp`, `redundant-campus --routing ospf`, `redundant-campus --routing eigrp`, or `pt730-pipeline campus --routing ospf|eigrp` when the lab needs multi-core L3 routing; use RIP/static only when the assignment requires them.
- For edge-security labs, prefer the built-in `edge-security` template's verified router/switch/PC/server models over ASA/firewall models that are risky in PT 7.3.0.
- For integrated enterprise labs, prefer `enterprise-edge --routing ospf`, `enterprise-edge --routing eigrp`, or `enterprise-edge --routing bgp` before hand-combining campus, WAN, DMZ, and ISP-edge templates; render with `--group-by auto` or `site`.
- Do not use DHCP client live validation by default; prefer static IP smoke checks.
- In this repository, prefix shell commands with `rtk` when the local `AGENTS.md`/`RTK.md` rule is active.
