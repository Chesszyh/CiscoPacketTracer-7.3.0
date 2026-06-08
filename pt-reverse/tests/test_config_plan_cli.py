#!/usr/bin/env python3
"""Tests for offline IOS config generation from topology plans."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PLAN = ROOT / "bin" / "pt730-config-plan"
SAFETY = ROOT / "bin" / "pt730-safety"


class ConfigPlanCliTest(unittest.TestCase):
    def topology(self) -> dict[str, Any]:
        return {
            "devices": [
                {"name": "MLS1", "category": "switch", "model": "2960-24TT"},
                {"name": "SW-OFFICE", "category": "switch", "model": "2960-24TT"},
                {"name": "PC-OFFICE-1", "category": "pc", "model": "PC-PT"},
                {"name": "SW-SRV", "category": "switch", "model": "2960-24TT"},
                {"name": "WEB-SRV", "category": "server", "model": "Server-PT"},
            ],
            "links": [
                {"a": "MLS1", "pa": "FastEthernet0/1", "b": "SW-OFFICE", "pb": "GigabitEthernet0/1", "cable": "cross", "vlan": 20},
                {"a": "SW-OFFICE", "pa": "FastEthernet0/1", "b": "PC-OFFICE-1", "pb": "FastEthernet0", "cable": "straight", "vlan": 20},
                {"a": "MLS1", "pa": "FastEthernet0/2", "b": "SW-SRV", "pb": "GigabitEthernet0/1", "cable": "cross", "vlan": 10},
                {"a": "SW-SRV", "pa": "FastEthernet0/1", "b": "WEB-SRV", "pb": "FastEthernet0", "cable": "straight", "vlan": 10},
            ],
            "ios_configs": [{"device": "MLS1", "source": "manual", "commands": ["enable", "show version"]}],
        }

    def l3_topology(self) -> dict[str, Any]:
        return {
            "devices": [
                {"name": "MLS1", "category": "switch", "model": "2960-24TT"},
                {"name": "MLS2", "category": "switch", "model": "2960-24TT"},
                {"name": "SW-OFFICE", "category": "switch", "model": "2960-24TT"},
                {"name": "SW-TEACH", "category": "switch", "model": "2960-24TT"},
                {"name": "PC-OFFICE-1", "category": "pc", "model": "PC-PT"},
                {"name": "PC-TEACH-1", "category": "pc", "model": "PC-PT"},
            ],
            "links": [
                {"a": "MLS1", "pa": "GigabitEthernet0/1", "b": "MLS2", "pb": "GigabitEthernet0/1", "cable": "cross", "note": "10.10.12.0/30"},
                {"a": "MLS1", "pa": "FastEthernet0/1", "b": "SW-OFFICE", "pb": "GigabitEthernet0/1", "cable": "cross", "vlan": 20},
                {"a": "SW-OFFICE", "pa": "FastEthernet0/1", "b": "PC-OFFICE-1", "pb": "FastEthernet0", "cable": "straight", "vlan": 20},
                {"a": "MLS2", "pa": "FastEthernet0/1", "b": "SW-TEACH", "pb": "GigabitEthernet0/1", "cable": "cross", "vlan": 30},
                {"a": "SW-TEACH", "pa": "FastEthernet0/1", "b": "PC-TEACH-1", "pb": "FastEthernet0", "cable": "straight", "vlan": 30},
            ],
            "pc_configs": [
                {"name": "PC-OFFICE-1", "port": "FastEthernet0", "ip": "192.168.0.1", "mask": "255.255.255.192", "gateway": "192.168.0.62"},
                {"name": "PC-TEACH-1", "port": "FastEthernet0", "ip": "192.168.0.65", "mask": "255.255.255.192", "gateway": "192.168.0.126"},
            ],
        }

    def run_config_plan(self, plan: dict[str, Any], *args: str) -> subprocess.CompletedProcess[str]:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as f:
            json.dump(plan, f)
            path = f.name
        try:
            return subprocess.run(
                [str(CONFIG_PLAN), "campus", path, *args],
                cwd=ROOT.parent,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
                check=False,
            )
        finally:
            Path(path).unlink(missing_ok=True)

    def test_schema_describes_config_plan_surface(self) -> None:
        result = subprocess.run(
            [str(CONFIG_PLAN), "schema"],
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
        self.assertIn("switch-switch links become trunk interfaces", data["rules"])
        self.assertIn("--routing none|rip|ospf|static", data["options"])
        self.assertIn("export-configs --source", data["options"])

    def test_campus_generates_switch_ios_configs_from_vlan_links(self) -> None:
        result = self.run_config_plan(self.topology())
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        configs = {config["device"]: config for config in data["ios_configs"] if config.get("source") == "pt730-config-plan campus"}
        self.assertEqual(set(configs), {"MLS1", "SW-OFFICE", "SW-SRV"})

        office_commands = [command.strip() for command in configs["SW-OFFICE"]["commands"]]
        self.assertIn("vlan 20", office_commands)
        self.assertIn("interface GigabitEthernet0/1", office_commands)
        self.assertIn("switchport mode trunk", office_commands)
        self.assertIn("switchport trunk allowed vlan 20", office_commands)
        self.assertIn("interface FastEthernet0/1", office_commands)
        self.assertIn("switchport mode access", office_commands)
        self.assertIn("switchport access vlan 20", office_commands)
        self.assertIn("no shutdown", office_commands)

        core_commands = [command.strip() for command in configs["MLS1"]["commands"]]
        self.assertIn("vlan 10", core_commands)
        self.assertIn("vlan 20", core_commands)
        self.assertIn("interface FastEthernet0/1", core_commands)
        self.assertIn("switchport trunk allowed vlan 20", core_commands)
        self.assertIn("interface FastEthernet0/2", core_commands)
        self.assertIn("switchport trunk allowed vlan 10", core_commands)

        manual_configs = [config for config in data["ios_configs"] if config.get("source") == "manual"]
        self.assertEqual(len(manual_configs), 1)

    def test_ios_only_outputs_config_records(self) -> None:
        result = self.run_config_plan(self.topology(), "--ios-only")
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(set(data), {"ios_configs"})
        self.assertEqual(len(data["ios_configs"]), 3)

    def test_campus_l3_generates_svis_routed_links_and_rip(self) -> None:
        result = self.run_config_plan(self.l3_topology(), "--l3", "--routing", "rip")
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        configs = {config["device"]: config for config in data["ios_configs"] if config.get("source") == "pt730-config-plan campus"}

        mls1_commands = [command.strip() for command in configs["MLS1"]["commands"]]
        self.assertIn("ip routing", mls1_commands)
        self.assertIn("interface Vlan20", mls1_commands)
        self.assertIn("ip address 192.168.0.62 255.255.255.192", mls1_commands)
        self.assertIn("interface GigabitEthernet0/1", mls1_commands)
        self.assertIn("no switchport", mls1_commands)
        self.assertIn("ip address 10.10.12.1 255.255.255.252", mls1_commands)
        self.assertIn("router rip", mls1_commands)
        self.assertIn("network 10.0.0.0", mls1_commands)
        self.assertIn("network 192.168.0.0", mls1_commands)

        mls2_commands = [command.strip() for command in configs["MLS2"]["commands"]]
        self.assertIn("interface Vlan30", mls2_commands)
        self.assertIn("ip address 192.168.0.126 255.255.255.192", mls2_commands)
        self.assertIn("ip address 10.10.12.2 255.255.255.252", mls2_commands)

        access_commands = [command.strip() for command in configs["SW-OFFICE"]["commands"]]
        self.assertNotIn("ip routing", access_commands)
        self.assertNotIn("interface Vlan20", access_commands)

    def test_campus_l3_can_generate_ospf_between_svis_and_routed_links(self) -> None:
        result = self.run_config_plan(self.l3_topology(), "--l3", "--routing", "ospf")
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        configs = {config["device"]: config for config in data["ios_configs"] if config.get("source") == "pt730-config-plan campus"}

        mls1_commands = [command.strip() for command in configs["MLS1"]["commands"]]
        self.assertIn("ip routing", mls1_commands)
        self.assertIn("router ospf 1", mls1_commands)
        self.assertIn("router-id 10.255.0.1", mls1_commands)
        self.assertIn("passive-interface Vlan20", mls1_commands)
        self.assertIn("network 192.168.0.0 0.0.0.63 area 0", mls1_commands)
        self.assertIn("network 10.10.12.0 0.0.0.3 area 0", mls1_commands)
        self.assertNotIn("router rip", mls1_commands)
        self.assertNotIn("ip route 192.168.0.64 255.255.255.192 10.10.12.2", mls1_commands)

        mls2_commands = [command.strip() for command in configs["MLS2"]["commands"]]
        self.assertIn("router-id 10.255.0.2", mls2_commands)
        self.assertIn("passive-interface Vlan30", mls2_commands)
        self.assertIn("network 192.168.0.64 0.0.0.63 area 0", mls2_commands)
        self.assertIn("network 10.10.12.0 0.0.0.3 area 0", mls2_commands)

    def test_campus_l3_can_generate_static_routes_between_svi_networks(self) -> None:
        result = self.run_config_plan(self.l3_topology(), "--l3", "--routing", "static")
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        configs = {config["device"]: config for config in data["ios_configs"] if config.get("source") == "pt730-config-plan campus"}

        mls1_commands = [command.strip() for command in configs["MLS1"]["commands"]]
        self.assertIn("ip route 192.168.0.64 255.255.255.192 10.10.12.2", mls1_commands)
        self.assertNotIn("router rip", mls1_commands)

        mls2_commands = [command.strip() for command in configs["MLS2"]["commands"]]
        self.assertIn("ip route 192.168.0.0 255.255.255.192 10.10.12.1", mls2_commands)

    def test_output_file_can_be_safety_checked(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            in_path = Path(tmpdir) / "topology.json"
            out_path = Path(tmpdir) / "configured.json"
            in_path.write_text(json.dumps(self.topology()), encoding="utf-8")
            result = subprocess.run(
                [str(CONFIG_PLAN), "campus", str(in_path), "--output", str(out_path)],
                cwd=ROOT.parent,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "")
            safety = subprocess.run(
                [str(SAFETY), "plan", str(out_path)],
                cwd=ROOT.parent,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
                check=False,
            )
            self.assertEqual(safety.returncode, 0, safety.stdout + safety.stderr)

    def test_export_configs_writes_device_cfg_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            in_path = Path(tmpdir) / "topology.json"
            configured_path = Path(tmpdir) / "configured.json"
            output_dir = Path(tmpdir) / "configs"
            in_path.write_text(json.dumps(self.topology()), encoding="utf-8")
            generated = subprocess.run(
                [str(CONFIG_PLAN), "campus", str(in_path), "--output", str(configured_path)],
                cwd=ROOT.parent,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
                check=False,
            )
            self.assertEqual(generated.returncode, 0, generated.stderr)
            exported = subprocess.run(
                [str(CONFIG_PLAN), "export-configs", str(configured_path), "--output-dir", str(output_dir)],
                cwd=ROOT.parent,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
                check=False,
            )
            self.assertEqual(exported.returncode, 0, exported.stderr)
            manifest = json.loads(exported.stdout)
            self.assertEqual(manifest["count"], 4)
            office_cfg = output_dir / "SW-OFFICE.cfg"
            self.assertTrue(office_cfg.exists())
            self.assertIn("switchport access vlan 20", office_cfg.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
