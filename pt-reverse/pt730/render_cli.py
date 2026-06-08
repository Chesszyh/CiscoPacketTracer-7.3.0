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
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from topology_cli import _enforce_plan_safety, _load_plan


COURSE_REQUIRED_VLANS = ("10", "20", "30", "40", "50", "60", "61", "62", "63", "64", "65")
COURSE_SERVER_NETWORK = ipaddress.ip_network("172.16.1.0/26")
COURSE_PC_NETWORK = ipaddress.ip_network("192.168.0.0/21")
COURSE_SERVER_GATEWAY = "172.16.1.62"
COURSE_EXPECTED_SERVERS = 50
COURSE_EXPECTED_PCS = 1900
RENDER_THEMES = ("light", "dark", "paper")
RENDER_GROUP_BY = ("none", "auto", "network", "vlan", "site", "category")


@dataclass(frozen=True)
class RenderOptions:
    theme: str = "light"
    link_labels: bool = True
    model_labels: bool = True
    group_by: str = "none"


def render_palette(theme: str) -> dict[str, str]:
    if theme == "dark":
        return {
            "bg": "#0f172a",
            "html_bg": "#020617",
            "panel_bg": "#0f172a",
            "panel_border": "#334155",
            "text": "#e2e8f0",
            "muted": "#94a3b8",
            "report_bg": "#111827",
            "link": "#94a3b8",
            "label": "#e2e8f0",
            "label_back": "#0f172a",
            "router_fill": "#1e3a8a",
            "router_stroke": "#93c5fd",
            "switch_fill": "#14532d",
            "switch_stroke": "#86efac",
            "server_fill": "#78350f",
            "server_stroke": "#fbbf24",
            "pc_fill": "#312e81",
            "pc_stroke": "#a5b4fc",
            "wireless_fill": "#164e63",
            "wireless_stroke": "#67e8f9",
            "wireless_link": "#22d3ee",
            "device_fill": "#1f2937",
            "device_stroke": "#94a3b8",
            "group_fill": "#1e293b",
            "group_stroke": "#64748b",
        }
    if theme == "paper":
        return {
            "bg": "#fbf7ef",
            "html_bg": "#f3eadb",
            "panel_bg": "#fffaf2",
            "panel_border": "#d6c6ad",
            "text": "#1f2933",
            "muted": "#6b5f51",
            "report_bg": "#fffaf2",
            "link": "#6b7280",
            "label": "#374151",
            "label_back": "#fbf7ef",
            "router_fill": "#dbeafe",
            "router_stroke": "#1d4ed8",
            "switch_fill": "#dcfce7",
            "switch_stroke": "#15803d",
            "server_fill": "#fde68a",
            "server_stroke": "#b45309",
            "pc_fill": "#e0e7ff",
            "pc_stroke": "#4338ca",
            "wireless_fill": "#cffafe",
            "wireless_stroke": "#0891b2",
            "wireless_link": "#0e7490",
            "device_fill": "#f1f5f9",
            "device_stroke": "#64748b",
            "group_fill": "#fff3d7",
            "group_stroke": "#b8975b",
        }
    return {
        "bg": "#f8fafc",
        "html_bg": "#f1f5f9",
        "panel_bg": "#ffffff",
        "panel_border": "#cbd5e1",
        "text": "#0f172a",
        "muted": "#475569",
        "report_bg": "#ffffff",
        "link": "#475569",
        "label": "#334155",
        "label_back": "#f8fafc",
        "router_fill": "#dbeafe",
        "router_stroke": "#1d4ed8",
        "switch_fill": "#dcfce7",
        "switch_stroke": "#15803d",
        "server_fill": "#fef3c7",
        "server_stroke": "#b45309",
        "pc_fill": "#e0e7ff",
        "pc_stroke": "#4338ca",
        "wireless_fill": "#cffafe",
        "wireless_stroke": "#0891b2",
        "wireless_link": "#0e7490",
        "device_fill": "#f1f5f9",
        "device_stroke": "#64748b",
        "group_fill": "#e2e8f0",
        "group_stroke": "#64748b",
    }


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


