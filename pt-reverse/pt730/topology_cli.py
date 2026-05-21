#!/usr/bin/env python3
"""Packet Tracer 7.3.0 topology CLI over the local Script Module bridge."""

from __future__ import annotations

import argparse
import ipaddress
import json
import re
import socket
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from model_registry import risky_model_notes, safe_model_names


DEFAULT_BRIDGE = "http://127.0.0.1:54321"


CABLE_CODES = {
    "straight": 8100,
    "ethernet-straight": 8100,
    "copper-straight": 8100,
    "cross": 8101,
    "ethernet-cross": 8101,
    "copper-cross": 8101,
    "roll": 8102,
    "rollover": 8102,
    "fiber": 8103,
    "phone": 8104,
    "cable": 8105,
    "serial": 8106,
    "auto": 8107,
    "console": 8108,
    "wireless": 8109,
    "coaxial": 8110,
    "octal": 8111,
    "cellular": 8112,
    "usb": 8113,
    "custom_io": 8114,
}


DEVICE_TYPES = {
    "router": 0,
    "switch": 1,
    "hub": 2,
    "wireless": 7,
    "accesspoint": 7,
    "pc": 8,
    "server": 9,
    "multilayer_switch": 16,
    "laptop": 18,
    "asa": 27,
}


MODULE_TYPES = {
    "HWIC-1GE-SFP": 2,
    "HWIC-2T": 2,
    "HWIC-4ESW": 2,
    "HWIC-8A": 2,
    "HWIC-AP-AG-B": 2,
    "NIM-2T": 2,
    "NIM-ES2-4": 2,
    "WIC-1AM": 2,
    "WIC-1ENET": 2,
    "WIC-1T": 2,
    "WIC-2AM": 2,
    "WIC-2T": 2,
}


PT730_SAFE_MODELS = safe_model_names()
PT730_RISKY_MODELS = risky_model_notes()
PT730_VERIFIED_MODULES = {"HWIC-2T"}
PT730_VERIFIED_CABLES = {8100, 8101, 8106}
PT730_MODEL_PORTS = {
    "2911": {"GigabitEthernet0/0", "GigabitEthernet0/1", "GigabitEthernet0/2"},
    "2960-24TT": {
        *(f"FastEthernet0/{i}" for i in range(1, 25)),
        "GigabitEthernet0/1",
        "GigabitEthernet0/2",
    },
    "PC-PT": {"FastEthernet0"},
    "Server-PT": {"FastEthernet0"},
}
PT730_MODULE_PORTS = {
    "HWIC-2T": {"Serial0/0/0", "Serial0/0/1"},
}
PHYSICAL_INTERFACE_PREFIXES = ("FastEthernet", "GigabitEthernet", "Ethernet", "Serial")
VIRTUAL_INTERFACE_PREFIXES = ("Vlan", "Loopback", "Port-channel", "Tunnel", "Null")


def _request(url: str, body: str | None = None, timeout: float = 10.0) -> tuple[int, str]:
    data = body.encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if body is not None else "GET")
    if body is not None:
        req.add_header("Content-Type", "text/plain; charset=utf-8")
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.status, response.read().decode("utf-8", "replace")


def _wrap(js: str, *, request_id: str, result_url: str) -> str:
    request_id_json = json.dumps(request_id)
    result_url_json = json.dumps(result_url)
    return (
        "function __ptPost(ok,v){"
        f"var __payload=JSON.stringify({{pt730_request_id:{request_id_json},ok:!!ok,value:String(v)}});"
        f"var __url={result_url_json};"
        "var __inner=\"var x=new XMLHttpRequest();\"+"
        "\"x.open('POST',\"+JSON.stringify(__url)+\",true);\"+"
        "\"x.setRequestHeader('Content-Type','text/plain;charset=utf-8');\"+"
        "\"x.send(\"+JSON.stringify(__payload)+\");\";"
        "window.webview.evaluateJavaScriptAsync(__inner);"
        "}"
        "try{var __r=(function(){"
        + js
        + "})();__ptPost(true,__r === undefined ? 'undefined' : __r);}"
        "catch(__e){__ptPost(false,__e && (__e.stack || __e.message) ? (__e.stack || __e.message) : __e);}"
    )


def _decode_tagged_result(body: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    if "pt730_request_id" not in parsed:
        return None
    return parsed


def eval_js(js: str, bridge: str, timeout: float) -> str:
    try:
        status, body = _request(f"{bridge}/status", timeout=3.0)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"bridge status failed: {exc}") from exc

    if status != 200 or '"connected": true' not in body:
        raise RuntimeError(f"bridge not connected: {body}")

    # PTBuilder 7.3.0 is unreliable with multi-line runCode payloads. Keep the
    # payload one-line while preserving string-literal contents inside each line.
    one_line_js = " ".join(line.strip() for line in js.splitlines() if line.strip())
    request_id = uuid.uuid4().hex
    result_url = f"{bridge.rstrip('/')}/result"
    _request(f"{bridge}/queue", _wrap(one_line_js, request_id=request_id, result_url=result_url), timeout=3.0)

    deadline = time.monotonic() + timeout
    stale = 0
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            detail = f"; discarded {stale} stale result(s)" if stale else ""
            raise TimeoutError(f"timed out waiting for Packet Tracer result {request_id}{detail}")
        try:
            status, body = _request(f"{bridge}/result?request_id={request_id}", timeout=min(remaining, 9.5))
        except (TimeoutError, socket.timeout):
            continue
        if status == 204:
            continue
        tagged = _decode_tagged_result(body)
        if not tagged or tagged.get("pt730_request_id") != request_id:
            stale += 1
            continue
        value = str(tagged.get("value", ""))
        if not tagged.get("ok", False):
            raise RuntimeError(value)
        return value


