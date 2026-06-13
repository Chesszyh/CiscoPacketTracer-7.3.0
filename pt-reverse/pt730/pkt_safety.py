"""Offline Packet Tracer ``.pkt`` open preflight checks.

Packet Tracer 7.3.0 stores saved files in an opaque binary format in this
environment, so this module is a guardrail rather than a complete parser.  It
blocks known-bad file fingerprints and any risky model names that are visible in
the bytes before a live ``fileOpen()`` call can crash Packet Tracer.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from model_registry import risky_model_notes


KNOWN_BAD_PACKET_HASHES: dict[str, str] = {
    "9d016b690bd6b3a89f4fba308696f21935955ca5ee73966eb414a930fbd3954a": (
        "local crash reproducer reported after adding 3560-24PS multilayer switches; "
        "PT 7.3.0 raised Access violation - no RTTI data"
    ),
}


@dataclass(frozen=True)
class PacketIssue:
    code: str
    message: str
    evidence: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message, "evidence": self.evidence}


@dataclass(frozen=True)
class PacketPreflight:
    path: str
    size: int
    sha256: str
    risky_signatures: tuple[str, ...]
    issues: tuple[PacketIssue, ...]
    warnings: tuple[str, ...]

    @property
    def safe_to_open(self) -> bool:
        return not self.issues

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "size": self.size,
            "sha256": self.sha256,
            "safe_to_open": self.safe_to_open,
            "risky_signatures": list(self.risky_signatures),
            "issues": [issue.to_dict() for issue in self.issues],
            "warnings": list(self.warnings),
        }


def _signature_needles(text: str) -> tuple[bytes, ...]:
    variants = {text, text.lower(), text.upper()}
    needles: list[bytes] = []
    for variant in sorted(variants):
        needles.append(variant.encode("utf-8"))
        needles.append(variant.encode("utf-16-le"))
        needles.append(variant.encode("utf-16-be"))
    return tuple(dict.fromkeys(needles))


def _visible_risky_signatures(data: bytes) -> tuple[str, ...]:
    lowered = data.lower()
    found: list[str] = []
    for model in risky_model_notes():
        for needle in _signature_needles(model):
            haystack = lowered if needle == needle.lower() and b"\x00" not in needle else data
            if needle in haystack:
                found.append(model)
                break
    return tuple(found)


def inspect_packet_file(
    path: Path,
    *,
    known_bad_hashes: dict[str, str] | None = None,
) -> PacketPreflight:
    source = path.expanduser()
    if not source.is_absolute():
        source = Path.cwd() / source
    data = source.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    known_bad = known_bad_hashes if known_bad_hashes is not None else KNOWN_BAD_PACKET_HASHES

    issues: list[PacketIssue] = []
    if digest in known_bad:
        issues.append(PacketIssue("known_bad_hash", known_bad[digest], digest))

    signatures = _visible_risky_signatures(data)
    for model in signatures:
        note = risky_model_notes().get(model, "risky or blocked model")
        issues.append(PacketIssue("risky_model_signature", f"{model}: {note}", model))

    warnings = [
        "Packet Tracer .pkt files are opaque in PT 7.3.0; absence of visible signatures does not prove the file is safe."
    ]
    return PacketPreflight(str(source), len(data), digest, signatures, tuple(issues), tuple(warnings))


def assert_packet_file_safe(path: Path, *, allow_risky: bool = False) -> PacketPreflight:
    report = inspect_packet_file(path)
    if report.issues and not allow_risky:
        details = "; ".join(f"{issue.code}: {issue.message}" for issue in report.issues)
        raise RuntimeError(
            f"refusing to open Packet Tracer file before live PT contact: {details}. "
            "Pass --allow-risky only for a supervised recovery attempt."
        )
    return report
