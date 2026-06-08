#!/usr/bin/env python3
"""Tests for end-to-end offline campus pipeline generation."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PIPELINE = ROOT / "bin" / "pt730-pipeline"


class PipelineCliTest(unittest.TestCase):
    def test_schema_describes_compact_option(self) -> None:
        result = subprocess.run(
            [str(PIPELINE), "schema"],
            cwd=ROOT.parent,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertIn("--compact", data["campus"]["optional"])

    def test_campus_pipeline_generates_agent_ready_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir) / "out"
            result = subprocess.run(
                [
                    str(PIPELINE),
                    "campus",
                    "--ip-plan",
                    str(ROOT / "examples" / "ip-plan-campus.json"),
                    "--compose-spec",
                    str(ROOT / "examples" / "compose-campus.json"),
                    "--output-dir",
                    str(out_dir),
                    "--routing",
                    "rip",
                ],
                cwd=ROOT.parent,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            manifest = json.loads(result.stdout)
            self.assertEqual(manifest["kind"], "pt730-campus-pipeline")
            self.assertEqual(manifest["routing"], "rip")
            self.assertTrue(manifest["safety"]["ok"])

            expected = [
                "ip-plan.json",
                "topology.composed.json",
                "topology.configured.json",
                "topology.layout.json",
                "topology.summary.json",
                "topology.md",
                "topology.svg",
                "topology.html",
                "topology.drawio",
                "safety.json",
                "manifest.json",
                "configs/MLS1.cfg",
            ]
            for relative in expected:
                self.assertTrue((out_dir / relative).exists(), relative)
            self.assertEqual(manifest["artifacts"]["svg"], "topology.svg")
            self.assertEqual(manifest["artifacts"]["html"], "topology.html")
            self.assertEqual(manifest["artifacts"]["drawio"], "topology.drawio")
            self.assertIn("<svg", (out_dir / "topology.svg").read_text(encoding="utf-8"))
            self.assertIn("<!doctype html>", (out_dir / "topology.html").read_text(encoding="utf-8"))
            self.assertIn("<mxfile", (out_dir / "topology.drawio").read_text(encoding="utf-8"))

            layout = json.loads((out_dir / "topology.layout.json").read_text(encoding="utf-8"))
            self.assertGreater(len(layout["devices"]), 0)
            self.assertGreater(len(layout["ios_configs"]), 0)
            self.assertIn("router rip", (out_dir / "configs" / "MLS1.cfg").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
