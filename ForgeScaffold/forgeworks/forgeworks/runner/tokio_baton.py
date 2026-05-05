import json
import time
import yaml
import logging
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from pathlib import Path

logger = logging.getLogger(__name__)


def _model_dump(obj: BaseModel) -> Dict[str, Any]:
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    return obj.dict()

class ValidatedHypothesis(BaseModel):
    """
    Output of Phase 1 (The Scout).
    Contains the researched approach and identified gaps.
    """
    approach_summary: str = Field(default="")
    identified_components: list[str] = Field(default_factory=list)
    risk_assessment: str = Field(default="")
    confidence_score: float = Field(default=0.0)

class SpecContract(BaseModel):
    """
    Output of Phase 2 (The Legislator).
    Contains strict constraints, allowable imports, and the verification plan for the Builder.
    """
    allowed_imports: list[str] = Field(default_factory=list)
    prohibited_actions: list[str] = Field(default_factory=list)
    verification_plan: str = Field(default="")
    architecture_rules: str = Field(default="")

class RelayBaton(BaseModel):
    """
    The serialized state object passed between Relay Phases. 
    State is NOT held in RAM; instead, Tokio flushes this to disk.
    """
    ticket_id: str
    ticket_intent: str
    hypothesis_path: Optional[str] = None
    spec_contract_path: Optional[str] = None
    builder_artifact_path: Optional[str] = None
    sandbox_receipt_path: Optional[str] = None
    judge_verdict_path: Optional[str] = None
    
    # Optional flags to manage state
    current_phase: int = 1
    retry_count: int = 0
    max_retries: int = 3
    last_error_log: Optional[str] = None
    sandbox_directory: Optional[str] = None

    # Per-phase observability (OpenFang-inspired StepResult equivalent)
    # Keys are phase names: "Scout", "Legislator", "Builder", "Judge", "Deployer"
    phase_timing: Dict[str, float] = Field(default_factory=dict)   # wall time in seconds
    phase_tokens: Dict[str, int]   = Field(default_factory=dict)   # tokens consumed

    def record_phase_metric(
        self,
        phase_name: str,
        duration_sec: float,
        tokens: int = 0,
    ) -> None:
        """Record timing and token usage for a completed phase."""
        self.phase_timing[phase_name] = round(duration_sec, 3)
        if tokens:
            self.phase_tokens[phase_name] = tokens
        logger.debug(
            f"📊 Phase metric: {phase_name} duration={duration_sec:.2f}s tokens={tokens}"
        )
    
    @classmethod
    def load_from_disk(cls, filepath: str) -> Optional['RelayBaton']:
        path = Path(filepath)
        if not path.exists():
            return None
        try:
            with open(path, 'r') as f:
                data = json.load(f)
            return cls(**data)
        except Exception as e:
            logger.error(f"Failed to load baton from {filepath}: {e}")
            return None

    def save_to_disk(self, filepath: str):
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(path, 'w') as f:
                json.dump(_model_dump(self), f, indent=2)
            logger.info(f"💾 Flushed RelayBaton state to disk: {filepath}")
        except Exception as e:
            logger.error(f"Failed to save baton to {filepath}: {e}")
            raise

    def get_hypothesis(self) -> Optional[ValidatedHypothesis]:
        if not self.hypothesis_path or not Path(self.hypothesis_path).exists():
            return None
        with open(self.hypothesis_path, 'r') as f:
            data = json.load(f)
        return ValidatedHypothesis(**data)

    def save_hypothesis(self, hypothesis: ValidatedHypothesis, directory: str):
        path = Path(directory) / f"{self.ticket_id}_hypothesis.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w') as f:
            json.dump(_model_dump(hypothesis), f, indent=2)
        self.hypothesis_path = str(path)
        logger.info(f"💾 Flushed ValidatedHypothesis to {path}")

    def get_spec_contract(self) -> Optional[SpecContract]:
        if not self.spec_contract_path or not Path(self.spec_contract_path).exists():
            return None
        with open(self.spec_contract_path, 'r') as f:
            data = yaml.safe_load(f)
        return SpecContract(**data)

    def save_spec_contract(self, contract: SpecContract, directory: str):
        path = Path(directory) / f"{self.ticket_id}_spec_contract.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w') as f:
            yaml.dump(_model_dump(contract), f, default_flow_style=False)
        self.spec_contract_path = str(path)
        logger.info(f"💾 Flushed SpecContract to {path}")
