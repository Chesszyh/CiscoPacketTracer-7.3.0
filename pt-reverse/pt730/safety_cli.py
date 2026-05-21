#!/usr/bin/env python3
"""Offline safety checker for Packet Tracer 7.3.0 automation plans."""

from __future__ import annotations

import argparse
import ipaddress
import json
import re
import sys
from pathlib import Path
from typing import Any

from catalog_cli import ALL_MODELS, ALL_MODULES, RISKY_MODELS, SAFE_MODELS, VERIFIED_CABLE_CODES, VERIFIED_MODULES
from topology_cli import CABLE_CODES


RISKY_JS_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bdhcpRun\s*\("), "DhcpClientProcess.dhcpRun() can block or crash PT 7.3.0"),
    (re.compile(r"\bfileOpenFromBytes\s*\("), "fileOpenFromBytes(...) argument combinations were unreliable in PT 7.3.0"),
]

GUARDED_JS_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bfileNew\s*\("), "fileNew is safe when intentional, but it clears the current workspace"),
    (re.compile(r"\bsetDhcpFlag\s*\(\s*true\s*\)"), "DHCP client validation is unstable; prefer static IP for smoke checks"),
]

PHYSICAL_INTERFACE_PREFIXES = ("FastEthernet", "GigabitEthernet", "Ethernet", "Serial")
VIRTUAL_INTERFACE_PREFIXES = ("Vlan", "Loopback", "Port-channel", "Tunnel", "Null")


def print_json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def load_json(path: str) -> dict[str, Any]:
    if path == "-":
        data = json.load(sys.stdin)
    else:
        with Path(path).open("r", encoding="utf-8") as f:
            data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("plan must be a JSON object")
    return data


def add_issue(issues: list[dict[str, Any]], level: str, where: str, message: str, **extra: Any) -> None:
    issue = {"level": level, "where": where, "message": message}
    issue.update(extra)
    issues.append(issue)


def cable_status(value: Any) -> tuple[str, str]:
    raw = "straight" if value is None else str(value)
    key = raw.lower().replace(" ", "-")
    code: int | None = None
    if raw.isdigit():
        code = int(raw)
    elif key in CABLE_CODES:
        code = int(CABLE_CODES[key])
    if code is None:
        return "error", f"unknown cable type: {raw}"
    if code in VERIFIED_CABLE_CODES:
        return "ok", f"verified cable code {code}"
    return "warning", f"known cable code {code}, not live-verified locally"


def config_commands(config: dict[str, Any]) -> list[str]:
    raw = config.get("commands", config.get("cmds", config.get("config", config.get("cli", []))))
    if isinstance(raw, str):
        return [line.strip() for line in raw.splitlines() if line.strip() and not line.strip().startswith("!")]
    if isinstance(raw, list):
        return [str(line).strip() for line in raw if str(line).strip() and not str(line).strip().startswith("!")]
    return []


def interface_blocks(commands: list[str]) -> dict[str, list[str]]:
    blocks: dict[str, list[str]] = {}
    current: str | None = None
    for command in commands:
        match = re.match(r"^interface\s+(.+)$", command, flags=re.IGNORECASE)
        if match:
            candidate = match.group(1).strip()
            if candidate.lower().startswith("range "):
                current = None
                continue
            current = candidate
            blocks.setdefault(current, [])
            continue
        if current is not None:
            blocks[current].append(command)
    return blocks


def is_physical_interface(name: str) -> bool:
    return name.startswith(PHYSICAL_INTERFACE_PREFIXES) and not name.startswith(VIRTUAL_INTERFACE_PREFIXES)


def interface_needs_no_shutdown(commands: list[str]) -> bool:
    return any(command.lower().startswith(("ip address ", "switchport ")) for command in commands)


def has_command(commands: list[str], command: str) -> bool:
    target = command.lower()
    return any(line.lower() == target for line in commands)


def has_command_prefix(commands: list[str], prefix: str) -> bool:
    target = prefix.lower()
    return any(line.lower().startswith(target) for line in commands)


def ipv4(value: Any) -> ipaddress.IPv4Address:
    return ipaddress.ip_address(str(value))


