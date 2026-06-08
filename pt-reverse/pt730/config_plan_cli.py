#!/usr/bin/env python3
"""Generate IOS config records from topology plan VLAN/link metadata."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any

from ios_template_cli import render_commands
from topology_cli import _load_plan


SOURCE = "pt730-config-plan campus"
SWITCH_MODELS = {"2950-24", "2960-24TT"}
ENDPOINT_CATEGORIES = {"pc", "server", "laptop", "host", "endpoint"}


def _name(device: dict[str, Any], index: int = 0) -> str:
    value = device.get("name", device.get("id"))
    return str(value) if value not in (None, "") else f"device_{index}"


def _category(device: dict[str, Any]) -> str:
    return str(device.get("category", device.get("kind", ""))).lower().replace("-", "_").replace(" ", "_")


def _is_switch(device: dict[str, Any]) -> bool:
    return _category(device) in {"switch", "multilayer_switch"} or str(device.get("model", "")) in SWITCH_MODELS


def _is_endpoint(device: dict[str, Any]) -> bool:
    return _category(device) in ENDPOINT_CATEGORIES or str(device.get("model", "")) in {"PC-PT", "Server-PT", "Laptop-PT"}


def _pick(link: dict[str, Any], names: tuple[str, ...]) -> str:
    for name in names:
        value = link.get(name)
        if value not in (None, ""):
            return str(value)
    return ""


def _vlan(link: dict[str, Any]) -> str | None:
    value = link.get("vlan", link.get("vlan_id"))
    if value in (None, ""):
        return None
    return str(value)


def _merge_allowed(existing: Any, vlan: str | None) -> list[str]:
    values: set[str] = set()
    if isinstance(existing, list):
        values.update(str(item) for item in existing)
    elif existing not in (None, "", "all"):
        values.update(str(item).strip() for item in str(existing).split(",") if str(item).strip())
    if vlan:
        values.add(vlan)
    return sorted(values, key=lambda item: int(item) if item.isdigit() else item)


def _interface_record(name: str, mode: str, vlan: str | None) -> dict[str, Any]:
    if mode == "access":
        return {"name": name, "mode": "access", "vlan": vlan}
    return {"name": name, "mode": "trunk", "allowed_vlans": [vlan] if vlan else "all"}


def _add_interface(configs: dict[str, dict[str, Any]], device: str, port: str, mode: str, vlan: str | None) -> None:
    spec = configs.setdefault(device, {"device": device, "hostname": device, "vlans": [], "interfaces": []})
    if vlan and not any(str(item.get("id", item.get("vlan", ""))) == vlan for item in spec["vlans"]):
        spec["vlans"].append({"id": int(vlan) if vlan.isdigit() else vlan})
    for interface in spec["interfaces"]:
        if interface.get("name") != port:
            continue
        if interface.get("mode") == "trunk" or mode == "trunk":
            interface["mode"] = "trunk"
            interface.pop("vlan", None)
            interface["allowed_vlans"] = _merge_allowed(interface.get("allowed_vlans"), vlan)
        elif vlan:
            interface["vlan"] = vlan
        return
    spec["interfaces"].append(_interface_record(port, mode, vlan))


def generated_ios_configs(plan: dict[str, Any]) -> list[dict[str, Any]]:
    devices = [_device for _device in plan.get("devices", []) if isinstance(_device, dict)]
    by_name = {_name(device, index): device for index, device in enumerate(devices)}
    switch_names = {name for name, device in by_name.items() if _is_switch(device)}
    endpoint_names = {name for name, device in by_name.items() if _is_endpoint(device)}
    specs: dict[str, dict[str, Any]] = {}

    for link in plan.get("links", []):
        if not isinstance(link, dict):
            continue
        a = _pick(link, ("a", "device_a", "from", "from_device"))
        b = _pick(link, ("b", "device_b", "to", "to_device"))
        pa = _pick(link, ("pa", "port_a", "from_port"))
        pb = _pick(link, ("pb", "port_b", "to_port"))
        vlan = _vlan(link)
        if not a or not b or not pa or not pb:
            continue
        a_is_switch = a in switch_names
        b_is_switch = b in switch_names
        if a_is_switch and b_is_switch:
            _add_interface(specs, a, pa, "trunk", vlan)
            _add_interface(specs, b, pb, "trunk", vlan)
        elif a_is_switch and b in endpoint_names:
            _add_interface(specs, a, pa, "access", vlan)
        elif b_is_switch and a in endpoint_names:
            _add_interface(specs, b, pb, "access", vlan)

    records = []
    for device in sorted(specs):
        spec = specs[device]
        spec["vlans"] = sorted(spec["vlans"], key=lambda item: int(item["id"]) if str(item["id"]).isdigit() else str(item["id"]))
        spec["interfaces"] = sorted(spec["interfaces"], key=lambda item: str(item["name"]))
        records.append({"device": device, "source": SOURCE, "commands": render_commands(spec)})
    return records


def configured_plan(plan: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(plan)
    existing = [config for config in result.get("ios_configs", []) if not (isinstance(config, dict) and config.get("source") == SOURCE)]
    result["ios_configs"] = existing + generated_ios_configs(result)
    return result


def schema() -> dict[str, Any]:
    return {
        "commands": ["schema", "campus"],
        "rules": [
            "switch-switch links become trunk interfaces",
            "switch-endpoint links become access interfaces",
            "link.vlan values become VLAN declarations and allowed/access VLANs",
            "existing ios_configs with other sources are preserved",
        ],
        "output": "full topology JSON by default; use --ios-only for {ios_configs:[...]}",
    }


def emit_json(value: dict[str, Any], output: Path | None, *, compact: bool) -> None:
    text = json.dumps(value, ensure_ascii=False, indent=None if compact else 2, separators=(",", ":") if compact else None) + "\n"
    if output is None:
        print(text, end="")
        return
    output.write_text(text, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pt730-config-plan", description=__doc__)
    parser.add_argument("--compact", action="store_true", help="emit compact JSON")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("schema", help="print config generation rules")
    campus_p = sub.add_parser("campus", help="generate switch IOS config records from topology VLAN links")
    campus_p.add_argument("plan", type=Path)
    campus_p.add_argument("--output", type=Path, help="write JSON to a file instead of stdout")
    campus_p.add_argument("--ios-only", action="store_true", help="output only generated ios_configs")

    args = parser.parse_args(argv)
    try:
        if args.cmd == "schema":
            emit_json(schema(), None, compact=args.compact)
            return 0
        if args.cmd == "campus":
            plan = _load_plan(args.plan)
            generated = generated_ios_configs(plan)
            if args.ios_only:
                emit_json({"ios_configs": generated}, args.output, compact=args.compact)
            else:
                emit_json(configured_plan(plan), args.output, compact=args.compact)
            return 0
        raise ValueError(f"unknown command: {args.cmd}")
    except Exception as exc:  # noqa: BLE001
        print(f"pt730-config-plan: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
