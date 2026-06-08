# Packet Tracer 7.3.0 automation notes

This directory contains local interoperability work for controlling the installed
Cisco Packet Tracer 7.3.0 copy from Linux/Wine.

Read `SAFETY.md` before adding new live probes.  PT 7.3.0 can crash when some
internal process APIs are called through the Script Module bridge.

中文完整操作说明见 [`使用手册.md`](使用手册.md)。

## Current runtime

Start or check Packet Tracer:

```bash
pt-reverse/bin/pt730-launch start
pt-reverse/bin/pt730-launch status
pt-reverse/bin/pt730-recover --notify
pt-reverse/bin/pt730-selftest
pt-reverse/bin/pt730-mcp --list-tools
pt-reverse/bin/pt730-capabilities
pt-reverse/bin/pt730-models manifest
pt-reverse/bin/pt730-template schema
pt-reverse/bin/pt730-template lan-star --pcs 4 --servers 1 --network 192.168.10.0/24
pt-reverse/bin/pt730-template router-ring --routers 4 --interconnect-pool 10.20.0.0/28
pt-reverse/bin/pt730-pipeline schema
pt-reverse/bin/pt730-pipeline campus --ip-plan pt-reverse/examples/ip-plan-campus.json --compose-spec pt-reverse/examples/compose-campus.json --output-dir compose-campus-out --routing rip
pt-reverse/bin/pt730-ip-plan schema
pt-reverse/bin/pt730-ip-plan campus pt-reverse/examples/ip-plan-campus.json
pt-reverse/bin/pt730-compose schema
pt-reverse/bin/pt730-compose campus pt-reverse/examples/compose-campus.json
pt-reverse/bin/pt730-config-plan schema
pt-reverse/bin/pt730-ios-template schema
pt-reverse/bin/pt730-ios-template render pt-reverse/examples/ios-template-campus-router.json
pt-reverse/bin/pt730-layout pt-reverse/examples/simple-lan.json --style lan
pt-reverse/bin/pt730-render mermaid pt-reverse/examples/simple-lan.json
pt-reverse/bin/pt730-render svg pt-reverse/examples/simple-lan.json
pt-reverse/bin/pt730-render drawio pt-reverse/examples/simple-lan.json
pt-reverse/bin/pt730-render html pt-reverse/examples/simple-lan.json
pt-reverse/bin/pt730-render markdown pt-reverse/examples/simple-lan.json
pt-reverse/bin/pt730-render summary pt-reverse/examples/simple-lan.json
pt-reverse/bin/pt730-render course-audit pt-reverse/course-design/college-network-topology-pt73-safe.json
```

Install the Codex skill wrapper from this repo when an agent should discover the
workflow automatically:

```bash
ln -sfn "$PWD/pt-reverse/skills/cisco-packet-tracer-730" "$HOME/.codex/skills/cisco-packet-tracer-730"
```

Run the MCP stdio wrapper when an MCP client should call the offline tools:

```bash
pt-reverse/bin/pt730-mcp
```

The MCP wrapper exposes offline tools and guarded live tools.  Any live
Packet Tracer contact requires `allow_live=true`; `pt730_live_apply`,
`pt730_live_eval`, `pt730_live_smoke`, IOS/terminal/ping tools, PC static/DHCP
tools, Server-PT service/account/config tools, FTP client tools,
app/bridge/launch/recover lifecycle tools, and simulation/PDU tools support
`dry_run=true` previews that return the underlying CLI command without touching
Packet Tracer. Catalog and JavaScript safety checks are exposed offline through
MCP, along with `pt730_schema` for retrieving template, IP-plan, compose,
config-plan, pipeline, and IOS-template input schemas. Model registry reads are
exposed through MCP; model metadata writes require `allow_write=true` unless run
as `dry_run=true`.
Built-in template MCP tools expose the same DNS, layout, no-layout, compact,
and naming options as the underlying `pt730-template` CLI.
Campus workflow MCP tools expose compact JSON and layout-style controls through
`pt730_ip_plan_campus`, `pt730_compose_campus`, and `pt730_pipeline_campus`.
Render MCP tools expose visual theme and label controls through `pt730_render`
for SVG, draw.io, HTML, and Mermaid where supported.
The `pt730_layout` MCP tool exposes canvas size, spacing, margin, and compact
JSON controls for denser or cleaner topology diagrams.
Config planning MCP tools expose IOS-only output, source filtering, and compact
JSON controls through `pt730_config_plan_campus` and `pt730_export_configs`.

