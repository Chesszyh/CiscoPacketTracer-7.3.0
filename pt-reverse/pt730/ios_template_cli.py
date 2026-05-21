#!/usr/bin/env python3
"""Render high-level IOS JSON templates to command sequences."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("IOS template must be a JSON object")
    return data


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def require(value: Any, message: str) -> Any:
    if value in (None, ""):
        raise ValueError(message)
    return value


def vlan_list(value: Any) -> str:
    if isinstance(value, list):
        return ",".join(str(item) for item in value)
    return str(value)


def render_commands(spec: dict[str, Any]) -> list[str]:
    device = str(require(spec.get("device", spec.get("name", "")), "device is required"))
    commands = ["enable", "configure terminal"]
    hostname = spec.get("hostname")
    if hostname:
        commands.append(f"hostname {hostname}")

    for vlan in as_list(spec.get("vlans")):
        if not isinstance(vlan, dict):
            raise ValueError("vlan entries must be objects")
        vlan_id = require(vlan.get("id", vlan.get("vlan")), "vlan id is required")
        commands.append(f"vlan {vlan_id}")
        if vlan.get("name"):
            commands.append(f" name {vlan['name']}")
        commands.append("exit")

    for interface in as_list(spec.get("interfaces")):
        if not isinstance(interface, dict):
            raise ValueError("interface entries must be objects")
        name = str(require(interface.get("name"), "interface name is required"))
        commands.append(f"interface {name}")
        if interface.get("description"):
            commands.append(f" description {interface['description']}")
        mode = str(interface.get("mode", "")).lower()
        if mode == "trunk":
            commands.extend([" switchport mode trunk", f" switchport trunk allowed vlan {vlan_list(interface.get('allowed_vlans', 'all'))}"])
        elif mode == "access":
            commands.extend([" switchport mode access", f" switchport access vlan {require(interface.get('vlan'), 'access interface vlan is required')}"])
        if interface.get("ip"):
            commands.append(f" ip address {interface['ip']} {require(interface.get('mask'), 'interface mask is required')}")
        if interface.get("nat") in ("inside", "outside"):
            commands.append(f" ip nat {interface['nat']}")
        if interface.get("shutdown") is True:
            commands.append(" shutdown")
        else:
            commands.append(" no shutdown")
        commands.append("exit")

    rip = spec.get("rip")
    if isinstance(rip, dict):
        commands.append("router rip")
        if rip.get("version"):
            commands.append(f" version {rip['version']}")
        if rip.get("no_auto_summary", True):
            commands.append(" no auto-summary")
        for network in as_list(rip.get("networks")):
            commands.append(f" network {network}")
        commands.append("exit")

    for route in as_list(spec.get("static_routes")):
        if not isinstance(route, dict):
            raise ValueError("static route entries must be objects")
        commands.append(
            f"ip route {require(route.get('destination'), 'static route destination is required')} "
            f"{require(route.get('mask'), 'static route mask is required')} "
            f"{require(route.get('next_hop', route.get('interface')), 'static route next_hop/interface is required')}"
        )

    for acl in as_list(spec.get("acls")):
        if not isinstance(acl, dict):
            raise ValueError("acl entries must be objects")
        number = require(acl.get("number", acl.get("name")), "acl number/name is required")
        acl_type = str(acl.get("type", "standard")).lower()
        for rule in as_list(acl.get("rules")):
            if not isinstance(rule, dict):
                raise ValueError("acl rule entries must be objects")
            action = str(rule.get("action", "permit"))
            if acl_type == "extended":
                protocol = str(rule.get("protocol", "ip"))
                src = str(rule.get("source", "any"))
                src_wc = rule.get("source_wildcard")
                dst = str(rule.get("destination", "any"))
                dst_wc = rule.get("destination_wildcard")
                parts = ["access-list", str(number), action, protocol, src]
                if src != "any" and src_wc:
                    parts.append(str(src_wc))
                parts.append(dst)
                if dst != "any" and dst_wc:
                    parts.append(str(dst_wc))
                commands.append(" ".join(parts))
            else:
                source = str(rule.get("source", "any"))
                wildcard = rule.get("wildcard")
                line = f"access-list {number} {action} {source}"
                if source != "any" and wildcard:
                    line += f" {wildcard}"
                commands.append(line)

    nat = spec.get("nat")
    if isinstance(nat, dict):
        for interface_name in as_list(nat.get("inside_interfaces")):
            commands.extend([f"interface {interface_name}", " ip nat inside", "exit"])
        for interface_name in as_list(nat.get("outside_interfaces")):
            commands.extend([f"interface {interface_name}", " ip nat outside", "exit"])
        for overload in as_list(nat.get("overloads")):
            if not isinstance(overload, dict):
                raise ValueError("nat overload entries must be objects")
            commands.append(
                f"ip nat inside source list {require(overload.get('acl'), 'nat overload acl is required')} "
                f"interface {require(overload.get('interface'), 'nat overload interface is required')} overload"
            )

    commands.append("end")
    if spec.get("save", False):
        commands.append("write memory")
    if not device:
        raise ValueError("device is required")
    return commands


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    render_p = sub.add_parser("render", help="render IOS commands")
    render_p.add_argument("spec", type=Path)
    render_p.add_argument("--topology-json", action="store_true", help="wrap commands in a pt730-topo ios_configs object")

    args = parser.parse_args(argv)
    try:
        spec = load_json(args.spec)
        commands = render_commands(spec)
        if args.topology_json:
            print(json.dumps({"ios_configs": [{"device": spec.get("device", spec.get("name")), "commands": commands}]}, ensure_ascii=False, indent=2))
        else:
            print("\n".join(commands))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"pt730-ios-template: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
