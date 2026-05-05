#!/usr/bin/env python3
"""
Smart Model Selector Service
Automatically selects the best LLM model based on query type and intent.

Model Selection Strategy:
- Qwen2.5-Coder:7b: Code generation, technical documentation, programming tasks
- DeepSeek-R1: Reasoning, analysis, complex problem-solving
- llama3.2:3b: Fallback for general queries, lightweight tasks
"""

import logging
import re
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class ModelSelection:
    """Result of model selection."""
    model_name: str
    model_type: str  # 'code', 'reasoning', 'general'
    confidence: float
    reason: str

    @property
    def model_id(self) -> str:
        """Alias for model_name to support legacy code."""
        return self.model_name

class SmartModelSelector:
    """
    Intelligent model selector that chooses the optimal LLM based on query characteristics.
    Dynamically loads model configuration from ModelConfigManager.
    """
    
    # Default Model configurations (fallback if config unavailable)
    DEFAULT_MODELS = {
        'code': {
            'name': 'qwen2.5-coder:7b',
            'description': 'Qwen2.5-Coder - Specialized code generation model',
            'strengths': ['code generation', 'debugging', 'technical documentation', 'API usage']
        },
        'reasoning': {
            'name': 'hf.co/unsloth/DeepSeek-R1-Distill-Qwen-32B-GGUF:Q4_K_M',
            'description': 'DeepSeek-R1 (32B) - Advanced reasoning and analysis',
            'strengths': ['complex reasoning', 'analysis', 'problem decomposition', 'strategic thinking']
        },
        'general': {
            'name': 'ministral-3:8b',
            'description': 'Ministral 3 - Fast, capable general-purpose model',
            'strengths': ['general chat', 'simple queries', 'quick responses']
        },
        'vision': {
            'name': 'glm-ocr',
            'description': 'GLM-OCR - SOTA Multimodal and OCR model',
            'strengths': ['OCR', 'diagram analysis', 'table extraction', 'visual reasoning']
        }
    }
    
    # Runtime models (loaded from config)
    MODELS = {}
    
    # Code generation patterns (highest priority)
    CODE_PATTERNS = [
        # Function/script creation
        r'\b(write|create|generate|build|make)\s+(a\s+)?(function|script|code|program|class|method)\b',
        r'\bhelp\s+me\s+(write|create|code)\b',
        
        # Programming languages
        r'\b(python|javascript|java|c\+\+|rust|go|typescript|ruby|php)\s+(function|code|script|class)\b',
        r'\bwrite\s+(python|javascript|java|c\+\+|rust|go|typescript|ruby|php)\b',
        
        # File operations in code context
        r'\bfunction\s+that\s+(reads|writes|parses|processes|handles)\b',
        r'\bscript\s+that\s+(reads|writes|parses|processes|handles)\b',
        r'\bcode\s+that\s+(reads|writes|parses|processes|handles)\b',
        
        # Specific coding tasks
        r'\b(parse|extract|process)\s+(json|xml|csv|yaml|html)\b',
        r'\b(api|rest|graphql|endpoint)\s+(call|request|integration)\b',
        r'\b(regex|regular\s+expression)\s+',
        r'\b(algorithm|data\s+structure|implementation)\b',
        r'\b(debug|fix|refactor|optimize)\s+(code|function|script)\b',
        
        # Code-related questions
        r'\bhow\s+to\s+(read|write|parse|process)\s+.*\s+(file|data|json|xml|csv)\b',
        r'\bhow\s+do\s+i\s+(read|write|parse|process)\s+.*\s+(file|data|json|xml|csv)\b',
        
        # Error handling in code
        r'\b(error\s+handling|exception\s+handling|try\s+catch|gracefully)\b.*\b(code|function|script)\b',
        r'\bmake\s+sure\s+it\s+handles\s+errors\b',
    ]
    
    # Reasoning patterns (medium priority)
    REASONING_PATTERNS = [
        # Analysis and reasoning
        r'\b(analyze|explain|why|how\s+does|what\s+is\s+the\s+reason)\b',
        r'\b(compare|contrast|difference\s+between|pros\s+and\s+cons)\b',
        r'\b(strategy|approach|methodology|framework)\b',
        r'\b(evaluate|assess|judge|determine)\b',
        
        # Complex problem-solving
        r'\b(solve|solution|resolve|address)\s+.*\s+(problem|issue|challenge)\b',
        r'\b(think\s+through|reason\s+about|consider)\b',
        r'\b(implications|consequences|trade-offs)\b',
        
        # Research and investigation
        r'\b(research|investigate|explore|study)\b',
        r'\b(what\s+are\s+the|tell\s+me\s+about|explain\s+the)\b',
    ]
    
    # Vision/Multimodal patterns (Phase 3 Integration)
    VISION_PATTERNS = [
        r'\b(analyze|look\s+at|parse|process|describe)\s+(the\s+|this\s+|my\s+)?(image|picture|photo|screenshot|diagram|chart|graph)\b',
        r'\bwhat\s+is\s+(in|on|inside)\s+(the\s+|this\s+|my\s+)?(image|picture|photo|screenshot|diagram)\b',
        r'\b(extract|get|read|ocr)\s+(the\s+|this\s+|my\s+)?(text|data|tables|formulas|info|information)\s+(from|in)\s+(the\s+|this\s+|my\s+)?(image|screenshot|pdf|file)\b',
        r'\b(ocr|handwriting|transcribe)\b',
        r'\bvisual\s+reasoning\b',
    ]
    
    def __init__(self):
        """Initialize the smart model selector with config-based models."""
        self.selection_count = 0
        self.model_usage_stats = {
            'code': 0,
            'reasoning': 0,
            'general': 0,
            'vision': 0
        }
        
        # Load models from configuration
        self._load_models_from_config()
        
        logger.info("🧠 SmartModelSelector initialized with 3 models")
        logger.info(f"   - Code: {self.MODELS['code']['name']}")
        logger.info(f"   - Reasoning: {self.MODELS['reasoning']['name']}")
        logger.info(f"   - General: {self.MODELS['general']['name']}")
    
    def _load_models_from_config(self):
        """Load model configuration from ModelConfigManager."""
        try:
            from services.model_config_manager import get_model_config_manager
            
            config_manager = get_model_config_manager()
            config = config_manager.load_config()
            
            # Update MODELS with config values
            self.MODELS = {
                'code': {
                    'name': config.get('code_model', self.DEFAULT_MODELS['code']['name']),
                    'description': self.DEFAULT_MODELS['code']['description'],
                    'strengths': self.DEFAULT_MODELS['code']['strengths']
                },
                'reasoning': {
                    'name': config.get('reasoning_model', self.DEFAULT_MODELS['reasoning']['name']),
                    'description': self.DEFAULT_MODELS['reasoning']['description'],
                    'strengths': self.DEFAULT_MODELS['reasoning']['strengths']
                },
                'general': {
                    'name': config.get('general_model', self.DEFAULT_MODELS['general']['name']),
                    'description': self.DEFAULT_MODELS['general']['description'],
                    'strengths': self.DEFAULT_MODELS['general']['strengths']
                },
                'vision': {
                    'name': config.get('vision_model', self.DEFAULT_MODELS['vision']['name']),
                    'description': self.DEFAULT_MODELS['vision']['description'],
                    'strengths': self.DEFAULT_MODELS['vision']['strengths']
                }
            }
            
            logger.info("✅ Loaded models from configuration")
            
        except Exception as e:
            logger.warning(f"⚠️ Failed to load config, using defaults: {e}")
            # Fall back to default models
            self.MODELS = self.DEFAULT_MODELS.copy()
    
    def reload_config(self):
        """
        Reload model configuration from ModelConfigManager.
        
        This method is called when the user changes model selection in the
        Core Engines UI to immediately apply the new configuration.
        """
        logger.info("🔄 Reloading model configuration...")
        self._load_models_from_config()
        logger.info("✅ Model configuration reloaded")
    
    def select_model(self, query: str, context: Optional[Dict[str, Any]] = None, task_type: Optional[str] = None) -> ModelSelection:
        """
        Select the optimal model for the given query or task.
        
        Args:
            query: User query string or task description
            context: Optional context information
            task_type: Optional explicit task type ('code', 'reasoning', 'general', 'vision')
            
        Returns:
            ModelSelection with chosen model and reasoning
        """
        self.selection_count += 1
        query_lower = query.lower() if query else ""
        
        # Priority -2: Resource Efficiency Mode (Pinned Model)
        # NOTE: Code tasks are EXEMPT — reasoning models burn tokens on <think>
        # blocks and return empty code. Code tasks MUST use the code model.
        try:
            # from sam.config import get_sam_config  # SAM-specific
            sam_config = get_sam_config()
            if sam_config.resource_efficiency_mode and task_type not in ['code', 'vision']:
                pinned_model = sam_config.pinned_model_name
                
                # Check if we have a specific reasoning model configured that should take precedence
                reasoning_model = self.MODELS.get('reasoning', {}).get('name')
                if reasoning_model and task_type == 'reasoning':
                    pinned_model = reasoning_model
                    
                logger.info(f"🚀 RESOURCE EFFICIENCY MODE ACTIVE - Pinning task {task_type or 'general'} to {pinned_model}")
                return ModelSelection(
                    model_name=pinned_model,
                    model_type=task_type or 'general',
                    confidence=1.0,
                    reason=f"Resource Efficiency Mode active ({'Reasoning Override' if reasoning_model and task_type == 'reasoning' else 'Model Pinning'})"
                )
        except Exception as e:
            logger.debug(f"Could not check resource efficiency mode: {e}")

        # Priority -1: Explicit task_type override
        if task_type and task_type in self.MODELS:
            logger.info(f"🎯 Explicit task type '{task_type}' requested - Selecting {self.MODELS[task_type]['name']}")
            self.model_usage_stats[task_type] += 1
            return ModelSelection(
                model_name=self.MODELS[task_type]['name'],
                model_type=task_type,
                confidence=1.0,
                reason=f"Explicit task type override: {task_type}"
            )

        # Priority 0: Check for Vision/Multimodal patterns (Highest priority for images)
        vision_score = self._calculate_pattern_score(query_lower, self.VISION_PATTERNS)
        if vision_score > 0.4:
            logger.info(f"👁️ Vision/OCR task detected (score: {vision_score:.2f}) - Selecting GLM-OCR")
            self.model_usage_stats['vision'] += 1
            return ModelSelection(
                model_name=self.MODELS['vision']['name'],
                model_type='vision',
                confidence=min(vision_score, 1.0),
                reason=f"Visual/Multimodal query detected (confidence: {vision_score:.2f})"
            )

        # Priority 1: Check for code generation patterns
        code_score = self._calculate_pattern_score(query_lower, self.CODE_PATTERNS)
        if code_score > 0:
            logger.info(f"💻 Code generation detected (score: {code_score:.2f}) - Selecting Qwen2.5-Coder")
            self.model_usage_stats['code'] += 1
            return ModelSelection(
                model_name=self.MODELS['code']['name'],
                model_type='code',
                confidence=min(code_score, 1.0),
                reason=f"Code generation query detected (confidence: {code_score:.2f})"
            )
        
        # Priority 2: Check for reasoning patterns
        reasoning_score = self._calculate_pattern_score(query_lower, self.REASONING_PATTERNS)
        if reasoning_score > 0.3:  # Lower threshold for reasoning
            logger.info(f"🧠 Reasoning task detected (score: {reasoning_score:.2f}) - Selecting DeepSeek-R1")
            self.model_usage_stats['reasoning'] += 1
            return ModelSelection(
                model_name=self.MODELS['reasoning']['name'],
                model_type='reasoning',
                confidence=min(reasoning_score, 1.0),
                reason=f"Reasoning/analysis query detected (confidence: {reasoning_score:.2f})"
            )
        
        # Priority 3: Default to general model for simple queries
        logger.info(f"💬 General query detected - Selecting ministral-3:8b")
        self.model_usage_stats['general'] += 1
        return ModelSelection(
            model_name=self.MODELS['general']['name'],
            model_type='general',
            confidence=0.5,
            reason="General query - using lightweight model"
        )
    
    def _calculate_pattern_score(self, query: str, patterns: list) -> float:
        """
        Calculate a score based on pattern matches.
        
        Args:
            query: Query string (lowercase)
            patterns: List of regex patterns to match
            
        Returns:
            Score between 0 and 1 (can exceed 1 for multiple matches)
        """
        score = 0.0
        matches = 0
        
        for pattern in patterns:
            if re.search(pattern, query, re.IGNORECASE):
                matches += 1
                score += 0.5  # Each match adds 0.5 to score
        
        # Bonus for multiple matches (indicates strong signal)
        if matches > 1:
            score += 0.3 * (matches - 1)
        
        return score
    
    def get_model_info(self, model_type: str) -> Dict[str, Any]:
        """Get information about a specific model type."""
        return self.MODELS.get(model_type, {})
    
    def get_usage_stats(self) -> Dict[str, Any]:
        """Get usage statistics for all models."""
        total = sum(self.model_usage_stats.values())
        return {
            'total_selections': self.selection_count,
            'model_usage': self.model_usage_stats,
            'usage_percentages': {
                model_type: (count / total * 100) if total > 0 else 0
                for model_type, count in self.model_usage_stats.items()
            }
        }
    
    def override_model(self, model_type: str) -> Optional[str]:
        """
        Manually override model selection.
        
        Args:
            model_type: 'code', 'reasoning', or 'general'
            
        Returns:
            Model name if valid, None otherwise
        """
        if model_type in self.MODELS:
            return self.MODELS[model_type]['name']
        return None


# Global instance
_selector_instance = None

def get_model_selector() -> SmartModelSelector:
    """Get or create the global SmartModelSelector instance."""
    global _selector_instance
    if _selector_instance is None:
        _selector_instance = SmartModelSelector()
    return _selector_instance

