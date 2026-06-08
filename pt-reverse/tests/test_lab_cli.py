#!/usr/bin/env python3
"""Tests for one-spec offline lab bundle generation."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT / "bin" / "pt730-lab"


class LabCliTest(unittest.TestCase):
    def run_lab(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(LAB), *args],
            cwd=ROOT.parent,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=60,
            check=False,
        )

    def write_spec(self, tmpdir: str, spec: dict) -> Path:
        path = Path(tmpdir) / "lab-spec.json"
        path.write_text(json.dumps(spec), encoding="utf-8")
        return path

    def test_schema_describes_templates_and_outputs(self) -> None:
        result = self.run_lab("schema")
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertIn("template", data["commands"])
        self.assertIn("plan", data["commands"])
        self.assertIn("report", data["commands"])
        self.assertIn("enterprise-edge", data["templates"])
        self.assertIn("campus_vlans", data["templates"]["enterprise-edge"]["options"])
        self.assertIn("render/<basename>.*", data["template"]["outputs"])
        self.assertIn("--output", data["report"]["optional"])
        self.assertIn("--basename", data["plan"]["optional"])
        self.assertIn("--title", data["plan"]["optional"])
        self.assertIn("--legend", data["plan"]["optional"])
        self.assertEqual(data["template"]["render_options"]["formats"], ["svg", "drawio", "html", "markdown", "summary"])
        self.assertIn("preset", data["template"]["render_options"])
        self.assertIn("title", data["template"]["render_options"])
        self.assertIn("legend", data["template"]["render_options"])

    def test_template_generates_agent_ready_lab_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            spec = self.write_spec(
                tmpdir,
                {
                    "name": "enterprise-demo",
                    "template": "enterprise-edge",
                    "template_options": {
                        "name": "ENT",
                        "campus_vlans": 2,
                        "hosts_per_vlan": 1,
                        "campus_servers": 2,
                        "branches": 1,
                        "branch_hosts": 1,
                        "dmz_servers": 1,
                        "internet_hosts": 1,
                        "routing": "ospf",
                        "layout_style": "campus",
                    },
                    "render": {
                        "basename": "enterprise-demo",
                        "formats": ["svg", "drawio", "html", "markdown", "summary"],
                        "theme": "paper",
                        "group_by": "auto",
                        "title": "Enterprise Demo",
                        "legend": True,
                    },
                    "export_configs": True,
                },
            )
            out_dir = Path(tmpdir) / "lab"
            result = self.run_lab("template", str(spec), "--output-dir", str(out_dir))
            self.assertEqual(result.returncode, 0, result.stderr)
            manifest = json.loads(result.stdout)
            self.assertEqual(manifest["kind"], "pt730-lab-template-bundle")
            self.assertEqual(manifest["template"], "enterprise-edge")
            self.assertTrue(manifest["safety"]["ok"])
            self.assertEqual(manifest["render_bundle"]["formats"], ["svg", "drawio", "html", "markdown", "summary"])
            self.assertEqual(manifest["render_bundle"]["options"]["title"], "Enterprise Demo")
            self.assertEqual(manifest["render_bundle"]["options"]["legend"], True)
            self.assertGreater(manifest["config_files"]["count"], 0)

            expected = [
                "topology.json",
                "safety.json",
                "manifest.json",
                "render/enterprise-demo.svg",
                "render/enterprise-demo.drawio",
                "render/enterprise-demo.html",
                "render/enterprise-demo.md",
                "render/enterprise-demo.summary.json",
                "render/enterprise-demo.manifest.json",
                "configs/R-ENT-EDGE.cfg",
            ]
            for relative in expected:
                self.assertTrue((out_dir / relative).exists(), relative)

            topology = json.loads((out_dir / "topology.json").read_text(encoding="utf-8"))
            self.assertEqual(topology["metadata"]["lab_bundle"]["name"], "enterprise-demo")
            self.assertEqual(topology["metadata"]["lab_bundle"]["template"], "enterprise-edge")
            self.assertIn("Enterprise Demo", (out_dir / "render" / "enterprise-demo.svg").read_text(encoding="utf-8"))
            self.assertIn("Legend", (out_dir / "render" / "enterprise-demo.html").read_text(encoding="utf-8"))
            self.assertIn("router ospf 1", (out_dir / "configs" / "R-ENT-EDGE.cfg").read_text(encoding="utf-8"))

    def test_template_can_limit_render_formats(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            spec = self.write_spec(
                tmpdir,
                {
                    "template": "lan-star",
                    "template_options": {"name": "SMALL", "pcs": 1, "servers": 1},
                    "render": {"basename": "small", "formats": ["summary"]},
                    "export_configs": False,
                },
            )
            out_dir = Path(tmpdir) / "lab"
            result = self.run_lab("template", str(spec), "--output-dir", str(out_dir))
            self.assertEqual(result.returncode, 0, result.stderr)
            manifest = json.loads(result.stdout)
            self.assertEqual(manifest["render_bundle"]["formats"], ["summary"])
            self.assertEqual(manifest["config_files"]["count"], 0)
            self.assertTrue((out_dir / "render" / "small.summary.json").exists())
            self.assertFalse((out_dir / "render" / "small.svg").exists())
            self.assertFalse((out_dir / "configs").exists())

    def test_template_report_preset_sets_report_render_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            spec = self.write_spec(
                tmpdir,
                {
                    "name": "preset-demo",
                    "template": "lan-star",
                    "template_options": {"name": "PRESET", "pcs": 1, "servers": 1},
                    "render": {"preset": "report"},
                    "export_configs": False,
                },
            )
            out_dir = Path(tmpdir) / "lab"
            result = self.run_lab("template", str(spec), "--output-dir", str(out_dir))
            self.assertEqual(result.returncode, 0, result.stderr)
            manifest = json.loads(result.stdout)
            self.assertEqual(manifest["render_bundle"]["formats"], ["svg", "drawio", "html", "markdown", "summary", "diagram-audit", "verification-json", "verification-md"])
            self.assertEqual(manifest["render_bundle"]["options"]["preset"], "report")
            self.assertEqual(manifest["render_bundle"]["options"]["theme"], "paper")
            self.assertEqual(manifest["render_bundle"]["options"]["link_labels"], False)
            self.assertEqual(manifest["render_bundle"]["options"]["group_by"], "auto")
            self.assertEqual(manifest["render_bundle"]["options"]["title"], "preset-demo")
            self.assertEqual(manifest["render_bundle"]["options"]["legend"], True)
            self.assertTrue((out_dir / "render" / "preset-demo.diagram-audit.json").exists())
            self.assertTrue((out_dir / "render" / "preset-demo.verification.json").exists())
            self.assertTrue((out_dir / "render" / "preset-demo.verification.md").exists())
            self.assertEqual(manifest["render_bundle"]["verification_plan"]["ok"], True)

    def test_plan_generates_lab_bundle_from_existing_topology_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir) / "plan-lab"
            result = self.run_lab(
                "plan",
                "pt-reverse/examples/two-router-serial-configured.json",
                "--output-dir",
                str(out_dir),
                "--name",
                "serial-lab",
                "--basename",
                "serial",
                "--formats",
                "svg,summary",
                "--group-by",
                "category",
                "--title",
                "Serial Lab",
                "--legend",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            manifest = json.loads(result.stdout)
            self.assertEqual(manifest["kind"], "pt730-lab-plan-bundle")
            self.assertEqual(manifest["name"], "serial-lab")
            self.assertEqual(manifest["render_bundle"]["formats"], ["svg", "summary"])
            self.assertEqual(manifest["render_bundle"]["options"]["title"], "Serial Lab")
            self.assertEqual(manifest["render_bundle"]["options"]["legend"], True)
            self.assertTrue(manifest["safety"]["ok"])
            self.assertEqual(manifest["config_files"]["count"], 2)
            self.assertTrue((out_dir / "topology.json").exists())
            self.assertTrue((out_dir / "safety.json").exists())
            self.assertTrue((out_dir / "render" / "serial.svg").exists())
            self.assertTrue((out_dir / "render" / "serial.summary.json").exists())
            self.assertTrue((out_dir / "configs" / "R_AUTO1.cfg").exists())
            topology = json.loads((out_dir / "topology.json").read_text(encoding="utf-8"))
            self.assertEqual(topology["metadata"]["lab_bundle"]["name"], "serial-lab")
            self.assertEqual(topology["metadata"]["lab_bundle"]["plan"], "pt-reverse/examples/two-router-serial-configured.json")

    def test_plan_report_preset_sets_report_render_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir) / "plan-lab"
            result = self.run_lab(
                "plan",
                "pt-reverse/examples/two-router-serial-configured.json",
                "--output-dir",
                str(out_dir),
                "--basename",
                "serial-report",
                "--preset",
                "report",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            manifest = json.loads(result.stdout)
            self.assertEqual(manifest["render_bundle"]["formats"], ["svg", "drawio", "html", "markdown", "summary", "diagram-audit", "verification-json", "verification-md"])
            self.assertEqual(manifest["render_bundle"]["options"]["preset"], "report")
            self.assertEqual(manifest["render_bundle"]["options"]["theme"], "paper")
            self.assertEqual(manifest["render_bundle"]["options"]["link_labels"], False)
            self.assertEqual(manifest["render_bundle"]["options"]["group_by"], "auto")
            self.assertEqual(manifest["render_bundle"]["options"]["title"], "serial-report")
            self.assertEqual(manifest["render_bundle"]["options"]["legend"], True)
            self.assertTrue((out_dir / "render" / "serial-report.diagram-audit.json").exists())
            self.assertTrue((out_dir / "render" / "serial-report.verification.json").exists())
            self.assertTrue((out_dir / "render" / "serial-report.verification.md").exists())
            self.assertEqual(manifest["render_bundle"]["verification_plan"]["counts"]["ios"], 2)

    def test_report_generates_coursework_deliverable_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir) / "plan-lab"
            bundle = self.run_lab(
                "plan",
                "pt-reverse/examples/two-router-serial-configured.json",
                "--output-dir",
                str(out_dir),
                "--basename",
                "serial",
                "--formats",
                "svg,summary,diagram-audit",
                "--title",
                "Serial Lab",
                "--legend",
            )
            self.assertEqual(bundle.returncode, 0, bundle.stderr)

            result = self.run_lab("report", str(out_dir / "manifest.json"), "--title", "Serial Deliverable")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("# Serial Deliverable", result.stdout)
            self.assertIn("## Artifact Checklist", result.stdout)
            self.assertIn("serial.svg", result.stdout)
            self.assertIn("R_AUTO1.cfg", result.stdout)
            self.assertIn("Suggested Recording Checklist", result.stdout)

            report_bundle = self.run_lab(
                "plan",
                "pt-reverse/examples/two-router-serial-configured.json",
                "--output-dir",
                str(out_dir / "report-preset"),
                "--basename",
                "serial-report",
                "--preset",
                "report",
            )
            self.assertEqual(report_bundle.returncode, 0, report_bundle.stderr)
            report_result = self.run_lab("report", str(out_dir / "report-preset" / "manifest.json"))
            self.assertEqual(report_result.returncode, 0, report_result.stderr)
            self.assertIn("## Verification Plan", report_result.stdout)
            self.assertIn("serial-report.verification.md", report_result.stdout)
            self.assertIn("Verification plan", report_result.stdout)

            report_path = out_dir / "deliverable.md"
            written = self.run_lab("report", str(out_dir / "manifest.json"), "--output", str(report_path))
            self.assertEqual(written.returncode, 0, written.stderr)
            payload = json.loads(written.stdout)
            self.assertEqual(payload["kind"], "pt730-lab-report")
            self.assertTrue(report_path.exists())
            self.assertIn("Packet Tracer lab bundle", report_path.read_text(encoding="utf-8"))

    def test_template_rejects_unknown_template(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            spec = self.write_spec(tmpdir, {"template": "not-real"})
            result = self.run_lab("template", str(spec), "--output-dir", str(Path(tmpdir) / "lab"))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unknown template", result.stderr)

    def test_template_rejects_unknown_template_option(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            spec = self.write_spec(tmpdir, {"template": "lan-star", "template_options": {"bogus": 1}})
            result = self.run_lab("template", str(spec), "--output-dir", str(Path(tmpdir) / "lab"))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unknown option", result.stderr)


if __name__ == "__main__":
    unittest.main()
