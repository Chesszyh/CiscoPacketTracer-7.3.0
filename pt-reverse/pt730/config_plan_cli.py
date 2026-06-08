#!/usr/bin/env python3
"""Generate IOS config records from topology plan VLAN/link metadata."""

from __future__ import annotations

import argparse
import copy
import ipaddress
import json
import re
import sys
from pathlib import Path
from typing import Any

from ios_template_cli import render_commands
from topology_cli import _load_plan


SOURCE = "pt730-config-plan campus"
SWITCH_MODELS = {"2950-24", "2960-24TT"}
ENDPOINT_CATEGORIES = {"pc", "server", "laptop", "host", "endpoint"}
CORE_ROLES = {"core", "distribution", "multilayer", "multilayer_switch", "l3_switch"}


def _name(device: dict[str, Any], index: int = 0) -> str:
    value = device.get("name", device.get("id"))
    return str(value) if value not in (None, "") else f"device_{index}"


def _category(device: dict[str, Any]) -> str:
    return str(device.get("category", device.get("kind", ""))).lower().replace("-", "_").replace(" ", "_")


def _is_switch(device: dict[str, Any]) -> bool:
    return _category(device) in {"switch", "multilayer_switch"} or str(device.get("model", "")) in SWITCH_MODELS


def _is_endpoint(device: dict[str, Any]) -> bool:
    return _category(device) in ENDPOINT_CATEGORIES or str(device.get("model", "")) in {"PC-PT", "Server-PT", "Laptop-PT"}


def _is_core_switch(name: str, device: dict[str, Any]) -> bool:
    role = str(device.get("role", device.get("pt_role", ""))).lower().replace("-", "_").replace(" ", "_")
    upper_name = name.upper()
    return _category(device) == "multilayer_switch" or role in CORE_ROLES or upper_name.startswith(("MLS", "CORE", "DIST"))


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
    return sorted(values, key=_natural_key)


def _natural_key(value: Any) -> tuple[int, Any]:
    text = str(value)
    return (0, int(text)) if text.isdigit() else (1, text)


def _ensure_spec(configs: dict[str, dict[str, Any]], device: str) -> dict[str, Any]:
    return configs.setdefault(device, {"device": device, "hostname": device, "vlans": [], "interfaces": []})


def _add_vlan(spec: dict[str, Any], vlan: str | None) -> None:
    if vlan and not any(str(item.get("id", item.get("vlan", ""))) == vlan for item in spec["vlans"]):
        spec["vlans"].append({"id": int(vlan) if vlan.isdigit() else vlan})


def _interface_record(name: str, mode: str, vlan: str | None) -> dict[str, Any]:
    if mode == "access":
        return {"name": name, "mode": "access", "vlan": vlan}
    return {"name": name, "mode": "trunk", "allowed_vlans": [vlan] if vlan else "all"}


def _add_interface(configs: dict[str, dict[str, Any]], device: str, port: str, mode: str, vlan: str | None) -> None:
    spec = _ensure_spec(configs, device)
    _add_vlan(spec, vlan)
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


def _add_l3_interface(configs: dict[str, dict[str, Any]], device: str, interface: dict[str, Any]) -> None:
    spec = _ensure_spec(configs, device)
    spec["ip_routing"] = True
    for existing in spec["interfaces"]:
        if existing.get("name") == interface.get("name"):
            existing.update({key: value for key, value in interface.items() if value not in (None, "")})
            return
    spec["interfaces"].append(interface)


def _device_vlans(links: list[dict[str, Any]], endpoint_names: set[str]) -> dict[str, str]:
    vlans: dict[str, str] = {}
    for link in links:
        vlan = _vlan(link)
        if not vlan:
            continue
        a = _pick(link, ("a", "device_a", "from", "from_device"))
        b = _pick(link, ("b", "device_b", "to", "to_device"))
        if a in endpoint_names:
            vlans[a] = vlan
        if b in endpoint_names:
            vlans[b] = vlan
    return vlans


def _vlan_owners(links: list[dict[str, Any]], by_name: dict[str, dict[str, Any]], switch_names: set[str]) -> dict[str, str]:
    owners: dict[str, str] = {}
    for link in links:
        vlan = _vlan(link)
        if not vlan or vlan in owners:
            continue
        a = _pick(link, ("a", "device_a", "from", "from_device"))
        b = _pick(link, ("b", "device_b", "to", "to_device"))
        if a not in switch_names or b not in switch_names:
            continue
        a_core = _is_core_switch(a, by_name.get(a, {}))
        b_core = _is_core_switch(b, by_name.get(b, {}))
        if a_core and not b_core:
            owners[vlan] = a
        elif b_core and not a_core:
            owners[vlan] = b
        else:
            owners[vlan] = a
    return owners