def _load_plan(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        plan = json.load(f)
    if not isinstance(plan, dict):
        raise ValueError("topology plan must be a JSON object")
    plan.setdefault("devices", [])
    plan.setdefault("modules", [])
    plan.setdefault("links", [])
    plan.setdefault("pc_configs", [])
    plan.setdefault("server_configs", [])
    plan.setdefault("ios_configs", [])
    if not isinstance(plan["devices"], list) or not isinstance(plan["links"], list):
        raise ValueError("plan.devices and plan.links must be arrays")
    if not isinstance(plan["modules"], list):
        raise ValueError("plan.modules must be an array")
    if not isinstance(plan["pc_configs"], list):
        raise ValueError("plan.pc_configs must be an array")
    if not isinstance(plan["server_configs"], list):
        raise ValueError("plan.server_configs must be an array")
    if not isinstance(plan["ios_configs"], list):
        raise ValueError("plan.ios_configs must be an array")
    return plan


def _safety_issue(level: str, where: str, message: str) -> dict[str, str]:
    return {"level": level, "where": where, "message": message}


def _config_commands(config: dict[str, Any]) -> list[str]:
    raw = config.get("commands", config.get("cmds", config.get("config", config.get("cli", []))))
    if isinstance(raw, str):
        return [line.strip() for line in raw.splitlines() if line.strip() and not line.strip().startswith("!")]
    if isinstance(raw, list):
        return [str(line).strip() for line in raw if str(line).strip() and not str(line).strip().startswith("!")]
    return []


def _interface_blocks(commands: list[str]) -> dict[str, list[str]]:
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


def _is_physical_interface(name: str) -> bool:
    return name.startswith(PHYSICAL_INTERFACE_PREFIXES) and not name.startswith(VIRTUAL_INTERFACE_PREFIXES)


def _interface_needs_no_shutdown(commands: list[str]) -> bool:
    return any(command.lower().startswith(("ip address ", "switchport ")) for command in commands)


def _has_command(commands: list[str], command: str) -> bool:
    target = command.lower()
    return any(line.lower() == target for line in commands)


def _has_command_prefix(commands: list[str], prefix: str) -> bool:
    target = prefix.lower()
    return any(line.lower().startswith(target) for line in commands)


def _plan_safety_issues(plan: dict[str, Any]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    device_names: set[str] = set()
    device_ports: dict[str, set[str]] = {}
    serial_links: list[tuple[str, str, str, str]] = []
    ios_interface_blocks: dict[tuple[str, str], list[str]] = {}
    for index, device in enumerate(plan.get("devices", [])):
        if not isinstance(device, dict):
            issues.append(_safety_issue("error", f"devices[{index}]", "device entry must be an object"))
            continue
        name = str(device.get("name", device.get("id", "")))
        if not name:
            issues.append(_safety_issue("error", f"devices[{index}]", "device name is missing"))
        elif name in device_names:
            issues.append(_safety_issue("error", f"devices[{index}]", f"{name}: duplicate device name"))
        else:
            device_names.add(name)
        model = str(device.get("model", ""))
        if name and model in PT730_MODEL_PORTS:
            device_ports[name] = set(PT730_MODEL_PORTS[model])
        if not model:
            issues.append(_safety_issue("error", f"devices[{index}]", "device model is missing"))
        elif model in PT730_RISKY_MODELS:
            issues.append(_safety_issue("error", f"devices[{index}]", f"{model}: {PT730_RISKY_MODELS[model]}"))
        elif model not in PT730_SAFE_MODELS:
            issues.append(_safety_issue("warning", f"devices[{index}]", f"{model}: not live-verified on this PT 7.3.0 setup"))

    for index, module in enumerate(plan.get("modules", [])):
        if not isinstance(module, dict):
            issues.append(_safety_issue("error", f"modules[{index}]", "module entry must be an object"))
            continue
        model = str(module.get("model", module.get("module", module.get("name", ""))))
        if model and model not in PT730_VERIFIED_MODULES:
            issues.append(_safety_issue("warning", f"modules[{index}]", f"{model}: module is not live-verified on this PT 7.3.0 setup"))
        device_name = str(module.get("device", module.get("device_name", module.get("on", ""))))
        if device_name and device_name not in device_names:
            issues.append(_safety_issue("error", f"modules[{index}]", f"{device_name}: unknown module target device"))
        if device_name in device_ports and model in PT730_MODULE_PORTS:
            device_ports[device_name].update(PT730_MODULE_PORTS[model])

    def check_port(where: str, device_name: str, port_name: str) -> None:
        ports = device_ports.get(device_name)
        if ports is not None and port_name and port_name not in ports:
            issues.append(_safety_issue("error", where, f"{device_name}:{port_name}: unknown port"))

    def check_ipv4(where: str, label: str, value: Any) -> ipaddress.IPv4Address | None:
        if value in (None, ""):
            return None
        try:
            return ipaddress.ip_address(str(value))
        except ValueError:
            issues.append(_safety_issue("error", where, f"{label}: invalid IPv4 address {value}"))
            return None

    def check_ip_subnet(where: str, ip_value: Any, mask_value: Any, gateway_value: Any) -> None:
        ip_addr = check_ipv4(where, "ip", ip_value)
        check_ipv4(where, "mask", mask_value)
        gateway = check_ipv4(where, "gateway", gateway_value)
        if ip_addr is None or gateway is None or mask_value in (None, ""):
            return
        try:
            network = ipaddress.ip_network(f"{ip_addr}/{mask_value}", strict=False)
        except ValueError:
            issues.append(_safety_issue("error", where, f"mask: invalid IPv4 network mask {mask_value}"))
            return
        if gateway not in network:
            issues.append(_safety_issue("error", where, f"{gateway}: gateway outside subnet {network}"))

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
            network = ipaddress.ip_network(f"{network_value}/{mask_value}", strict=False)
        except ValueError:
            issues.append(_safety_issue("error", where, f"{network_value}/{mask_value}: invalid DHCP network"))
            return
        for field in ("start", "start_ip", "first_ip", "end", "end_ip", "last_ip", "gateway", "default_gateway", "router", "dns", "dns_server"):
            if field not in dhcp or dhcp.get(field) in (None, ""):
                continue
            address = check_ipv4(where, field, dhcp.get(field))
            if address is not None and field not in {"dns", "dns_server"} and address not in network:
                issues.append(_safety_issue("error", where, f"{field}={address}: outside DHCP network {network}"))

    for index, link in enumerate(plan.get("links", [])):
        if not isinstance(link, dict):
            issues.append(_safety_issue("error", f"links[{index}]", "link entry must be an object"))
            continue
        a = str(link.get("a", link.get("device_a", link.get("from", link.get("from_device", "")))))
        b = str(link.get("b", link.get("device_b", link.get("to", link.get("to_device", "")))))
        pa = str(link.get("pa", link.get("port_a", link.get("from_port", ""))))
        pb = str(link.get("pb", link.get("port_b", link.get("to_port", ""))))
        if not a or not b or not pa or not pb:
            issues.append(_safety_issue("error", f"links[{index}]", "link requires a/pa/b/pb"))
        for endpoint in (a, b):
            if endpoint and endpoint not in device_names:
                issues.append(_safety_issue("error", f"links[{index}]", f"{endpoint}: unknown endpoint device"))
        check_port(f"links[{index}]", a, pa)
        check_port(f"links[{index}]", b, pb)
        cable = str(link.get("cable", link.get("type", "straight")))
        key = cable.lower().replace(" ", "-")
        code = int(cable) if cable.isdigit() else CABLE_CODES.get(key)
        if code is None:
            issues.append(_safety_issue("error", f"links[{index}]", f"{cable}: unknown cable type"))
        elif int(code) not in PT730_VERIFIED_CABLES:
            issues.append(_safety_issue("warning", f"links[{index}]", f"{cable}: cable code {code} is not live-verified locally"))
        if code == CABLE_CODES["serial"] or pa.lower().startswith("serial") or pb.lower().startswith("serial"):
            serial_links.append((a, pa, b, pb))

    for index, config in enumerate(plan.get("pc_configs", [])):
        if not isinstance(config, dict):
            issues.append(_safety_issue("error", f"pc_configs[{index}]", "pc config entry must be an object"))
            continue
        name = str(config.get("name", config.get("device", config.get("pc", ""))))
        if name and name not in device_names:
            issues.append(_safety_issue("error", f"pc_configs[{index}]", f"{name}: unknown configured device"))
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
            issues.append(_safety_issue("warning", f"pc_configs[{index}]", f"{name}: DHCP client validation is guarded; static IP is safer for unattended smoke tests"))

    for collection, aliases in (
        ("server_configs", ("name", "device", "server")),
        ("ios_configs", ("name", "device", "router", "switch")),
    ):
        for index, config in enumerate(plan.get(collection, [])):
            if not isinstance(config, dict):
                issues.append(_safety_issue("error", f"{collection}[{index}]", f"{collection} entry must be an object"))
                continue
            name = ""
            for alias in aliases:
                if config.get(alias):
                    name = str(config.get(alias))
                    break
            if name and name not in device_names:
                issues.append(_safety_issue("error", f"{collection}[{index}]", f"{name}: unknown configured device"))
            if collection == "server_configs":
                check_port(f"{collection}[{index}]", name, str(config.get("port", "FastEthernet0")))
                check_dhcp_pool(f"{collection}[{index}].dhcp", config.get("dhcp"))
            elif collection == "ios_configs":
                blocks = _interface_blocks(_config_commands(config))
                for interface, commands in blocks.items():
                    ios_interface_blocks[(name, interface)] = commands
                    ports = device_ports.get(name)
                    if ports is not None and _is_physical_interface(interface) and interface not in ports:
                        issues.append(_safety_issue("error", f"{collection}[{index}]", f"{name}:{interface}: unknown IOS interface"))
                    if _interface_needs_no_shutdown(commands) and not _has_command(commands, "no shutdown") and not _has_command(commands, "shutdown"):
                        issues.append(_safety_issue("warning", f"{collection}[{index}]", f"{name}:{interface}: configured IOS interface has no no shutdown"))
    for a, pa, b, pb in serial_links:
        a_commands = ios_interface_blocks.get((a, pa), [])
        b_commands = ios_interface_blocks.get((b, pb), [])
        if not _has_command_prefix(a_commands, "clock rate ") and not _has_command_prefix(b_commands, "clock rate "):
            issues.append(_safety_issue("warning", "links", f"{a}:{pa} <-> {b}:{pb}: serial link has no clock rate on either endpoint"))
    return issues


def _enforce_plan_safety(plan: dict[str, Any], *, allow_risky: bool, strict: bool) -> None:
    issues = _plan_safety_issues(plan)
    blocking = []
    for issue in issues:
        if issue["level"] == "error" and allow_risky:
            print(f"pt730-topo: safety override: {issue['where']}: {issue['message']}", file=sys.stderr)
            continue
        if issue["level"] == "warning" and not strict:
            print(f"pt730-topo: safety warning: {issue['where']}: {issue['message']}", file=sys.stderr)
            continue
        blocking.append(issue)
    if blocking:
        detail = "; ".join(f"{issue['where']}: {issue['message']}" for issue in blocking)
        raise ValueError(f"safety check failed: {detail}")


def _plan_summary(plan: dict[str, Any]) -> dict[str, Any]:
    device_names = [str(device.get("name", device.get("id", ""))) for device in plan.get("devices", []) if isinstance(device, dict)]
    return {
        "dry_run": True,
        "counts": {
            "devices": len(plan.get("devices", [])),
            "modules": len(plan.get("modules", [])),
            "links": len(plan.get("links", [])),
            "pc_configs": len(plan.get("pc_configs", [])),
            "server_configs": len(plan.get("server_configs", [])),
            "ios_configs": len(plan.get("ios_configs", [])),
        },
        "devices": device_names,
        "safety_issues": _plan_safety_issues(plan),
    }


def _apply_js(plan: dict[str, Any], *, replace: bool) -> str:
    payload = {
        "devices": plan["devices"],
        "modules": plan.get("modules", []),
        "links": plan["links"],
        "pcConfigs": plan["pc_configs"],
        "serverConfigs": plan["server_configs"],
        "iosConfigs": plan["ios_configs"],
        "replace": replace or bool(plan.get("replace")),
        "cableCodes": CABLE_CODES,
        "deviceTypes": DEVICE_TYPES,
        "moduleTypes": MODULE_TYPES,
    }
    plan_json = json.dumps(payload, ensure_ascii=False)
    return f"""
var plan = {plan_json};
var net = ipc.network();
var lw = ipc.appWindow().getActiveWorkspace().getLogicalWorkspace();

function fail(msg) {{
  throw new Error(msg);
}}

function pick(obj, names, fallback) {{
  for (var i = 0; i < names.length; i++) {{
    if (obj[names[i]] !== undefined && obj[names[i]] !== null) return obj[names[i]];
  }}
  return fallback;
}}

function deviceByName(name) {{
  try {{
    var d = net.getDevice(String(name));
    if (d && d.getName) return d;
  }} catch (e) {{}}
  return null;
}}

function portByName(deviceName, portName) {{
  var d = deviceByName(deviceName);
  if (!d) fail("device not found: " + deviceName);
  try {{
    var p = d.getPort(String(portName));
    if (p && p.getName) return p;
  }} catch (e) {{}}
  fail("port not found: " + deviceName + ":" + portName);
}}

function cableCode(value) {{
  var v = value === undefined || value === null ? "straight" : String(value);
  var key = v.toLowerCase().replace(/ /g, "-");
  if (plan.cableCodes[key] !== undefined) return String(plan.cableCodes[key]);
  if (/^[0-9]+$/.test(v)) return v;
  fail("unknown cable type: " + v);
}}

function deviceType(spec) {{
  var explicit = pick(spec, ["type", "type_id", "device_type", "devType"], null);
  if (explicit !== null) return String(explicit);
  var category = String(pick(spec, ["category", "kind"], "")).toLowerCase();
  if (plan.deviceTypes[category] !== undefined) return String(plan.deviceTypes[category]);
  fail("device type missing for " + spec.name + "; use type/type_id or category");
}}

function moduleType(spec) {{
  var explicit = pick(spec, ["module_type", "type", "type_id"], null);
  if (explicit !== null) return String(explicit);
  var model = String(pick(spec, ["model", "module", "name"], ""));
  if (plan.moduleTypes[model] !== undefined) return String(plan.moduleTypes[model]);
  fail("module type missing for " + model + "; use module_type/type_id");
}}

function linkExists(a, pa, b, pb) {{
  var count = net.getLinkCount();
  for (var i = 0; i < count; i++) {{
    var l = net.getLinkAt(i);
    var p1 = l.getPort1();
    var p2 = l.getPort2();
    var a1 = p1.getOwnerDevice().getName();
    var b1 = p2.getOwnerDevice().getName();
    var pa1 = p1.getName();
    var pb1 = p2.getName();
    if ((a1 === a && pa1 === pa && b1 === b && pb1 === pb) ||
        (a1 === b && pa1 === pb && b1 === a && pb1 === pa)) {{
      return true;
    }}
  }}
  return false;
}}

function portLink(deviceName, portName) {{
  var p = portByName(deviceName, portName);
  try {{ return p.getLink(); }} catch (e) {{ return null; }}
}}

function moveDevice(name, x, y) {{
  if (x === undefined || y === undefined) return;
  try {{ lw.setCanvasItemRealPos(String(name), Number(x), Number(y)); return; }} catch (e) {{}}
  try {{ deviceByName(name).moveToLocation(Number(x), Number(y)); }} catch (e2) {{}}
}}

function removeIfExists(name) {{
  if (!deviceByName(name)) return false;
  var ok = lw.removeDevice(String(name));
  return !!ok;
}}

function addOneDevice(spec) {{
  var name = String(pick(spec, ["name", "id"], ""));
  if (!name) fail("device without name");
  var x = Number(pick(spec, ["x"], 100));
  var y = Number(pick(spec, ["y"], 100));
  var existing = deviceByName(name);
  if (existing) {{
    moveDevice(name, x, y);
    return {{name: name, status: "exists"}};
  }}
  var model = String(pick(spec, ["model"], ""));
  if (!model) fail("device model missing for " + name);
  var assigned = lw.addDevice(deviceType(spec), model, x, y);
  if (!assigned) fail("Packet Tracer refused device " + name + " model=" + model);
  var d = deviceByName(assigned);
  if (!d) fail("created device not found: " + assigned);
  if (assigned !== name) d.setName(name);
  moveDevice(name, x, y);
  return {{name: name, assigned: String(assigned), model: model, status: "added"}};
}}

function addOneModule(spec) {{
  var deviceName = String(pick(spec, ["device", "device_name", "on"], ""));
  var slot = String(pick(spec, ["slot"], ""));
  var model = String(pick(spec, ["model", "module", "name"], ""));
  if (!deviceName || !slot || !model) fail("module requires device/slot/model");
  var d = deviceByName(deviceName);
  if (!d) fail("device not found for module: " + deviceName);
  if (typeof d.addModule !== "function") fail("device does not support addModule: " + deviceName);
  var hadPower = false;
  var canPower = typeof d.getPower === "function" && typeof d.setPower === "function";
  if (canPower) {{
    try {{ hadPower = !!d.getPower(); d.setPower(false); }} catch (e) {{}}
  }}
  var ret = d.addModule(slot, moduleType(spec), model);
  if (canPower) {{
    try {{ d.setPower(hadPower); if (hadPower && typeof d.skipBoot === "function") d.skipBoot(); }} catch (e2) {{}}
  }}
  if (ret !== true) fail("Packet Tracer refused module " + model + " on " + deviceName + ":" + slot);
  return {{device: deviceName, slot: slot, model: model, status: "added"}};
}}

function addOneLink(spec) {{
  var a = String(pick(spec, ["a", "device_a", "from", "from_device"], ""));
  var b = String(pick(spec, ["b", "device_b", "to", "to_device"], ""));
  var pa = String(pick(spec, ["pa", "port_a", "from_port"], ""));
  var pb = String(pick(spec, ["pb", "port_b", "to_port"], ""));
  if (!a || !b || !pa || !pb) fail("link requires a/pa/b/pb");
  if (linkExists(a, pa, b, pb)) return {{a: a, pa: pa, b: b, pb: pb, status: "exists"}};
  if (portLink(a, pa)) fail("port already linked: " + a + ":" + pa);
  if (portLink(b, pb)) fail("port already linked: " + b + ":" + pb);
  var code = cableCode(pick(spec, ["cable", "type", "link_type", "cable_type"], "straight"));
  var before = net.getLinkCount();
  var ret = lw.createLink(a, pa, b, pb, code);
  var after = net.getLinkCount();
  if (!ret && after <= before) fail("Packet Tracer refused link " + a + ":" + pa + " -> " + b + ":" + pb);
  return {{a: a, pa: pa, b: b, pb: pb, cable: code, status: "added"}};
}}

function configurePc(spec) {{
  var name = String(pick(spec, ["name", "device", "pc"], ""));
  if (!name) fail("pc config without device name");
  var d = deviceByName(name);
  if (!d) fail("device not found for pc config: " + name);
  var portName = String(pick(spec, ["port"], "FastEthernet0"));
  var p = portByName(name, portName);
  var dhcp = pick(spec, ["dhcp", "dhcp_enabled", "dhcpEnabled"], null);
  var ip = pick(spec, ["ip", "ip_address", "address"], null);
  var mask = pick(spec, ["mask", "subnet_mask", "netmask"], "255.255.255.0");
  var gateway = pick(spec, ["gateway", "default_gateway", "gw"], null);
  var dns = pick(spec, ["dns", "dns_server"], null);
  if (dhcp !== null) {{
    if (typeof d.setDhcpFlag !== "function") fail("device has no DHCP flag API: " + name);
    d.setDhcpFlag(!!dhcp);
  }}
  if (ip) p.setIpSubnetMask(String(ip), String(mask));
  if (gateway) p.setDefaultGateway(String(gateway));
  if (dns) p.setDnsServerIp(String(dns));
  return {{name: name, port: portName, dhcp: dhcp === null ? null : !!dhcp, ip: ip ? String(ip) : "", mask: ip ? String(mask) : "", status: "configured"}};
}}

function configureServer(spec) {{
  var name = String(pick(spec, ["name", "device", "server"], ""));
  if (!name) fail("server config without device name");
  var d = deviceByName(name);
  if (!d) fail("device not found for server config: " + name);
  var portName = String(pick(spec, ["port"], "FastEthernet0"));
  var result = {{name: name, port: portName, status: "configured"}};

  var httpEnabled = pick(spec, ["http", "http_enabled"], null);
  if (httpEnabled !== null) {{
    var http = d.getProcess("HttpServerProcess");
    if (!http || typeof http.setEnable !== "function") fail("HTTP process not writable on " + name);
    http.setEnable(!!httpEnabled);
    result.http = {{enabled: !!http.isEnabled()}};
  }}

  var tftpEnabled = pick(spec, ["tftp", "tftp_enabled"], null);
  if (tftpEnabled !== null) {{
    var tftp = d.getProcess("TftpServerProcess") || d.getProcess("TftpServer");
    if (!tftp || typeof tftp.setEnabled !== "function") fail("TFTP process not writable on " + name);
    tftp.setEnabled(!!tftpEnabled);
    result.tftp = {{enabled: tftp.isEnabled ? !!tftp.isEnabled() : null}};
  }}

  var ftpSpec = pick(spec, ["ftp", "ftp_enabled"], null);
  if (ftpSpec !== null) {{
    var ftp = d.getProcess("FtpServerProcess");
    if (!ftp) fail("FTP process missing on " + name);
    var ftpEnabled = null;
    var ftpAccounts = [];
    var ftpRemoveAccounts = [];
    if (typeof ftpSpec === "object") {{
      ftpEnabled = pick(ftpSpec, ["enabled"], null);
      ftpAccounts = pick(ftpSpec, ["accounts", "users"], []);
      ftpRemoveAccounts = pick(ftpSpec, ["remove_accounts", "remove_users"], []);
    }} else {{
      ftpEnabled = ftpSpec;
    }}
    if (ftpEnabled !== null) {{
      if (typeof ftp.setEnabled !== "function") fail("FTP process not writable on " + name);
      ftp.setEnabled(!!ftpEnabled);
    }}
    var ftpResult = {{enabled: ftp.isEnabled ? !!ftp.isEnabled() : null, added: [], removed: []}};
    if (ftpAccounts.length || ftpRemoveAccounts.length) {{
      if (typeof ftp.getFtpUserAccountManager !== "function") fail("FTP user manager unavailable on " + name);
      var mgr = ftp.getFtpUserAccountManager();
      if (!mgr) fail("FTP user manager unavailable on " + name);
      for (var fr = 0; fr < ftpRemoveAccounts.length; fr++) {{
        var removeUser = String(ftpRemoveAccounts[fr]);
        if (mgr.isExistingUser && mgr.isExistingUser(removeUser)) {{
          mgr.removeFtpUser(removeUser);
          ftpResult.removed.push(removeUser);
        }}
      }}
      for (var fa = 0; fa < ftpAccounts.length; fa++) {{
        var acct = ftpAccounts[fa];
        var username = String(pick(acct, ["username", "user", "name"], ""));
        var password = String(pick(acct, ["password", "pass"], ""));
        var permissions = String(pick(acct, ["permissions", "permission", "perms"], "RWDNL"));
        if (!username) fail("FTP account missing username on " + name);
        if (mgr.isExistingUser && mgr.isExistingUser(username)) mgr.removeFtpUser(username);
        mgr.addFtpUser(username, password, permissions);
        ftpResult.added.push({{username: username, permissions: permissions}});
      }}
      if (mgr.getUsersCount) ftpResult.user_count = String(mgr.getUsersCount());
    }}
    result.ftp = ftpResult;
  }}

  var dnsSpec = pick(spec, ["dns"], null);
  if (dnsSpec !== null) {{
    var dns = d.getProcess("DnsServerProcess");
    if (!dns) fail("DNS process missing on " + name);
    var dnsEnabled = pick(dnsSpec, ["enabled"], null);
    if (dnsEnabled !== null) {{
      if (typeof dns.setEnable !== "function") fail("DNS process not writable on " + name);
      dns.setEnable(!!dnsEnabled);
    }}
    var records = pick(dnsSpec, ["records", "a_records"], []);
    var added = [];
    for (var dr = 0; dr < records.length; dr++) {{
      var rec = records[dr];
      var host = String(pick(rec, ["name", "host", "hostname"], ""));
      var ip = String(pick(rec, ["ip", "address"], ""));
      var type = String(pick(rec, ["type"], "A")).toUpperCase();
      if (!host || !ip) fail("DNS A record requires name/ip on " + name);
      if (type !== "A" && type !== "A-REC") fail("only DNS A records are supported by pt730-topo on " + name);
      if (typeof dns.addARecordToNameServerDb !== "function") fail("DNS A record API missing on " + name);
      added.push({{name: host, ip: ip, added: !!dns.addARecordToNameServerDb(host, ip)}});
    }}
    result.dns = {{enabled: dns.isEnabled ? !!dns.isEnabled() : null, added: added}};
  }}

  var emailSpec = pick(spec, ["email"], null);
  if (emailSpec !== null) {{
    var email = d.getProcess("EmailServerProcess");
    var smtp = d.getProcess("SmtpServerProcess");
    var pop3 = d.getProcess("Pop3ServerProcess");
    if (!email) fail("Email process missing on " + name);
    var emailEnabled = typeof emailSpec === "object" ? pick(emailSpec, ["enabled"], null) : emailSpec;
    if (emailEnabled !== null) {{
      if (!smtp || typeof smtp.setEnable !== "function") fail("SMTP process not writable on " + name);
      if (!pop3 || typeof pop3.setEnable !== "function") fail("POP3 process not writable on " + name);
      smtp.setEnable(!!emailEnabled);
      pop3.setEnable(!!emailEnabled);
    }}
    if (typeof emailSpec === "object") {{
      var domain = pick(emailSpec, ["domain", "smtp_domain"], null);
      if (domain !== null && smtp && typeof smtp.setServerDomainName === "function") smtp.setServerDomainName(String(domain));
      var removeEmailUsers = pick(emailSpec, ["remove_accounts", "remove_users"], []);
      var emailAccounts = pick(emailSpec, ["accounts", "users"], []);
      for (var er = 0; er < removeEmailUsers.length; er++) {{
        if (typeof email.deleteUser === "function") email.deleteUser(String(removeEmailUsers[er]));
      }}
      for (var ea = 0; ea < emailAccounts.length; ea++) {{
        var eacct = emailAccounts[ea];
        var euser = String(pick(eacct, ["username", "user", "name"], ""));
        var epass = String(pick(eacct, ["password", "pass"], ""));
        if (!euser) fail("Email account missing username on " + name);
        try {{ if (typeof email.deleteUser === "function") email.deleteUser(euser); }} catch (e) {{}}
        if (typeof email.addUser !== "function") fail("Email add user API missing on " + name);
        email.addUser(euser, epass);
      }}
    }}
    result.email = {{
      smtp_enabled: smtp && smtp.isEnabled ? !!smtp.isEnabled() : null,
      pop3_enabled: pop3 && pop3.isEnabled ? !!pop3.isEnabled() : null,
      domain: smtp && smtp.getServerDomainName ? String(smtp.getServerDomainName()) : "",
      accounts: email.getAllEmailAcctAsStrings ? String(email.getAllEmailAcctAsStrings()) : ""
    }};
  }}

  var ntpSpec = pick(spec, ["ntp"], null);
  if (ntpSpec !== null) {{
    var ntp = d.getProcess("NtpServerProcess");
    if (!ntp) fail("NTP process missing on " + name);
    var ntpEnabled = typeof ntpSpec === "object" ? pick(ntpSpec, ["enabled"], null) : ntpSpec;
    if (ntpEnabled !== null) ntp.setEnabled(!!ntpEnabled);
    if (typeof ntpSpec === "object") {{
      var ntpAuth = pick(ntpSpec, ["authentication", "auth"], null);
      var ntpKeyId = pick(ntpSpec, ["key_id", "key"], null);
      var ntpMd5 = pick(ntpSpec, ["md5", "password"], null);
      if (ntpAuth !== null && typeof ntp.setNtpServerAuthentication === "function") ntp.setNtpServerAuthentication(!!ntpAuth);
      if (ntpKeyId !== null && typeof ntp.setKeyID === "function") ntp.setKeyID(String(ntpKeyId));
      if (ntpMd5 !== null && typeof ntp.setServerMd5Str === "function") ntp.setServerMd5Str(String(ntpMd5));
    }}
    result.ntp = {{
      enabled: ntp.isEnabled ? !!ntp.isEnabled() : null,
      authentication: ntp.getNtpServerAuthentication ? !!ntp.getNtpServerAuthentication() : null,
      key_id: ntp.getKeyId ? String(ntp.getKeyId()) : "",
      md5: ntp.getServerMd5Str ? String(ntp.getServerMd5Str()) : ""
    }};
  }}

  var syslogSpec = pick(spec, ["syslog"], null);
  if (syslogSpec !== null) {{
    var syslog = d.getProcess("SyslogServerProcess");
    if (!syslog) fail("Syslog process missing on " + name);
    var syslogEnabled = typeof syslogSpec === "object" ? pick(syslogSpec, ["enabled"], null) : syslogSpec;
    if (syslogEnabled !== null) syslog.setEnable(!!syslogEnabled);
    if (typeof syslogSpec === "object") {{
      var syslogPort = pick(syslogSpec, ["port"], null);
      if (syslogPort !== null && typeof syslog.setPortNumber === "function") syslog.setPortNumber(Number(syslogPort));
    }}
    result.syslog = {{
      enabled: syslog.isEnabled ? !!syslog.isEnabled() : null,
      port: syslog.getPortNumber ? String(syslog.getPortNumber()) : ""
    }};
  }}

  var dhcpSpec = pick(spec, ["dhcp"], null);
  if (dhcpSpec !== null) {{
    var dhcp = d.getProcess("DhcpServerMainProcess").getDhcpServerProcessByPortName(portName);
    if (!dhcp) fail("DHCP process missing on " + name + ":" + portName);
    var dhcpEnabled = pick(dhcpSpec, ["enabled"], null);
    if (dhcpEnabled !== null) {{
      if (typeof dhcp.setEnable !== "function") fail("DHCP process not writable on " + name);
      dhcp.setEnable(!!dhcpEnabled);
    }}
    var poolIndex = Number(pick(dhcpSpec, ["pool_index", "pool"], 0));
    var pool = dhcp.getPoolAt(poolIndex);
    if (!pool) fail("DHCP pool not found on " + name + ":" + portName + " index " + poolIndex);
    var network = pick(dhcpSpec, ["network"], null);
    var mask = pick(dhcpSpec, ["mask", "subnet_mask", "netmask"], null);
    var start = pick(dhcpSpec, ["start", "start_ip", "first_ip"], null);
    var end = pick(dhcpSpec, ["end", "end_ip", "last_ip"], null);
    var gateway = pick(dhcpSpec, ["gateway", "default_gateway", "router"], null);
    var dnsServer = pick(dhcpSpec, ["dns", "dns_server"], null);
    var maxUsers = pick(dhcpSpec, ["max_users", "max"], null);
    if (network) pool.setNetworkAddress(String(network));
    if (mask) pool.setNetworkMask(String(network || pool.getNetworkAddress()), String(mask));
    if (gateway) pool.setDefaultRouter(String(gateway));
    if (dnsServer) pool.setDnsServerIp(String(dnsServer));
    if (start) {{
      pool.setStartIp(String(start));
      if (typeof pool.setNextAvailableIpAddress === "function") pool.setNextAvailableIpAddress(String(start));
    }}
    if (end) pool.setEndIp(String(end));
    if (maxUsers !== null) pool.setMaxUsers(Number(maxUsers));
    result.dhcp = {{
      enabled: dhcp.isEnable ? !!dhcp.isEnable() : null,
      pool_index: poolIndex,
      network: String(pool.getNetworkAddress()),
      mask: String(pool.getSubnetMask()),
      start_ip: String(pool.getStartIp()),
      end_ip: String(pool.getEndIp()),
      default_gateway: String(pool.getDefaultRouter()),
      dns_server: String(pool.getDnsServerIp()),
      max_users: String(pool.getMaxUsers())
    }};
  }}
  return result;
}}

function iosCommands(spec) {{
  var commands = pick(spec, ["commands", "cmds", "config", "cli"], []);
  if (typeof commands === "string") return commands.split("\\n");
  if (commands && typeof commands.length === "number") return commands;
  fail("ios config commands must be a string or array");
}}

function configureIos(spec) {{
  var name = String(pick(spec, ["name", "device", "router", "switch"], ""));
  if (!name) fail("ios config without device name");
  var d = deviceByName(name);
  if (!d) fail("device not found for ios config: " + name);
  var cli = d.getCommandLine ? d.getCommandLine() : null;
  if (!cli || typeof cli.enterCommand !== "function") fail("device has no IOS command line: " + name);
  if (pick(spec, ["init_dialog", "initDialog", "answer_initial_dialog"], false)) {{
    cli.enterCommand("no");
    cli.enterCommand("");
  }}
  var commands = iosCommands(spec);
  for (var i = 0; i < commands.length; i++) {{
    var cmd = String(commands[i]);
    if (cmd.length) cli.enterCommand(cmd);
  }}
  if (pick(spec, ["save", "write_memory"], false)) {{
    cli.enterCommand("end");
    cli.enterCommand("write memory");
  }}
  var prompt = cli.getPrompt ? String(cli.getPrompt()) : "";
  return {{name: name, commands: commands.length, prompt: prompt, status: "configured"}};
}}

var result = {{devices: [], modules: [], links: [], pc_configs: [], server_configs: [], ios_configs: []}};
if (plan.replace) {{
  for (var r = plan.devices.length - 1; r >= 0; r--) {{
    var rn = String(pick(plan.devices[r], ["name", "id"], ""));
    if (rn) removeIfExists(rn);
  }}
}}
for (var i = 0; i < plan.devices.length; i++) result.devices.push(addOneDevice(plan.devices[i]));
for (var m = 0; m < plan.modules.length; m++) result.modules.push(addOneModule(plan.modules[m]));
for (var j = 0; j < plan.links.length; j++) result.links.push(addOneLink(plan.links[j]));
for (var k = 0; k < plan.pcConfigs.length; k++) result.pc_configs.push(configurePc(plan.pcConfigs[k]));
for (var s = 0; s < plan.serverConfigs.length; s++) result.server_configs.push(configureServer(plan.serverConfigs[s]));
for (var c = 0; c < plan.iosConfigs.length; c++) result.ios_configs.push(configureIos(plan.iosConfigs[c]));
return JSON.stringify(result);
"""


def _remove_js(devices: list[dict[str, Any]]) -> str:
    payload = {"devices": devices}
    plan_json = json.dumps(payload, ensure_ascii=False)
    return f"""
var plan = {plan_json};
var net = ipc.network();
var lw = ipc.appWindow().getActiveWorkspace().getLogicalWorkspace();
function pick(obj, names, fallback) {{
  for (var i = 0; i < names.length; i++) {{
    if (obj[names[i]] !== undefined && obj[names[i]] !== null) return obj[names[i]];
  }}
  return fallback;
}}
function deviceByName(name) {{
  try {{
    var d = net.getDevice(String(name));
    if (d && d.getName) return d;
  }} catch (e) {{}}
  return null;
}}
var result = {{removed: []}};
for (var i = plan.devices.length - 1; i >= 0; i--) {{
  var name = String(pick(plan.devices[i], ["name", "id"], ""));
  if (!name) continue;
  if (!deviceByName(name)) {{
    result.removed.push({{name: name, status: "missing"}});
  }} else {{
    result.removed.push({{name: name, status: lw.removeDevice(name) ? "removed" : "failed"}});
  }}
}}
return JSON.stringify(result);
"""


def _query_js() -> str:
    return """
var net = ipc.network();
var devices = [];
function boolValue(value) { return value ? true : false; }
function tryString(fn, fallback) {
  try {
    var value = fn();
    if (value === undefined || value === null) return fallback;
    return String(value);
  } catch (e) {
    return fallback;
  }
}
function serviceEnabled(device, processName, methodName) {
  try {
    var proc = device.getProcess(processName);
    if (!proc) return null;
    if (methodName && typeof proc[methodName] === "function") return boolValue(proc[methodName]());
    if (typeof proc.isEnabled === "function") return boolValue(proc.isEnabled());
    if (typeof proc.isEnable === "function") return boolValue(proc.isEnable());
  } catch (e) {}
  return null;
}
for (var i = 0; i < net.getDeviceCount(); i++) {
  var d = net.getDeviceAt(i);
  var ports = [];
  try {
    for (var p = 0; p < d.getPortCount(); p++) {
      var port = d.getPortAt(p);
      var linked = false;
      try { linked = !!port.getLink(); } catch (e) {}
      ports.push({
        name: port.getName(),
        type: port.getType(),
        terminal: port.getTerminalTypeShortString(),
        linked: linked,
        ip: port.getIpAddress ? port.getIpAddress() : "",
        mask: port.getSubnetMask ? port.getSubnetMask() : "",
        gateway: port.getDefaultGateway ? port.getDefaultGateway() : "",
        dns: port.getDnsServerIp ? port.getDnsServerIp() : ""
      });
    }
  } catch (e2) {}
  var commandLine = null;
  try {
    var cli = d.getCommandLine ? d.getCommandLine() : null;
    if (cli) {
      var output = cli.getOutput ? String(cli.getOutput()) : "";
      commandLine = {
        prompt: cli.getPrompt ? String(cli.getPrompt()) : "",
        output_length: output.length,
        output_tail: output.length > 12000 ? output.substring(output.length - 12000) : output
      };
    }
  } catch (e3) {}
  var services = {};
  try {
    services.http = {enabled: serviceEnabled(d, "HttpServerProcess", "isEnabled")};
    services.dns = {enabled: serviceEnabled(d, "DnsServerProcess", "isEnabled")};
    services.ftp = {enabled: serviceEnabled(d, "FtpServerProcess", "isEnabled")};
    services.tftp = {enabled: serviceEnabled(d, "TftpServerProcess", "isEnabled")};
    services.email = {
      smtp_enabled: serviceEnabled(d, "SmtpServerProcess", "isEnabled"),
      pop3_enabled: serviceEnabled(d, "Pop3ServerProcess", "isEnabled")
    };
    services.ntp = {enabled: serviceEnabled(d, "NtpServerProcess", "isEnabled")};
    services.syslog = {enabled: serviceEnabled(d, "SyslogServerProcess", "isEnabled")};
  } catch (e4) {}
  devices.push({
    name: d.getName(),
    model: d.getModel(),
    type: d.getType(),
    x: d.getXCoordinate ? d.getXCoordinate() : null,
    y: d.getYCoordinate ? d.getYCoordinate() : null,
    ports: ports,
    command_line: commandLine,
    services: services
  });
}
var links = [];
for (var l = 0; l < net.getLinkCount(); l++) {
  var link = net.getLinkAt(l);
  var p1 = link.getPort1();
  var p2 = link.getPort2();
  links.push({
    a: p1.getOwnerDevice().getName(),
    pa: p1.getName(),
    b: p2.getOwnerDevice().getName(),
    pb: p2.getName(),
    cable: String(link.getConnectionType())
  });
}
return JSON.stringify({devices: devices, links: links});
"""


def _load_query(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("query JSON must be an object")
    data.setdefault("devices", [])
    data.setdefault("links", [])
    return data


def _as_config_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(str(item) for item in value)
    return ""


def _device_config_text(device: dict[str, Any]) -> str:
    for key in ("running_config", "startup_config", "ios_config", "configuration", "config"):
        text = _as_config_text(device.get(key))
        if text.strip():
            return text
    command_line = device.get("command_line")
    if isinstance(command_line, dict):
        for key in ("running_config", "startup_config", "config", "output_tail", "output", "text"):
            text = _as_config_text(command_line.get(key))
            if text.strip():
                return text
    return ""


def _parse_ios_config_summary(text: str) -> dict[str, Any]:
    interfaces: dict[str, dict[str, Any]] = {}
    vlans: dict[str, dict[str, str]] = {}
    static_routes: list[dict[str, str]] = []
    rip_networks: list[str] = []
    acl_numbers: set[str] = set()
    nat = {"inside_interfaces": [], "outside_interfaces": [], "overload": False}
    current_interface: str | None = None
    current_vlan: str | None = None
    current_router: str | None = None

    for raw_line in text.replace("\r\n", "\n").splitlines():
        line = raw_line.strip()
        if not line or line == "!" or line.startswith("--More--"):
            continue
        interface_match = re.match(r"^interface\s+(.+)$", line, flags=re.IGNORECASE)
        if interface_match:
            current_interface = interface_match.group(1).strip()
            current_vlan = None
            current_router = None
            interfaces.setdefault(current_interface, {})
            continue
        vlan_match = re.match(r"^vlan\s+(\S+)$", line, flags=re.IGNORECASE)
        if vlan_match:
            current_vlan = vlan_match.group(1)
            current_interface = None
            current_router = None
            vlans.setdefault(current_vlan, {})
            continue
        router_match = re.match(r"^router\s+(\S+)", line, flags=re.IGNORECASE)
        if router_match:
            current_router = router_match.group(1).lower()
            current_interface = None
            current_vlan = None
            continue
        route_match = re.match(r"^ip\s+route\s+(\S+)\s+(\S+)\s+(\S+)", line, flags=re.IGNORECASE)
        if route_match:
            current_interface = None
            current_vlan = None
            current_router = None
            static_routes.append({"destination": route_match.group(1), "mask": route_match.group(2), "next_hop": route_match.group(3)})
            continue
        acl_match = re.match(r"^access-list\s+(\S+)\s+", line, flags=re.IGNORECASE)
        if acl_match:
            acl_numbers.add(acl_match.group(1))
        if re.match(r"^ip\s+nat\s+inside\s+source\s+list\s+", line, flags=re.IGNORECASE):
            nat["overload"] = True

        if current_interface:
            info = interfaces.setdefault(current_interface, {})
            ip_match = re.match(r"^ip\s+address\s+(\S+)\s+(\S+)", line, flags=re.IGNORECASE)
            if ip_match:
                info["ip"] = ip_match.group(1)
                info["mask"] = ip_match.group(2)
            mode_match = re.match(r"^switchport\s+mode\s+(\S+)", line, flags=re.IGNORECASE)
            if mode_match:
                info["switchport_mode"] = mode_match.group(1)
            access_match = re.match(r"^switchport\s+access\s+vlan\s+(\S+)", line, flags=re.IGNORECASE)
            if access_match:
                info["access_vlan"] = access_match.group(1)
            trunk_match = re.match(r"^switchport\s+trunk\s+allowed\s+vlan\s+(.+)", line, flags=re.IGNORECASE)
            if trunk_match:
                info["trunk_allowed_vlans"] = trunk_match.group(1).strip()
            nat_match = re.match(r"^ip\s+nat\s+(inside|outside)$", line, flags=re.IGNORECASE)
            if nat_match:
                direction = nat_match.group(1).lower()
                info["nat"] = direction
                key = "inside_interfaces" if direction == "inside" else "outside_interfaces"
                if current_interface not in nat[key]:
                    nat[key].append(current_interface)
            if line.lower() == "shutdown":
                info["shutdown"] = True
            elif line.lower() == "no shutdown":
                info["shutdown"] = False
        elif current_vlan:
            name_match = re.match(r"^name\s+(.+)", line, flags=re.IGNORECASE)
            if name_match:
                vlans.setdefault(current_vlan, {})["name"] = name_match.group(1).strip()
        elif current_router == "rip":
            network_match = re.match(r"^network\s+(\S+)", line, flags=re.IGNORECASE)
            if network_match:
                rip_networks.append(network_match.group(1))

    return {
        "interfaces": interfaces,
        "vlans": vlans,
        "routing": {"rip_networks": rip_networks, "static_routes": static_routes},
        "acl_numbers": sorted(acl_numbers),
        "nat": nat,
    }


def _query_summary(query: dict[str, Any]) -> dict[str, Any]:
    devices = [device for device in query.get("devices", []) if isinstance(device, dict)]
    links = [link for link in query.get("links", []) if isinstance(link, dict)]
    ip_configs: list[dict[str, Any]] = []
    ios_devices: list[dict[str, Any]] = []
    server_services: list[dict[str, Any]] = []
    config_summaries: list[dict[str, Any]] = []
    for device in devices:
        name = str(device.get("name", ""))
        model = str(device.get("model", ""))
        for port in device.get("ports", []):
            if not isinstance(port, dict):
                continue
            if port.get("ip"):
                ip_configs.append(
                    {
                        "device": name,
                        "model": model,
                        "port": str(port.get("name", "")),
                        "ip": str(port.get("ip", "")),
                        "mask": str(port.get("mask", "")),
                        "gateway": str(port.get("gateway", "")),
                        "dns": str(port.get("dns", "")),
                        "linked": bool(port.get("linked", False)),
                    }
                )
        command_line = device.get("command_line")
        if isinstance(command_line, dict) and command_line.get("prompt") is not None:
            ios_devices.append({"device": name, "model": model, "prompt": str(command_line.get("prompt", ""))})
        config_text = _device_config_text(device)
        if config_text.strip():
            config_summaries.append({"device": name, "model": model, **_parse_ios_config_summary(config_text)})
        services = device.get("services")
        if isinstance(services, dict):
            enabled = []
            present = []
            for service, state in sorted(services.items()):
                if isinstance(state, dict):
                    values = [value for value in state.values() if isinstance(value, bool)]
                    if values:
                        present.append(service)
                    if any(values):
                        enabled.append(service)
            if present or enabled:
                server_services.append({"device": name, "model": model, "present": present, "enabled": enabled})
    return {
        "counts": {"devices": len(devices), "links": len(links), "ip_configs": len(ip_configs), "ios_devices": len(ios_devices), "server_service_devices": len(server_services), "config_summaries": len(config_summaries)},
        "devices": [{"name": str(device.get("name", "")), "model": str(device.get("model", "")), "type": str(device.get("type", ""))} for device in devices],
        "links": links,
        "ip_configs": ip_configs,
        "ios_devices": ios_devices,
        "server_services": server_services,
        "config_summaries": config_summaries,
    }


def _print_json(raw: str) -> None:
    try:
        print(json.dumps(json.loads(raw), ensure_ascii=False, indent=2))
    except json.JSONDecodeError:
        print(raw)


def _print_json_obj(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def _chunks(items: list[Any], size: int) -> list[list[Any]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _decode_result(raw: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {"raw": raw}
    return parsed if isinstance(parsed, dict) else {"raw": parsed}


def _apply_batched(plan: dict[str, Any], *, replace: bool, batch_size: int, bridge: str, timeout: float) -> dict[str, Any]:
    result: dict[str, Any] = {
        "removed": [],
        "device_batches": [],
        "module_batches": [],
        "link_batches": [],
        "pc_config_batches": [],
        "server_config_batches": [],
        "ios_config_batches": [],
    }
    if batch_size < 1:
        raise ValueError("--batch-size must be positive")

    devices = plan["devices"]
    modules = plan.get("modules", [])
    links = plan["links"]
    pc_configs = plan["pc_configs"]
    server_configs = plan["server_configs"]
    ios_configs = plan["ios_configs"]

    if replace or bool(plan.get("replace")):
        for batch in _chunks(devices, batch_size):
            raw = eval_js(_remove_js(batch), bridge, timeout)
            parsed = _decode_result(raw)
            result["removed"].extend(parsed.get("removed", []))

    for batch in _chunks(devices, batch_size):
        raw = eval_js(_apply_js({"devices": batch, "modules": [], "links": [], "pc_configs": [], "server_configs": [], "ios_configs": []}, replace=False), bridge, timeout)
        result["device_batches"].append(_decode_result(raw))

    for batch in _chunks(modules, batch_size):
        raw = eval_js(_apply_js({"devices": [], "modules": batch, "links": [], "pc_configs": [], "server_configs": [], "ios_configs": []}, replace=False), bridge, timeout)
        result["module_batches"].append(_decode_result(raw))

    for batch in _chunks(links, batch_size):
        raw = eval_js(_apply_js({"devices": [], "modules": [], "links": batch, "pc_configs": [], "server_configs": [], "ios_configs": []}, replace=False), bridge, timeout)
        result["link_batches"].append(_decode_result(raw))

    for batch in _chunks(pc_configs, batch_size):
        raw = eval_js(_apply_js({"devices": [], "modules": [], "links": [], "pc_configs": batch, "server_configs": [], "ios_configs": []}, replace=False), bridge, timeout)
        result["pc_config_batches"].append(_decode_result(raw))

    for batch in _chunks(server_configs, batch_size):
        raw = eval_js(_apply_js({"devices": [], "modules": [], "links": [], "pc_configs": [], "server_configs": batch, "ios_configs": []}, replace=False), bridge, timeout)
        result["server_config_batches"].append(_decode_result(raw))

    for batch in _chunks(ios_configs, batch_size):
        raw = eval_js(_apply_js({"devices": [], "modules": [], "links": [], "pc_configs": [], "server_configs": [], "ios_configs": batch}, replace=False), bridge, timeout)
        result["ios_config_batches"].append(_decode_result(raw))

    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bridge", default=DEFAULT_BRIDGE)
    parser.add_argument("--timeout", type=float, default=20.0)
    sub = parser.add_subparsers(dest="cmd", required=True)

    apply_p = sub.add_parser("apply", help="apply a topology JSON plan")
    apply_p.add_argument("plan", type=Path)
    apply_p.add_argument("--replace", action="store_true", help="remove named plan devices before recreating them")
    apply_p.add_argument("--batch-size", type=int, default=0, help="apply in small batches to avoid PT 7.3.0 script timeouts")
    apply_p.add_argument("--allow-risky", action="store_true", help="allow known crash-risk or unverified plan items")
    apply_p.add_argument("--strict-safety", action="store_true", help="treat safety warnings as failures")
    apply_p.add_argument("--dry-run", action="store_true", help="run offline safety checks and print a plan summary without contacting Packet Tracer")

    query_p = sub.add_parser("query", help="query current devices and links")
    query_p.add_argument("--summary", action="store_true", help="summarize current canvas devices, links, IPs, IOS prompts, and services")

    summarize_p = sub.add_parser("summarize-query", help="summarize a saved pt730-topo query JSON file")
    summarize_p.add_argument("query_json", type=Path)

    args = parser.parse_args(argv)
    try:
        if args.cmd == "apply":
            plan = _load_plan(args.plan)
            _enforce_plan_safety(plan, allow_risky=args.allow_risky, strict=args.strict_safety)
            if args.dry_run:
                print(json.dumps(_plan_summary(plan), ensure_ascii=False, indent=2))
                return 0
            if args.batch_size:
                print(json.dumps(
                    _apply_batched(plan, replace=args.replace, batch_size=args.batch_size, bridge=args.bridge, timeout=args.timeout),
                    ensure_ascii=False,
                    indent=2,
                ))
            else:
                _print_json(eval_js(_apply_js(plan, replace=args.replace), args.bridge, args.timeout))
            return 0
        if args.cmd == "query":
            raw = eval_js(_query_js(), args.bridge, args.timeout)
            if args.summary:
                _print_json_obj(_query_summary(_decode_result(raw)))
            else:
                _print_json(raw)
            return 0
        if args.cmd == "summarize-query":
            _print_json_obj(_query_summary(_load_query(args.query_json)))
            return 0
    except (OSError, ValueError, RuntimeError, TimeoutError, urllib.error.URLError) as exc:
        print(f"pt730-topo: {exc}", file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