The known-good launch path is:

```bash
cd "Cisco Packet Tracer 7.3.0/bin"
env WINEDEBUG=-all QTWEBENGINE_REMOTE_DEBUGGING=9223 wine PacketTracer7.exe --pt-ipc-port 39000
```

Observed/expected listening ports:

- `39000`: Packet Tracer IPC/PTMP when the ExApp IPC listener is active
- `38000`: Packet Tracer Multiuser
- `9223`: QtWebEngine remote debugging

## PTMP probe

Run:

```bash
python3 pt-reverse/pt730/ptmp_client.py probe
```

Expected Packet Tracer 7.3.0 behavior:

1. PTMP text-mode negotiation succeeds.
2. Empty clear-text auth succeeds.
3. Packet Tracer disconnects with `Cep Not Registered` because the client has
   not registered as a valid ExApp/CEP.

That confirms the socket layer is reachable, but not yet sufficient for creating
topologies.

## Built-in automation surfaces

Packet Tracer 7.3.0 exposes two relevant automation surfaces:

- `Extensions -> IPC`: external applications ("ExApps") over PTMP on default
  port `39000`.
- `Extensions -> Scripting`: in-process JavaScript Script Modules with access to
  the `ipc` object.

The local help files confirm that Script Modules can directly call IPC APIs from
JavaScript. Important methods observed in the help/binary surface include:

- `ipc.network()`
- `ipc.appWindow()`
- `LogicalWorkspace.addDevice(devType, devModel, x, y)`
- `LogicalWorkspace.createLink(...)`
- `AppWindow.fileNew(...)`, `fileOpen(...)`, `fileSaveAs(...)`,
  `fileSaveToBytes(...)`
- `Network.getDevice(...)`, `getDeviceAt(...)`, `getDeviceCount(...)`,
  `getLinkAt(...)`
- device command-line access via `device.getCommandLine().enterCommand(...)`

## Practical assessment

Direct CLI control through a documented command-line API is not available in
Packet Tracer 7.3.0. A full AI-agent workflow is still feasible, but it needs one
of these bridge strategies:

1. Register a real ExApp/CEP over PTMP. This requires a valid `.pta` metadata
   entry and the post-auth CEP registration message format.
2. Install a Script Module once through Packet Tracer's GUI. The module can run
   inside PT, expose a local HTTP/TCP bridge, and call `ipc.network()` directly.

Existing community MCP projects use the second strategy with a PTBuilder module
and a localhost bridge, but they currently target Packet Tracer 8.2+ rather than
7.3.0, so compatibility must be tested instead of assumed.

## Local bridge workflow

Start Packet Tracer and the localhost bridge:

```bash
pt-reverse/bin/pt730-launch start
pt-reverse/bin/pt730-bridge start
pt-reverse/bin/pt730-bridge bootstrap
```

On PT 7.3.0, install/start the Builder through
`Extensions -> Scripting -> Configure PT Script Modules`.  Add
`pt-reverse/upstream/MCP-Packet-Tracer/V3-MCP-BUILDER.pts`, select the new
Builder module, click `Start`, then open its code editor (`Edit` or the Builder
Code Editor menu if it appears).  Paste the bootstrap JavaScript there and click
Run.  After that, command-line calls can drive Packet Tracer through the Script
Module:

```bash
pt-reverse/bin/pt730-eval --expr 'ipc.network().getDeviceCount()'
printf '%s\n' '"stdin:"+ipc.network().getLinkCount()' | pt-reverse/bin/pt730-eval --expr --stdin
pt-reverse/bin/pt730-app count
pt-reverse/bin/pt730-topo query
pt-reverse/bin/pt730-topo query --summary
pt-reverse/bin/pt730-topo summarize-query pt-reverse/examples/simple-lan-live-query.json
pt-reverse/bin/pt730-template lan-star --pcs 4 --servers 1 --network 192.168.10.0/24
pt-reverse/bin/pt730-template router-ring --routers 4 --interconnect-pool 10.20.0.0/28
pt-reverse/bin/pt730-pipeline campus --ip-plan pt-reverse/examples/ip-plan-campus.json --compose-spec pt-reverse/examples/compose-campus.json --output-dir compose-campus-out --routing rip
pt-reverse/bin/pt730-ip-plan campus pt-reverse/examples/ip-plan-campus.json --output ip-plan-campus.json
pt-reverse/bin/pt730-compose campus pt-reverse/examples/compose-campus.json --segments-from-ip-plan ip-plan-campus.json --output compose-campus.layout.json
pt-reverse/bin/pt730-config-plan campus compose-campus.layout.json --l3 --routing rip --output compose-campus.configured.json
pt-reverse/bin/pt730-topo apply --dry-run pt-reverse/examples/simple-lan.json
pt-reverse/bin/pt730-layout pt-reverse/examples/simple-lan.json --style lan --output simple-lan.layout.json
pt-reverse/bin/pt730-topo apply pt-reverse/examples/simple-lan.json
pt-reverse/bin/pt730-topo apply --replace pt-reverse/examples/four-router-ring.json
pt-reverse/bin/pt730-topo apply --replace pt-reverse/examples/two-router-serial.json
pt-reverse/bin/pt730-topo apply --replace --batch-size 2 pt-reverse/examples/two-router-serial-configured.json
pt-reverse/bin/pt730-topo apply --strict-safety pt-reverse/examples/simple-lan.json
pt-reverse/bin/pt730-ios R_DEMO --cmd 'show ip interface brief'
pt-reverse/bin/pt730-ping R_AUTO1 10.10.10.2
pt-reverse/bin/pt730-pc dhcp PC_DHCP --renew --wait 10 --expect-network 192.168.200.0/24
pt-reverse/bin/pt730-term PC_DHCP --cmd 'ping dhcpdemo.local' --wait 8 --expect 'Lost = 0 \\(0% loss\\)'
pt-reverse/bin/pt730-ftp PC_DHCP 192.168.200.10 --username lab --password packet --cmd dir --expect 'ftp>'
pt-reverse/bin/pt730-sim simple-pdu PC_DHCP SRV_DHCP
pt-reverse/bin/pt730-safety plan pt-reverse/examples/server-dhcp-lan.json
pt-reverse/bin/pt730-models manifest
pt-reverse/bin/pt730-models queue
pt-reverse/bin/pt730-models probe-plan 1841
pt-reverse/bin/pt730-models validate 1841 --dry-run
pt-reverse/bin/pt730-models validate 1841 --live --record-failure-status risky
pt-reverse/bin/pt730-models validate-batch --dry-run --limit 2
pt-reverse/bin/pt730-models record 1841 --status risky --reason 'Packet Tracer crashed' --evidence './bin/1.dmp'
pt-reverse/bin/pt730-ios-template render pt-reverse/examples/ios-template-campus-router.json --topology-json
pt-reverse/bin/pt730-capabilities --table
pt-reverse/bin/pt730-render mermaid pt-reverse/examples/simple-lan.json
pt-reverse/bin/pt730-render svg pt-reverse/examples/simple-lan.json --output simple-lan.svg
pt-reverse/bin/pt730-render drawio pt-reverse/examples/simple-lan.json --output simple-lan.drawio
pt-reverse/bin/pt730-render html pt-reverse/examples/simple-lan.json --output simple-lan.html
pt-reverse/bin/pt730-render markdown pt-reverse/examples/simple-lan.json
pt-reverse/bin/pt730-render markdown pt-reverse/course-design/college-network-topology-pt73-safe.json --output pt-reverse/course-design/college-network-topology-pt73-safe.generated.md
pt-reverse/bin/pt730-render summary pt-reverse/course-design/college-network-topology-pt73-safe.json --output pt-reverse/course-design/college-network-topology-pt73-safe.summary.json
pt-reverse/bin/pt730-render course-audit pt-reverse/course-design/college-network-topology-pt73-safe.json --output pt-reverse/course-design/college-network-topology-pt73-safe.audit.json
```

`pt730-eval` and `pt730-topo` tag every request with a unique request id.  The
local bridge now stores tagged results separately, so a slow or timed-out
command no longer poisons the next command's result.  Parallel terminal callers
are also safe for read-only checks; topology mutation commands should still be
kept sequential because Packet Tracer's workspace itself is not transactional.