def _network_from_host(ip_value: Any, mask_value: Any, where: str) -> ipaddress.IPv4Network:
    if ip_value in (None, "") or mask_value in (None, ""):
        raise ValueError(f"{where}: ip and mask are required")
    try:
        return ipaddress.ip_network(f"{ip_value}/{mask_value}", strict=False)
    except ValueError as exc:
        raise ValueError(f"{where}: invalid IPv4 address/mask") from exc


def _gateway_groups(plan: dict[str, Any], device_vlans: dict[str, str]) -> dict[str, dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for index, config in enumerate(plan.get("pc_configs", [])):
        if not isinstance(config, dict):
            continue
        name = _pick(config, ("name", "device", "host"))
        vlan = device_vlans.get(name)
        gateway = config.get("gateway", config.get("default_gateway", config.get("gw")))
        mask = config.get("mask", config.get("subnet_mask", config.get("netmask")))
        if not vlan or gateway in (None, "") or mask in (None, ""):
            continue
        network = _network_from_host(gateway, mask, f"pc_configs[{index}].gateway")
        existing = groups.get(vlan)
        if existing and (existing["gateway"] != str(gateway) or existing["mask"] != str(mask)):
            raise ValueError(f"VLAN {vlan}: conflicting gateway/mask values in pc_configs")
        groups[vlan] = {"gateway": str(gateway), "mask": str(mask), "network": network}
    return groups


def _extract_link_network(link: dict[str, Any]) -> ipaddress.IPv4Network | None:
    for key in ("l3_subnet", "subnet", "network", "note", "description"):
        value = link.get(key)
        if value in (None, ""):
            continue
        match = re.search(r"\b(?:\d{1,3}\.){3}\d{1,3}/\d{1,2}\b", str(value))
        if not match:
            continue
        try:
            return ipaddress.ip_network(match.group(0), strict=False)
        except ValueError:
            continue
    return None


def _rip_network(ip_value: ipaddress.IPv4Address) -> str:
    octets = str(ip_value).split(".")
    first = int(octets[0])
    if first < 128:
        return f"{octets[0]}.0.0.0"
    if first < 192:
        return f"{octets[0]}.{octets[1]}.0.0"
    return f"{octets[0]}.{octets[1]}.{octets[2]}.0"


def _sorted_networks(values: set[str]) -> list[str]:
    return sorted(values, key=lambda item: tuple(int(part) for part in item.split(".")))


def _ospf_network_record(network: ipaddress.IPv4Network) -> dict[str, Any]:
    return {"network": str(network.network_address), "wildcard": str(network.hostmask), "area": 0}


def _first_hop(adjacency: dict[str, list[dict[str, Any]]], source: str, target: str) -> ipaddress.IPv4Address | None:
    if source == target:
        return None
    queue: list[tuple[str, ipaddress.IPv4Address | None]] = [(source, None)]
    seen = {source}
    while queue:
        device, first_next_hop = queue.pop(0)
        for edge in sorted(adjacency.get(device, []), key=lambda item: str(item["neighbor"])):
            neighbor = str(edge["neighbor"])
            if neighbor in seen:
                continue
            next_hop = first_next_hop or edge["next_hop"]
            if neighbor == target:
                return next_hop
            seen.add(neighbor)
            queue.append((neighbor, next_hop))
    return None


def _add_static_routes(
    configs: dict[str, dict[str, Any]],
    svi_networks: dict[str, list[ipaddress.IPv4Network]],
    adjacency: dict[str, list[dict[str, Any]]],
) -> None:
    l3_devices = sorted(set(svi_networks) | set(adjacency))
    for source in l3_devices:
        local_networks = set(svi_networks.get(source, []))
        routes: dict[tuple[str, str, str], dict[str, str]] = {}
        for target in sorted(svi_networks):
            if target == source:
                continue
            next_hop = _first_hop(adjacency, source, target)
            if next_hop is None:
                raise ValueError(f"{source}: no L3 path to {target} for static route planning")
            for network in svi_networks[target]:
                if network in local_networks:
                    continue
                route = {"destination": str(network.network_address), "mask": str(network.netmask), "next_hop": str(next_hop)}
                routes[(route["destination"], route["mask"], route["next_hop"])] = route
        if routes:
            spec = _ensure_spec(configs, source)
            spec["ip_routing"] = True
            spec["static_routes"] = sorted(routes.values(), key=lambda item: (tuple(int(part) for part in item["destination"].split(".")), item["mask"], item["next_hop"]))


def _add_l3_plan(
    plan: dict[str, Any],
    configs: dict[str, dict[str, Any]],
    by_name: dict[str, dict[str, Any]],
    switch_names: set[str],
    endpoint_names: set[str],
    *,
    routing: str,
) -> None:
    links = [link for link in plan.get("links", []) if isinstance(link, dict)]
    rip_networks: dict[str, set[str]] = {}
    ospf_networks: dict[str, dict[str, ipaddress.IPv4Network]] = {}
    ospf_passive_interfaces: dict[str, set[str]] = {}
    svi_networks: dict[str, list[ipaddress.IPv4Network]] = {}
    adjacency: dict[str, list[dict[str, Any]]] = {}
    device_vlans = _device_vlans(links, endpoint_names)
    vlan_owners = _vlan_owners(links, by_name, switch_names)
    gateway_groups = _gateway_groups(plan, device_vlans)

    for vlan, gateway in sorted(gateway_groups.items(), key=lambda item: _natural_key(item[0])):
        owner = vlan_owners.get(vlan)
        if not owner:
            continue
        spec = _ensure_spec(configs, owner)
        spec["ip_routing"] = True
        _add_vlan(spec, vlan)
        _add_l3_interface(
            configs,
            owner,
            {
                "name": f"Vlan{vlan}",
                "description": f"gateway for VLAN {vlan}",
                "ip": gateway["gateway"],
                "mask": gateway["mask"],
            },
        )
        rip_networks.setdefault(owner, set()).add(_rip_network(ipaddress.ip_address(gateway["gateway"])))
        ospf_networks.setdefault(owner, {})[str(gateway["network"])] = gateway["network"]
        ospf_passive_interfaces.setdefault(owner, set()).add(f"Vlan{vlan}")
        svi_networks.setdefault(owner, []).append(gateway["network"])

    for link in links:
        if _vlan(link):
            continue
        a = _pick(link, ("a", "device_a", "from", "from_device"))
        b = _pick(link, ("b", "device_b", "to", "to_device"))
        pa = _pick(link, ("pa", "port_a", "from_port"))
        pb = _pick(link, ("pb", "port_b", "to_port"))
        if a not in switch_names or b not in switch_names or not pa or not pb:
            continue
        network = _extract_link_network(link)
        if network is None:
            continue
        hosts = list(network.hosts())
        if len(hosts) < 2:
            continue
        a_ip = hosts[0]
        b_ip = hosts[1]
        mask = str(network.netmask)
        _add_l3_interface(configs, a, {"name": pa, "description": f"L3 link to {b} {network}", "mode": "routed", "ip": str(a_ip), "mask": mask})
        _add_l3_interface(configs, b, {"name": pb, "description": f"L3 link to {a} {network}", "mode": "routed", "ip": str(b_ip), "mask": mask})
        rip_networks.setdefault(a, set()).add(_rip_network(a_ip))
        rip_networks.setdefault(b, set()).add(_rip_network(b_ip))
        ospf_networks.setdefault(a, {})[str(network)] = network
        ospf_networks.setdefault(b, {})[str(network)] = network
        adjacency.setdefault(a, []).append({"neighbor": b, "next_hop": b_ip})
        adjacency.setdefault(b, []).append({"neighbor": a, "next_hop": a_ip})

    if routing == "rip":
        for device, networks in rip_networks.items():
            if networks:
                spec = _ensure_spec(configs, device)
                spec["rip"] = {"version": 2, "no_auto_summary": True, "networks": _sorted_networks(networks)}
    elif routing == "ospf":
        for router_id_index, device in enumerate(sorted(ospf_networks), start=1):
            networks = sorted(ospf_networks[device].values(), key=lambda item: int(item.network_address))
            if networks:
                spec = _ensure_spec(configs, device)
                spec["ospf"] = {
                    "process_id": 1,
                    "router_id": f"10.255.0.{router_id_index}",
                    "passive_interfaces": sorted(ospf_passive_interfaces.get(device, set()), key=str),
                    "networks": [_ospf_network_record(network) for network in networks],
                }
    elif routing == "static":
        _add_static_routes(configs, svi_networks, adjacency)


def generated_ios_configs(plan: dict[str, Any], *, include_l3: bool = False, routing: str = "none") -> list[dict[str, Any]]:
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

    if include_l3:
        _add_l3_plan(plan, specs, by_name, switch_names, endpoint_names, routing=routing)

    records = []
    for device in sorted(specs):
        spec = specs[device]
        spec["vlans"] = sorted(spec["vlans"], key=lambda item: _natural_key(item["id"]))
        spec["interfaces"] = sorted(spec["interfaces"], key=lambda item: str(item["name"]))
        records.append({"device": device, "source": SOURCE, "commands": render_commands(spec)})
    return records


def configured_plan(plan: dict[str, Any], *, include_l3: bool = False, routing: str = "none") -> dict[str, Any]:
    result = copy.deepcopy(plan)
    existing = [config for config in result.get("ios_configs", []) if not (isinstance(config, dict) and config.get("source") == SOURCE)]
    result["ios_configs"] = existing + generated_ios_configs(result, include_l3=include_l3, routing=routing)
    return result


def _commands_text(config: dict[str, Any]) -> str:
    raw = config.get("commands", config.get("config", config.get("text", "")))
    if isinstance(raw, list):
        lines = [str(line).rstrip() for line in raw]
        text = "\n".join(lines)
    else:
        text = str(raw).replace("\r\n", "\n").rstrip()
    return text + "\n" if text else ""


def _safe_stem(value: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return stem.strip("._") or "config"


def export_config_files(plan: dict[str, Any], output_dir: Path, *, source: str | None = None) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    used: dict[str, int] = {}
    files: list[dict[str, Any]] = []
    for index, config in enumerate(plan.get("ios_configs", []), start=1):
        if not isinstance(config, dict):
            continue
        if source is not None and str(config.get("source", "")) != source:
            continue
        device = _pick(config, ("device", "name", "router", "switch")) or f"config-{index}"
        stem = _safe_stem(device)
        used[stem] = used.get(stem, 0) + 1
        suffix = "" if used[stem] == 1 else f"-{used[stem]}"
        path = output_dir / f"{stem}{suffix}.cfg"
        text = _commands_text(config)
        path.write_text(text, encoding="utf-8")
        files.append({"device": device, "source": str(config.get("source", "")), "path": str(path), "bytes": len(text.encode("utf-8"))})
    return {"kind": "pt730-config-files", "count": len(files), "files": files}


def schema() -> dict[str, Any]:
    return {
        "commands": ["schema", "campus", "export-configs"],
        "rules": [
            "switch-switch links become trunk interfaces",
            "switch-endpoint links become access interfaces",
            "link.vlan values become VLAN declarations and allowed/access VLANs",
            "--l3 derives VLAN SVI gateways from pc_configs gateway/mask values",
            "--l3 derives routed switch-switch links from note/subnet/network CIDR metadata",
            "--routing rip adds RIPv2 network statements to L3 switch configs",
            "--routing ospf adds OSPF process 1, router IDs, passive SVI interfaces, and network statements to L3 switch configs",
            "--routing static adds static routes between derived SVI networks",
            "existing ios_configs with other sources are preserved",
        ],
        "options": ["--l3", "--routing none|rip|ospf|static", "--ios-only", "--compact", "--output", "export-configs --output-dir", "export-configs --source"],
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
    campus_p.add_argument("--l3", action="store_true", help="derive SVI gateways and routed switch-switch links")
    campus_p.add_argument("--routing", choices=("none", "rip", "ospf", "static"), default="none", help="routing config to derive with --l3")

    export_p = sub.add_parser("export-configs", help="write ios_configs from a topology JSON into .cfg files")
    export_p.add_argument("plan", type=Path)
    export_p.add_argument("--output-dir", type=Path, required=True)
    export_p.add_argument("--source", help="only export ios_configs matching this source")

    args = parser.parse_args(argv)
    try:
        if args.cmd == "schema":
            emit_json(schema(), None, compact=args.compact)
            return 0
        if args.cmd == "campus":
            plan = _load_plan(args.plan)
            include_l3 = bool(args.l3 or args.routing != "none")
            generated = generated_ios_configs(plan, include_l3=include_l3, routing=args.routing)
            if args.ios_only:
                emit_json({"ios_configs": generated}, args.output, compact=args.compact)
            else:
                emit_json(configured_plan(plan, include_l3=include_l3, routing=args.routing), args.output, compact=args.compact)
            return 0
        if args.cmd == "export-configs":
            emit_json(export_config_files(_load_plan(args.plan), args.output_dir, source=args.source), None, compact=args.compact)
            return 0
        raise ValueError(f"unknown command: {args.cmd}")
    except Exception as exc:  # noqa: BLE001
        print(f"pt730-config-plan: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
