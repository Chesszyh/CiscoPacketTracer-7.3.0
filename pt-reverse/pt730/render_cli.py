#!/usr/bin/env python3
"""Render Packet Tracer topology JSON plans without contacting Packet Tracer."""

from __future__ import annotations

import argparse
import html
import ipaddress
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

from topology_cli import _enforce_plan_safety, _load_plan


COURSE_REQUIRED_VLANS = ("10", "20", "30", "40", "50", "60", "61", "62", "63", "64", "65")
COURSE_SERVER_NETWORK = ipaddress.ip_network("172.16.1.0/26")
COURSE_PC_NETWORK = ipaddress.ip_network("192.168.0.0/21")
COURSE_SERVER_GATEWAY = "172.16.1.62"
COURSE_EXPECTED_SERVERS = 50
COURSE_EXPECTED_PCS = 1900


def node_id(name: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_]", "_", name)
    if not value or value[0].isdigit():
        value = "n_" + value
    return value


def label(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def pick(obj: dict[str, Any], names: tuple[str, ...], fallback: str = "") -> str:
    for name in names:
        value = obj.get(name)
        if value is not None:
            return str(value)
    return fallback


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def yes_no(value: Any) -> str:
    if value is True:
        return "yes"
    if value is False:
        return "no"
    return ""


def svg_text(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def ip_config_fields(config: dict[str, Any]) -> dict[str, str]:
    return {
        "name": pick(config, ("name", "device", "pc", "server")),
        "port": pick(config, ("port",), "FastEthernet0"),
        "dhcp": yes_no(config.get("dhcp")),
        "ip": pick(config, ("ip", "ip_address", "address")),
        "mask": pick(config, ("mask", "subnet_mask", "netmask")),
        "gateway": pick(config, ("gateway", "default_gateway", "gw")),
        "dns": pick(config, ("dns", "dns_server")),
    }


def address_groups(plan: dict[str, Any]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str], dict[str, Any]] = {}
    for config in plan.get("pc_configs", []):
        if not isinstance(config, dict):
            continue
        fields = ip_config_fields(config)
        if not fields["ip"] or not fields["mask"]:
            continue
        try:
            network = ipaddress.ip_network(f"{fields['ip']}/{fields['mask']}", strict=False)
        except ValueError:
            continue
        key = (str(network), fields["gateway"], fields["dns"])
        entry = groups.setdefault(
            key,
            {
                "network": str(network),
                "gateway": fields["gateway"],
                "dns": fields["dns"],
                "hosts": [],
            },
        )
        entry["hosts"].append(fields["name"])
    return sorted(groups.values(), key=lambda item: ipaddress.ip_network(item["network"]).network_address)


def server_name(config: dict[str, Any]) -> str:
    return pick(config, ("name", "device", "server"))


def server_service_rows(plan: dict[str, Any]) -> dict[str, list[list[Any]]]:
    rows: dict[str, list[list[Any]]] = {
        "dns": [],
        "ftp": [],
        "email": [],
        "dhcp": [],
        "time_logging": [],
    }
    for config in plan.get("server_configs", []):
        if not isinstance(config, dict):
            continue
        name = server_name(config)

        dns = config.get("dns")
        if isinstance(dns, dict):
            for record in as_list(dns.get("records")):
                if isinstance(record, dict):
                    rows["dns"].append([name, pick(record, ("name", "host", "domain")), pick(record, ("ip", "address"))])

        ftp = config.get("ftp")
        if isinstance(ftp, dict):
            for account in as_list(ftp.get("accounts", ftp.get("users"))):
                if isinstance(account, dict):
                    rows["ftp"].append([
                        name,
                        pick(account, ("username", "user", "name")),
                        pick(account, ("permissions", "permission", "rights")),
                    ])

        email = config.get("email")
        if isinstance(email, dict):
            domain = pick(email, ("domain",))
            for account in as_list(email.get("accounts", email.get("users"))):
                if isinstance(account, dict):
                    rows["email"].append([name, domain, pick(account, ("username", "user", "name"))])

        dhcp = config.get("dhcp")
        if isinstance(dhcp, dict):
            rows["dhcp"].append([
                name,
                yes_no(dhcp.get("enabled")),
                pick(dhcp, ("network",)),
                pick(dhcp, ("mask", "subnet_mask", "netmask")),
                pick(dhcp, ("start", "start_ip", "first_ip")),
                pick(dhcp, ("end", "end_ip", "last_ip")),
                pick(dhcp, ("gateway", "default_gateway", "router")),
                pick(dhcp, ("dns", "dns_server")),
                pick(dhcp, ("max_users", "maximum_users")),
            ])

        ntp = config.get("ntp")
        syslog = config.get("syslog")
        if isinstance(ntp, dict) or isinstance(syslog, dict):
            rows["time_logging"].append([
                name,
                yes_no(ntp.get("enabled")) if isinstance(ntp, dict) else "",
                yes_no(ntp.get("authentication")) if isinstance(ntp, dict) else "",
                yes_no(syslog.get("enabled")) if isinstance(syslog, dict) else "",
                pick(syslog, ("port",)) if isinstance(syslog, dict) else "",
            ])
    return rows


def mermaid(plan: dict[str, Any], *, direction: str) -> str:
    lines = [f"flowchart {direction}"]
    seen_ids: set[str] = set()
    for index, device in enumerate(plan.get("devices", [])):
        if not isinstance(device, dict):
            continue
        name = pick(device, ("name", "id"), f"device_{index}")
        model = pick(device, ("model",), "")
        category = pick(device, ("category", "kind"), "")
        nid = node_id(name)
        seen_ids.add(nid)
        detail = f"{name}\\n{model}" if model else name
        if category:
            detail += f"\\n{category}"
        lines.append(f'  {nid}["{label(detail)}"]')

    for index, link in enumerate(plan.get("links", [])):
        if not isinstance(link, dict):
            continue
        a = pick(link, ("a", "device_a", "from", "from_device"), f"a_{index}")
        b = pick(link, ("b", "device_b", "to", "to_device"), f"b_{index}")
        pa = pick(link, ("pa", "port_a", "from_port"), "")
        pb = pick(link, ("pb", "port_b", "to_port"), "")
        cable = pick(link, ("cable", "type", "link_type", "cable_type"), "straight")
        link_label = " / ".join(part for part in [pa, cable, pb] if part)
        lines.append(f'  {node_id(a)} ---|"{label(link_label)}"| {node_id(b)}')

    if len(lines) == 1:
        lines.append("  empty[\"empty topology\"]")
    return "\n".join(lines) + "\n"


def svg_device_kind(device: dict[str, Any]) -> str:
    category = pick(device, ("category", "kind")).lower()
    model = pick(device, ("model",)).lower()
    name = pick(device, ("name", "id")).lower()
    joined = " ".join([category, model, name])
    if "router" in joined or model in {"2911", "1941", "1841"}:
        return "router"
    if "switch" in joined or "2960" in joined or "3560" in joined or "multilayer" in joined:
        return "switch"
    if "server" in joined:
        return "server"
    if "pc" in joined or "host" in joined or "laptop" in joined:
        return "pc"
    return "device"


def svg_devices(plan: dict[str, Any]) -> list[dict[str, Any]]:
    devices: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, device in enumerate(plan.get("devices", [])):
        if not isinstance(device, dict):
            continue
        item = dict(device)
        name = pick(item, ("name", "id"), f"device_{index}")
        item["name"] = name
        devices.append(item)
        seen.add(name)

    for index, link in enumerate(plan.get("links", [])):
        if not isinstance(link, dict):
            continue
        for names, fallback in ((("a", "device_a", "from", "from_device"), f"a_{index}"), (("b", "device_b", "to", "to_device"), f"b_{index}")):
            name = pick(link, names, fallback)
            if name and name not in seen:
                devices.append({"name": name, "category": "device", "model": ""})
                seen.add(name)

    return devices


def svg_positions(devices: list[dict[str, Any]]) -> tuple[dict[str, tuple[float, float]], float, float]:
    if not devices:
        return {}, 320.0, 220.0

    cols = max(1, math.ceil(math.sqrt(len(devices))))
    raw: dict[str, tuple[float, float]] = {}
    for index, device in enumerate(devices):
        name = pick(device, ("name", "id"), f"device_{index}")
        x = as_float(device.get("x"))
        y = as_float(device.get("y"))
        if x is None or y is None:
            x = float((index % cols) * 220)
            y = float((index // cols) * 150)
        raw[name] = (x, y)

    min_x = min(x for x, _ in raw.values())
    min_y = min(y for _, y in raw.values())
    max_x = max(x for x, _ in raw.values())
    max_y = max(y for _, y in raw.values())
    pad = 90.0
    positions = {name: (x - min_x + pad, y - min_y + pad) for name, (x, y) in raw.items()}
    width = max(320.0, max_x - min_x + pad * 2)
    height = max(220.0, max_y - min_y + pad * 2)
    return positions, width, height


def svg_link_label(link: dict[str, Any]) -> str:
    parts = [
        pick(link, ("pa", "port_a", "from_port")),
        pick(link, ("cable", "type", "link_type", "cable_type"), "straight"),
        pick(link, ("pb", "port_b", "to_port")),
    ]
    vlan = pick(link, ("vlan", "vlan_id"))
    if vlan:
        parts.append(f"VLAN {vlan}")
    note = pick(link, ("note", "description"))
    if note:
        parts.append(note)
    return " / ".join(part for part in parts if part)


def svg_device_group(device: dict[str, Any], x: float, y: float) -> list[str]:
    kind = svg_device_kind(device)
    name = pick(device, ("name", "id"))
    model = pick(device, ("model",))
    lines = [f'  <g class="device {kind}" transform="translate({x:.1f} {y:.1f})">']
    lines.append(f"    <title>{svg_text(name)} {svg_text(model)}</title>")
    if kind == "router":
        lines.append('    <ellipse cx="0" cy="0" rx="64" ry="32" />')
        lines.append('    <path d="M -34 -5 L 34 -5 M -18 8 L 18 8" />')
    elif kind == "switch":
        lines.append('    <rect x="-68" y="-32" width="136" height="64" rx="8" />')
        lines.append('    <path d="M -42 -8 H 42 M -42 8 H 42 M -42 -8 L -24 -20 M 42 8 L 24 20" />')
    elif kind == "server":
        lines.append('    <rect x="-54" y="-38" width="108" height="76" rx="6" />')
        lines.append('    <path d="M -54 -16 H 54 M -40 8 H 22 M 34 8 h8" />')
    elif kind == "pc":
        lines.append('    <rect x="-54" y="-36" width="108" height="62" rx="6" />')
        lines.append('    <path d="M -24 34 H 24 M -10 26 V 34 M 10 26 V 34" />')
    else:
        lines.append('    <rect x="-58" y="-32" width="116" height="64" rx="8" />')
    lines.append(f'    <text class="device-name" x="0" y="52">{svg_text(name)}</text>')
    if model:
        lines.append(f'    <text class="device-model" x="0" y="68">{svg_text(model)}</text>')
    lines.append("  </g>")
    return lines


def svg(plan: dict[str, Any]) -> str:
    devices = svg_devices(plan)
    positions, width, height = svg_positions(devices)
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="{height:.0f}" viewBox="0 0 {width:.0f} {height:.0f}" role="img" aria-labelledby="title desc">',
        "  <title id=\"title\">Packet Tracer topology</title>",
        "  <desc id=\"desc\">Offline-rendered Packet Tracer 7.3.0 topology diagram.</desc>",
        "  <style>",
        "    svg { background: #f8fafc; font-family: Inter, Segoe UI, Arial, sans-serif; }",
        "    .link { stroke: #475569; stroke-width: 2.2; stroke-linecap: round; }",
        "    .link-label { fill: #334155; font-size: 10px; text-anchor: middle; paint-order: stroke; stroke: #f8fafc; stroke-width: 4px; stroke-linejoin: round; }",
        "    .device text { text-anchor: middle; stroke: none; }",
        "    .device-name { fill: #0f172a; font-size: 13px; font-weight: 700; }",
        "    .device-model { fill: #475569; font-size: 10px; }",
        "    .device rect, .device ellipse { stroke-width: 2; }",
        "    .device path { fill: none; stroke-width: 2; stroke-linecap: round; }",
        "    .router ellipse { fill: #dbeafe; stroke: #1d4ed8; } .router path { stroke: #1d4ed8; }",
        "    .switch rect { fill: #dcfce7; stroke: #15803d; } .switch path { stroke: #15803d; }",
        "    .server rect { fill: #fef3c7; stroke: #b45309; } .server path { stroke: #b45309; }",
        "    .pc rect { fill: #e0e7ff; stroke: #4338ca; } .pc path { stroke: #4338ca; }",
        "    .device.device rect { fill: #f1f5f9; stroke: #64748b; }",
        "  </style>",
    ]

    for index, link in enumerate(plan.get("links", [])):
        if not isinstance(link, dict):
            continue
        a = pick(link, ("a", "device_a", "from", "from_device"), f"a_{index}")
        b = pick(link, ("b", "device_b", "to", "to_device"), f"b_{index}")
        if a not in positions or b not in positions:
            continue
        x1, y1 = positions[a]
        x2, y2 = positions[b]
        lines.append(f'  <line class="link" x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" />')
        link_label = svg_link_label(link)
        if link_label:
            mid_x = (x1 + x2) / 2
            mid_y = (y1 + y2) / 2 - 8
            lines.append(f'  <text class="link-label" x="{mid_x:.1f}" y="{mid_y:.1f}">{svg_text(link_label)}</text>')

    for device in devices:
        name = pick(device, ("name", "id"))
        if name in positions:
            x, y = positions[name]
            lines.extend(svg_device_group(device, x, y))

    if not devices:
        lines.append('  <text class="device-name" x="160" y="110">empty topology</text>')

    lines.append("</svg>")
    return "\n".join(lines) + "\n"


def cell(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", "<br>")


def markdown_table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    lines.extend("| " + " | ".join(cell(value) for value in row) + " |" for row in rows)
    return lines


def markdown(plan: dict[str, Any]) -> str:
    lines: list[str] = ["# Packet Tracer Topology Plan", ""]

    device_rows = []
    for device in plan.get("devices", []):
        if isinstance(device, dict):
            device_rows.append([
                pick(device, ("name", "id")),
                pick(device, ("model",)),
                pick(device, ("category", "kind")),
                pick(device, ("x",)),
                pick(device, ("y",)),
            ])
    lines.extend(["## Devices", ""])
    lines.extend(markdown_table(["Name", "Model", "Category", "X", "Y"], device_rows))
    lines.append("")

    module_rows = []
    for module in plan.get("modules", []):
        if isinstance(module, dict):
            module_rows.append([
                pick(module, ("device", "device_name", "on")),
                pick(module, ("slot",)),
                pick(module, ("model", "module", "name")),
            ])
    if module_rows:
        lines.extend(["## Modules", ""])
        lines.extend(markdown_table(["Device", "Slot", "Module"], module_rows))
        lines.append("")

    link_rows = []
    for link in plan.get("links", []):
        if isinstance(link, dict):
            link_rows.append([
                pick(link, ("a", "device_a", "from", "from_device")),
                pick(link, ("pa", "port_a", "from_port")),
                pick(link, ("b", "device_b", "to", "to_device")),
                pick(link, ("pb", "port_b", "to_port")),
                pick(link, ("cable", "type", "link_type", "cable_type"), "straight"),
                pick(link, ("vlan", "vlan_id")),
                pick(link, ("note", "description")),
            ])
    lines.extend(["## Links", ""])
    lines.extend(markdown_table(["A", "Port A", "B", "Port B", "Cable", "VLAN", "Note"], link_rows))
    lines.append("")

    pc_rows = []
    for config in plan.get("pc_configs", []):
        if isinstance(config, dict):
            pc_rows.append([
                pick(config, ("name", "device", "pc")),
                pick(config, ("port",), "FastEthernet0"),
                "yes" if config.get("dhcp") is True else "no" if config.get("dhcp") is False else "",
                pick(config, ("ip", "ip_address", "address")),
                pick(config, ("mask", "subnet_mask", "netmask")),
                pick(config, ("gateway", "default_gateway", "gw")),
                pick(config, ("dns", "dns_server")),
            ])
    if pc_rows:
        lines.extend(["## PC And Host IP Configs", ""])
        lines.extend(markdown_table(["Name", "Port", "DHCP", "IP", "Mask", "Gateway", "DNS"], pc_rows))
        lines.append("")

    address_rows = []
    for group in address_groups(plan):
        hosts = group["hosts"]
        shown_hosts = ", ".join(hosts[:6])
        if len(hosts) > 6:
            shown_hosts += f", ... (+{len(hosts) - 6})"
        address_rows.append([group["network"], group["gateway"], group["dns"], len(hosts), shown_hosts])
    if address_rows:
        lines.extend(["## Address Summary", ""])
        lines.extend(markdown_table(["Network", "Gateway", "DNS", "Configured Hosts", "Sample Hosts"], address_rows))
        lines.append("")

    server_rows = []
    for config in plan.get("server_configs", []):
        if isinstance(config, dict):
            services = []
            for service in ("http", "ftp", "dns", "tftp", "email", "ntp", "syslog", "dhcp"):
                if service in config:
                    services.append(service.upper())
            server_rows.append([pick(config, ("name", "device", "server")), pick(config, ("port",), "FastEthernet0"), ", ".join(services)])
    if server_rows:
        lines.extend(["## Server Services", ""])
        lines.extend(markdown_table(["Name", "Port", "Configured Services"], server_rows))
        lines.append("")

    service_rows = server_service_rows(plan)
    if service_rows["dns"]:
        lines.extend(["## DNS Records", ""])
        lines.extend(markdown_table(["Server", "Name", "IP"], service_rows["dns"]))
        lines.append("")
    if service_rows["ftp"]:
        lines.extend(["## FTP Users", ""])
        lines.extend(markdown_table(["Server", "Username", "Permissions"], service_rows["ftp"]))
        lines.append("")
    if service_rows["email"]:
        lines.extend(["## Email Accounts", ""])
        lines.extend(markdown_table(["Server", "Domain", "Username"], service_rows["email"]))
        lines.append("")
    if service_rows["dhcp"]:
        lines.extend(["## DHCP Server Pools", ""])
        lines.extend(markdown_table(["Server", "Enabled", "Network", "Mask", "Start", "End", "Gateway", "DNS", "Max Users"], service_rows["dhcp"]))
        lines.append("")
    if service_rows["time_logging"]:
        lines.extend(["## Time And Logging Services", ""])
        lines.extend(markdown_table(["Server", "NTP", "NTP Auth", "Syslog", "Syslog Port"], service_rows["time_logging"]))
        lines.append("")

    ios_rows = []
    for config in plan.get("ios_configs", []):
        if isinstance(config, dict):
            commands = config.get("commands", config.get("cmds", config.get("config", config.get("cli", []))))
            if isinstance(commands, str):
                command_count = len([line for line in commands.splitlines() if line.strip()])
            elif isinstance(commands, list):
                command_count = len(commands)
            else:
                command_count = 0
            init_dialog = "yes" if config.get("init_dialog") or config.get("initDialog") or config.get("answer_initial_dialog") else "no"
            ios_rows.append([
                pick(config, ("name", "device", "router", "switch")),
                init_dialog,
                command_count,
                "yes" if config.get("save") or config.get("write_memory") else "no",
            ])
    if ios_rows:
        lines.extend(["## IOS Configs", ""])
        lines.extend(markdown_table(["Device", "Init Dialog", "Commands", "Save"], ios_rows))
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def summary(plan: dict[str, Any]) -> str:
    vlan_counts: dict[str, int] = {}
    noted_links: list[dict[str, str]] = []
    for link in plan.get("links", []):
        if not isinstance(link, dict):
            continue
        vlan = pick(link, ("vlan", "vlan_id"))
        if vlan:
            vlan_counts[vlan] = vlan_counts.get(vlan, 0) + 1
        note = pick(link, ("note", "description"))
        if note:
            noted_links.append(
                {
                    "a": pick(link, ("a", "device_a", "from", "from_device")),
                    "pa": pick(link, ("pa", "port_a", "from_port")),
                    "b": pick(link, ("b", "device_b", "to", "to_device")),
                    "pb": pick(link, ("pb", "port_b", "to_port")),
                    "note": note,
                }
            )

    service_rows = server_service_rows(plan)
    data = {
        "counts": {
            "devices": len(plan.get("devices", [])),
            "modules": len(plan.get("modules", [])),
            "links": len(plan.get("links", [])),
            "pc_configs": len(plan.get("pc_configs", [])),
            "server_configs": len(plan.get("server_configs", [])),
            "ios_configs": len(plan.get("ios_configs", [])),
        },
        "address_groups": [
            {
                "network": group["network"],
                "gateway": group["gateway"],
                "dns": group["dns"],
                "configured_hosts": len(group["hosts"]),
                "hosts": group["hosts"],
            }
            for group in address_groups(plan)
        ],
        "vlan_link_counts": dict(sorted(vlan_counts.items(), key=lambda item: int(item[0]) if item[0].isdigit() else item[0])),
        "noted_links": noted_links,
        "server_service_counts": {name: len(rows) for name, rows in service_rows.items()},
    }
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def course_audit(plan: dict[str, Any]) -> tuple[dict[str, Any], int]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    vlan_counts: dict[str, int] = {}
    for link in plan.get("links", []):
        if not isinstance(link, dict):
            continue
        vlan = pick(link, ("vlan", "vlan_id"))
        if vlan:
            vlan_counts[vlan] = vlan_counts.get(vlan, 0) + 1

    present_vlans = sorted(vlan_counts, key=lambda value: int(value) if value.isdigit() else value)
    missing_vlans = [vlan for vlan in COURSE_REQUIRED_VLANS if vlan not in vlan_counts]
    if missing_vlans:
        errors.append({"where": "links", "message": "missing required VLAN links", "missing": missing_vlans})

    server_groups: list[dict[str, Any]] = []
    pc_groups: list[dict[str, Any]] = []
    out_of_scope_groups: list[dict[str, Any]] = []
    for group in address_groups(plan):
        network = ipaddress.ip_network(group["network"])
        rendered = {
            "network": group["network"],
            "gateway": group["gateway"],
            "dns": group["dns"],
            "configured_hosts": len(group["hosts"]),
            "hosts": group["hosts"],
        }
        if network.subnet_of(COURSE_SERVER_NETWORK):
            server_groups.append(rendered)
        elif network.subnet_of(COURSE_PC_NETWORK):
            pc_groups.append(rendered)
        else:
            out_of_scope_groups.append(rendered)

    if not server_groups:
        errors.append({"where": "pc_configs", "message": "missing representative hosts in required server address space"})
    if not pc_groups:
        errors.append({"where": "pc_configs", "message": "missing representative hosts in required PC address space"})
    if out_of_scope_groups:
        errors.append({"where": "pc_configs", "message": "configured hosts outside assignment address spaces", "groups": out_of_scope_groups})
    if server_groups and not any(group["gateway"] == COURSE_SERVER_GATEWAY for group in server_groups):
        errors.append({"where": "pc_configs", "message": "server representative hosts do not use required gateway", "gateway": COURSE_SERVER_GATEWAY})

    representative_hosts = len([config for config in plan.get("pc_configs", []) if isinstance(config, dict)])
    if representative_hosts < len(COURSE_REQUIRED_VLANS):
        warnings.append(
            {
                "where": "pc_configs",
                "message": "fewer representative host configs than required VLANs",
                "configured": representative_hosts,
                "required_vlans": len(COURSE_REQUIRED_VLANS),
            }
        )

    report = {
        "kind": "college-network-course-audit",
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "checks": {
            "required_vlans": {
                "expected": list(COURSE_REQUIRED_VLANS),
                "present": present_vlans,
                "missing": missing_vlans,
                "link_counts": dict(sorted(vlan_counts.items(), key=lambda item: int(item[0]) if item[0].isdigit() else item[0])),
            },
            "server_address_space": {
                "network": str(COURSE_SERVER_NETWORK),
                "gateway": COURSE_SERVER_GATEWAY,
                "representative_groups": server_groups,
            },
            "pc_address_space": {
                "network": str(COURSE_PC_NETWORK),
                "representative_groups": pc_groups,
            },
            "representative_hosts": {
                "configured": representative_hosts,
                "expected_servers": COURSE_EXPECTED_SERVERS,
                "expected_pcs": COURSE_EXPECTED_PCS,
                "note": "Packet Tracer plan is representative; full capacity is documented in course-design Markdown.",
            },
        },
    }
    return report, 0 if report["ok"] else 1


def emit(text: str, output: Path | None) -> None:
    if output is None:
        print(text, end="")
        return
    output.write_text(text, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict-safety", action="store_true", help="treat safety warnings as failures")
    parser.add_argument("--allow-risky", action="store_true", help="allow known crash-risk or unverified plan items")
    sub = parser.add_subparsers(dest="cmd", required=True)

    mermaid_p = sub.add_parser("mermaid", help="render a plan as Mermaid flowchart")
    mermaid_p.add_argument("plan", type=Path)
    mermaid_p.add_argument("--direction", default="LR", choices=["LR", "TD", "TB", "RL", "BT"])
    mermaid_p.add_argument("--output", type=Path, help="write output to a file instead of stdout")

    svg_p = sub.add_parser("svg", help="render a plan as an offline SVG topology diagram")
    svg_p.add_argument("plan", type=Path)
    svg_p.add_argument("--output", type=Path, help="write output to a file instead of stdout")

    markdown_p = sub.add_parser("markdown", help="render a plan as Markdown tables")
    markdown_p.add_argument("plan", type=Path)
    markdown_p.add_argument("--output", type=Path, help="write output to a file instead of stdout")

    summary_p = sub.add_parser("summary", help="render a plan as machine-readable JSON summary")
    summary_p.add_argument("plan", type=Path)
    summary_p.add_argument("--output", type=Path, help="write output to a file instead of stdout")

    audit_p = sub.add_parser("course-audit", help="audit the college-network course-design topology plan offline")
    audit_p.add_argument("plan", type=Path)
    audit_p.add_argument("--output", type=Path, help="write output to a file instead of stdout")

    args = parser.parse_args(argv)
    try:
        if args.cmd == "mermaid":
            plan = _load_plan(args.plan)
            _enforce_plan_safety(plan, allow_risky=args.allow_risky, strict=args.strict_safety)
            emit(mermaid(plan, direction=args.direction), args.output)
            return 0
        if args.cmd == "svg":
            plan = _load_plan(args.plan)
            _enforce_plan_safety(plan, allow_risky=args.allow_risky, strict=args.strict_safety)
            emit(svg(plan), args.output)
            return 0
        if args.cmd == "markdown":
            plan = _load_plan(args.plan)
            _enforce_plan_safety(plan, allow_risky=args.allow_risky, strict=args.strict_safety)
            emit(markdown(plan), args.output)
            return 0
        if args.cmd == "summary":
            plan = _load_plan(args.plan)
            _enforce_plan_safety(plan, allow_risky=args.allow_risky, strict=args.strict_safety)
            emit(summary(plan), args.output)
            return 0
        if args.cmd == "course-audit":
            plan = _load_plan(args.plan)
            _enforce_plan_safety(plan, allow_risky=args.allow_risky, strict=args.strict_safety)
            report, code = course_audit(plan)
            emit(json.dumps(report, ensure_ascii=False, indent=2) + "\n", args.output)
            return code
    except (OSError, ValueError) as exc:
        print(f"pt730-render: {exc}", file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
