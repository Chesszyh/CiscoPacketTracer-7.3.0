#!/usr/bin/env python3
"""Tests for offline topology plan editing."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "bin" / "pt730-plan"
LAYOUT = ROOT / "bin" / "pt730-layout"
RENDER = ROOT / "bin" / "pt730-render"
SAFETY = ROOT / "bin" / "pt730-safety"


class PlanCliTest(unittest.TestCase):
    def run_plan(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(PLAN), *args],
            cwd=ROOT.parent,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
        )

    def test_schema_describes_plan_editor(self) -> None:
        result = self.run_plan("schema", "--compact")
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["kind"], "pt730-plan-schema")
        self.assertIn("set-metadata", data["commands"])
        self.assertIn("add-device", data["commands"])
        self.assertIn("remove-device", data["commands"])
        self.assertIn("add-module", data["commands"])
        self.assertIn("remove-module", data["commands"])
        self.assertIn("add-link", data["commands"])
        self.assertIn("remove-link", data["commands"])
        for command in (
            "add-ap-config",
            "remove-ap-config",
            "add-annotation",
            "remove-annotation",
            "add-pc-config",
            "remove-pc-config",
            "add-ipv6-config",
            "remove-ipv6-config",
            "add-vlan-config",
            "remove-vlan-config",
            "add-dhcp-pool",
            "remove-dhcp-pool",
            "add-server-config",
            "remove-server-config",
            "add-ios-config",
            "remove-ios-config",
            "add-security-policy",
            "remove-security-policy",
        ):
            self.assertIn(command, data["commands"])

    def test_plan_editor_builds_renderable_topology(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "agent-lan.json"
            steps = [
                ("new", "--name", "Agent LAN", "--output", str(path)),
                ("add-device", str(path), "--name", "R1", "--category", "router", "--model", "2911", "--output", str(path)),
                ("add-device", str(path), "--name", "SW1", "--category", "switch", "--model", "2960-24TT", "--output", str(path)),
                ("add-device", str(path), "--name", "PC1", "--category", "pc", "--model", "PC-PT", "--output", str(path)),
                ("add-link", str(path), "--a", "R1", "--pa", "GigabitEthernet0/0", "--b", "SW1", "--pb", "FastEthernet0/1", "--output", str(path)),
                ("add-link", str(path), "--a", "SW1", "--pa", "FastEthernet0/2", "--b", "PC1", "--pb", "FastEthernet0", "--output", str(path)),
                ("add-pc-config", str(path), "--name", "PC1", "--ip", "192.168.10.10", "--mask", "255.255.255.0", "--gateway", "192.168.10.1", "--output", str(path)),
                ("add-annotation", str(path), "--id", "gateway-note", "--target", "R1", "--title", "Gateway", "--text", "Default gateway validation.", "--output", str(path)),
            ]
            for step in steps:
                result = self.run_plan(*step)
                self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(len(data["devices"]), 3)
            self.assertEqual(len(data["links"]), 2)
            self.assertEqual(data["pc_configs"][0]["ip"], "192.168.10.10")
            self.assertEqual(data["annotations"][0]["id"], "gateway-note")

            layout_path = Path(tmpdir) / "agent-lan-layout.json"
            layout = subprocess.run(
                [str(LAYOUT), str(path), "--style", "lan", "--output", str(layout_path)],
                cwd=ROOT.parent,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
                check=False,
            )
            self.assertEqual(layout.returncode, 0, layout.stderr)
            safety = subprocess.run(
                [str(SAFETY), "plan", str(layout_path)],
                cwd=ROOT.parent,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
                check=False,
            )
            self.assertEqual(safety.returncode, 0, safety.stdout + safety.stderr)
            render = subprocess.run(
                [str(RENDER), "summary", str(layout_path)],
                cwd=ROOT.parent,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
                check=False,
            )
            self.assertEqual(render.returncode, 0, render.stderr)
            summary = json.loads(render.stdout)
            self.assertEqual(summary["counts"]["devices"], 3)
            self.assertEqual(summary["counts"]["annotations"], 1)

    def test_plan_editor_adds_modules_and_wireless_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "wan-wifi.json"
            steps = [
                ("new", "--name", "WAN WiFi", "--output", str(path)),
                ("add-device", str(path), "--name", "R1", "--category", "router", "--model", "2911", "--output", str(path)),
                ("add-device", str(path), "--name", "R2", "--category", "router", "--model", "2911", "--output", str(path)),
                ("add-device", str(path), "--name", "AP1", "--category", "accesspoint", "--model", "AccessPoint-PT", "--ssid", "CLASSROOM", "--output", str(path)),
                ("add-device", str(path), "--name", "LAP1", "--category", "laptop", "--model", "Laptop-PT", "--ssid", "CLASSROOM", "--output", str(path)),
                ("add-module", str(path), "--device", "R1", "--slot", "0/0", "--model", "HWIC-2T", "--output", str(path)),
                ("add-module", str(path), "--device", "R2", "--slot", "0/0", "--model", "HWIC-2T", "--output", str(path)),
                ("add-link", str(path), "--a", "R1", "--pa", "Serial0/0/0", "--b", "R2", "--pb", "Serial0/0/0", "--cable", "serial", "--note", "WAN serial", "--output", str(path)),
                ("add-link", str(path), "--a", "AP1", "--pa", "Port 0", "--b", "LAP1", "--pb", "FastEthernet0", "--cable", "wireless", "--note", "SSID CLASSROOM", "--output", str(path)),
                ("add-ap-config", str(path), "--name", "AP1", "--ssid", "CLASSROOM", "--channel", "6", "--auth", "wpa2-psk", "--password", "packet123", "--note", "offline metadata", "--output", str(path)),
            ]
            for step in steps:
                result = self.run_plan(*step)
                self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual([module["model"] for module in data["modules"]], ["HWIC-2T", "HWIC-2T"])
            self.assertEqual(data["devices"][2]["ssid"], "CLASSROOM")
            self.assertEqual(data["ap_configs"][0]["auth"], "wpa2-psk")

            safety = subprocess.run(
                [str(SAFETY), "plan", str(path)],
                cwd=ROOT.parent,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
                check=False,
            )
            self.assertEqual(safety.returncode, 0, safety.stdout + safety.stderr)
            render = subprocess.run(
                [str(RENDER), "summary", str(path)],
                cwd=ROOT.parent,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
                check=False,
            )
            self.assertEqual(render.returncode, 0, render.stderr)
            summary = json.loads(render.stdout)
            self.assertEqual(summary["counts"]["modules"], 2)
            self.assertEqual(summary["counts"]["ap_configs"], 1)
            self.assertEqual(summary["wireless"]["ssids"], ["CLASSROOM"])

    def test_plan_editor_removes_items_and_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "editable.json"
            steps = [
                ("new", "--name", "Editable", "--output", str(path)),
                ("set-metadata", str(path), "--key", "owner", "--value", "agent", "--output", str(path)),
                ("set-metadata", str(path), "--key", "tags", "--json", '["draft","wan"]', "--output", str(path)),
                ("add-device", str(path), "--name", "R1", "--category", "router", "--model", "2911", "--output", str(path)),
                ("add-device", str(path), "--name", "SW1", "--category", "switch", "--model", "2960-24TT", "--output", str(path)),
                ("add-device", str(path), "--name", "PC1", "--category", "pc", "--model", "PC-PT", "--output", str(path)),
                ("add-module", str(path), "--device", "R1", "--slot", "0/0", "--model", "HWIC-2T", "--output", str(path)),
                ("add-link", str(path), "--a", "R1", "--pa", "GigabitEthernet0/0", "--b", "SW1", "--pb", "FastEthernet0/1", "--output", str(path)),
                ("add-link", str(path), "--a", "SW1", "--pa", "FastEthernet0/2", "--b", "PC1", "--pb", "FastEthernet0", "--output", str(path)),
                ("add-pc-config", str(path), "--name", "PC1", "--ip", "192.168.10.10", "--mask", "255.255.255.0", "--gateway", "192.168.10.1", "--output", str(path)),
                ("add-annotation", str(path), "--target", "PC1", "--title", "Client", "--text", "temporary client", "--output", str(path)),
            ]
            for step in steps:
                result = self.run_plan(*step)
                self.assertEqual(result.returncode, 0, result.stderr)
            result = self.run_plan("remove-device", str(path), "--name", "PC1", "--output", str(path))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("use --cascade", result.stderr)
            self.assertIn("PC1", [device["name"] for device in json.loads(path.read_text(encoding="utf-8"))["devices"]])

            result = self.run_plan("remove-link", str(path), "--a", "PC1", "--b", "SW1", "--pa", "WrongPort", "--output", str(path))
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(len(json.loads(path.read_text(encoding="utf-8"))["links"]), 2)
            result = self.run_plan("remove-link", str(path), "--a", "PC1", "--b", "SW1", "--pa", "FastEthernet0", "--output", str(path))
            self.assertEqual(result.returncode, 0, result.stderr)

            remove_steps = [
                ("remove-link", str(path), "--a", "R1", "--b", "SW1", "--pa", "GigabitEthernet0/0", "--pb", "FastEthernet0/1", "--output", str(path)),
                ("remove-module", str(path), "--device", "R1", "--slot", "0/0", "--output", str(path)),
                ("remove-device", str(path), "--name", "PC1", "--cascade", "--output", str(path)),
                ("set-metadata", str(path), "--key", "owner", "--remove", "--output", str(path)),
            ]
            for step in remove_steps:
                result = self.run_plan(*step)
                self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertNotIn("owner", data["metadata"])
            self.assertEqual(data["metadata"]["tags"], ["draft", "wan"])
            self.assertEqual([device["name"] for device in data["devices"]], ["R1", "SW1"])
            self.assertEqual(data["modules"], [])
            self.assertEqual(data["links"], [])
            self.assertEqual(data["pc_configs"], [])
            self.assertEqual(data["annotations"], [])

    def test_plan_editor_adds_config_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "configured-lan.json"
            dns_json = json.dumps({"enabled": True, "records": [{"name": "www.lab.local", "ip": "192.168.10.10"}]})
            ftp_json = json.dumps({"enabled": True, "accounts": [{"username": "lab", "password": "packet", "permissions": "RWDNL"}]})
            dhcp_json = json.dumps(
                {
                    "enabled": True,
                    "network": "192.168.10.0",
                    "mask": "255.255.255.0",
                    "start": "192.168.10.100",
                    "end": "192.168.10.120",
                    "gateway": "192.168.10.1",
                    "dns": "192.168.10.10",
                    "max_users": 21,
                }
            )
            steps = [
                ("new", "--name", "Configured LAN", "--output", str(path)),
                ("add-device", str(path), "--name", "R1", "--category", "router", "--model", "2911", "--output", str(path)),
                ("add-device", str(path), "--name", "SW1", "--category", "switch", "--model", "2960-24TT", "--output", str(path)),
                ("add-device", str(path), "--name", "SRV1", "--category", "server", "--model", "Server-PT", "--output", str(path)),
                ("add-device", str(path), "--name", "PC1", "--category", "pc", "--model", "PC-PT", "--output", str(path)),
                ("add-device", str(path), "--name", "AP1", "--category", "accesspoint", "--model", "AccessPoint-PT", "--output", str(path)),
                ("add-link", str(path), "--a", "R1", "--pa", "GigabitEthernet0/0", "--b", "SW1", "--pb", "FastEthernet0/1", "--output", str(path)),
                ("add-link", str(path), "--a", "SW1", "--pa", "FastEthernet0/2", "--b", "PC1", "--pb", "FastEthernet0", "--vlan", "10", "--output", str(path)),
                ("add-link", str(path), "--a", "SW1", "--pa", "FastEthernet0/3", "--b", "SRV1", "--pb", "FastEthernet0", "--vlan", "10", "--output", str(path)),
                ("add-ap-config", str(path), "--name", "AP1", "--ssid", "CLASSROOM", "--channel", "6", "--output", str(path)),
                ("add-annotation", str(path), "--id", "service-note", "--target", "SRV1", "--title", "Services", "--text", "HTTP/DNS/FTP enabled.", "--output", str(path)),
                ("add-pc-config", str(path), "--name", "PC1", "--ip", "192.168.10.20", "--mask", "255.255.255.0", "--gateway", "192.168.10.1", "--dns", "192.168.10.10", "--output", str(path)),
                ("add-pc-config", str(path), "--name", "SRV1", "--ip", "192.168.10.10", "--mask", "255.255.255.0", "--gateway", "192.168.10.1", "--dns", "192.168.10.10", "--output", str(path)),
                ("add-ipv6-config", str(path), "--name", "PC1", "--ipv6", "2001:db8:10::20", "--prefix", "64", "--gateway", "2001:db8:10::1", "--dns", "2001:db8:10::10", "--output", str(path)),
                ("add-vlan-config", str(path), "--id", "10", "--name", "USERS", "--network", "192.168.10.0/24", "--gateway", "192.168.10.1", "--description", "User and service VLAN", "--output", str(path)),
                ("add-dhcp-pool", str(path), "--device", "R1", "--name", "VLAN10", "--vlan", "10", "--network", "192.168.10.0", "--mask", "255.255.255.0", "--start", "192.168.10.100", "--end", "192.168.10.120", "--gateway", "192.168.10.1", "--dns", "192.168.10.10", "--output", str(path)),
                ("add-server-config", str(path), "--name", "SRV1", "--http", "--dns-json", dns_json, "--ftp-json", ftp_json, "--dhcp-json", dhcp_json, "--output", str(path)),
                (
                    "add-ios-config",
                    str(path),
                    "--device",
                    "R1",
                    "--init-dialog",
                    "--command",
                    "enable",
                    "--command",
                    "configure terminal",
                    "--command",
                    "interface GigabitEthernet0/0",
                    "--command",
                    "ip address 192.168.10.1 255.255.255.0",
                    "--command",
                    "no shutdown",
                    "--command",
                    "end",
                    "--output",
                    str(path),
                ),
                ("add-security-policy", str(path), "--device", "R1", "--type", "inside_acl", "--interface", "GigabitEthernet0/0", "--acl", "10", "--direction", "in", "--summary", "Permit campus users.", "--output", str(path)),
            ]
            for step in steps:
                result = self.run_plan(*step)
                self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["ap_configs"][0]["ssid"], "CLASSROOM")
            self.assertEqual(data["annotations"][0]["id"], "service-note")
            self.assertEqual(data["ipv6_configs"][0]["ipv6"], "2001:db8:10::20")
            self.assertEqual(data["vlan_configs"][0]["id"], 10)
            self.assertEqual(data["dhcp_pools"][0]["name"], "VLAN10")
            self.assertEqual(data["server_configs"][0]["dns"]["records"][0]["name"], "www.lab.local")
            self.assertEqual(data["ios_configs"][0]["commands"][2], "interface GigabitEthernet0/0")
            self.assertEqual(data["security_policies"][0]["acl"], "10")

            safety = subprocess.run(
                [str(SAFETY), "plan", str(path)],
                cwd=ROOT.parent,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
                check=False,
            )
            self.assertEqual(safety.returncode, 0, safety.stdout + safety.stderr)
            render = subprocess.run(
                [str(RENDER), "summary", str(path)],
                cwd=ROOT.parent,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
                check=False,
            )
            self.assertEqual(render.returncode, 0, render.stderr)
            summary = json.loads(render.stdout)
            self.assertEqual(summary["counts"]["ap_configs"], 1)
            self.assertEqual(summary["counts"]["annotations"], 1)
            self.assertEqual(summary["counts"]["ipv6_configs"], 1)
            self.assertEqual(summary["counts"]["vlan_configs"], 1)
            self.assertEqual(summary["counts"]["dhcp_pools"], 1)
            self.assertEqual(summary["counts"]["server_configs"], 1)
            self.assertEqual(summary["counts"]["ios_configs"], 1)
            self.assertEqual(summary["counts"]["security_policies"], 1)

            remove_steps = [
                ("remove-ap-config", str(path), "--name", "AP1", "--output", str(path)),
                ("remove-annotation", str(path), "--id", "service-note", "--output", str(path)),
                ("remove-pc-config", str(path), "--name", "PC1", "--output", str(path)),
                ("remove-pc-config", str(path), "--name", "SRV1", "--output", str(path)),
                ("remove-ipv6-config", str(path), "--name", "PC1", "--output", str(path)),
                ("remove-vlan-config", str(path), "--id", "10", "--output", str(path)),
                ("remove-dhcp-pool", str(path), "--device", "R1", "--name", "VLAN10", "--output", str(path)),
                ("remove-server-config", str(path), "--name", "SRV1", "--output", str(path)),
                ("remove-ios-config", str(path), "--device", "R1", "--output", str(path)),
                ("remove-security-policy", str(path), "--device", "R1", "--type", "inside_acl", "--interface", "GigabitEthernet0/0", "--output", str(path)),
            ]
            for step in remove_steps:
                result = self.run_plan(*step)
                self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(path.read_text(encoding="utf-8"))
            for key in ("ap_configs", "annotations", "pc_configs", "ipv6_configs", "vlan_configs", "dhcp_pools", "server_configs", "ios_configs", "security_policies"):
                self.assertEqual(data[key], [], key)

    def test_add_link_rejects_missing_endpoint_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "bad.json"
            self.assertEqual(self.run_plan("new", "--output", str(path)).returncode, 0)
            result = self.run_plan("add-link", str(path), "--a", "R1", "--b", "SW1")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("not found", result.stderr)

    def test_add_module_rejects_missing_device_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "bad-module.json"
            self.assertEqual(self.run_plan("new", "--output", str(path)).returncode, 0)
            result = self.run_plan("add-module", str(path), "--device", "R1", "--slot", "0/0", "--model", "HWIC-2T")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("target device not found", result.stderr)


if __name__ == "__main__":
    unittest.main()
