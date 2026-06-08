#!/usr/bin/env python3
"""Locate and run the local Packet Tracer 7.3.0 CLI toolkit."""

from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path


def is_repo(path: Path) -> bool:
    return (path / "pt-reverse" / "bin" / "pt730-selftest").exists()


def repo_root() -> Path:
    env = os.environ.get("PT730_REPO")
    if env and is_repo(Path(env)):
        return Path(env).resolve()

    here = Path(__file__).resolve()
    for parent in [here, *here.parents]:
        if is_repo(parent):
            return parent

    cwd = Path.cwd().resolve()
    for parent in [cwd, *cwd.parents]:
        if is_repo(parent):
            return parent

    raise SystemExit("pt730_cli.py: set PT730_REPO to the CiscoPacketTracer-7.3.0 repo")


def tool_path(root: Path, tool: str) -> Path:
    name = tool if tool.startswith("pt730-") else f"pt730-{tool}"
    path = root / "pt-reverse" / "bin" / name
    if not path.exists():
        raise SystemExit(f"pt730_cli.py: missing tool: {path}")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("root", help="print the toolkit repo root")

    bin_p = sub.add_parser("bin", help="print a pt730 tool path")
    bin_p.add_argument("tool")

    run_p = sub.add_parser("run", help="run a pt730 tool from the repo root")
    run_p.add_argument("tool")
    run_p.add_argument("args", nargs=argparse.REMAINDER)

    args = parser.parse_args(argv)
    root = repo_root()
    if args.cmd == "root":
        print(root)
        return 0
    if args.cmd == "bin":
        print(tool_path(root, args.tool))
        return 0
    if args.cmd == "run":
        command = [str(tool_path(root, args.tool)), *args.args]
        return subprocess.run(command, cwd=root, check=False).returncode
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
