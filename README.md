# Packet Tracer 7.3.0 Automation Toolkit

Local tooling for controlling and auditing Cisco Packet Tracer 7.3.0 through a
Script Module bridge.  The repository focuses on reproducible offline checks,
offline IP/VLAN planning, high-level topology composition, deterministic
topology auto-layout, safe topology-plan rendering, and small guarded live
operations for the fixed 7.3.0 version used in the coursework.

This source release does **not** include Cisco Packet Tracer binaries, DLLs,
crash dumps, or extracted Cisco application documentation.  Install Packet
Tracer separately and keep the application files outside Git.

## Contents

- `pt-reverse/bin/`: command wrappers for launch, bridge, topology, IP planning,
  compose, layout, render, safety, app, IOS, PC, server, FTP, and terminal
  helpers.
- `pt-reverse/pt730/`: Python implementations for offline validation, rendering,
  catalog lookup, and bridge helpers.
- `pt-reverse/examples/`: topology JSON examples and locally generated Packet
  Tracer lab files.
- `pt-reverse/course-design/`: college-network design plan, generated audit
  artifacts, and switch configuration snippets.
- `pt-reverse/upstream/MCP-Packet-Tracer`: upstream catalog submodule used by
  `pt730-catalog`.

## Setup

```bash
git submodule update --init --recursive
pt-reverse/bin/pt730-selftest
```

Use the offline tools first:

```bash
pt-reverse/bin/pt730-ip-plan campus pt-reverse/examples/ip-plan-campus.json --output ip-plan-campus.json
pt-reverse/bin/pt730-compose campus pt-reverse/examples/compose-campus.json --segments-from-ip-plan ip-plan-campus.json --output compose-campus.layout.json
pt-reverse/bin/pt730-safety plan pt-reverse/course-design/college-network-topology-pt73-safe.json
pt-reverse/bin/pt730-layout pt-reverse/course-design/college-network-topology-pt73-safe.json --style campus --preserve-existing --output college-network-topology-pt73-safe.layout.json
pt-reverse/bin/pt730-render markdown pt-reverse/course-design/college-network-topology-pt73-safe.json
pt-reverse/bin/pt730-render course-audit pt-reverse/course-design/college-network-topology-pt73-safe.json
```

Read `pt-reverse/SAFETY.md` before running live Packet Tracer operations.

For a detailed Chinese workflow manual, read
[`pt-reverse/使用手册.md`](pt-reverse/使用手册.md).

## Legal Note

Cisco Packet Tracer is Cisco software.  This repository contains helper scripts,
coursework topology plans, and generated lab artifacts only; it is not a
redistribution of Packet Tracer itself.
