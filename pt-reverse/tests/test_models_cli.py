#!/usr/bin/env python3
"""Tests for PT 7.3.0 model safety registry CLI."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "bin" / "pt730-models"


class ModelsCliTest(unittest.TestCase):
    def run_cmd(self, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        proc_env = os.environ.copy()
        if env:
            proc_env.update(env)
        return subprocess.run(
            [str(MODELS), *args],
            cwd=ROOT.parent,
            env=proc_env,
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

    def test_queue_lists_unverified_models_with_guarded_commands(self) -> None:
        result = self.run_cmd("queue")
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertGreater(data["counts"]["unverified"], 0)
        self.assertEqual(data["items"][0]["status"], "unverified")
        self.assertIn("--dry-run", data["items"][0]["dry_run_command"])
        self.assertIn("--live", data["items"][0]["live_command"])

    def test_validate_batch_dry_run_lists_one_at_a_time_steps(self) -> None:
        result = self.run_cmd("validate-batch", "--dry-run", "--limit", "2")
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertTrue(data["dry_run"])
        self.assertEqual(data["count"], 2)
        self.assertEqual(len(data["items"]), 2)
        self.assertIn("validate", data["items"][0]["command"])
        self.assertIn("--live", data["items"][0]["command"])
        self.assertIn("record", data["items"][0]["after_failure"])

    def test_validate_batch_quotes_blocked_model_names_when_included(self) -> None:
        result = self.run_cmd("validate-batch", "--dry-run", "--include-blocked")
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        blocked = next(item for item in data["items"] if item["model"] == "Power Distribution Device")
        self.assertIn("'Power Distribution Device'", blocked["command"])
        self.assertIn("--allow-blocked", blocked["command"])

    def test_record_failed_validation_marks_model_risky_with_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env = {"PT730_MODEL_VALIDATIONS": str(Path(tmpdir) / "model-validations.json")}
            recorded = self.run_cmd("record", "1841", "--status", "risky", "--reason", "Packet Tracer crashed", "--evidence", "dump=1.dmp", env=env)
            self.assertEqual(recorded.returncode, 0, recorded.stderr)
            manifest = self.run_cmd("manifest", env=env)
            self.assertEqual(manifest.returncode, 0, manifest.stderr)
        data = json.loads(manifest.stdout)
        self.assertIn("1841", data["risky"])
        self.assertNotIn("1841", data["unverified"])
        record = next(item for item in data["records"]["risky"] if item["model"] == "1841")
        self.assertIn("Packet Tracer crashed", record["note"])
        self.assertEqual(record["validation"]["evidence"], ["dump=1.dmp"])

    def test_record_rejects_safe_without_save_reopen_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env = {"PT730_MODEL_VALIDATIONS": str(Path(tmpdir) / "model-validations.json")}
            result = self.run_cmd("record", "1841", "--status", "safe", "--reason", "query worked", env=env)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("save/reopen", result.stderr)


if __name__ == "__main__":
    unittest.main()
