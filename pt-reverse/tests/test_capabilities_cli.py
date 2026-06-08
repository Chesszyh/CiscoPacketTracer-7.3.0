#!/usr/bin/env python3
"""Tests for the PT 7.3.0 agent capabilities manifest CLI."""

from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CAPABILITIES = ROOT / "bin" / "pt730-capabilities"


class CapabilitiesCliTest(unittest.TestCase):
    def run_cmd(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(CAPABILITIES), *args],
            cwd=ROOT.parent,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
        )

    def test_default_output_is_machine_readable_manifest(self) -> None:
        result = self.run_cmd()
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["packet_tracer_version"], "7.3.0")
        self.assertIn("pt730-layout", data["offline_tools"])
        self.assertIn("pt730-compose", data["offline_tools"])
        self.assertIn("pt730-mcp", data["offline_tools"])
        self.assertIn("pt730-config-plan", data["offline_tools"])
        self.assertIn("pt730-ip-plan", data["offline_tools"])
        self.assertIn("pt730-render", data["offline_tools"])
        self.assertIn("pt730-models", data["offline_tools"])
        self.assertIn("pt730-pipeline", data["offline_tools"])
        self.assertIn("pt730-ios-template", data["offline_tools"])
        self.assertIn("pt730-safety", data["offline_tools"])
        self.assertIn("pt730-template", data["offline_tools"])
        self.assertIn("pt730-topo", data["live_tools"])
        self.assertIn("dhcpRun(", data["blocked_patterns"])
        self.assertIn("schema", data["ios_template_features"])
        self.assertIn("routed_interfaces", data["ios_template_features"])
        self.assertIn("l3_svis", data["config_plan_features"])
        self.assertIn("static_routes", data["config_plan_features"])
        self.assertIn("config_file_export", data["config_plan_features"])
        self.assertIn("core_interconnect_pool", data["compose_features"])
        self.assertIn("campus", data["pipeline_features"])
        self.assertIn("config_file_export", data["pipeline_features"])
        self.assertIn("drawio_render", data["pipeline_features"])
        self.assertIn("drawio", data["render_features"])
        self.assertIn("lan_star", data["template_features"])
        self.assertIn("router_ring", data["template_features"])
        self.assertIn("tools_call", data["mcp_features"])
        self.assertIn("pt-reverse/bin/pt730-template lan-star --pcs 4 --servers 1 --network 192.168.10.0/24", data["recommended_workflow"])
        self.assertIn("pt-reverse/bin/pt730-template router-ring --routers 4 --interconnect-pool 10.20.0.0/28", data["recommended_workflow"])
        self.assertIn("pt-reverse/bin/pt730-pipeline campus --ip-plan <ip-plan.json> --compose-spec <campus-spec.json> --output-dir <out-dir> --routing rip", data["recommended_workflow"])
        self.assertIn("pt-reverse/bin/pt730-layout <plan.json> --output <layout.json>", data["recommended_workflow"])
        self.assertIn("pt-reverse/bin/pt730-compose campus <campus-spec.json> --output <plan.json>", data["recommended_workflow"])
        self.assertIn("pt-reverse/bin/pt730-config-plan campus <plan.json> --output <configured-plan.json>", data["recommended_workflow"])
        self.assertIn("pt-reverse/bin/pt730-config-plan campus <plan.json> --l3 --routing rip --output <configured-plan.json>", data["recommended_workflow"])
        self.assertIn("pt-reverse/bin/pt730-config-plan campus <plan.json> --l3 --routing static --output <configured-plan.json>", data["recommended_workflow"])
        self.assertIn("pt-reverse/bin/pt730-config-plan export-configs <configured-plan.json> --output-dir <configs-dir>", data["recommended_workflow"])
        self.assertIn("pt-reverse/bin/pt730-ip-plan campus <ip-plan.json> --output <planned-segments.json>", data["recommended_workflow"])
        self.assertIn("pt-reverse/bin/pt730-ios-template schema", data["recommended_workflow"])
        self.assertIn("pt-reverse/bin/pt730-render drawio <plan.json> --output <diagram.drawio>", data["recommended_workflow"])
        self.assertIn("pt-reverse/bin/pt730-mcp --list-tools", data["recommended_workflow"])

    def test_table_output_is_human_readable(self) -> None:
        result = self.run_cmd("--table")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Offline tools", result.stdout)
        self.assertIn("Live tools", result.stdout)


if __name__ == "__main__":
    unittest.main()
