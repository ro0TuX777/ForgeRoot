"""
ForgeWorks 5-Phase Relay Runner
================================
Scout → Legislator → Builder → Judge → Deployer
"""
from .phase1_scout import run_scout
from .phase2_legislator import run_legislator
from .phase3_builder import run_builder
from .phase4_judge import run_judge
from .phase5_deployer import run_deployer

__all__ = ["run_scout", "run_legislator", "run_builder", "run_judge", "run_deployer"]
