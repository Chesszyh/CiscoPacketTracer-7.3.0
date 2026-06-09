#!/usr/bin/env python3
"""Render Packet Tracer topology JSON plans without contacting Packet Tracer."""

from __future__ import annotations

import argparse
import html
import ipaddress
import json
import math
import re
import shlex
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
RENDER_PRESETS = ("manual", "report")
BUNDLE_RENDER_FORMATS = (
    "mermaid",
    "svg",
    "drawio",
    "html",
    "markdown",
    "summary",
    "course-audit",
    "diagram-audit",
    "verification-json",
    "verification-md",
)
BUNDLE_DEFAULT_FORMATS = ("svg", "drawio", "html", "markdown", "summary")
BUNDLE_REPORT_FORMATS = ("svg", "drawio", "html", "markdown", "summary", "diagram-audit", "verification-json", "verification-md")
DIAGRAM_AUDIT_OVERLAP_X = 120.0
DIAGRAM_AUDIT_OVERLAP_Y = 90.0
DIAGRAM_AUDIT_MAX_WIDTH = 1800.0
DIAGRAM_AUDIT_MAX_HEIGHT = 1200.0
DIAGRAM_AUDIT_GROUPING_DEVICE_COUNT = 18
DIAGRAM_AUDIT_LABEL_LINK_COUNT = 24
BUNDLE_EXTENSIONS = {
    "mermaid": "mmd",
    "svg": "svg",
    "drawio": "drawio",
    "html": "html",
    "markdown": "md",
    "summary": "summary.json",
    "course-audit": "audit.json",
    "diagram-audit": "diagram-audit.json",
    "verification-json": "verification.json",
    "verification-md": "verification.md",
}


@dataclass(frozen=True)
class RenderOptions:
    theme: str = "light"
    link_labels: bool = True
    model_labels: bool = True
    group_by: str = "none"
    title: str = ""
    legend: bool = False
    preset: str = "manual"


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
        "ipv6": pick(config, ("ipv6", "ipv6_address", "ipv6_ip")),
        "ipv6_prefix": pick(config, ("ipv6_prefix", "prefix", "prefix_length")),
        "ipv6_gateway": pick(config, ("ipv6_gateway", "gateway6", "default_gateway6")),
        "ipv6_dns": pick(config, ("ipv6_dns", "dns6", "dns_server6")),
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


def ipv6_config_fields(config: dict[str, Any]) -> dict[str, str]:
    return {
        "name": pick(config, ("name", "device", "pc", "server")),
        "port": pick(config, ("port",), "FastEthernet0"),
        "ipv6": pick(config, ("ipv6", "ipv6_address", "address")),
        "prefix": pick(config, ("prefix", "ipv6_prefix", "prefix_length")),
        "gateway": pick(config, ("gateway", "ipv6_gateway", "gateway6", "default_gateway6")),
        "dns": pick(config, ("dns", "ipv6_dns", "dns6", "dns_server6")),
        "note": pick(config, ("note", "description")),
    }


def ipv6_config_entries(plan: dict[str, Any]) -> list[dict[str, Any]]:
    explicit = [config for config in plan.get("ipv6_configs", []) if isinstance(config, dict)]
    if explicit:
        return explicit
    return [config for config in plan.get("pc_configs", []) if isinstance(config, dict) and pick(config, ("ipv6", "ipv6_address", "ipv6_ip"))]


def ipv6_address_groups(plan: dict[str, Any]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str], dict[str, Any]] = {}
    for config in ipv6_config_entries(plan):
        fields = ipv6_config_fields(config)
        if not fields["ipv6"] or not fields["prefix"]:
            continue
        try:
            network = ipaddress.ip_network(f"{fields['ipv6']}/{fields['prefix']}", strict=False)
        except ValueError:
            continue
        if not isinstance(network, ipaddress.IPv6Network):
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


def _enabled_service(value: Any) -> bool:
    if isinstance(value, dict):
        enabled = value.get("enabled")
        if enabled is False:
            return False
        if enabled is None:
            return True
        return bool(enabled)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "enabled"}
    return value is True


def _host_fields(plan: dict[str, Any]) -> dict[str, dict[str, str]]:
    hosts: dict[str, dict[str, str]] = {}
    for config in plan.get("pc_configs", []):
        if not isinstance(config, dict):
            continue
        fields = ip_config_fields(config)
        name = fields["name"]
        if not name:
            continue
        hosts[name] = fields
    return hosts


def _device_category_map(plan: dict[str, Any]) -> dict[str, str]:
    categories: dict[str, str] = {}
    for index, device in enumerate(plan.get("devices", [])):
        if not isinstance(device, dict):
            continue
        name = pick(device, ("name", "id"), f"device_{index}")
        categories[name] = pick(device, ("category", "kind")).lower()
    return categories


def _server_config_map(plan: dict[str, Any]) -> dict[str, dict[str, Any]]:
    servers: dict[str, dict[str, Any]] = {}
    for config in plan.get("server_configs", []):
        if not isinstance(config, dict):
            continue
        name = server_name(config)
        if name:
            servers[name] = config
    return servers


def _command_string(command: list[str]) -> str:
    return " ".join(shlex.quote(str(part)) for part in command)


def _safe_check_id(prefix: str, *parts: Any, used: set[str]) -> str:
    raw = "_".join(str(part) for part in (prefix, *parts) if part not in (None, ""))
    value = node_id(raw).lower()
    base = value
    suffix = 2
    while value in used:
        value = f"{base}_{suffix}"
        suffix += 1
    used.add(value)
    return value


def _check(
    used: set[str],
    *,
    prefix: str,
    parts: tuple[Any, ...],
    category: str,
    title: str,
    purpose: str,
    manual: str,
    cli: list[str] | None = None,
    mcp_tool: str = "",
    mcp_arguments: dict[str, Any] | None = None,
    source: str = "",
    target: str = "",
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "id": _safe_check_id(prefix, *parts, used=used),
        "category": category,
        "title": title,
        "purpose": purpose,
        "source": source,
        "target": target,
        "manual": manual,
    }
    if cli:
        record["cli"] = {"command": cli, "shell": _command_string(cli)}
    if mcp_tool:
        args = dict(mcp_arguments or {})
        args.setdefault("dry_run", True)
        record["mcp"] = {"tool": mcp_tool, "arguments": args}
    return record


def _host_network(fields: dict[str, str]) -> str:
    if not fields.get("ip") or not fields.get("mask"):
        return ""
    try:
        return str(ipaddress.ip_network(f"{fields['ip']}/{fields['mask']}", strict=False))
    except ValueError:
        return ""


def _representative_hosts(plan: dict[str, Any], *, max_hosts: int) -> list[dict[str, str]]:
    hosts = _host_fields(plan)
    server_names = set(_server_config_map(plan))
    selected: list[dict[str, str]] = []
    selected_names: set[str] = set()
    for group in address_groups(plan):
        for name in group["hosts"]:
            if name in server_names or name in selected_names or name not in hosts:
                continue
            selected.append(hosts[name])
            selected_names.add(name)
            break
        if len(selected) >= max_hosts:
            return selected
    if not selected:
        for name, fields in hosts.items():
            if name in server_names or name in selected_names:
                continue
            selected.append(fields)
            selected_names.add(name)
            if len(selected) >= max_hosts:
                break
    if not selected:
        for name, fields in hosts.items():
            if name in selected_names:
                continue
            selected.append(fields)
            selected_names.add(name)
            if len(selected) >= max_hosts:
                break
    return selected


