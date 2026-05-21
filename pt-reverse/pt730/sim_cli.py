#!/usr/bin/env python3
"""Limited Packet Tracer 7.3.0 simulation/PDU helper over the local bridge."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
from typing import Any

from topology_cli import DEFAULT_BRIDGE, eval_js


def print_json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def eval_json(js: str, *, bridge: str, timeout: float) -> dict[str, Any]:
    raw = eval_js(js, bridge, timeout)
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise RuntimeError(f"expected JSON object, got {type(parsed).__name__}")
    return parsed


def status_js() -> str:
    return """
var app = ipc.appWindow();
var simToolbar = app.getSimulationToolbar ? app.getSimulationToolbar() : null;
return JSON.stringify({
  simulation_mode: app.isSimulationMode ? !!app.isSimulationMode() : null,
  event_list_on: simToolbar && simToolbar.isEventListOn ? !!simToolbar.isEventListOn() : null,
  exposed: {
    simulation_panel: !!(app.getSimulationPanel && app.getSimulationPanel()),
    realtime_toolbar: !!(app.getRealtimeToolbar && app.getRealtimeToolbar()),
    user_created_pdu: !!(app.getUserCreatedPDU && app.getUserCreatedPDU()),
    pdu_list_window: !!(app.getPDUListWindow && app.getPDUListWindow())
  }
});
"""


def reset_js() -> str:
    return """
var app = ipc.appWindow();
var panel = app.getSimulationPanel ? app.getSimulationPanel() : null;
if (!panel || typeof panel.resetSimulation !== "function") throw new Error("SimulationPanel.resetSimulation is unavailable");
var ret = panel.resetSimulation();
return JSON.stringify({action: "reset", result: String(ret), simulation_mode: app.isSimulationMode ? !!app.isSimulationMode() : null});
"""


def fast_forward_js(steps: int) -> str:
    return f"""
var app = ipc.appWindow();
var rt = app.getRealtimeToolbar ? app.getRealtimeToolbar() : null;
if (!rt || typeof rt.fastForwardTime !== "function") throw new Error("RealtimeToolbar.fastForwardTime is unavailable");
var results = [];
for (var i = 0; i < {int(steps)}; i++) {{
  results.push(String(rt.fastForwardTime()));
}}
return JSON.stringify({{action: "fast-forward", steps: {int(steps)}, results: results}});
"""


def event_list_js(enabled: bool) -> str:
    return f"""
var app = ipc.appWindow();
var simToolbar = app.getSimulationToolbar ? app.getSimulationToolbar() : null;
if (!simToolbar || typeof simToolbar.setEventListToggle !== "function") throw new Error("SimulationToolbar.setEventListToggle is unavailable");
simToolbar.setEventListToggle({str(bool(enabled)).lower()});
return JSON.stringify({{action: "event-list", enabled: simToolbar.isEventListOn ? !!simToolbar.isEventListOn() : {str(bool(enabled)).lower()}}});
"""


def simple_pdu_js(source: str, target: str) -> str:
    source_json = json.dumps(source)
    target_json = json.dumps(target)
    return f"""
var net = ipc.network();
var app = ipc.appWindow();
var pdu = app.getUserCreatedPDU ? app.getUserCreatedPDU() : null;
if (!pdu || typeof pdu.addSimplePdu !== "function") throw new Error("UserCreatedPDU.addSimplePdu is unavailable");
var src = net.getDevice({source_json});
var dst = net.getDevice({target_json});
if (!src) throw new Error("source device not found: " + {source_json});
if (!dst) throw new Error("target device not found: " + {target_json});
var ret = pdu.addSimplePdu(src, dst);
return JSON.stringify({{action: "simple-pdu", source: {source_json}, target: {target_json}, result: String(ret), note: "PT 7.3 exposes addSimplePdu but not a script-readable PDU event list/status"}});
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bridge", default=DEFAULT_BRIDGE)
    parser.add_argument("--timeout", type=float, default=10.0)
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="show exposed simulation/PDU surfaces")
    sub.add_parser("reset", help="call SimulationPanel.resetSimulation()")

    ff_p = sub.add_parser("fast-forward", help="call RealtimeToolbar.fastForwardTime()")
    ff_p.add_argument("--steps", type=int, default=1)

    ev_p = sub.add_parser("event-list", help="show or hide the simulation event list")
    ev_g = ev_p.add_mutually_exclusive_group(required=True)
    ev_g.add_argument("--on", action="store_true")
    ev_g.add_argument("--off", action="store_true")

    pdu_p = sub.add_parser("simple-pdu", help="add a GUI-style Simple PDU between two devices")
    pdu_p.add_argument("source")
    pdu_p.add_argument("target")

    args = parser.parse_args(argv)
    try:
        if args.cmd == "status":
            print_json(eval_json(status_js(), bridge=args.bridge, timeout=args.timeout))
            return 0
        if args.cmd == "reset":
            print_json(eval_json(reset_js(), bridge=args.bridge, timeout=args.timeout))
            return 0
        if args.cmd == "fast-forward":
            if args.steps < 1:
                raise ValueError("--steps must be positive")
            print_json(eval_json(fast_forward_js(args.steps), bridge=args.bridge, timeout=args.timeout))
            return 0
        if args.cmd == "event-list":
            print_json(eval_json(event_list_js(args.on), bridge=args.bridge, timeout=args.timeout))
            return 0
        if args.cmd == "simple-pdu":
            print_json(eval_json(simple_pdu_js(args.source, args.target), bridge=args.bridge, timeout=args.timeout))
            return 0
    except (OSError, ValueError, RuntimeError, TimeoutError, urllib.error.URLError, json.JSONDecodeError) as exc:
        print(f"pt730-sim: {exc}", file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
