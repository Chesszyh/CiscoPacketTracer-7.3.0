#!/usr/bin/env python3
"""Tests for built-in topology templates."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "bin" / "pt730-template"
SAFETY = ROOT / "bin" / "pt730-safety"
RENDER = ROOT / "bin" / "pt730-render"


class TemplateCliTest(unittest.TestCase):
    def run_template(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(TEMPLATE), *args],
            cwd=ROOT.parent,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
        )

    def assert_safe_and_renderable(self, plan: dict) -> None:
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
        finally:
            Path(path).unlink(missing_ok=True)

    def test_schema_lists_builtin_templates(self) -> None:
        result = self.run_template("schema")
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertIn("lan-star", data["commands"])
        self.assertIn("router-ring", data["commands"])
        self.assertIn("lan-star", data["templates"])
        self.assertIn("router-ring", data["templates"])

    def test_lan_star_generates_static_hosts_server_services_and_layout(self) -> None:
        result = self.run_template(
            "lan-star",
            "--name",
            "DEMO",
            "--pcs",
            "3",
            "--servers",
            "1",
            "--network",
            "192.168.10.0/24",
            "--gateway",
            "192.168.10.1",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = json.loads(result.stdout)
        names = {device["name"] for device in plan["devices"]}
        self.assertEqual(names, {"R-DEMO", "SW-DEMO", "PC-DEMO-1", "PC-DEMO-2", "PC-DEMO-3", "SRV-DEMO-1"})
        self.assertTrue(all("x" in device and "y" in device for device in plan["devices"]))
        self.assertEqual(len(plan["links"]), 5)
        self.assertEqual(len(plan["pc_configs"]), 4)
        self.assertEqual(plan["pc_configs"][0]["gateway"], "192.168.10.1")
        self.assertEqual(plan["server_configs"][0]["http"], True)
        self.assert_safe_and_renderable(plan)

    def test_router_ring_generates_serial_modules_links_and_rip_configs(self) -> None:
        result = self.run_template("router-ring", "--routers", "4", "--interconnect-pool", "10.20.0.0/28")
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = json.loads(result.stdout)
        self.assertEqual(len(plan["devices"]), 4)
        self.assertEqual(len(plan["modules"]), 4)
        self.assertEqual(len(plan["links"]), 4)
        self.assertEqual(len(plan["ios_configs"]), 4)
        commands = [command.strip() for command in plan["ios_configs"][0]["commands"]]
        self.assertIn("router rip", commands)
        self.assertIn("clock rate 64000", commands)
        self.assert_safe_and_renderable(plan)


if __name__ == "__main__":
    unittest.main()
