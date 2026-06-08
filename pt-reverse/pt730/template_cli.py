#!/usr/bin/env python3
"""Generate built-in Packet Tracer 7.3.0 topology templates."""

from __future__ import annotations

import argparse
import ipaddress
import json
import sys
from pathlib import Path
from typing import Any

from layout_cli import LayoutOptions, STYLES, layout_plan


def _mask(network: ipaddress.IPv4Network) -> str:
    return str(network.netmask)


def _host(network: ipaddress.IPv4Network, offset: int) -> ipaddress.IPv4Address:
    address = ipaddress.ip_address(int(network.network_address) + offset)
    if address not in network:
        raise ValueError(f"{network}: host offset {offset} is outside network")
    return address


def _emit(plan: dict[str, Any], output: Path | None, *, compact: bool) -> None:
    text = json.dumps(plan, ensure_ascii=False, indent=None if compact else 2, separators=(",", ":") if compact else None) + "\n"
    if output is None:
        print(text, end="")
        return
    output.write_text(text, encoding="utf-8")


def _maybe_layout(plan: dict[str, Any], *, style: str, no_layout: bool) -> dict[str, Any]:
    if no_layout:
        return plan
    return layout_plan(plan, LayoutOptions(style=style))


def schema() -> dict[str, Any]:
    return {
        "commands": ["schema", "lan-star", "router-ring"],
        "templates": {
            "lan-star": {
                "description": "One router, one access switch, static PCs, optional HTTP servers.",
                "options": ["--name", "--pcs", "--servers", "--network", "--gateway", "--dns", "--layout-style", "--no-layout"],
            },
            "router-ring": {
                "description": "Serial WAN ring of 2911 routers with HWIC-2T modules and RIPv2 configs.",
                "options": ["--name", "--routers", "--interconnect-pool", "--layout-style", "--no-layout"],
            },
        },
    }


def lan_star(*, name: str, pcs: int, servers: int, network: str, gateway: str | None, dns: str | None, layout_style: str, no_layout: bool) -> dict[str, Any]:
    if pcs < 0 or servers < 0:
        raise ValueError("pcs and servers must be >= 0")
    if pcs + servers < 1:
        raise ValueError("lan-star requires at least one PC or server")
    net = ipaddress.ip_network(network, strict=False)
    gw = ipaddress.ip_address(gateway) if gateway else _host(net, 1)
    if gw not in net:
        raise ValueError(f"gateway {gw} is outside {net}")
    if net.num_addresses < pcs + servers + 3:
        raise ValueError(f"{net}: not enough addresses for requested hosts")

    slug = name.upper()
    router = f"R-{slug}"
    switch = f"SW-{slug}"
    plan: dict[str, Any] = {
        "devices": [
            {"name": router, "category": "router", "model": "2911"},
            {"name": switch, "category": "switch", "model": "2960-24TT"},
        ],
        "links": [{"a": router, "pa": "GigabitEthernet0/0", "b": switch, "pb": "FastEthernet0/1", "cable": "straight"}],
        "pc_configs": [],
        "server_configs": [],
        "ios_configs": [
            {
                "device": router,
                "init_dialog": True,
                "commands": [
                    "enable",
                    "configure terminal",
                    f"hostname {router}",
                    "interface GigabitEthernet0/0",
                    f"ip address {gw} {_mask(net)}",
                    "no shutdown",
                    "end",
                ],
            }
        ],
        "metadata": {"source": "pt730-template lan-star", "name": name, "network": str(net)},
    }

    next_offset = 2 if gw == _host(net, 1) else 1
    for index in range(1, pcs + 1):
        host = f"PC-{slug}-{index}"
        ip_addr = _host(net, next_offset)
        while ip_addr == gw:
            next_offset += 1
            ip_addr = _host(net, next_offset)
        next_offset += 1
        plan["devices"].append({"name": host, "category": "pc", "model": "PC-PT"})
        plan["links"].append({"a": switch, "pa": f"FastEthernet0/{len(plan['links']) + 1}", "b": host, "pb": "FastEthernet0", "cable": "straight"})
        plan["pc_configs"].append({"name": host, "port": "FastEthernet0", "ip": str(ip_addr), "mask": _mask(net), "gateway": str(gw), "dns": dns or ""})

    for index in range(1, servers + 1):
        server = f"SRV-{slug}-{index}"
        ip_addr = _host(net, next_offset)
        while ip_addr == gw:
            next_offset += 1
            ip_addr = _host(net, next_offset)
        next_offset += 1
        plan["devices"].append({"name": server, "category": "server", "model": "Server-PT"})
        plan["links"].append({"a": switch, "pa": f"FastEthernet0/{len(plan['links']) + 1}", "b": server, "pb": "FastEthernet0", "cable": "straight"})
        plan["pc_configs"].append({"name": server, "port": "FastEthernet0", "ip": str(ip_addr), "mask": _mask(net), "gateway": str(gw), "dns": dns or str(ip_addr)})
        plan["server_configs"].append({"name": server, "http": True})

    return _maybe_layout(plan, style=layout_style, no_layout=no_layout)


