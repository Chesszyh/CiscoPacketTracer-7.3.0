#!/usr/bin/env python3
"""Tests for high-level IOS template rendering."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "bin" / "pt730-ios-template"


class IosTemplateCliTest(unittest.TestCase):
    def run_template(self, spec: dict, *args: str) -> subprocess.CompletedProcess[str]:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as f:
            json.dump(spec, f)
            path = f.name
        try:
            return subprocess.run(
                [str(TEMPLATE), "render", path, *args],
                cwd=ROOT.parent,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
                check=False,
            )
        finally:
            Path(path).unlink(missing_ok=True)

    def test_render_vlan_trunk_rip_static_route_acl_nat(self) -> None:
        result = self.run_template(
            {
                "device": "R1",
                "hostname": "R1",
                "ip_routing": True,
                "vlans": [{"id": 10, "name": "SERVER"}],
                "interfaces": [
                    {"name": "GigabitEthernet0/0", "ip": "10.0.0.1", "mask": "255.255.255.0", "description": "LAN", "acl_in": 10},
                    {"name": "GigabitEthernet0/3", "mode": "routed", "ip": "10.10.12.1", "mask": "255.255.255.252"},
                    {"name": "GigabitEthernet0/1", "mode": "trunk", "allowed_vlans": [10, 20]},
                    {"name": "Vlan10", "ip": "192.168.10.1", "mask": "255.255.255.0"},
                ],
                "spanning_tree": {
                    "mode": "rapid-pvst",
                    "root_primary": [10, 20],
                    "vlan_priorities": [{"vlan": 30, "priority": 4096}],
                    "portfast_default": True,
                    "bpduguard_default": True,
                },
                "etherchannels": [
                    {
                        "group": 1,
                        "mode": "active",
                        "interfaces": ["GigabitEthernet0/1", "GigabitEthernet0/2"],
                        "port_channel": {"mode": "trunk", "allowed_vlans": [10, 20], "description": "UPLINK_BUNDLE"},
                    }
                ],
                "rip": {"version": 2, "networks": ["10.0.0.0", "192.168.10.0"], "no_auto_summary": True},
                "ospf": {
                    "process_id": 1,
                    "router_id": "10.255.0.1",
                    "passive_interfaces": ["Vlan10"],
                    "networks": [{"network": "192.168.10.0", "wildcard": "0.0.0.255", "area": 0}],
                },
                "static_routes": [{"destination": "0.0.0.0", "mask": "0.0.0.0", "next_hop": "10.0.0.254"}],
                "acls": [
                    {
                        "type": "standard",
                        "number": 10,
                        "rules": [{"action": "permit", "source": "192.168.10.0", "wildcard": "0.0.0.255"}],
                    }
                ],
                "nat": {
                    "inside_interfaces": ["GigabitEthernet0/0"],
                    "outside_interfaces": ["GigabitEthernet0/2"],
                    "overloads": [{"acl": 10, "interface": "GigabitEthernet0/2"}],
                },
            }
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("hostname R1", result.stdout)
        self.assertIn("ip routing", result.stdout)
        self.assertIn("vlan 10", result.stdout)
        self.assertIn("no switchport", result.stdout)
        self.assertIn("switchport trunk allowed vlan 10,20", result.stdout)
        self.assertIn("spanning-tree mode rapid-pvst", result.stdout)
        self.assertIn("spanning-tree vlan 10,20 root primary", result.stdout)
        self.assertIn("spanning-tree vlan 30 priority 4096", result.stdout)
        self.assertIn("spanning-tree portfast default", result.stdout)
        self.assertIn("spanning-tree bpduguard default", result.stdout)
        self.assertIn("channel-group 1 mode active", result.stdout)
        self.assertIn("interface Port-channel1", result.stdout)
        self.assertIn("description UPLINK_BUNDLE", result.stdout)
        self.assertIn("router rip", result.stdout)
        self.assertIn("router ospf 1", result.stdout)
        self.assertIn("router-id 10.255.0.1", result.stdout)
        self.assertIn("passive-interface Vlan10", result.stdout)
        self.assertIn("network 192.168.10.0 0.0.0.255 area 0", result.stdout)
        self.assertIn("ip route 0.0.0.0 0.0.0.0 10.0.0.254", result.stdout)
        self.assertIn("access-list 10 permit 192.168.10.0 0.0.0.255", result.stdout)
        self.assertIn("ip access-group 10 in", result.stdout)
        self.assertIn("ip nat inside source list 10 interface GigabitEthernet0/2 overload", result.stdout)

    def test_render_fhrp_dhcp_relay_and_infrastructure_services(self) -> None:
        result = self.run_template(
            {
                "device": "CORE-A",
                "hostname": "CORE-A",
                "interfaces": [
                    {
                        "name": "Vlan20",
                        "ip": "192.168.20.2",
                        "mask": "255.255.255.0",
                        "helper_addresses": ["172.16.1.10"],
                        "hsrp": {
                            "group": 20,
                            "version": 2,
                            "ip": "192.168.20.1",
                            "priority": 110,
                            "preempt": True,
                            "timers": {"hello": 1, "hold": 3},
                            "track": [{"interface": "GigabitEthernet0/2", "decrement": 20}],
                        },
                    }
                ],
                "dhcp": {
                    "excluded_addresses": [{"start": "192.168.20.1", "end": "192.168.20.20"}],
                    "pools": [
                        {
                            "name": "VLAN20",
                            "network": "192.168.20.0",
                            "mask": "255.255.255.0",
                            "default_router": "192.168.20.1",
                            "dns_server": ["172.16.1.10", "172.16.1.11"],
                            "domain_name": "campus.local",
                        }
                    ],
                },
                "ntp": {"servers": [{"address": "172.16.1.20", "prefer": True}], "source_interface": "Vlan20"},
                "logging": {"hosts": ["172.16.1.30"], "trap": "informational", "source_interface": "Vlan20", "timestamps_log": True},
                "snmp": {"communities": [{"name": "campusRO", "mode": "RO", "acl": 10}], "location": "Core Room"},
            }
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ip helper-address 172.16.1.10", result.stdout)
        self.assertIn("standby version 2", result.stdout)
        self.assertIn("standby 20 ip 192.168.20.1", result.stdout)
        self.assertIn("standby 20 priority 110", result.stdout)
        self.assertIn("standby 20 preempt", result.stdout)
        self.assertIn("standby 20 timers 1 3", result.stdout)
        self.assertIn("standby 20 track GigabitEthernet0/2 20", result.stdout)
        self.assertIn("ip dhcp excluded-address 192.168.20.1 192.168.20.20", result.stdout)
        self.assertIn("ip dhcp pool VLAN20", result.stdout)
        self.assertIn("default-router 192.168.20.1", result.stdout)
        self.assertIn("dns-server 172.16.1.10 172.16.1.11", result.stdout)
        self.assertIn("ntp source Vlan20", result.stdout)
        self.assertIn("ntp server 172.16.1.20 prefer", result.stdout)
        self.assertIn("service timestamps log datetime msec", result.stdout)
        self.assertIn("logging source-interface Vlan20", result.stdout)
        self.assertIn("logging trap informational", result.stdout)
        self.assertIn("logging host 172.16.1.30", result.stdout)
        self.assertIn("snmp-server community campusRO RO 10", result.stdout)
        self.assertIn("snmp-server location Core Room", result.stdout)

    def test_render_as_topology_ios_config_json(self) -> None:
        result = self.run_template({"device": "R1", "hostname": "R1"}, "--topology-json")
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["ios_configs"][0]["device"], "R1")
        self.assertIn("hostname R1", data["ios_configs"][0]["commands"])

    def test_render_multiple_device_templates_as_topology_json(self) -> None:
        result = self.run_template(
            {
                "devices": [
                    {"device": "R1", "hostname": "R1", "rip": {"version": 2, "networks": ["10.0.0.0"]}},
                    {"device": "SW1", "hostname": "SW1", "vlans": [{"id": 10}], "interfaces": [{"name": "FastEthernet0/1", "mode": "access", "vlan": 10}]},
                ]
            },
            "--topology-json",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual([item["device"] for item in data["ios_configs"]], ["R1", "SW1"])
        self.assertIn("router rip", data["ios_configs"][0]["commands"])
        self.assertIn("switchport access vlan 10", [command.strip() for command in data["ios_configs"][1]["commands"]])

    def test_rejects_missing_acl_number(self) -> None:
        result = self.run_template({"device": "R1", "acls": [{"rules": [{"action": "permit", "source": "any"}]}]})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("acl number", result.stderr)

    def test_schema_describes_supported_json_surface(self) -> None:
        result = subprocess.run(
            [str(TEMPLATE), "schema"],
            cwd=ROOT.parent,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        fields = data["fields"]
        self.assertIn("vlans", fields)
        self.assertIn("interfaces[].mode=trunk", fields)
        self.assertIn("interfaces[].acl_in", fields)
        self.assertIn("interfaces[].mode=routed", fields)
        self.assertIn("ip_routing", fields)
        self.assertIn("spanning_tree", fields)
        self.assertIn("etherchannels", fields)
        self.assertIn("interfaces[].helper_addresses", fields)
        self.assertIn("interfaces[].hsrp", fields)
        self.assertIn("rip.networks", fields)
        self.assertIn("ospf.networks", fields)
        self.assertIn("ospf.passive_interfaces", fields)
        self.assertIn("static_routes", fields)
        self.assertIn("dhcp.pools", fields)
        self.assertIn("ntp.servers", fields)
        self.assertIn("logging.hosts", fields)
        self.assertIn("snmp.communities", fields)
        self.assertIn("acls[].type=extended", fields)
        self.assertIn("nat.overloads", fields)
        self.assertEqual(data["example"]["interfaces"][1]["mode"], "trunk")


if __name__ == "__main__":
    unittest.main()