def _server_ip_records(plan: dict[str, Any], *, max_targets: int) -> list[dict[str, str]]:
    hosts = _host_fields(plan)
    server_names = set(_server_config_map(plan))
    records = [hosts[name] for name in hosts if name in server_names and hosts[name].get("ip")]
    if not records:
        categories = _device_category_map(plan)
        records = [fields for name, fields in hosts.items() if categories.get(name) == "server" and fields.get("ip")]
    return records[:max_targets]


def _ipv6_host_fields(plan: dict[str, Any]) -> dict[str, dict[str, str]]:
    hosts: dict[str, dict[str, str]] = {}
    for config in ipv6_config_entries(plan):
        fields = ipv6_config_fields(config)
        name = fields["name"]
        if name and fields["ipv6"]:
            hosts[name] = fields
    return hosts


def _server_ipv6_records(plan: dict[str, Any], *, max_targets: int) -> list[dict[str, str]]:
    hosts = _ipv6_host_fields(plan)
    server_names = set(_server_config_map(plan))
    records = [hosts[name] for name in hosts if name in server_names and hosts[name].get("ipv6")]
    if not records:
        categories = _device_category_map(plan)
        records = [fields for name, fields in hosts.items() if categories.get(name) == "server" and fields.get("ipv6")]
    return records[:max_targets]


def _ios_commands(config: dict[str, Any]) -> list[str]:
    raw = config.get("commands", config.get("cmds", config.get("config", config.get("cli", []))))
    if isinstance(raw, list):
        return [str(item) for item in raw]
    if isinstance(raw, str):
        return [line.strip() for line in raw.splitlines() if line.strip()]
    return []


def _ios_show_commands(commands: list[str]) -> list[str]:
    lowered = "\n".join(commands).lower()
    show = ["show ip interface brief", "show running-config | section hostname"]
    if "ipv6 unicast-routing" in lowered or re.search(r"(?m)^\s*ipv6\s+(address|enable)\b", lowered):
        show.append("show ipv6 interface brief")
    if "router ospf" in lowered:
        show.extend(["show ip ospf neighbor", "show ip route ospf", "show ip protocols"])
    if "ipv6 router ospf" in lowered or re.search(r"(?m)^\s*ipv6\s+ospf\s+\S+\s+area\s+", lowered):
        show.extend(["show ipv6 ospf neighbor", "show ipv6 route ospf"])
    if "router eigrp" in lowered:
        show.extend(["show ip eigrp neighbors", "show ip route eigrp", "show ip protocols"])
    if "router bgp" in lowered:
        show.extend(["show ip bgp summary", "show ip route bgp", "show ip protocols"])
    if "router rip" in lowered:
        show.extend(["show ip route rip", "show ip protocols"])
    if "ipv6 router rip" in lowered or re.search(r"(?m)^\s*ipv6\s+rip\s+\S+\s+enable", lowered):
        show.append("show ipv6 route rip")
    if re.search(r"(?m)^\s*ip route\s+", lowered):
        show.append("show ip route static")
    if re.search(r"(?m)^\s*ipv6 route\s+", lowered):
        show.append("show ipv6 route static")
    if "standby " in lowered:
        show.append("show standby brief")
    if "spanning-tree" in lowered:
        show.extend(["show spanning-tree summary", "show spanning-tree root"])
    if "channel-group" in lowered or "port-channel" in lowered:
        show.append("show etherchannel summary")
    if "ip nat " in lowered:
        show.extend(["show ip nat translations", "show ip nat statistics"])
    if "ip access-group" in lowered or re.search(r"(?m)^\s*access-list\s+", lowered):
        show.append("show access-lists")
    if "ip dhcp pool" in lowered:
        show.extend(["show ip dhcp pool", "show ip dhcp binding"])
    if "logging host" in lowered:
        show.append("show logging")
    if "ntp server" in lowered:
        show.append("show ntp associations")
    if "snmp-server" in lowered:
        show.append("show snmp")
    if "ip ssh " in lowered or "crypto key generate rsa" in lowered:
        show.append("show ip ssh")
    if re.search(r"(?m)^\s*username\s+", lowered):
        show.append("show running-config | include ^username")
    if re.search(r"(?m)^\s*enable\s+(secret|password)\s+", lowered):
        show.append("show running-config | include enable")
    if "line console" in lowered:
        show.append("show running-config | section line con")
    if "line vty" in lowered:
        show.append("show running-config | section line vty")
    deduped: list[str] = []
    for command in show:
        if command not in deduped:
            deduped.append(command)
    return deduped


def _service_names(config: dict[str, Any]) -> list[str]:
    names = []
    for service in ("http", "dns", "ftp", "tftp", "email", "ntp", "syslog", "dhcp"):
        if _enabled_service(config.get(service)):
            names.append(service)
    return names