def _rip_network(address: ipaddress.IPv4Address) -> str:
    octets = str(address).split(".")
    first = int(octets[0])
    if first < 128:
        return f"{octets[0]}.0.0.0"
    if first < 192:
        return f"{octets[0]}.{octets[1]}.0.0"
    return f"{octets[0]}.{octets[1]}.{octets[2]}.0"


def router_ring(*, name: str, routers: int, interconnect_pool: str, layout_style: str, no_layout: bool) -> dict[str, Any]:
    if routers < 2:
        raise ValueError("router-ring requires at least two routers")
    pool = ipaddress.ip_network(interconnect_pool, strict=False)
    subnets = list(pool.subnets(new_prefix=30))
    if len(subnets) < routers:
        raise ValueError(f"{pool}: not enough /30 subnets for {routers} ring links")
    slug = name.upper()
    names = [f"R-{slug}-{index}" for index in range(1, routers + 1)]
    plan: dict[str, Any] = {
        "devices": [{"name": router, "category": "router", "model": "2911"} for router in names],
        "modules": [{"device": router, "slot": "0/0", "model": "HWIC-2T"} for router in names],
        "links": [],
        "pc_configs": [],
        "ios_configs": [],
        "metadata": {"source": "pt730-template router-ring", "name": name, "interconnect_pool": str(pool)},
    }
    configs: dict[str, list[str]] = {
        router: ["enable", "configure terminal", f"hostname {router}"] for router in names
    }
    rip_networks: set[str] = set()

    for index, subnet in enumerate(subnets[:routers]):
        a = names[index]
        b = names[(index + 1) % routers]
        hosts = list(subnet.hosts())
        a_ip = hosts[0]
        b_ip = hosts[1]
        a_port = "Serial0/0/0"
        b_port = "Serial0/0/1"
        plan["links"].append({"a": a, "pa": a_port, "b": b, "pb": b_port, "cable": "serial", "note": str(subnet)})
        configs[a].extend(["interface " + a_port, f"ip address {a_ip} {_mask(subnet)}", "clock rate 64000", "no shutdown", "exit"])
        configs[b].extend(["interface " + b_port, f"ip address {b_ip} {_mask(subnet)}", "no shutdown", "exit"])
        rip_networks.add(_rip_network(a_ip))
        rip_networks.add(_rip_network(b_ip))

    for router in names:
        commands = configs[router]
        commands.extend(["router rip", "version 2", "no auto-summary"])
        for network in sorted(rip_networks, key=lambda value: tuple(int(part) for part in value.split("."))):
            commands.append(f"network {network}")
        commands.extend(["exit", "end"])
        plan["ios_configs"].append({"device": router, "init_dialog": True, "commands": commands})

    return _maybe_layout(plan, style=layout_style, no_layout=no_layout)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pt730-template", description=__doc__)
    parser.add_argument("--compact", action="store_true", help="emit compact JSON")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("schema", help="print built-in template schema")

    lan_p = sub.add_parser("lan-star", help="generate a router-switch-PC/server star LAN")
    lan_p.add_argument("--name", default="LAN")
    lan_p.add_argument("--pcs", type=int, default=2)
    lan_p.add_argument("--servers", type=int, default=0)
    lan_p.add_argument("--network", default="192.168.10.0/24")
    lan_p.add_argument("--gateway")
    lan_p.add_argument("--dns")
    lan_p.add_argument("--layout-style", choices=STYLES, default="lan")
    lan_p.add_argument("--no-layout", action="store_true")
    lan_p.add_argument("--output", type=Path)

    ring_p = sub.add_parser("router-ring", help="generate a serial router ring with RIPv2")
    ring_p.add_argument("--name", default="RING")
    ring_p.add_argument("--routers", type=int, default=4)
    ring_p.add_argument("--interconnect-pool", default="10.20.0.0/28")
    ring_p.add_argument("--layout-style", choices=STYLES, default="ring")
    ring_p.add_argument("--no-layout", action="store_true")
    ring_p.add_argument("--output", type=Path)

    args = parser.parse_args(argv)
    try:
        if args.cmd == "schema":
            _emit(schema(), None, compact=args.compact)
            return 0
        if args.cmd == "lan-star":
            _emit(
                lan_star(
                    name=args.name,
                    pcs=args.pcs,
                    servers=args.servers,
                    network=args.network,
                    gateway=args.gateway,
                    dns=args.dns,
                    layout_style=args.layout_style,
                    no_layout=args.no_layout,
                ),
                args.output,
                compact=args.compact,
            )
            return 0
        if args.cmd == "router-ring":
            _emit(
                router_ring(
                    name=args.name,
                    routers=args.routers,
                    interconnect_pool=args.interconnect_pool,
                    layout_style=args.layout_style,
                    no_layout=args.no_layout,
                ),
                args.output,
                compact=args.compact,
            )
            return 0
        raise ValueError(f"unknown command: {args.cmd}")
    except Exception as exc:  # noqa: BLE001
        print(f"pt730-template: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
