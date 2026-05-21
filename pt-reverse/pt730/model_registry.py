"""PT 7.3.0 model safety registry.

Statuses intentionally separate known-good local evidence from models that are
only common in Packet Tracer catalogs.  Unverified models need one-at-a-time
manual probing before they can be promoted to safe automation defaults.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ModelRecord:
    model: str
    category: str
    status: str
    note: str
    type_id: int | None = None
    validation: dict[str, Any] | None = None

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
VALID_STATUSES = {"safe", "unverified", "risky", "blocked"}


def validation_store_path() -> Path:
    override = os.environ.get("PT730_MODEL_VALIDATIONS")
    if override:
        return Path(override)
    return Path(__file__).with_name("model_validations.json")


def load_validation_store(path: Path | None = None) -> dict[str, Any]:
    store_path = path or validation_store_path()
    if not store_path.exists():
        return {"version": 1, "validations": {}}
    with store_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("model validation store must be a JSON object")
    validations = data.setdefault("validations", {})
    if not isinstance(validations, dict):
        raise ValueError("model validation store validations must be an object")
    data.setdefault("version", 1)
    return data


def save_validation_store(data: dict[str, Any], path: Path | None = None) -> None:
    store_path = path or validation_store_path()
    store_path.parent.mkdir(parents=True, exist_ok=True)
    with store_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")


def _apply_validation(record: ModelRecord, validation: dict[str, Any] | None) -> ModelRecord:
    if not isinstance(validation, dict):
        return record
    status = str(validation.get("status", record.status))
    if status not in VALID_STATUSES:
        return record
    note = str(validation.get("note", validation.get("reason", record.note)))
    return ModelRecord(record.model, record.category, status, note, record.type_id, validation)


def effective_records(path: Path | None = None) -> tuple[ModelRecord, ...]:
    store = load_validation_store(path)
    validations = store.get("validations", {})
    return tuple(_apply_validation(record, validations.get(record.model)) for record in COMMON_MODELS)


def effective_registry(path: Path | None = None) -> dict[str, ModelRecord]:
    return {record.model: record for record in effective_records(path)}


def safe_model_names(path: Path | None = None) -> set[str]:
    return {record.model for record in effective_records(path) if record.status == "safe"}


def safe_model_notes(path: Path | None = None) -> dict[str, str]:
    return {record.model: record.note for record in effective_records(path) if record.status == "safe"}


def risky_model_notes(path: Path | None = None) -> dict[str, str]:
    return {record.model: record.note for record in effective_records(path) if record.status in {"risky", "blocked"}}


def models_by_status(path: Path | None = None) -> dict[str, list[dict[str, object]]]:
    grouped: dict[str, list[dict[str, object]]] = {"safe": [], "unverified": [], "risky": [], "blocked": []}
    for record in effective_records(path):
        grouped.setdefault(record.status, []).append(record_to_dict(record))
    return grouped


def record_to_dict(record: ModelRecord) -> dict[str, object]:
    data: dict[str, object] = {
        "model": record.model,
        "category": record.category,
        "status": record.status,
        "note": record.note,
        "type_id": record.type_id,
        "unattended_safe": record.unattended_safe,
    }
    if record.validation:
        data["validation"] = record.validation
    return data


def status_notes(status: str) -> str:
    return {
        "safe": "live-verified locally; allowed by default safety gate",
        "unverified": "candidate for one-at-a-time manual validation",
        "risky": "known or likely to destabilize PT 7.3.0; requires explicit override",
        "blocked": "do not automate in this environment",
    }.get(status, "unknown status")
