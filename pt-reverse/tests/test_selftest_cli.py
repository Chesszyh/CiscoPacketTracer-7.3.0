#!/usr/bin/env python3
"""Tests for the offline PT 7.3.0 self-test wrapper."""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SELFTEST = ROOT / "bin" / "pt730-selftest"


class SelftestCliTest(unittest.TestCase):
    def run_cmd(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(SELFTEST), *args],
            cwd=ROOT.parent,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
        )

    def test_help_describes_offline_selftest(self) -> None:
        result = self.run_cmd("--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("offline", result.stdout.lower())
        self.assertIn("safety", result.stdout.lower())

    def test_default_selftest_is_offline_and_passes(self) -> None:
        result = self.run_cmd()
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("pt730-selftest: OK", result.stdout)
        self.assertIn("ip planning checks", result.stdout)
        self.assertIn("compose checks", result.stdout)
        self.assertIn("config planning checks", result.stdout)
        self.assertIn("layout checks", result.stdout)
        self.assertNotIn("pt730-app", result.stdout, "default self-test must not contact live Packet Tracer")


if __name__ == "__main__":
    unittest.main()
