#!/usr/bin/env python3
"""Packet Tracer PC FTP client helper over the local bridge."""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
from pathlib import Path
from typing import Any

from term_cli import eval_json, send_js, wait_for_pattern
from topology_cli import DEFAULT_BRIDGE


def send_and_wait(
    device: str,
    command: str,
    pattern: str,
    *,
    bridge: str,
    timeout: float,
    wait_seconds: float,
) -> dict[str, Any]:
    sent = eval_json(send_js(device, [command]), bridge=bridge, timeout=timeout)
    ok, record = wait_for_pattern(
        device,
        int(sent.get("start", 0)),
        pattern,
        bridge=bridge,
        timeout=timeout,
        wait_seconds=wait_seconds,
    )
    if not ok:
        raise RuntimeError(f"expected FTP output pattern not found after {command!r}: {pattern}")
    return record


def load_commands(args: argparse.Namespace) -> list[str]:
    commands: list[str] = []
    if args.file:
        text = args.file.read_text(encoding="utf-8")
        commands.extend(line.rstrip() for line in text.splitlines() if line.strip() or args.keep_blank)
    commands.extend(args.cmd or [])
    return commands


def print_delta(records: list[dict[str, Any]], *, tail_lines: int) -> None:
    output = "\n".join(str(record.get("delta", "")).rstrip() for record in records if str(record.get("delta", "")).strip())
    if not output:
        return
    lines = output.splitlines()
    print("\n".join(lines[-tail_lines:]))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("client", help="PC/server/laptop device that has a Packet Tracer command line")
    parser.add_argument("server", help="FTP server hostname or IP address")
    parser.add_argument("--username", "-u", default="cisco")
    parser.add_argument("--password", "-p", default="cisco")
    parser.add_argument("--cmd", action="append", help="FTP command to run after login; may be repeated")
    parser.add_argument("--file", type=Path, help="read FTP commands from a text file")
    parser.add_argument("--keep-blank", action="store_true", help="keep blank lines from --file")
    parser.add_argument("--expect", help="regular expression that must match combined command output")
    parser.add_argument("--no-quit", action="store_true", help="leave the FTP session open")
    parser.add_argument("--bridge", default=DEFAULT_BRIDGE)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--connect-wait", type=float, default=8.0)
    parser.add_argument("--command-wait", type=float, default=8.0)
    parser.add_argument("--tail-lines", type=int, default=120)
    args = parser.parse_args(argv)

    try:
        commands = load_commands(args)
        records: list[dict[str, Any]] = []
        records.append(
            send_and_wait(
                args.client,
                f"ftp {args.server}",
                r"Username:",
                bridge=args.bridge,
                timeout=args.timeout,
                wait_seconds=args.connect_wait,
            )
        )
        records.append(
            send_and_wait(
                args.client,
                args.username,
                r"Password:",
                bridge=args.bridge,
                timeout=args.timeout,
                wait_seconds=args.command_wait,
            )
        )
        records.append(
            send_and_wait(
                args.client,
                args.password,
                r"ftp>",
                bridge=args.bridge,
                timeout=args.timeout,
                wait_seconds=args.command_wait,
            )
        )
        for command in commands:
            records.append(
                send_and_wait(
                    args.client,
                    command,
                    r"ftp>",
                    bridge=args.bridge,
                    timeout=args.timeout,
                    wait_seconds=args.command_wait,
                )
            )
        if not args.no_quit:
            records.append(
                send_and_wait(
                    args.client,
                    "quit",
                    r"C:\\>|C>",
                    bridge=args.bridge,
                    timeout=args.timeout,
                    wait_seconds=args.command_wait,
                )
            )

        combined = "\n".join(str(record.get("delta", "")) for record in records)
        print_delta(records, tail_lines=args.tail_lines)
        if args.expect and not re.search(args.expect, combined, re.MULTILINE):
            print(f"pt730-ftp: expected pattern not found: {args.expect}", file=sys.stderr)
            return 1
        return 0
    except (OSError, ValueError, RuntimeError, TimeoutError, urllib.error.URLError, json.JSONDecodeError, re.error) as exc:
        print(f"pt730-ftp: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
