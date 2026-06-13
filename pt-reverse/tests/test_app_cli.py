#!/usr/bin/env python3
"""Tests for app-level Packet Tracer helper guards."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "bin" / "pt730-app"


class AppCliTest(unittest.TestCase):
    def run_cmd(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(APP), *args],
            cwd=ROOT.parent,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
        )

    def test_inspect_pkt_reports_risky_model_without_live_contact(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            pkt = Path(tmpdir) / "visible-risk.pkt"
            pkt.write_bytes(b"PacketTracer\x003560-24PS\x00")

            result = self.run_cmd("inspect-pkt", str(pkt))

        self.assertEqual(result.returncode, 1)
        data = json.loads(result.stdout)
        self.assertFalse(data["safe_to_open"])
        self.assertIn("3560-24PS", data["risky_signatures"])

    def test_open_refuses_risky_pkt_before_live_eval(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            pkt = Path(tmpdir) / "visible-risk.pkt"
            pkt.write_bytes(b"PacketTracer\x003560-24PS\x00")

            result = self.run_cmd("open", str(pkt))

        self.assertEqual(result.returncode, 1)
        self.assertIn("refusing to open Packet Tracer file", result.stderr)
        self.assertNotIn("pt730-eval", result.stderr)


if __name__ == "__main__":
    unittest.main()
