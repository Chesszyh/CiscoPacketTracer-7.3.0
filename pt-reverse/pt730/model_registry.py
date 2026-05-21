"""PT 7.3.0 model safety registry.

Statuses intentionally separate known-good local evidence from models that are
only common in Packet Tracer catalogs.  Unverified models need one-at-a-time
manual probing before they can be promoted to safe automation defaults.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelRecord:
    model: str
    category: str
    status: str
    note: str
    type_id: int | None = None

    @property
    def unattended_safe(self) -> bool:
        return self.status == "safe"


COMMON_MODELS: tuple[ModelRecord, ...] = (
    ModelRecord("2911", "router", "safe", "live verified locally with GigabitEthernet ports and HWIC-2T serial module", 0),
    ModelRecord("2960-24TT", "switch", "safe", "live verified locally as stable L2 switch", 1),
    ModelRecord("PC-PT", "pc", "safe", "live verified locally with FastEthernet0 and static pc_configs", 8),
    ModelRecord("Server-PT", "server", "safe", "live verified locally with FastEthernet0, static IP, and server services", 9),
    ModelRecord("1841", "router", "unverified", "common router; not yet live-verified in this PT 7.3.0 Wine setup", 0),
    ModelRecord("1941", "router", "unverified", "common router; not yet live-verified in this PT 7.3.0 Wine setup", 0),
    ModelRecord("2901", "router", "unverified", "common router; not yet live-verified in this PT 7.3.0 Wine setup", 0),
    ModelRecord("4321", "router", "unverified", "common ISR router; not yet live-verified in this PT 7.3.0 Wine setup", 0),
    ModelRecord("4331", "router", "unverified", "common ISR router; not yet live-verified in this PT 7.3.0 Wine setup", 0),
    ModelRecord("2950-24", "switch", "unverified", "common access switch; not yet live-verified in this PT 7.3.0 Wine setup", 1),
    ModelRecord("2950T", "switch", "unverified", "common access switch; not yet live-verified in this PT 7.3.0 Wine setup", 1),
    ModelRecord("3560-24PS", "switch", "risky", "known PT 7.3.0 crash risk when created by automation", 1),
    ModelRecord("3650-24PS", "multilayer_switch", "risky", "likely same PT 7.3.0 crash class as 3560; avoid unattended runs", 16),
    ModelRecord("Laptop-PT", "laptop", "unverified", "common end device; not yet live-verified in this PT 7.3.0 Wine setup", 18),
    ModelRecord("Printer-PT", "pc", "unverified", "common end device; not yet live-verified in this PT 7.3.0 Wine setup", 8),
    ModelRecord("AccessPoint-PT", "wireless", "unverified", "wireless device; not yet live-verified in this PT 7.3.0 Wine setup", 7),
    ModelRecord("WRT300N", "wireless", "unverified", "wireless router; not yet live-verified in this PT 7.3.0 Wine setup", 7),
    ModelRecord("ASA5505", "asa", "unverified", "ASA firewall; not yet live-verified in this PT 7.3.0 Wine setup", 27),
    ModelRecord("ASA5506", "asa", "unverified", "ASA firewall; not yet live-verified in this PT 7.3.0 Wine setup", 27),
    ModelRecord("Cloud-PT", "hub", "unverified", "WAN/cloud device; not yet live-verified in this PT 7.3.0 Wine setup", 2),
    ModelRecord("IP Phone", "pc", "unverified", "voice endpoint; not yet live-verified in this PT 7.3.0 Wine setup", 8),
    ModelRecord("Power Distribution Device", "physical", "blocked", "auto-created physical/power objects can destabilize automated sessions", None),
)


MODEL_REGISTRY: dict[str, ModelRecord] = {record.model: record for record in COMMON_MODELS}


def models_by_status() -> dict[str, list[dict[str, object]]]:
    grouped: dict[str, list[dict[str, object]]] = {"safe": [], "unverified": [], "risky": [], "blocked": []}
    for record in COMMON_MODELS:
        grouped.setdefault(record.status, []).append(record_to_dict(record))
    return grouped


def record_to_dict(record: ModelRecord) -> dict[str, object]:
    return {
        "model": record.model,
        "category": record.category,
        "status": record.status,
        "note": record.note,
        "type_id": record.type_id,
        "unattended_safe": record.unattended_safe,
    }


def status_notes(status: str) -> str:
    return {
        "safe": "live-verified locally; allowed by default safety gate",
        "unverified": "candidate for one-at-a-time manual validation",
        "risky": "known or likely to destabilize PT 7.3.0; requires explicit override",
        "blocked": "do not automate in this environment",
    }.get(status, "unknown status")
