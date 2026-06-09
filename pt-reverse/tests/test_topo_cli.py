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

    def test_apply_dry_run_accepts_known_ios_subinterface_before_live_bridge(self) -> None:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as f:
            json.dump(
                {
                    "devices": [{"name": "R1", "category": "router", "model": "2911"}],
                    "ios_configs": [
                        {
                            "device": "R1",
                            "commands": [
                                "interface GigabitEthernet0/0.10",
                                "encapsulation dot1Q 10",
                                "ip address 192.168.10.1 255.255.255.0",
                                "no shutdown",
                            ],
                        }
                    ],
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
        self.assertEqual(result.returncode, 0, result.stderr)

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
                        "output_tail": "\nshow running-config\nipv6 unicast-routing\nspanning-tree mode rapid-pvst\nspanning-tree vlan 10 root primary\nspanning-tree vlan 20 priority 4096\nspanning-tree portfast default\nspanning-tree bpduguard default\ninterface GigabitEthernet0/0\n ip address 10.0.0.1 255.255.255.0\n ipv6 address 2001:db8:10::1/64\n ipv6 ospf 10 area 0\n ipv6 rip CAMPUS6 enable\n ip helper-address 172.16.1.10\n standby version 2\n standby 10 ip 10.0.0.254\n standby 10 priority 110\n standby 10 preempt\n standby 10 timers 1 3\n standby 10 track GigabitEthernet0/1 20\n ip nat inside\n ip access-group 10 in\n channel-group 1 mode active\n no shutdown\ninterface Port-channel1\n switchport mode trunk\n switchport trunk allowed vlan 10,20\n no shutdown\nip dhcp excluded-address 10.0.0.1 10.0.0.20\nip dhcp pool VLAN10\n network 10.0.0.0 255.255.255.0\n default-router 10.0.0.254\n dns-server 172.16.1.10 172.16.1.11\n domain-name campus.local\nntp source GigabitEthernet0/0\nntp server 172.16.1.20 prefer\nlogging source-interface GigabitEthernet0/0\nlogging trap informational\nlogging host 172.16.1.30\nservice timestamps log datetime msec\nsnmp-server community campusRO RO 10\nsnmp-server location Core Room\nrouter rip\n version 2\n network 10.0.0.0\nrouter eigrp 100\n no auto-summary\n passive-interface GigabitEthernet0/0\n network 10.0.0.0 0.0.0.255\nrouter ospf 1\n router-id 10.255.0.1\n passive-interface GigabitEthernet0/0\n network 10.0.0.0 0.0.0.255 area 0\nrouter bgp 65001\n bgp log-neighbor-changes\n bgp router-id 10.255.255.1\n neighbor 203.0.113.2 remote-as 65000\n neighbor 203.0.113.2 description ISP\n network 172.16.1.0 mask 255.255.255.192\n redistribute connected\nipv6 router ospf 10\n router-id 10.255.0.6\n passive-interface GigabitEthernet0/1\nipv6 router rip CAMPUS6\n redistribute connected\nip route 0.0.0.0 0.0.0.0 10.0.0.254\nipv6 route 2001:db8:ffff::/64 2001:db8:10::fe 5\naccess-list 10 permit 10.0.0.0 0.0.0.255\nip nat inside source list 10 interface GigabitEthernet0/1 overload\n",
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
        self.assertEqual(data["config_summaries"][0]["routing"]["eigrp"]["asn"], "100")
        self.assertEqual(data["config_summaries"][0]["routing"]["eigrp"]["passive_interfaces"], ["GigabitEthernet0/0"])
        self.assertEqual(data["config_summaries"][0]["routing"]["eigrp"]["networks"][0]["wildcard"], "0.0.0.255")
        self.assertEqual(data["config_summaries"][0]["routing"]["ospf"]["process_id"], "1")
        self.assertEqual(data["config_summaries"][0]["routing"]["ospf"]["router_id"], "10.255.0.1")
        self.assertEqual(data["config_summaries"][0]["routing"]["ospf"]["passive_interfaces"], ["GigabitEthernet0/0"])
        self.assertEqual(data["config_summaries"][0]["routing"]["ospf"]["networks"][0]["wildcard"], "0.0.0.255")
        self.assertEqual(data["config_summaries"][0]["routing"]["bgp"]["asn"], "65001")
        self.assertEqual(data["config_summaries"][0]["routing"]["bgp"]["router_id"], "10.255.255.1")
        self.assertEqual(data["config_summaries"][0]["routing"]["bgp"]["neighbors"][0]["remote_as"], "65000")
        self.assertEqual(data["config_summaries"][0]["routing"]["bgp"]["networks"][0]["mask"], "255.255.255.192")
        self.assertEqual(data["config_summaries"][0]["routing"]["bgp"]["redistribute"], ["connected"])
        self.assertEqual(data["config_summaries"][0]["routing"]["static_routes"][0]["next_hop"], "10.0.0.254")
        self.assertTrue(data["config_summaries"][0]["routing"]["ipv6_unicast_routing"])
        self.assertEqual(data["config_summaries"][0]["routing"]["ospfv3"]["process_id"], "10")
        self.assertEqual(data["config_summaries"][0]["routing"]["ospfv3"]["router_id"], "10.255.0.6")
        self.assertEqual(data["config_summaries"][0]["routing"]["ospfv3"]["passive_interfaces"], ["GigabitEthernet0/1"])
        self.assertEqual(data["config_summaries"][0]["routing"]["ripng"]["process_name"], "CAMPUS6")
        self.assertEqual(data["config_summaries"][0]["routing"]["ripng"]["redistribute"], ["connected"])
        self.assertEqual(data["config_summaries"][0]["routing"]["ipv6_static_routes"][0]["next_hop"], "2001:db8:10::fe")
        self.assertEqual(data["config_summaries"][0]["routing"]["ipv6_static_routes"][0]["distance"], "5")
        self.assertEqual(data["config_summaries"][0]["spanning_tree"]["mode"], "rapid-pvst")
        self.assertEqual(data["config_summaries"][0]["spanning_tree"]["roots"][0]["role"], "primary")
        self.assertEqual(data["config_summaries"][0]["spanning_tree"]["priorities"][0]["priority"], "4096")
        self.assertTrue(data["config_summaries"][0]["spanning_tree"]["portfast_default"])
        self.assertTrue(data["config_summaries"][0]["spanning_tree"]["bpduguard_default"])
        self.assertEqual(data["config_summaries"][0]["interfaces"]["GigabitEthernet0/0"]["channel_group"], "1")
        self.assertEqual(data["config_summaries"][0]["interfaces"]["GigabitEthernet0/0"]["ipv6_addresses"], ["2001:db8:10::1/64"])
        self.assertEqual(data["config_summaries"][0]["interfaces"]["GigabitEthernet0/0"]["ospfv3"][0]["area"], "0")
        self.assertEqual(data["config_summaries"][0]["interfaces"]["GigabitEthernet0/0"]["ripng"][0]["process_name"], "CAMPUS6")
        self.assertEqual(data["config_summaries"][0]["interfaces"]["GigabitEthernet0/0"]["helper_addresses"], ["172.16.1.10"])
        self.assertEqual(data["config_summaries"][0]["interfaces"]["GigabitEthernet0/0"]["standby_version"], "2")
        self.assertEqual(data["config_summaries"][0]["interfaces"]["GigabitEthernet0/0"]["hsrp"]["10"]["ip"], "10.0.0.254")
        self.assertEqual(data["config_summaries"][0]["interfaces"]["GigabitEthernet0/0"]["hsrp"]["10"]["priority"], "110")
        self.assertTrue(data["config_summaries"][0]["interfaces"]["GigabitEthernet0/0"]["hsrp"]["10"]["preempt"])
        self.assertEqual(data["config_summaries"][0]["interfaces"]["GigabitEthernet0/0"]["hsrp"]["10"]["timers"]["hold"], "3")
        self.assertEqual(data["config_summaries"][0]["interfaces"]["GigabitEthernet0/0"]["hsrp"]["10"]["track"][0]["decrement"], "20")
        self.assertEqual(data["config_summaries"][0]["interfaces"]["Port-channel1"]["trunk_allowed_vlans"], "10,20")
        self.assertEqual(data["config_summaries"][0]["dhcp"]["excluded_addresses"][0]["end"], "10.0.0.20")
        self.assertEqual(data["config_summaries"][0]["dhcp"]["pools"]["VLAN10"]["default_router"], ["10.0.0.254"])
        self.assertEqual(data["config_summaries"][0]["dhcp"]["pools"]["VLAN10"]["dns_server"], ["172.16.1.10", "172.16.1.11"])
        self.assertEqual(data["config_summaries"][0]["ntp"]["source"], "GigabitEthernet0/0")
        self.assertEqual(data["config_summaries"][0]["ntp"]["servers"][0]["address"], "172.16.1.20")
        self.assertEqual(data["config_summaries"][0]["logging"]["hosts"][0]["address"], "172.16.1.30")
        self.assertEqual(data["config_summaries"][0]["logging"]["trap"], "informational")
        self.assertTrue(data["config_summaries"][0]["logging"]["timestamps_log"])
        self.assertEqual(data["config_summaries"][0]["snmp"]["communities"][0]["name"], "campusRO")
        self.assertEqual(data["config_summaries"][0]["snmp"]["location"], "Core Room")
        self.assertIn("10", data["config_summaries"][0]["acl_numbers"])
        self.assertEqual(data["config_summaries"][0]["interfaces"]["GigabitEthernet0/0"]["acl_in"], "10")
        self.assertEqual(data["config_summaries"][0]["acl_applications"][0]["direction"], "in")
        self.assertTrue(data["config_summaries"][0]["nat"]["overload"])

    def test_export_from_saved_query_writes_raw_and_summary_files(self) -> None:
        query = {
            "devices": [
                {
                    "name": "R1",
                    "model": "2911",
                    "type": "0",
                    "ports": [{"name": "GigabitEthernet0/0", "linked": True, "ip": "10.0.0.1", "mask": "255.255.255.0"}],
                    "command_line": {"prompt": "R1#"},
                }
            ],
            "links": [],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            query_path = Path(tmpdir) / "query.json"
            raw_path = Path(tmpdir) / "raw.json"
            summary_path = Path(tmpdir) / "summary.json"
            query_path.write_text(json.dumps(query), encoding="utf-8")
            result = subprocess.run(
                [str(TOPO), "export", "--from-query", str(query_path), "--raw-out", str(raw_path), "--summary-out", str(summary_path)],
                cwd=ROOT.parent,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            manifest = json.loads(result.stdout)
            self.assertEqual(manifest["raw_out"], str(raw_path))
            self.assertEqual(manifest["summary_out"], str(summary_path))
            self.assertEqual(json.loads(raw_path.read_text(encoding="utf-8"))["devices"][0]["name"], "R1")
            self.assertEqual(json.loads(summary_path.read_text(encoding="utf-8"))["counts"]["devices"], 1)

    def test_export_from_saved_query_can_write_markdown_summary(self) -> None:
        query = {
            "devices": [
                {
                    "name": "R1",
                    "model": "2911",
                    "type": "0",
                    "ports": [{"name": "GigabitEthernet0/0", "linked": True, "ip": "10.0.0.1", "mask": "255.255.255.0"}],
                    "command_line": {
                        "prompt": "R1#",
                        "output_tail": "interface GigabitEthernet0/0\n ip address 10.0.0.1 255.255.255.0\n ip access-group 10 in\n",
                    },
                }
            ],
            "links": [],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            query_path = Path(tmpdir) / "query.json"
            raw_path = Path(tmpdir) / "raw.json"
            summary_path = Path(tmpdir) / "summary.json"
            markdown_path = Path(tmpdir) / "summary.md"
            query_path.write_text(json.dumps(query), encoding="utf-8")
            result = subprocess.run(
                [
                    str(TOPO),
                    "export",
                    "--from-query",
                    str(query_path),
                    "--raw-out",
                    str(raw_path),
                    "--summary-out",
                    str(summary_path),
                    "--markdown-out",
                    str(markdown_path),
                ],
                cwd=ROOT.parent,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            markdown = markdown_path.read_text(encoding="utf-8")
            self.assertIn("# Packet Tracer Canvas Summary", markdown)
            self.assertIn("R1", markdown)
            self.assertIn("10.0.0.1", markdown)
            self.assertIn("GigabitEthernet0/0 -> ACL 10 in", markdown)

    def test_export_markdown_reports_unreadable_links(self) -> None:
        query = {
            "devices": [{"name": "AP1", "model": "AccessPoint-PT", "type": "7"}],
            "links": [{"index": 0, "status": "unreadable", "error": "link object does not expose getPort1/getPort2"}],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            query_path = Path(tmpdir) / "query.json"
            raw_path = Path(tmpdir) / "raw.json"
            summary_path = Path(tmpdir) / "summary.json"
            markdown_path = Path(tmpdir) / "summary.md"
            query_path.write_text(json.dumps(query), encoding="utf-8")
            result = subprocess.run(
                [
                    str(TOPO),
                    "export",
                    "--from-query",
                    str(query_path),
                    "--raw-out",
                    str(raw_path),
                    "--summary-out",
                    str(summary_path),
                    "--markdown-out",
                    str(markdown_path),
                ],
                cwd=ROOT.parent,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            markdown = markdown_path.read_text(encoding="utf-8")
            self.assertIn("link[0]: unreadable", markdown)
            self.assertIn("getPort1/getPort2", markdown)


if __name__ == "__main__":
    unittest.main()
