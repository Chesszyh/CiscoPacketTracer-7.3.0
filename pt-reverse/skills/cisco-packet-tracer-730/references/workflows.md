# PT 7.3 CLI Workflows

## Offline Self-Check

```bash
pt-reverse/bin/pt730-selftest
python3 -m unittest discover -s pt-reverse/tests -p 'test_*.py'
pt-reverse/bin/pt730-capabilities
pt-reverse/bin/pt730-mcp --list-tools
```

## MCP Stdio Wrapper

Start the server:

```bash
pt-reverse/bin/pt730-mcp
```

Minimal JSON-RPC smoke call:

```bash
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"pt730_render","arguments":{"format":"summary","plan":"pt-reverse/examples/simple-lan.json"}}}' \
  | pt-reverse/bin/pt730-mcp
```

The MCP wrapper exposes offline tools plus guarded live tools. Live tools require `allow_live=true`; `pt730_live_apply` with `dry_run=true` stays offline and is safe for preflight checks. Live wrappers also support safe command previews with `dry_run=true`: eval, smoke, IOS commands, PC static/DHCP, terminal checks, IOS ping, Server-PT inspect/service/DNS/FTP/email/NTP/Syslog/DHCP config, PC FTP client sessions, app/bridge/launch/recover lifecycle actions, and simulation/PDU actions. `pt730_schema` exposes template/IP-plan/compose/config/pipeline/lab/IOS-template schemas; catalog and JavaScript safety checks are exposed as offline MCP tools. Model registry reads are exposed as MCP tools; `pt730_models_record` requires `allow_write=true` unless `dry_run=true`.

Example schema query:

```bash
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"pt730_schema","arguments":{"target":"compose","compact":true}}}' \
  | pt-reverse/bin/pt730-mcp
printf '%s\n' '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"pt730_schema","arguments":{"target":"lab","compact":true}}}' \
  | pt-reverse/bin/pt730-mcp
```

Example template generation through MCP:

```bash
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"pt730_template_lan_star","arguments":{"name":"AGENT","pcs":2,"servers":1,"network":"192.168.60.0/24","gateway":"192.168.60.1","dns":"192.168.60.254","layout_style":"grid","compact":true}}}' \
  | pt-reverse/bin/pt730-mcp
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"pt730_template_wireless_lan","arguments":{"name":"WIFI","aps":2,"laptops":4,"servers":1,"network":"192.168.80.0/24","gateway":"192.168.80.1","ssid":"PT730-LAB","layout_style":"lan","compact":true}}}' \
  | pt-reverse/bin/pt730-mcp
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"pt730_template_vlan_router_on_stick","arguments":{"name":"ROAS","vlans":3,"hosts_per_vlan":2,"servers_per_vlan":1,"native_vlan":10,"client_addressing":"dhcp","layout_style":"hierarchical","compact":true}}}' \
  | pt-reverse/bin/pt730-mcp
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"pt730_template_edge_security","arguments":{"name":"SEC","inside_hosts":3,"dmz_servers":2,"internet_hosts":1,"domain":"sec.local","layout_style":"hierarchical","compact":true}}}' \
  | pt-reverse/bin/pt730-mcp
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"pt730_template_wan_ring","arguments":{"name":"AGENT","sites":3,"hosts_per_site":2,"servers_per_site":1,"routing":"ospf","layout_style":"ring","compact":true}}}' \
  | pt-reverse/bin/pt730-mcp
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"pt730_template_campus","arguments":{"name":"AGENT","cores":2,"segments":4,"hosts_per_segment":2,"servers":4,"l3":true,"routing":"ospf","layout_style":"campus","compact":true}}}' \
  | pt-reverse/bin/pt730-mcp
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"pt730_template_redundant_campus","arguments":{"name":"AGENT","segments":4,"hosts_per_segment":2,"servers":4,"routing":"ospf","layout_style":"campus","compact":true}}}' \
  | pt-reverse/bin/pt730-mcp
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"pt730_template_enterprise_edge","arguments":{"name":"ENT","campus_vlans":3,"hosts_per_vlan":2,"branches":2,"branch_hosts":2,"dmz_servers":2,"routing":"ospf","layout_style":"campus","compact":true}}}' \
  | pt-reverse/bin/pt730-mcp
```

