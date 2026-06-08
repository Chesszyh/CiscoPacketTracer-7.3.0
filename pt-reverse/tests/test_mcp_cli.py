#!/usr/bin/env python3
"""Tests for the PT 7.3.0 MCP stdio wrapper."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MCP = ROOT / "bin" / "pt730-mcp"


class McpCliTest(unittest.TestCase):
    def run_mcp(self, messages: list[dict]) -> list[dict]:
        payload = "\n".join(json.dumps(message) for message in messages) + "\n"
        result = subprocess.run(
            [str(MCP)],
            cwd=ROOT.parent,
            input=payload,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=60,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return [json.loads(line) for line in result.stdout.splitlines() if line.strip()]

    def test_initialize_and_tools_list(self) -> None:
        responses = self.run_mcp(
            [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            ]
        )
        self.assertEqual(responses[0]["result"]["capabilities"]["tools"]["listChanged"], False)
        tools = responses[1]["result"]["tools"]
        names = [tool["name"] for tool in tools]
        self.assertIn("pt730_render", names)
        self.assertIn("pt730_pipeline_campus", names)
        self.assertIn("pt730_template_lan_star", names)
        self.assertIn("pt730_live_apply", names)
        self.assertIn("pt730_live_query", names)
        self.assertIn("pt730_live_count", names)
        self.assertIn("pt730_live_save_as", names)
        self.assertIn("pt730_live_ios", names)
        self.assertIn("pt730_live_pc_static", names)
        self.assertIn("pt730_live_term", names)
        self.assertIn("pt730_live_ping", names)
        self.assertIn("pt730_live_server_inspect", names)
        render = next(tool for tool in tools if tool["name"] == "pt730_render")
        self.assertIn("format", render["inputSchema"]["required"])
        live_count = next(tool for tool in tools if tool["name"] == "pt730_live_count")
        self.assertIn("allow_live", live_count["inputSchema"]["required"])

    def test_tools_call_render_summary_returns_text_and_structured_content(self) -> None:
        responses = self.run_mcp(
            [
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {
                        "name": "pt730_render",
                        "arguments": {
                            "format": "summary",
                            "plan": "pt-reverse/examples/simple-lan.json",
                        },
                    },
                }
            ]
        )
        result = responses[0]["result"]
        self.assertEqual(result["isError"], False)
        self.assertIn('"devices": 3', result["content"][0]["text"])
        self.assertEqual(result["structuredContent"]["exitCode"], 0)
        self.assertIn("192.168.50.0/24", result["structuredContent"]["stdout"])

    def test_tools_call_pipeline_generates_manifest_and_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir) / "mcp-pipeline"
            responses = self.run_mcp(
                [
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/call",
                        "params": {
                            "name": "pt730_pipeline_campus",
                            "arguments": {
                                "ip_plan": "pt-reverse/examples/ip-plan-campus.json",
                                "compose_spec": "pt-reverse/examples/compose-campus.json",
                                "output_dir": str(out_dir),
                                "routing": "rip",
                            },
                        },
                    }
                ]
            )
            result = responses[0]["result"]
            self.assertEqual(result["isError"], False)
            manifest = json.loads(result["structuredContent"]["stdout"])
            self.assertEqual(manifest["kind"], "pt730-campus-pipeline")
            self.assertEqual(manifest["artifacts"]["drawio"], "topology.drawio")
            self.assertTrue((out_dir / "topology.drawio").exists())

    def test_live_tool_without_allow_live_returns_protocol_error(self) -> None:
        responses = self.run_mcp(
            [
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": "pt730_live_count", "arguments": {}},
                }
            ]
        )
        self.assertEqual(responses[0]["error"]["code"], -32602)
        self.assertIn("allow_live", responses[0]["error"]["message"])

    def test_live_device_tool_without_allow_live_or_dry_run_returns_error(self) -> None:
        responses = self.run_mcp(
            [
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {
                        "name": "pt730_live_ios",
                        "arguments": {"device": "R1", "commands": ["show ip interface brief"]},
                    },
                }
            ]
        )
        self.assertEqual(responses[0]["error"]["code"], -32602)
        self.assertIn("allow_live", responses[0]["error"]["message"])

    def test_live_device_tool_dry_run_returns_command_preview(self) -> None:
        responses = self.run_mcp(
            [
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {
                        "name": "pt730_live_ios",
                        "arguments": {
                            "device": "R1",
                            "commands": ["show ip interface brief"],
                            "dry_run": True,
                        },
                    },
                }
            ]
        )
        result = responses[0]["result"]
        self.assertEqual(result["isError"], False)
        self.assertIn("pt730-ios", result["content"][0]["text"])
        self.assertIn("--cmd", result["structuredContent"]["command"])
        self.assertEqual(result["structuredContent"]["dryRun"], True)

    def test_live_pc_static_dry_run_returns_command_preview(self) -> None:
        responses = self.run_mcp(
            [
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {
                        "name": "pt730_live_pc_static",
                        "arguments": {
                            "device": "PC1",
                            "ip": "192.168.1.10",
                            "mask": "255.255.255.0",
                            "gateway": "192.168.1.1",
                            "dry_run": True,
                        },
                    },
                }
            ]
        )
        command = responses[0]["result"]["structuredContent"]["command"]
        self.assertIn("pt730-pc", command[0])
        self.assertIn("static", command)
        self.assertIn("192.168.1.10", command)

    def test_live_terminal_ping_and_server_dry_run_return_command_previews(self) -> None:
        responses = self.run_mcp(
            [
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {
                        "name": "pt730_live_term",
                        "arguments": {
                            "device": "PC1",
                            "commands": ["ping 192.168.1.1"],
                            "wait": 8,
                            "expect": "Lost = 0",
                            "dry_run": True,
                        },
                    },
                },
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "pt730_live_ping",
                        "arguments": {
                            "device": "R1",
                            "target": "10.0.0.2",
                            "dry_run": True,
                        },
                    },
                },
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": "pt730_live_server_inspect",
                        "arguments": {
                            "device": "SRV1",
                            "dry_run": True,
                        },
                    },
                },
            ]
        )
        term_command = responses[0]["result"]["structuredContent"]["command"]
        ping_command = responses[1]["result"]["structuredContent"]["command"]
        server_command = responses[2]["result"]["structuredContent"]["command"]
        self.assertIn("pt730-term", term_command[0])
        self.assertIn("--expect", term_command)
        self.assertIn("pt730-ping", ping_command[0])
        self.assertIn("10.0.0.2", ping_command)
        self.assertIn("pt730-server", server_command[0])
        self.assertIn("inspect", server_command)

    def test_live_apply_dry_run_is_allowed_without_live_bridge(self) -> None:
        responses = self.run_mcp(
            [
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {
                        "name": "pt730_live_apply",
                        "arguments": {
                            "plan": "pt-reverse/examples/simple-lan.json",
                            "dry_run": True,
                        },
                    },
                }
            ]
        )
        result = responses[0]["result"]
        self.assertEqual(result["isError"], False)
        self.assertIn('"devices": 3', result["content"][0]["text"])
        self.assertIn("--dry-run", result["structuredContent"]["command"])

    def test_unknown_tool_returns_protocol_error(self) -> None:
        responses = self.run_mcp(
            [
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": "pt730_not_a_tool", "arguments": {}},
                }
            ]
        )
        self.assertEqual(responses[0]["error"]["code"], -32602)
        self.assertIn("Unknown tool", responses[0]["error"]["message"])


if __name__ == "__main__":
    unittest.main()