def mermaid(plan: dict[str, Any], *, direction: str, link_labels: bool = True) -> str:
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
        if link_labels and link_label:
            lines.append(f'  {node_id(a)} ---|"{label(link_label)}"| {node_id(b)}')
        else:
            lines.append(f"  {node_id(a)} --- {node_id(b)}")

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
    if "accesspoint" in joined or "access point" in joined or name.startswith("ap-"):
        return "wireless"
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


def link_endpoint(link: dict[str, Any], aliases: tuple[str, ...]) -> str:
    return pick(link, aliases)


def link_pairs(plan: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    pairs: list[tuple[str, str, dict[str, Any]]] = []
    for link in plan.get("links", []):
        if not isinstance(link, dict):
            continue
        a = link_endpoint(link, ("a", "device_a", "from", "from_device"))
        b = link_endpoint(link, ("b", "device_b", "to", "to_device"))
        if a and b:
            pairs.append((a, b, link))
    return pairs


def chosen_group_by(plan: dict[str, Any], group_by: str) -> str:
    if group_by != "auto":
        return group_by
    if any("site " in pick(link, ("note", "description")).lower() for link in plan.get("links", []) if isinstance(link, dict)):
        return "site"
    if any(pick(link, ("vlan", "vlan_id")) for link in plan.get("links", []) if isinstance(link, dict)):
        return "vlan"
    if address_groups(plan):
        return "network"
    return "category"


def visual_groups(plan: dict[str, Any], devices: list[dict[str, Any]], group_by: str) -> list[dict[str, Any]]:
    mode = chosen_group_by(plan, group_by)
    if mode == "none":
        return []

    known = {pick(device, ("name", "id"), f"device_{index}") for index, device in enumerate(devices)}
    pairs = link_pairs(plan)
    direct_neighbors: dict[str, set[str]] = {name: set() for name in known}
    for a, b, _link in pairs:
        if a in known and b in known:
            direct_neighbors.setdefault(a, set()).add(b)
            direct_neighbors.setdefault(b, set()).add(a)

    groups: dict[str, set[str]] = {}
    if mode == "network":
        for group in address_groups(plan):
            label_text = group["network"]
            members = {name for name in group["hosts"] if name in known}
            for member in list(members):
                for neighbor in direct_neighbors.get(member, set()):
                    neighbor_device = next((device for device in devices if pick(device, ("name", "id")) == neighbor), {})
                    if svg_device_kind(neighbor_device) in {"switch", "router", "wireless"}:
                        members.add(neighbor)
            if members:
                gateway = group.get("gateway")
                if gateway:
                    label_text = f"{label_text} gw {gateway}"
                groups[label_text] = members
    elif mode == "vlan":
        for a, b, link in pairs:
            vlan = pick(link, ("vlan", "vlan_id"))
            if vlan:
                groups.setdefault(f"VLAN {vlan}", set()).update(name for name in (a, b) if name in known)
    elif mode == "site":
        for a, b, link in pairs:
            note = pick(link, ("note", "description"))
            match = re.search(r"\bsite\s+([A-Za-z0-9_-]+)", note, flags=re.IGNORECASE)
            if match:
                groups.setdefault(f"Site {match.group(1)}", set()).update(name for name in (a, b) if name in known)
        if not groups:
            for device in devices:
                name = pick(device, ("name", "id"))
                match = re.search(r"-(\d+)(?:-|$)", name)
                if match:
                    groups.setdefault(f"Site {match.group(1)}", set()).add(name)
    elif mode == "category":
        labels = {"router": "Routers", "switch": "Switches", "server": "Servers", "pc": "Hosts", "wireless": "Wireless", "device": "Other Devices"}
        for device in devices:
            name = pick(device, ("name", "id"))
            groups.setdefault(labels.get(svg_device_kind(device), "Other Devices"), set()).add(name)

    result = []
    for label_text, members in groups.items():
        filtered = sorted((member for member in members if member in known), key=str.lower)
        if len(filtered) >= 2:
            result.append({"label": label_text, "devices": filtered})
    return sorted(result, key=lambda item: (item["label"].lower(), item["devices"]))


def visual_group_boxes(groups: list[dict[str, Any]], positions: dict[str, tuple[float, float]]) -> list[dict[str, Any]]:
    boxes = []
    for index, group in enumerate(groups):
        points = [positions[name] for name in group["devices"] if name in positions]
        if len(points) < 2:
            continue
        min_x = min(x for x, _ in points)
        max_x = max(x for x, _ in points)
        min_y = min(y for _, y in points)
        max_y = max(y for _, y in points)
        pad_x = 88.0
        pad_y = 72.0
        boxes.append(
            {
                "id": f"group-{index + 1}",
                "label": group["label"],
                "x": max(4.0, min_x - pad_x),
                "y": max(18.0, min_y - pad_y),
                "width": max(180.0, max_x - min_x + pad_x * 2),
                "height": max(130.0, max_y - min_y + pad_y * 2),
            }
        )
    return boxes


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


def is_wireless_link(link: dict[str, Any]) -> bool:
    cable = pick(link, ("cable", "type", "link_type", "cable_type")).lower()
    note = pick(link, ("note", "description")).lower()
    return "wireless" in cable or "wireless" in note


def svg_device_group(device: dict[str, Any], x: float, y: float, *, options: RenderOptions) -> list[str]:
    kind = svg_device_kind(device)
    name = pick(device, ("name", "id"))
    model = pick(device, ("model",))
    lines = [f'  <g class="device {kind}" transform="translate({x:.1f} {y:.1f})">']
    title = name if not options.model_labels or not model else f"{name} {model}"
    lines.append(f"    <title>{svg_text(title)}</title>")
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
    elif kind == "wireless":
        lines.append('    <rect x="-54" y="-34" width="108" height="68" rx="8" />')
        lines.append('    <circle cx="0" cy="2" r="5" />')
        lines.append('    <path d="M -30 -2 Q 0 -30 30 -2 M -19 10 Q 0 -9 19 10" />')
    else:
        lines.append('    <rect x="-58" y="-32" width="116" height="64" rx="8" />')
    lines.append(f'    <text class="device-name" x="0" y="52">{svg_text(name)}</text>')
    if model and options.model_labels:
        lines.append(f'    <text class="device-model" x="0" y="68">{svg_text(model)}</text>')
    lines.append("  </g>")
    return lines


def svg(plan: dict[str, Any], *, options: RenderOptions = RenderOptions()) -> str:
    devices = svg_devices(plan)
    positions, width, height = svg_positions(devices)
    groups = visual_groups(plan, devices, options.group_by)
    group_boxes = visual_group_boxes(groups, positions)
    for box in group_boxes:
        width = max(width, box["x"] + box["width"] + 12.0)
        height = max(height, box["y"] + box["height"] + 12.0)
    palette = render_palette(options.theme)
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="{height:.0f}" viewBox="0 0 {width:.0f} {height:.0f}" role="img" aria-labelledby="title desc">',
        "  <title id=\"title\">Packet Tracer topology</title>",
        "  <desc id=\"desc\">Offline-rendered Packet Tracer 7.3.0 topology diagram.</desc>",
        "  <style>",
        f"    svg {{ background: {palette['bg']}; font-family: Inter, Segoe UI, Arial, sans-serif; }}",
        f"    .link {{ stroke: {palette['link']}; stroke-width: 2.2; stroke-linecap: round; }}",
        f"    .link-label {{ fill: {palette['label']}; font-size: 10px; text-anchor: middle; paint-order: stroke; stroke: {palette['label_back']}; stroke-width: 4px; stroke-linejoin: round; }}",
        "    .device text { text-anchor: middle; stroke: none; }",
        f"    .device-name {{ fill: {palette['text']}; font-size: 13px; font-weight: 700; }}",
        f"    .device-model {{ fill: {palette['muted']}; font-size: 10px; }}",
        "    .device rect, .device ellipse { stroke-width: 2; }",
        "    .device path { fill: none; stroke-width: 2; stroke-linecap: round; }",
        "    .device circle { stroke-width: 2; }",
        f"    .group-box {{ fill: {palette['group_fill']}; fill-opacity: 0.22; stroke: {palette['group_stroke']}; stroke-width: 1.4; stroke-dasharray: 8 6; }}",
        f"    .group-label {{ fill: {palette['muted']}; font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 0; }}",
        f"    .router ellipse {{ fill: {palette['router_fill']}; stroke: {palette['router_stroke']}; }} .router path {{ stroke: {palette['router_stroke']}; }}",
        f"    .switch rect {{ fill: {palette['switch_fill']}; stroke: {palette['switch_stroke']}; }} .switch path {{ stroke: {palette['switch_stroke']}; }}",
        f"    .server rect {{ fill: {palette['server_fill']}; stroke: {palette['server_stroke']}; }} .server path {{ stroke: {palette['server_stroke']}; }}",
        f"    .pc rect {{ fill: {palette['pc_fill']}; stroke: {palette['pc_stroke']}; }} .pc path {{ stroke: {palette['pc_stroke']}; }}",
        f"    .wireless rect, .wireless circle {{ fill: {palette['wireless_fill']}; stroke: {palette['wireless_stroke']}; }} .wireless path {{ stroke: {palette['wireless_stroke']}; }}",
        f"    .wireless-link {{ stroke: {palette['wireless_link']}; stroke-dasharray: 7 7; }}",
        f"    .device:not(.router):not(.switch):not(.server):not(.pc):not(.wireless) rect {{ fill: {palette['device_fill']}; stroke: {palette['device_stroke']}; }}",
        "  </style>",
    ]

    for box in group_boxes:
        lines.append(f'  <g class="visual-group" id="{svg_text(box["id"])}">')
        lines.append(f'    <rect class="group-box" x="{box["x"]:.1f}" y="{box["y"]:.1f}" width="{box["width"]:.1f}" height="{box["height"]:.1f}" rx="14" />')
        lines.append(f'    <text class="group-label" x="{box["x"] + 14:.1f}" y="{box["y"] + 22:.1f}">{svg_text(box["label"])}</text>')
        lines.append("  </g>")

    for index, link in enumerate(plan.get("links", [])):
        if not isinstance(link, dict):
            continue
        a = pick(link, ("a", "device_a", "from", "from_device"), f"a_{index}")
        b = pick(link, ("b", "device_b", "to", "to_device"), f"b_{index}")
        if a not in positions or b not in positions:
            continue
        x1, y1 = positions[a]
        x2, y2 = positions[b]
        classes = "link wireless-link" if is_wireless_link(link) else "link"
        lines.append(f'  <line class="{classes}" x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" />')
        link_label = svg_link_label(link)
        if options.link_labels and link_label:
            mid_x = (x1 + x2) / 2
            mid_y = (y1 + y2) / 2 - 8
            lines.append(f'  <text class="link-label" x="{mid_x:.1f}" y="{mid_y:.1f}">{svg_text(link_label)}</text>')

    for device in devices:
        name = pick(device, ("name", "id"))
        if name in positions:
            x, y = positions[name]
            lines.extend(svg_device_group(device, x, y, options=options))

    if not devices:
        lines.append('  <text class="device-name" x="160" y="110">empty topology</text>')

    lines.append("</svg>")
    return "\n".join(lines) + "\n"


