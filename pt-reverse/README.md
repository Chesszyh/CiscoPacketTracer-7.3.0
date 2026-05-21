# Packet Tracer 7.3.0 automation notes

This directory contains local interoperability work for controlling the installed
Cisco Packet Tracer 7.3.0 copy from Linux/Wine.

Read `SAFETY.md` before adding new live probes.  PT 7.3.0 can crash when some
internal process APIs are called through the Script Module bridge.

## Current runtime

Start or check Packet Tracer:

```bash
pt-reverse/bin/pt730-launch start
pt-reverse/bin/pt730-launch status
pt-reverse/bin/pt730-recover --notify
pt-reverse/bin/pt730-selftest
pt-reverse/bin/pt730-capabilities
pt-reverse/bin/pt730-render mermaid pt-reverse/examples/simple-lan.json
pt-reverse/bin/pt730-render markdown pt-reverse/examples/simple-lan.json
pt-reverse/bin/pt730-render summary pt-reverse/examples/simple-lan.json
pt-reverse/bin/pt730-render course-audit pt-reverse/course-design/college-network-topology-pt73-safe.json
```

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

Paste the bootstrap JavaScript into the PT-MCP Builder Code Editor and click Run.
After that, command-line calls can drive Packet Tracer through the Script Module:

```bash
pt-reverse/bin/pt730-eval --expr 'ipc.network().getDeviceCount()'
printf '%s\n' '"stdin:"+ipc.network().getLinkCount()' | pt-reverse/bin/pt730-eval --expr --stdin
pt-reverse/bin/pt730-app count
pt-reverse/bin/pt730-topo query
pt-reverse/bin/pt730-topo apply --dry-run pt-reverse/examples/simple-lan.json
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
pt-reverse/bin/pt730-capabilities --table
pt-reverse/bin/pt730-render mermaid pt-reverse/examples/simple-lan.json
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
Use `pt730-render markdown <plan.json>` for report-ready offline tables.  It
includes link VLAN/notes, configured host IPs, inferred address groups, server
service details, and IOS config counts.  Use `pt730-render summary <plan.json>`
for a compact JSON summary that agents can consume before any live operation.
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
