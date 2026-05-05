"""Recursive loop orchestrator for Azul."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from ..ticket import AzulTicket
from ..ticket_store import AzulTicketStore
from ..training_pairs import TrainingPairStore
from ..xp_ledger import XPLedger
from .config import LoopConfig, ensure_loop_dirs, load_loop_config
from .drift_scanner import DriftScanner
from .gold_labels import GoldLabelStore
from .pattern_analyzer import PatternAnalyzer
from .recommender import ImprovementRecommender
from .types import DistillationBatch, LoopReport


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


class LoopOrchestrator:
    def __init__(
        self,
        *,
        cfg: Optional[LoopConfig] = None,
        ticket_store: Optional[AzulTicketStore] = None,
        ledger: Optional[XPLedger] = None,
        pair_store: Optional[TrainingPairStore] = None,
        gold_labels: Optional[GoldLabelStore] = None,
    ) -> None:
        self.cfg = cfg or load_loop_config()
        ensure_loop_dirs(self.cfg)

        self.ticket_store = ticket_store or AzulTicketStore()
        self.ledger = ledger or XPLedger()
        self.pair_store = pair_store or TrainingPairStore()
        self.gold_labels = gold_labels or GoldLabelStore(cfg=self.cfg)

        self.analyzer = PatternAnalyzer(
            cfg=self.cfg,
            store=self.ticket_store,
            ledger=self.ledger,
            pairs=self.pair_store,
            gold_labels=self.gold_labels,
        )
        self.drift_scanner = DriftScanner(cfg=self.cfg, gold_labels=self.gold_labels)
        self.recommender = ImprovementRecommender(cfg=self.cfg)

        self._state = self._load_state()

    @staticmethod
    def _cadence_seconds(cadence: str) -> int:
        c = cadence.strip().lower()
        if c == "daily":
            return 86400
        if c == "weekly":
            return 7 * 86400
        if c == "monthly":
            return 30 * 86400
        # Default safe cadence.
        return 7 * 86400

    @staticmethod
    def _is_due(last_iso: str, cadence_seconds: int) -> bool:
        if not last_iso:
            return True
        try:
            last = datetime.fromisoformat(last_iso)
        except ValueError:
            return True
        return (_now() - last).total_seconds() >= cadence_seconds

    def _load_state(self) -> Dict[str, Any]:
        path = self.cfg.loop_state_path
        if not path.exists():
            return {
                "enabled": self.cfg.enabled,
                "completed_since_analysis": 0,
                "last_ticket_id": "",
                "last_report_path": "",
                "last_report_at": "",
                "last_drift_path": "",
                "last_drift_at": "",
                "last_distillation_batch_path": "",
                "last_distillation_batch_at": "",
                "distilled_pair_ids": [],
            }
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        if not isinstance(data, dict):
            data = {}
        defaults = {
            "enabled": self.cfg.enabled,
            "completed_since_analysis": 0,
            "last_ticket_id": "",
            "last_report_path": "",
            "last_report_at": "",
            "last_drift_path": "",
            "last_drift_at": "",
            "last_distillation_batch_path": "",
            "last_distillation_batch_at": "",
            "distilled_pair_ids": [],
        }
        defaults.update(data)
        return defaults

    def _save_state(self) -> None:
        self.cfg.loop_state_path.write_text(json.dumps(self._state, indent=2), encoding="utf-8")

    def status_snapshot(self) -> Dict[str, Any]:
        agreement = {
            "action_contract_stub": self.gold_labels.compute_agreement_rate("action_contract_stub", window=20),
            "verdict_override": self.gold_labels.compute_agreement_rate("verdict_override", window=20),
            "gate_policy_recommendation": self.gold_labels.compute_agreement_rate(
                "gate_policy_recommendation", window=20
            ),
        }
        out = dict(self._state)
        out["enabled"] = self.cfg.enabled
        out["threshold_window"] = self.cfg.threshold_window
        out["agreement_rates"] = agreement
        return out

    def _is_terminal_ticket(self, ticket: AzulTicket) -> bool:
        status = getattr(ticket.status, "value", str(ticket.status))
        return status in {"COMPLETED", "REJECTED", "WARNED", "FAILED"}

    def _record_metadata_labels(self, ticket: AzulTicket) -> None:
        metadata = getattr(ticket, "metadata", {}) or {}
        if not isinstance(metadata, dict):
            return

        verdict_override = metadata.get("verdict_override")
        if isinstance(verdict_override, dict):
            original = verdict_override.get("original_verdict")
            approved = verdict_override.get("approved_verdict")
            if isinstance(original, dict) and isinstance(approved, dict):
                self.gold_labels.record_verdict_override(
                    ticket_id=ticket.ticket_id,
                    original_verdict=original,
                    approved_verdict=approved,
                    reviewer_id=str(verdict_override.get("reviewer_id", "lead_architect")),
                    reason=str(verdict_override.get("reason", "manual override")),
                )

        policy_edit = metadata.get("policy_edit")
        if isinstance(policy_edit, dict):
            original_policy = policy_edit.get("original")
            approved_policy = policy_edit.get("approved")
            if isinstance(original_policy, dict) and isinstance(approved_policy, dict):
                self.gold_labels.record_policy_edit(
                    policy_name=str(policy_edit.get("policy_name", "unknown_policy")),
                    original_policy=original_policy,
                    approved_policy=approved_policy,
                    reviewer_id=str(policy_edit.get("reviewer_id", "lead_architect")),
                    source=str(policy_edit.get("source", "metadata.policy_edit")),
                )

    def on_ticket_completed(self, ticket: AzulTicket) -> Optional[Dict[str, Any]]:
        if not self.cfg.enabled:
            return None
        if not self._is_terminal_ticket(ticket):
            return None

        self._record_metadata_labels(ticket)

        self._state["last_ticket_id"] = ticket.ticket_id
        self._state["completed_since_analysis"] = int(self._state.get("completed_since_analysis", 0)) + 1
        self._save_state()

        if self._is_due(
            str(self._state.get("last_report_at", "")),
            self._cadence_seconds(self.cfg.report_cadence),
        ) or self._is_due(
            str(self._state.get("last_drift_at", "")),
            self._cadence_seconds(self.cfg.drift_cadence),
        ):
            return self.run_scheduled_scan(trigger="scheduled_cadence")

        if self._is_due(
            str(self._state.get("last_distillation_batch_at", "")),
            self._cadence_seconds(self.cfg.distill_cadence),
        ):
            self.run_distillation_batch()

        if int(self._state.get("completed_since_analysis", 0)) >= self.cfg.threshold_window:
            return self.run_scheduled_scan(trigger="threshold_window")
        return None

    def _policy_edit_count(self) -> int:
        labels = self.gold_labels.get_labels(artifact_type="gate_policy_recommendation", limit=200)
        return sum(1 for label in labels if not label.agreement)

    def _persist_report(self, report: LoopReport) -> Path:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = self.cfg.reports_dir / f"report_{stamp}.json"
        path.write_text(json.dumps(asdict(report), indent=2), encoding="utf-8")
        return path

    def run_scheduled_scan(self, trigger: str = "scheduled") -> Dict[str, Any]:
        drift = self.drift_scanner.scan_drift()
        analysis = self.analyzer.analyze()
        distillation_batch = self.run_distillation_batch()
        plan = self.recommender.recommend(
            report=analysis,
            policy_edit_count=self._policy_edit_count(),
            distillation_batch=distillation_batch,
        )

        loop_report = LoopReport(
            generated_at=_now_iso(),
            trigger=trigger,
            analysis=analysis,
            drift=drift,
            plan=plan,
        )
        report_path = self._persist_report(loop_report)

        drift_path = ""
        drift_reports = sorted(self.cfg.drift_reports_dir.glob("drift_*.json"))
        if drift_reports:
            drift_path = str(drift_reports[-1])

        self._state["completed_since_analysis"] = 0
        self._state["last_report_path"] = str(report_path)
        self._state["last_report_at"] = _now_iso()
        self._state["last_drift_path"] = drift_path
        self._state["last_drift_at"] = _now_iso() if drift_path else self._state.get("last_drift_at", "")
        self._save_state()

        # Regenerate ticket export so SAM's sync script always picks up the latest entries.
        ticket_export_path = self.cfg.azul_data_dir / "ticket_export" / "ticket_export.jsonl"
        self.gold_labels.export_ticket_summaries(ticket_export_path)

        return {
            "status": "ok",
            "report_path": str(report_path),
            "drift_path": drift_path,
            "trigger": trigger,
        }

    def run_distillation_batch(self) -> Optional[DistillationBatch]:
        pairs = self.pair_store.get_pairs(min_score=self.cfg.distill_min_score)
        if not pairs:
            return None

        used_ids = set(self._state.get("distilled_pair_ids") or [])
        fresh_pairs = [pair for pair in pairs if pair.get("pair_id") not in used_ids]
        if len(fresh_pairs) < self.cfg.distill_batch_size:
            return None

        selected = fresh_pairs[: self.cfg.distill_batch_size]
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        batch_dir = self.cfg.distillation_batches_dir / f"batch_{stamp}"
        batch_dir.mkdir(parents=True, exist_ok=True)

        pairs_path = batch_dir / "pairs.jsonl"
        with pairs_path.open("w", encoding="utf-8") as handle:
            for pair in selected:
                handle.write(json.dumps(pair) + "\n")

        scores = [float(pair.get("verification_score", 0.0) or 0.0) for pair in selected]
        domains = sorted({str(pair.get("domain", "unknown")) for pair in selected})
        manifest = {
            "created_at": _now_iso(),
            "pair_count": len(selected),
            "avg_score": (sum(scores) / float(len(scores))) if scores else 0.0,
            "domains": domains,
            "pairs_path": str(pairs_path),
            "min_score": self.cfg.distill_min_score,
            "batch_size": self.cfg.distill_batch_size,
            "mode": "data_prep_only",
        }
        manifest_path = batch_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        self._state["last_distillation_batch_path"] = str(manifest_path)
        self._state["last_distillation_batch_at"] = _now_iso()
        self._state["distilled_pair_ids"] = sorted(used_ids | {pair.get("pair_id") for pair in selected})
        self._save_state()

        return DistillationBatch(
            pair_count=manifest["pair_count"],
            avg_score=manifest["avg_score"],
            domains=domains,
            manifest_path=str(manifest_path),
        )

    def latest_report(self) -> Dict[str, Any]:
        path = Path(str(self._state.get("last_report_path") or ""))
        if not path.exists():
            reports = sorted(self.cfg.reports_dir.glob("report_*.json"))
            if not reports:
                return {}
            path = reports[-1]
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def latest_drift_report(self) -> Dict[str, Any]:
        path = Path(str(self._state.get("last_drift_path") or ""))
        if not path.exists():
            reports = sorted(self.cfg.drift_reports_dir.glob("drift_*.json"))
            if not reports:
                return {}
            path = reports[-1]
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}


__all__ = ["LoopOrchestrator"]