def svg_fragment(plan: dict[str, Any], *, options: RenderOptions = RenderOptions()) -> str:
    lines = svg(plan, options=options).splitlines()
    if lines and lines[0].startswith("<?xml"):
        lines = lines[1:]
    return "\n".join(lines)


def html_report(plan: dict[str, Any], *, options: RenderOptions = RenderOptions()) -> str:
    report = markdown(plan)
    palette = render_palette(options.theme)
    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="en">',
            "<head>",
            '  <meta charset="utf-8">',
            '  <meta name="viewport" content="width=device-width, initial-scale=1">',
            "  <title>Packet Tracer Topology Plan</title>",
            "  <style>",
            f"    body {{ margin: 0; background: {palette['html_bg']}; color: {palette['text']}; font-family: Inter, Segoe UI, Arial, sans-serif; }}",
            "    main { max-width: 1180px; margin: 0 auto; padding: 24px; }",
            "    h1 { font-size: 24px; margin: 0 0 18px; }",
            "    section { margin-top: 20px; }",
            f"    .diagram {{ overflow: auto; background: {palette['panel_bg']}; border: 1px solid {palette['panel_border']}; }}",
            "    .diagram svg { display: block; min-width: 100%; }",
            f"    pre {{ overflow: auto; white-space: pre-wrap; background: {palette['report_bg']}; border: 1px solid {palette['panel_border']}; padding: 16px; line-height: 1.45; }}",
            "  </style>",
            "</head>",
            "<body>",
            "  <main>",
            "    <h1>Packet Tracer Topology Plan</h1>",
            '    <section class="diagram" aria-label="Topology diagram">',
            svg_fragment(plan, options=options),
            "    </section>",
            '    <section aria-label="Topology report">',
            f"      <pre>{svg_text(report)}</pre>",
            "    </section>",
            "  </main>",
            "</body>",
            "</html>",
            "",
        ]
    )


