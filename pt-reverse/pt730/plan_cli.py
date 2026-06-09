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


def schema() -> dict[str, Any]:
    return {
        "kind": "pt730-plan-schema",
        "commands": ["schema", "new", "add-device", "add-link", "add-annotation", "add-pc-config"],
        "workflow": [
            "pt730-plan new --name LAB --output lab.json",
            "pt730-plan add-device lab.json --name R1 --category router --model 2911 --output lab.json",
            "pt730-plan add-device lab.json --name SW1 --category switch --model 2960-24TT --output lab.json",
            "pt730-plan add-link lab.json --a R1 --pa GigabitEthernet0/0 --b SW1 --pb FastEthernet0/1 --output lab.json",
            "pt730-layout lab.json --style lan --output lab-layout.json",
            "pt730-render svg lab-layout.json --preset report --output lab.svg",
        ],
        "device_fields": ["name", "model", "category", "x", "y", "site", "role", "vlan", "note"],
        "link_fields": ["a", "pa", "b", "pb", "cable", "vlan", "note"],
        "annotation_fields": ["id", "kind", "target", "title", "text", "x", "y", "width", "height", "color"],
        "pc_config_fields": ["name", "port", "dhcp", "ip", "mask", "gateway", "dns"],
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
        else:
            raise ValueError(f"unknown command: {args.cmd}")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"pt730-plan: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