def verification_plan(plan: dict[str, Any], *, max_hosts: int = 12, max_service_targets: int = 8) -> dict[str, Any]:
    used: set[str] = set()
    checks: list[dict[str, Any]] = []
    hosts = _host_fields(plan)
    ipv6_hosts = _ipv6_host_fields(plan)
    representative_hosts = _representative_hosts(plan, max_hosts=max_hosts)
    server_ips = _server_ip_records(plan, max_targets=max_service_targets)
    server_ipv6s = _server_ipv6_records(plan, max_targets=max_service_targets)
    server_configs = _server_config_map(plan)
    sample_client = representative_hosts[0] if representative_hosts else next(iter(hosts.values()), {})

    for host in representative_hosts:
        name = host["name"]
        gateway = host.get("gateway")
        dns = host.get("dns")
        if host.get("dhcp") == "yes":
            network = _host_network(host)
            cli = ["pt-reverse/bin/pt730-pc", "dhcp", name, "--port", host.get("port") or "FastEthernet0", "--renew", "--wait", "10"]
            args: dict[str, Any] = {"device": name, "port": host.get("port") or "FastEthernet0", "renew": True, "wait": 10}
            if network:
                cli.extend(["--expect-network", network])
                args["expect_network"] = network
            checks.append(
                _check(
                    used,
                    prefix="dhcp",
                    parts=(name,),
                    category="dhcp",
                    title=f"Verify DHCP lease on {name}",
                    purpose="Confirm the DHCP client receives a usable address before connectivity checks.",
                    manual=f"Open {name} Desktop > IP Configuration, select DHCP, then confirm a non-zero IP address.",
                    cli=cli,
                    mcp_tool="pt730_live_pc_dhcp",
                    mcp_arguments=args,
                    source=name,
                    target=network,
                )
            )
        if gateway:
            checks.append(
                _check(
                    used,
                    prefix="ping_gateway",
                    parts=(name, gateway),
                    category="connectivity",
                    title=f"Ping default gateway from {name}",
                    purpose="Confirm host access VLAN/subnet gateway reachability.",
                    manual=f"On {name}, run: ping {gateway}",
                    cli=["pt-reverse/bin/pt730-term", name, "--cmd", f"ping {gateway}", "--wait", "8", "--expect", r"Lost = 0 \(0% loss\)"],
                    mcp_tool="pt730_live_term",
                    mcp_arguments={"device": name, "commands": [f"ping {gateway}"], "wait": 8, "expect": r"Lost = 0 \(0% loss\)"},
                    source=name,
                    target=gateway,
                )
            )
        if dns and dns != gateway:
            checks.append(
                _check(
                    used,
                    prefix="ping_dns",
                    parts=(name, dns),
                    category="connectivity",
                    title=f"Ping DNS server from {name}",
                    purpose="Confirm the host can reach its configured DNS server.",
                    manual=f"On {name}, run: ping {dns}",
                    cli=["pt-reverse/bin/pt730-term", name, "--cmd", f"ping {dns}", "--wait", "8", "--expect", r"Lost = 0 \(0% loss\)"],
                    mcp_tool="pt730_live_term",
                    mcp_arguments={"device": name, "commands": [f"ping {dns}"], "wait": 8, "expect": r"Lost = 0 \(0% loss\)"},
                    source=name,
                    target=dns,
                )
            )
        ipv6_host = ipv6_hosts.get(name, {})
        ipv6_gateway = ipv6_host.get("gateway")
        if ipv6_gateway:
            checks.append(
                _check(
                    used,
                    prefix="ping_ipv6_gateway",
                    parts=(name, ipv6_gateway),
                    category="ipv6",
                    title=f"Ping IPv6 default gateway from {name}",
                    purpose="Confirm dual-stack host IPv6 gateway reachability.",
                    manual=f"On {name}, run: ping {ipv6_gateway}",
                    cli=["pt-reverse/bin/pt730-term", name, "--cmd", f"ping {ipv6_gateway}", "--wait", "8", "--expect", r"Lost = 0 \(0% loss\)"],
                    mcp_tool="pt730_live_term",
                    mcp_arguments={"device": name, "commands": [f"ping {ipv6_gateway}"], "wait": 8, "expect": r"Lost = 0 \(0% loss\)"},
                    source=name,
                    target=ipv6_gateway,
                )
            )
        for server in server_ips:
            if server.get("ip") and server["ip"] != host.get("ip"):
                checks.append(
                    _check(
                        used,
                        prefix="ping_server",
                        parts=(name, server["name"], server["ip"]),
                        category="connectivity",
                        title=f"Ping {server['name']} from {name}",
                        purpose="Confirm representative host-to-server reachability.",
                        manual=f"On {name}, run: ping {server['ip']}",
                        cli=["pt-reverse/bin/pt730-term", name, "--cmd", f"ping {server['ip']}", "--wait", "8", "--expect", r"Lost = 0 \(0% loss\)"],
                        mcp_tool="pt730_live_term",
                        mcp_arguments={"device": name, "commands": [f"ping {server['ip']}"], "wait": 8, "expect": r"Lost = 0 \(0% loss\)"},
                        source=name,
                        target=server["ip"],
                    )
                )
        for server in server_ipv6s:
            if server.get("ipv6") and server["ipv6"] != ipv6_host.get("ipv6"):
                checks.append(
                    _check(
                        used,
                        prefix="ping_ipv6_server",
                        parts=(name, server["name"], server["ipv6"]),
                        category="ipv6",
                        title=f"Ping IPv6 server {server['name']} from {name}",
                        purpose="Confirm representative host-to-server IPv6 reachability.",
                        manual=f"On {name}, run: ping {server['ipv6']}",
                        cli=["pt-reverse/bin/pt730-term", name, "--cmd", f"ping {server['ipv6']}", "--wait", "8", "--expect", r"Lost = 0 \(0% loss\)"],
                        mcp_tool="pt730_live_term",
                        mcp_arguments={"device": name, "commands": [f"ping {server['ipv6']}"], "wait": 8, "expect": r"Lost = 0 \(0% loss\)"},
                        source=name,
                        target=server["ipv6"],
                    )
                )

    for config in plan.get("ios_configs", []):
        if not isinstance(config, dict):
            continue
        device = pick(config, ("device", "name", "router", "switch"))
        if not device:
            continue
        show_commands = _ios_show_commands(_ios_commands(config))
        checks.append(
            _check(
                used,
                prefix="ios_show",
                parts=(device,),
                category="ios",
                title=f"Inspect IOS state on {device}",
                purpose="Confirm generated IOS configuration is present and routing/switching features are active.",
                manual=f"On {device} CLI, run: " + "; ".join(show_commands),
                cli=["pt-reverse/bin/pt730-ios", device, *sum((["--cmd", command] for command in show_commands), []), "--output", "tail"],
                mcp_tool="pt730_live_ios",
                mcp_arguments={"device": device, "commands": show_commands},
                source=device,
            )
        )

    for name, config in list(server_configs.items())[:max_service_targets]:
        services = _service_names(config)
        host = hosts.get(name, {})
        server_ip = host.get("ip", "")
        if services:
            checks.append(
                _check(
                    used,
                    prefix="server_inspect",
                    parts=(name,),
                    category="services",
                    title=f"Inspect services on {name}",
                    purpose="Confirm configured Server-PT services are enabled and visible through the bridge.",
                    manual=f"Open {name} Services tab and verify: {', '.join(service.upper() for service in services)}.",
                    cli=["pt-reverse/bin/pt730-server", "inspect", name],
                    mcp_tool="pt730_live_server_inspect",
                    mcp_arguments={"device": name},
                    source=name,
                    target=", ".join(services),
                )
            )
        if "http" in services and sample_client and server_ip:
            checks.append(
                _check(
                    used,
                    prefix="http_pdu",
                    parts=(sample_client.get("name"), name),
                    category="services",
                    title=f"HTTP reachability to {name}",
                    purpose="Use a simple PDU as a lightweight service-path smoke check before browser testing.",
                    manual=f"From {sample_client.get('name')}, open a browser to http://{server_ip}/ or send a simple PDU to {name}.",
                    cli=["pt-reverse/bin/pt730-sim", "simple-pdu", sample_client.get("name", ""), name],
                    mcp_tool="pt730_live_sim",
                    mcp_arguments={"action": "simple_pdu", "source": sample_client.get("name", ""), "target": name},
                    source=sample_client.get("name", ""),
                    target=server_ip,
                )
            )
        dns = config.get("dns")
        if isinstance(dns, dict) and sample_client:
            for record in as_list(dns.get("records"))[:max_service_targets]:
                if not isinstance(record, dict):
                    continue
                hostname = pick(record, ("name", "host", "domain"))
                if not hostname:
                    continue
                checks.append(
                    _check(
                        used,
                        prefix="dns_lookup",
                        parts=(sample_client.get("name"), hostname),
                        category="services",
                        title=f"Resolve and ping {hostname}",
                        purpose="Confirm DNS record resolution and routed reachability from a representative client.",
                        manual=f"On {sample_client.get('name')}, run: ping {hostname}",
                        cli=["pt-reverse/bin/pt730-term", sample_client.get("name", ""), "--cmd", f"ping {hostname}", "--wait", "8", "--expect", r"Lost = 0 \(0% loss\)"],
                        mcp_tool="pt730_live_term",
                        mcp_arguments={"device": sample_client.get("name", ""), "commands": [f"ping {hostname}"], "wait": 8, "expect": r"Lost = 0 \(0% loss\)"},
                        source=sample_client.get("name", ""),
                        target=hostname,
                    )
                )
        ftp = config.get("ftp")
        if isinstance(ftp, dict) and sample_client and server_ip:
            for account in as_list(ftp.get("accounts", ftp.get("users")))[:1]:
                if not isinstance(account, dict):
                    continue
                username = pick(account, ("username", "user", "name"))
                password = pick(account, ("password", "pass"), "packet")
                if not username:
                    continue
                checks.append(
                    _check(
                        used,
                        prefix="ftp_login",
                        parts=(sample_client.get("name"), name, username),
                        category="services",
                        title=f"FTP login to {name}",
                        purpose="Confirm an FTP account can authenticate and list files from a representative client.",
                        manual=f"On {sample_client.get('name')}, run: ftp {server_ip}, login as {username}, then run dir.",
                        cli=["pt-reverse/bin/pt730-ftp", sample_client.get("name", ""), server_ip, "--username", username, "--password", password, "--cmd", "dir", "--expect", "ftp>"],
                        mcp_tool="pt730_live_ftp",
                        mcp_arguments={"client": sample_client.get("name", ""), "server": server_ip, "username": username, "password": password, "commands": ["dir"], "expect": "ftp>"},
                        source=sample_client.get("name", ""),
                        target=server_ip,
                    )
                )

    return {
        "kind": "pt730-verification-plan",
        "packet_tracer_version": "7.3.0",
        "ok": True,
        "limits": {"max_hosts": max_hosts, "max_service_targets": max_service_targets},
        "counts": {
            "checks": len(checks),
            "connectivity": len([check for check in checks if check["category"] == "connectivity"]),
            "ios": len([check for check in checks if check["category"] == "ios"]),
            "services": len([check for check in checks if check["category"] == "services"]),
            "dhcp": len([check for check in checks if check["category"] == "dhcp"]),
            "ipv6": len([check for check in checks if check["category"] == "ipv6"]),
            "representative_hosts": len(representative_hosts),
            "server_targets": len(server_ips),
        },
        "notes": [
            "This plan is offline guidance; commands contact live Packet Tracer only when an operator executes them.",
            "MCP arguments include dry_run=true by default so an agent can preview before allow_live=true execution.",
            "Run checks sequentially because PT 7.3.0 live terminal automation is crash-prone under concurrent access.",
        ],
        "checks": checks,
    }