def drawio_style(kind: str, *, theme: str) -> tuple[str, float, float]:
    palette = render_palette(theme)
    if kind == "router":
        return (f"ellipse;whiteSpace=wrap;html=1;fillColor={palette['router_fill']};strokeColor={palette['router_stroke']};fontColor={palette['text']};fontStyle=1;", 128.0, 64.0)
    if kind == "switch":
        return (f"rounded=1;whiteSpace=wrap;html=1;fillColor={palette['switch_fill']};strokeColor={palette['switch_stroke']};fontColor={palette['text']};fontStyle=1;", 136.0, 64.0)
    if kind == "server":
        return (f"rounded=1;whiteSpace=wrap;html=1;fillColor={palette['server_fill']};strokeColor={palette['server_stroke']};fontColor={palette['text']};fontStyle=1;", 116.0, 76.0)
    if kind == "pc":
        return (f"rounded=1;whiteSpace=wrap;html=1;fillColor={palette['pc_fill']};strokeColor={palette['pc_stroke']};fontColor={palette['text']};fontStyle=1;", 116.0, 70.0)
    if kind == "wireless":
        return (f"rounded=1;whiteSpace=wrap;html=1;fillColor={palette['wireless_fill']};strokeColor={palette['wireless_stroke']};fontColor={palette['text']};fontStyle=1;", 116.0, 70.0)
    return (f"rounded=1;whiteSpace=wrap;html=1;fillColor={palette['device_fill']};strokeColor={palette['device_stroke']};fontColor={palette['text']};fontStyle=1;", 116.0, 64.0)


