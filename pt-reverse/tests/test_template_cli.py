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
        self.assertIn("dual-stack-lan", data["commands"])
        self.assertIn("router-ring", data["commands"])
        self.assertIn("wan-ring", data["commands"])
        self.assertIn("wireless-lan", data["commands"])
        self.assertIn("vlan-router-on-stick", data["commands"])
        self.assertIn("switching-lab", data["commands"])
        self.assertIn("server-services", data["commands"])
        self.assertIn("edge-security", data["commands"])
        self.assertIn("campus", data["commands"])
        self.assertIn("redundant-campus", data["commands"])
        self.assertIn("enterprise-edge", data["commands"])
        self.assertIn("lan-star", data["templates"])
        self.assertIn("dual-stack-lan", data["templates"])
        self.assertIn("wireless-lan", data["templates"])
        self.assertIn("vlan-router-on-stick", data["templates"])
        self.assertIn("switching-lab", data["templates"])
        self.assertIn("server-services", data["templates"])
        self.assertIn("edge-security", data["templates"])
        self.assertIn("router-ring", data["templates"])
        self.assertIn("wan-ring", data["templates"])
        self.assertIn("campus", data["templates"])
        self.assertIn("redundant-campus", data["templates"])
        self.assertIn("enterprise-edge", data["templates"])
        self.assertIn("ospf", " ".join(data["templates"]["wan-ring"]["options"]))
        self.assertIn("--routing none|rip|ospf|static", data["templates"]["campus"]["options"])
        self.assertIn("--routing none|rip|ospf", data["templates"]["redundant-campus"]["options"])
        self.assertIn("--routing none|rip|ospf|static", data["templates"]["enterprise-edge"]["options"])
        self.assertIn("--client-addressing static|dhcp", data["templates"]["vlan-router-on-stick"]["options"])
        self.assertIn("--ipv6-prefix", data["templates"]["dual-stack-lan"]["options"])
        self.assertIn("--access-switches", data["templates"]["switching-lab"]["options"])
        self.assertIn("--services all|http,dns,ftp,tftp,email,ntp,syslog,dhcp", data["templates"]["server-services"]["options"])

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

    def test_dual_stack_lan_generates_ipv6_metadata_and_ios_configs(self) -> None:
        result = self.run_template(
            "dual-stack-lan",
            "--name",
            "DUAL",
            "--pcs",
            "2",
            "--servers",
            "1",
            "--ipv4-network",
            "192.168.60.0/24",
            "--ipv4-gateway",
            "192.168.60.1",
            "--ipv6-prefix",
            "2001:db8:60::/64",
            "--ipv6-gateway",
            "2001:db8:60::1",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = json.loads(result.stdout)
        names = {device["name"] for device in plan["devices"]}
        self.assertEqual(names, {"R-DUAL-DS", "SW-DUAL-DS", "PC-DUAL-1", "PC-DUAL-2", "SRV-DUAL-1"})
        self.assertTrue(all("x" in device and "y" in device for device in plan["devices"]))
        self.assertEqual(len(plan["links"]), 4)
        self.assertEqual(len(plan["pc_configs"]), 3)
        self.assertEqual(len(plan["ipv6_configs"]), 3)
        self.assertEqual(plan["metadata"]["source"], "pt730-template dual-stack-lan")
        self.assertEqual(plan["metadata"]["ipv6_prefix"], "2001:db8:60::/64")
        self.assertEqual(plan["pc_configs"][0]["ip"], "192.168.60.2")
        self.assertEqual(plan["pc_configs"][0]["ipv6"], "2001:db8:60::2")
        self.assertEqual(plan["pc_configs"][0]["ipv6_gateway"], "2001:db8:60::1")
        joined = "\n".join(command for config in plan["ios_configs"] for command in config["commands"])
        self.assertIn("ipv6 unicast-routing", joined)
        self.assertIn("ipv6 address 2001:db8:60::1/64", joined)
        self.assertIn("ipv6 enable", joined)
        self.assertIn("dns", plan["server_configs"][0])
        self.assertIn("ipv6_dns_records", plan["metadata"])
        self.assert_safe_and_renderable(plan)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as f:
            json.dump(plan, f)
            path = f.name
        try:
            summary = subprocess.run(
                [str(RENDER), "summary", path],
                cwd=ROOT.parent,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
                check=False,
            )
            self.assertEqual(summary.returncode, 0, summary.stderr)
            data = json.loads(summary.stdout)
            self.assertEqual(data["counts"]["ipv6_configs"], 3)
            self.assertEqual(data["ipv6_address_groups"][0]["network"], "2001:db8:60::/64")
            verification = subprocess.run(
                [str(RENDER), "verification-plan", path, "--format", "json"],
                cwd=ROOT.parent,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
                check=False,
            )
            self.assertEqual(verification.returncode, 0, verification.stderr)
            checks = json.loads(verification.stdout)
            self.assertGreaterEqual(checks["counts"]["ipv6"], 2)
        finally:
            Path(path).unlink(missing_ok=True)

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

    def test_vlan_router_on_stick_generates_dot1q_trunk_subinterfaces_and_access_ports(self) -> None:
        result = self.run_template(
            "vlan-router-on-stick",
            "--name",
            "LAB",
            "--vlans",
            "3",
            "--hosts-per-vlan",
            "2",
            "--servers-per-vlan",
            "1",
            "--address-pool",
            "192.168.20.0/22",
            "--vlan-base",
            "10",
            "--native-vlan",
            "10",
            "--domain",
            "lab.local",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = json.loads(result.stdout)
        names = {device["name"] for device in plan["devices"]}
        self.assertIn("R-LAB-ROAS", names)
        self.assertIn("SW-LAB-ACCESS", names)
        self.assertIn("PC-LAB-V10-1", names)
        self.assertIn("SRV-LAB-V12-1", names)
        self.assertTrue(all("x" in device and "y" in device for device in plan["devices"]))
        self.assertEqual(len(plan["devices"]), 11)
        self.assertEqual(len(plan["links"]), 10)
        self.assertEqual(len(plan["pc_configs"]), 9)
        self.assertEqual(len(plan["vlan_configs"]), 3)
        self.assertEqual([config["id"] for config in plan["vlan_configs"]], [10, 11, 12])
        self.assertEqual({link.get("vlan") for link in plan["links"] if "vlan" in link}, {10, 11, 12})
        self.assertEqual(plan["metadata"]["source"], "pt730-template vlan-router-on-stick")
        services = {config["name"]: config for config in plan["server_configs"]}
        self.assertIn("dns", services["SRV-LAB-V10-1"])
        joined = "\n".join(command for config in plan["ios_configs"] for command in config["commands"])
        self.assertIn("encapsulation dot1Q 10 native", joined)
        self.assertIn("encapsulation dot1Q 11", joined)
        self.assertIn("switchport mode trunk", joined)
        self.assertIn("switchport trunk allowed vlan 10,11,12", joined)
        self.assertIn("switchport access vlan 12", joined)
        self.assertNotIn("3560-24PS", json.dumps(plan))
        self.assert_safe_and_renderable(plan)

    def test_vlan_router_on_stick_supports_router_dhcp_client_addressing(self) -> None:
        result = self.run_template(
            "vlan-router-on-stick",
            "--name",
            "DHCP",
            "--vlans",
            "2",
            "--hosts-per-vlan",
            "2",
            "--servers-per-vlan",
            "1",
            "--address-pool",
            "192.168.40.0/23",
            "--vlan-base",
            "30",
            "--client-addressing",
            "dhcp",
            "--domain",
            "dhcp.local",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = json.loads(result.stdout)
        self.assertEqual(plan["metadata"]["client_addressing"], "dhcp")
        self.assertEqual(len(plan["dhcp_pools"]), 2)
        self.assertEqual(plan["dhcp_pools"][0]["name"], "VLAN30")
        self.assertEqual(plan["dhcp_pools"][0]["start"], "192.168.40.3")
        self.assertEqual(plan["dhcp_pools"][0]["end"], "192.168.40.4")
        self.assertEqual(plan["dhcp_pools"][0]["dns"], "192.168.40.2")
        pc_configs = {config["name"]: config for config in plan["pc_configs"]}
        self.assertEqual(pc_configs["PC-DHCP-V30-1"]["dhcp"], True)
        self.assertNotIn("ip", pc_configs["PC-DHCP-V30-1"])
        self.assertEqual(pc_configs["SRV-DHCP-V30-1"]["ip"], "192.168.40.2")
        joined = "\n".join(command for config in plan["ios_configs"] for command in config["commands"])
        self.assertIn("ip dhcp excluded-address 192.168.40.1", joined)
        self.assertIn("ip dhcp excluded-address 192.168.40.2", joined)
        self.assertIn("ip dhcp pool VLAN30", joined)
        self.assertIn("network 192.168.40.0 255.255.255.0", joined)
        self.assertIn("default-router 192.168.40.1", joined)
        self.assertIn("dns-server 192.168.40.2", joined)
        self.assertIn("domain-name dhcp.local", joined)
        self.assert_safe_and_renderable(plan)

    def test_vlan_router_on_stick_dhcp_allows_no_servers(self) -> None:
        result = self.run_template(
            "vlan-router-on-stick",
            "--name",
            "NOSRV",
            "--vlans",
            "1",
            "--hosts-per-vlan",
            "2",
            "--servers-per-vlan",
            "0",
            "--address-pool",
            "192.168.50.0/24",
            "--client-addressing",
            "dhcp",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = json.loads(result.stdout)
        self.assertEqual(len(plan["server_configs"]), 0)
        self.assertEqual(len([device for device in plan["devices"] if device["category"] == "server"]), 0)
        self.assertEqual(plan["dhcp_pools"][0]["start"], "192.168.50.2")
        self.assertEqual(plan["dhcp_pools"][0]["end"], "192.168.50.3")
        joined = "\n".join(command for config in plan["ios_configs"] for command in config["commands"])
        self.assertNotIn("dns-server", joined)
        self.assert_safe_and_renderable(plan)

    def test_switching_lab_generates_stp_etherchannel_and_access_vlans(self) -> None:
        result = self.run_template(
            "switching-lab",
            "--name",
            "SW",
            "--vlans",
            "3",
            "--hosts-per-vlan",
            "2",
            "--access-switches",
            "2",
            "--address-pool",
            "192.168.48.0/22",
            "--vlan-base",
            "10",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = json.loads(result.stdout)
        names = {device["name"] for device in plan["devices"]}
        self.assertIn("SW-SW-DIST-A", names)
        self.assertIn("SW-SW-DIST-B", names)
        self.assertIn("SW-SW-ACC-1", names)
        self.assertIn("PC-SW-V12-2", names)
        self.assertTrue(all("x" in device and "y" in device for device in plan["devices"]))
        self.assertEqual(len(plan["devices"]), 10)
        self.assertEqual(len(plan["links"]), 12)
        self.assertEqual(len(plan["pc_configs"]), 6)
        self.assertEqual(len(plan["vlan_configs"]), 3)
        self.assertEqual([config["id"] for config in plan["vlan_configs"]], [10, 11, 12])
        self.assertEqual({link.get("vlan") for link in plan["links"] if "vlan" in link}, {10, 11, 12})
        self.assertEqual(plan["metadata"]["source"], "pt730-template switching-lab")
        joined = "\n".join(command for config in plan["ios_configs"] for command in config["commands"])
        self.assertIn("spanning-tree vlan 10,11,12 root primary", joined)
        self.assertIn("spanning-tree vlan 10,11,12 root secondary", joined)
        self.assertIn("channel-group 1 mode active", joined)
        self.assertIn("interface Port-channel1", joined)
        self.assertIn("switchport trunk allowed vlan 10,11,12", joined)
        self.assertIn("switchport access vlan 12", joined)
        self.assertIn("spanning-tree bpduguard enable", joined)
        self.assertNotIn("3560-24PS", json.dumps(plan))
        self.assert_safe_and_renderable(plan)

    def test_server_services_generates_service_metadata_dhcp_clients_and_ios(self) -> None:
        result = self.run_template(
            "server-services",
            "--name",
            "SVC",
            "--clients",
            "3",
            "--network",
            "192.168.200.0/24",
            "--domain",
            "services.local",
            "--services",
            "all",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = json.loads(result.stdout)
        names = {device["name"] for device in plan["devices"]}
        self.assertEqual(
            names,
            {
                "R-SVC-GW",
                "SW-SVC-SERVICES",
                "SRV-SVC-SERVICES",
                "PC-SVC-CLIENT-1",
                "PC-SVC-CLIENT-2",
                "PC-SVC-CLIENT-3",
            },
        )
        self.assertTrue(all("x" in device and "y" in device for device in plan["devices"]))
        self.assertEqual(len(plan["links"]), 5)
        self.assertEqual(len(plan["pc_configs"]), 4)
        self.assertEqual(len(plan["server_configs"]), 1)
        self.assertEqual(plan["metadata"]["source"], "pt730-template server-services")
        self.assertEqual(plan["pc_configs"][0]["ip"], "192.168.200.2")
        self.assertTrue(all(config.get("dhcp") is True for config in plan["pc_configs"][1:]))
        services = plan["server_configs"][0]
        self.assertEqual(services["http"], True)
        self.assertEqual(services["tftp"], True)
        self.assertIn("dns", services)
        self.assertIn("ftp", services)
        self.assertIn("email", services)
        self.assertIn("ntp", services)
        self.assertIn("syslog", services)
        self.assertIn("dhcp", services)
        self.assertEqual(services["dns"]["records"][1]["name"], "www.services.local")
        self.assertEqual(services["ftp"]["accounts"][0]["username"], "lab")
        self.assertEqual(services["email"]["domain"], "services.local")
        self.assertEqual(services["dhcp"]["start"], "192.168.200.3")
        self.assertEqual(services["dhcp"]["end"], "192.168.200.5")
        joined = "\n".join(command for config in plan["ios_configs"] for command in config["commands"])
        self.assertIn("ip address 192.168.200.1 255.255.255.0", joined)
        self.assertIn("spanning-tree portfast", joined)
        self.assert_safe_and_renderable(plan)

    def test_server_services_can_disable_dhcp_for_static_clients(self) -> None:
        result = self.run_template(
            "server-services",
            "--name",
            "STATIC",
            "--clients",
            "2",
            "--services",
            "http,dns,ftp",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = json.loads(result.stdout)
        self.assertNotIn("dhcp", plan["server_configs"][0])
        self.assertEqual(plan["pc_configs"][1]["ip"], "192.168.200.3")
        self.assertEqual(plan["pc_configs"][2]["ip"], "192.168.200.4")
        self.assertFalse(any(config.get("dhcp") is True for config in plan["pc_configs"]))
        self.assert_safe_and_renderable(plan)

    def test_edge_security_generates_nat_acl_dmz_and_static_routes(self) -> None:
        result = self.run_template(
            "edge-security",
            "--name",
            "SEC",
            "--inside-hosts",
            "2",
            "--dmz-servers",
            "2",
            "--internet-hosts",
            "1",
            "--domain",
            "sec.local",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = json.loads(result.stdout)
        names = {device["name"] for device in plan["devices"]}
        self.assertEqual(
            names,
            {
                "R-SEC-EDGE",
                "R-SEC-ISP",
                "SW-SEC-LAN",
                "SW-SEC-DMZ",
                "SW-SEC-INET",
                "PC-SEC-IN-1",
                "PC-SEC-IN-2",
                "SRV-SEC-WEB",
                "SRV-SEC-DNS",
                "PC-SEC-INET-1",
            },
        )
        self.assertTrue(all("x" in device and "y" in device for device in plan["devices"]))
        self.assertEqual(len(plan["links"]), 9)
        self.assertEqual(len(plan["pc_configs"]), 5)
        self.assertEqual(len(plan["server_configs"]), 2)
        self.assertEqual(len(plan["ios_configs"]), 2)
        self.assertEqual(len(plan["security_policies"]), 2)
        self.assertEqual(plan["metadata"]["source"], "pt730-template edge-security")
        self.assertEqual(plan["metadata"]["domain"], "sec.local")
        services = {config["name"]: config for config in plan["server_configs"]}
        self.assertIn("http", services["SRV-SEC-WEB"])
        self.assertIn("dns", services["SRV-SEC-DNS"])
        self.assertEqual(services["SRV-SEC-DNS"]["dns"]["records"][0]["name"], "www.sec.local")
        joined = "\n".join(command for config in plan["ios_configs"] for command in config["commands"])
        self.assertIn("ip nat inside source list 10 interface GigabitEthernet0/2 overload", joined)
        self.assertIn("ip access-group 101 in", joined)
        self.assertIn("access-list 101 deny ip any 192.168.10.0 0.0.0.255", joined)
        self.assertIn("ip route 0.0.0.0 0.0.0.0 203.0.113.1", joined)
        self.assertIn("ip route 172.16.10.0 255.255.255.0 203.0.113.2", joined)
        self.assertNotIn("ASA5505", json.dumps(plan))
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

    def test_wan_ring_supports_ospf_routing_configs(self) -> None:
        result = self.run_template(
            "wan-ring",
            "--name",
            "OSPF",
            "--sites",
            "3",
            "--hosts-per-site",
            "1",
            "--servers-per-site",
            "0",
            "--interconnect-pool",
            "10.50.0.0/28",
            "--lan-pool",
            "192.168.140.0/22",
            "--routing",
            "ospf",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = json.loads(result.stdout)
        self.assertEqual(len(plan["ios_configs"]), 3)
        joined = "\n".join(command for config in plan["ios_configs"] for command in config["commands"])
        self.assertIn("router ospf 1", joined)
        self.assertIn("router-id 10.255.0.1", joined)
        self.assertIn("passive-interface GigabitEthernet0/0", joined)
        self.assertIn("network 192.168.140.0 0.0.0.255 area 0", joined)
        self.assertIn("network 10.50.0.0 0.0.0.3 area 0", joined)
        self.assertNotIn("router rip", joined)
        self.assertNotIn("ip route", joined)
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

    def test_campus_supports_ospf_l3_configs(self) -> None:
        result = self.run_template(
            "campus",
            "--name",
            "OSPF",
            "--cores",
            "2",
            "--segments",
            "3",
            "--hosts-per-segment",
            "1",
            "--servers",
            "2",
            "--l3",
            "--routing",
            "ospf",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = json.loads(result.stdout)
        joined = "\n".join(command for config in plan["ios_configs"] for command in config["commands"])
        self.assertIn("router ospf 1", joined)
        self.assertIn("router-id 10.255.0.1", joined)
        self.assertIn("passive-interface Vlan10", joined)
        self.assertIn("network 172.16.1.0 0.0.0.63 area 0", joined)
        self.assertIn("network 10.10.0.0 0.0.0.3 area 0", joined)
        self.assertNotIn("router rip", joined)
        self.assert_safe_and_renderable(plan)

    def test_redundant_campus_generates_dual_core_hsrp_services_and_layout(self) -> None:
        result = self.run_template(
            "redundant-campus",
            "--name",
            "AGENT",
            "--segments",
            "3",
            "--hosts-per-segment",
            "2",
            "--servers",
            "4",
            "--routing",
            "ospf",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = json.loads(result.stdout)
        names = {device["name"] for device in plan["devices"]}
        self.assertIn("CORE-AGENT-A", names)
        self.assertIn("CORE-AGENT-B", names)
        self.assertIn("SW-AGENT-SRV", names)
        self.assertIn("SW-AGENT-V20", names)
        self.assertIn("SRV-AGENT-NMS", names)
        self.assertIn("PC-AGENT-V22-2", names)
        self.assertTrue(all("x" in device and "y" in device for device in plan["devices"]))
        self.assertEqual(plan["metadata"]["source"], "pt730-template redundant-campus")
        self.assertIn("dual_homed_access", plan["metadata"]["features"])
        self.assertEqual(len(plan["redundancy_groups"]), 3)
        self.assertEqual(plan["vlan_configs"][0]["gateway"], "172.16.1.62")
        self.assertEqual({link.get("vlan") for link in plan["links"] if "vlan" in link}, {10, 20, 21, 22})
        self.assertEqual(len(plan["dhcp_pools"]), 3)
        services = {config["name"]: config for config in plan["server_configs"]}
        self.assertIn("http", services["SRV-AGENT-WEB"])
        self.assertIn("dns", services["SRV-AGENT-DNS"])
        self.assertIn("ftp", services["SRV-AGENT-FTP"])
        self.assertIn("ntp", services["SRV-AGENT-NMS"])
        self.assertIn("syslog", services["SRV-AGENT-NMS"])
        joined = "\n".join(command for config in plan["ios_configs"] for command in config["commands"])
        self.assertIn("spanning-tree vlan 10,20,21,22 root primary", joined)
        self.assertIn("spanning-tree vlan 10,20,21,22 root secondary", joined)
        self.assertIn("standby 20 ip 192.168.0.254", joined)
        self.assertIn("standby 20 priority 110", joined)
        self.assertIn("ip helper-address 172.16.1.1", joined)
        self.assertIn("ip dhcp pool VLAN20", joined)
        self.assertIn("ntp server 172.16.1.4 prefer", joined)
        self.assertIn("logging host 172.16.1.4", joined)
        self.assertIn("snmp-server community campusRO RO 10", joined)
        self.assertIn("router ospf 1", joined)
        self.assert_safe_and_renderable(plan)

    def test_enterprise_edge_generates_integrated_hq_dmz_branch_wan_topology(self) -> None:
        result = self.run_template("enterprise-edge", "--name", "ENT")
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = json.loads(result.stdout)
        names = {device["name"] for device in plan["devices"]}
        self.assertIn("R-ENT-EDGE", names)
        self.assertIn("R-ENT-ISP", names)
        self.assertIn("SW-ENT-HQ-CORE", names)
        self.assertIn("SW-ENT-DMZ", names)
        self.assertIn("R-ENT-BR2", names)
        self.assertIn("PC-ENT-BR2-2", names)
        self.assertIn("SRV-ENT-DMZ-WEB", names)
        self.assertTrue(all("x" in device and "y" in device for device in plan["devices"]))
        self.assertEqual(len(plan["devices"]), 30)
        self.assertEqual(len(plan["modules"]), 3)
        self.assertEqual(len(plan["links"]), 30)
        self.assertEqual(len(plan["pc_configs"]), 17)
        self.assertEqual(len(plan["server_configs"]), 6)
        self.assertEqual(len(plan["ios_configs"]), 13)
        self.assertEqual(len(plan["security_policies"]), 2)
        self.assertEqual(plan["metadata"]["source"], "pt730-template enterprise-edge")
        self.assertIn("branch_wan", plan["metadata"]["features"])
        self.assertEqual({config["id"] for config in plan["vlan_configs"]}, {10, 20, 21, 22})
        self.assertEqual({link.get("vlan") for link in plan["links"] if "vlan" in link}, {10, 20, 21, 22})
        services = {config["name"]: config for config in plan["server_configs"]}
        self.assertIn("http", services["SRV-ENT-WEB"])
        self.assertIn("dns", services["SRV-ENT-DNS"])
        self.assertIn("ftp", services["SRV-ENT-FTP"])
        self.assertIn("email", services["SRV-ENT-MAIL"])
        self.assertIn("dns", services["SRV-ENT-DMZ-DNS"])
        joined = "\n".join(command for config in plan["ios_configs"] for command in config["commands"])
        self.assertIn("encapsulation dot1Q 20", joined)
        self.assertIn("ip nat inside source list 10 interface GigabitEthernet0/2 overload", joined)
        self.assertIn("access-list 101 deny ip any 192.168.0.0 0.0.7.255", joined)
        self.assertIn("router ospf 1", joined)
        self.assertIn("network 10.60.0.0 0.0.0.3 area 0", joined)
        self.assertIn("passive-interface GigabitEthernet0/0", joined)
        self.assertIn("ip route 172.16.10.0 255.255.255.0 203.0.113.1", joined)
        self.assertNotIn("ASA5505", json.dumps(plan))
        self.assertNotIn("3560-24PS", json.dumps(plan))
        self.assert_safe_and_renderable(plan)


if __name__ == "__main__":
    unittest.main()