Example full lab bundle through MCP:

```bash
cat > lab-spec.json <<'JSON'
{
  "name": "enterprise-demo",
  "template": "enterprise-edge",
  "template_options": {
    "name": "ENT",
    "campus_vlans": 3,
    "hosts_per_vlan": 2,
    "campus_servers": 4,
    "branches": 2,
    "branch_hosts": 2,
    "dmz_servers": 2,
    "routing": "ospf"
  },
  "render": {"basename": "enterprise-demo", "preset": "report"},
  "export_configs": true
}
JSON
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"pt730_lab_template","arguments":{"spec":"lab-spec.json","output_dir":"enterprise-demo-lab","compact":true}}}' \
  | pt-reverse/bin/pt730-mcp
printf '%s\n' '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"pt730_lab_plan","arguments":{"plan":"pt-reverse/examples/two-router-serial-configured.json","output_dir":"serial-plan-lab","basename":"serial","preset":"report","compact":true}}}' \
  | pt-reverse/bin/pt730-mcp
printf '%s\n' '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"pt730_lab_report","arguments":{"manifest":"enterprise-demo-lab/manifest.json","output":"enterprise-demo-lab/deliverable.md","title":"Enterprise Demo Deliverable","compact":true}}}' \
  | pt-reverse/bin/pt730-mcp
```

Example campus workflow steps through MCP:

```bash
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"pt730_ip_plan_campus","arguments":{"spec":"pt-reverse/examples/ip-plan-campus.json","compact":true}}}' \
  | pt-reverse/bin/pt730-mcp
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"pt730_compose_campus","arguments":{"spec":"pt-reverse/examples/compose-campus.json","layout_style":"grid","compact":true}}}' \
  | pt-reverse/bin/pt730-mcp
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"pt730_pipeline_campus","arguments":{"ip_plan":"pt-reverse/examples/ip-plan-campus.json","compose_spec":"pt-reverse/examples/compose-campus.json","output_dir":"compose-campus-out","routing":"ospf","layout_style":"grid","compact":true}}}' \
  | pt-reverse/bin/pt730-mcp
```

Example layout control through MCP:

```bash
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"pt730_layout","arguments":{"plan":"pt-reverse/examples/simple-lan.json","style":"grid","canvas_width":400,"canvas_height":300,"spacing_x":120,"spacing_y":100,"margin":20,"compact":true}}}' \
  | pt-reverse/bin/pt730-mcp
```

Example visual render control through MCP:

```bash
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"pt730_render","arguments":{"format":"svg","plan":"pt-reverse/examples/simple-lan.json","theme":"dark","title":"Simple LAN","legend":true,"link_labels":false,"model_labels":false,"group_by":"network"}}}' \
  | pt-reverse/bin/pt730-mcp
printf '%s\n' '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"pt730_render","arguments":{"format":"svg","plan":"pt-reverse/examples/simple-lan.json","preset":"report"}}}' \
  | pt-reverse/bin/pt730-mcp
printf '%s\n' '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"pt730_render","arguments":{"format":"diagram-audit","plan":"pt-reverse/examples/simple-lan.json","preset":"report"}}}' \
  | pt-reverse/bin/pt730-mcp
printf '%s\n' '{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"pt730_render_bundle","arguments":{"plan":"pt-reverse/examples/simple-lan.json","output_dir":"simple-lan-render","basename":"simple-lan","preset":"report"}}}' \
  | pt-reverse/bin/pt730-mcp
```

Example config planning through MCP:

