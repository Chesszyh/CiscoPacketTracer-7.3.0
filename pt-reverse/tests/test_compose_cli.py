#!/usr/bin/env python3
"""Tests for high-level topology composition."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "bin" / "pt730-compose"
SAFETY = ROOT / "bin" / "pt730-safety"
RENDER = ROOT / "bin" / "pt730-render"


class ComposeCliTest(unittest.TestCase):
    def run_compose(self, spec: dict[str, Any], *args: str) -> subprocess.CompletedProcess[str]:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as f:
            json.dump(spec, f)
            path = f.name
        try:
            return subprocess.run(
                [str(COMPOSE), "campus", path, *args],
                cwd=ROOT.parent,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
                check=False,
            )
        finally:
            Path(path).unlink(missing_ok=True)

    def campus_spec(self) -> dict[str, Any]:
        return {
            "name": "agent-college",
            "core": {"count": 2, "prefix": "MLS"},
            "server_defaults": {
                "mask": "255.255.255.192",
                "gateway": "172.16.1.62",
                "dns": "172.16.1.11",
            },
            "server_switch": {"name": "SW-SRV", "vlan": 10, "core": "MLS1"},
            "servers": [
                {"name": "WEB-SRV", "ip": "172.16.1.10", "services": {"http": True}},
                {
                    "name": "DNS-SRV",
                    "ip": "172.16.1.11",
                    "services": {"dns": {"enabled": True, "records": [{"name": "www.college.local", "ip": "172.16.1.10"}]}},
                },
            ],
            "segments": [
                {
                    "name": "OFFICE",
                    "vlan": 20,
                    "subnet": "192.168.0.0/26",
                    "gateway": "192.168.0.62",
                    "dns": "172.16.1.11",
                    "representative_hosts": 2,
                    "core": "MLS1",
                },
                {
                    "name": "TEACH",
                    "vlan": 30,
                    "subnet": "192.168.0.64/26",
                    "gateway": "192.168.0.126",
                    "dns": "172.16.1.11",
                    "representative_hosts": 3,
                    "core": "MLS2",
                },
            ],
        }

    def test_schema_describes_agent_friendly_compose_spec(self) -> None:
        result = subprocess.run(
            [str(COMPOSE), "schema"],
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
        self.assertIn("segments[].representative_hosts", data["fields"])
        self.assertIn("servers[].services", data["fields"])
        self.assertEqual(data["example"]["core"]["prefix"], "MLS")

    def test_campus_spec_generates_safe_layout_ready_topology(self) -> None:
        result = self.run_compose(self.campus_spec())
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = json.loads(result.stdout)

        names = {device["name"] for device in plan["devices"]}
        self.assertIn("MLS1", names)
        self.assertIn("MLS2", names)
        self.assertIn("SW-SRV", names)
        self.assertIn("WEB-SRV", names)
        self.assertIn("DNS-SRV", names)
        self.assertIn("SW-OFFICE", names)
        self.assertIn("SW-TEACH", names)
        self.assertIn("PC-OFFICE-1", names)
        self.assertIn("PC-TEACH-3", names)
        self.assertTrue(all("x" in device and "y" in device for device in plan["devices"]))

        self.assertEqual(len(plan["server_configs"]), 2)
        dns_config = next(config for config in plan["server_configs"] if config["name"] == "DNS-SRV")
        self.assertEqual(dns_config["dns"]["records"][0]["name"], "www.college.local")
        pc_configs = {config["name"]: config for config in plan["pc_configs"]}
        self.assertEqual(pc_configs["WEB-SRV"]["gateway"], "172.16.1.62")
        self.assertEqual(pc_configs["PC-OFFICE-1"]["ip"], "192.168.0.1")
        self.assertEqual(pc_configs["PC-TEACH-3"]["ip"], "192.168.0.67")

        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as f:
            json.dump(plan, f)
            path = f.name
        try:
            safety = subprocess.run(
                [str(SAFETY), "plan", path],
                cwd=ROOT.parent,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
                check=False,
            )
            self.assertEqual(safety.returncode, 0, safety.stdout + safety.stderr)
            render = subprocess.run(
                [str(RENDER), "summary", path],
                cwd=ROOT.parent,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
                check=False,
            )
            self.assertEqual(render.returncode, 0, render.stderr)
            summary = json.loads(render.stdout)
            self.assertEqual(summary["counts"]["devices"], len(plan["devices"]))
            self.assertIn("192.168.0.0/26", [group["network"] for group in summary["address_groups"]])
            self.assertEqual(summary["vlan_link_counts"]["20"], 3)
        finally:
            Path(path).unlink(missing_ok=True)

    def test_output_file_suppresses_stdout(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            spec_path = Path(tmpdir) / "campus.json"
            out_path = Path(tmpdir) / "topology.json"
            spec_path.write_text(json.dumps(self.campus_spec()), encoding="utf-8")
            result = subprocess.run(
                [str(COMPOSE), "campus", str(spec_path), "--output", str(out_path)],
                cwd=ROOT.parent,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "")
            self.assertIn("devices", json.loads(out_path.read_text(encoding="utf-8")))

    def test_can_load_segments_from_ip_plan_output(self) -> None:
        ip_plan = {
            "kind": "pt730-ip-plan",
            "compose": {
                "segments": [
                    {
                        "name": "OFFICE",
                        "vlan": 20,
                        "subnet": "192.168.0.0/26",
                        "gateway": "192.168.0.62",
                        "dns": "172.16.1.11",
                        "representative_hosts": 2,
                        "core": "MLS1",
                    }
                ]
            },
        }
        compose_spec = {
            "name": "ip-planned-campus",
            "core": {"count": 1, "prefix": "MLS"},
            "segments": [],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            spec_path = Path(tmpdir) / "campus.json"
            ip_path = Path(tmpdir) / "planned.json"
            spec_path.write_text(json.dumps(compose_spec), encoding="utf-8")
            ip_path.write_text(json.dumps(ip_plan), encoding="utf-8")
            result = subprocess.run(
                [str(COMPOSE), "campus", str(spec_path), "--segments-from-ip-plan", str(ip_path)],
                cwd=ROOT.parent,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            plan = json.loads(result.stdout)
            names = {device["name"] for device in plan["devices"]}
            self.assertIn("SW-OFFICE", names)
            self.assertIn("PC-OFFICE-1", names)
            pc_configs = {config["name"]: config for config in plan["pc_configs"]}
            self.assertEqual(pc_configs["PC-OFFICE-1"]["gateway"], "192.168.0.62")

    def test_rejects_gateway_outside_segment_subnet(self) -> None:
        spec = self.campus_spec()
        spec["segments"][0]["gateway"] = "192.168.1.254"
        result = self.run_compose(spec)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("gateway outside subnet", result.stderr)


if __name__ == "__main__":
    unittest.main()