def verification_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = ["# Packet Tracer Verification Plan", ""]
    counts = report.get("counts") if isinstance(report.get("counts"), dict) else {}
    lines.extend(["## Summary", ""])
    lines.extend(markdown_table(["Field", "Value"], [[key, value] for key, value in counts.items()]))
    lines.append("")
    notes = report.get("notes")
    if isinstance(notes, list) and notes:
        lines.extend(["## Notes", ""])
        for note in notes:
            lines.append(f"- {note}")
        lines.append("")

    checks = report.get("checks") if isinstance(report.get("checks"), list) else []
    for category, title in (("dhcp", "DHCP Checks"), ("connectivity", "Connectivity Checks"), ("ios", "IOS Checks"), ("services", "Service Checks")):
        rows = []
        for check in checks:
            if not isinstance(check, dict) or check.get("category") != category:
                continue
            cli = check.get("cli") if isinstance(check.get("cli"), dict) else {}
            mcp = check.get("mcp") if isinstance(check.get("mcp"), dict) else {}
            rows.append([
                check.get("id", ""),
                check.get("title", ""),
                check.get("source", ""),
                check.get("target", ""),
                check.get("manual", ""),
                cli.get("shell", ""),
                mcp.get("tool", ""),
            ])
        if rows:
            lines.extend([f"## {title}", ""])
            lines.extend(markdown_table(["ID", "Check", "Source", "Target", "Manual", "CLI", "MCP Tool"], rows))
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


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


def shifted_positions(positions: dict[str, tuple[float, float]], *, dy: float) -> dict[str, tuple[float, float]]:
    if dy == 0:
        return positions
    return {name: (x, y + dy) for name, (x, y) in positions.items()}


def shifted_group_boxes(boxes: list[dict[str, Any]], *, dy: float) -> list[dict[str, Any]]:
    if dy == 0:
        return boxes
    return [{**box, "y": box["y"] + dy} for box in boxes]


def visible_title_height(options: RenderOptions) -> float:
    return 58.0 if options.title else 0.0


def present_device_kinds(devices: list[dict[str, Any]]) -> list[str]:
    preferred = ["router", "switch", "server", "pc", "wireless", "device"]
    present = {svg_device_kind(device) for device in devices}
    return [kind for kind in preferred if kind in present]


def legend_items(plan: dict[str, Any], devices: list[dict[str, Any]]) -> list[dict[str, str]]:
    labels = {
        "router": "Router",
        "switch": "Switch",
        "server": "Server",
        "pc": "PC/Laptop",
        "wireless": "Wireless AP",
        "device": "Other Device",
    }
    items = [{"kind": kind, "label": labels[kind], "type": "device"} for kind in present_device_kinds(devices)]
    if any(isinstance(link, dict) and is_wireless_link(link) for link in plan.get("links", [])):
        items.append({"kind": "wireless-link", "label": "Wireless Link", "type": "link"})
    return items


def legend_height(plan: dict[str, Any], devices: list[dict[str, Any]], options: RenderOptions) -> float:
    if not options.legend or not legend_items(plan, devices):
        return 0.0
    return 78.0


def legend_required_width(plan: dict[str, Any], devices: list[dict[str, Any]], options: RenderOptions) -> float:
    if not options.legend:
        return 0.0
    items = legend_items(plan, devices)
    if not items:
        return 0.0
    width = 110.0
    for item in items:
        width += max(112.0, len(item["label"]) * 7.2 + 46.0)
    return width + 24.0


def svg_kind_colors(kind: str, palette: dict[str, str]) -> tuple[str, str]:
    if kind == "router":
        return palette["router_fill"], palette["router_stroke"]
    if kind == "switch":
        return palette["switch_fill"], palette["switch_stroke"]
    if kind == "server":
        return palette["server_fill"], palette["server_stroke"]
    if kind == "pc":
        return palette["pc_fill"], palette["pc_stroke"]
    if kind == "wireless":
        return palette["wireless_fill"], palette["wireless_stroke"]
    return palette["device_fill"], palette["device_stroke"]