```bash
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"pt730_config_plan_campus","arguments":{"plan":"pt-reverse/course-design/college-network-topology-pt73-safe.json","ios_only":true,"compact":true}}}' \
  | pt-reverse/bin/pt730-mcp
```

Example config export through MCP:

```bash
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"pt730_export_configs","arguments":{"plan":"topology.configured.json","output_dir":"configs","source":"pt730-config-plan campus","compact":true}}}' \
  | pt-reverse/bin/pt730-mcp
```

Example IOS template rendering for switching features:

```bash
pt-reverse/bin/pt730-ios-template render pt-reverse/examples/ios-template-switching.json
pt-reverse/bin/pt730-ios-template render pt-reverse/examples/ios-template-switching.json --topology-json
pt-reverse/bin/pt730-ios-template render pt-reverse/examples/ios-template-fhrp-services.json
pt-reverse/bin/pt730-ios-template render pt-reverse/examples/ios-template-fhrp-services.json --topology-json
```

The switching IOS template supports STP/Rapid PVST root and priority commands,
portfast/bpduguard defaults, EtherChannel member `channel-group` commands, and
Port-channel trunk/access/routed interface configuration.
The FHRP/services template supports DHCP relay `ip helper-address`, HSRP
`standby` groups, IOS DHCP pools, NTP servers, Syslog hosts, and SNMP
communities for dual-core campus labs.

Example device preview:

```bash
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"pt730_live_ios","arguments":{"device":"R1","commands":["show ip interface brief"],"dry_run":true}}}' \
  | pt-reverse/bin/pt730-mcp
```

Example lifecycle preview:

```bash
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"pt730_live_recover","arguments":{"wait":5,"notify":true,"dry_run":true}}}' \
  | pt-reverse/bin/pt730-mcp
```

Example Server-PT account/config preview:

```bash
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"pt730_live_server_email_add","arguments":{"device":"SRV1","username":"student","password":"packet","domain":"example.local","dry_run":true}}}' \
  | pt-reverse/bin/pt730-mcp
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"pt730_live_server_ntp_config","arguments":{"device":"SRV1","enabled":true,"auth":"on","key_id":"1","md5":"cisco","dry_run":true}}}' \
  | pt-reverse/bin/pt730-mcp
```

Example catalog/safety calls:

```bash
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"pt730_catalog","arguments":{"action":"ports","model":"2911"}}}' \
  | pt-reverse/bin/pt730-mcp
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"pt730_safety_js","arguments":{"code":"ipc.network().getDeviceCount()"}}}' \
  | pt-reverse/bin/pt730-mcp
```

## Built-In Templates

