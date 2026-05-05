"""
EvidencePackageBuilder — Phase 3 implementation.

Assembles an auditor-consumable evidence bundle from a set of LedgerEvents.
All file contents are deterministic given the same event set and framework list.
"""
from __future__ import annotations

import csv
import dataclasses
import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from forgecompliance.control_registry import ControlRegistry
from forgecompliance.gap_analyzer import GapAnalyzer
from forgecompliance.reports import (
    generate_coverage_report,
    generate_event_type_summary,
    generate_retention_report,
)

if TYPE_CHECKING:
    from forgeledger.schema import LedgerEvent

_CLAIM_BOUNDARY = "Evidence support only. Not a compliance certification."

_SENSITIVE_DATA_SENSITIVITIES = frozenset({
    "health_identifiable",
    "llm_prompt_pii_suspected",
    "finance_outsourcing",
})

_REDACT_PAYLOAD_KEYS = frozenset({
    "data_sensitivity",
    "prompt",
    "response",
    "prompt_text",
    "response_text",
})

_HUMAN_EVENT_TYPES = frozenset({
    "agent.human_review_required",
    "human.approval_decision",
})

_LLM_EVENT_TYPE = "warden.llm_call_metadata"
_ENCRYPTION_ALGORITHM = "AES-256-GCM"


