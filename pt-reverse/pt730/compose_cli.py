#!/usr/bin/env python3
"""Compose high-level topology specs into Packet Tracer topology JSON plans."""

from __future__ import annotations

import argparse
import copy
import ipaddress
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

from layout_cli import LayoutOptions, STYLES, layout_plan


SAFE_SWITCH_MODEL = "2960-24TT"
SAFE_PC_MODEL = "PC-PT"
SAFE_SERVER_MODEL = "Server-PT"
DEFAULT_HOSTS_PER_ACCESS_SWITCH = 24


class PortAllocator:
    def __init__(self) -> None:
        self.used: dict[str, set[str]] = {}

    def use(self, device: str, port: str) -> str:
        ports = self.used.setdefault(device, set())
        if port in ports:
            raise ValueError(f"{device}:{port}: duplicate generated port")
        ports.add(port)
        return port

    def next_fastethernet(self, device: str) -> str:
        for index in range(1, 25):
            port = f"FastEthernet0/{index}"
            if port not in self.used.setdefault(device, set()):
                return self.use(device, port)
        raise ValueError(f"{device}: no free FastEthernet0/1-24 ports")

    def next_gigabit(self, device: str) -> str:
        for index in range(1, 3):
            port = f"GigabitEthernet0/{index}"
            if port not in self.used.setdefault(device, set()):
                return self.use(device, port)
        raise ValueError(f"{device}: no free GigabitEthernet0/1-2 ports")


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("compose spec must be a JSON object")
    return data


def _segments_from_ip_plan(path: Path) -> list[dict[str, Any]]:
    data = _load_json(path)
    compose = data.get("compose")
    if not isinstance(compose, dict):
        raise ValueError("ip plan output must contain compose object")
    segments = compose.get("segments")
    if not isinstance(segments, list):
        raise ValueError("ip plan output must contain compose.segments array")
    return copy.deepcopy(segments)


def _slug(value: Any) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "-", str(value).strip().upper()).strip("-")
    return text or "SEGMENT"


def _int(value: Any, default: int, *, label: str, minimum: int = 0) -> int:
    if value in (None, ""):
        result = default
    else:
        try:
            result = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{label}: must be an integer") from exc
    if result < minimum:
        raise ValueError(f"{label}: must be >= {minimum}")
    return result


def _mask_for(network: ipaddress.IPv4Network) -> str:
    return str(network.netmask)


def _gateway_for(network: ipaddress.IPv4Network, raw_gateway: Any, where: str) -> ipaddress.IPv4Address:
    if raw_gateway in (None, ""):
        if network.num_addresses <= 2:
            hosts = list(network.hosts())
            if not hosts:
                raise ValueError(f"{where}: subnet has no usable gateway address")
            return hosts[-1]
        return ipaddress.ip_address(int(network.broadcast_address) - 1)
    try:
        gateway = ipaddress.ip_address(str(raw_gateway))
    except ValueError as exc:
        raise ValueError(f"{where}: gateway is not a valid IPv4 address") from exc
    if gateway not in network:
        raise ValueError(f"{where}: gateway outside subnet {network}")
    return gateway


def _host_addresses(network: ipaddress.IPv4Network, gateway: ipaddress.IPv4Address, count: int, where: str) -> list[ipaddress.IPv4Address]:
    addresses: list[ipaddress.IPv4Address] = []
    for address in network.hosts():
        if address == gateway:
            continue
        addresses.append(address)
        if len(addresses) >= count:
            break
    if len(addresses) < count:
        raise ValueError(f"{where}: not enough usable host addresses in {network}")
    return addresses


def _device(name: str, category: str, model: str, **extra: Any) -> dict[str, Any]:
    device = {"name": name, "category": category, "model": model}
    device.update({key: value for key, value in extra.items() if value not in (None, "")})
    return device


def _link(a: str, pa: str, b: str, pb: str, cable: str, *, vlan: Any = None, note: str | None = None, l3_subnet: Any = None) -> dict[str, Any]:
    link = {"a": a, "pa": pa, "b": b, "pb": pb, "cable": cable}
    if vlan not in (None, ""):
        link["vlan"] = int(vlan) if str(vlan).isdigit() else str(vlan)
    if l3_subnet not in (None, ""):
        link["l3_subnet"] = str(l3_subnet)
    if note:
        link["note"] = note
    return link


def _server_config(server: dict[str, Any]) -> dict[str, Any] | None:
    services = server.get("services")
    if not isinstance(services, dict) or not services:
        return None
    config = {"name": str(server["name"])}
    config.update(services)
    return config