```bash
pt-reverse/bin/pt730-template lan-star --pcs 4 --servers 1 --network 192.168.10.0/24 --output lan-star.json
pt-reverse/bin/pt730-template wireless-lan --aps 2 --laptops 4 --servers 1 --ssid PT730-LAB --network 192.168.80.0/24 --output wireless-lan.json
pt-reverse/bin/pt730-template vlan-router-on-stick --vlans 3 --hosts-per-vlan 2 --servers-per-vlan 1 --native-vlan 10 --client-addressing dhcp --output vlan-router-on-stick.json
pt-reverse/bin/pt730-template edge-security --inside-hosts 3 --dmz-servers 2 --internet-hosts 1 --domain edge.local --output edge-security.json
pt-reverse/bin/pt730-template router-ring --routers 4 --interconnect-pool 10.20.0.0/28 --output router-ring.json
pt-reverse/bin/pt730-template wan-ring --sites 3 --hosts-per-site 2 --servers-per-site 1 --routing ospf --output wan-ring.json
pt-reverse/bin/pt730-template campus --cores 2 --segments 4 --hosts-per-segment 2 --servers 4 --l3 --routing ospf --output campus.json
pt-reverse/bin/pt730-template redundant-campus --segments 4 --hosts-per-segment 2 --servers 4 --routing ospf --output redundant-campus.json
pt-reverse/bin/pt730-template enterprise-edge --campus-vlans 3 --branches 2 --dmz-servers 2 --routing ospf --output enterprise-edge.json
pt-reverse/bin/pt730-lab template lab-spec.json --output-dir enterprise-demo-lab
pt-reverse/bin/pt730-lab plan topology.json --output-dir topology-lab --basename topology --formats svg,drawio,html,markdown,summary,diagram-audit --title "Campus Topology" --legend
pt-reverse/bin/pt730-lab plan topology.json --output-dir topology-lab-report --basename topology --preset report
pt-reverse/bin/pt730-lab report topology-lab/manifest.json --output topology-lab/deliverable.md
pt-reverse/bin/pt730-safety plan lan-star.json
pt-reverse/bin/pt730-render svg lan-star.json --title "LAN Star" --legend --group-by network --output lan-star.svg
pt-reverse/bin/pt730-render drawio lan-star.json --group-by network --output lan-star.drawio
pt-reverse/bin/pt730-render html lan-star.json --group-by network --output lan-star.html
pt-reverse/bin/pt730-render diagram-audit lan-star.json --output lan-star.diagram-audit.json
pt-reverse/bin/pt730-render bundle lan-star.json --output-dir lan-star-render --basename lan-star --formats svg,drawio,html,markdown,summary,diagram-audit --title "LAN Star" --legend
pt-reverse/bin/pt730-render bundle lan-star.json --output-dir lan-star-report --basename lan-star --preset report
```

`wireless-lan` uses verified `AccessPoint-PT` and `Laptop-PT` models and writes
AP/SSID metadata under `ap_configs`. Wireless links use cable code `8109`, which
passes non-strict safety with a live-verification warning; keep live applies
small unless the user explicitly asks for wireless live validation.

`vlan-router-on-stick` uses verified `2911`, `2960-24TT`, `PC-PT`, and
`Server-PT` models. It writes `vlan_configs`, router 802.1Q subinterfaces,
switch trunk/access IOS commands, static or DHCP host configs, optional router
DHCP pools under `dhcp_pools`, and optional per-VLAN HTTP/DNS server records.
DHCP client live lease validation remains guarded; offline generation and
rendering are safe.

`wan-ring --routing ospf` writes router IDs, passive LAN interfaces, and
per-router `network ... area 0` statements for each direct LAN/serial subnet.
Use `rip`, `static`, or `none` when that better matches the lab.

`campus --l3 --routing ospf` writes OSPF process 1, deterministic router IDs,
SVI passive-interface commands, and direct SVI/core-link `network ... area 0`
statements for multi-core campus L3 labs. Use `rip`, `static`, or `none` when
that better matches the assignment.

`redundant-campus --routing ospf` writes a dual-core, dual-homed campus plan
with HSRP virtual gateways, STP primary/secondary root roles, DHCP relay, IOS
DHCP pools, NTP/Syslog/SNMP client config, server services, and VLAN metadata
for group-by-VLAN SVG/draw.io/HTML renders. Use `rip` or `none` when dynamic
OSPF is not wanted.

`enterprise-edge --routing ospf` writes an integrated HQ/branch/DMZ/Internet
plan with HQ router-on-a-stick VLANs, server zone, DMZ public services,
ISP/Internet test LAN, branch serial WAN routers, NAT overload, outside ACL
metadata, and HTTP/DNS/FTP/email server configs. Use `--group-by auto` or
`--group-by site` for clearer SVG/draw.io/HTML renders.

`edge-security` uses verified `2911`, `2960-24TT`, `PC-PT`, and `Server-PT`
models to generate an ISP edge, inside LAN, DMZ, Internet test host, NAT
overload, outside ACL, static routes, and `security_policies` metadata. Use it
for ASA-like security labs without touching risky ASA models in PT 7.3.0.

## Lab Bundle