The topology JSON format is intentionally small:

```json
{
  "devices": [
    {"name": "R1", "category": "router", "model": "2911", "x": 220, "y": 180},
    {"name": "SW1", "category": "switch", "model": "2960-24TT", "x": 440, "y": 180},
    {"name": "PC1", "category": "pc", "model": "PC-PT", "x": 660, "y": 180}
  ],
  "modules": [
    {"device": "R1", "slot": "0/0", "model": "HWIC-2T"}
  ],
  "links": [
    {"a": "R1", "pa": "GigabitEthernet0/0", "b": "SW1", "pb": "FastEthernet0/1", "cable": "straight"},
    {"a": "SW1", "pa": "FastEthernet0/2", "b": "PC1", "pb": "FastEthernet0", "cable": "straight"}
  ],
  "pc_configs": [
    {"name": "PC1", "port": "FastEthernet0", "ip": "192.168.1.10", "mask": "255.255.255.0", "gateway": "192.168.1.1"},
    {"name": "PC2", "dhcp": true}
  ],
  "server_configs": [
    {
      "name": "SRV1",
      "http": true,
      "tftp": true,
      "dns": {"enabled": true, "records": [{"name": "www.college.local", "ip": "172.16.1.10"}]},
      "email": {"enabled": true, "domain": "college.local", "accounts": [{"username": "student", "password": "packet"}]},
      "ntp": {"enabled": true, "authentication": false},
      "syslog": {"enabled": true, "port": 514},
      "dhcp": {
        "enabled": true,
        "network": "192.168.1.0",
        "mask": "255.255.255.0",
        "start": "192.168.1.100",
        "end": "192.168.1.199",
        "gateway": "192.168.1.1",
        "dns": "172.16.1.10"
      }
    }
  ],
  "ios_configs": [
    {"device": "R1", "init_dialog": true, "commands": ["enable", "show ip interface brief"]}
  ]
}
```

Run the live regression check for the server/DHCP/DNS/FTP example:

```bash
pt-reverse/bin/pt730-smoke
pt-reverse/bin/pt730-smoke --new
pt-reverse/bin/pt730-smoke --dhcp
pt-reverse/bin/pt730-smoke --no-apply
```

The smoke test uses a static PC address by default.  `--dhcp` is intentionally
opt-in because live DHCP client behavior in PT 7.3.0 is unstable through Script
Module automation on this Wine setup.