def _core_names(core_spec: dict[str, Any]) -> list[str]:
    count = _int(core_spec.get("count"), 1, label="core.count", minimum=1)
    prefix = str(core_spec.get("prefix", "MLS"))
    names = core_spec.get("names")
    if names is not None:
        if not isinstance(names, list) or not names:
            raise ValueError("core.names must be a non-empty array")
        rendered = [str(name) for name in names]
        if len(rendered) != count:
            raise ValueError("core.names length must match core.count")
        return rendered
    return [f"{prefix}{index}" for index in range(1, count + 1)]


def _core_interconnect_networks(core_spec: dict[str, Any], link_count: int) -> list[ipaddress.IPv4Network]:
    raw_pool = core_spec.get("interconnect_pool", core_spec.get("l3_pool"))
    if raw_pool in (None, "") or link_count <= 0:
        return []
    try:
        pool = ipaddress.ip_network(str(raw_pool), strict=False)
    except ValueError as exc:
        raise ValueError("core.interconnect_pool: invalid IPv4 network") from exc
    prefix = _int(core_spec.get("interconnect_prefix", core_spec.get("l3_prefix")), 30, label="core.interconnect_prefix", minimum=0)
    if prefix > 32:
        raise ValueError("core.interconnect_prefix: must be <= 32")
    if prefix < pool.prefixlen:
        raise ValueError("core.interconnect_prefix: must be greater than or equal to pool prefix length")
    networks = list(pool.subnets(new_prefix=prefix))
    if len(networks) < link_count:
        raise ValueError(f"core.interconnect_pool: not enough /{prefix} subnets for {link_count} core link(s)")
    return networks[:link_count]


def _connect_core_ring(core: list[str], ports: PortAllocator, links: list[dict[str, Any]], networks: list[ipaddress.IPv4Network]) -> None:
    if len(core) <= 1:
        return
    if len(core) == 2:
        l3_subnet = networks[0] if networks else None
        note = f"core interconnect {l3_subnet}" if l3_subnet else "core interconnect"
        links.append(_link(core[0], ports.use(core[0], "GigabitEthernet0/1"), core[1], ports.use(core[1], "GigabitEthernet0/1"), "cross", note=note, l3_subnet=l3_subnet))
        return
    for index, a in enumerate(core):
        b = core[(index + 1) % len(core)]
        l3_subnet = networks[index] if index < len(networks) else None
        note = f"core ring {l3_subnet}" if l3_subnet else "core ring"
        links.append(_link(a, ports.use(a, "GigabitEthernet0/1"), b, ports.use(b, "GigabitEthernet0/2"), "cross", note=note, l3_subnet=l3_subnet))


def _pick_core(segment: dict[str, Any], core: list[str], index: int) -> str:
    requested = segment.get("core", segment.get("uplink_core"))
    if requested:
        value = str(requested)
        if value not in core:
            raise ValueError(f"segments[{index}].core: unknown core device {value}")
        return value
    return core[index % len(core)]


