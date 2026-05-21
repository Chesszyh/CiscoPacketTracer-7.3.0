#!/usr/bin/env python3
"""Tests for topology CLI offline behaviors."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOPO = ROOT / "bin" / "pt730-topo"


class TopologyCliTest(unittest.TestCase):
    def test_apply_dry_run_returns_summary_without_live_bridge(self) -> None:
        result = subprocess.run(
            [str(TOPO), "--timeout", "1", "apply", "--dry-run", str(ROOT / "examples" / "simple-lan.json")],
            cwd=ROOT.parent,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertTrue(data["dry_run"])
        self.assertEqual(data["counts"]["devices"], 3)
        self.assertEqual(data["counts"]["links"], 2)

    def test_apply_dry_run_rejects_risky_model_before_live_bridge(self) -> None:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as f:
            json.dump({"devices": [{"name": "BAD", "category": "switch", "model": "3560-24PS"}]}, f)
            path = f.name
        try:
            result = subprocess.run(
                [str(TOPO), "--timeout", "1", "apply", "--dry-run", path],
                cwd=ROOT.parent,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
                check=False,
            )
        finally:
            Path(path).unlink(missing_ok=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("safety check failed", result.stderr)

    def test_apply_dry_run_rejects_unknown_ios_interface_before_live_bridge(self) -> None:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as f:
            json.dump(
                {
                    "devices": [{"name": "R1", "category": "router", "model": "2911"}],
                    "ios_configs": [{"device": "R1", "commands": ["interface GigabitEthernet0/99", "ip address 10.0.0.1 255.255.255.0"]}],
                },
                f,
            )
            path = f.name
        try:
            result = subprocess.run(
                [str(TOPO), "--timeout", "1", "apply", "--dry-run", path],
                cwd=ROOT.parent,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
                check=False,
            )
        finally:
            Path(path).unlink(missing_ok=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unknown IOS interface", result.stderr)

    def test_apply_dry_run_rejects_model_marked_risky_by_validation_overlay(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            validation_path = Path(tmpdir) / "model-validations.json"
            validation_path.write_text(
                json.dumps({"version": 1, "validations": {"1841": {"status": "risky", "note": "crashed during local validation"}}}),
                encoding="utf-8",
            )
            plan_path = Path(tmpdir) / "plan.json"
            plan_path.write_text(json.dumps({"devices": [{"name": "R1", "category": "router", "model": "1841"}]}), encoding="utf-8")
            env = os.environ.copy()
            env["PT730_MODEL_VALIDATIONS"] = str(validation_path)
            result = subprocess.run(
                [str(TOPO), "--timeout", "1", "apply", "--dry-run", str(plan_path)],
                cwd=ROOT.parent,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
                check=False,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("crashed during local validation", result.stderr)

    def test_summarize_query_extracts_links_ip_and_services(self) -> None:
        query = {
            "devices": [
                {
                    "name": "R1",
                    "model": "2911",
                    "type": "0",
                    "ports": [{"name": "GigabitEthernet0/0", "linked": True, "ip": "10.0.0.1", "mask": "255.255.255.0"}],
                    "command_line": {
                        "prompt": "R1#",
                        "output_tail": "\nshow running-config\ninterface GigabitEthernet0/0\n ip address 10.0.0.1 255.255.255.0\n ip nat inside\n no shutdown\nrouter rip\n version 2\n network 10.0.0.0\nip route 0.0.0.0 0.0.0.0 10.0.0.254\naccess-list 10 permit 10.0.0.0 0.0.0.255\nip nat inside source list 10 interface GigabitEthernet0/1 overload\n",
                    },
                },
                {
                    "name": "SRV1",
                    "model": "Server-PT",
                    "type": "9",
                    "ports": [{"name": "FastEthernet0", "linked": True, "ip": "10.0.0.10", "mask": "255.255.255.0", "gateway": "10.0.0.1", "dns": "10.0.0.10"}],
                    "services": {"http": {"enabled": True}, "dns": {"enabled": True}},
                },
            ],
            "links": [{"a": "R1", "pa": "GigabitEthernet0/0", "b": "SRV1", "pb": "FastEthernet0", "cable": "8100"}],
        }
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as f:
            json.dump(query, f)
            path = f.name
        try:
            result = subprocess.run(
                [str(TOPO), "summarize-query", path],
                cwd=ROOT.parent,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
                check=False,
            )
        finally:
            Path(path).unlink(missing_ok=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["counts"]["devices"], 2)
        self.assertEqual(data["links"][0]["a"], "R1")
        self.assertEqual(data["ip_configs"][0]["device"], "R1")
        self.assertEqual(data["server_services"][0]["device"], "SRV1")
        self.assertEqual(data["ios_devices"][0]["device"], "R1")
        self.assertEqual(data["config_summaries"][0]["device"], "R1")
        self.assertIn("GigabitEthernet0/0", data["config_summaries"][0]["interfaces"])
        self.assertEqual(data["config_summaries"][0]["routing"]["rip_networks"], ["10.0.0.0"])
        self.assertEqual(data["config_summaries"][0]["routing"]["static_routes"][0]["next_hop"], "10.0.0.254")
        self.assertIn("10", data["config_summaries"][0]["acl_numbers"])
        self.assertTrue(data["config_summaries"][0]["nat"]["overload"])


if __name__ == "__main__":
    unittest.main()