def ipv4_network(address: Any, mask: Any) -> ipaddress.IPv4Network:
    return ipaddress.ip_network(f"{address}/{mask}", strict=False)


def check_plan(plan: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    device_names: set[str] = set()
    device_ports: dict[str, set[str]] = {}
    serial_links: list[tuple[str, str, str, str]] = []
    ios_interface_blocks: dict[tuple[str, str], list[str]] = {}

    for index, device in enumerate(plan.get("devices", [])):
        if not isinstance(device, dict):
            add_issue(issues, "error", f"devices[{index}]", "device entry must be an object")
            continue
        name = str(device.get("name", device.get("id", "")))
        if not name:
            add_issue(issues, "error", f"devices[{index}]", "device name is missing")
        elif name in device_names:
            add_issue(issues, "error", f"devices[{index}]", "duplicate device name", name=name)
        else:
            device_names.add(name)
        model = str(device.get("model", ""))
        if name and model in ALL_MODELS:
            device_ports[name] = {str(getattr(port, "full_name", "")) for port in ALL_MODELS[model].ports}
        if not model:
            add_issue(issues, "error", f"devices[{index}]", "device model is missing", name=name)
        elif model in RISKY_MODELS:
            add_issue(issues, "error", f"devices[{index}]", RISKY_MODELS[model], name=name, model=model)
        elif model not in SAFE_MODELS:
            add_issue(issues, "warning", f"devices[{index}]", "device model is not live-verified on this PT 7.3.0 setup", name=name, model=model)

    for index, module in enumerate(plan.get("modules", [])):
        if not isinstance(module, dict):
            add_issue(issues, "error", f"modules[{index}]", "module entry must be an object")
            continue
        model = str(module.get("model", module.get("module", module.get("name", ""))))
        if not model:
            add_issue(issues, "error", f"modules[{index}]", "module model is missing")
        elif model not in VERIFIED_MODULES:
            add_issue(issues, "warning", f"modules[{index}]", "module is not live-verified on this PT 7.3.0 setup", model=model)
        device_name = str(module.get("device", module.get("device_name", module.get("on", ""))))
        if device_name and device_name not in device_names:
            add_issue(issues, "error", f"modules[{index}]", "unknown module target device", name=device_name)
        if device_name in device_ports and model in ALL_MODULES:
            device_ports[device_name].update(str(port) for port in ALL_MODULES[model].ports_added)

    def check_port(where: str, device_name: str, port_name: str) -> None:
        ports = device_ports.get(device_name)
        if ports is not None and port_name and port_name not in ports:
            add_issue(issues, "error", where, "unknown port", name=device_name, port=port_name)

    def check_ipv4(where: str, label: str, value: Any) -> ipaddress.IPv4Address | None:
        if value in (None, ""):
            return None
        try:
            return ipv4(value)
        except ValueError:
            add_issue(issues, "error", where, "invalid IPv4 address", field=label, value=str(value))
            return None

    def check_ip_subnet(where: str, ip_value: Any, mask_value: Any, gateway_value: Any) -> None:
        ip_addr = check_ipv4(where, "ip", ip_value)
        check_ipv4(where, "mask", mask_value)
        gateway = check_ipv4(where, "gateway", gateway_value)
        if ip_addr is None or gateway is None or mask_value in (None, ""):
            return
        try:
            network = ipv4_network(ip_addr, mask_value)
        except ValueError:
            add_issue(issues, "error", where, "invalid IPv4 network mask", field="mask", value=str(mask_value))
            return
        if gateway not in network:
            add_issue(issues, "error", where, "gateway outside subnet", gateway=str(gateway), subnet=str(network))

    def check_dhcp_pool(where: str, dhcp: Any) -> None:
        if not isinstance(dhcp, dict):
            return
        network_value = dhcp.get("network")
        mask_value = dhcp.get("mask", dhcp.get("subnet_mask", dhcp.get("netmask")))
        if network_value in (None, "") or mask_value in (None, ""):
            return
        check_ipv4(where, "network", network_value)
        check_ipv4(where, "mask", mask_value)
        try:
            network = ipv4_network(network_value, mask_value)
        except ValueError:
            add_issue(issues, "error", where, "invalid DHCP network", network=str(network_value), mask=str(mask_value))
            return
        for field in ("start", "start_ip", "first_ip", "end", "end_ip", "last_ip", "gateway", "default_gateway", "router", "dns", "dns_server"):
            if field not in dhcp or dhcp.get(field) in (None, ""):
                continue
            address = check_ipv4(where, field, dhcp.get(field))
            if address is not None and field not in {"dns", "dns_server"} and address not in network:
                add_issue(issues, "error", where, "outside DHCP network", field=field, value=str(address), network=str(network))

    for index, link in enumerate(plan.get("links", [])):
        if not isinstance(link, dict):
            add_issue(issues, "error", f"links[{index}]", "link entry must be an object")
            continue
        a = str(link.get("a", link.get("device_a", link.get("from", link.get("from_device", "")))))
        b = str(link.get("b", link.get("device_b", link.get("to", link.get("to_device", "")))))
        pa = str(link.get("pa", link.get("port_a", link.get("from_port", ""))))
        pb = str(link.get("pb", link.get("port_b", link.get("to_port", ""))))
        if not a or not b or not pa or not pb:
            add_issue(issues, "error", f"links[{index}]", "link requires a/pa/b/pb")
        for endpoint in (a, b):
            if endpoint and endpoint not in device_names:
                add_issue(issues, "error", f"links[{index}]", "unknown endpoint device", name=endpoint)
        check_port(f"links[{index}]", a, pa)
        check_port(f"links[{index}]", b, pb)
        level, message = cable_status(link.get("cable", link.get("type", "straight")))
        if level != "ok":
            add_issue(issues, level, f"links[{index}]", message)
        if str(link.get("cable", link.get("type", "straight"))).lower() == "serial" or "serial" in {pa.lower()[:6], pb.lower()[:6]}:
            serial_links.append((a, pa, b, pb))

    for index, config in enumerate(plan.get("pc_configs", [])):
        if not isinstance(config, dict):
            add_issue(issues, "error", f"pc_configs[{index}]", "pc config entry must be an object")
            continue
        name = str(config.get("name", config.get("device", config.get("pc", ""))))
        if name and name not in device_names:
            add_issue(issues, "error", f"pc_configs[{index}]", "unknown configured device", name=name)
        check_port(f"pc_configs[{index}]", name, str(config.get("port", "FastEthernet0")))
        if config.get("ip") or config.get("ip_address") or config.get("address"):
            check_ip_subnet(
                f"pc_configs[{index}]",
                config.get("ip", config.get("ip_address", config.get("address"))),
                config.get("mask", config.get("subnet_mask", config.get("netmask", "255.255.255.0"))),
                config.get("gateway", config.get("default_gateway", config.get("gw"))),
            )
        check_ipv4(f"pc_configs[{index}]", "dns", config.get("dns", config.get("dns_server")))
        if config.get("dhcp") is True:
            add_issue(
                issues,
                "warning",
                f"pc_configs[{index}]",
                "DHCP client checks are guarded; static addressing is safer for unattended smoke tests",
                name=str(config.get("name", config.get("device", ""))),
            )

    for collection, aliases in (
        ("server_configs", ("name", "device", "server")),
        ("ios_configs", ("name", "device", "router", "switch")),
    ):
        for index, config in enumerate(plan.get(collection, [])):
            if not isinstance(config, dict):
                add_issue(issues, "error", f"{collection}[{index}]", f"{collection} entry must be an object")
                continue
            name = ""
            for alias in aliases:
                if config.get(alias):
                    name = str(config.get(alias))
                    break
            if name and name not in device_names:
                add_issue(issues, "error", f"{collection}[{index}]", "unknown configured device", name=name)
            if collection == "server_configs":
                check_port(f"{collection}[{index}]", name, str(config.get("port", "FastEthernet0")))
                check_dhcp_pool(f"{collection}[{index}].dhcp", config.get("dhcp"))
            elif collection == "ios_configs":
                blocks = interface_blocks(config_commands(config))
                for interface, commands in blocks.items():
                    ios_interface_blocks[(name, interface)] = commands
                    ports = device_ports.get(name)
                    if ports is not None and is_physical_interface(interface) and interface not in ports:
                        add_issue(issues, "error", f"{collection}[{index}]", "unknown IOS interface", name=name, interface=interface)
                    if interface_needs_no_shutdown(commands) and not has_command(commands, "no shutdown") and not has_command(commands, "shutdown"):
                        add_issue(
                            issues,
                            "warning",
                            f"{collection}[{index}]",
                            "configured IOS interface has no no shutdown",
                            name=name,
                            interface=interface,
                        )

    for a, pa, b, pb in serial_links:
        a_commands = ios_interface_blocks.get((a, pa), [])
        b_commands = ios_interface_blocks.get((b, pb), [])
        if not has_command_prefix(a_commands, "clock rate ") and not has_command_prefix(b_commands, "clock rate "):
            add_issue(issues, "warning", "links", "serial link has no clock rate on either endpoint", a=a, pa=pa, b=b, pb=pb)

    return issues


def check_js(code: str) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for regex, message in RISKY_JS_PATTERNS:
        if regex.search(code):
            add_issue(issues, "error", "javascript", message, pattern=regex.pattern)
    for regex, message in GUARDED_JS_PATTERNS:
        if regex.search(code):
            add_issue(issues, "warning", "javascript", message, pattern=regex.pattern)
    for model, note in RISKY_MODELS.items():
        if model in code:
            add_issue(issues, "error", "javascript", note, model=model)
    return issues


def summarize(kind: str, issues: list[dict[str, Any]], *, strict: bool) -> dict[str, Any]:
    errors = [issue for issue in issues if issue["level"] == "error"]
    warnings = [issue for issue in issues if issue["level"] == "warning"]
    ok = not errors and (not strict or not warnings)
    return {"kind": kind, "ok": ok, "strict": strict, "errors": errors, "warnings": warnings}


def exit_code(report: dict[str, Any]) -> int:
    return 0 if report["ok"] else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true", help="treat warnings as failures")
    sub = parser.add_subparsers(dest="cmd", required=True)

    plan_p = sub.add_parser("plan", help="check a topology JSON plan without contacting Packet Tracer")
    plan_p.add_argument("path", help="plan JSON path, or - for stdin")
    plan_p.add_argument("--strict", action="store_true", default=argparse.SUPPRESS, help="treat warnings as failures")

    js_p = sub.add_parser("js", help="check JavaScript before passing it to pt730-eval")
    js_p.add_argument("--strict", action="store_true", default=argparse.SUPPRESS, help="treat warnings as failures")
    js_src = js_p.add_mutually_exclusive_group(required=True)
    js_src.add_argument("--file", type=Path)
    js_src.add_argument("--stdin", action="store_true")
    js_src.add_argument("code", nargs="?")

    sub.add_parser("policy", help="print the current safety policy")

    args = parser.parse_args(argv)
    try:
        if args.cmd == "plan":
            report = summarize("plan", check_plan(load_json(args.path)), strict=args.strict)
            print_json(report)
            return exit_code(report)
        if args.cmd == "js":
            if args.file:
                code = args.file.read_text(encoding="utf-8")
            elif args.stdin:
                code = sys.stdin.read()
            else:
                code = args.code or ""
            report = summarize("javascript", check_js(code), strict=args.strict)
            print_json(report)
            return exit_code(report)
        if args.cmd == "policy":
            print_json(
                {
                    "safe_models": SAFE_MODELS,
                    "risky_models": RISKY_MODELS,
                    "verified_modules": VERIFIED_MODULES,
                    "verified_cable_codes": VERIFIED_CABLE_CODES,
                    "risky_js_patterns": [pattern.pattern for pattern, _ in RISKY_JS_PATTERNS],
                    "guarded_js_patterns": [pattern.pattern for pattern, _ in GUARDED_JS_PATTERNS],
                }
            )
            return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"pt730-safety: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
