#!/usr/bin/env python3
"""Generic Packet Tracer device terminal helper over the local bridge."""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
from pathlib import Path
from typing import Any

from topology_cli import DEFAULT_BRIDGE, eval_js


def js_string(value: str) -> str:
    return json.dumps(value)


def eval_json(js: str, *, bridge: str, timeout: float) -> dict[str, Any]:
    raw = eval_js(js, bridge, timeout)
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise RuntimeError(f"expected JSON object, got {type(parsed).__name__}")
    return parsed


def send_js(device: str, commands: list[str]) -> str:
    payload = json.dumps({"device": device, "commands": commands}, ensure_ascii=False)
    return f"""
var payload = {payload};
var d = ipc.network().getDevice(String(payload.device));
if (!d) throw new Error("device not found: " + payload.device);
var cli = d.getCommandLine ? d.getCommandLine() : null;
if (!cli || typeof cli.enterCommand !== "function") throw new Error("device has no command line: " + payload.device);
var before = cli.getOutput ? String(cli.getOutput()) : "";
for (var i = 0; i < payload.commands.length; i++) {{
  cli.enterCommand(String(payload.commands[i]));
}}
var after = cli.getOutput ? String(cli.getOutput()) : "";
var prompt = cli.getPrompt ? String(cli.getPrompt()) : "";
return JSON.stringify({{device: String(payload.device), prompt: prompt, start: before.length, output: after, delta: after.substring(before.length)}});
"""


def poll_js(device: str, start: int) -> str:
    return f"""
var d = ipc.network().getDevice({js_string(device)});
if (!d) throw new Error("device not found: " + {js_string(device)});
var cli = d.getCommandLine ? d.getCommandLine() : null;
if (!cli || typeof cli.getOutput !== "function") throw new Error("device has no readable command line: " + {js_string(device)});
var output = String(cli.getOutput());
var prompt = cli.getPrompt ? String(cli.getPrompt()) : "";
return JSON.stringify({{device: {js_string(device)}, prompt: prompt, start: {int(start)}, output: output, delta: output.substring({int(start)})}});
"""


def load_commands(args: argparse.Namespace) -> list[str]:
    commands: list[str] = []
    if args.file:
        text = args.file.read_text(encoding="utf-8")
        commands.extend(line.rstrip() for line in text.splitlines() if line.strip() or args.keep_blank)
    commands.extend(args.cmd or [])
    if not commands:
        raise ValueError("provide --cmd or --file")
    return commands


def print_output(record: dict[str, Any], mode: str, tail_lines: int, delta_only: bool) -> None:
    output = str(record.get("delta" if delta_only else "output", ""))
    if mode == "none":
        return
    if mode == "tail":
        print("\n".join(output.splitlines()[-tail_lines:]))
        return
    print(output)


def wait_for_pattern(
    device: str,
    start: int,
    pattern: str,
    *,
    bridge: str,
    timeout: float,
    wait_seconds: float,
) -> tuple[bool, dict[str, Any]]:
    regex = re.compile(pattern, re.MULTILINE)
    deadline = time.monotonic() + wait_seconds
    record = eval_json(poll_js(device, start), bridge=bridge, timeout=timeout)
    while time.monotonic() < deadline:
        if regex.search(str(record.get("delta", ""))):
            return True, record
        time.sleep(0.5)
        record = eval_json(poll_js(device, start), bridge=bridge, timeout=timeout)
    return bool(regex.search(str(record.get("delta", "")))), record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("device")
    parser.add_argument("--bridge", default=DEFAULT_BRIDGE)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--cmd", action="append", help="command to send; may be repeated")
    parser.add_argument("--file", type=Path, help="read commands from a text file")
    parser.add_argument("--keep-blank", action="store_true", help="keep blank lines from --file")
    parser.add_argument("--wait", type=float, default=0.0, help="poll command output for this many seconds")
    parser.add_argument("--expect", help="regular expression that must match newly produced output")
    parser.add_argument("--output", choices=["tail", "full", "none"], default="tail")
    parser.add_argument("--tail-lines", type=int, default=80)
    parser.add_argument("--all-output", action="store_true", help="print full terminal buffer instead of only new output")
    args = parser.parse_args(argv)

    try:
        commands = load_commands(args)
        sent = eval_json(send_js(args.device, commands), bridge=args.bridge, timeout=args.timeout)
        record = sent
        ok = True
        if args.expect:
            wait_seconds = args.wait if args.wait > 0 else 0.1
            ok, record = wait_for_pattern(
                args.device,
                int(sent.get("start", 0)),
                args.expect,
                bridge=args.bridge,
                timeout=args.timeout,
                wait_seconds=wait_seconds,
            )
        elif args.wait > 0:
            time.sleep(args.wait)
            record = eval_json(poll_js(args.device, int(sent.get("start", 0))), bridge=args.bridge, timeout=args.timeout)
        print_output(record, args.output, args.tail_lines, delta_only=not args.all_output)
        if args.expect and not ok:
            print(f"pt730-term: expected pattern not found: {args.expect}", file=sys.stderr)
            return 1
        return 0
    except (OSError, ValueError, RuntimeError, TimeoutError, urllib.error.URLError, json.JSONDecodeError, re.error) as exc:
        print(f"pt730-term: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
