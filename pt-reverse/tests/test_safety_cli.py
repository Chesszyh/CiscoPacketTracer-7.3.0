#!/usr/bin/env python3
"""Tests for offline topology safety validation."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SAFETY = ROOT / "bin" / "pt730-safety"


class SafetyCliTest(unittest.TestCase):
    def run_plan(self, plan: dict) -> subprocess.CompletedProcess[str]:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as f:
            json.dump(plan, f)
            path = f.name
        try:
            return subprocess.run(
                [str(SAFETY), "plan", path],
                cwd=ROOT.parent,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
                check=False,
            )
        finally:
            Path(path).unlink(missing_ok=True)

    def test_duplicate_device_names_fail_offline(self) -> None:
        result = self.run_plan(
            {
                "devices": [
                    {"name": "PC1", "category": "pc", "model": "PC-PT"},
                    {"name": "PC1", "category": "pc", "model": "PC-PT"},
                ]
            }
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("duplicate device name", result.stdout)

    def test_link_to_missing_device_fails_offline(self) -> None:
        result = self.run_plan(
            {
                "devices": [{"name": "PC1", "category": "pc", "model": "PC-PT"}],
                "links": [{"a": "PC1", "pa": "FastEthernet0", "b": "SW1", "pb": "FastEthernet0/1"}],
            }
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unknown endpoint device", result.stdout)

    def test_config_for_missing_device_fails_offline(self) -> None:
        result = self.run_plan(
            {
                "devices": [{"name": "PC1", "category": "pc", "model": "PC-PT"}],
                "pc_configs": [{"name": "PC2", "ip": "192.168.1.2", "mask": "255.255.255.0"}],
            }
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unknown configured device", result.stdout)

    def test_link_to_missing_port_fails_offline(self) -> None:
        result = self.run_plan(
            {
                "devices": [
                    {"name": "PC1", "category": "pc", "model": "PC-PT"},
                    {"name": "SW1", "category": "switch", "model": "2960-24TT"},
                ],
                "links": [{"a": "PC1", "pa": "FastEthernet9", "b": "SW1", "pb": "FastEthernet0/1"}],
            }
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unknown port", result.stdout)

    def test_verified_module_ports_are_accepted(self) -> None:
        result = self.run_plan(
            {
                "devices": [
                    {"name": "R1", "category": "router", "model": "2911"},
                    {"name": "R2", "category": "router", "model": "2911"},
                ],
                "modules": [
                    {"device": "R1", "slot": "0/0", "model": "HWIC-2T"},
                    {"device": "R2", "slot": "0/0", "model": "HWIC-2T"},
                ],
                "links": [{"a": "R1", "pa": "Serial0/0/0", "b": "R2", "pb": "Serial0/0/0", "cable": "serial"}],
            }
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_invalid_pc_ip_fails_offline(self) -> None:
        result = self.run_plan(
            {
                "devices": [{"name": "PC1", "category": "pc", "model": "PC-PT"}],
                "pc_configs": [{"name": "PC1", "ip": "192.168.300.1", "mask": "255.255.255.0"}],
            }
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("invalid IPv4 address", result.stdout)

    def test_gateway_outside_pc_subnet_fails_offline(self) -> None:
        result = self.run_plan(
            {
                "devices": [{"name": "PC1", "category": "pc", "model": "PC-PT"}],
                "pc_configs": [
                    {"name": "PC1", "ip": "192.168.1.10", "mask": "255.255.255.0", "gateway": "192.168.2.1"}
                ],
            }
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("gateway outside subnet", result.stdout)

    def test_dhcp_pool_start_outside_network_fails_offline(self) -> None:
        result = self.run_plan(
            {
                "devices": [{"name": "SRV1", "category": "server", "model": "Server-PT"}],
                "server_configs": [
                    {
                        "name": "SRV1",
                        "dhcp": {
                            "enabled": True,
                            "network": "192.168.10.0",
                            "mask": "255.255.255.0",
                            "start": "192.168.11.10",
                            "end": "192.168.10.100",
                            "gateway": "192.168.10.1",
                        },
                    }
                ],
            }
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("outside DHCP network", result.stdout)

    def test_ios_config_unknown_physical_interface_fails_offline(self) -> None:
        result = self.run_plan(
            {
                "devices": [{"name": "R1", "category": "router", "model": "2911"}],
                "ios_configs": [{"device": "R1", "commands": ["interface GigabitEthernet0/99", "ip address 10.0.0.1 255.255.255.0"]}],
            }
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unknown IOS interface", result.stdout)

    def test_ios_config_interface_without_no_shutdown_warns_offline(self) -> None:
        result = self.run_plan(
            {
                "devices": [{"name": "R1", "category": "router", "model": "2911"}],
                "ios_configs": [{"device": "R1", "commands": ["interface GigabitEthernet0/0", "ip address 10.0.0.1 255.255.255.0"]}],
            }
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("configured IOS interface has no no shutdown", result.stdout)

    def test_serial_link_without_clock_rate_warns_offline(self) -> None:
        result = self.run_plan(
            {
                "devices": [
                    {"name": "R1", "category": "router", "model": "2911"},
                    {"name": "R2", "category": "router", "model": "2911"},
                ],
                "modules": [
                    {"device": "R1", "slot": "0/0", "model": "HWIC-2T"},
                    {"device": "R2", "slot": "0/0", "model": "HWIC-2T"},
                ],
                "links": [{"a": "R1", "pa": "Serial0/0/0", "b": "R2", "pb": "Serial0/0/0", "cable": "serial"}],
                "ios_configs": [
                    {"device": "R1", "commands": ["interface Serial0/0/0", "ip address 10.0.0.1 255.255.255.252", "no shutdown"]},
                    {"device": "R2", "commands": ["interface Serial0/0/0", "ip address 10.0.0.2 255.255.255.252", "no shutdown"]},
                ],
            }
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("serial link has no clock rate", result.stdout)


if __name__ == "__main__":
    unittest.main()
