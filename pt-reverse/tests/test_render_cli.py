#!/usr/bin/env python3
"""Tests for offline topology rendering."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RENDER = ROOT / "bin" / "pt730-render"


class RenderCliTest(unittest.TestCase):
    def run_render(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(RENDER), *args],
            cwd=ROOT.parent,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
        )

    def test_mermaid_renders_devices_and_links(self) -> None:
        result = self.run_render("mermaid", str(ROOT / "examples" / "simple-lan.json"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("flowchart LR", result.stdout)
        self.assertIn("R_DEMO", result.stdout)
        self.assertIn("PC_DEMO", result.stdout)
        self.assertIn("GigabitEthernet0/0", result.stdout)
        self.assertIn("FastEthernet0/1", result.stdout)

    def test_mermaid_can_hide_link_labels(self) -> None:
        result = self.run_render("mermaid", str(ROOT / "examples" / "simple-lan.json"), "--no-link-labels")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("R_DEMO --- SW_DEMO", result.stdout)
        self.assertNotIn("GigabitEthernet0/0", result.stdout)

    def test_mermaid_strict_rejects_guarded_dhcp_warning(self) -> None:
        result = self.run_render("--strict-safety", "mermaid", str(ROOT / "examples" / "server-dhcp-lan.json"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("safety check failed", result.stderr)

    def test_markdown_renders_tables(self) -> None:
        result = self.run_render("markdown", str(ROOT / "examples" / "simple-lan.json"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("## Devices", result.stdout)
        self.assertIn("| R_DEMO | 2911 | router |", result.stdout)
        self.assertIn("## Links", result.stdout)
        self.assertIn("GigabitEthernet0/0", result.stdout)
        self.assertIn("| A | Port A | B | Port B | Cable | VLAN | Note |", result.stdout)
        self.assertIn("192.168.50.10", result.stdout)

    def test_svg_renders_devices_and_links(self) -> None:
        result = self.run_render("svg", str(ROOT / "examples" / "simple-lan.json"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("<svg", result.stdout)
        self.assertIn("R_DEMO", result.stdout)
        self.assertIn("SW_DEMO", result.stdout)
        self.assertIn("PC_DEMO", result.stdout)
        self.assertIn("<line", result.stdout)
        self.assertIn("GigabitEthernet0/0", result.stdout)

    def test_svg_visual_options_control_theme_and_labels(self) -> None:
        result = self.run_render("svg", str(ROOT / "examples" / "simple-lan.json"), "--theme", "dark", "--no-link-labels", "--no-model-labels")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("background: #0f172a", result.stdout)
        self.assertIn("R_DEMO", result.stdout)
        self.assertNotIn("GigabitEthernet0/0", result.stdout)
        self.assertNotIn("2911", result.stdout)

    def test_svg_can_include_title_and_legend(self) -> None:
        result = self.run_render("svg", str(ROOT / "examples" / "simple-lan.json"), "--title", "Demo LAN", "--legend")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('<title id="title">Demo LAN</title>', result.stdout)
        self.assertIn('class="diagram-title"', result.stdout)
        self.assertIn('class="legend"', result.stdout)
        self.assertIn("Legend", result.stdout)
        self.assertIn("Router", result.stdout)
        self.assertIn("Switch", result.stdout)
        self.assertIn("PC/Laptop", result.stdout)

    def test_svg_report_preset_uses_report_friendly_defaults(self) -> None:
        result = self.run_render("svg", str(ROOT / "examples" / "simple-lan.json"), "--preset", "report")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("background: #fbf7ef", result.stdout)
        self.assertIn('<title id="title">simple-lan</title>', result.stdout)
        self.assertIn('class="legend"', result.stdout)
        self.assertIn("192.168.50.0/24 gw 192.168.50.1", result.stdout)
        self.assertNotIn("GigabitEthernet0/0", result.stdout)

    def test_svg_can_render_network_group_boxes(self) -> None:
        result = self.run_render("svg", str(ROOT / "examples" / "simple-lan.json"), "--group-by", "network")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('class="visual-group"', result.stdout)
        self.assertIn('class="group-box"', result.stdout)
        self.assertIn("192.168.50.0/24 gw 192.168.50.1", result.stdout)

    def test_svg_output_option_writes_file(self) -> None:
        out = ROOT / "tests" / ".render-output.svg"
        out.unlink(missing_ok=True)
        try:
            result = self.run_render("svg", str(ROOT / "examples" / "simple-lan.json"), "--output", str(out))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "")
            text = out.read_text(encoding="utf-8")
            self.assertIn("<svg", text)
            self.assertIn("PC_DEMO", text)
        finally:
            out.unlink(missing_ok=True)

    def test_drawio_renders_importable_mxfile(self) -> None:
        result = self.run_render("drawio", str(ROOT / "examples" / "simple-lan.json"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("<mxfile", result.stdout)
        self.assertIn("<mxGraphModel", result.stdout)
        self.assertIn("R_DEMO", result.stdout)
        self.assertIn("SW_DEMO", result.stdout)
        self.assertIn("PC_DEMO", result.stdout)
        self.assertIn("GigabitEthernet0/0", result.stdout)
        self.assertIn("edge=\"1\"", result.stdout)

    def test_drawio_visual_options_control_theme_and_labels(self) -> None:
        result = self.run_render("drawio", str(ROOT / "examples" / "simple-lan.json"), "--theme", "paper", "--no-link-labels", "--no-model-labels")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("labelBackgroundColor=#fbf7ef", result.stdout)
        self.assertIn('value="R_DEMO"', result.stdout)
        self.assertNotIn("GigabitEthernet0/0", result.stdout)
        self.assertNotIn("2911", result.stdout)

    def test_drawio_can_include_title_and_legend(self) -> None:
        result = self.run_render("drawio", str(ROOT / "examples" / "simple-lan.json"), "--title", "Demo LAN", "--legend")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('id="title" value="Demo LAN"', result.stdout)
        self.assertIn('id="legend-panel" value="Legend"', result.stdout)
        self.assertIn('value="Router"', result.stdout)
        self.assertIn('value="Switch"', result.stdout)
        self.assertIn('value="PC/Laptop"', result.stdout)

    def test_drawio_can_render_network_group_boxes(self) -> None:
        result = self.run_render("drawio", str(ROOT / "examples" / "simple-lan.json"), "--group-by", "network")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('value="192.168.50.0/24 gw 192.168.50.1"', result.stdout)
        self.assertIn("fillOpacity=18", result.stdout)
        self.assertIn("dashed=1", result.stdout)

    def test_render_outputs_topology_annotations(self) -> None:
        plan = {
            "devices": [
                {"name": "R1", "category": "router", "model": "2911", "x": 100, "y": 100},
                {"name": "SW1", "category": "switch", "model": "2960-24TT", "x": 280, "y": 100},
            ],
            "links": [{"a": "R1", "pa": "GigabitEthernet0/0", "b": "SW1", "pb": "GigabitEthernet0/1", "cable": "straight"}],
            "annotations": [
                {
                    "id": "callout-core",
                    "kind": "info",
                    "target": "R1",
                    "title": "Core Gateway",
                    "text": "Default gateway and routing validation point.",
                },
                {
                    "id": "note-report",
                    "kind": "warning",
                    "x": 24,
                    "y": 260,
                    "text": "Manual IPv6 host configuration remains report metadata.",
                },
            ],
        }
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as f:
            json.dump(plan, f)
            path = f.name
        try:
            mermaid_result = self.run_render("mermaid", path)
            svg_result = self.run_render("svg", path)
            drawio_result = self.run_render("drawio", path)
            markdown_result = self.run_render("markdown", path)
            summary_result = self.run_render("summary", path)
            audit_result = self.run_render("diagram-audit", path)
        finally:
            Path(path).unlink(missing_ok=True)
        self.assertEqual(mermaid_result.returncode, 0, mermaid_result.stderr)
        self.assertIn("annotation_callout_core", mermaid_result.stdout)
        self.assertIn("Core Gateway", mermaid_result.stdout)
        self.assertIn("R1 -.-> annotation_callout_core", mermaid_result.stdout)
        self.assertIn("classDef annotation_1 fill:#dbeafe,stroke:#2563eb", mermaid_result.stdout)
        self.assertEqual(svg_result.returncode, 0, svg_result.stderr)
        self.assertIn('class="annotation annotation-info"', svg_result.stdout)
        self.assertIn('id="callout-core"', svg_result.stdout)
        self.assertIn("Core Gateway", svg_result.stdout)
        self.assertIn('class="annotation-leader"', svg_result.stdout)
        self.assertEqual(drawio_result.returncode, 0, drawio_result.stderr)
        self.assertIn('id="annotation-1"', drawio_result.stdout)
        self.assertIn("Core Gateway", drawio_result.stdout)
        self.assertIn('id="annotation-leader-1"', drawio_result.stdout)
        self.assertEqual(markdown_result.returncode, 0, markdown_result.stderr)
        self.assertIn("## Diagram Annotations", markdown_result.stdout)
        self.assertIn("| callout-core | info | R1 | Core Gateway |", markdown_result.stdout)
        self.assertEqual(summary_result.returncode, 0, summary_result.stderr)
        summary = json.loads(summary_result.stdout)
        self.assertEqual(summary["counts"]["annotations"], 2)
        self.assertEqual(summary["annotations"][1]["kind"], "warning")
        self.assertEqual(audit_result.returncode, 0, audit_result.stderr)
        audit = json.loads(audit_result.stdout)
        self.assertEqual(audit["checks"]["counts"]["annotations"], 2)

    def test_render_can_append_temporary_cli_annotations(self) -> None:
        annotation = {
            "id": "cli-note",
            "kind": "success",
            "target": "R_DEMO",
            "title": "CLI Note",
            "text": "Temporary render-only annotation.",
        }
        result = self.run_render("summary", str(ROOT / "examples" / "simple-lan.json"), "--annotation", json.dumps(annotation))
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["counts"]["annotations"], 1)
        self.assertEqual(data["annotations"][0]["id"], "cli-note")

    def test_wireless_ap_rendering_and_summary_metadata(self) -> None:
        plan = {
            "devices": [
                {"name": "SW-WIFI", "category": "switch", "model": "2960-24TT", "x": 100, "y": 100},
                {"name": "AP-WIFI-1", "category": "accesspoint", "model": "AccessPoint-PT", "x": 260, "y": 100},
                {"name": "LAP-WIFI-1", "category": "laptop", "model": "Laptop-PT", "x": 260, "y": 240},
            ],
            "links": [
                {"a": "SW-WIFI", "pa": "FastEthernet0/2", "b": "AP-WIFI-1", "pb": "Port 0", "cable": "straight"},
                {"a": "AP-WIFI-1", "pa": "Port 0", "b": "LAP-WIFI-1", "pb": "FastEthernet0", "cable": "wireless", "note": "wireless association SSID PT730-LAB"},
            ],
            "pc_configs": [
                {"name": "LAP-WIFI-1", "ip": "192.168.80.2", "mask": "255.255.255.0", "gateway": "192.168.80.1", "dns": "192.168.80.10"}
            ],
            "ap_configs": [{"name": "AP-WIFI-1", "ssid": "PT730-LAB", "mode": "access-point"}],
        }
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as f:
            json.dump(plan, f)
            path = f.name
        try:
            svg_result = self.run_render("svg", path, "--group-by", "network")
            drawio_result = self.run_render("drawio", path)
            markdown_result = self.run_render("markdown", path)
            summary_result = self.run_render("summary", path)
        finally:
            Path(path).unlink(missing_ok=True)
        self.assertEqual(svg_result.returncode, 0, svg_result.stderr)
        self.assertIn('class="device wireless"', svg_result.stdout)
        self.assertIn('class="link wireless-link"', svg_result.stdout)
        self.assertIn("192.168.80.0/24 gw 192.168.80.1", svg_result.stdout)
        self.assertEqual(drawio_result.returncode, 0, drawio_result.stderr)
        self.assertIn("dashed=1", drawio_result.stdout)
        self.assertIn("strokeColor=#0e7490", drawio_result.stdout)
        self.assertEqual(markdown_result.returncode, 0, markdown_result.stderr)
        self.assertIn("## Wireless AP Configs", markdown_result.stdout)
        self.assertIn("| AP-WIFI-1 | PT730-LAB | access-point |", markdown_result.stdout)
        self.assertEqual(summary_result.returncode, 0, summary_result.stderr)
        data = json.loads(summary_result.stdout)
        self.assertEqual(data["counts"]["ap_configs"], 1)
        self.assertEqual(data["wireless"]["aps"], 1)
        self.assertEqual(data["wireless"]["ssids"], ["PT730-LAB"])
        self.assertEqual(data["wireless"]["links"], 1)

    def test_drawio_output_option_writes_file(self) -> None:
        out = ROOT / "tests" / ".render-output.drawio"
        out.unlink(missing_ok=True)
        try:
            result = self.run_render("drawio", str(ROOT / "examples" / "simple-lan.json"), "--output", str(out))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "")
            text = out.read_text(encoding="utf-8")
            self.assertIn("<mxfile", text)
            self.assertIn("PC_DEMO", text)
        finally:
            out.unlink(missing_ok=True)

    def test_html_renders_embedded_diagram_and_report(self) -> None:
        result = self.run_render("html", str(ROOT / "examples" / "simple-lan.json"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("<!doctype html>", result.stdout)
        self.assertIn("<svg", result.stdout)
        self.assertIn("R_DEMO", result.stdout)
        self.assertIn("Packet Tracer Topology Plan", result.stdout)
        self.assertIn("192.168.50.10", result.stdout)

    def test_html_visual_options_control_theme_and_diagram_labels(self) -> None:
        result = self.run_render("html", str(ROOT / "examples" / "simple-lan.json"), "--theme", "dark", "--no-link-labels", "--no-model-labels")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("background: #020617", result.stdout)
        self.assertIn("<svg", result.stdout)
        self.assertIn("192.168.50.10", result.stdout)
        diagram = result.stdout.split("    </section>", 1)[0]
        self.assertNotIn("GigabitEthernet0/0", diagram)
        self.assertNotIn("2911", diagram)

    def test_html_can_include_title_and_legend(self) -> None:
        result = self.run_render("html", str(ROOT / "examples" / "simple-lan.json"), "--title", "Demo LAN", "--legend")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("<title>Demo LAN</title>", result.stdout)
        self.assertIn("<h1>Demo LAN</h1>", result.stdout)
        self.assertIn('class="legend"', result.stdout)
        self.assertIn("PC/Laptop", result.stdout)

    def test_html_can_render_vlan_group_boxes(self) -> None:
        result = self.run_render("html", str(ROOT / "course-design" / "college-network-topology-pt73-safe.json"), "--group-by", "vlan")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("VLAN 10", result.stdout)
        self.assertIn('class="group-box"', result.stdout)

    def test_html_output_option_writes_file(self) -> None:
        out = ROOT / "tests" / ".render-output.html"
        out.unlink(missing_ok=True)
        try:
            result = self.run_render("html", str(ROOT / "examples" / "simple-lan.json"), "--output", str(out))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "")
            text = out.read_text(encoding="utf-8")
            self.assertIn("<!doctype html>", text)
            self.assertIn("PC_DEMO", text)
        finally:
            out.unlink(missing_ok=True)

    def test_markdown_renders_address_and_link_metadata(self) -> None:
        result = self.run_render("markdown", str(ROOT / "course-design" / "college-network-topology-pt73-safe.json"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("## Address Summary", result.stdout)
        self.assertIn("| 192.168.0.0/26 | 192.168.0.62 | 172.16.1.11 | 2 | PC-OFFICE-1, PC-OFFICE-2 |", result.stdout)
        self.assertIn("10.10.12.0/30", result.stdout)
        self.assertIn("| MLS1 | FastEthernet0/1 | SW-SRV | GigabitEthernet0/1 | cross | 10 |", result.stdout)

    def test_markdown_renders_ios_config_summary(self) -> None:
        result = self.run_render("markdown", str(ROOT / "examples" / "two-router-serial-configured.json"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("## IOS Configs", result.stdout)
        self.assertIn("| R_AUTO1 | yes | 8 |", result.stdout)
        self.assertIn("| R_AUTO2 | yes | 7 |", result.stdout)

    def test_markdown_renders_server_service_details(self) -> None:
        result = self.run_render("markdown", str(ROOT / "examples" / "server-dhcp-lan.json"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("## DNS Records", result.stdout)
        self.assertIn("| SRV_DHCP | dhcpdemo.local | 192.168.200.10 |", result.stdout)
        self.assertIn("## FTP Users", result.stdout)
        self.assertIn("| SRV_DHCP | lab | RWDNL |", result.stdout)
        self.assertIn("## Email Accounts", result.stdout)
        self.assertIn("| SRV_DHCP | college.local | student |", result.stdout)
        self.assertIn("## DHCP Server Pools", result.stdout)
        self.assertIn("| SRV_DHCP | yes | 192.168.200.0 | 255.255.255.0 | 192.168.200.100 | 192.168.200.150 |", result.stdout)

    def test_markdown_and_summary_render_security_policies(self) -> None:
        plan = {
            "devices": [{"name": "R-EDGE", "category": "router", "model": "2911"}],
            "links": [],
            "security_policies": [
                {
                    "device": "R-EDGE",
                    "type": "nat_overload",
                    "interface": "GigabitEthernet0/2",
                    "acl": "10",
                    "direction": "inside-to-outside",
                    "summary": "PAT inside users to outside",
                },
                {
                    "device": "R-EDGE",
                    "type": "outside_acl",
                    "interface": "GigabitEthernet0/2",
                    "acl": "101",
                    "direction": "in",
                    "summary": "Deny inbound to inside LAN",
                },
            ],
        }
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as f:
            json.dump(plan, f)
            path = f.name
        try:
            markdown_result = self.run_render("markdown", path)
            summary_result = self.run_render("summary", path)
        finally:
            Path(path).unlink(missing_ok=True)
        self.assertEqual(markdown_result.returncode, 0, markdown_result.stderr)
        self.assertIn("## Security Policies", markdown_result.stdout)
        self.assertIn("| R-EDGE | nat_overload | GigabitEthernet0/2 | 10 | inside-to-outside | PAT inside users to outside |", markdown_result.stdout)
        self.assertEqual(summary_result.returncode, 0, summary_result.stderr)
        data = json.loads(summary_result.stdout)
        self.assertEqual(data["counts"]["security_policies"], 2)
        self.assertEqual(data["security_policies"][1]["type"], "outside_acl")

    def test_markdown_and_summary_render_vlan_configs(self) -> None:
        plan = {
            "devices": [{"name": "SW1", "category": "switch", "model": "2960-24TT"}],
            "links": [],
            "vlan_configs": [
                {"id": 10, "name": "STAFF", "network": "192.168.10.0/24", "gateway": "192.168.10.1"},
                {"id": 20, "name": "STUDENTS", "network": "192.168.20.0/24", "gateway": "192.168.20.1"},
            ],
        }
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as f:
            json.dump(plan, f)
            path = f.name
        try:
            markdown_result = self.run_render("markdown", path)
            summary_result = self.run_render("summary", path)
        finally:
            Path(path).unlink(missing_ok=True)
        self.assertEqual(markdown_result.returncode, 0, markdown_result.stderr)
        self.assertIn("## VLAN Configs", markdown_result.stdout)
        self.assertIn("| 10 | STAFF | 192.168.10.0/24 | 192.168.10.1 |", markdown_result.stdout)
        self.assertEqual(summary_result.returncode, 0, summary_result.stderr)
        data = json.loads(summary_result.stdout)
        self.assertEqual(data["counts"]["vlan_configs"], 2)
        self.assertEqual(data["vlans"][1]["name"], "STUDENTS")

    def test_markdown_and_summary_render_router_dhcp_pools(self) -> None:
        plan = {
            "devices": [{"name": "R1", "category": "router", "model": "2911"}],
            "links": [],
            "dhcp_pools": [
                {
                    "device": "R1",
                    "name": "VLAN10",
                    "vlan": 10,
                    "network": "192.168.10.0",
                    "mask": "255.255.255.0",
                    "start": "192.168.10.20",
                    "end": "192.168.10.200",
                    "gateway": "192.168.10.1",
                    "dns": "192.168.10.2",
                }
            ],
        }
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as f:
            json.dump(plan, f)
            path = f.name
        try:
            markdown_result = self.run_render("markdown", path)
            summary_result = self.run_render("summary", path)
        finally:
            Path(path).unlink(missing_ok=True)
        self.assertEqual(markdown_result.returncode, 0, markdown_result.stderr)
        self.assertIn("## Router DHCP Pools", markdown_result.stdout)
        self.assertIn("| R1 | VLAN10 | 10 | 192.168.10.0 | 255.255.255.0 | 192.168.10.20 | 192.168.10.200 |", markdown_result.stdout)
        self.assertEqual(summary_result.returncode, 0, summary_result.stderr)
        data = json.loads(summary_result.stdout)
        self.assertEqual(data["counts"]["dhcp_pools"], 1)
        self.assertEqual(data["dhcp_pools"][0]["gateway"], "192.168.10.1")

    def test_summary_outputs_machine_readable_counts(self) -> None:
        result = self.run_render("summary", str(ROOT / "course-design" / "college-network-topology-pt73-safe.json"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"devices": 40', result.stdout)
        self.assertIn('"links": 40', result.stdout)
        self.assertIn('"address_groups"', result.stdout)
        self.assertIn('"192.168.0.0/26"', result.stdout)

    def test_diagram_audit_accepts_clean_render(self) -> None:
        result = self.run_render("diagram-audit", str(ROOT / "examples" / "simple-lan.json"))
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["kind"], "pt730-diagram-audit")
        self.assertTrue(data["ok"])
        self.assertEqual(data["errors"], [])
        self.assertEqual(data["warnings"], [])
        self.assertEqual(data["checks"]["counts"]["rendered_devices"], 3)
        self.assertEqual(data["checks"]["components"]["count"], 1)

    def test_diagram_audit_accepts_report_preset_options(self) -> None:
        result = self.run_render("diagram-audit", str(ROOT / "examples" / "simple-lan.json"), "--preset", "report")
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertTrue(data["ok"])
        self.assertEqual(data["checks"]["render_options"]["preset"], "report")
        self.assertEqual(data["checks"]["render_options"]["group_by"], "auto")
        self.assertEqual(data["checks"]["render_options"]["legend"], True)

    def test_diagram_audit_reports_layout_warnings_without_failing(self) -> None:
        plan = {
            "devices": [
                {"name": "R1", "category": "router", "model": "2911", "x": 100, "y": 100},
                {"name": "SW1", "category": "switch", "model": "2960-24TT", "x": 150, "y": 130},
                {"name": "PC1", "category": "pc", "model": "PC-PT"},
                {"name": "SRV1", "category": "server", "model": "Server-PT", "x": 900, "y": 900},
            ],
            "links": [{"a": "R1", "pa": "GigabitEthernet0/0", "b": "SW1", "pb": "FastEthernet0/1", "cable": "straight"}],
        }
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as f:
            json.dump(plan, f)
            path = f.name
        try:
            result = self.run_render("diagram-audit", path)
        finally:
            Path(path).unlink(missing_ok=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertTrue(data["ok"])
        messages = [warning["message"] for warning in data["warnings"]]
        self.assertIn("some devices have no explicit x/y coordinates; renderer will use deterministic fallback positions", messages)
        self.assertIn("some rendered devices are close enough to overlap visually", messages)
        self.assertIn("topology has disconnected components", messages)
        self.assertEqual(data["checks"]["overlaps"][0]["a"], "R1")
        self.assertEqual(data["checks"]["coordinates"]["missing"], ["PC1"])

    def test_diagram_audit_rejects_empty_topology(self) -> None:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as f:
            json.dump({"devices": [], "links": []}, f)
            path = f.name
        try:
            result = self.run_render("diagram-audit", path)
        finally:
            Path(path).unlink(missing_ok=True)
        self.assertNotEqual(result.returncode, 0)
        data = json.loads(result.stdout)
        self.assertFalse(data["ok"])
        self.assertIn("empty topology has no devices or links", data["errors"][0]["message"])

    def test_output_option_writes_file(self) -> None:
        out = ROOT / "tests" / ".render-output.md"
        out.unlink(missing_ok=True)
        try:
            result = self.run_render("markdown", str(ROOT / "examples" / "simple-lan.json"), "--output", str(out))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "")
            self.assertIn("## Devices", out.read_text(encoding="utf-8"))
        finally:
            out.unlink(missing_ok=True)

    def test_bundle_writes_default_artifacts_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir) / "bundle"
            result = self.run_render(
                "bundle",
                str(ROOT / "examples" / "simple-lan.json"),
                "--output-dir",
                str(out_dir),
                "--basename",
                "simple",
                "--theme",
                "paper",
                "--group-by",
                "network",
                "--no-link-labels",
                "--no-model-labels",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            manifest = json.loads(result.stdout)
            self.assertEqual(manifest["kind"], "pt730-render-bundle")
            self.assertEqual(manifest["basename"], "simple")
            self.assertEqual(manifest["formats"], ["svg", "drawio", "html", "markdown", "summary"])
            self.assertEqual(manifest["options"]["theme"], "paper")
            self.assertEqual(manifest["options"]["link_labels"], False)
            self.assertEqual(manifest["options"]["model_labels"], False)
            self.assertEqual(manifest["options"]["group_by"], "network")
            self.assertEqual(manifest["options"]["title"], "")
            self.assertEqual(manifest["options"]["legend"], False)
            self.assertEqual(manifest["counts"]["devices"], 3)
            self.assertEqual(manifest["artifacts"]["svg"], "simple.svg")
            self.assertEqual(manifest["artifacts"]["drawio"], "simple.drawio")
            self.assertEqual(manifest["artifacts"]["html"], "simple.html")
            self.assertEqual(manifest["artifacts"]["markdown"], "simple.md")
            self.assertEqual(manifest["artifacts"]["summary"], "simple.summary.json")
            self.assertEqual(manifest["artifacts"]["manifest"], "simple.manifest.json")
            for filename in manifest["artifacts"].values():
                self.assertTrue((out_dir / filename).exists(), filename)
            svg_text = (out_dir / "simple.svg").read_text(encoding="utf-8")
            self.assertIn("192.168.50.0/24 gw 192.168.50.1", svg_text)
            self.assertNotIn("GigabitEthernet0/0", svg_text)
            self.assertNotIn("2911", svg_text)
            summary_data = json.loads((out_dir / "simple.summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary_data["counts"]["links"], 2)
            saved_manifest = json.loads((out_dir / "simple.manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(saved_manifest["artifacts"], manifest["artifacts"])

    def test_bundle_formats_option_limits_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir) / "bundle"
            result = self.run_render(
                "bundle",
                str(ROOT / "examples" / "simple-lan.json"),
                "--output-dir",
                str(out_dir),
                "--basename",
                "small",
                "--formats",
                "summary,markdown",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            manifest = json.loads(result.stdout)
            self.assertEqual(manifest["formats"], ["summary", "markdown"])
            self.assertTrue((out_dir / "small.summary.json").exists())
            self.assertTrue((out_dir / "small.md").exists())
            self.assertFalse((out_dir / "small.svg").exists())

    def test_bundle_can_include_diagram_audit_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir) / "bundle"
            result = self.run_render(
                "bundle",
                str(ROOT / "examples" / "simple-lan.json"),
                "--output-dir",
                str(out_dir),
                "--basename",
                "simple",
                "--formats",
                "summary,diagram-audit",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            manifest = json.loads(result.stdout)
            self.assertEqual(manifest["formats"], ["summary", "diagram-audit"])
            self.assertEqual(manifest["diagram_audit"], {"ok": True, "exit_code": 0})
            self.assertEqual(manifest["artifacts"]["diagram-audit"], "simple.diagram-audit.json")
            audit_data = json.loads((out_dir / "simple.diagram-audit.json").read_text(encoding="utf-8"))
            self.assertEqual(audit_data["kind"], "pt730-diagram-audit")

    def test_verification_plan_outputs_live_checklist(self) -> None:
        result = self.run_render("verification-plan", str(ROOT / "examples" / "server-dhcp-lan.json"))
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["kind"], "pt730-verification-plan")
        self.assertGreaterEqual(data["counts"]["checks"], 5)
        self.assertGreaterEqual(data["counts"]["services"], 3)
        self.assertIn("pt730_live_term", {check.get("mcp", {}).get("tool") for check in data["checks"]})
        self.assertIn("pt730_live_server_inspect", {check.get("mcp", {}).get("tool") for check in data["checks"]})
        self.assertIn("pt730_live_ftp", {check.get("mcp", {}).get("tool") for check in data["checks"]})
        self.assertTrue(any(check["source"] == "PC_DHCP" and check["target"] == "dhcpdemo.local" for check in data["checks"]))

        markdown = self.run_render("verification-plan", str(ROOT / "examples" / "server-dhcp-lan.json"), "--format", "markdown")
        self.assertEqual(markdown.returncode, 0, markdown.stderr)
        self.assertIn("# Packet Tracer Verification Plan", markdown.stdout)
        self.assertIn("## Service Checks", markdown.stdout)
        self.assertIn("pt-reverse/bin/pt730-ftp PC_DHCP", markdown.stdout)

    def test_verification_plan_includes_bgp_show_commands(self) -> None:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as f:
            json.dump(
                {
                    "devices": [{"name": "R-BGP", "category": "router", "model": "2911"}],
                    "ios_configs": [
                        {
                            "device": "R-BGP",
                            "commands": [
                                "router bgp 65001",
                                "neighbor 203.0.113.2 remote-as 65000",
                                "network 172.16.1.0 mask 255.255.255.192",
                            ],
                        }
                    ],
                },
                f,
            )
            path = f.name
        try:
            result = self.run_render("verification-plan", path)
        finally:
            Path(path).unlink(missing_ok=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        ios_checks = [check for check in data["checks"] if check.get("category") == "ios"]
        self.assertTrue(ios_checks)
        commands = ios_checks[0]["mcp"]["arguments"]["commands"]
        self.assertIn("show ip bgp summary", commands)
        self.assertIn("show ip route bgp", commands)
        self.assertIn("show ip protocols", commands)

    def test_verification_plan_includes_ipv6_routing_show_commands(self) -> None:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as f:
            json.dump(
                {
                    "devices": [{"name": "R6", "category": "router", "model": "2911"}],
                    "ios_configs": [
                        {
                            "device": "R6",
                            "commands": [
                                "ipv6 unicast-routing",
                                "interface GigabitEthernet0/0",
                                "ipv6 address 2001:db8:10::1/64",
                                "ipv6 ospf 10 area 0",
                                "ipv6 rip CAMPUS6 enable",
                                "ipv6 router ospf 10",
                                "router-id 10.255.0.6",
                                "ipv6 router rip CAMPUS6",
                                "redistribute connected",
                                "ipv6 route 2001:db8:ffff::/64 2001:db8:10::fe",
                            ],
                        }
                    ],
                },
                f,
            )
            path = f.name
        try:
            result = self.run_render("verification-plan", path)
        finally:
            Path(path).unlink(missing_ok=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        ios_checks = [check for check in data["checks"] if check.get("category") == "ios"]
        self.assertTrue(ios_checks)
        commands = ios_checks[0]["mcp"]["arguments"]["commands"]
        self.assertIn("show ipv6 interface brief", commands)
        self.assertIn("show ipv6 ospf neighbor", commands)
        self.assertIn("show ipv6 route ospf", commands)
        self.assertIn("show ipv6 route rip", commands)
        self.assertIn("show ipv6 route static", commands)

    def test_verification_plan_includes_management_show_commands(self) -> None:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as f:
            json.dump(
                {
                    "devices": [{"name": "R-MGMT", "category": "router", "model": "2911"}],
                    "ios_configs": [
                        {
                            "device": "R-MGMT",
                            "commands": [
                                "enable secret class",
                                "username admin privilege 15 secret cisco123",
                                "ip domain-name campus.local",
                                "ip ssh version 2",
                                "crypto key generate rsa modulus 1024",
                                "line console 0",
                                "login",
                                "line vty 0 4",
                                "login local",
                                "transport input ssh",
                            ],
                        }
                    ],
                },
                f,
            )
            path = f.name
        try:
            result = self.run_render("verification-plan", path)
        finally:
            Path(path).unlink(missing_ok=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        ios_checks = [check for check in data["checks"] if check.get("category") == "ios"]
        self.assertTrue(ios_checks)
        commands = ios_checks[0]["mcp"]["arguments"]["commands"]
        self.assertIn("show ip ssh", commands)
        self.assertIn("show running-config | include ^username", commands)
        self.assertIn("show running-config | include enable", commands)
        self.assertIn("show running-config | section line con", commands)
        self.assertIn("show running-config | section line vty", commands)

    def test_bundle_report_preset_adds_report_defaults_and_diagram_audit(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir) / "bundle"
            result = self.run_render(
                "bundle",
                str(ROOT / "examples" / "simple-lan.json"),
                "--output-dir",
                str(out_dir),
                "--basename",
                "report-simple",
                "--preset",
                "report",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            manifest = json.loads(result.stdout)
            self.assertEqual(manifest["formats"], ["svg", "drawio", "html", "markdown", "summary", "diagram-audit", "verification-json", "verification-md"])
            self.assertEqual(manifest["options"]["preset"], "report")
            self.assertEqual(manifest["options"]["theme"], "paper")
            self.assertEqual(manifest["options"]["link_labels"], False)
            self.assertEqual(manifest["options"]["group_by"], "auto")
            self.assertEqual(manifest["options"]["title"], "report-simple")
            self.assertEqual(manifest["options"]["legend"], True)
            self.assertEqual(manifest["diagram_audit"], {"ok": True, "exit_code": 0})
            self.assertEqual(manifest["verification_plan"]["ok"], True)
            self.assertGreaterEqual(manifest["verification_plan"]["counts"]["checks"], 1)
            self.assertTrue((out_dir / "report-simple.diagram-audit.json").exists())
            self.assertTrue((out_dir / "report-simple.verification.json").exists())
            self.assertTrue((out_dir / "report-simple.verification.md").exists())

    def test_course_audit_accepts_course_design_plan(self) -> None:
        result = self.run_render("course-audit", str(ROOT / "course-design" / "college-network-topology-pt73-safe.json"))
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertTrue(data["ok"])
        self.assertEqual(data["checks"]["required_vlans"]["missing"], [])
        self.assertEqual(data["checks"]["server_address_space"]["network"], "172.16.1.0/26")
        self.assertEqual(data["checks"]["pc_address_space"]["network"], "192.168.0.0/21")
        self.assertEqual(data["checks"]["representative_hosts"]["configured"], 23)

    def test_course_audit_rejects_missing_course_vlans(self) -> None:
        plan = {
            "devices": [
                {"name": "SW1", "category": "switch", "model": "2960-24TT"},
                {"name": "PC1", "category": "pc", "model": "PC-PT"},
            ],
            "links": [{"a": "SW1", "pa": "FastEthernet0/1", "b": "PC1", "pb": "FastEthernet0", "vlan": 20}],
            "pc_configs": [{"name": "PC1", "ip": "192.168.0.1", "mask": "255.255.255.192", "gateway": "192.168.0.62"}],
        }
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as f:
            json.dump(plan, f)
            path = f.name
        try:
            result = self.run_render("course-audit", path)
        finally:
            Path(path).unlink(missing_ok=True)
        self.assertNotEqual(result.returncode, 0)
        data = json.loads(result.stdout)
        self.assertIn("10", data["checks"]["required_vlans"]["missing"])
        self.assertIn("missing required VLAN links", data["errors"][0]["message"])


if __name__ == "__main__":
    unittest.main()