def compose_campus(spec: dict[str, Any], *, do_layout: bool, layout_style: str) -> dict[str, Any]:
    core_spec = spec.get("core", {})
    if not isinstance(core_spec, dict):
        raise ValueError("core must be an object")
    server_defaults = spec.get("server_defaults", {})
    if server_defaults is None:
        server_defaults = {}
    if not isinstance(server_defaults, dict):
        raise ValueError("server_defaults must be an object")
    servers = spec.get("servers", [])
    segments = spec.get("segments", [])
    if not isinstance(servers, list):
        raise ValueError("servers must be an array")
    if not isinstance(segments, list):
        raise ValueError("segments must be an array")

    core = _core_names(core_spec)
    core_model = str(core_spec.get("model", SAFE_SWITCH_MODEL))
    access_model = str(spec.get("access_model", SAFE_SWITCH_MODEL))
    pc_model = str(spec.get("pc_model", SAFE_PC_MODEL))
    server_model = str(spec.get("server_model", SAFE_SERVER_MODEL))
    ports = PortAllocator()

    plan: dict[str, Any] = {
        "devices": [],
        "links": [],
        "pc_configs": [],
        "server_configs": [],
        "ios_configs": [],
        "metadata": {
            "source": "pt730-compose campus",
            "name": str(spec.get("name", "campus")),
        },
    }

    for name in core:
        plan["devices"].append(
            _device(
                name,
                "switch",
                core_model,
                pt_note="PT 7.3 automation-safe visual substitute for core/multilayer switch.",
            )
        )
    core_link_count = 0 if len(core) <= 1 else 1 if len(core) == 2 else len(core)
    _connect_core_ring(core, ports, plan["links"], _core_interconnect_networks(core_spec, core_link_count))

    server_switch_spec = spec.get("server_switch", {})
    if server_switch_spec is None:
        server_switch_spec = {}
    if not isinstance(server_switch_spec, dict):
        raise ValueError("server_switch must be an object")
    server_switch = str(server_switch_spec.get("name", "SW-SRV"))
    server_vlan = server_switch_spec.get("vlan", 10)
    if servers:
        plan["devices"].append(_device(server_switch, "switch", access_model))
        server_core = str(server_switch_spec.get("core", server_switch_spec.get("uplink_core", core[0])))
        if server_core not in core:
            raise ValueError(f"server_switch.core: unknown core device {server_core}")
        plan["links"].append(
            _link(
                server_core,
                ports.next_fastethernet(server_core),
                server_switch,
                ports.next_gigabit(server_switch),
                "cross",
                vlan=server_vlan,
                note="server access uplink",
            )
        )

    for index, server in enumerate(servers):
        if not isinstance(server, dict):
            raise ValueError(f"servers[{index}]: must be an object")
        name = str(server.get("name", f"SRV-{index + 1}"))
        plan["devices"].append(_device(name, "server", server_model))
        if servers:
            plan["links"].append(
                _link(
                    server_switch,
                    ports.next_fastethernet(server_switch),
                    name,
                    "FastEthernet0",
                    "straight",
                    vlan=server_vlan,
                    note="server host",
                )
            )
        ip = server.get("ip", server.get("address"))
        if ip:
            plan["pc_configs"].append(
                {
                    "name": name,
                    "port": "FastEthernet0",
                    "ip": str(ip),
                    "mask": str(server.get("mask", server_defaults.get("mask", "255.255.255.0"))),
                    "gateway": str(server.get("gateway", server_defaults.get("gateway", ""))),
                    "dns": str(server.get("dns", server_defaults.get("dns", ""))),
                }
            )
        config = _server_config({"name": name, **server})
        if config is not None:
            plan["server_configs"].append(config)

    for segment_index, segment in enumerate(segments):
        if not isinstance(segment, dict):
            raise ValueError(f"segments[{segment_index}]: must be an object")
        slug = _slug(segment.get("name", f"SEG{segment_index + 1}"))
        vlan = segment.get("vlan", segment.get("vlan_id"))
        if vlan in (None, ""):
            raise ValueError(f"segments[{segment_index}].vlan: missing")
        subnet_raw = segment.get("subnet", segment.get("network"))
        if subnet_raw in (None, ""):
            raise ValueError(f"segments[{segment_index}].subnet: missing")
        try:
            network = ipaddress.ip_network(str(subnet_raw), strict=False)
        except ValueError as exc:
            raise ValueError(f"segments[{segment_index}].subnet: invalid IPv4 subnet") from exc
        gateway = _gateway_for(network, segment.get("gateway", segment.get("default_gateway")), f"segments[{segment_index}]")
        host_count = _int(
            segment.get("representative_hosts", segment.get("hosts")),
            2,
            label=f"segments[{segment_index}].representative_hosts",
            minimum=0,
        )
        switch_count = _int(
            segment.get("access_switches", segment.get("switch_count")),
            max(1, math.ceil(max(host_count, 1) / DEFAULT_HOSTS_PER_ACCESS_SWITCH)),
            label=f"segments[{segment_index}].access_switches",
            minimum=1,
        )
        addresses = _host_addresses(network, gateway, host_count, f"segments[{segment_index}]")
        switch_base = str(segment.get("switch", f"SW-{slug}"))
        host_prefix = str(segment.get("host_prefix", f"PC-{slug}"))
        access_switches = [switch_base if switch_count == 1 else f"{switch_base}-{index}" for index in range(1, switch_count + 1)]
        for switch_offset, switch_name in enumerate(access_switches):
            plan["devices"].append(_device(switch_name, "switch", access_model))
            core_name = _pick_core(segment, core, segment_index + switch_offset)
            plan["links"].append(
                _link(
                    core_name,
                    ports.next_fastethernet(core_name),
                    switch_name,
                    ports.next_gigabit(switch_name),
                    "cross",
                    vlan=vlan,
                    note=f"{slug} access uplink",
                )
            )
        for host_index, address in enumerate(addresses, start=1):
            switch_name = access_switches[(host_index - 1) % len(access_switches)]
            host_name = f"{host_prefix}-{host_index}"
            plan["devices"].append(_device(host_name, "pc", pc_model))
            plan["links"].append(
                _link(
                    switch_name,
                    ports.next_fastethernet(switch_name),
                    host_name,
                    "FastEthernet0",
                    "straight",
                    vlan=vlan,
                    note=f"{slug} representative host",
                )
            )
            plan["pc_configs"].append(
                {
                    "name": host_name,
                    "port": "FastEthernet0",
                    "ip": str(address),
                    "mask": _mask_for(network),
                    "gateway": str(gateway),
                    "dns": str(segment.get("dns", spec.get("dns", ""))),
                }
            )

    if do_layout:
        plan = layout_plan(plan, LayoutOptions(style=layout_style))
    return plan