def drawio(plan: dict[str, Any], *, options: RenderOptions = RenderOptions()) -> str:
    devices = svg_devices(plan)
    positions, width, height = svg_positions(devices)
    groups = visual_groups(plan, devices, options.group_by)
    group_boxes = visual_group_boxes(groups, positions)
    for box in group_boxes:
        width = max(width, box["x"] + box["width"] + 12.0)
        height = max(height, box["y"] + box["height"] + 12.0)
    ids = {pick(device, ("name", "id"), f"device_{index}"): f"d{index + 2}" for index, device in enumerate(devices)}
    palette = render_palette(options.theme)
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<mxfile host="app.diagrams.net" modified="2026-06-08T00:00:00.000Z" agent="pt730-render" version="24.7.17" type="device">',
        '  <diagram id="pt730-topology" name="Packet Tracer Topology">',
        f'    <mxGraphModel dx="{max(800, int(width))}" dy="{max(600, int(height))}" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="{max(850, int(width + 80))}" pageHeight="{max(1100, int(height + 80))}" math="0" shadow="0">',
        "      <root>",
        '        <mxCell id="0" />',
        '        <mxCell id="1" parent="0" />',
    ]

    for index, box in enumerate(group_boxes):
        style = (
            "rounded=1;whiteSpace=wrap;html=1;dashed=1;fillColor="
            f"{palette['group_fill']};fillOpacity=18;strokeColor={palette['group_stroke']};"
            f"fontColor={palette['muted']};fontStyle=1;align=left;verticalAlign=top;spacingLeft=10;spacingTop=6;"
        )
        lines.append(f'        <mxCell id="g{index + 2}" value="{svg_text(box["label"])}" style="{svg_text(style)}" vertex="1" parent="1">')
        lines.append(f'          <mxGeometry x="{box["x"]:.1f}" y="{box["y"]:.1f}" width="{box["width"]:.1f}" height="{box["height"]:.1f}" as="geometry" />')
        lines.append("        </mxCell>")

    for index, device in enumerate(devices):
        name = pick(device, ("name", "id"), f"device_{index}")
        model = pick(device, ("model",))
        kind = svg_device_kind(device)
        style, item_width, item_height = drawio_style(kind, theme=options.theme)
        x, y = positions.get(name, (90.0, 90.0))
        value = name if not model or not options.model_labels else f"{name}\n{model}"
        lines.append(f'        <mxCell id="{ids[name]}" value="{svg_text(value)}" style="{svg_text(style)}" vertex="1" parent="1">')
        lines.append(f'          <mxGeometry x="{x - item_width / 2:.1f}" y="{y - item_height / 2:.1f}" width="{item_width:.1f}" height="{item_height:.1f}" as="geometry" />')
        lines.append("        </mxCell>")

    next_id = len(devices) + 2
    for index, link in enumerate(plan.get("links", [])):
        if not isinstance(link, dict):
            continue
        a = pick(link, ("a", "device_a", "from", "from_device"), f"a_{index}")
        b = pick(link, ("b", "device_b", "to", "to_device"), f"b_{index}")
        if a not in ids or b not in ids:
            continue
        label_text = svg_link_label(link) if options.link_labels else ""
        edge_color = palette["wireless_link"] if is_wireless_link(link) else palette["link"]
        dashed = "dashed=1;" if is_wireless_link(link) else ""
        edge_style = f"endArrow=none;html=1;rounded=0;{dashed}strokeColor={edge_color};fontColor={palette['label']};labelBackgroundColor={palette['label_back']};"
        lines.append(f'        <mxCell id="e{next_id}" value="{svg_text(label_text)}" style="{svg_text(edge_style)}" edge="1" parent="1" source="{ids[a]}" target="{ids[b]}">')
        lines.append('          <mxGeometry relative="1" as="geometry" />')
        lines.append("        </mxCell>")
        next_id += 1

    if not devices:
        lines.append('        <mxCell id="d2" value="empty topology" style="text;html=1;strokeColor=none;fillColor=none;" vertex="1" parent="1">')
        lines.append('          <mxGeometry x="80" y="80" width="160" height="40" as="geometry" />')
        lines.append("        </mxCell>")

    lines.extend(
        [
            "      </root>",
            "    </mxGraphModel>",
            "  </diagram>",
            "</mxfile>",
            "",
        ]
    )
    return "\n".join(lines)


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

    vlan_rows = []
    for config in plan.get("vlan_configs", []):
        if isinstance(config, dict):
            vlan_rows.append([
                pick(config, ("id", "vlan", "vlan_id")),
                pick(config, ("name",)),
                pick(config, ("network", "subnet")),
                pick(config, ("gateway",)),
                pick(config, ("description", "note")),
            ])
    if vlan_rows:
        lines.extend(["## VLAN Configs", ""])
        lines.extend(markdown_table(["VLAN", "Name", "Network", "Gateway", "Note"], vlan_rows))
        lines.append("")

    dhcp_pool_rows = []
    for pool in plan.get("dhcp_pools", []):
        if isinstance(pool, dict):
            dhcp_pool_rows.append([
                pick(pool, ("device", "router")),
                pick(pool, ("name", "pool")),
                pick(pool, ("vlan", "vlan_id")),
                pick(pool, ("network",)),
                pick(pool, ("mask", "subnet_mask", "netmask")),
                pick(pool, ("start", "start_ip", "first_ip")),
                pick(pool, ("end", "end_ip", "last_ip")),
                pick(pool, ("gateway", "default_router", "default_gateway")),
                pick(pool, ("dns", "dns_server")),
            ])
    if dhcp_pool_rows:
        lines.extend(["## Router DHCP Pools", ""])
        lines.extend(markdown_table(["Device", "Pool", "VLAN", "Network", "Mask", "Start", "End", "Gateway", "DNS"], dhcp_pool_rows))
        lines.append("")

    ap_rows = []
    for config in plan.get("ap_configs", []):
        if isinstance(config, dict):
            ap_rows.append([
                pick(config, ("name", "device", "ap")),
                pick(config, ("ssid",)),
                pick(config, ("mode",)),
                pick(config, ("note", "description")),
            ])
    if ap_rows:
        lines.extend(["## Wireless AP Configs", ""])
        lines.extend(markdown_table(["Name", "SSID", "Mode", "Note"], ap_rows))
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

    security_rows = []
    for policy in plan.get("security_policies", []):
        if isinstance(policy, dict):
            security_rows.append([
                pick(policy, ("device", "router", "name")),
                pick(policy, ("type", "kind")),
                pick(policy, ("interface", "port")),
                pick(policy, ("acl", "acl_id", "acl_number")),
                pick(policy, ("direction",)),
                pick(policy, ("summary", "description", "note")),
            ])
    if security_rows:
        lines.extend(["## Security Policies", ""])
        lines.extend(markdown_table(["Device", "Type", "Interface", "ACL", "Direction", "Summary"], security_rows))
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
            "ap_configs": len(plan.get("ap_configs", [])),
            "vlan_configs": len(plan.get("vlan_configs", [])),
            "dhcp_pools": len(plan.get("dhcp_pools", [])),
            "server_configs": len(plan.get("server_configs", [])),
            "security_policies": len(plan.get("security_policies", [])),
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
        "vlans": [
            {
                "id": pick(config, ("id", "vlan", "vlan_id")),
                "name": pick(config, ("name",)),
                "network": pick(config, ("network", "subnet")),
                "gateway": pick(config, ("gateway",)),
            }
            for config in plan.get("vlan_configs", [])
            if isinstance(config, dict)
        ],
        "dhcp_pools": [
            {
                "device": pick(pool, ("device", "router")),
                "name": pick(pool, ("name", "pool")),
                "vlan": pick(pool, ("vlan", "vlan_id")),
                "network": pick(pool, ("network",)),
                "mask": pick(pool, ("mask", "subnet_mask", "netmask")),
                "start": pick(pool, ("start", "start_ip", "first_ip")),
                "end": pick(pool, ("end", "end_ip", "last_ip")),
                "gateway": pick(pool, ("gateway", "default_router", "default_gateway")),
                "dns": pick(pool, ("dns", "dns_server")),
            }
            for pool in plan.get("dhcp_pools", [])
            if isinstance(pool, dict)
        ],
        "noted_links": noted_links,
        "wireless": {
            "aps": len(plan.get("ap_configs", [])),
            "ssids": sorted({pick(config, ("ssid",)) for config in plan.get("ap_configs", []) if isinstance(config, dict) and pick(config, ("ssid",))}),
            "links": len([link for link in plan.get("links", []) if isinstance(link, dict) and is_wireless_link(link)]),
        },
        "security_policies": [
            {
                "device": pick(policy, ("device", "router", "name")),
                "type": pick(policy, ("type", "kind")),
                "interface": pick(policy, ("interface", "port")),
                "acl": pick(policy, ("acl", "acl_id", "acl_number")),
                "direction": pick(policy, ("direction",)),
                "summary": pick(policy, ("summary", "description", "note")),
            }
            for policy in plan.get("security_policies", [])
            if isinstance(policy, dict)
        ],
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


