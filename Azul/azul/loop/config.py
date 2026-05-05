"""Configuration for Azul recursive loop."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from ..config import AZUL_DATA_DIR, GATE_POLICIES_DIR


_REPO_ROOT = Path(__file__).resolve().parents[3]


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class LoopConfig:
    enabled: bool
    threshold_window: int
    reject_threshold: float
    agreement_threshold: float
    mismatch_repeat: int
    override_repeat: int
    distill_batch_size: int
    distill_min_score: float
    drift_cadence: str
    report_cadence: str
    distill_cadence: str
    azul_data_dir: Path
    contracts_dir: Path
    policies_dir: Path

    @property
    def gold_labels_dir(self) -> Path:
        return self.azul_data_dir / "gold_labels"

    @property
    def gold_labels_path(self) -> Path:
        return self.gold_labels_dir / "gold_labels.jsonl"

    @property
    def reports_dir(self) -> Path:
        return self.azul_data_dir / "improvement_reports"

    @property
    def drift_reports_dir(self) -> Path:
        return self.azul_data_dir / "drift_reports"

    @property
    def distillation_batches_dir(self) -> Path:
        return self.azul_data_dir / "distillation_batches"

    @property
    def loop_state_path(self) -> Path:
        return self.azul_data_dir / "loop_state.json"

    @property
    def baseline_contracts_dir(self) -> Path:
        return self.azul_data_dir / "baselines" / "contracts"

    @property
    def baseline_policies_dir(self) -> Path:
        return self.azul_data_dir / "baselines" / "policies"


def load_loop_config() -> LoopConfig:
    data_root = Path(os.environ.get("AZUL_DATA_DIR", AZUL_DATA_DIR)).resolve()

    contracts_root = Path(
        os.environ.get("FORGE_ATLAS_CATALOG_PATH", str(_REPO_ROOT / "action_catalogs"))
    ).resolve()
    active_contracts = contracts_root / "active"
    contracts_dir = active_contracts if active_contracts.exists() else contracts_root

    policies_dir = Path(os.environ.get("AZUL_GATE_POLICIES_DIR", str(GATE_POLICIES_DIR))).resolve()

    return LoopConfig(
        enabled=_env_bool("FORGE_LOOP_ENABLED", True),
        threshold_window=max(1, _env_int("FORGE_LOOP_THRESHOLD_WINDOW", 50)),
        reject_threshold=_env_float("FORGE_LOOP_REJECT_THRESHOLD", 0.30),
        agreement_threshold=_env_float("FORGE_LOOP_AGREEMENT_THRESHOLD", 0.70),
        mismatch_repeat=max(1, _env_int("FORGE_LOOP_MISMATCH_REPEAT", 3)),
        override_repeat=max(1, _env_int("FORGE_LOOP_OVERRIDE_REPEAT", 5)),
        distill_batch_size=max(1, _env_int("FORGE_LOOP_DISTILL_BATCH_SIZE", 100)),
        distill_min_score=_env_float("FORGE_LOOP_DISTILL_MIN_SCORE", 90.0),
        drift_cadence=os.environ.get("FORGE_LOOP_DRIFT_CADENCE", "weekly"),
        report_cadence=os.environ.get("FORGE_LOOP_REPORT_CADENCE", "weekly"),
        distill_cadence=os.environ.get("FORGE_LOOP_DISTILL_CADENCE", "monthly"),
        azul_data_dir=data_root,
        contracts_dir=contracts_dir,
        policies_dir=policies_dir,
    )


def ensure_loop_dirs(cfg: LoopConfig) -> None:
    dirs = [
        cfg.azul_data_dir,
        cfg.gold_labels_dir,
        cfg.reports_dir,
        cfg.drift_reports_dir,
        cfg.distillation_batches_dir,
        cfg.baseline_contracts_dir,
        cfg.baseline_policies_dir,
    ]
    for directory in dirs:
        directory.mkdir(parents=True, exist_ok=True)
