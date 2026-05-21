# Packet Tracer 7.3.0 automation safety notes

This Wine/PT 7.3.0 setup is fragile. Prefer boring, observable operations and
avoid probing internal process methods unless they are already verified here.

## Safe default operations

- `pt730-app count`
- `pt730-app save-as ...`
- `pt730-topo query`
- `pt730-topo apply` with verified models only:
  - `2911`
  - `2960-24TT`
  - `PC-PT`
  - `Server-PT`
- `pt730-pc static ...`
- `pt730-term ... ping ...`
- `pt730-ftp ... --cmd dir`
- `pt730-server inspect`
- `pt730-server` service configuration for HTTP, DNS, FTP, TFTP, Email, NTP,
  Syslog, and DHCP server pool fields

`pt730-smoke` intentionally uses static client addressing by default.

Before unattended topology creation, run the offline checker:

```bash
pt-reverse/bin/pt730-safety plan pt-reverse/examples/server-dhcp-lan.json
pt-reverse/bin/pt730-topo apply --dry-run pt-reverse/examples/server-dhcp-lan.json
pt-reverse/bin/pt730-safety js 'ipc.network().getDeviceCount()'
```

Before and after changing the automation tools, run the offline self-test:

```bash
pt-reverse/bin/pt730-selftest
```

Use `pt730-selftest --live` only when you explicitly want the final safe
bridge/count probe.

For a machine-readable agent summary of safe tools and guarded operations:

```bash
pt-reverse/bin/pt730-capabilities
pt-reverse/bin/pt730-models manifest
```

For an offline visual preview of a plan:

```bash
pt-reverse/bin/pt730-render mermaid pt-reverse/examples/simple-lan.json
pt-reverse/bin/pt730-render markdown pt-reverse/examples/simple-lan.json
pt-reverse/bin/pt730-render summary pt-reverse/examples/simple-lan.json
pt-reverse/bin/pt730-render course-audit pt-reverse/course-design/college-network-topology-pt73-safe.json
```

`pt730-render` never contacts Packet Tracer.  The Markdown renderer includes
link VLAN/notes, configured host address groups, server service details, and IOS
config counts.  Add `--output <path>` to write review artifacts before deciding
whether a live apply is worth the risk.  `course-audit` is specific to the
college-network assignment and checks required VLAN presence plus the mandated
server and PC address spaces.

`pt730-models manifest`, `queue`, `probe-plan`, and `validate --dry-run` never
contact Packet Tracer.  `queue` is the common-device validation backlog;
`validate --live` is a supervised one-model experiment: save the current
workspace first, validate one model, and record crashes/refusals as `risky` or
`blocked` instead of retrying blindly.  `pt730-models record` stores this
evidence in `pt-reverse/pt730/model_validations.json`; that overlay feeds both
the offline safety checker and the live topology safety gate.  A model can be
promoted to `safe` only with explicit save/reopen evidence.
`validate-batch --dry-run` is offline; `validate-batch --live` is intentionally
sequential and stops on the first failure unless `--keep-going` is set.  Use
`--record-failure-status risky|blocked` or `--record-failures risky|blocked`
when you want live validation failures to update the safety overlay
automatically.

`pt730-topo apply` also runs this safety gate before contacting Packet Tracer.
Known risky models fail by default.  Warnings are printed to stderr; use
`--strict-safety` to fail on warnings, or `--allow-risky` only for manual,
supervised experiments.

`pt730-smoke` also runs `pt730-safety plan` before applying its plan.
The plan checker also rejects duplicate device names and references to missing
devices in links, modules, PC configs, server configs, and IOS configs.
For live-verified models it also rejects unknown endpoint/config ports, including
module-provided ports such as `HWIC-2T` serial interfaces.
It validates IPv4 syntax for PC/static and Server-PT DHCP settings, checks PC
gateways against the configured subnet, and checks DHCP pool start/end/gateway
addresses against the pool network.  IOS config blocks are scanned for obvious
physical interface typos, configured interfaces that omit `no shutdown`, and
serial links where neither endpoint config includes a `clock rate`.

## Guarded operations

- DHCP client lease validation is allowed only when explicitly requested:
  `pt730-smoke --dhcp` or `pt730-pc dhcp ...`.
- Simulation/PDU helpers can create a simple PDU, but PT 7.3.0 does not expose
  a reliable script-readable pass/fail event list. Use ping for automated
  pass/fail checks.
- New device models must be tested one at a time after saving the current file.

## Known risky operations

- Do not call `DhcpClientProcess.dhcpRun(...)` from `pt730-eval` or custom
  probes. It can block the Script Module command loop and crash PT. `pt730-eval`
  refuses `dhcpRun(` unless `--allow-risky` is passed.
- Avoid automated placement of `3560-24PS` and `3650-24PS`; they have crashed
  or destabilized this PT 7.3.0 build.
- Do not mutate `.pkt` bytes directly. Use Packet Tracer save/open APIs and
  ASCII temporary paths.

## Recovery

If PT crashes or command results stop returning:

```bash
pt-reverse/bin/pt730-recover --notify
```

Manual equivalent:

```bash
pt-reverse/bin/pt730-bridge restart
pt-reverse/bin/pt730-launch restart
pt-reverse/bin/pt730-bridge status
pt-reverse/bin/pt730-app --timeout 8 count
```

If `bridge status` shows `connected:false`, run the PT-MCP Builder bootstrap in
Packet Tracer again.
