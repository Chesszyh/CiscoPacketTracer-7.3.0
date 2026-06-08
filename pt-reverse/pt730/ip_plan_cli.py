#!/usr/bin/env python3
"""Plan campus VLAN IPv4 subnets for Packet Tracer topology composition."""

from __future__ import annotations

import argparse
import ipaddress
import json
import sys
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("IP plan spec must be a JSON object")
    return data


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


def _usable_hosts(network: ipaddress.IPv4Network) -> int:
    if network.prefixlen == 32:
        return 1
    if network.prefixlen == 31:
        return 2
    return max(0, network.num_addresses - 2)


def _capacity_hosts(network: ipaddress.IPv4Network, gateway_reserved: int) -> int:
    return max(0, _usable_hosts(network) - gateway_reserved)


def _prefix_for(hosts: int, gateway_reserved: int) -> int:
    needed = max(1, hosts + gateway_reserved)
    for prefix in range(30, -1, -1):
        candidate = ipaddress.ip_network(f"0.0.0.0/{prefix}")
        if _usable_hosts(candidate) >= needed:
            return prefix
    raise ValueError(f"cannot allocate subnet for {hosts} host(s)")


def _align_address(address: int, prefix: int) -> int:
    block_size = 1 << (32 - prefix)
    return ((address + block_size - 1) // block_size) * block_size


def _next_subnet(pool: ipaddress.IPv4Network, cursor: int, prefix: int, where: str) -> ipaddress.IPv4Network:
    aligned = _align_address(cursor, prefix)
    subnet = ipaddress.ip_network((aligned, prefix))
    if not subnet.subnet_of(pool):
        raise ValueError(f"{where}: {subnet} does not fit inside address pool {pool}")
    return subnet


def _gateway(network: ipaddress.IPv4Network, mode: str) -> ipaddress.IPv4Address:
    if network.num_addresses <= 2:
        hosts = list(network.hosts())
        if not hosts:
            raise ValueError(f"{network}: subnet has no usable gateway address")
        return hosts[-1]
    if mode == "first":
        return ipaddress.ip_address(int(network.network_address) + 1)
    if mode == "last":
        return ipaddress.ip_address(int(network.broadcast_address) - 1)
    raise ValueError(f"gateway_mode: unsupported value {mode}")


def _summarize_unused(pool: ipaddress.IPv4Network, cursor: int) -> list[dict[str, Any]]:
    start = max(cursor, int(pool.network_address))
    end = int(pool.broadcast_address)
    if start > end:
        return []
    networks = ipaddress.summarize_address_range(ipaddress.ip_address(start), ipaddress.ip_address(end))
    return [
        {
            "subnet": str(network),
            "mask": str(network.netmask),
            "usable_hosts": _usable_hosts(network),
        }
        for network in networks
    ]


def plan_campus(spec: dict[str, Any]) -> dict[str, Any]:
    raw_pool = spec.get("address_pool", spec.get("pool"))
    if raw_pool in (None, ""):
        raise ValueError("address_pool is required")
    try:
        pool = ipaddress.ip_network(str(raw_pool), strict=False)
    except ValueError as exc:
        raise ValueError("address_pool: invalid IPv4 network") from exc
    groups = spec.get("groups", spec.get("segments"))
    if not isinstance(groups, list) or not groups:
        raise ValueError("groups must be a non-empty array")

    gateway_mode = str(spec.get("gateway_mode", "last")).lower()
    gateway_reserved = _int(spec.get("gateway_reserved"), 1, label="gateway_reserved", minimum=1)
    default_representative_hosts = _int(spec.get("default_representative_hosts"), 2, label="default_representative_hosts", minimum=0)
    dns = spec.get("dns", "")
    cursor = int(pool.network_address)
    segments: list[dict[str, Any]] = []

    for index, group in enumerate(groups):
        if not isinstance(group, dict):
            raise ValueError(f"groups[{index}]: must be an object")
        name = str(group.get("name", f"SEGMENT-{index + 1}"))
        hosts = _int(group.get("hosts", group.get("host_count")), 0, label=f"groups[{index}].hosts", minimum=0)
        vlan = group.get("vlan", group.get("vlan_id"))
        if vlan in (None, ""):
            raise ValueError(f"groups[{index}].vlan: missing")
        prefix = group.get("prefix", group.get("prefixlen"))
        if prefix in (None, ""):
            prefix_len = _prefix_for(hosts, gateway_reserved)
        else:
            prefix_len = _int(prefix, 0, label=f"groups[{index}].prefix", minimum=0)
            if prefix_len > 32:
                raise ValueError(f"groups[{index}].prefix: must be <= 32")
        subnet = _next_subnet(pool, cursor, prefix_len, f"groups[{index}]")
        capacity_hosts = _capacity_hosts(subnet, gateway_reserved)
        if capacity_hosts < hosts:
            raise ValueError(f"groups[{index}]: {subnet} capacity {capacity_hosts} is smaller than requested hosts {hosts}")
        gateway = _gateway(subnet, str(group.get("gateway_mode", gateway_mode)).lower())
        representative_hosts = _int(
            group.get("representative_hosts"),
            min(default_representative_hosts, capacity_hosts),
            label=f"groups[{index}].representative_hosts",
            minimum=0,
        )
        segment: dict[str, Any] = {
            "name": name,
            "vlan": int(vlan) if str(vlan).isdigit() else str(vlan),
            "requested_hosts": hosts,
            "subnet": str(subnet),
            "mask": str(subnet.netmask),
            "gateway": str(gateway),
            "usable_hosts": _usable_hosts(subnet),
            "gateway_reserved": gateway_reserved,
            "capacity_hosts": capacity_hosts,
            "representative_hosts": representative_hosts,
        }
        if dns not in (None, ""):
            segment["dns"] = str(group.get("dns", dns))
        elif group.get("dns") not in (None, ""):
            segment["dns"] = str(group["dns"])
        for optional in ("core", "access_switches", "switch", "host_prefix"):
            if group.get(optional) not in (None, ""):
                segment[optional] = group[optional]
        segments.append(segment)
        cursor = int(subnet.broadcast_address) + 1

    compose_segments = []
    for segment in segments:
        compose = {
            "name": segment["name"],
            "vlan": segment["vlan"],
            "subnet": segment["subnet"],
            "gateway": segment["gateway"],
            "representative_hosts": segment["representative_hosts"],
            "planned_hosts": segment["requested_hosts"],
            "capacity_hosts": segment["capacity_hosts"],
        }
        for optional in ("dns", "core", "access_switches", "switch", "host_prefix"):
            if optional in segment:
                compose[optional] = segment[optional]
        compose_segments.append(compose)

    return {
        "kind": "pt730-ip-plan",
        "address_pool": str(pool),
        "gateway_mode": gateway_mode,
        "segments": segments,
        "compose": {"segments": compose_segments},
        "unused": _summarize_unused(pool, cursor),
    }


def schema() -> dict[str, Any]:
    return {
        "commands": ["schema", "campus"],
        "fields": [
            "address_pool",
            "dns",
            "gateway_mode=last|first",
            "default_representative_hosts",
            "groups[].name",
            "groups[].hosts",
            "groups[].vlan",
            "groups[].prefix",
            "groups[].representative_hosts",
            "groups[].core",
            "groups[].access_switches",
        ],
        "example": {
            "address_pool": "192.168.0.0/21",
            "dns": "172.16.1.11",
            "default_representative_hosts": 2,
            "groups": [
                {"name": "OFFICE", "hosts": 60, "vlan": 20, "core": "MLS1"},
                {"name": "TEACH", "hosts": 60, "vlan": 30, "core": "MLS2"},
                {"name": "RESEARCH", "hosts": 120, "vlan": 40},
                {"name": "GRAD", "hosts": 200, "vlan": 50},
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
    parser = argparse.ArgumentParser(prog="pt730-ip-plan", description=__doc__)
    parser.add_argument("--compact", action="store_true", help="emit compact JSON")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("schema", help="print the campus IP planning schema and example")

    campus_p = sub.add_parser("campus", help="plan VLSM subnets for campus topology composition")
    campus_p.add_argument("spec", type=Path)
    campus_p.add_argument("--output", type=Path, help="write JSON to a file instead of stdout")

    args = parser.parse_args(argv)
    try:
        if args.cmd == "schema":
            emit_json(schema(), None, compact=args.compact)
            return 0
        if args.cmd == "campus":
            emit_json(plan_campus(_load_json(args.spec)), args.output, compact=args.compact)
            return 0
        raise ValueError(f"unknown command: {args.cmd}")
    except Exception as exc:  # noqa: BLE001
        print(f"pt730-ip-plan: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
