"""
SAM Model Manager Integration Layer
====================================

Provides a singleton bridge between ModelLibraryManager and Core Engines.
Enables dynamic model switching and notification of all engines when models change.

This is the critical integration layer that connects SAM's Model Library Management
system with the Core Engines, allowing true model updatability.

Author: SAM Development Team
Version: 1.0.0
"""

import logging
from typing import Dict, List, Optional, Callable, Any
from threading import Lock
from pathlib import Path
import time

from forgeworks.core_engines.integration.model_library_manager import ModelLibraryManager, ModelInfo, DownloadedModel
from forgeworks.core_engines.engines.model_interface import BaseModelEngine, ModelStatus
from forgeworks.core_engines.monitoring.model_performance_monitor import get_performance_monitor

logger = logging.getLogger(__name__)


class ModelManagerIntegration:
    """
    Singleton bridge between ModelLibraryManager and Core Engines.
    
    Responsibilities:
    - Maintain reference to active model engine
    - Notify all registered engines when model changes
    - Provide unified interface for model switching
    - Cache loaded engines for performance
    - Handle model validation before switching
    """
    
    _instance = None
    _lock = Lock()
    
    def __new__(cls):
        """Ensure singleton pattern."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """Initialize the integration layer."""
        if self._initialized:
            return

        self.logger = logging.getLogger(f"{__name__}.ModelManagerIntegration")

        # Core components
        self.library_manager = ModelLibraryManager()
        self.active_engine: Optional[BaseModelEngine] = None
        self.active_model_id: Optional[str] = None

        # Engine caching
        self.engine_cache: Dict[str, BaseModelEngine] = {}

        # Listener pattern for model change notifications
        self.listeners: List[Callable[[BaseModelEngine], None]] = []

        # Thread safety
        self._switch_lock = Lock()

        # Phase 5: Performance monitoring
        self.performance_monitor = get_performance_monitor()
        self.model_switch_times: Dict[str, float] = {}  # Track when models were switched

        # Phase 3: Register as listener with ModelLibraryManager
        self.library_manager.register_model_switch_listener(self._on_model_switched_from_library)

        self._initialized = True
        self.logger.info("✅ ModelManagerIntegration initialized (with Phase 5 performance monitoring)")
    
    @classmethod
    def get_instance(cls) -> "ModelManagerIntegration":
        """Get the singleton instance."""
        return cls()
    
    def get_active_engine(self) -> Optional[BaseModelEngine]:
        """
        Get the currently active model engine.
        
        Returns:
            The active BaseModelEngine instance, or None if no model is active
        """
        # [PHASE 3] Strict Lazy Loading: Do NOT call _load_default_engine here.
        # This prevents HTTP/Ollama overhead during the critical startup sequence.
        # Engines should be loaded only when the first actual request is made.
        return self.active_engine

    def generate(self, prompt: str, **kwargs) -> str:
        """
        Standardized generation entry point with lazy loading.
        
        This is the "smart" entry point that ensures a model is loaded
        before attempting inference.
        """
        if self.active_engine is None:
            self.logger.info("🚀 First generation request received - triggering lazy model load")
            if not self._load_default_engine():
                raise RuntimeError("Failed to load default model engine for generation")
        
        return self.active_engine.generate(prompt, **kwargs)

    def embed(self, text: str) -> List[float]:
        """
        Standardized embedding entry point with lazy loading.
        """
        if self.active_engine is None:
            self.logger.info("🚀 First embedding request received - triggering lazy model load")
            if not self._load_default_engine():
                raise RuntimeError("Failed to load default model engine for embedding")
        
        return self.active_engine.embed(text)
    
    def _load_default_engine(self) -> bool:
        """
        Load the default model engine.
        
        Returns:
            True if default engine loaded successfully, False otherwise
        """
        try:
            # Try to load DeepSeek as default
            from forgeworks.core_engines.engines.model_interface import DeepSeekEngine
            
            self.logger.info("Loading default engine: DeepSeek")
            engine = DeepSeekEngine()
            
            if engine.load_model():
                self.active_engine = engine
                self.active_model_id = "deepseek"
                self.engine_cache["deepseek"] = engine
                self.logger.info("✅ Default engine loaded successfully")
                return True
            else:
                self.logger.error("❌ Failed to load default engine")
                return False
                
        except Exception as e:
            self.logger.error(f"❌ Error loading default engine: {e}")
            return False
    
    def switch_model(self, model_id: str, unload_previous: bool = False) -> bool:
        """
        Switch to a different model.
        
        Args:
            model_id: ID of the model to switch to
            unload_previous: If True, explicitly unload the current model before loading the new one
            
        Returns:
            True if switch successful, False otherwise
        """
        with self._switch_lock:
            try:
                # Check if model is already active
                if self.active_model_id == model_id and self.active_engine is not None:
                    self.logger.info(f"Model {model_id} is already active")
                    return True
                
                # [PHASE 6] Memory Guard: Unload current engine if requested
                if unload_previous and self.active_engine:
                    current_id = self.active_model_id
                    self.logger.info(f"🛡️ Memory Guard: Unloading {current_id} before switching to {model_id}")
                    try:
                        self.active_engine.unload_model()
                        # Also trigger Ollama unload via ConfigManager if possible
                        from forgeworks.core_engines.config.model_config_manager import get_model_config_manager
                        get_model_config_manager().unload_model(current_id)
                    except Exception as unload_error:
                        self.logger.warning(f"Failed to fully unload {current_id}: {unload_error}")

                # Check if model is in cache
                if model_id in self.engine_cache:
                    self.logger.info(f"Loading {model_id} from cache")
                    engine = self.engine_cache[model_id]
                    # Ensure it's actually loaded if we unload it previously
                    if not engine.is_loaded:
                        engine.load_model()
                    self.active_engine = engine
                    self.active_model_id = model_id
                    self._notify_listeners(self.active_engine)
                    return True
                
                # Load new engine based on model family
                engine = self._create_engine_for_model(model_id)
                
                if engine is None:
                    self.logger.error(f"❌ Failed to create engine for model {model_id}")
                    return False
                
                # Load the model
                if not engine.load_model():
                    self.logger.error(f"❌ Failed to load model {model_id}")
                    return False
                
                # Switch successful
                self.active_engine = engine
                self.active_model_id = model_id
                self.engine_cache[model_id] = engine
                
                # Notify all listeners
                self._notify_listeners(engine)
                
                self.logger.info(f"✅ Successfully switched to model: {model_id}")
                return True
                
            except Exception as e:
                self.logger.error(f"❌ Error switching to model {model_id}: {e}")
                return False
    
    def _create_engine_for_model(self, model_id: str) -> Optional[BaseModelEngine]:
        """
        Create an engine instance for a specific model.
        
        Args:
            model_id: ID of the model
            
        Returns:
            BaseModelEngine instance or None if creation failed
        """
        try:
            # Import engine classes
            from forgeworks.core_engines.engines.model_interface import (
                DeepSeekEngine, LlamaEngine, JambaEngine, QwenEngine, GLMEngine
            )
            
            model_family = None
            
            # Try to get model info from library catalog
            if model_id in self.library_manager.available_models:
                model_info = self.library_manager.available_models[model_id]
                model_family = model_info.model_family.lower()
            else:
                # FALLBACK: Infer model family from Ollama model name
                self.logger.info(f"⚡ Model {model_id} not in catalog, inferring family from name...")
                model_id_lower = model_id.lower()
                
                if 'qwen' in model_id_lower:
                    model_family = 'qwen'
                elif 'llama' in model_id_lower:
                    model_family = 'llama'
                elif 'deepseek' in model_id_lower:
                    model_family = 'deepseek'
                elif 'glm' in model_id_lower or 'ocr' in model_id_lower:
                    model_family = 'glm'
                elif 'jamba' in model_id_lower:
                    model_family = 'jamba'
                else:
                    # Default to DeepSeek for unknown models
                    model_family = 'deepseek'
                    self.logger.warning(f"⚠️ Unknown model family for {model_id}, defaulting to DeepSeek")
            
            # Create appropriate engine based on model family
            if model_family == "deepseek":
                return DeepSeekEngine(engine_id=model_id, model_name=model_id)
            elif model_family == "llama":
                return LlamaEngine(engine_id=model_id, model_name=model_id)
            elif model_family == "jamba":
                return JambaEngine(engine_id=model_id, model_name=model_id)
            elif model_family == "qwen":
                return QwenEngine(engine_id=model_id, model_name=model_id)
            elif model_family == "glm":
                return GLMEngine(engine_id=model_id, model_name=model_id)
            else:
                self.logger.error(f"Unknown model family: {model_family}")
                return None
                
        except Exception as e:
            self.logger.error(f"Error creating engine for model {model_id}: {e}")
            return None

    
    def register_listener(self, callback: Callable[[BaseModelEngine], None]) -> None:
        """
        Register a callback to be notified when model changes.
        
        Args:
            callback: Function to call when model switches. Receives new engine as argument.
        """
        if callback not in self.listeners:
            self.listeners.append(callback)
            self.logger.debug(f"Registered listener: {callback.__name__}")
    
    def unregister_listener(self, callback: Callable[[BaseModelEngine], None]) -> None:
        """
        Unregister a callback.
        
        Args:
            callback: Function to unregister
        """
        if callback in self.listeners:
            self.listeners.remove(callback)
            self.logger.debug(f"Unregistered listener: {callback.__name__}")
    
    def _notify_listeners(self, new_engine: BaseModelEngine) -> None:
        """
        Notify all registered listeners of model change.

        Args:
            new_engine: The new active engine
        """
        for listener in self.listeners:
            try:
                listener(new_engine)
            except Exception as e:
                self.logger.error(f"Error notifying listener {listener.__name__}: {e}")

    def _on_model_switched_from_library(self, model_id: str, model_info: ModelInfo) -> None:
        """
        Handle model switch notification from ModelLibraryManager.

        Phase 3: Called when ModelLibraryManager.activate_model() is called.
        This bridges the library manager to the integration layer.

        Args:
            model_id: ID of the newly activated model
            model_info: ModelInfo of the newly activated model
        """
        try:
            self.logger.info(f"🔄 Model switch notification from library: {model_id}")

            # Switch to the new model
            if self.switch_model(model_id):
                self.logger.info(f"✅ Successfully switched to {model_id} via library notification")
            else:
                self.logger.error(f"❌ Failed to switch to {model_id} via library notification")

        except Exception as e:
            self.logger.error(f"❌ Error handling model switch from library: {e}")

    def get_available_models(self) -> List[ModelInfo]:
        """Get list of available models."""
        return self.library_manager.get_available_models()
    
    def get_downloaded_models(self) -> List[DownloadedModel]:
        """Get list of downloaded models."""
        return self.library_manager.get_downloaded_models()
    
    def get_model_status(self, model_id: str) -> str:
        """Get status of a model."""
        return self.library_manager.get_model_status(model_id)
    
    def download_model(self, model_id: str) -> bool:
        """Download a model."""
        return self.library_manager.download_model(model_id)
    
    def get_download_progress(self, model_id: str) -> Optional[Dict[str, Any]]:
        """Get download progress for a model."""
        return self.library_manager.get_download_progress(model_id)
    
    def cancel_download(self, model_id: str) -> bool:
        """Cancel a model download."""
        return self.library_manager.cancel_download(model_id)
    
    def delete_model(self, model_id: str) -> bool:
        """Delete a downloaded model."""
        return self.library_manager.delete_model(model_id)

    def activate_model(self, model_id: str) -> bool:
        """
        Activate a model through the library manager.

        Phase 3: Public API for activating models. This triggers the full
        model switching pipeline including listener notifications.

        Args:
            model_id: ID of the model to activate

        Returns:
            True if activation successful, False otherwise
        """
        return self.library_manager.activate_model(model_id)

    def get_active_model_info(self) -> Optional[Dict[str, Any]]:
        """
        Get information about the currently active model.

        Returns:
            Dictionary with model info or None if no model is active
        """
        return self.library_manager.get_active_model()

    def get_validation_report(self, model_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the validation report for a model.

        Phase 4: Returns validation results from model switching.

        Args:
            model_id: ID of the model

        Returns:
            Validation report or None if not available
        """
        return self.library_manager.get_validation_report(model_id)

    # ============================================================================
    # Phase 5: Performance Monitoring Integration
    # ============================================================================

    def record_inference_metric(
        self,
        inference_time_ms: float,
        tokens_generated: int,
        context_length: int,
        success: bool = True,
        error_message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Record an inference metric for the currently active model.

        Phase 5: Called by Core Engines to report inference performance.

        Args:
            inference_time_ms: Time taken for inference in milliseconds
            tokens_generated: Number of tokens generated
            context_length: Length of input context
            success: Whether inference was successful
            error_message: Error message if failed
            metadata: Additional metadata
        """
        if self.active_model_id:
            self.performance_monitor.record_inference(
                model_id=self.active_model_id,
                inference_time_ms=inference_time_ms,
                tokens_generated=tokens_generated,
                context_length=context_length,
                success=success,
                error_message=error_message,
                metadata=metadata
            )

    def establish_performance_baseline(self, model_id: Optional[str] = None):
        """
        Establish a performance baseline for a model.

        Phase 5: Called after model switch to set baseline metrics.

        Args:
            model_id: Model ID (defaults to active model)
        """
        target_model = model_id or self.active_model_id
        if target_model:
            self.performance_monitor.set_baseline(target_model)
            self.model_switch_times[target_model] = time.time()
            self.logger.info(f"✅ Performance baseline established for {target_model}")

    def get_performance_stats(self, model_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Get performance statistics for a model.

        Phase 5: Returns aggregated performance metrics.

        Args:
            model_id: Model ID (defaults to active model)

        Returns:
            Performance statistics or None if not available
        """
        target_model = model_id or self.active_model_id
        if target_model:
            stats = self.performance_monitor.get_stats(target_model)
            if stats:
                return stats.to_dict()
        return None

    def compare_model_performance(self, model_ids: List[str]) -> Dict[str, Any]:
        """
        Compare performance of multiple models.

        Phase 5: Enables A/B testing and model comparison.

        Args:
            model_ids: List of model IDs to compare

        Returns:
            Comparison dictionary with performance metrics
        """
        return self.performance_monitor.compare_models(model_ids)

    def get_performance_report(self) -> Dict[str, Any]:
        """
        Get comprehensive performance report for all models.

        Phase 5: Returns full performance monitoring data.

        Returns:
            Performance report dictionary
        """
        return self.performance_monitor.get_performance_report()


# Global convenience function
def get_model_manager_integration() -> ModelManagerIntegration:
    """Get the global ModelManagerIntegration instance."""
    return ModelManagerIntegration.get_instance()

