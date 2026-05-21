#!/usr/bin/env python3
"""Packet Tracer 7.3.0 PC/host interface CLI over the local bridge."""

from __future__ import annotations

import argparse
import ipaddress
import json
import sys
import time
import urllib.error
from typing import Any

from topology_cli import DEFAULT_BRIDGE, eval_js


def js_string(value: str) -> str:
    return json.dumps(value)


def print_json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def eval_json(js: str, *, bridge: str, timeout: float) -> dict[str, Any]:
    raw = eval_js(js, bridge, timeout)
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise RuntimeError(f"expected JSON object, got {type(parsed).__name__}")
    return parsed


def inspect_js(device: str, port: str) -> str:
    return f"""
var deviceName = {js_string(device)};
var portName = {js_string(port)};
var d = ipc.network().getDevice(deviceName);
if (!d) throw new Error("device not found: " + deviceName);
var p = d.getPort(portName);
if (!p) throw new Error("port not found: " + deviceName + ":" + portName);
var dhcp = null;
try {{ if (typeof d.getDhcpFlag === "function") dhcp = !!d.getDhcpFlag(); }} catch (e) {{}}
return JSON.stringify({{
  device: deviceName,
  model: d.getModel ? String(d.getModel()) : "",
  port: portName,
  dhcp: dhcp,
  ip: p.getIpAddress ? String(p.getIpAddress()) : "",
  mask: p.getSubnetMask ? String(p.getSubnetMask()) : ""
}});
"""


def static_js(device: str, port: str, ip: str, mask: str, gateway: str | None, dns: str | None) -> str:
    return f"""
var deviceName = {js_string(device)};
var portName = {js_string(port)};
var d = ipc.network().getDevice(deviceName);
if (!d) throw new Error("device not found: " + deviceName);
if (typeof d.setDhcpFlag === "function") d.setDhcpFlag(false);
var p = d.getPort(portName);
if (!p) throw new Error("port not found: " + deviceName + ":" + portName);
p.setIpSubnetMask({js_string(ip)}, {js_string(mask)});
if ({json.dumps(gateway)} !== null) p.setDefaultGateway({json.dumps(gateway)});
if ({json.dumps(dns)} !== null) p.setDnsServerIp({json.dumps(dns)});
return JSON.stringify({{
  device: deviceName,
  port: portName,
  dhcp: d.getDhcpFlag ? !!d.getDhcpFlag() : null,
  ip: String(p.getIpAddress()),
  mask: String(p.getSubnetMask()),
  status: "configured"
}});
"""


def dhcp_js(device: str, port: str, renew: bool) -> str:
    return f"""
var deviceName = {js_string(device)};
var portName = {js_string(port)};
var renew = {str(bool(renew)).lower()};
var d = ipc.network().getDevice(deviceName);
if (!d) throw new Error("device not found: " + deviceName);
if (typeof d.setDhcpFlag !== "function") throw new Error("device has no DHCP flag API: " + deviceName);
var p = d.getPort(portName);
if (!p) throw new Error("port not found: " + deviceName + ":" + portName);
if (renew) {{
  try {{
    var c = d.getProcess("DhcpClientProcess");
    // PT 7.3.0 exposes dhcpRun(), but calling it through Script Module IPC can
    // block or crash this Wine session. Only reset the stored client state.
    if (c && typeof c.resetDhcpConfOn === "function") c.resetDhcpConfOn(portName);
  }} catch (e) {{}}
}}
d.setDhcpFlag(true);
return JSON.stringify({{
  device: deviceName,
  port: portName,
  dhcp: d.getDhcpFlag ? !!d.getDhcpFlag() : true,
  ip: p.getIpAddress ? String(p.getIpAddress()) : "",
  mask: p.getSubnetMask ? String(p.getSubnetMask()) : "",
  status: renew ? "renew-started" : "enabled"
}});
"""


def ip_ready(record: dict[str, Any], expect_network: str | None) -> bool:
    ip = str(record.get("ip", ""))
    if not ip or ip == "0.0.0.0":
        return False
    if not expect_network:
        return True
    return ipaddress.ip_address(ip) in ipaddress.ip_network(expect_network, strict=False)


def wait_for_dhcp(device: str, port: str, *, bridge: str, timeout: float, wait_seconds: float, expect_network: str | None) -> dict[str, Any]:
    deadline = time.monotonic() + wait_seconds
    last = eval_json(inspect_js(device, port), bridge=bridge, timeout=timeout)
    retried_enable = False
    while time.monotonic() < deadline:
        if ip_ready(last, expect_network):
            last["status"] = "dhcp-ready"
            return last
        if last.get("dhcp") is False and not retried_enable:
            # Immediately after a topology rebuild PT 7.3.0 can briefly drop
            # the host DHCP flag. Re-enable it once instead of failing a live
            # lab check on that transient state.
            eval_json(dhcp_js(device, port, False), bridge=bridge, timeout=timeout)
            retried_enable = True
        time.sleep(0.5)
        last = eval_json(inspect_js(device, port), bridge=bridge, timeout=timeout)
    last["status"] = "dhcp-timeout"
    if expect_network:
        last["expected_network"] = expect_network
    return last


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bridge", default=DEFAULT_BRIDGE)
    parser.add_argument("--timeout", type=float, default=10.0)
    sub = parser.add_subparsers(dest="cmd", required=True)

    inspect_p = sub.add_parser("inspect", help="inspect a PC/server/laptop port IP state")
    inspect_p.add_argument("device")
    inspect_p.add_argument("--port", default="FastEthernet0")

    static_p = sub.add_parser("static", help="set a static IPv4 address")
    static_p.add_argument("device")
    static_p.add_argument("--port", default="FastEthernet0")
    static_p.add_argument("--ip", required=True)
    static_p.add_argument("--mask", required=True)
    static_p.add_argument("--gateway")
    static_p.add_argument("--dns")

    dhcp_p = sub.add_parser("dhcp", help="enable DHCP client mode")
    dhcp_p.add_argument("device")
    dhcp_p.add_argument("--port", default="FastEthernet0")
    dhcp_p.add_argument("--renew", action="store_true", help="reset DHCP state before enabling the client")
    dhcp_p.add_argument("--wait", type=float, default=0.0, help="wait for a non-zero DHCP lease")
    dhcp_p.add_argument("--expect-network", help="require the leased address to fall inside this CIDR")

    args = parser.parse_args(argv)
    try:
        if args.cmd == "inspect":
            print_json(eval_json(inspect_js(args.device, args.port), bridge=args.bridge, timeout=args.timeout))
            return 0
        if args.cmd == "static":
            print_json(eval_json(static_js(args.device, args.port, args.ip, args.mask, args.gateway, args.dns), bridge=args.bridge, timeout=args.timeout))
            return 0
        if args.cmd == "dhcp":
            first = eval_json(dhcp_js(args.device, args.port, args.renew), bridge=args.bridge, timeout=args.timeout)
            if args.wait > 0:
                result = wait_for_dhcp(
                    args.device,
                    args.port,
                    bridge=args.bridge,
                    timeout=args.timeout,
                    wait_seconds=args.wait,
                    expect_network=args.expect_network,
                )
                print_json(result)
                return 0 if result.get("status") == "dhcp-ready" else 1
            print_json(first)
            return 0
    except (OSError, ValueError, RuntimeError, TimeoutError, urllib.error.URLError, json.JSONDecodeError) as exc:
        print(f"pt730-pc: {exc}", file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
