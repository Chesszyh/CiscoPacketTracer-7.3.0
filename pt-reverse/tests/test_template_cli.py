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
        self.assertIn("wan-ring", data["commands"])
        self.assertIn("wireless-lan", data["commands"])
        self.assertIn("campus", data["commands"])
        self.assertIn("lan-star", data["templates"])
        self.assertIn("wireless-lan", data["templates"])
        self.assertIn("router-ring", data["templates"])
        self.assertIn("wan-ring", data["templates"])
        self.assertIn("campus", data["templates"])

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

    def test_wireless_lan_generates_safe_aps_laptops_services_and_layout(self) -> None:
        result = self.run_template(
            "wireless-lan",
            "--name",
            "WIFI",
            "--aps",
            "2",
            "--laptops",
            "4",
            "--servers",
            "1",
            "--network",
            "192.168.80.0/24",
            "--gateway",
            "192.168.80.1",
            "--ssid",
            "CLASSROOM",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = json.loads(result.stdout)
        names = {device["name"] for device in plan["devices"]}
        self.assertEqual(
            names,
            {
                "R-WIFI",
                "SW-WIFI",
                "AP-WIFI-1",
                "AP-WIFI-2",
                "LAP-WIFI-1",
                "LAP-WIFI-2",
                "LAP-WIFI-3",
                "LAP-WIFI-4",
                "SRV-WIFI-1",
            },
        )
        self.assertTrue(all("x" in device and "y" in device for device in plan["devices"]))
        models = {device["model"] for device in plan["devices"]}
        self.assertEqual(models, {"2911", "2960-24TT", "AccessPoint-PT", "Laptop-PT", "Server-PT"})
        self.assertEqual(len(plan["links"]), 8)
        self.assertEqual(len([link for link in plan["links"] if link.get("cable") == "wireless"]), 4)
        self.assertEqual(len(plan["pc_configs"]), 5)
        self.assertEqual(len(plan["ap_configs"]), 2)
        self.assertEqual(plan["ap_configs"][0]["ssid"], "CLASSROOM")
        self.assertEqual(plan["pc_configs"][0]["gateway"], "192.168.80.1")
        self.assertEqual(plan["pc_configs"][0]["dns"], "192.168.80.6")
        self.assertEqual(plan["server_configs"][0]["http"], True)
        self.assertIn("dns", plan["server_configs"][0])
        self.assertEqual(plan["metadata"]["source"], "pt730-template wireless-lan")
        self.assertEqual(plan["metadata"]["ssid"], "CLASSROOM")
        encoded = json.dumps(plan)
        self.assertNotIn("WirelessEndDevice-PT", encoded)
        self.assertNotIn("SMARTPHONE-PT", encoded)
        self.assertNotIn("WRT300N", encoded)
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

    def test_wan_ring_generates_site_lans_services_and_routing_configs(self) -> None:
        result = self.run_template(
            "wan-ring",
            "--name",
            "BRANCH",
            "--sites",
            "3",
            "--hosts-per-site",
            "2",
            "--servers-per-site",
            "1",
            "--interconnect-pool",
            "10.30.0.0/28",
            "--lan-pool",
            "192.168.100.0/22",
            "--routing",
            "static",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = json.loads(result.stdout)
        names = {device["name"] for device in plan["devices"]}
        self.assertIn("R-BRANCH-1", names)
        self.assertIn("SW-BRANCH-2", names)
        self.assertIn("PC-BRANCH-3-2", names)
        self.assertIn("SRV-BRANCH-1-1", names)
        self.assertTrue(all("x" in device and "y" in device for device in plan["devices"]))
        self.assertEqual(len(plan["devices"]), 15)
        self.assertEqual(len(plan["modules"]), 3)
        self.assertEqual(len(plan["links"]), 15)
        self.assertEqual(len(plan["pc_configs"]), 9)
        self.assertEqual(len(plan["ios_configs"]), 3)
        self.assertEqual(plan["metadata"]["source"], "pt730-template wan-ring")
        services = {config["name"]: config for config in plan["server_configs"]}
        self.assertIn("dns", services["SRV-BRANCH-1-1"])
        self.assertEqual(len(services["SRV-BRANCH-1-1"]["dns"]["records"]), 3)
        joined = "\n".join(command for config in plan["ios_configs"] for command in config["commands"])
        self.assertIn("ip route 192.168.101.0 255.255.255.0 10.30.0.2", joined)
        self.assertIn("interface Serial0/0/0", joined)
        self.assertNotIn("3560-24PS", json.dumps(plan))
        self.assert_safe_and_renderable(plan)

    def test_campus_generates_core_access_servers_services_and_l3_configs(self) -> None:
        result = self.run_template(
            "campus",
            "--name",
            "AGENT",
            "--cores",
            "2",
            "--segments",
            "3",
            "--hosts-per-segment",
            "2",
            "--servers",
            "4",
            "--l3",
            "--routing",
            "rip",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = json.loads(result.stdout)
        names = {device["name"] for device in plan["devices"]}
        self.assertIn("MLS1", names)
        self.assertIn("MLS2", names)
        self.assertIn("SW-AGENT-SRV", names)
        self.assertIn("SRV-AGENT-WEB", names)
        self.assertIn("SRV-AGENT-DNS", names)
        self.assertIn("PC-SEG-3-2", names)
        self.assertTrue(all("x" in device and "y" in device for device in plan["devices"]))
        self.assertEqual(plan["metadata"]["source"], "pt730-template campus")
        self.assertEqual(len(plan["pc_configs"]), 10)
        self.assertEqual({link.get("vlan") for link in plan["links"] if "vlan" in link}, {10, 20, 21, 22})
        services = {config["name"]: config for config in plan["server_configs"]}
        self.assertIn("http", services["SRV-AGENT-WEB"])
        self.assertIn("dns", services["SRV-AGENT-DNS"])
        self.assertIn("ftp", services["SRV-AGENT-FTP"])
        self.assertIn("email", services["SRV-AGENT-MAIL"])
        joined = "\n".join(command for config in plan["ios_configs"] for command in config["commands"])
        self.assertIn("ip routing", joined)
        self.assertIn("router rip", joined)
        self.assert_safe_and_renderable(plan)


if __name__ == "__main__":
    unittest.main()
