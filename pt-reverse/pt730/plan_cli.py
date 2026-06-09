#!/usr/bin/env python3
"""Create and edit Packet Tracer topology JSON plans offline."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from topology_cli import _load_plan


def _emit(plan: dict[str, Any], output: Path | None, *, compact: bool) -> None:
    text = json.dumps(plan, ensure_ascii=False, indent=None if compact else 2, separators=(",", ":") if compact else None) + "\n"
    if output is None:
        print(text, end="")
        return
    output.write_text(text, encoding="utf-8")


def _str_value(value: str | None) -> str:
    return value or ""


def _optional_int(value: int | None) -> int | None:
    return value if value is not None else None


def _json_value(raw: str | None, *, label: str) -> Any:
    value = _str_value(raw)
    if not value:
        return None
    if value.startswith("@"):
        value = Path(value[1:]).read_text(encoding="utf-8")
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} must be valid JSON or @path: {exc}") from exc


def _json_object(raw: str | None, *, label: str) -> dict[str, Any] | None:
    value = _json_value(raw, label=label)
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _json_string_list(raw: str | None, *, label: str) -> list[str]:
    value = _json_value(raw, label=label)
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be a JSON array of strings")
    return value


def _file_lines(path: Path | None) -> list[str]:
    if path is None:
        return []
    return [line.rstrip("\n") for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _device_names(plan: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for item in plan.get("devices", []):
        if isinstance(item, dict) and item.get("name") not in (None, ""):
            names.add(str(item["name"]))
    return names


def _ensure_list(plan: dict[str, Any], key: str) -> list[Any]:
    value = plan.get(key)
    if isinstance(value, list):
        return value
    value = []
    plan[key] = value
    return value


def _first_present(item: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = item.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def schema() -> dict[str, Any]:
    return {
        "kind": "pt730-plan-schema",
        "commands": ["schema", "new", "add-device", "add-link", "add-annotation", "add-pc-config", "add-ipv6-config", "add-vlan-config", "add-dhcp-pool", "add-server-config", "add-ios-config", "add-security-policy"],
        "workflow": [
            "pt730-plan new --name LAB --output lab.json",
            "pt730-plan add-device lab.json --name R1 --category router --model 2911 --output lab.json",
            "pt730-plan add-device lab.json --name SW1 --category switch --model 2960-24TT --output lab.json",
            "pt730-plan add-link lab.json --a R1 --pa GigabitEthernet0/0 --b SW1 --pb FastEthernet0/1 --output lab.json",
            "pt730-plan add-ios-config lab.json --device R1 --command 'enable' --command 'configure terminal' --command 'end' --output lab.json",
            "pt730-layout lab.json --style lan --output lab-layout.json",
            "pt730-render svg lab-layout.json --preset report --output lab.svg",
        ],
        "device_fields": ["name", "model", "category", "x", "y", "site", "role", "vlan", "note"],
        "link_fields": ["a", "pa", "b", "pb", "cable", "vlan", "note"],
        "annotation_fields": ["id", "kind", "target", "title", "text", "x", "y", "width", "height", "color"],
        "pc_config_fields": ["name", "port", "dhcp", "ip", "mask", "gateway", "dns"],
        "ipv6_config_fields": ["name", "port", "ipv6", "prefix", "gateway", "dns", "note"],
        "vlan_config_fields": ["id", "name", "network", "gateway", "description"],
        "dhcp_pool_fields": ["device", "name", "vlan", "network", "mask", "start", "end", "gateway", "dns"],
        "server_config_fields": ["name", "port", "http", "tftp", "ftp_json", "dns_json", "email_json", "ntp_json", "syslog_json", "dhcp_json", "service"],
        "ios_config_fields": ["device", "source", "init_dialog", "save", "command", "commands_file", "commands_json"],
        "security_policy_fields": ["device", "type", "interface", "acl", "direction", "summary"],
    }


def new_plan(*, name: str) -> dict[str, Any]:
    metadata: dict[str, Any] = {"source": "pt730-plan new"}
    if name:
        metadata["name"] = name
    return {"metadata": metadata, "devices": [], "links": []}


def add_device(plan: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    devices = _ensure_list(plan, "devices")
    name = args.name
    existing_index = next((index for index, item in enumerate(devices) if isinstance(item, dict) and str(item.get("name", "")) == name), None)
    if existing_index is not None and not args.replace:
        raise ValueError(f"device {name!r} already exists; use --replace to update it")
    device: dict[str, Any] = {"name": name}
    for key in ("model", "category", "site", "role", "note"):
        value = _str_value(getattr(args, key))
        if value:
            device[key] = value
    vlan = _optional_int(args.vlan)
    if vlan is not None:
        device["vlan"] = vlan
    for key in ("x", "y"):
        value = _optional_int(getattr(args, key))
        if value is not None:
            device[key] = value
    if existing_index is None:
        devices.append(device)
    else:
        devices[existing_index] = {**devices[existing_index], **device}
    return plan


def add_link(plan: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    names = _device_names(plan)
    missing = [name for name in (args.a, args.b) if name not in names]
    if missing and not args.allow_missing:
        raise ValueError(f"link endpoint device(s) not found: {', '.join(missing)}; use --allow-missing to keep a forward reference")
    link: dict[str, Any] = {"a": args.a, "b": args.b, "cable": args.cable}
    for source, target in (("pa", "pa"), ("pb", "pb"), ("note", "note")):
        value = _str_value(getattr(args, source))
        if value:
            link[target] = value
    vlan = _optional_int(args.vlan)
    if vlan is not None:
        link["vlan"] = vlan
    _ensure_list(plan, "links").append(link)
    return plan


def add_annotation(plan: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    if not args.text and not args.title:
        raise ValueError("add-annotation requires --text or --title")
    item: dict[str, Any] = {}
    for key in ("id", "kind", "target", "title", "text", "color"):
        value = _str_value(getattr(args, key))
        if value:
            item[key] = value
    for key in ("x", "y", "width", "height"):
        value = _optional_int(getattr(args, key))
        if value is not None:
            item[key] = value
    _ensure_list(plan, "annotations").append(item)
    return plan


def add_pc_config(plan: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    configs = _ensure_list(plan, "pc_configs")
    key = (args.name, args.port)
    existing_index = next((index for index, item in enumerate(configs) if isinstance(item, dict) and (str(item.get("name", "")), str(item.get("port", "FastEthernet0"))) == key), None)
    if existing_index is not None and not args.replace:
        raise ValueError(f"pc_config for {args.name!r} {args.port!r} already exists; use --replace to update it")
    config: dict[str, Any] = {"name": args.name, "port": args.port}
    if args.dhcp:
        config["dhcp"] = True
    for key_name in ("ip", "mask", "gateway", "dns"):
        value = _str_value(getattr(args, key_name))
        if value:
            config[key_name] = value
    if existing_index is None:
        configs.append(config)
    else:
        configs[existing_index] = {**configs[existing_index], **config}
    return plan


def add_ipv6_config(plan: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    configs = _ensure_list(plan, "ipv6_configs")
    key = (args.name, args.port)
    existing_index = next((index for index, item in enumerate(configs) if isinstance(item, dict) and (str(item.get("name", "")), str(item.get("port", "FastEthernet0"))) == key), None)
    if existing_index is not None and not args.replace:
        raise ValueError(f"ipv6_config for {args.name!r} {args.port!r} already exists; use --replace to update it")
    config: dict[str, Any] = {"name": args.name, "port": args.port}
    for key_name in ("ipv6", "prefix", "gateway", "dns", "note"):
        value = _str_value(getattr(args, key_name))
        if value:
            config[key_name] = value
    if existing_index is None:
        configs.append(config)
    else:
        configs[existing_index] = {**configs[existing_index], **config}
    return plan


def add_vlan_config(plan: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    configs = _ensure_list(plan, "vlan_configs")
    existing_index = next((index for index, item in enumerate(configs) if isinstance(item, dict) and int(item.get("id", item.get("vlan", item.get("vlan_id", -1)))) == args.id), None)
    if existing_index is not None and not args.replace:
        raise ValueError(f"vlan_config for VLAN {args.id} already exists; use --replace to update it")
    config: dict[str, Any] = {"id": args.id}
    for key_name in ("name", "network", "gateway", "description"):
        value = _str_value(getattr(args, key_name))
        if value:
            config[key_name] = value
    if existing_index is None:
        configs.append(config)
    else:
        configs[existing_index] = {**configs[existing_index], **config}
    return plan


def add_dhcp_pool(plan: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    pools = _ensure_list(plan, "dhcp_pools")
    key = (args.device, args.name)
    existing_index = next((index for index, item in enumerate(pools) if isinstance(item, dict) and (str(item.get("device", item.get("router", ""))), str(item.get("name", item.get("pool", "")))) == key), None)
    if existing_index is not None and not args.replace:
        raise ValueError(f"dhcp_pool for {args.device!r} {args.name!r} already exists; use --replace to update it")
    pool: dict[str, Any] = {"name": args.name}
    if args.device:
        pool["device"] = args.device
    vlan = _optional_int(args.vlan)
    if vlan is not None:
        pool["vlan"] = vlan
    for key_name in ("network", "mask", "start", "end", "gateway", "dns"):
        value = _str_value(getattr(args, key_name))
        if value:
            pool[key_name] = value
    if existing_index is None:
        pools.append(pool)
    else:
        pools[existing_index] = {**pools[existing_index], **pool}
    return plan


def add_server_config(plan: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    configs = _ensure_list(plan, "server_configs")
    existing_index = next((index for index, item in enumerate(configs) if isinstance(item, dict) and _first_present(item, ("name", "device", "server")) == args.name), None)
    if existing_index is not None and not args.replace:
        raise ValueError(f"server_config for {args.name!r} already exists; use --replace to update it")
    config: dict[str, Any] = {"name": args.name}
    if args.port:
        config["port"] = args.port
    for service in args.service:
        normalized = service.strip().lower()
        if normalized not in {"http", "tftp", "ftp", "dns", "email", "ntp", "syslog", "dhcp"}:
            raise ValueError(f"unsupported server service: {service}")
        config[normalized] = True if normalized in {"http", "tftp"} else {"enabled": True}
    if args.http:
        config["http"] = True
    if args.tftp:
        config["tftp"] = True
    for key_name in ("ftp", "dns", "email", "ntp", "syslog", "dhcp"):
        value = _json_object(getattr(args, f"{key_name}_json"), label=f"--{key_name}-json")
        if value is not None:
            config[key_name] = value
    if existing_index is None:
        configs.append(config)
    else:
        configs[existing_index] = {**configs[existing_index], **config}
    return plan


def add_ios_config(plan: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    configs = _ensure_list(plan, "ios_configs")
    source = args.source or "pt730-plan"
    key = (args.device, source)
    existing_index = next((index for index, item in enumerate(configs) if isinstance(item, dict) and (_first_present(item, ("device", "name", "router", "switch")), str(item.get("source", "pt730-plan"))) == key), None)
    if existing_index is not None and not args.replace:
        raise ValueError(f"ios_config for {args.device!r} source {source!r} already exists; use --replace to update it")
    commands = list(args.command)
    commands.extend(_file_lines(args.commands_file))
    commands.extend(_json_string_list(args.commands_json, label="--commands-json"))
    if not commands:
        raise ValueError("add-ios-config requires --command, --commands-file, or --commands-json")
    config: dict[str, Any] = {"device": args.device, "source": source, "commands": commands}
    if args.init_dialog:
        config["init_dialog"] = True
    if args.save:
        config["save"] = True
    if existing_index is None:
        configs.append(config)
    else:
        configs[existing_index] = {**configs[existing_index], **config}
    return plan


def add_security_policy(plan: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    policies = _ensure_list(plan, "security_policies")
    key = (args.device, args.type, args.interface)
    existing_index = next((index for index, item in enumerate(policies) if isinstance(item, dict) and (_first_present(item, ("device", "router", "name")), str(item.get("type", item.get("kind", ""))), str(item.get("interface", item.get("port", "")))) == key), None)
    if existing_index is not None and not args.replace:
        raise ValueError(f"security_policy for {args.device!r} {args.type!r} {args.interface!r} already exists; use --replace to update it")
    policy: dict[str, Any] = {"device": args.device, "type": args.type}
    for key_name in ("interface", "acl", "direction", "summary"):
        value = _str_value(getattr(args, key_name))
        if value:
            policy[key_name] = value
    if existing_index is None:
        policies.append(policy)
    else:
        policies[existing_index] = {**policies[existing_index], **policy}
    return plan


def add_common_io(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--output", type=Path, help="write JSON to a file instead of stdout")
    parser.add_argument("--compact", action="store_true", help="emit compact JSON")


def add_plan_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("plan", type=Path, help="input topology JSON plan")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pt730-plan", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    schema_p = sub.add_parser("schema", help="print plan editor schema")
    schema_p.add_argument("--compact", action="store_true", help="emit compact JSON")

    new_p = sub.add_parser("new", help="create an empty topology plan")
    new_p.add_argument("--name", default="", help="logical topology name stored in metadata")
    add_common_io(new_p)

    device_p = sub.add_parser("add-device", help="append or update one device")
    add_plan_arg(device_p)
    device_p.add_argument("--name", required=True)
    device_p.add_argument("--model", default="")
    device_p.add_argument("--category", default="")
    device_p.add_argument("--x", type=int)
    device_p.add_argument("--y", type=int)
    device_p.add_argument("--site", default="")
    device_p.add_argument("--role", default="")
    device_p.add_argument("--vlan", type=int)
    device_p.add_argument("--note", default="")
    device_p.add_argument("--replace", action="store_true", help="replace/update an existing device with the same name")
    add_common_io(device_p)

    link_p = sub.add_parser("add-link", help="append one topology link")
    add_plan_arg(link_p)
    link_p.add_argument("--a", required=True, help="first endpoint device")
    link_p.add_argument("--b", required=True, help="second endpoint device")
    link_p.add_argument("--pa", default="", help="first endpoint port")
    link_p.add_argument("--pb", default="", help="second endpoint port")
    link_p.add_argument("--cable", default="straight")
    link_p.add_argument("--vlan", type=int)
    link_p.add_argument("--note", default="")
    link_p.add_argument("--allow-missing", action="store_true", help="allow links to devices not yet present in the plan")
    add_common_io(link_p)

    annotation_p = sub.add_parser("add-annotation", help="append one report/diagram callout")
    add_plan_arg(annotation_p)
    annotation_p.add_argument("--id", default="")
    annotation_p.add_argument("--kind", default="note")
    annotation_p.add_argument("--target", default="")
    annotation_p.add_argument("--title", default="")
    annotation_p.add_argument("--text", default="")
    annotation_p.add_argument("--x", type=int)
    annotation_p.add_argument("--y", type=int)
    annotation_p.add_argument("--width", type=int)
    annotation_p.add_argument("--height", type=int)
    annotation_p.add_argument("--color", default="")
    add_common_io(annotation_p)

    pc_p = sub.add_parser("add-pc-config", help="append or update one PC/server IPv4 config record")
    add_plan_arg(pc_p)
    pc_p.add_argument("--name", required=True)
    pc_p.add_argument("--port", default="FastEthernet0")
    pc_p.add_argument("--dhcp", action="store_true")
    pc_p.add_argument("--ip", default="")
    pc_p.add_argument("--mask", default="")
    pc_p.add_argument("--gateway", default="")
    pc_p.add_argument("--dns", default="")
    pc_p.add_argument("--replace", action="store_true", help="replace/update an existing config for the same name and port")
    add_common_io(pc_p)

    ipv6_p = sub.add_parser("add-ipv6-config", help="append or update one PC/server IPv6 config record")
    add_plan_arg(ipv6_p)
    ipv6_p.add_argument("--name", required=True)
    ipv6_p.add_argument("--port", default="FastEthernet0")
    ipv6_p.add_argument("--ipv6", default="")
    ipv6_p.add_argument("--prefix", default="")
    ipv6_p.add_argument("--gateway", default="")
    ipv6_p.add_argument("--dns", default="")
    ipv6_p.add_argument("--note", default="")
    ipv6_p.add_argument("--replace", action="store_true", help="replace/update an existing IPv6 config for the same name and port")
    add_common_io(ipv6_p)

    vlan_p = sub.add_parser("add-vlan-config", help="append or update one VLAN metadata record")
    add_plan_arg(vlan_p)
    vlan_p.add_argument("--id", type=int, required=True)
    vlan_p.add_argument("--name", default="")
    vlan_p.add_argument("--network", default="")
    vlan_p.add_argument("--gateway", default="")
    vlan_p.add_argument("--description", default="")
    vlan_p.add_argument("--replace", action="store_true", help="replace/update an existing VLAN record with the same id")
    add_common_io(vlan_p)

    dhcp_p = sub.add_parser("add-dhcp-pool", help="append or update one router DHCP pool metadata record")
    add_plan_arg(dhcp_p)
    dhcp_p.add_argument("--name", required=True)
    dhcp_p.add_argument("--device", default="")
    dhcp_p.add_argument("--vlan", type=int)
    dhcp_p.add_argument("--network", default="")
    dhcp_p.add_argument("--mask", default="")
    dhcp_p.add_argument("--start", default="")
    dhcp_p.add_argument("--end", default="")
    dhcp_p.add_argument("--gateway", default="")
    dhcp_p.add_argument("--dns", default="")
    dhcp_p.add_argument("--replace", action="store_true", help="replace/update an existing DHCP pool with the same device and name")
    add_common_io(dhcp_p)

    server_p = sub.add_parser("add-server-config", help="append or update one Server-PT service config record")
    add_plan_arg(server_p)
    server_p.add_argument("--name", required=True)
    server_p.add_argument("--port", default="FastEthernet0")
    server_p.add_argument("--http", action="store_true")
    server_p.add_argument("--tftp", action="store_true")
    server_p.add_argument("--service", action="append", default=[], help="enable a service: http, tftp, ftp, dns, email, ntp, syslog, or dhcp")
    server_p.add_argument("--ftp-json", default="", help="FTP service JSON object or @file")
    server_p.add_argument("--dns-json", default="", help="DNS service JSON object or @file")
    server_p.add_argument("--email-json", default="", help="Email service JSON object or @file")
    server_p.add_argument("--ntp-json", default="", help="NTP service JSON object or @file")
    server_p.add_argument("--syslog-json", default="", help="Syslog service JSON object or @file")
    server_p.add_argument("--dhcp-json", default="", help="DHCP service JSON object or @file")
    server_p.add_argument("--replace", action="store_true", help="replace/update an existing Server-PT config with the same name")
    add_common_io(server_p)

    ios_p = sub.add_parser("add-ios-config", help="append or update one IOS command config record")
    add_plan_arg(ios_p)
    ios_p.add_argument("--device", required=True)
    ios_p.add_argument("--source", default="pt730-plan")
    ios_p.add_argument("--init-dialog", action="store_true")
    ios_p.add_argument("--save", action="store_true")
    ios_p.add_argument("--command", action="append", default=[], help="one IOS command; can be repeated")
    ios_p.add_argument("--commands-file", type=Path, help="newline-delimited IOS commands")
    ios_p.add_argument("--commands-json", default="", help="JSON array of IOS commands or @file")
    ios_p.add_argument("--replace", action="store_true", help="replace/update an existing IOS config with the same device and source")
    add_common_io(ios_p)

    security_p = sub.add_parser("add-security-policy", help="append or update one security policy metadata record")
    add_plan_arg(security_p)
    security_p.add_argument("--device", required=True)
    security_p.add_argument("--type", required=True)
    security_p.add_argument("--interface", default="")
    security_p.add_argument("--acl", default="")
    security_p.add_argument("--direction", default="")
    security_p.add_argument("--summary", default="")
    security_p.add_argument("--replace", action="store_true", help="replace/update an existing security policy with the same device/type/interface")
    add_common_io(security_p)

    args = parser.parse_args(argv)
    try:
        if args.cmd == "schema":
            print(json.dumps(schema(), ensure_ascii=False, indent=None if args.compact else 2, separators=(",", ":") if args.compact else None))
            return 0
        if args.cmd == "new":
            _emit(new_plan(name=args.name), args.output, compact=args.compact)
            return 0

        plan = _load_plan(args.plan)
        if args.cmd == "add-device":
            _emit(add_device(plan, args), args.output, compact=args.compact)
        elif args.cmd == "add-link":
            _emit(add_link(plan, args), args.output, compact=args.compact)
        elif args.cmd == "add-annotation":
            _emit(add_annotation(plan, args), args.output, compact=args.compact)
        elif args.cmd == "add-pc-config":
            _emit(add_pc_config(plan, args), args.output, compact=args.compact)
        elif args.cmd == "add-ipv6-config":
            _emit(add_ipv6_config(plan, args), args.output, compact=args.compact)
        elif args.cmd == "add-vlan-config":
            _emit(add_vlan_config(plan, args), args.output, compact=args.compact)
        elif args.cmd == "add-dhcp-pool":
            _emit(add_dhcp_pool(plan, args), args.output, compact=args.compact)
        elif args.cmd == "add-server-config":
            _emit(add_server_config(plan, args), args.output, compact=args.compact)
        elif args.cmd == "add-ios-config":
            _emit(add_ios_config(plan, args), args.output, compact=args.compact)
        elif args.cmd == "add-security-policy":
            _emit(add_security_policy(plan, args), args.output, compact=args.compact)
        else:
            raise ValueError(f"unknown command: {args.cmd}")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"pt730-plan: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