def schema() -> dict[str, Any]:
    return {
        "commands": ["schema", "campus"],
        "fields": [
            "core.count",
            "core.prefix",
            "core.names",
            "core.interconnect_pool",
            "core.interconnect_prefix",
            "server_defaults.mask",
            "server_defaults.gateway",
            "server_defaults.dns",
            "server_switch.name",
            "server_switch.vlan",
            "servers[].name",
            "servers[].ip",
            "servers[].services",
            "segments[].name",
            "segments[].vlan",
            "segments[].subnet",
            "segments[].gateway",
            "segments[].dns",
            "segments[].representative_hosts",
            "segments[].access_switches",
            "segments[].core",
        ],
        "example": {
            "name": "agent-college",
            "core": {"count": 2, "prefix": "MLS", "interconnect_pool": "10.10.12.0/30"},
            "server_defaults": {"mask": "255.255.255.192", "gateway": "172.16.1.62", "dns": "172.16.1.11"},
            "server_switch": {"name": "SW-SRV", "vlan": 10, "core": "MLS1"},
            "servers": [
                {"name": "WEB-SRV", "ip": "172.16.1.10", "services": {"http": True}},
                {"name": "DNS-SRV", "ip": "172.16.1.11", "services": {"dns": {"enabled": True, "records": [{"name": "www.college.local", "ip": "172.16.1.10"}]}}},
            ],
            "segments": [
                {"name": "OFFICE", "vlan": 20, "subnet": "192.168.0.0/26", "gateway": "192.168.0.62", "representative_hosts": 2},
                {"name": "TEACH", "vlan": 30, "subnet": "192.168.0.64/26", "gateway": "192.168.0.126", "representative_hosts": 2},
            ],
        },
    }


def emit_json(value: dict[str, Any], output: Path | None, *, compact: bool) -> None:
    text = json.dumps(value, ensure_ascii=False, indent=None if compact else 2, separators=(",", ":") if compact else None) + "\n"
    if output is None:
        print(text, end="")
        return
    output.write_text(text, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pt730-compose", description=__doc__)
    parser.add_argument("--compact", action="store_true", help="emit compact JSON")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("schema", help="print the campus compose schema and example")

    campus_p = sub.add_parser("campus", help="compose a campus topology plan from a compact JSON spec")
    campus_p.add_argument("spec", type=Path)
    campus_p.add_argument("--output", type=Path, help="write topology JSON to a file instead of stdout")
    campus_p.add_argument("--layout-style", choices=STYLES, default="campus", help="layout style to apply after composition")
    campus_p.add_argument("--no-layout", action="store_true", help="do not assign x/y coordinates")
    campus_p.add_argument("--segments-from-ip-plan", type=Path, help="replace spec.segments with compose.segments from pt730-ip-plan output")

    args = parser.parse_args(argv)
    try:
        if args.cmd == "schema":
            emit_json(schema(), None, compact=args.compact)
            return 0
        if args.cmd == "campus":
            spec = _load_json(args.spec)
            if args.segments_from_ip_plan is not None:
                spec = copy.deepcopy(spec)
                spec["segments"] = _segments_from_ip_plan(args.segments_from_ip_plan)
            plan = compose_campus(spec, do_layout=not args.no_layout, layout_style=args.layout_style)
            emit_json(plan, args.output, compact=args.compact)
            return 0
        raise ValueError(f"unknown command: {args.cmd}")
    except Exception as exc:  # noqa: BLE001
        print(f"pt730-compose: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
