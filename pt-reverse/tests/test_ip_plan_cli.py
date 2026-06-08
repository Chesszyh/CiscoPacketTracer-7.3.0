#!/usr/bin/env python3
"""Tests for offline IP/VLAN planning."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
IP_PLAN = ROOT / "bin" / "pt730-ip-plan"
COMPOSE = ROOT / "bin" / "pt730-compose"
SAFETY = ROOT / "bin" / "pt730-safety"


class IpPlanCliTest(unittest.TestCase):
    def run_plan(self, spec: dict[str, Any], *args: str) -> subprocess.CompletedProcess[str]:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as f:
            json.dump(spec, f)
            path = f.name
        try:
            return subprocess.run(
                [str(IP_PLAN), "campus", path, *args],
                cwd=ROOT.parent,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
                check=False,
            )
        finally:
            Path(path).unlink(missing_ok=True)

    def plan_spec(self) -> dict[str, Any]:
        return {
            "address_pool": "192.168.0.0/21",
            "dns": "172.16.1.11",
            "default_representative_hosts": 2,
            "groups": [
                {"name": "OFFICE", "hosts": 60, "vlan": 20, "core": "MLS1"},
                {"name": "TEACH", "hosts": 60, "vlan": 30, "core": "MLS2"},
                {"name": "RESEARCH", "hosts": 120, "vlan": 40, "representative_hosts": 3},
                {"name": "GRAD", "hosts": 200, "vlan": 50},
            ],
        }

    def test_schema_describes_ip_plan_spec(self) -> None:
        result = subprocess.run(
            [str(IP_PLAN), "schema"],
            cwd=ROOT.parent,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertIn("campus", data["commands"])
        self.assertIn("groups[].hosts", data["fields"])
        self.assertEqual(data["example"]["address_pool"], "192.168.0.0/21")

    def test_campus_plans_vlsm_segments_in_input_order(self) -> None:
        result = self.run_plan(self.plan_spec())
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        segments = data["segments"]
        self.assertEqual([segment["name"] for segment in segments], ["OFFICE", "TEACH", "RESEARCH", "GRAD"])
        self.assertEqual([segment["subnet"] for segment in segments], ["192.168.0.0/26", "192.168.0.64/26", "192.168.0.128/25", "192.168.1.0/24"])
        self.assertEqual([segment["gateway"] for segment in segments], ["192.168.0.62", "192.168.0.126", "192.168.0.254", "192.168.1.254"])
        self.assertEqual(segments[0]["capacity_hosts"], 61)
        self.assertEqual(segments[2]["representative_hosts"], 3)
        self.assertEqual(data["compose"]["segments"][0]["dns"], "172.16.1.11")
        self.assertEqual(data["compose"]["segments"][0]["core"], "MLS1")
        self.assertEqual(data["unused"][0]["subnet"], "192.168.2.0/23")

    def test_output_segments_feed_compose_and_safety(self) -> None:
        ip_result = self.run_plan(self.plan_spec())
        self.assertEqual(ip_result.returncode, 0, ip_result.stderr)
        planned = json.loads(ip_result.stdout)
        compose_spec = {
            "name": "planned-campus",
            "core": {"count": 2, "prefix": "MLS"},
            "server_defaults": {"mask": "255.255.255.192", "gateway": "172.16.1.62", "dns": "172.16.1.11"},
            "server_switch": {"name": "SW-SRV", "vlan": 10, "core": "MLS1"},
            "servers": [{"name": "DNS-SRV", "ip": "172.16.1.11", "services": {"dns": {"enabled": True}}}],
            "segments": planned["compose"]["segments"],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            spec_path = Path(tmpdir) / "compose.json"
            plan_path = Path(tmpdir) / "topology.json"
            spec_path.write_text(json.dumps(compose_spec), encoding="utf-8")
            compose = subprocess.run(
                [str(COMPOSE), "campus", str(spec_path), "--output", str(plan_path)],
                cwd=ROOT.parent,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
                check=False,
            )
            self.assertEqual(compose.returncode, 0, compose.stderr)
            safety = subprocess.run(
                [str(SAFETY), "plan", str(plan_path)],
                cwd=ROOT.parent,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
                check=False,
            )
            self.assertEqual(safety.returncode, 0, safety.stdout + safety.stderr)

    def test_output_file_suppresses_stdout(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            spec_path = Path(tmpdir) / "ip-plan.json"
            out_path = Path(tmpdir) / "planned.json"
            spec_path.write_text(json.dumps(self.plan_spec()), encoding="utf-8")
            result = subprocess.run(
                [str(IP_PLAN), "campus", str(spec_path), "--output", str(out_path)],
                cwd=ROOT.parent,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "")
            self.assertIn("segments", json.loads(out_path.read_text(encoding="utf-8")))

    def test_rejects_insufficient_address_pool(self) -> None:
        spec = {
            "address_pool": "192.168.0.0/30",
            "groups": [{"name": "TOO-BIG", "hosts": 4, "vlan": 10}],
        }
        result = self.run_plan(spec)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("does not fit inside address pool", result.stderr)


if __name__ == "__main__":
    unittest.main()