`pt730-safety plan` and `pt730-topo apply` also perform offline structural
checks before PT is touched: duplicate device names, unknown link endpoints, and
configs targeting missing devices fail fast.  For live-verified models, unknown
port names also fail offline; verified module ports such as `HWIC-2T`
`Serial0/0/0` and `Serial0/0/1` are included in that check.
Static PC IPv4 settings and Server-PT DHCP pools are also checked for invalid
addresses and out-of-subnet gateways/pool ranges.
IOS config blocks are also scanned offline for obvious physical interface typos,
configured interfaces that omit `no shutdown`, and serial links where neither
endpoint config includes a `clock rate`.
Use `pt730-topo apply --dry-run <plan.json>` to run those checks and print a
plan summary without contacting Packet Tracer.
Use `pt730-ip-plan campus <spec.json> --output <planned.json>` to turn address
pools and department host counts into VLSM VLAN segments that can be copied into
`pt730-compose`.
Use `pt730-compose campus <spec.json> --segments-from-ip-plan <planned.json>
--output <plan.json>` to expand a compact agent-friendly campus spec into
devices, safe ports, links, static host IPs, server services, and default layout
coordinates before touching Packet Tracer.
Use `pt730-template lan-star ...` and `pt730-template router-ring ...` when an
agent needs a common lab topology without first writing a topology JSON file.
Use `pt730-pipeline campus --ip-plan <ip-plan.json> --compose-spec
<campus-spec.json> --output-dir <out-dir> --routing rip` to run the offline
agent workflow in one command and write a manifest, safety report, rendered
tables, SVG topology diagram, diagrams.net/draw.io file, HTML review page,
topology JSON files, and per-device configs.
Set `core.interconnect_pool` in the compose spec to assign `/30` L3 subnets to
core switch links for later config planning.
Use `pt730-config-plan campus <plan.json> --output <configured-plan.json>` to
derive switch VLAN/access/trunk IOS configs from the topology link metadata.
Add `--l3 --routing rip` to derive SVI gateways, routed switch interlinks, and
RIPv2 from host gateway/mask values plus CIDR metadata on core links.  Use
`--l3 --routing static` to emit static routes between the derived SVI networks
instead of RIP.
Use `pt730-config-plan export-configs <configured-plan.json> --output-dir
<configs-dir>` to write the generated `ios_configs` into per-device `.cfg`
files for reports or manual paste-in.
Add `--source "pt730-config-plan campus"` to export only generated records, and
put `--compact` before the subcommand for compact JSON output.
Use `pt730-layout <plan.json> --output <layout.json>` to assign deterministic
coordinates before safety checks, rendering, or live apply.  Supported styles
are `auto`, `hierarchical`, `campus`, `lan`, `ring`, and `grid`; use
`--preserve-existing` when a human has already placed some devices.
Use `pt730-render markdown <plan.json>` for report-ready offline tables.  It
includes link VLAN/notes, configured host IPs, inferred address groups, server
service details, and IOS config counts.  Use `pt730-render summary <plan.json>`
for a compact JSON summary that agents can consume before any live operation.
Use `pt730-render svg <plan.json> --output <diagram.svg>` for an offline
topology diagram that respects existing `x`/`y` coordinates and falls back to a
deterministic grid when coordinates are missing.
Use `pt730-render drawio <plan.json> --output <diagram.drawio>` for an
importable diagrams.net/draw.io topology file that keeps device/link labels
editable.
For cleaner large diagrams, add `--theme light|dark|paper`,
`--no-link-labels`, or `--no-model-labels` to SVG/draw.io/HTML renders; Mermaid
supports `--no-link-labels`.
Use `pt730-render html <plan.json> --output <review.html>` for a self-contained
browser review page with the SVG diagram and Markdown report text embedded.
For this course assignment, `pt730-render course-audit <plan.json>` checks the
required VLAN links, the server address space `172.16.1.0/26`, the PC address
space `192.168.0.0/21`, and representative host coverage.

Known Packet Tracer 7.3.0 compatibility details:

- Raw `lw.addDevice(type, model, x, y)` works.
- Raw `lw.createLink(deviceA, portA, deviceB, portB, linkType)` works only when
  `linkType` is a Packet Tracer connection code string such as `"8100"`;
  upstream-style names such as `"straight"` are not accepted by 7.3.0.
- The CLI maps friendly cable names to PT codes before calling `createLink`.
- Useful cable codes: `straight=8100`, `cross=8101`, `roll=8102`,
  `fiber=8103`, `serial=8106`, `auto=8107`, `console=8108`.
- PC/server-style Ethernet ports can be configured with
  `setIpSubnetMask(ip, mask)`, `setDefaultGateway(gateway)`, and
  `setDnsServerIp(dns)`; `pt730-topo` supports this via `pc_configs`.
  `pc_configs` can also set `dhcp: true` or `dhcp: false` through
  `device.setDhcpFlag(...)`.
- Router modules can be installed with a top-level `modules` array before links
  are created.  Verified example: `HWIC-2T` in slot `"0/0"` on `2911`, producing
  `Serial0/0/0` and `Serial0/0/1`; serial links use cable code `8106`.
- Router IOS CLI works through `device.getCommandLine().enterCommand(command)`.
  The `pt730-ios` wrapper can send `--cmd` values or a config text file.  Fresh
  routers that are still at the initial configuration dialog should be called
  once with `--init-dialog`, or the config file should start by answering the
  prompt manually.
- `pt730-topo` can also run top-level `ios_configs` after devices/modules/links
  are created.  This makes single-command topology build + IOS bootstrap
  possible for small labs.
- `pt730-topo` also accepts top-level `server_configs` for `Server-PT` HTTP,
  DNS A records, FTP users, and default DHCP pool settings.  The standalone
  `pt730-server inspect` command is useful for verification after applying.

## Catalog helper

`pt730-catalog` is an offline lookup helper for agents and shell scripts.  It
uses the bundled upstream MCP-Packet-Tracer catalog for model/module/port data,
then overlays local PT 7.3.0 safety notes from this Wine environment:

```bash
pt-reverse/bin/pt730-catalog devices --status safe --table
pt-reverse/bin/pt730-catalog devices --status risky --table
pt-reverse/bin/pt730-catalog device 2911
pt-reverse/bin/pt730-catalog ports 2960 --table
pt-reverse/bin/pt730-catalog modules --model 2911 --status verified
pt-reverse/bin/pt730-catalog cables --table
pt-reverse/bin/pt730-catalog infer-cable router switch
```

JSON is the default output for machine use.  Use `--table` for quick human
inspection.  Treat `pt730_status=safe` and `pt730_status=verified` as the
unattended automation set.  `unverified` means "present in the upstream catalog,
not yet live-tested on this exact PT 7.3.0 build"; `risky` means the model is
known or likely to destabilize this PT 7.3.0 session.

## Model validation registry

`pt730-models` tracks common Packet Tracer models with PT 7.3.0-specific safety
status.  It is deliberately conservative: only locally exercised models are
`safe`; common but untested models are `unverified`; crash-prone models are
`risky`; physical/power objects are `blocked`.

```bash
pt-reverse/bin/pt730-models manifest
pt-reverse/bin/pt730-models queue
pt-reverse/bin/pt730-models probe-plan 1841
pt-reverse/bin/pt730-models validate 1841 --dry-run
pt-reverse/bin/pt730-models validate 1841 --live
pt-reverse/bin/pt730-models validate 1841 --live --record-failure-status risky
pt-reverse/bin/pt730-models validate-batch --dry-run --limit 2
pt-reverse/bin/pt730-models validate-batch --live --limit 2 --record-failures risky
pt-reverse/bin/pt730-models record 1841 --status risky --reason 'Packet Tracer crashed' --evidence './bin/1.dmp'
pt-reverse/bin/pt730-models record 1841 --status safe --reason 'create/query/save/reopen passed' --save-reopen
pt-reverse/bin/pt730-models probe-plan 3560-24PS --allow-risky
```

`queue` prints the unverified common-device validation backlog with exact
`--dry-run` and `--live` commands.  `probe-plan` produces a one-device topology
plan for manual, saved-workspace validation.  Promote a model to `safe` only
after create/query/save/reopen works on this exact PT 7.3.0 setup.
`validate --dry-run` prints the guarded live-check steps without contacting PT.
`validate --live` actually creates just the candidate model and runs
`pt730-topo query --summary`; use it one model at a time after saving the
current workspace.  Add `--record-failure-status risky` or `blocked` to
automatically record a failed live validation.  `validate-batch --dry-run`
prints the ordered one-at-a-time validation sequence from the queue;
`validate-batch --live` runs it in order and stops on the first failure unless
`--keep-going` is set; add `--record-failures risky` or `blocked` to
automatically persist each failed model.  `record` writes local validation evidence to
`pt-reverse/pt730/model_validations.json`; the overlay immediately affects
`manifest`, `queue`, `probe-plan`, `pt730-safety`, and `pt730-topo apply`.
Promoting to `safe` requires `--save-reopen`.

## IOS template renderer

`pt730-ios-template` turns higher-level JSON into IOS command sequences.  The
first supported template surface covers VLANs, access/trunk interfaces, routed
interfaces, interface ACL binding with `acl_in`/`acl_out`, RIPv2, static
routes, standard/extended ACL lines, and NAT overload.

```bash
pt-reverse/bin/pt730-ios-template schema
pt-reverse/bin/pt730-ios-template render pt-reverse/examples/ios-template-campus-router.json
pt-reverse/bin/pt730-ios-template render pt-reverse/examples/ios-template-campus-router.json --topology-json
```

Use `--topology-json` when you want to merge the generated commands into a
`pt730-topo` plan under `ios_configs`.  A template file may contain either one
device object or a top-level `devices` array for multiple IOS devices.  Use
`schema` for a machine-readable list of supported fields and a minimal example
that agents can copy before rendering commands.

## Reverse query summaries

`pt730-topo query` now asks Packet Tracer for devices, links, ports, IP fields,
IOS prompts, terminal output tails, and visible server-service states.  Add
`--summary` for a compact agent/report-friendly view, including parsed IOS
configuration hints for interfaces, VLANs, RIP networks, static routes, ACL
numbers, interface ACL applications, and NAT.  You can also summarize a saved
query result offline:

```bash
pt-reverse/bin/pt730-topo query --summary
pt-reverse/bin/pt730-topo summarize-query pt-reverse/examples/simple-lan-live-query.json
pt-reverse/bin/pt730-topo export --raw-out pt-reverse/course-design/current-query.json --summary-out pt-reverse/course-design/current-summary.json
pt-reverse/bin/pt730-topo export --raw-out pt-reverse/course-design/current-query.json --summary-out pt-reverse/course-design/current-summary.json --markdown-out pt-reverse/course-design/current-summary.md
```

## Application-level CLI helpers

`pt730-app` wraps safe `ipc.appWindow()` operations:

```bash
pt-reverse/bin/pt730-app count
pt-reverse/bin/pt730-app save
pt-reverse/bin/pt730-app save-as out/demo.pkt
pt-reverse/bin/pt730-app open out/demo.pkt
pt-reverse/bin/pt730-app new
pt-reverse/bin/pt730-app screenshot out/demo.png
```

For path-sensitive operations, `save-as` and `open` default to an ASCII
temporary filename inside `Cisco Packet Tracer 7.3.0/bin`, then copy on the
Linux side.  `open` mirrors the same idea in reverse: it copies the requested
file into Packet Tracer's default `C:/users/.../Cisco Packet Tracer 7.3.0/saves`
directory with an ASCII temporary filename, then calls `fileOpen()` with that
absolute Windows path.  PT 7.3.0 returns `"0"` for a successful path-based open.
Use `--direct` only when you want Packet Tracer/Wine to touch the source/target
path itself.

## IOS CLI helper

`pt730-ios` sends terminal commands into an IOS device:

```bash
pt-reverse/bin/pt730-ios R_DEMO --init-dialog
pt-reverse/bin/pt730-ios R_DEMO --cmd 'show ip interface brief'
pt-reverse/bin/pt730-ios R_DEMO --file pt-reverse/examples/router-demo-ios.cfg --output tail
pt-reverse/bin/pt730-ping R_AUTO1 10.10.10.2
```

The wrapper uses Packet Tracer's script-accessible command line object.  It is
appropriate for routers and IOS-like switches.  For PC/server IP settings, use
`pc_configs` in `pt730-topo` instead of IOS commands.

`pt730-ping` is a small IOS ping wrapper: it sends `ping <target>`, waits for
the asynchronous IOS output, parses `Success rate is N percent`, and exits
non-zero if the rate is below `--expect`.

## Generic terminal helper

`pt730-term` sends commands to any device with a script-accessible command line,
including routers, switches, and PC command prompt windows.  It records the
terminal buffer length before sending commands, then polls only the newly
produced output, so old ping output does not satisfy a new `--expect` pattern:

```bash
pt-reverse/bin/pt730-term PC_DHCP --cmd 'ping 192.168.200.10' \
  --wait 8 --expect 'Lost = 0 \\(0% loss\\)'
pt-reverse/bin/pt730-term PC_DHCP --cmd 'ping dhcpdemo.local' \
  --wait 8 --expect 'Lost = 0 \\(0% loss\\)'
```

Keep terminal commands to the same device sequential.  Packet Tracer exposes one
command buffer per device; concurrent `pt730-term` calls can interleave, and a
DHCP renew running in parallel can make a DNS ping fail before the lease is
ready.

## FTP client helper

`pt730-ftp` drives the PC command prompt's built-in FTP client: it connects,
waits for `Username:`, submits credentials, waits for the `ftp>` prompt, runs
optional FTP commands, and exits back to `C:\>` unless `--no-quit` is passed.

```bash
pt-reverse/bin/pt730-ftp PC_DHCP 192.168.200.10 \
  --username lab --password packet \
  --cmd dir --expect 'asa842-k8.bin'
```

This is intended as a service validation wrapper for `Server-PT` FTP labs.  It
shares the same caveat as `pt730-term`: keep terminal automation for a single
device sequential.

## Simulation/PDU helper

`pt730-sim` exposes the subset of Simulation/PDU controls that PT 7.3.0 makes
callable through Script IPC:

```bash
pt-reverse/bin/pt730-sim status
pt-reverse/bin/pt730-sim event-list --on
pt-reverse/bin/pt730-sim reset
pt-reverse/bin/pt730-sim fast-forward --steps 3
pt-reverse/bin/pt730-sim simple-pdu PC_DHCP SRV_DHCP
```

Current limitation: `UserCreatedPDU.addSimplePdu(sourceDevice, targetDevice)` is
callable and returns a result code, but PT 7.3.0 did not expose a script-readable
PDU event list/status API in the tested objects.  For automated pass/fail
connectivity checks, prefer `pt730-term ... ping ... --expect ...` or
`pt730-ping` on IOS devices.

## PC/host IP helper

`pt730-pc` wraps PC/server/laptop-style Ethernet port configuration and DHCP
lease checks:

```bash
pt-reverse/bin/pt730-pc inspect PC_DHCP
pt-reverse/bin/pt730-pc static PC1 --ip 192.168.1.10 --mask 255.255.255.0 --gateway 192.168.1.1
pt-reverse/bin/pt730-pc dhcp PC_DHCP --renew --wait 10 --expect-network 192.168.200.0/24
```

DHCP lease acquisition is asynchronous in PT 7.3.0.  `--wait` polls until the
port has a non-zero address, and `--expect-network` makes the command fail if
the lease is outside the intended network.

Do not call the internal `DhcpClientProcess.dhcpRun()` method from ad-hoc
`pt730-eval` probes.  In this environment it can block the Script Module command
loop and crash Packet Tracer.  The wrapper only uses `resetDhcpConfOn(...)` plus
the device DHCP flag.  `pt730-eval` refuses `dhcpRun(` by default; overriding
that requires `--allow-risky`.

## Server service helper

`pt730-server` configures the script-accessible services on `Server-PT`.  The
tested surface in PT 7.3.0 is HTTP enable/disable, DNS enable/disable plus A
records, FTP enable/disable plus user add/remove, Email SMTP/POP3 enable plus
user add/remove, TFTP enable/disable, NTP basic settings, Syslog enable/port,
and the first DHCP pool attached to `FastEthernet0`:

```bash
pt-reverse/bin/pt730-server inspect SRV_API
pt-reverse/bin/pt730-server http SRV_API --enable
pt-reverse/bin/pt730-server dns-add SRV_API www.college.local 192.168.100.10
pt-reverse/bin/pt730-server ftp-add SRV_API lab packet --permissions RWDNL
pt-reverse/bin/pt730-server email-add SRV_API student packet --domain college.local
pt-reverse/bin/pt730-server tftp SRV_API --enable
pt-reverse/bin/pt730-server ntp-config SRV_API --enable --auth off --key-id 0 --md5 ''
pt-reverse/bin/pt730-server syslog-config SRV_API --enable --port 514
pt-reverse/bin/pt730-server dhcp-config SRV_API \
  --network 192.168.100.0 --mask 255.255.255.0 \
  --start 192.168.100.100 --end 192.168.100.199 \
  --gateway 192.168.100.1 --dns 192.168.100.10 \
  --max-users 100 --enable
```

The implementation uses `Server-PT.getProcess("DnsServerProcess")`,
`getProcess("HttpServerProcess")`, and
`getProcess("DhcpServerMainProcess").getDhcpServerProcessByPortName(...)`.
This is more direct than editing the GUI tabs, but it is still PT 7.3.0
specific; inspect the result after configuration.

FTP users are managed through
`getProcess("FtpServerProcess").getFtpUserAccountManager()`.  The default
full-permission string is `RWDNL`, matching Packet Tracer's built-in
`cisco/cisco` account.

Email users are managed through `EmailServerProcess.addUser(username,
password)` / `deleteUser(username)`, while SMTP and POP3 are toggled through
their separate `SmtpServerProcess` and `Pop3ServerProcess` objects.

Current limitation: the HTTP service itself can be enabled from the terminal,
and the default server web files are present, but live editing of HTTP page file
contents is not yet exposed through the tested Script IPC surface.  The relevant
strings (`addHttpPage`, `addTextFile`, `FileManager`) exist in the binary, but
they did not appear as callable methods on `Server-PT`, `HttpServerProcess`,
`FileManager`, or `ipc.systemFileManager()` in this PT 7.3.0 build.
