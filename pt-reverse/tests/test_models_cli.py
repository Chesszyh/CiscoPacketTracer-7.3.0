#!/usr/bin/env python3
"""Tests for PT 7.3.0 model safety registry CLI."""

from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "bin" / "pt730-models"


class ModelsCliTest(unittest.TestCase):
    def run_cmd(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(MODELS), *args],
            cwd=ROOT.parent,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
        )

    def test_manifest_groups_common_models_by_status(self) -> None:
        result = self.run_cmd("manifest")
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertIn("2911", data["safe"])
        self.assertIn("3560-24PS", data["risky"])
        self.assertIn("3650-24PS", data["risky"])
        self.assertIn("1841", data["unverified"])
        self.assertIn("Power Distribution Device", data["blocked"])

    def test_probe_plan_for_unverified_common_model_is_guarded(self) -> None:
        result = self.run_cmd("probe-plan", "1841")
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["model"], "1841")
        self.assertEqual(data["status"], "unverified")
        self.assertFalse(data["unattended_safe"])
        self.assertEqual(data["plan"]["devices"][0]["model"], "1841")

    def test_probe_plan_rejects_blocked_model_by_default(self) -> None:
        result = self.run_cmd("probe-plan", "Power Distribution Device")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("blocked", result.stderr)

    def test_probe_plan_allows_risky_only_with_flag(self) -> None:
        rejected = self.run_cmd("probe-plan", "3560-24PS")
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn("risky", rejected.stderr)
        allowed = self.run_cmd("probe-plan", "3560-24PS", "--allow-risky")
        self.assertEqual(allowed.returncode, 0, allowed.stderr)
        self.assertEqual(json.loads(allowed.stdout)["status"], "risky")

    def test_validate_dry_run_prints_guarded_commands_without_live_bridge(self) -> None:
        result = self.run_cmd("validate", "1841", "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertTrue(data["dry_run"])
        self.assertEqual(data["model"], "1841")
        self.assertIn("pt730-topo apply", data["steps"][0]["command"])
        self.assertIn("pt730-topo query --summary", data["steps"][1]["command"])

    def test_validate_refuses_live_without_explicit_flag(self) -> None:
        result = self.run_cmd("validate", "1841")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--live", result.stderr)


if __name__ == "__main__":
    unittest.main()