Use `pt730-lab template <lab-spec.json> --output-dir <out-dir>` when an agent
should create a complete offline deliverable from one template spec. Use
`pt730-lab plan <plan.json> --output-dir <out-dir>` for the same bundle after
an agent has already composed or hand-authored a custom topology JSON. The
output directory contains `topology.json`, `safety.json`,
`render/<basename>.*`, `configs/*.cfg`, and `manifest.json`. Include
`diagram-audit` in render `formats` when the agent should emit a JSON quality
gate for empty diagrams, missing coordinates, overlaps, disconnected
components, oversized canvases, and dense label/grouping advice. Template specs
use snake_case `template_options`; both paths can set render `formats`,
`theme`, title, legend, labels, and `group_by`. Use `--preset report` or
`render.preset: report` for report-ready paper theme, auto grouping, legend,
hidden link labels, and default `diagram-audit`. Use `pt730-lab report
<out-dir>/manifest.json --output <out-dir>/deliverable.md` to add a Markdown
coursework index with artifact status, safety summary, render outputs, config
files, and suggested recording checks. Through MCP, call `pt730_lab_report`.

## Campus Pipeline

```bash
pt-reverse/bin/pt730-pipeline campus \
  --ip-plan pt-reverse/examples/ip-plan-campus.json \
  --compose-spec pt-reverse/examples/compose-campus.json \
  --output-dir compose-campus-out \
  --routing ospf
```

Expected key outputs:

- `ip-plan.json`
- `topology.layout.json`
- `topology.summary.json`
- `topology.md`
- `topology.svg`
- `topology.drawio`
- `topology.html`
- `configs/*.cfg`
- `manifest.json`

## Manual Campus Steps

```bash
pt-reverse/bin/pt730-ip-plan campus pt-reverse/examples/ip-plan-campus.json --output ip-plan-campus.json
pt-reverse/bin/pt730-compose campus pt-reverse/examples/compose-campus.json --segments-from-ip-plan ip-plan-campus.json --output topology.composed.json
pt-reverse/bin/pt730-config-plan campus topology.composed.json --l3 --routing ospf --output topology.configured.json
pt-reverse/bin/pt730-config-plan --compact campus topology.composed.json --ios-only
pt-reverse/bin/pt730-layout topology.configured.json --style campus --output topology.layout.json
pt-reverse/bin/pt730-safety plan topology.layout.json
pt-reverse/bin/pt730-render markdown topology.layout.json --output topology.md
pt-reverse/bin/pt730-render drawio topology.layout.json --theme paper --output topology.drawio
pt-reverse/bin/pt730-render svg topology.layout.json --theme dark --title "Campus Topology" --legend --no-link-labels --output topology.clean.svg
pt-reverse/bin/pt730-render diagram-audit topology.layout.json --output topology.diagram-audit.json
pt-reverse/bin/pt730-render bundle topology.layout.json --output-dir topology-render --basename topology --formats svg,drawio,html,markdown,summary,diagram-audit --theme paper --title "Campus Topology" --legend --group-by vlan
pt-reverse/bin/pt730-config-plan --compact export-configs topology.configured.json --output-dir configs --source "pt730-config-plan campus"
```

## Course Audit

```bash
pt-reverse/bin/pt730-render course-audit \
  pt-reverse/course-design/college-network-topology-pt73-safe.json \
  --output pt-reverse/course-design/college-network-topology-pt73-safe.audit.json
```

The audit checks required VLAN links, `172.16.1.0/26` server space, `192.168.0.0/21` PC space, and representative host coverage.

## Live Apply Guardrail

Only use after the user asks for live Packet Tracer interaction:

```bash
pt-reverse/bin/pt730-recover --notify
pt-reverse/bin/pt730-safety plan <plan.json>
pt-reverse/bin/pt730-topo --timeout 1 apply --dry-run <plan.json>
pt-reverse/bin/pt730-topo apply --batch-size 1 <plan.json>
pt-reverse/bin/pt730-app save-as <out.pkt>
```
