"""Pattern analyzer for recursive loop metrics."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from ..ticket_store import AzulTicketStore
from ..training_pairs import TrainingPairStore
from ..xp_ledger import XPLedger
from .config import LoopConfig, load_loop_config
from .gold_labels import GoldLabelStore
from .types import AnalysisReport, FailureCluster, MetricTrend, ThresholdFlag


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _score_from_ticket(ticket: Any) -> float:
    bundle = getattr(ticket, "review_bundle", None) or {}
    metrics = bundle.get("metrics", {}) if isinstance(bundle, dict) else {}
    try:
        return float(metrics.get("total_score", 0.0) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _ticket_type(ticket: Any) -> str:
    t = getattr(ticket, "ticket_type", "unknown")
    return getattr(t, "value", str(t))


def _ticket_status(ticket: Any) -> str:
    s = getattr(ticket, "status", "unknown")
    return getattr(s, "value", str(s))


def _metric_int(metrics: Dict[str, Any], key: str) -> int:
    try:
        return int(metrics.get(key, 0) or 0)
    except (TypeError, ValueError):
        return 0


class PatternAnalyzer:
    def __init__(
        self,
        cfg: Optional[LoopConfig] = None,
        store: Optional[AzulTicketStore] = None,
        ledger: Optional[XPLedger] = None,
        pairs: Optional[TrainingPairStore] = None,
        gold_labels: Optional[GoldLabelStore] = None,
    ) -> None:
        self.cfg = cfg or load_loop_config()
        self.store = store or AzulTicketStore()
        self.ledger = ledger or XPLedger()
        self.pairs = pairs or TrainingPairStore()
        self.gold_labels = gold_labels or GoldLabelStore(cfg=self.cfg)

    def analyze(self) -> AnalysisReport:
        tickets = self.store.list_completed()
        if self.cfg.threshold_window > 0:
            tickets = tickets[-self.cfg.threshold_window :]

        reject_by_type: Dict[str, int] = defaultdict(int)
        total_by_type: Dict[str, int] = defaultdict(int)
        deny_by_phase: Dict[str, int] = defaultdict(int)
        mismatch_frequency: Dict[str, int] = defaultdict(int)
        failure_modes: Counter[str] = Counter()
        scores: List[float] = []
        dev_stats: Dict[str, Dict[str, float]] = defaultdict(lambda: {"count": 0.0, "pass": 0.0, "score": 0.0})

        for ticket in tickets:
            ttype = _ticket_type(ticket)
            total_by_type[ttype] += 1

            status = _ticket_status(ticket)
            verdict = str(getattr(ticket, "verdict", "") or "")
            if status == "REJECTED" or verdict == "reject":
                reject_by_type[ttype] += 1

            score = _score_from_ticket(ticket)
            scores.append(score)

            bundle = getattr(ticket, "review_bundle", None) or {}
            metrics = bundle.get("metrics", {}) if isinstance(bundle, dict) else {}
            deny_count = _metric_int(metrics, "deny_count")
            if deny_count > 0:
                phase = str(bundle.get("failure_gate") or "unknown_gate")
                deny_by_phase[phase] += deny_count

            mismatch_count = _metric_int(metrics, "oracle_mismatch_count")
            if mismatch_count <= 0:
                mismatch_count = _metric_int(metrics, "oracle_mismatch")
            if mismatch_count > 0:
                mismatch_key = str(bundle.get("failure_reason") or getattr(ticket, "verdict_reason", "oracle_mismatch"))
                mismatch_frequency[mismatch_key] += mismatch_count

            failure_key = str(
                (bundle.get("failure_reason") if isinstance(bundle, dict) else "")
                or getattr(ticket, "verdict_reason", "")
                or "none"
            )
            failure_modes[failure_key] += 1

            source = getattr(ticket, "source", {}) or {}
            metadata = getattr(ticket, "metadata", {}) or {}
            dev_id = str(source.get("developer") or source.get("actor") or metadata.get("reviewer_id") or "unknown")
            dev_stats[dev_id]["count"] += 1.0
            if verdict == "pass":
                dev_stats[dev_id]["pass"] += 1.0
            dev_stats[dev_id]["score"] += score

        reject_rate = {
            key: (reject_by_type.get(key, 0) / float(total))
            for key, total in total_by_type.items()
            if total > 0
        }

        score_distribution = {
            "lt70": sum(1 for score in scores if score < 70.0),
            "70_79": sum(1 for score in scores if 70.0 <= score < 80.0),
            "80_89": sum(1 for score in scores if 80.0 <= score < 90.0),
            "ge90": sum(1 for score in scores if score >= 90.0),
        }

        first_half = scores[: len(scores) // 2]
        second_half = scores[len(scores) // 2 :]
        prev_avg = (sum(first_half) / float(len(first_half))) if first_half else 0.0
        curr_avg = (sum(second_half) / float(len(second_half))) if second_half else 0.0

        score_trend = MetricTrend(
            name="total_score",
            current=curr_avg,
            previous=prev_avg,
            delta=curr_avg - prev_avg,
            direction="up" if curr_avg > prev_avg else "down" if curr_avg < prev_avg else "flat",
        )

        clusters = [
            FailureCluster(
                failure_mode=mode,
                count=count,
                examples=[mode[:200]],
            )
            for mode, count in failure_modes.most_common(8)
            if mode and mode != "none"
        ]

        now = datetime.now(timezone.utc)
        since = (now - timedelta(days=7)).isoformat()
        recent_xp = self.ledger.get_summary(since=since)
        xp_velocity = float(recent_xp.get("total_xp", 0)) / 7.0

        pair_count = self.pairs.count()
        total_tickets = len(tickets)
        distillation_yield = (pair_count / float(total_tickets)) if total_tickets > 0 else 0.0

        ranking: List[Dict[str, Any]] = []
        for dev_id, stats in dev_stats.items():
            count = max(stats["count"], 1.0)
            ranking.append(
                {
                    "developer": dev_id,
                    "ticket_count": int(stats["count"]),
                    "pass_rate": stats["pass"] / count,
                    "avg_score": stats["score"] / count,
                }
            )
        ranking.sort(key=lambda row: (row["pass_rate"], row["avg_score"]), reverse=True)

        agreement_rates = {
            "action_contract_stub": self.gold_labels.compute_agreement_rate("action_contract_stub", window=20),
            "verdict_override": self.gold_labels.compute_agreement_rate("verdict_override", window=20),
            "gate_policy_recommendation": self.gold_labels.compute_agreement_rate(
                "gate_policy_recommendation", window=20
            ),
        }

        threshold_flags: List[ThresholdFlag] = []
        max_reject = max(reject_rate.values(), default=0.0)
        threshold_flags.append(
            ThresholdFlag(
                level=1,
                metric="reject_rate",
                value=max_reject,
                threshold=self.cfg.reject_threshold,
                triggered=max_reject > self.cfg.reject_threshold,
                reason="Reject rate exceeds threshold" if max_reject > self.cfg.reject_threshold else "",
            )
        )

        min_agreement = min(agreement_rates.values(), default=1.0)
        threshold_flags.append(
            ThresholdFlag(
                level=1,
                metric="agreement_rate",
                value=min_agreement,
                threshold=self.cfg.agreement_threshold,
                triggered=min_agreement < self.cfg.agreement_threshold,
                reason="Agreement rate below threshold" if min_agreement < self.cfg.agreement_threshold else "",
            )
        )

        top_mismatch = max(mismatch_frequency.values(), default=0)
        threshold_flags.append(
            ThresholdFlag(
                level=2,
                metric="oracle_mismatch_repeat",
                value=float(top_mismatch),
                threshold=float(self.cfg.mismatch_repeat),
                triggered=top_mismatch >= self.cfg.mismatch_repeat,
                reason="Recurring oracle mismatch detected" if top_mismatch >= self.cfg.mismatch_repeat else "",
            )
        )

        return AnalysisReport(
            generated_at=_now_iso(),
            ticket_count=len(tickets),
            reject_rate=reject_rate,
            deny_rate=dict(deny_by_phase),
            oracle_mismatch_frequency=dict(mismatch_frequency),
            score_distribution=score_distribution,
            score_trend=score_trend,
            failure_mode_clustering=clusters,
            xp_velocity=xp_velocity,
            distillation_yield=distillation_yield,
            dev_performance_ranking=ranking,
            agreement_rates=agreement_rates,
            threshold_flags=threshold_flags,
        )


__all__ = ["PatternAnalyzer"]