def svg_legend(plan: dict[str, Any], devices: list[dict[str, Any]], *, options: RenderOptions, width: float, y: float, palette: dict[str, str]) -> list[str]:
    items = legend_items(plan, devices)
    if not options.legend or not items:
        return []
    lines = [
        f'  <g class="legend" transform="translate(24 {y:.1f})">',
        f'    <rect class="legend-panel" x="0" y="0" width="{max(280.0, width - 48.0):.1f}" height="58" rx="8" />',
        '    <text class="legend-title" x="14" y="22">Legend</text>',
    ]
    x = 86.0
    for item in items:
        kind = item["kind"]
        if item["type"] == "link":
            lines.append(f'    <line class="legend-link wireless-link" x1="{x:.1f}" y1="38" x2="{x + 24:.1f}" y2="38" />')
            lines.append(f'    <text class="legend-label" x="{x + 32:.1f}" y="42">{svg_text(item["label"])}</text>')
        else:
            fill, stroke = svg_kind_colors(kind, palette)
            lines.append(f'    <rect class="legend-marker" x="{x:.1f}" y="29" width="24" height="16" rx="4" fill="{fill}" stroke="{stroke}" />')
            lines.append(f'    <text class="legend-label" x="{x + 32:.1f}" y="42">{svg_text(item["label"])}</text>')
        x += max(112.0, len(item["label"]) * 7.2 + 46.0)
    lines.append("  </g>")
    return lines


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
    title_height = visible_title_height(options)
    legend_extra_height = legend_height(plan, devices, options)
    positions = shifted_positions(positions, dy=title_height)
    group_boxes = shifted_group_boxes(group_boxes, dy=title_height)
    height += title_height + legend_extra_height
    if options.title or options.legend:
        width = max(width, 520.0)
    width = max(width, legend_required_width(plan, devices, options))
    for box in group_boxes:
        width = max(width, box["x"] + box["width"] + 12.0)
        height = max(height, box["y"] + box["height"] + 12.0)
    palette = render_palette(options.theme)
    title_text = options.title or "Packet Tracer topology"
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="{height:.0f}" viewBox="0 0 {width:.0f} {height:.0f}" role="img" aria-labelledby="title desc">',
        f'  <title id="title">{svg_text(title_text)}</title>',
        "  <desc id=\"desc\">Offline-rendered Packet Tracer 7.3.0 topology diagram.</desc>",
        "  <style>",
        f"    svg {{ background: {palette['bg']}; font-family: Inter, Segoe UI, Arial, sans-serif; }}",
        f"    .diagram-title {{ fill: {palette['text']}; font-size: 22px; font-weight: 800; }}",
        f"    .diagram-subtitle {{ fill: {palette['muted']}; font-size: 12px; }}",
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
        f"    .legend-panel {{ fill: {palette['panel_bg']}; stroke: {palette['panel_border']}; stroke-width: 1.2; }}",
        f"    .legend-title {{ fill: {palette['text']}; font-size: 12px; font-weight: 800; text-transform: uppercase; letter-spacing: 0; }}",
        f"    .legend-label {{ fill: {palette['muted']}; font-size: 12px; }}",
        "    .legend-marker { stroke-width: 1.8; }",
        "    .legend-link { stroke-width: 2.4; stroke-linecap: round; }",
        f"    .router ellipse {{ fill: {palette['router_fill']}; stroke: {palette['router_stroke']}; }} .router path {{ stroke: {palette['router_stroke']}; }}",
        f"    .switch rect {{ fill: {palette['switch_fill']}; stroke: {palette['switch_stroke']}; }} .switch path {{ stroke: {palette['switch_stroke']}; }}",
        f"    .server rect {{ fill: {palette['server_fill']}; stroke: {palette['server_stroke']}; }} .server path {{ stroke: {palette['server_stroke']}; }}",
        f"    .pc rect {{ fill: {palette['pc_fill']}; stroke: {palette['pc_stroke']}; }} .pc path {{ stroke: {palette['pc_stroke']}; }}",
        f"    .wireless rect, .wireless circle {{ fill: {palette['wireless_fill']}; stroke: {palette['wireless_stroke']}; }} .wireless path {{ stroke: {palette['wireless_stroke']}; }}",
        f"    .wireless-link {{ stroke: {palette['wireless_link']}; stroke-dasharray: 7 7; }}",
        f"    .device:not(.router):not(.switch):not(.server):not(.pc):not(.wireless) rect {{ fill: {palette['device_fill']}; stroke: {palette['device_stroke']}; }}",
        "  </style>",
    ]

    if options.title:
        lines.append(f'  <text class="diagram-title" x="24" y="32">{svg_text(options.title)}</text>')
        lines.append('  <text class="diagram-subtitle" x="24" y="50">Packet Tracer 7.3.0 offline topology</text>')

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
        lines.append(f'  <text class="device-name" x="160" y="{110 + title_height:.1f}">empty topology</text>')

    if legend_extra_height:
        lines.extend(svg_legend(plan, devices, options=options, width=width, y=height - legend_extra_height + 12.0, palette=palette))

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
    title_text = options.title or "Packet Tracer Topology Plan"
    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="en">',
            "<head>",
            '  <meta charset="utf-8">',
            '  <meta name="viewport" content="width=device-width, initial-scale=1">',
            f"  <title>{svg_text(title_text)}</title>",
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
            f"    <h1>{svg_text(title_text)}</h1>",
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
    title_height = 70.0 if options.title else 0.0
    legend_extra_height = 92.0 if options.legend and legend_items(plan, devices) else 0.0
    positions = shifted_positions(positions, dy=title_height)
    group_boxes = shifted_group_boxes(group_boxes, dy=title_height)
    height += title_height + legend_extra_height
    if options.title or options.legend:
        width = max(width, 540.0)
    width = max(width, legend_required_width(plan, devices, options))
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

    if options.title:
        title_style = f"text;html=1;strokeColor=none;fillColor=none;fontColor={palette['text']};fontSize=22;fontStyle=1;align=left;verticalAlign=middle;"
        subtitle_style = f"text;html=1;strokeColor=none;fillColor=none;fontColor={palette['muted']};fontSize=12;align=left;verticalAlign=middle;"
        lines.append(f'        <mxCell id="title" value="{svg_text(options.title)}" style="{svg_text(title_style)}" vertex="1" parent="1">')
        lines.append('          <mxGeometry x="24" y="18" width="460" height="28" as="geometry" />')
        lines.append("        </mxCell>")
        lines.append(f'        <mxCell id="subtitle" value="Packet Tracer 7.3.0 offline topology" style="{svg_text(subtitle_style)}" vertex="1" parent="1">')
        lines.append('          <mxGeometry x="24" y="46" width="360" height="18" as="geometry" />')
        lines.append("        </mxCell>")

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

    legend_y = height - legend_extra_height + 18.0 if legend_extra_height else 0.0
    if options.legend and legend_extra_height:
        panel_style = f"rounded=1;whiteSpace=wrap;html=1;fillColor={palette['panel_bg']};strokeColor={palette['panel_border']};fontColor={palette['text']};fontStyle=1;align=left;verticalAlign=top;spacingLeft=10;spacingTop=6;"
        lines.append(f'        <mxCell id="legend-panel" value="Legend" style="{svg_text(panel_style)}" vertex="1" parent="1">')
        lines.append(f'          <mxGeometry x="24" y="{legend_y:.1f}" width="{max(300.0, width - 48.0):.1f}" height="64" as="geometry" />')
        lines.append("        </mxCell>")
        legend_x = 104.0
        for index, item in enumerate(legend_items(plan, devices)):
            label_text = item["label"]
            if item["type"] == "link":
                line_style = f"shape=line;html=1;rounded=0;dashed=1;strokeColor={palette['wireless_link']};strokeWidth=2;"
                lines.append(f'        <mxCell id="legend-link-{index}" value="" style="{svg_text(line_style)}" vertex="1" parent="1">')
                lines.append(f'          <mxGeometry x="{legend_x:.1f}" y="{legend_y + 36:.1f}" width="28" height="4" as="geometry" />')
                lines.append("        </mxCell>")
            else:
                fill, stroke = svg_kind_colors(item["kind"], palette)
                marker_style = f"rounded=1;whiteSpace=wrap;html=1;fillColor={fill};strokeColor={stroke};"
                lines.append(f'        <mxCell id="legend-marker-{index}" value="" style="{svg_text(marker_style)}" vertex="1" parent="1">')
                lines.append(f'          <mxGeometry x="{legend_x:.1f}" y="{legend_y + 28:.1f}" width="24" height="16" as="geometry" />')
                lines.append("        </mxCell>")
            label_style = f"text;html=1;strokeColor=none;fillColor=none;fontColor={palette['muted']};fontSize=12;align=left;verticalAlign=middle;"
            lines.append(f'        <mxCell id="legend-label-{index}" value="{svg_text(label_text)}" style="{svg_text(label_style)}" vertex="1" parent="1">')
            lines.append(f'          <mxGeometry x="{legend_x + 32:.1f}" y="{legend_y + 25:.1f}" width="{max(80.0, len(label_text) * 7.2):.1f}" height="22" as="geometry" />')
            lines.append("        </mxCell>")
            legend_x += max(112.0, len(label_text) * 7.2 + 46.0)

    if not devices:
        lines.append('        <mxCell id="d2" value="empty topology" style="text;html=1;strokeColor=none;fillColor=none;" vertex="1" parent="1">')
        lines.append(f'          <mxGeometry x="80" y="{80 + title_height:.1f}" width="160" height="40" as="geometry" />')
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

    ipv6_rows = []
    for config in ipv6_config_entries(plan):
        fields = ipv6_config_fields(config)
        ipv6_rows.append([fields["name"], fields["port"], fields["ipv6"], fields["prefix"], fields["gateway"], fields["dns"], fields["note"]])
    if ipv6_rows:
        lines.extend(["## IPv6 Host Configs", ""])
        lines.extend(markdown_table(["Name", "Port", "IPv6", "Prefix", "Gateway", "DNS", "Note"], ipv6_rows))
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

    ipv6_address_rows = []
    for group in ipv6_address_groups(plan):
        hosts = group["hosts"]
        shown_hosts = ", ".join(hosts[:6])
        if len(hosts) > 6:
            shown_hosts += f", ... (+{len(hosts) - 6})"
        ipv6_address_rows.append([group["network"], group["gateway"], group["dns"], len(hosts), shown_hosts])
    if ipv6_address_rows:
        lines.extend(["## IPv6 Address Summary", ""])
        lines.extend(markdown_table(["Prefix", "Gateway", "DNS", "Configured Hosts", "Sample Hosts"], ipv6_address_rows))
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
            "ipv6_configs": len(ipv6_config_entries(plan)),
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
        "ipv6_address_groups": [
            {
                "network": group["network"],
                "gateway": group["gateway"],
                "dns": group["dns"],
                "configured_hosts": len(group["hosts"]),
                "hosts": group["hosts"],
            }
            for group in ipv6_address_groups(plan)
        ],
        "ipv6_configs": [
            ipv6_config_fields(config)
            for config in ipv6_config_entries(plan)
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


def _rounded(value: float) -> float | int:
    rounded = round(value, 1)
    if rounded.is_integer():
        return int(rounded)
    return rounded


def _coordinate_bounds(positions: dict[str, tuple[float, float]]) -> dict[str, Any] | None:
    if not positions:
        return None
    xs = [x for x, _ in positions.values()]
    ys = [y for _, y in positions.values()]
    min_x = min(xs)
    min_y = min(ys)
    max_x = max(xs)
    max_y = max(ys)
    return {
        "min_x": _rounded(min_x),
        "min_y": _rounded(min_y),
        "max_x": _rounded(max_x),
        "max_y": _rounded(max_y),
        "width": _rounded(max_x - min_x),
        "height": _rounded(max_y - min_y),
    }


def _link_endpoint_name(link: dict[str, Any], aliases: tuple[str, ...]) -> str:
    return pick(link, aliases)


def diagram_audit(plan: dict[str, Any], *, options: RenderOptions = RenderOptions()) -> tuple[dict[str, Any], int]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    advice: list[str] = []
    explicit_devices = [device for device in plan.get("devices", []) if isinstance(device, dict)]
    links = [link for link in plan.get("links", []) if isinstance(link, dict)]
    devices = svg_devices(plan)
    device_names = [pick(device, ("name", "id"), f"device_{index}") for index, device in enumerate(devices)]
    explicit_names = {
        pick(device, ("name", "id"), f"device_{index}")
        for index, device in enumerate(explicit_devices)
    }
    implicit_names = [name for name in device_names if name not in explicit_names]

    if not explicit_devices and not links:
        errors.append({"where": "devices", "message": "empty topology has no devices or links"})

    explicit_positions: dict[str, tuple[float, float]] = {}
    missing_coordinates: list[str] = []
    for index, device in enumerate(devices):
        name = pick(device, ("name", "id"), f"device_{index}")
        x = as_float(device.get("x"))
        y = as_float(device.get("y"))
        if x is None or y is None:
            missing_coordinates.append(name)
        else:
            explicit_positions[name] = (x, y)

    rendered_positions, rendered_width, rendered_height = svg_positions(devices)
    overlaps: list[dict[str, Any]] = []
    for left_index, left_name in enumerate(device_names):
        if left_name not in rendered_positions:
            continue
        x1, y1 = rendered_positions[left_name]
        for right_name in device_names[left_index + 1 :]:
            if right_name not in rendered_positions:
                continue
            x2, y2 = rendered_positions[right_name]
            dx = abs(x1 - x2)
            dy = abs(y1 - y2)
            if dx < DIAGRAM_AUDIT_OVERLAP_X and dy < DIAGRAM_AUDIT_OVERLAP_Y:
                overlaps.append(
                    {
                        "a": left_name,
                        "b": right_name,
                        "dx": _rounded(dx),
                        "dy": _rounded(dy),
                        "threshold_x": int(DIAGRAM_AUDIT_OVERLAP_X),
                        "threshold_y": int(DIAGRAM_AUDIT_OVERLAP_Y),
                    }
                )

    malformed_links: list[dict[str, Any]] = []
    graph: dict[str, set[str]] = {name: set() for name in device_names}
    for index, link in enumerate(links):
        a = _link_endpoint_name(link, ("a", "device_a", "from", "from_device"))
        b = _link_endpoint_name(link, ("b", "device_b", "to", "to_device"))
        if not a or not b:
            malformed_links.append({"index": index, "a": a, "b": b})
            continue
        graph.setdefault(a, set()).add(b)
        graph.setdefault(b, set()).add(a)

    components: list[list[str]] = []
    visited: set[str] = set()
    order = {name: index for index, name in enumerate(graph)}
    for name in graph:
        if name in visited:
            continue
        stack = [name]
        component: list[str] = []
        visited.add(name)
        while stack:
            current = stack.pop()
            component.append(current)
            for neighbor in sorted(graph[current], key=lambda value: order.get(value, len(order))):
                if neighbor not in visited:
                    visited.add(neighbor)
                    stack.append(neighbor)
        components.append(sorted(component, key=lambda value: order.get(value, len(order))))

    if len(devices) > 1 and not links:
        warnings.append({"where": "links", "message": "topology has multiple devices but no links", "devices": len(devices)})
        advice.append("add links between devices or split the plan into separate diagrams")
    if missing_coordinates:
        warnings.append(
            {
                "where": "devices",
                "message": "some devices have no explicit x/y coordinates; renderer will use deterministic fallback positions",
                "missing": missing_coordinates,
            }
        )
        advice.append("run pt730-layout or add x/y coordinates before final SVG/draw.io export")
    if implicit_names:
        warnings.append(
            {
                "where": "links",
                "message": "some link endpoints are not declared as devices; renderer will create implicit placeholder devices",
                "devices": implicit_names,
            }
        )
        advice.append("declare every link endpoint in devices so models, categories, and coordinates are explicit")
    if malformed_links:
        errors.append({"where": "links", "message": "one or more links are missing endpoint names", "links": malformed_links})
    if overlaps:
        warnings.append({"where": "devices", "message": "some rendered devices are close enough to overlap visually", "pairs": overlaps})
        advice.append("increase layout spacing or manually move overlapping devices")
    if len(components) > 1:
        warnings.append({"where": "links", "message": "topology has disconnected components", "components": components})
        advice.append("verify disconnected components are intentional before recording the lab video")
    if rendered_width > DIAGRAM_AUDIT_MAX_WIDTH or rendered_height > DIAGRAM_AUDIT_MAX_HEIGHT:
        warnings.append(
            {
                "where": "canvas",
                "message": "rendered canvas is large for report screenshots",
                "width": _rounded(rendered_width),
                "height": _rounded(rendered_height),
                "max_width": int(DIAGRAM_AUDIT_MAX_WIDTH),
                "max_height": int(DIAGRAM_AUDIT_MAX_HEIGHT),
            }
        )
        advice.append("use a denser layout or split the topology into overview and detail diagrams")
    if len(devices) > DIAGRAM_AUDIT_GROUPING_DEVICE_COUNT and options.group_by == "none":
        warnings.append(
            {
                "where": "options.group_by",
                "message": "large diagrams are easier to read with visual grouping",
                "devices": len(devices),
                "suggestion": "use --group-by auto, vlan, site, network, or category",
            }
        )
        advice.append("render large topologies with --group-by auto or a domain-specific grouping mode")
    if len(links) > DIAGRAM_AUDIT_LABEL_LINK_COUNT and options.link_labels:
        warnings.append(
            {
                "where": "options.link_labels",
                "message": "many link labels can clutter the diagram",
                "links": len(links),
                "suggestion": "use --no-link-labels for the final visual render",
            }
        )
        advice.append("hide link labels in dense final diagrams and keep exact ports in Markdown/config tables")
    if not errors and not warnings:
        advice.append("diagram appears suitable for offline SVG/draw.io/HTML rendering")

    report = {
        "kind": "pt730-diagram-audit",
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "checks": {
            "counts": {
                "explicit_devices": len(explicit_devices),
                "rendered_devices": len(devices),
                "implicit_devices": len(implicit_names),
                "links": len(links),
            },
            "coordinates": {
                "with_coordinates": len(explicit_positions),
                "missing": missing_coordinates,
            },
            "bounds": {
                "coordinate_bounds": _coordinate_bounds(explicit_positions),
                "rendered_bounds": {
                    "min_x": 0,
                    "min_y": 0,
                    "max_x": _rounded(rendered_width),
                    "max_y": _rounded(rendered_height),
                    "width": _rounded(rendered_width),
                    "height": _rounded(rendered_height),
                },
            },
            "overlaps": overlaps,
            "links": {
                "malformed": malformed_links,
                "implicit_endpoint_devices": implicit_names,
            },
            "components": {
                "count": len(components),
                "components": components,
            },
            "render_options": {
                "preset": options.preset,
                "link_labels": options.link_labels,
                "model_labels": options.model_labels,
                "group_by": options.group_by,
                "theme": options.theme,
                "title": options.title,
                "legend": options.legend,
            },
            "render_advice": advice,
        },
    }
    return report, 0 if report["ok"] else 1


def parse_bundle_formats(value: str) -> list[str]:
    formats: list[str] = []
    for raw in value.split(","):
        fmt = raw.strip()
        if not fmt:
            continue
        if fmt not in BUNDLE_RENDER_FORMATS:
            raise ValueError(f"bundle format must be one of: {', '.join(BUNDLE_RENDER_FORMATS)}")
        if fmt not in formats:
            formats.append(fmt)
    if not formats:
        raise ValueError("bundle formats cannot be empty")
    return formats


def default_bundle_formats(preset: str) -> str:
    if preset == "report":
        return ",".join(BUNDLE_REPORT_FORMATS)
    return ",".join(BUNDLE_DEFAULT_FORMATS)


def preset_render_defaults(preset: str) -> dict[str, Any]:
    if preset == "report":
        return {
            "theme": "paper",
            "link_labels": False,
            "model_labels": True,
            "group_by": "auto",
            "title": "",
            "legend": True,
        }
    return {
        "theme": "light",
        "link_labels": True,
        "model_labels": True,
        "group_by": "none",
        "title": "",
        "legend": False,
    }


def bundle_filename(basename: str, fmt: str) -> str:
    return f"{basename}.{BUNDLE_EXTENSIONS[fmt]}"


def render_format(plan: dict[str, Any], fmt: str, *, options: RenderOptions, direction: str) -> tuple[str, int]:
    if fmt == "mermaid":
        return mermaid(plan, direction=direction, link_labels=options.link_labels), 0
    if fmt == "svg":
        return svg(plan, options=options), 0
    if fmt == "drawio":
        return drawio(plan, options=options), 0
    if fmt == "html":
        return html_report(plan, options=options), 0
    if fmt == "markdown":
        return markdown(plan), 0
    if fmt == "summary":
        return summary(plan), 0
    if fmt == "course-audit":
        report, code = course_audit(plan)
        return json.dumps(report, ensure_ascii=False, indent=2) + "\n", code
    if fmt == "diagram-audit":
        report, code = diagram_audit(plan, options=options)
        return json.dumps(report, ensure_ascii=False, indent=2) + "\n", code
    if fmt == "verification-json":
        report = verification_plan(plan)
        return json.dumps(report, ensure_ascii=False, indent=2) + "\n", 0
    if fmt == "verification-md":
        report = verification_plan(plan)
        return verification_markdown(report), 0
    raise ValueError(f"unsupported render format: {fmt}")


def render_bundle(
    plan: dict[str, Any],
    *,
    plan_path: Path,
    output_dir: Path,
    basename: str,
    formats: list[str],
    options: RenderOptions,
    direction: str = "LR",
) -> tuple[dict[str, Any], int]:
    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts: dict[str, str] = {}
    paths: dict[str, str] = {}
    bytes_written: dict[str, int] = {}
    exit_codes: dict[str, int] = {}

    for fmt in formats:
        text, code = render_format(plan, fmt, options=options, direction=direction)
        path = output_dir / bundle_filename(basename, fmt)
        path.write_text(text, encoding="utf-8")
        artifacts[fmt] = path.name
        paths[fmt] = str(path)
        bytes_written[fmt] = path.stat().st_size
        exit_codes[fmt] = code

    try:
        summary_data = json.loads(summary(plan))
    except json.JSONDecodeError:
        summary_data = {}

    manifest_path = output_dir / f"{basename}.manifest.json"
    artifacts["manifest"] = manifest_path.name
    paths["manifest"] = str(manifest_path)
    manifest = {
        "kind": "pt730-render-bundle",
        "plan": str(plan_path),
        "output_dir": str(output_dir),
        "basename": basename,
        "formats": formats,
        "artifacts": artifacts,
        "paths": paths,
        "bytes": bytes_written,
        "exit_codes": exit_codes,
        "options": {
            "preset": options.preset,
            "theme": options.theme,
            "link_labels": options.link_labels,
            "model_labels": options.model_labels,
            "group_by": options.group_by,
            "direction": direction,
            "title": options.title,
            "legend": options.legend,
        },
        "counts": summary_data.get("counts", {}),
    }
    if "course-audit" in formats:
        audit_path = output_dir / artifacts["course-audit"]
        try:
            audit_data = json.loads(audit_path.read_text(encoding="utf-8"))
            manifest["course_audit"] = {"ok": bool(audit_data.get("ok")), "exit_code": exit_codes["course-audit"]}
        except (OSError, json.JSONDecodeError):
            manifest["course_audit"] = {"ok": False, "exit_code": exit_codes["course-audit"]}
    if "diagram-audit" in formats:
        audit_path = output_dir / artifacts["diagram-audit"]
        try:
            audit_data = json.loads(audit_path.read_text(encoding="utf-8"))
            manifest["diagram_audit"] = {"ok": bool(audit_data.get("ok")), "exit_code": exit_codes["diagram-audit"]}
        except (OSError, json.JSONDecodeError):
            manifest["diagram_audit"] = {"ok": False, "exit_code": exit_codes["diagram-audit"]}
    if "verification-json" in formats:
        verification_path = output_dir / artifacts["verification-json"]
        try:
            verification_data = json.loads(verification_path.read_text(encoding="utf-8"))
            counts = verification_data.get("counts") if isinstance(verification_data.get("counts"), dict) else {}
            manifest["verification_plan"] = {"ok": bool(verification_data.get("ok")), "exit_code": exit_codes["verification-json"], "counts": counts}
        except (OSError, json.JSONDecodeError):
            manifest["verification_plan"] = {"ok": False, "exit_code": exit_codes["verification-json"], "counts": {}}
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest, max(exit_codes.values(), default=0)


def emit(text: str, output: Path | None) -> None:
    if output is None:
        print(text, end="")
        return
    output.write_text(text, encoding="utf-8")


def add_link_label_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--no-link-labels", action="store_false", dest="link_labels", default=None, help="hide link port/cable/VLAN labels")


def add_preset_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--preset", choices=RENDER_PRESETS, default="manual", help="render defaults preset; report uses paper theme, auto grouping, legend, hidden link labels, and report bundle formats")


def add_visual_options(parser: argparse.ArgumentParser) -> None:
    add_preset_option(parser)
    parser.add_argument("--theme", choices=RENDER_THEMES, default=None, help="diagram color theme")
    add_link_label_option(parser)
    parser.add_argument("--no-model-labels", action="store_false", dest="model_labels", default=None, help="hide device model labels")
    parser.add_argument("--group-by", choices=RENDER_GROUP_BY, default=None, help="draw visual group boxes by network, VLAN, site, category, or auto detection")
    parser.add_argument("--title", default="", help="visible diagram title for SVG, draw.io, and HTML renders")
    parser.add_argument("--legend", action="store_true", default=None, help="include a visible device/link legend in SVG, draw.io, and HTML renders")


def render_options(args: argparse.Namespace, *, default_title: str = "") -> RenderOptions:
    preset = getattr(args, "preset", "manual")
    defaults = preset_render_defaults(preset)
    title = getattr(args, "title", "") or (default_title if preset == "report" else "")
    return RenderOptions(
        theme=getattr(args, "theme", None) or defaults["theme"],
        link_labels=defaults["link_labels"] if getattr(args, "link_labels", None) is None else getattr(args, "link_labels"),
        model_labels=defaults["model_labels"] if getattr(args, "model_labels", None) is None else getattr(args, "model_labels"),
        group_by=getattr(args, "group_by", None) or defaults["group_by"],
        title=title,
        legend=defaults["legend"] if getattr(args, "legend", None) is None else getattr(args, "legend"),
        preset=preset,
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
    add_preset_option(mermaid_p)
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

    diagram_audit_p = sub.add_parser("diagram-audit", help="audit offline diagram readability and render suitability")
    diagram_audit_p.add_argument("plan", type=Path)
    diagram_audit_p.add_argument("--output", type=Path, help="write output to a file instead of stdout")
    add_visual_options(diagram_audit_p)

    verify_p = sub.add_parser("verification-plan", help="generate offline live/manual validation steps for a topology plan")
    verify_p.add_argument("plan", type=Path)
    verify_p.add_argument("--format", choices=["json", "markdown"], default="json", help="output format")
    verify_p.add_argument("--output", type=Path, help="write output to a file instead of stdout")
    verify_p.add_argument("--compact", action="store_true", help="emit compact JSON when --format json")
    verify_p.add_argument("--max-hosts", type=int, default=12, help="maximum representative hosts to include")
    verify_p.add_argument("--max-service-targets", type=int, default=8, help="maximum server/service targets to include")

    bundle_p = sub.add_parser("bundle", help="render one plan into multiple offline review artifacts and a manifest")
    bundle_p.add_argument("plan", type=Path)
    bundle_p.add_argument("--output-dir", type=Path, required=True, help="directory for generated artifacts")
    bundle_p.add_argument("--basename", default="topology", help="artifact filename prefix")
    bundle_p.add_argument("--formats", default=None, help="comma-separated formats: mermaid,svg,drawio,html,markdown,summary,course-audit,diagram-audit,verification-json,verification-md; defaults depend on --preset")
    bundle_p.add_argument("--direction", default="LR", choices=["LR", "TD", "TB", "RL", "BT"], help="Mermaid direction when mermaid is included")
    add_visual_options(bundle_p)

    args = parser.parse_args(argv)
    try:
        if args.cmd == "mermaid":
            plan = _load_plan(args.plan)
            _enforce_plan_safety(plan, allow_risky=args.allow_risky, strict=args.strict_safety)
            link_labels = preset_render_defaults(args.preset)["link_labels"] if args.link_labels is None else args.link_labels
            emit(mermaid(plan, direction=args.direction, link_labels=link_labels), args.output)
            return 0
        if args.cmd == "svg":
            plan = _load_plan(args.plan)
            _enforce_plan_safety(plan, allow_risky=args.allow_risky, strict=args.strict_safety)
            emit(svg(plan, options=render_options(args, default_title=args.plan.stem)), args.output)
            return 0
        if args.cmd == "drawio":
            plan = _load_plan(args.plan)
            _enforce_plan_safety(plan, allow_risky=args.allow_risky, strict=args.strict_safety)
            emit(drawio(plan, options=render_options(args, default_title=args.plan.stem)), args.output)
            return 0
        if args.cmd == "html":
            plan = _load_plan(args.plan)
            _enforce_plan_safety(plan, allow_risky=args.allow_risky, strict=args.strict_safety)
            emit(html_report(plan, options=render_options(args, default_title=args.plan.stem)), args.output)
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
        if args.cmd == "diagram-audit":
            plan = _load_plan(args.plan)
            _enforce_plan_safety(plan, allow_risky=args.allow_risky, strict=args.strict_safety)
            report, code = diagram_audit(plan, options=render_options(args, default_title=args.plan.stem))
            emit(json.dumps(report, ensure_ascii=False, indent=2) + "\n", args.output)
            return code
        if args.cmd == "verification-plan":
            if args.max_hosts < 1:
                raise ValueError("--max-hosts must be at least 1")
            if args.max_service_targets < 1:
                raise ValueError("--max-service-targets must be at least 1")
            plan = _load_plan(args.plan)
            _enforce_plan_safety(plan, allow_risky=args.allow_risky, strict=args.strict_safety)
            report = verification_plan(plan, max_hosts=args.max_hosts, max_service_targets=args.max_service_targets)
            if args.format == "markdown":
                emit(verification_markdown(report), args.output)
            else:
                text = json.dumps(
                    report,
                    ensure_ascii=False,
                    indent=None if args.compact else 2,
                    separators=(",", ":") if args.compact else None,
                ) + "\n"
                emit(text, args.output)
            return 0
        if args.cmd == "bundle":
            plan = _load_plan(args.plan)
            _enforce_plan_safety(plan, allow_risky=args.allow_risky, strict=args.strict_safety)
            manifest, code = render_bundle(
                plan,
                plan_path=args.plan,
                output_dir=args.output_dir,
                basename=args.basename,
                formats=parse_bundle_formats(args.formats or default_bundle_formats(args.preset)),
                options=render_options(args, default_title=args.basename),
                direction=args.direction,
            )
            print(json.dumps(manifest, ensure_ascii=False, indent=2))
            return code
    except (OSError, ValueError) as exc:
        print(f"pt730-render: {exc}", file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
