#!/usr/bin/env python3
"""Assign deterministic canvas coordinates to Packet Tracer topology plans."""

from __future__ import annotations

import argparse
import copy
import json
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from topology_cli import _load_plan


STYLES = ("auto", "hierarchical", "campus", "lan", "ring", "grid")
ROUTER_MODELS = {"1841", "1941", "2901", "2911", "4321", "4331"}
SWITCH_MODELS = {"2950-24", "2950T", "2960-24TT", "3560-24PS", "3650-24PS"}
ENDPOINT_MODELS = {"PC-PT", "Laptop-PT", "Printer-PT"}
SERVER_MODELS = {"Server-PT"}


@dataclass(frozen=True)
class LayoutOptions:
    style: str = "auto"
    preserve_existing: bool = False
    canvas_width: int = 1280
    canvas_height: int = 960
    spacing_x: int = 180
    spacing_y: int = 160
    margin: int = 80


def _name(device: dict[str, Any], index: int = 0) -> str:
    value = device.get("name", device.get("id"))
    return str(value) if value not in (None, "") else f"device_{index}"


def _natural_key(value: str) -> list[Any]:
    parts = re.split(r"(\d+)", value)
    return [int(part) if part.isdigit() else part.lower() for part in parts]


def _device_text(device: dict[str, Any], index: int = 0) -> str:
    fields = [_name(device, index), str(device.get("category", "")), str(device.get("kind", "")), str(device.get("model", ""))]
    return " ".join(fields).lower()


def _category(device: dict[str, Any]) -> str:
    return str(device.get("category", device.get("kind", ""))).lower().replace("-", "_").replace(" ", "_")


def _model(device: dict[str, Any]) -> str:
    return str(device.get("model", ""))


def _is_router(device: dict[str, Any], index: int = 0) -> bool:
    name = _name(device, index).upper()
    category = _category(device)
    model = _model(device)
    return category in {"router", "asa", "cloud"} or model in ROUTER_MODELS or bool(re.match(r"^(R\d|R[-_]\d|RTR|ROUTER|EDGE|WAN)", name))


def _is_server(device: dict[str, Any], index: int = 0) -> bool:
    text = _device_text(device, index)
    return _category(device) == "server" or _model(device) in SERVER_MODELS or "server" in text or "-srv" in text or "_srv" in text


def _is_endpoint(device: dict[str, Any], index: int = 0) -> bool:
    category = _category(device)
    model = _model(device)
    text = _device_text(device, index)
    return (
        category in {"pc", "laptop", "host", "end_device", "endpoint", "printer"}
        or model in ENDPOINT_MODELS
        or bool(re.match(r"^(PC|HOST|CLIENT|LAPTOP)[-_]?", _name(device, index).upper()))
        or "student" in text
    )


def _is_wireless(device: dict[str, Any], index: int = 0) -> bool:
    text = _device_text(device, index)
    return "wireless" in text or "accesspoint" in text or "access point" in text or _category(device) == "accesspoint"


def _is_core(device: dict[str, Any], index: int = 0) -> bool:
    name = _name(device, index).upper()
    category = _category(device)
    text = _device_text(device, index)
    return (
        category == "multilayer_switch"
        or _is_router(device, index)
        or bool(re.match(r"^(MLS|CORE|DIST|L3|BACKBONE)[-_]?\d*", name))
        or "core" in text
        or "multilayer" in text
    )


def _is_switch(device: dict[str, Any], index: int = 0) -> bool:
    category = _category(device)
    model = _model(device)
    text = _device_text(device, index)
    return category in {"switch", "multilayer_switch"} or model in SWITCH_MODELS or bool(re.match(r"^(SW|MLS|CORE)[-_]?", _name(device, index).upper())) or "switch" in text


def _is_server_switch(device: dict[str, Any], index: int = 0) -> bool:
    name = _name(device, index).upper()
    return _is_switch(device, index) and not _is_core(device, index) and ("SRV" in name or "SERVER" in name or "DMZ" in name)