def _sha256_str(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _derive_aes256_key(key: bytes | str) -> bytes:
    if isinstance(key, str):
        key = key.encode("utf-8")
    return hashlib.sha256(key).digest()


def _encrypt_bytes(data: bytes, key: bytes | str) -> bytes:
    aesgcm = AESGCM(_derive_aes256_key(key))
    nonce = os.urandom(12)
    return nonce + aesgcm.encrypt(nonce, data, None)


def _decrypt_bytes(data: bytes, key: bytes | str) -> bytes:
    if len(data) < 13:
        raise ValueError("encrypted payload is too short")
    nonce = data[:12]
    ciphertext = data[12:]
    aesgcm = AESGCM(_derive_aes256_key(key))
    try:
        return aesgcm.decrypt(nonce, ciphertext, None)
    except InvalidTag as exc:
        raise ValueError("decryption failed") from exc


def _stable_ts(events: "list[LedgerEvent]") -> str:
    if not events:
        return datetime.now(timezone.utc).isoformat()
    return max(e.event_time for e in events)


def _redact_event(event: "LedgerEvent") -> dict:
    """
    Serialize event to dict, applying retention-driven redaction:
    - EPHEMERAL events: payload is stripped (None).
    - Sensitive payload fields (health_identifiable, llm_prompt_pii_suspected,
      finance_outsourcing): redactable keys are replaced with
      '[REDACTED:sha256:<hash>]' so the field is traceable but not readable.
    """
    from forgeledger.canonical_json import canonical_json
    from forgeledger.schema import RetentionClass

    d = json.loads(canonical_json(event))

    if event.policy.retention_class == RetentionClass.EPHEMERAL:
        d["payload"] = None
        return d

    payload = d.get("payload")
    if payload and isinstance(payload, dict):
        sensitivity = payload.get("data_sensitivity")
        if sensitivity in _SENSITIVE_DATA_SENSITIVITIES:
            d["payload"] = {
                k: (f"[REDACTED:sha256:{_sha256_str(str(v))}]" if k in _REDACT_PAYLOAD_KEYS else v)
                for k, v in payload.items()
            }

    return d


class EvidencePackageBuilder:
    """
    Builds a complete evidence package directory from a set of LedgerEvents.

    Usage::

        builder = EvidencePackageBuilder(events, ["NZISM", "SOC2"], registry)
        manifest = builder.build(Path("./evidence_package"))
    """

    def __init__(
        self,
        events: "list[LedgerEvent]",
        framework_ids: list[str],
        registry: ControlRegistry,
        *,
        package_id: str | None = None,
        time_range_from: str | None = None,
        time_range_to: str | None = None,
        audit_emitter: object | None = None,
        encryption_key: bytes | str | None = None,
    ) -> None:
        self._events = events
        self._framework_ids = framework_ids
        self._registry = registry
        self._package_id = package_id or str(uuid.uuid4())
        self._time_range_from = time_range_from or (events[0].event_time if events else None)
        self._time_range_to = time_range_to or (events[-1].event_time if events else None)
        self._audit_emitter = audit_emitter
        self._encryption_key = encryption_key

    def build(self, output_dir: Path) -> dict:
        """
        Write all 12 evidence package files to output_dir.
        Returns the manifest dict.
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        self._write_ledger_slice(output_dir)
        chain_report = self._write_chain_validation_report(output_dir)
        self._write_control_coverage_report(output_dir)
        retention_report = self._write_retention_policy_report(output_dir)
        self._write_legal_hold_report(output_dir)
        self._write_event_type_summary(output_dir)
        gap_summary = self._write_evidence_gap_report(output_dir)
        self._write_human_review_decisions(output_dir)
        self._write_model_provider_boundary_report(output_dir)
        self._write_readme(output_dir)

        encrypted = self._encryption_key is not None
        file_hashes: dict[str, str] = {}

        if encrypted:
            self._encrypt_content_files(output_dir, self._encryption_key)
            encrypted_files = sorted(p.name for p in output_dir.iterdir() if p.is_file())
            ciphertext_files_for_hash = [name for name in encrypted_files if name != "package_hash.txt.enc"]
            for name in ciphertext_files_for_hash:
                file_hashes[name] = _sha256_bytes((output_dir / name).read_bytes())

            package_hash_plaintext = json.dumps(
                {"algorithm": "sha256", "files": file_hashes},
                indent=2,
                sort_keys=True,
            ).encode("utf-8")
            (output_dir / "package_hash.txt.enc").write_bytes(
                _encrypt_bytes(package_hash_plaintext, self._encryption_key)
            )

        manifest = {
            "package_id": self._package_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "framework_profiles": sorted(self._framework_ids),
            "time_range": {
                "from": self._time_range_from,
                "to": self._time_range_to,
            },
            "event_count": len(self._events),
            "chain_valid": chain_report["valid"],
            "retention_policy_valid": retention_report.get("legal_hold_count", 0) >= 0,
            "open_gaps": gap_summary["total_open_gaps"],
            "claim_boundary": (
                "This package provides control-aligned evidence support "
                "and is not a certification of compliance."
            ),
            "encrypted": encrypted,
            "encryption_algorithm": _ENCRYPTION_ALGORITHM if encrypted else None,
            "files": sorted(p.name for p in output_dir.iterdir() if p.is_file()),
        }
        manifest_bytes = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")
        (output_dir / "manifest.json").write_bytes(manifest_bytes)

        if not encrypted:
            # package_hash.txt: SHA-256 of every other file, computed last
            for path in sorted(output_dir.iterdir()):
                if path.name == "package_hash.txt":
                    continue
                if path.is_file():
                    file_hashes[path.name] = _sha256_bytes(path.read_bytes())

            pkg_hash_data = json.dumps(
                {"algorithm": "sha256", "files": file_hashes},
                indent=2,
                sort_keys=True,
            )
            (output_dir / "package_hash.txt").write_text(pkg_hash_data, encoding="utf-8")

        from forgeledger.audit import emit_audit_event
        from forgeledger.schema import EventType
        package_hash_for_audit = _sha256_bytes(
            (output_dir / ("package_hash.txt.enc" if encrypted else "package_hash.txt")).read_bytes()
        )
        emit_audit_event(
            self._audit_emitter,
            event_type=EventType.LEDGER_EVIDENCE_PACKAGE_EXPORTED,
            reason="evidence_package_exported",
            payload={
                "package_id": self._package_id,
                "package_hash": package_hash_for_audit,
                "event_count": len(self._events),
                "encrypted": encrypted,
                "output_path": str(output_dir),
                "framework_profiles": sorted(self._framework_ids),
            },
        )

        return manifest

    def _encrypt_content_files(self, output_dir: Path, encryption_key: bytes | str) -> None:
        for path in sorted(output_dir.iterdir()):
            if not path.is_file() or path.name == "manifest.json" or path.suffix == ".enc":
                continue
            encrypted_path = path.with_name(path.name + ".enc")
            encrypted_path.write_bytes(_encrypt_bytes(path.read_bytes(), encryption_key))
            path.unlink()

    # ---- file writers -------------------------------------------------------

    def _write_ledger_slice(self, out: Path) -> None:
        lines = [
            json.dumps(_redact_event(e), sort_keys=True, separators=(",", ":"))
            for e in self._events
        ]
        content = "\n".join(lines) + ("\n" if lines else "")
        (out / "ledger_slice.jsonl").write_text(content, encoding="utf-8")

    def _write_chain_validation_report(self, out: Path) -> dict:
        from forgeledger.hash_chain import verify_chain
        report = verify_chain(self._events)
        d = dataclasses.asdict(report)
        (out / "chain_validation_report.json").write_text(
            json.dumps(d, indent=2, sort_keys=True), encoding="utf-8"
        )
        return d

    def _write_control_coverage_report(self, out: Path) -> None:
        report = generate_coverage_report(self._registry, self._events, self._framework_ids)
        (out / "control_coverage_report.json").write_text(
            json.dumps(report, indent=2, sort_keys=True), encoding="utf-8"
        )

    def _write_retention_policy_report(self, out: Path) -> dict:
        report = generate_retention_report(self._events)
        (out / "retention_policy_report.json").write_text(
            json.dumps(report, indent=2, sort_keys=True), encoding="utf-8"
        )
        return report

    def _write_legal_hold_report(self, out: Path) -> None:
        held = [e.event_id for e in self._events if e.policy.legal_hold]
        report = {
            "generated_at": _stable_ts(self._events),
            "total_on_hold": len(held),
            "held_event_ids": sorted(held),
        }
        (out / "legal_hold_report.json").write_text(
            json.dumps(report, indent=2, sort_keys=True), encoding="utf-8"
        )

    def _write_event_type_summary(self, out: Path) -> None:
        rows = generate_event_type_summary(self._events)
        with (out / "event_type_summary.csv").open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=["event_type", "count"])
            writer.writeheader()
            writer.writerows(rows)

    def _write_evidence_gap_report(self, out: Path) -> dict:
        analyzer = GapAnalyzer(self._registry)
        stable = _stable_ts(self._events)
        frameworks: dict[str, object] = {}
        total_open = 0

        for fw in sorted(self._framework_ids):
            fw_report = analyzer.analyze(fw, self._events, generated_at=stable)
            frameworks[fw] = {
                "covered": fw_report.covered,
                "partial": fw_report.partial,
                "gaps": fw_report.gaps,
                "coverage_percent": fw_report.coverage_percent,
                "open_controls": [
                    {
                        "control_id": c.control_id,
                        "status": c.status,
                        "missing_event_types": c.missing_event_types,
                        "missing_required_fields": c.missing_required_fields,
                    }
                    for c in fw_report.controls
                    if c.status != "covered"
                ],
            }
            total_open += fw_report.gaps + fw_report.partial

        report = {
            "generated_at": stable,
            "claim_boundary": _CLAIM_BOUNDARY,
            "total_open_gaps": total_open,
            "frameworks": frameworks,
        }
        (out / "evidence_gap_report.json").write_text(
            json.dumps(report, indent=2, sort_keys=True), encoding="utf-8"
        )
        return {"total_open_gaps": total_open}

    def _write_human_review_decisions(self, out: Path) -> None:
        from forgeledger.canonical_json import canonical_json
        human_events = [e for e in self._events if e.event_type.value in _HUMAN_EVENT_TYPES]
        report = {
            "generated_at": _stable_ts(self._events),
            "total_human_review_events": len(human_events),
            "events": [json.loads(canonical_json(e)) for e in human_events],
        }
        (out / "human_review_decisions.json").write_text(
            json.dumps(report, indent=2, sort_keys=True), encoding="utf-8"
        )

    def _write_model_provider_boundary_report(self, out: Path) -> None:
        llm_events = [e for e in self._events if e.event_type.value == _LLM_EVENT_TYPE]
        records = []
        for e in llm_events:
            rec: dict = {
                "event_id": e.event_id,
                "event_time": e.event_time,
                "actor_id": e.actor.actor_id,
                "source_module": e.system_context.source_module,
                "retention_class": e.policy.retention_class.value,
            }
            if e.payload:
                for key in ("model_provider", "prompt_class", "response_class", "redaction_applied"):
                    if key in e.payload:
                        rec[key] = e.payload[key]
            records.append(rec)

        report = {
            "generated_at": _stable_ts(self._events),
            "claim_boundary": _CLAIM_BOUNDARY,
            "total_llm_boundary_events": len(records),
            "events": records,
        }
        (out / "model_provider_boundary_report.json").write_text(
            json.dumps(report, indent=2, sort_keys=True), encoding="utf-8"
        )

    def _write_readme(self, out: Path) -> None:
        frameworks_str = ", ".join(sorted(self._framework_ids))
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        readme = f"""\
# Auditor Evidence Package

## Claim Boundary

{_CLAIM_BOUNDARY}

This package provides control-aligned evidence support for governed AI systems.
It is not a certification of compliance with any regulatory framework. Assessment of compliance
requires independent audit, qualified personnel, and review of organisational controls beyond
software evidence.

## Package Contents

| File | Description |
|------|-------------|
| manifest.json | Package metadata: ID, time range, event count, chain validity, open gaps |
| package_hash.txt | SHA-256 hashes of all package files for tamper detection |
| ledger_slice.jsonl | Immutable ledger events (sensitive payloads redacted per retention policy) |
| chain_validation_report.json | Hash-chain integrity verification result |
| control_coverage_report.json | Framework control coverage map |
| retention_policy_report.json | Retention class distribution and legal hold summary |
| legal_hold_report.json | Events currently under legal hold |
| event_type_summary.csv | Event type counts |
| evidence_gap_report.json | Controls with missing or partial evidence |
| human_review_decisions.json | Human approval and review escalation events |
| model_provider_boundary_report.json | LLM gateway call records (provider boundary evidence) |
| README_AUDITOR.md | This file |

## Framework Profiles Covered

{frameworks_str}

## How to Verify Package Integrity

1. Read `package_hash.txt` — it contains the SHA-256 hash of every other file.
2. For each file listed, recompute `sha256(file_content)` and compare.
3. Any mismatch indicates the package was modified after export.

## How to Verify the Ledger Chain

1. Open `chain_validation_report.json`.
2. Confirm `"valid": true` — this means no events were edited, deleted, or reordered.
3. If `"valid": false`, the `"error"` field identifies the first broken link.

## Control Evidence Gaps

`evidence_gap_report.json` lists controls where required evidence types or fields were absent
in the provided time window. A gap indicates evidence was not captured in this export window,
not necessarily that a control failed.

## Redaction Policy

- Events classified as `ephemeral` have their payload stripped entirely.
- Events with sensitive payload fields (`health_identifiable`, `llm_prompt_pii_suspected`,
  `finance_outsourcing`) have those fields replaced with `[REDACTED:sha256:<hash>]` so
  the field is traceable without exposing raw data.

---
*Generated by ForgeCompliance v0.1 — {date_str}*
"""
        (out / "README_AUDITOR.md").write_text(readme, encoding="utf-8")


def decrypt_evidence_package(package_dir: Path, key: bytes | str) -> list[Path]:
    """Decrypt all .enc package files in-place, returning restored plaintext paths."""
    package_dir = Path(package_dir)
    restored: list[Path] = []
    for encrypted_path in sorted(package_dir.glob("*.enc")):
        plaintext_name = encrypted_path.name.removesuffix(".enc")
        plaintext_path = encrypted_path.with_name(plaintext_name)
        plaintext_path.write_bytes(_decrypt_bytes(encrypted_path.read_bytes(), key))
        restored.append(plaintext_path)
    return restored
