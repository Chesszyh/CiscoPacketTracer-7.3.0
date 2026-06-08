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

The MCP wrapper exposes offline tools plus guarded live tools. Live tools require `allow_live=true`; `pt730_live_apply` with `dry_run=true` stays offline and is safe for preflight checks. Live wrappers also support safe command previews with `dry_run=true`: IOS commands, PC static/DHCP, terminal checks, IOS ping, Server-PT inspect/service/DNS/FTP/DHCP config, PC FTP client sessions, and simulation/PDU actions.

Example device preview:

```bash
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"pt730_live_ios","arguments":{"device":"R1","commands":["show ip interface brief"],"dry_run":true}}}' \
  | pt-reverse/bin/pt730-mcp
```

## Built-In Templates

```bash
pt-reverse/bin/pt730-template lan-star --pcs 4 --servers 1 --network 192.168.10.0/24 --output lan-star.json
pt-reverse/bin/pt730-template router-ring --routers 4 --interconnect-pool 10.20.0.0/28 --output router-ring.json
pt-reverse/bin/pt730-safety plan lan-star.json
pt-reverse/bin/pt730-render svg lan-star.json --output lan-star.svg
pt-reverse/bin/pt730-render drawio lan-star.json --output lan-star.drawio
pt-reverse/bin/pt730-render html lan-star.json --output lan-star.html
```

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
pt-reverse/bin/pt730-layout topology.configured.json --style campus --output topology.layout.json
pt-reverse/bin/pt730-safety plan topology.layout.json
pt-reverse/bin/pt730-render markdown topology.layout.json --output topology.md
pt-reverse/bin/pt730-render drawio topology.layout.json --output topology.drawio
pt-reverse/bin/pt730-config-plan export-configs topology.configured.json --output-dir configs
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
