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

The MCP wrapper exposes offline tools plus guarded live tools. Live tools require `allow_live=true`; `pt730_live_apply` with `dry_run=true` stays offline and is safe for preflight checks. Live wrappers also support safe command previews with `dry_run=true`: eval, smoke, IOS commands, PC static/DHCP, terminal checks, IOS ping, Server-PT inspect/service/DNS/FTP/email/NTP/Syslog/DHCP config, PC FTP client sessions, app/bridge/launch/recover lifecycle actions, and simulation/PDU actions. `pt730_schema`, catalog, and JavaScript safety checks are exposed as offline MCP tools. Model registry reads are exposed as MCP tools; `pt730_models_record` requires `allow_write=true` unless `dry_run=true`.

Example schema query:

```bash
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"pt730_schema","arguments":{"target":"compose","compact":true}}}' \
  | pt-reverse/bin/pt730-mcp
```

Example template generation through MCP:

```bash
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"pt730_template_lan_star","arguments":{"name":"AGENT","pcs":2,"servers":1,"network":"192.168.60.0/24","gateway":"192.168.60.1","dns":"192.168.60.254","layout_style":"grid","compact":true}}}' \
  | pt-reverse/bin/pt730-mcp
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"pt730_template_wireless_lan","arguments":{"name":"WIFI","aps":2,"laptops":4,"servers":1,"network":"192.168.80.0/24","gateway":"192.168.80.1","ssid":"PT730-LAB","layout_style":"lan","compact":true}}}' \
  | pt-reverse/bin/pt730-mcp
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"pt730_template_wan_ring","arguments":{"name":"AGENT","sites":3,"hosts_per_site":2,"servers_per_site":1,"routing":"rip","layout_style":"ring","compact":true}}}' \
  | pt-reverse/bin/pt730-mcp
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"pt730_template_campus","arguments":{"name":"AGENT","cores":2,"segments":4,"hosts_per_segment":2,"servers":4,"l3":true,"routing":"rip","layout_style":"campus","compact":true}}}' \
  | pt-reverse/bin/pt730-mcp
```

Example campus workflow steps through MCP:

```bash
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"pt730_ip_plan_campus","arguments":{"spec":"pt-reverse/examples/ip-plan-campus.json","compact":true}}}' \
  | pt-reverse/bin/pt730-mcp
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"pt730_compose_campus","arguments":{"spec":"pt-reverse/examples/compose-campus.json","layout_style":"grid","compact":true}}}' \
  | pt-reverse/bin/pt730-mcp
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"pt730_pipeline_campus","arguments":{"ip_plan":"pt-reverse/examples/ip-plan-campus.json","compose_spec":"pt-reverse/examples/compose-campus.json","output_dir":"compose-campus-out","routing":"rip","layout_style":"grid","compact":true}}}' \
  | pt-reverse/bin/pt730-mcp
```

Example layout control through MCP:

```bash
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"pt730_layout","arguments":{"plan":"pt-reverse/examples/simple-lan.json","style":"grid","canvas_width":400,"canvas_height":300,"spacing_x":120,"spacing_y":100,"margin":20,"compact":true}}}' \
  | pt-reverse/bin/pt730-mcp
```

Example visual render control through MCP:

```bash
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"pt730_render","arguments":{"format":"svg","plan":"pt-reverse/examples/simple-lan.json","theme":"dark","link_labels":false,"model_labels":false,"group_by":"network"}}}' \
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
pt-reverse/bin/pt730-template router-ring --routers 4 --interconnect-pool 10.20.0.0/28 --output router-ring.json
pt-reverse/bin/pt730-template wan-ring --sites 3 --hosts-per-site 2 --servers-per-site 1 --routing rip --output wan-ring.json
pt-reverse/bin/pt730-template campus --cores 2 --segments 4 --hosts-per-segment 2 --servers 4 --l3 --routing rip --output campus.json
pt-reverse/bin/pt730-safety plan lan-star.json
pt-reverse/bin/pt730-render svg lan-star.json --group-by network --output lan-star.svg
pt-reverse/bin/pt730-render drawio lan-star.json --group-by network --output lan-star.drawio
pt-reverse/bin/pt730-render html lan-star.json --group-by network --output lan-star.html
```

`wireless-lan` uses verified `AccessPoint-PT` and `Laptop-PT` models and writes
AP/SSID metadata under `ap_configs`. Wireless links use cable code `8109`, which
passes non-strict safety with a live-verification warning; keep live applies
small unless the user explicitly asks for wireless live validation.

## Campus Pipeline

```bash
pt-reverse/bin/pt730-pipeline campus \
  --ip-plan pt-reverse/examples/ip-plan-campus.json \
  --compose-spec pt-reverse/examples/compose-campus.json \
  --output-dir compose-campus-out \
  --routing rip
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
pt-reverse/bin/pt730-config-plan campus topology.composed.json --l3 --routing rip --output topology.configured.json
pt-reverse/bin/pt730-config-plan --compact campus topology.composed.json --ios-only
pt-reverse/bin/pt730-layout topology.configured.json --style campus --output topology.layout.json
pt-reverse/bin/pt730-safety plan topology.layout.json
pt-reverse/bin/pt730-render markdown topology.layout.json --output topology.md
pt-reverse/bin/pt730-render drawio topology.layout.json --theme paper --output topology.drawio
pt-reverse/bin/pt730-render svg topology.layout.json --theme dark --no-link-labels --output topology.clean.svg
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
