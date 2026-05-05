"""Scheduled drift scanner with snapshot-on-first-scan baselines."""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from .config import LoopConfig, ensure_loop_dirs, load_loop_config
from .gold_labels import GoldLabelStore, compute_diff
from .types import DriftItem, DriftReport, MetricTrend


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _yaml_or_text(path: Path) -> Dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        data = yaml.safe_load(text)
    except Exception:
        data = None
    if isinstance(data, dict):
        return data
    return {"_raw": text}


def _iter_yaml_files(directory: Path) -> List[Path]:
    if not directory.exists():
        return []
    return sorted([p for p in directory.rglob("*.yaml") if p.is_file()])


def _contract_direction(before: Dict[str, Any], after: Dict[str, Any]) -> str:
    score = 0
    before_actions = before.get("actions") if isinstance(before, dict) else None
    after_actions = after.get("actions") if isinstance(after, dict) else None
    if isinstance(before_actions, list) and isinstance(after_actions, list) and before_actions and after_actions:
        b0 = before_actions[0] if isinstance(before_actions[0], dict) else {}
        a0 = after_actions[0] if isinstance(after_actions[0], dict) else {}
        b_guards = b0.get("guard_predicates") if isinstance(b0.get("guard_predicates"), list) else []
        a_guards = a0.get("guard_predicates") if isinstance(a0.get("guard_predicates"), list) else []
        if len(a_guards) > len(b_guards):
            score += 1
        elif len(a_guards) < len(b_guards):
            score -= 1

        b_risk = int(b0.get("risk_tier", 0) or 0)
        a_risk = int(a0.get("risk_tier", 0) or 0)
        if a_risk > b_risk:
            score += 1
        elif a_risk < b_risk:
            score -= 1

    if score > 0:
        return "improvement"
    if score < 0:
        return "regression"
    return "stable"


def _policy_direction(before: Dict[str, Any], after: Dict[str, Any]) -> str:
    score = 0
    for key in ("min_score", "warn_score"):
        b = float(before.get(key, 0) or 0)
        a = float(after.get(key, 0) or 0)
        if a > b:
            score += 1
        elif a < b:
            score -= 1
    for key in ("max_deny_count", "max_oracle_mismatch", "max_escalation_count"):
        b = float(before.get(key, 0) or 0)
        a = float(after.get(key, 0) or 0)
        if a < b:
            score += 1
        elif a > b:
            score -= 1
    if score > 0:
        return "improvement"
    if score < 0:
        return "regression"
    return "stable"


class DriftScanner:
    def __init__(self, cfg: Optional[LoopConfig] = None, gold_labels: Optional[GoldLabelStore] = None):
        self.cfg = cfg or load_loop_config()
        ensure_loop_dirs(self.cfg)
        self.gold_labels = gold_labels or GoldLabelStore(cfg=self.cfg)

    def _baseline_path(self, current_path: Path, base_dir: Path, root_dir: Path) -> Path:
        return base_dir / current_path.relative_to(root_dir)

    def _snapshot_if_missing(self, current_path: Path, baseline_path: Path) -> bool:
        if baseline_path.exists():
            return False
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(current_path, baseline_path)
        return True

    def scan_drift(self, since: Optional[str] = None) -> DriftReport:
        items: List[DriftItem] = []
        contracts_compared = 0
        contracts_drifted = 0
        policies_compared = 0
        policies_drifted = 0
        baseline_new_count = 0
        direction_score = 0

        for contract_path in _iter_yaml_files(self.cfg.contracts_dir):
            baseline_path = self._baseline_path(
                contract_path,
                self.cfg.baseline_contracts_dir,
                self.cfg.contracts_dir,
            )
            if self._snapshot_if_missing(contract_path, baseline_path):
                baseline_new_count += 1
                items.append(
                    DriftItem(
                        artifact_type="contract",
                        artifact_id=contract_path.stem,
                        path=str(contract_path),
                        status="new_baseline",
                        change_count=0,
                        direction="stable",
                        recommendation="Baseline created on first scan.",
                    )
                )
                continue

            contracts_compared += 1
            before = _yaml_or_text(baseline_path)
            after = _yaml_or_text(contract_path)
            diff = compute_diff(before, after)
            if not diff:
                continue

            contracts_drifted += 1
            direction = _contract_direction(before, after)
            if direction == "improvement":
                direction_score += 1
            elif direction == "regression":
                direction_score -= 1

            recommendation = (
                "Review drifted guard predicates and refresh generation prompt examples."
            )
            items.append(
                DriftItem(
                    artifact_type="contract",
                    artifact_id=contract_path.stem,
                    path=str(contract_path),
                    status="drifted",
                    change_count=len(diff),
                    direction=direction,
                    field_changes=diff,
                    recommendation=recommendation,
                )
            )

        for policy_path in _iter_yaml_files(self.cfg.policies_dir):
            baseline_path = self._baseline_path(
                policy_path,
                self.cfg.baseline_policies_dir,
                self.cfg.policies_dir,
            )
            if self._snapshot_if_missing(policy_path, baseline_path):
                baseline_new_count += 1
                items.append(
                    DriftItem(
                        artifact_type="policy",
                        artifact_id=policy_path.stem,
                        path=str(policy_path),
                        status="new_baseline",
                        change_count=0,
                        direction="stable",
                        recommendation="Baseline created on first scan.",
                    )
                )
                continue

            policies_compared += 1
            before = _yaml_or_text(baseline_path)
            after = _yaml_or_text(policy_path)
            diff = compute_diff(before, after)
            if not diff:
                continue

            policies_drifted += 1
            direction = _policy_direction(before, after)
            if direction == "improvement":
                direction_score += 1
            elif direction == "regression":
                direction_score -= 1

            items.append(
                DriftItem(
                    artifact_type="policy",
                    artifact_id=policy_path.stem,
                    path=str(policy_path),
                    status="drifted",
                    change_count=len(diff),
                    direction=direction,
                    field_changes=diff,
                    recommendation="Review policy threshold drift and validate intended strictness.",
                )
            )

        prev_rate, curr_rate = self.gold_labels.compute_agreement_trend(window=20)
        trend = MetricTrend(
            name="agreement_rate",
            current=curr_rate,
            previous=prev_rate,
            delta=curr_rate - prev_rate,
            direction="up" if curr_rate > prev_rate else "down" if curr_rate < prev_rate else "flat",
        )

        labels_since = len(self.gold_labels.get_labels(since=since)) if since else len(self.gold_labels.get_labels())
        recommendations = [item.recommendation for item in items if item.recommendation and item.status == "drifted"]

        if direction_score > 0:
            overall_direction = "improvement"
        elif direction_score < 0:
            overall_direction = "regression"
        else:
            overall_direction = "stable"

        report = DriftReport(
            scan_date=_now_iso(),
            contracts_compared=contracts_compared,
            contracts_drifted=contracts_drifted,
            policies_compared=policies_compared,
            policies_drifted=policies_drifted,
            drift_direction=overall_direction,
            gold_labels_since=labels_since,
            agreement_rate_trend=trend,
            recommendations=recommendations,
            items=items,
            baseline_new_count=baseline_new_count,
        )

        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out_path = self.cfg.drift_reports_dir / f"drift_{stamp}.json"
        out_path.write_text(json.dumps(asdict(report), indent=2), encoding="utf-8")
        return report


__all__ = ["DriftScanner"]
