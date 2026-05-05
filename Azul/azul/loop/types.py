"""Core types for Azul recursive loop."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class MetricTrend:
    name: str
    current: float
    previous: float
    delta: float
    direction: str


@dataclass
class FailureCluster:
    failure_mode: str
    count: int
    examples: List[str] = field(default_factory=list)


@dataclass
class ThresholdFlag:
    level: int
    metric: str
    value: float
    threshold: float
    triggered: bool
    reason: str


@dataclass
class GoldLabel:
    label_id: str
    artifact_type: str
    original: Dict[str, Any]
    approved: Dict[str, Any]
    diff: Dict[str, Any]
    reviewer_id: str
    timestamp: str
    agreement: bool
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AnalysisReport:
    generated_at: str
    ticket_count: int
    reject_rate: Dict[str, float]
    deny_rate: Dict[str, float]
    oracle_mismatch_frequency: Dict[str, int]
    score_distribution: Dict[str, int]
    score_trend: MetricTrend
    failure_mode_clustering: List[FailureCluster]
    xp_velocity: float
    distillation_yield: float
    dev_performance_ranking: List[Dict[str, Any]]
    agreement_rates: Dict[str, float]
    threshold_flags: List[ThresholdFlag]


@dataclass
class DriftItem:
    artifact_type: str
    artifact_id: str
    path: str
    status: str
    change_count: int
    direction: str
    field_changes: Dict[str, Any] = field(default_factory=dict)
    recommendation: str = ""


@dataclass
class DriftReport:
    scan_date: str
    contracts_compared: int
    contracts_drifted: int
    policies_compared: int
    policies_drifted: int
    drift_direction: str
    gold_labels_since: int
    agreement_rate_trend: MetricTrend
    recommendations: List[str] = field(default_factory=list)
    items: List[DriftItem] = field(default_factory=list)
    baseline_new_count: int = 0


@dataclass
class PromptDiff:
    target_file: str
    additions: List[str]
    removals: List[str]
    examples: List[str]
    rationale: str


@dataclass
class ContractPatch:
    contract_name: str
    field_changes: Dict[str, Any]
    rationale: str


@dataclass
class PolicyAdjustment:
    domain: str
    threshold_changes: Dict[str, Any]
    rationale: str
    expected_impact: str


@dataclass
class DistillationBatch:
    pair_count: int
    avg_score: float
    domains: List[str]
    manifest_path: str


@dataclass
class ImprovementPlan:
    prompt_diffs: List[PromptDiff] = field(default_factory=list)
    contract_patches: List[ContractPatch] = field(default_factory=list)
    policy_adjustments: List[PolicyAdjustment] = field(default_factory=list)
    distillation_batch: Optional[DistillationBatch] = None
    requires_human_review: bool = True


@dataclass
class LoopReport:
    generated_at: str
    trigger: str
    analysis: AnalysisReport
    drift: DriftReport
    plan: ImprovementPlan


def to_dict(value: Any) -> Dict[str, Any]:
    return asdict(value)
