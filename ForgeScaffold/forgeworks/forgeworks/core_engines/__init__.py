"""
ForgeWorks Core Engines
========================
Reusable model-switching framework ported from SAM's CoreEngines.
Provides SmartModelSelector, ModelConfigManager, and ModelManagerIntegration.
"""

from .integration.model_manager_integration import (
    ModelManagerIntegration,
    get_model_manager_integration,
)
from .selection.smart_model_selector import SmartModelSelector
from .config.model_config_manager import get_model_config_manager

__all__ = [
    "ModelManagerIntegration",
    "get_model_manager_integration",
    "SmartModelSelector",
    "get_model_config_manager",
]
