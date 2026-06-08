#!/usr/bin/env python3
"""Tests for offline topology auto-layout."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
LAYOUT = ROOT / "bin" / "pt730-layout"
RENDER = ROOT / "bin" / "pt730-render"
SAFETY = ROOT / "bin" / "pt730-safety"


class LayoutCliTest(unittest.TestCase):
    def run_layout(self, plan: dict[str, Any], *args: str) -> subprocess.CompletedProcess[str]:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as f:
            json.dump(plan, f)
            path = f.name
        try:
            return subprocess.run(
                [str(LAYOUT), path, *args],
                cwd=ROOT.parent,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
                check=False,
            )
        finally:
            Path(path).unlink(missing_ok=True)

    def test_lan_layout_adds_coordinates_and_preserves_plan_fields(self) -> None:
        plan = {
            "devices": [
                {"name": "R1", "category": "router", "model": "2911"},
                {"name": "SW1", "category": "switch", "model": "2960-24TT"},
                {"name": "PC1", "category": "pc", "model": "PC-PT"},
                {"name": "PC2", "category": "pc", "model": "PC-PT"},
            ],
            "links": [
                {"a": "R1", "pa": "GigabitEthernet0/0", "b": "SW1", "pb": "FastEthernet0/1", "cable": "straight"},
                {"a": "SW1", "pa": "FastEthernet0/2", "b": "PC1", "pb": "FastEthernet0", "cable": "straight"},
                {"a": "SW1", "pa": "FastEthernet0/3", "b": "PC2", "pb": "FastEthernet0", "cable": "straight"},
            ],
            "pc_configs": [{"name": "PC1", "ip": "192.168.1.10", "mask": "255.255.255.0", "gateway": "192.168.1.1"}],
        }
        result = self.run_layout(plan, "--style", "lan")
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["links"], plan["links"])
        self.assertEqual(data["pc_configs"], plan["pc_configs"])
        coords = {device["name"]: (device.get("x"), device.get("y")) for device in data["devices"]}
        self.assertEqual(set(coords), {"R1", "SW1", "PC1", "PC2"})
        for x, y in coords.values():
            self.assertIsInstance(x, int)
            self.assertIsInstance(y, int)
            self.assertGreaterEqual(x, 0)
            self.assertGreaterEqual(y, 0)
        self.assertLess(coords["R1"][0], coords["SW1"][0])
        self.assertLess(coords["SW1"][1], coords["PC1"][1])
        self.assertLess(coords["SW1"][1], coords["PC2"][1])

    def test_output_file_can_be_rendered_and_safety_checked(self) -> None:
        plan = {
            "devices": [
                {"name": "SW1", "category": "switch", "model": "2960-24TT"},
                {"name": "PC1", "category": "pc", "model": "PC-PT"},
            ],
            "links": [{"a": "SW1", "pa": "FastEthernet0/1", "b": "PC1", "pb": "FastEthernet0", "cable": "straight"}],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            in_path = Path(tmpdir) / "plan.json"
            out_path = Path(tmpdir) / "layout.json"
            in_path.write_text(json.dumps(plan), encoding="utf-8")
            result = subprocess.run(
                [str(LAYOUT), str(in_path), "--output", str(out_path)],
                cwd=ROOT.parent,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "")
            self.assertTrue(out_path.exists())

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
            render = subprocess.run(
                [str(RENDER), "summary", str(out_path)],
                cwd=ROOT.parent,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
                check=False,
            )
            self.assertEqual(render.returncode, 0, render.stderr)
            self.assertEqual(json.loads(render.stdout)["counts"]["devices"], 2)

    def test_preserve_existing_keeps_manual_coordinates(self) -> None:
        plan = {
            "devices": [
                {"name": "SW1", "category": "switch", "model": "2960-24TT", "x": 777, "y": 888},
                {"name": "PC1", "category": "pc", "model": "PC-PT"},
            ],
            "links": [{"a": "SW1", "pa": "FastEthernet0/1", "b": "PC1", "pb": "FastEthernet0", "cable": "straight"}],
        }
        result = self.run_layout(plan, "--preserve-existing")
        self.assertEqual(result.returncode, 0, result.stderr)
        devices = {device["name"]: device for device in json.loads(result.stdout)["devices"]}
        self.assertEqual((devices["SW1"]["x"], devices["SW1"]["y"]), (777, 888))
        self.assertIn("x", devices["PC1"])
        self.assertIn("y", devices["PC1"])

    def test_campus_layout_places_servers_above_core_and_hosts_below_access(self) -> None:
        plan = {
            "devices": [
                {"name": "MLS1", "category": "switch", "model": "2960-24TT"},
                {"name": "MLS2", "category": "switch", "model": "2960-24TT"},
                {"name": "SW-SRV", "category": "switch", "model": "2960-24TT"},
                {"name": "WEB-SRV", "category": "server", "model": "Server-PT"},
                {"name": "DNS-SRV", "category": "server", "model": "Server-PT"},
                {"name": "SW-OFFICE", "category": "switch", "model": "2960-24TT"},
                {"name": "PC-OFFICE-1", "category": "pc", "model": "PC-PT"},
                {"name": "PC-OFFICE-2", "category": "pc", "model": "PC-PT"},
                {"name": "RESEARCH-SW", "category": "switch", "model": "2960-24TT"},
                {"name": "PC-RESEARCH-1", "category": "pc", "model": "PC-PT"},
            ],
            "links": [
                {"a": "MLS1", "pa": "FastEthernet0/1", "b": "MLS2", "pb": "FastEthernet0/1", "cable": "cross"},
                {"a": "MLS1", "pa": "FastEthernet0/2", "b": "SW-SRV", "pb": "FastEthernet0/1", "cable": "cross"},
                {"a": "SW-SRV", "pa": "FastEthernet0/2", "b": "WEB-SRV", "pb": "FastEthernet0", "cable": "straight"},
                {"a": "SW-SRV", "pa": "FastEthernet0/3", "b": "DNS-SRV", "pb": "FastEthernet0", "cable": "straight"},
                {"a": "MLS2", "pa": "FastEthernet0/2", "b": "SW-OFFICE", "pb": "FastEthernet0/1", "cable": "cross"},
                {"a": "SW-OFFICE", "pa": "FastEthernet0/2", "b": "PC-OFFICE-1", "pb": "FastEthernet0", "cable": "straight"},
                {"a": "SW-OFFICE", "pa": "FastEthernet0/3", "b": "PC-OFFICE-2", "pb": "FastEthernet0", "cable": "straight"},
                {"a": "MLS2", "pa": "FastEthernet0/4", "b": "RESEARCH-SW", "pb": "FastEthernet0/1", "cable": "cross"},
                {"a": "RESEARCH-SW", "pa": "FastEthernet0/2", "b": "PC-RESEARCH-1", "pb": "FastEthernet0", "cable": "straight"},
            ],
        }
        result = self.run_layout(plan, "--style", "campus")
        self.assertEqual(result.returncode, 0, result.stderr)
        devices = {device["name"]: device for device in json.loads(result.stdout)["devices"]}
        server_y = min(devices[name]["y"] for name in ("WEB-SRV", "DNS-SRV"))
        server_switch_y = devices["SW-SRV"]["y"]
        core_y = min(devices[name]["y"] for name in ("MLS1", "MLS2"))
        access_y = devices["SW-OFFICE"]["y"]
        research_switch_y = devices["RESEARCH-SW"]["y"]
        pc_y = min(devices[name]["y"] for name in ("PC-OFFICE-1", "PC-OFFICE-2"))
        self.assertLess(server_y, core_y)
        self.assertLess(server_y, server_switch_y)
        self.assertLess(server_switch_y, core_y)
        self.assertGreater(access_y, core_y)
        self.assertGreater(research_switch_y, core_y)
        self.assertGreater(pc_y, access_y)
        self.assertGreater(devices["PC-RESEARCH-1"]["y"], research_switch_y)
        self.assertEqual(len({(device["x"], device["y"]) for device in devices.values()}), len(devices))

    def test_ring_layout_keeps_router_ring_inside_canvas(self) -> None:
        plan = {
            "devices": [
                {"name": f"R{i}", "category": "router", "model": "2911"}
                for i in range(1, 5)
            ],
            "links": [
                {"a": "R1", "pa": "GigabitEthernet0/0", "b": "R2", "pb": "GigabitEthernet0/0", "cable": "cross"},
                {"a": "R2", "pa": "GigabitEthernet0/1", "b": "R3", "pb": "GigabitEthernet0/0", "cable": "cross"},
                {"a": "R3", "pa": "GigabitEthernet0/1", "b": "R4", "pb": "GigabitEthernet0/0", "cable": "cross"},
                {"a": "R4", "pa": "GigabitEthernet0/1", "b": "R1", "pb": "GigabitEthernet0/1", "cable": "cross"},
            ],
        }
        result = self.run_layout(plan, "--style", "ring", "--canvas-width", "900", "--canvas-height", "700")
        self.assertEqual(result.returncode, 0, result.stderr)
        coords = [(device["x"], device["y"]) for device in json.loads(result.stdout)["devices"]]
        self.assertEqual(len(set(coords)), 4)
        for x, y in coords:
            self.assertGreaterEqual(x, 0)
            self.assertLessEqual(x, 900)
            self.assertGreaterEqual(y, 0)
            self.assertLessEqual(y, 700)

    def test_ring_layout_keeps_second_level_site_fanout_near_site_switches(self) -> None:
        plan = {
            "devices": [
                {"name": "R1", "category": "router", "model": "2911"},
                {"name": "R2", "category": "router", "model": "2911"},
                {"name": "R3", "category": "router", "model": "2911"},
                {"name": "SW1", "category": "switch", "model": "2960-24TT"},
                {"name": "SW2", "category": "switch", "model": "2960-24TT"},
                {"name": "SW3", "category": "switch", "model": "2960-24TT"},
                {"name": "PC1", "category": "pc", "model": "PC-PT"},
                {"name": "PC2", "category": "pc", "model": "PC-PT"},
                {"name": "PC3", "category": "pc", "model": "PC-PT"},
            ],
            "links": [
                {"a": "R1", "pa": "Serial0/0/0", "b": "R2", "pb": "Serial0/0/1", "cable": "serial"},
                {"a": "R2", "pa": "Serial0/0/0", "b": "R3", "pb": "Serial0/0/1", "cable": "serial"},
                {"a": "R3", "pa": "Serial0/0/0", "b": "R1", "pb": "Serial0/0/1", "cable": "serial"},
                {"a": "R1", "pa": "GigabitEthernet0/0", "b": "SW1", "pb": "FastEthernet0/1", "cable": "straight"},
                {"a": "R2", "pa": "GigabitEthernet0/0", "b": "SW2", "pb": "FastEthernet0/1", "cable": "straight"},
                {"a": "R3", "pa": "GigabitEthernet0/0", "b": "SW3", "pb": "FastEthernet0/1", "cable": "straight"},
                {"a": "SW1", "pa": "FastEthernet0/2", "b": "PC1", "pb": "FastEthernet0", "cable": "straight"},
                {"a": "SW2", "pa": "FastEthernet0/2", "b": "PC2", "pb": "FastEthernet0", "cable": "straight"},
                {"a": "SW3", "pa": "FastEthernet0/2", "b": "PC3", "pb": "FastEthernet0", "cable": "straight"},
            ],
        }
        result = self.run_layout(plan, "--style", "ring", "--canvas-width", "900", "--canvas-height", "700")
        self.assertEqual(result.returncode, 0, result.stderr)
        devices = {device["name"]: device for device in json.loads(result.stdout)["devices"]}
        self.assertGreater(abs(devices["PC2"]["x"] - devices["SW2"]["x"]), 0)
        self.assertLess(abs(devices["PC2"]["x"] - devices["SW2"]["x"]), abs(devices["PC2"]["x"] - devices["SW1"]["x"]))
        self.assertLess(abs(devices["PC3"]["x"] - devices["SW3"]["x"]), abs(devices["PC3"]["x"] - devices["SW1"]["x"]))
        for device in devices.values():
            self.assertGreaterEqual(device["x"], 0)
            self.assertLessEqual(device["x"], 900)
            self.assertGreaterEqual(device["y"], 0)
            self.assertLessEqual(device["y"], 700)


if __name__ == "__main__":
    unittest.main()
