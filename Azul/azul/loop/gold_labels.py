"""Gold label storage and agreement-rate helpers."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from .config import LoopConfig, ensure_loop_dirs, load_loop_config
from .types import GoldLabel


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _normalize(v) for k, v in sorted(value.items(), key=lambda i: str(i[0]))}
    if isinstance(value, list):
        return [_normalize(v) for v in value]
    return value


def compute_diff(original: Any, approved: Any) -> Dict[str, Any]:
    if _normalize(original) == _normalize(approved):
        return {}

    if isinstance(original, dict) and isinstance(approved, dict):
        diff: Dict[str, Any] = {}
        for key in sorted(set(original) | set(approved), key=str):
            o = original.get(key)
            a = approved.get(key)
            child = compute_diff(o, a)
            if child:
                diff[str(key)] = child
        return diff

    if isinstance(original, list) and isinstance(approved, list):
        return {"before": original, "after": approved}

    return {"before": original, "after": approved}


def _load_yaml_file(path: Path) -> Dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    try:
        data = yaml.safe_load(raw)
    except Exception:
        return {"_raw": raw}
    if isinstance(data, dict):
        return data
    return {"_raw": raw}


class GoldLabelStore:
    def __init__(self, cfg: Optional[LoopConfig] = None, path: Optional[Path] = None) -> None:
        self.cfg = cfg or load_loop_config()
        ensure_loop_dirs(self.cfg)
        self.path = Path(path or self.cfg.gold_labels_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record_label(
        self,
        artifact_type: str,
        original: Dict[str, Any],
        approved: Dict[str, Any],
        reviewer_id: str = "system",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> GoldLabel:
        normalized_original = _normalize(original)
        normalized_approved = _normalize(approved)
        diff = compute_diff(normalized_original, normalized_approved)
        label = GoldLabel(
            label_id=f"gl-{uuid.uuid4().hex[:12]}",
            artifact_type=artifact_type,
            original=normalized_original,
            approved=normalized_approved,
            diff=diff,
            reviewer_id=reviewer_id,
            timestamp=_now_iso(),
            agreement=(diff == {}),
            metadata=metadata or {},
        )
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(label.__dict__) + "\n")
        return label

    def record_contract_approval(
        self,
        *,
        baseline_contract_path: Path,
        approved_contract_path: Path,
        reviewer_id: str = "lead_architect",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> GoldLabel:
        original = _load_yaml_file(baseline_contract_path)
        approved = _load_yaml_file(approved_contract_path)
        meta = {
            "source": "contract_stub_approval",
            "baseline_contract_path": str(baseline_contract_path),
            "approved_contract_path": str(approved_contract_path),
        }
        if metadata:
            meta.update(metadata)
        return self.record_label(
            artifact_type="action_contract_stub",
            original=original,
            approved=approved,
            reviewer_id=reviewer_id,
            metadata=meta,
        )

    def record_verdict_override(
        self,
        *,
        ticket_id: str,
        original_verdict: Dict[str, Any],
        approved_verdict: Dict[str, Any],
        reviewer_id: str,
        reason: str,
    ) -> GoldLabel:
        return self.record_label(
            artifact_type="verdict_override",
            original=original_verdict,
            approved=approved_verdict,
            reviewer_id=reviewer_id,
            metadata={
                "source": "verdict_override",
                "ticket_id": ticket_id,
                "reason": reason,
            },
        )

    def record_policy_edit(
        self,
        *,
        policy_name: str,
        original_policy: Dict[str, Any],
        approved_policy: Dict[str, Any],
        reviewer_id: str,
        source: str = "level3_recommendation",
    ) -> GoldLabel:
        return self.record_label(
            artifact_type="gate_policy_recommendation",
            original=original_policy,
            approved=approved_policy,
            reviewer_id=reviewer_id,
            metadata={"source": source, "policy_name": policy_name},
        )

    def get_labels(
        self,
        artifact_type: Optional[str] = None,
        since: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[GoldLabel]:
        if not self.path.exists():
            return []

        labels: List[GoldLabel] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if artifact_type and row.get("artifact_type") != artifact_type:
                continue
            if since and str(row.get("timestamp", "")) < since:
                continue
            try:
                labels.append(GoldLabel(**row))
            except TypeError:
                continue

        labels.sort(key=lambda item: item.timestamp)
        if limit is not None:
            return labels[-limit:]
        return labels

    def compute_agreement_rate(self, artifact_type: Optional[str] = None, window: int = 20) -> float:
        if window <= 0:
            return 0.0
        labels = self.get_labels(artifact_type=artifact_type, limit=window)
        if not labels:
            return 1.0
        agreements = sum(1 for label in labels if label.agreement)
        return agreements / float(len(labels))

    def export_ticket_summaries(self, output_path: Path) -> int:
        """Write a ticket_export.jsonl for SAM's ticket_store_loader callback.

        Emits one line per GoldLabel that has a metadata.ticket_id field.
        Format: {"ticket_id": "...", "change_summary": "..."}

        change_summary is sourced from metadata.reason (verdict_override entries) or
        a generic description derived from artifact_type + diff keys for other types.

        Returns the number of entries written. Output file is rewritten on each call
        (not append-only — the full set of known tickets should always be present).
        """
        labels = self.get_labels()
        entries: Dict[str, Dict[str, str]] = {}

        for label in labels:
            ticket_id = label.metadata.get("ticket_id")
            if not ticket_id:
                continue
            reason = label.metadata.get("reason", "")
            if not reason:
                diff_keys = ", ".join(label.diff.keys()) if label.diff else "no changes"
                reason = f"{label.artifact_type} review — diff fields: {diff_keys}"
            entries[ticket_id] = {
                "ticket_id": ticket_id,
                "change_summary": reason,
            }

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as handle:
            for entry in entries.values():
                handle.write(json.dumps(entry) + "\n")
        return len(entries)

    def compute_agreement_trend(
        self,
        artifact_type: Optional[str] = None,
        window: int = 20,
    ) -> tuple[float, float]:
        if window <= 0:
            return 1.0, 1.0
        labels = self.get_labels(artifact_type=artifact_type, limit=window * 2)
        if not labels:
            return 1.0, 1.0
        previous = labels[:-window]
        current = labels[-window:]
        prev_rate = (
            sum(1 for label in previous if label.agreement) / float(len(previous)) if previous else 1.0
        )
        curr_rate = sum(1 for label in current if label.agreement) / float(len(current))
        return prev_rate, curr_rate