def add_link_label_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--no-link-labels", action="store_false", dest="link_labels", default=True, help="hide link port/cable/VLAN labels")


def add_visual_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--theme", choices=RENDER_THEMES, default="light", help="diagram color theme")
    add_link_label_option(parser)
    parser.add_argument("--no-model-labels", action="store_false", dest="model_labels", default=True, help="hide device model labels")
    parser.add_argument("--group-by", choices=RENDER_GROUP_BY, default="none", help="draw visual group boxes by network, VLAN, site, category, or auto detection")


def render_options(args: argparse.Namespace) -> RenderOptions:
    return RenderOptions(
        theme=getattr(args, "theme", "light"),
        link_labels=getattr(args, "link_labels", True),
        model_labels=getattr(args, "model_labels", True),
        group_by=getattr(args, "group_by", "none"),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict-safety", action="store_true", help="treat safety warnings as failures")
    parser.add_argument("--allow-risky", action="store_true", help="allow known crash-risk or unverified plan items")
    sub = parser.add_subparsers(dest="cmd", required=True)

    mermaid_p = sub.add_parser("mermaid", help="render a plan as Mermaid flowchart")
    mermaid_p.add_argument("plan", type=Path)
    mermaid_p.add_argument("--direction", default="LR", choices=["LR", "TD", "TB", "RL", "BT"])
    mermaid_p.add_argument("--output", type=Path, help="write output to a file instead of stdout")
    add_link_label_option(mermaid_p)

    svg_p = sub.add_parser("svg", help="render a plan as an offline SVG topology diagram")
    svg_p.add_argument("plan", type=Path)
    svg_p.add_argument("--output", type=Path, help="write output to a file instead of stdout")
    add_visual_options(svg_p)

    drawio_p = sub.add_parser("drawio", help="render a plan as an importable diagrams.net/draw.io mxfile")
    drawio_p.add_argument("plan", type=Path)
    drawio_p.add_argument("--output", type=Path, help="write output to a file instead of stdout")
    add_visual_options(drawio_p)

    html_p = sub.add_parser("html", help="render a plan as a self-contained HTML review page")
    html_p.add_argument("plan", type=Path)
    html_p.add_argument("--output", type=Path, help="write output to a file instead of stdout")
    add_visual_options(html_p)

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
            emit(mermaid(plan, direction=args.direction, link_labels=args.link_labels), args.output)
            return 0
        if args.cmd == "svg":
            plan = _load_plan(args.plan)
            _enforce_plan_safety(plan, allow_risky=args.allow_risky, strict=args.strict_safety)
            emit(svg(plan, options=render_options(args)), args.output)
            return 0
        if args.cmd == "drawio":
            plan = _load_plan(args.plan)
            _enforce_plan_safety(plan, allow_risky=args.allow_risky, strict=args.strict_safety)
            emit(drawio(plan, options=render_options(args)), args.output)
            return 0
        if args.cmd == "html":
            plan = _load_plan(args.plan)
            _enforce_plan_safety(plan, allow_risky=args.allow_risky, strict=args.strict_safety)
            emit(html_report(plan, options=render_options(args)), args.output)
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
