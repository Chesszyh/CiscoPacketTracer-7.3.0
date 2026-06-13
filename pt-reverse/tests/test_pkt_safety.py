#!/usr/bin/env python3
"""Tests for offline Packet Tracer .pkt preflight checks."""

from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pt730"))

from pkt_safety import inspect_packet_file  # noqa: E402


class PacketSafetyTest(unittest.TestCase):
    def test_detects_visible_risky_model_signature(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            pkt = Path(tmpdir) / "visible-risk.pkt"
            pkt.write_bytes(b"header\x003560-24PS\x00payload")

            report = inspect_packet_file(pkt)

        self.assertFalse(report.safe_to_open)
        self.assertIn("3560-24PS", report.risky_signatures)
        self.assertEqual(report.issues[0].code, "risky_model_signature")

    def test_detects_known_bad_hash_with_injected_registry(self) -> None:
        payload = b"opaque Packet Tracer packet"
        digest = hashlib.sha256(payload).hexdigest()
        with tempfile.TemporaryDirectory() as tmpdir:
            pkt = Path(tmpdir) / "opaque.pkt"
            pkt.write_bytes(payload)

            report = inspect_packet_file(pkt, known_bad_hashes={digest: "test crash reproducer"})

        self.assertFalse(report.safe_to_open)
        self.assertEqual(report.issues[0].code, "known_bad_hash")
        self.assertEqual(report.issues[0].evidence, digest)


if __name__ == "__main__":
    unittest.main()