def _endpoint(link: dict[str, Any], aliases: tuple[str, ...]) -> str:
    for alias in aliases:
        value = link.get(alias)
        if value not in (None, ""):
            return str(value)
    return ""


def _adjacency(plan: dict[str, Any]) -> dict[str, set[str]]:
    names = {_name(device, index) for index, device in enumerate(plan.get("devices", [])) if isinstance(device, dict)}
    graph = {name: set() for name in names}
    for link in plan.get("links", []):
        if not isinstance(link, dict):
            continue
        a = _endpoint(link, ("a", "device_a", "from", "from_device"))
        b = _endpoint(link, ("b", "device_b", "to", "to_device"))
        if a in graph and b in graph:
            graph[a].add(b)
            graph[b].add(a)
    return graph


def _device_map(devices: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {_name(device, index): device for index, device in enumerate(devices)}


def _sort_names(names: list[str]) -> list[str]:
    return sorted(names, key=_natural_key)


def _clamp(value: int, low: int, high: int) -> int:
    if high < low:
        return low
    return max(low, min(high, value))


def _point(x: float, y: float, options: LayoutOptions) -> tuple[int, int]:
    px = _clamp(int(round(x)), 0, options.canvas_width)
    py = _clamp(int(round(y)), 0, options.canvas_height)
    return px, py


def _has_coordinates(device: dict[str, Any]) -> bool:
    return isinstance(device.get("x"), (int, float)) and isinstance(device.get("y"), (int, float))


def _row(names: list[str], y: int, options: LayoutOptions, *, start_x: int | None = None) -> dict[str, tuple[int, int]]:
    if not names:
        return {}
    max_per_row = max(1, int((options.canvas_width - 2 * options.margin) / max(1, options.spacing_x)) + 1)
    positions: dict[str, tuple[int, int]] = {}
    for row_index in range(math.ceil(len(names) / max_per_row)):
        chunk = names[row_index * max_per_row : (row_index + 1) * max_per_row]
        width = (len(chunk) - 1) * options.spacing_x
        x0 = start_x if start_x is not None else (options.canvas_width - width) / 2
        yy = y + row_index * max(90, int(options.spacing_y * 0.7))
        for col, name in enumerate(chunk):
            positions[name] = _point(x0 + col * options.spacing_x, yy, options)
    return positions


def _fanout(names: list[str], parent: tuple[int, int], y: int, options: LayoutOptions) -> dict[str, tuple[int, int]]:
    if not names:
        return {}
    gap = max(70, min(120, int(options.spacing_x * 0.55)))
    width = (len(names) - 1) * gap
    x0 = parent[0] - width / 2
    return {name: _point(x0 + index * gap, y, options) for index, name in enumerate(names)}


def _best_parent(name: str, graph: dict[str, set[str]], by_name: dict[str, dict[str, Any]], candidates: set[str] | None = None) -> str | None:
    neighbors = _sort_names(list(graph.get(name, set())))
    if candidates is not None:
        neighbors = [neighbor for neighbor in neighbors if neighbor in candidates]
    if neighbors:
        return sorted(neighbors, key=lambda neighbor: (-len(graph.get(neighbor, set())), _natural_key(neighbor)))[0]
    return None


def _group_devices(plan: dict[str, Any]) -> dict[str, list[str]]:
    devices = [device for device in plan.get("devices", []) if isinstance(device, dict)]
    groups = {"core": [], "server_switch": [], "access": [], "server": [], "endpoint": [], "wireless": [], "other": []}
    for index, device in enumerate(devices):
        name = _name(device, index)
        if _is_server_switch(device, index):
            groups["server_switch"].append(name)
        elif _is_server(device, index):
            groups["server"].append(name)
        elif _is_wireless(device, index):
            groups["wireless"].append(name)
        elif _is_core(device, index):
            groups["core"].append(name)
        elif _is_switch(device, index):
            groups["access"].append(name)
        elif _is_endpoint(device, index):
            groups["endpoint"].append(name)
        else:
            groups["other"].append(name)
    return {key: _sort_names(value) for key, value in groups.items()}


def _choose_auto_style(plan: dict[str, Any]) -> str:
    groups = _group_devices(plan)
    if groups["core"] and (groups["access"] or groups["server"] or groups["server_switch"]) and len(plan.get("devices", [])) >= 6:
        return "campus"
    devices = [device for device in plan.get("devices", []) if isinstance(device, dict)]
    router_count = len([device for index, device in enumerate(devices) if _is_router(device, index)])
    if router_count >= 3:
        return "ring"
    if len(plan.get("devices", [])) <= 8:
        return "lan"
    return "hierarchical"


def _layout_grid(plan: dict[str, Any], options: LayoutOptions) -> dict[str, tuple[int, int]]:
    names = _sort_names([_name(device, index) for index, device in enumerate(plan.get("devices", [])) if isinstance(device, dict)])
    if not names:
        return {}
    ratio = max(0.3, options.canvas_width / max(1, options.canvas_height))
    columns = max(1, min(len(names), math.ceil(math.sqrt(len(names) * ratio))))
    positions = {}
    for index, name in enumerate(names):
        row = index // columns
        col = index % columns
        positions[name] = _point(options.margin + col * options.spacing_x, options.margin + row * options.spacing_y, options)
    return positions


def _layout_hierarchical(plan: dict[str, Any], options: LayoutOptions) -> dict[str, tuple[int, int]]:
    groups = _group_devices(plan)
    positions: dict[str, tuple[int, int]] = {}
    tiers = [
        groups["core"],
        groups["server_switch"] + groups["access"] + groups["wireless"],
        groups["server"] + groups["endpoint"] + groups["other"],
    ]
    for index, names in enumerate(tiers):
        positions.update(_row(names, options.margin + index * options.spacing_y, options))
    return positions


def _layout_lan(plan: dict[str, Any], options: LayoutOptions) -> dict[str, tuple[int, int]]:
    groups = _group_devices(plan)
    graph = _adjacency(plan)
    by_name = _device_map([device for device in plan.get("devices", []) if isinstance(device, dict)])
    network = groups["core"] + groups["server_switch"] + groups["access"] + groups["wireless"] + groups["other"]
    endpoints = groups["server"] + groups["endpoint"]
    positions = _row(network, options.margin + options.spacing_y, options, start_x=options.margin)
    if not network:
        positions.update(_row(endpoints, options.margin + options.spacing_y, options, start_x=options.margin))
        return positions
    network_set = set(network)
    children_by_parent: dict[str, list[str]] = {name: [] for name in network}
    for child in endpoints:
        parent = _best_parent(child, graph, by_name, network_set) or network[min(len(network) - 1, len(network) // 2)]
        children_by_parent.setdefault(parent, []).append(child)
    for parent in network:
        children = _sort_names(children_by_parent.get(parent, []))
        if not children:
            continue
        positions.update(_fanout(children, positions[parent], positions[parent][1] + options.spacing_y, options))
    return positions


def _layout_campus(plan: dict[str, Any], options: LayoutOptions) -> dict[str, tuple[int, int]]:
    groups = _group_devices(plan)
    graph = _adjacency(plan)
    by_name = _device_map([device for device in plan.get("devices", []) if isinstance(device, dict)])
    positions: dict[str, tuple[int, int]] = {}

    server_y = options.margin
    server_switch_y = options.margin + options.spacing_y
    core_y = options.margin + options.spacing_y * 2
    access_y = options.margin + options.spacing_y * 3
    endpoint_y = options.margin + options.spacing_y * 4

    core = groups["core"]
    if not core:
        switchish = groups["server_switch"] + groups["access"] + groups["wireless"]
        degrees = sorted(switchish, key=lambda name: (-len(graph.get(name, set())), _natural_key(name)))
        core = _sort_names(degrees[: max(1, min(3, len(degrees)))])

    positions.update(_row(groups["server"], server_y, options))
    positions.update(_row(groups["server_switch"], server_switch_y, options))
    positions.update(_row(core, core_y, options))

    core_set = set(core)
    access = [name for name in groups["access"] + groups["wireless"] + groups["other"] if name not in core_set]
    positions.update(_row(access, access_y, options))

    network_set = set(core + groups["server_switch"] + access)
    children_by_parent: dict[str, list[str]] = {name: [] for name in network_set}
    for child in groups["endpoint"]:
        parent = _best_parent(child, graph, by_name, network_set)
        if parent is None:
            parent = access[0] if access else (core[0] if core else None)
        if parent is not None:
            children_by_parent.setdefault(parent, []).append(child)
    for parent in _sort_names(list(children_by_parent)):
        children = _sort_names(children_by_parent[parent])
        if children and parent in positions:
            parent_y = positions[parent][1]
            positions.update(_fanout(children, positions[parent], max(parent_y + options.spacing_y, endpoint_y), options))

    return positions


def _layout_ring(plan: dict[str, Any], options: LayoutOptions) -> dict[str, tuple[int, int]]:
    groups = _group_devices(plan)
    graph = _adjacency(plan)
    by_name = _device_map([device for device in plan.get("devices", []) if isinstance(device, dict)])
    all_names = _sort_names(list(by_name))
    ring = groups["core"]
    if len(ring) < 3:
        ring = groups["core"] + groups["server_switch"] + groups["access"] + groups["wireless"]
    if len(ring) < 3:
        ring = all_names
    ring = _sort_names(ring)
    positions: dict[str, tuple[int, int]] = {}
    if not ring:
        return positions

    cx = options.canvas_width / 2
    cy = options.canvas_height / 2
    radius = max(100, min(options.canvas_width, options.canvas_height) * 0.30)
    for index, name in enumerate(ring):
        angle = -math.pi / 2 + (2 * math.pi * index / len(ring))
        positions[name] = _point(cx + math.cos(angle) * radius, cy + math.sin(angle) * radius, options)

    ring_set = set(ring)
    children_by_parent: dict[str, list[str]] = {name: [] for name in ring}
    for name in all_names:
        if name in ring_set:
            continue
        parent = _best_parent(name, graph, by_name, ring_set) or ring[0]
        children_by_parent.setdefault(parent, []).append(name)
    for parent in ring:
        children = _sort_names(children_by_parent.get(parent, []))
        if not children:
            continue
        px, py = positions[parent]
        dx = px - cx
        dy = py - cy
        length = math.hypot(dx, dy) or 1.0
        base_x = px + dx / length * options.spacing_x * 0.75
        base_y = py + dy / length * options.spacing_y * 0.75
        positions.update(_fanout(children, _point(base_x, base_y, options), int(base_y), options))
    return positions


def _avoid_collisions(
    positions: dict[str, tuple[int, int]],
    plan: dict[str, Any],
    options: LayoutOptions,
    *,
    preserved: set[str],
) -> dict[str, tuple[int, int]]:
    occupied: dict[tuple[int, int], str] = {}
    result: dict[str, tuple[int, int]] = {}
    devices = [device for device in plan.get("devices", []) if isinstance(device, dict)]
    ordered_names = [_name(device, index) for index, device in enumerate(devices)]
    for name in ordered_names:
        point = positions.get(name)
        if point is None:
            continue
        if name in preserved:
            result[name] = point
            occupied[point] = name
            continue
        x, y = point
        attempts = 0
        while (x, y) in occupied:
            attempts += 1
            x = _clamp(point[0] + 45 * attempts, 0, options.canvas_width)
            y = _clamp(point[1] + 35 * attempts, 0, options.canvas_height)
            if attempts > 20:
                y = _clamp(point[1] + options.spacing_y, 0, options.canvas_height)
                break
        result[name] = (x, y)
        occupied[(x, y)] = name
    return result


def layout_plan(plan: dict[str, Any], options: LayoutOptions) -> dict[str, Any]:
    laid_out = copy.deepcopy(plan)
    devices = [device for device in laid_out.get("devices", []) if isinstance(device, dict)]
    chosen = _choose_auto_style(laid_out) if options.style == "auto" else options.style
    if chosen == "grid":
        positions = _layout_grid(laid_out, options)
    elif chosen == "hierarchical":
        positions = _layout_hierarchical(laid_out, options)
    elif chosen == "campus":
        positions = _layout_campus(laid_out, options)
    elif chosen == "lan":
        positions = _layout_lan(laid_out, options)
    elif chosen == "ring":
        positions = _layout_ring(laid_out, options)
    else:
        raise ValueError(f"unsupported layout style: {chosen}")

    if len(positions) < len(devices):
        fallback = _layout_grid(laid_out, options)
        for name, point in fallback.items():
            positions.setdefault(name, point)

    preserved: set[str] = set()
    if options.preserve_existing:
        for index, device in enumerate(devices):
            name = _name(device, index)
            if _has_coordinates(device):
                positions[name] = (int(device["x"]), int(device["y"]))
                preserved.add(name)

    positions = _avoid_collisions(positions, laid_out, options, preserved=preserved)
    for index, device in enumerate(devices):
        name = _name(device, index)
        if options.preserve_existing and name in preserved:
            continue
        x, y = positions[name]
        device["x"] = x
        device["y"] = y
    return laid_out


def _emit(plan: dict[str, Any], output: Path | None, *, compact: bool) -> None:
    text = json.dumps(plan, ensure_ascii=False, indent=None if compact else 2, separators=(",", ":") if compact else None) + "\n"
    if output is None:
        print(text, end="")
        return
    output.write_text(text, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pt730-layout", description=__doc__)
    parser.add_argument("plan", type=Path, help="topology JSON plan to lay out")
    parser.add_argument("--style", choices=STYLES, default="auto", help="layout style, default: auto")
    parser.add_argument("--output", type=Path, help="write JSON to a file instead of stdout")
    parser.add_argument("--preserve-existing", action="store_true", help="do not replace existing numeric x/y coordinates")
    parser.add_argument("--canvas-width", type=int, default=1280, help="target Packet Tracer canvas width")
    parser.add_argument("--canvas-height", type=int, default=960, help="target Packet Tracer canvas height")
    parser.add_argument("--spacing-x", type=int, default=180, help="horizontal device spacing")
    parser.add_argument("--spacing-y", type=int, default=160, help="vertical device spacing")
    parser.add_argument("--margin", type=int, default=80, help="outer layout margin")
    parser.add_argument("--compact", action="store_true", help="emit compact JSON")
    args = parser.parse_args(argv)

    try:
        if args.canvas_width <= 0 or args.canvas_height <= 0:
            raise ValueError("canvas dimensions must be positive")
        if args.spacing_x <= 0 or args.spacing_y <= 0:
            raise ValueError("spacing values must be positive")
        if args.margin < 0:
            raise ValueError("margin must be non-negative")
        plan = _load_plan(args.plan)
        laid_out = layout_plan(
            plan,
            LayoutOptions(
                style=args.style,
                preserve_existing=args.preserve_existing,
                canvas_width=args.canvas_width,
                canvas_height=args.canvas_height,
                spacing_x=args.spacing_x,
                spacing_y=args.spacing_y,
                margin=args.margin,
            ),
        )
        _emit(laid_out, args.output, compact=args.compact)
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"pt730-layout: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
