"""
SAM 2.0 Model Interface - Compatibility Layer
=============================================

This module provides a unified interface for SAM to interact with different
model architectures (Transformer vs Hybrid Linear Attention) seamlessly.

The ModelInterface abstraction enables:
- Seamless switching between model architectures
- Fallback mechanisms for reliability
- A/B testing capabilities
- Gradual migration support
- Performance monitoring

Author: SAM Development Team
Version: 1.0.0
"""

import abc
import time
import logging
import requests
import json
from typing import Dict, List, Any, Optional, Union, Tuple
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

class ModelType(Enum):
    """Supported model types."""
    TRANSFORMER = "transformer"
    HYBRID_LINEAR = "hybrid_linear"
    MOCK = "mock"  # For testing

class ModelStatus(Enum):
    """Model status indicators."""
    READY = "ready"
    LOADING = "loading"
    ERROR = "error"
    UNAVAILABLE = "unavailable"

@dataclass
class ModelConfig:
    """Configuration for model instances."""
    model_type: ModelType
    model_name: str
    api_url: str
    max_context_length: int
    timeout_seconds: int = 300
    temperature: float = 0.7
    max_tokens: int = 1000
    fallback_enabled: bool = True
    performance_monitoring: bool = True

@dataclass
class GenerationRequest:
    """Standardized generation request."""
    prompt: str
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    top_p: Optional[float] = None
    stop_sequences: Optional[List[str]] = None
    context_length_hint: Optional[int] = None
    include_logprobs: bool = False
    tools: Optional[List[Dict[str, Any]]] = None
    tool_choice: Optional[Union[str, Dict[str, Any]]] = None
    request_timeout: Optional[int] = None
    stream: Optional[bool] = None
    # Model Relay Race: per-request model switching
    model_override: Optional[str] = None  # Use a different Ollama model for this request
    keep_alive: Optional[str] = None      # Ollama keep_alive (e.g. "0" to unload immediately)
    system_prompt: Optional[str] = None
    context: Optional[List[Dict[str, Any]]] = None

@dataclass
class GenerationResponse:
    """Standardized generation response."""
    text: str
    model_type: ModelType
    inference_time: float
    context_length: int
    success: bool
    error_message: Optional[str] = None
    performance_metrics: Optional[Dict[str, Any]] = None
    logprobs: Optional[List[Any]] = None
    entropy: Optional[float] = None

@dataclass
class ModelPerformanceMetrics:
    """Performance metrics for model monitoring."""
    total_requests: int
    successful_requests: int
    average_inference_time: float
    average_context_length: float
    error_rate: float
    last_request_time: float

class ModelInterface(abc.ABC):
    """Abstract base class for all model implementations."""

    def __init__(self, config: ModelConfig):
        self.config = config
        self.status = ModelStatus.LOADING
        self.metrics = ModelPerformanceMetrics(
            total_requests=0,
            successful_requests=0,
            average_inference_time=0.0,
            average_context_length=0.0,
            error_rate=0.0,
            last_request_time=0.0
        )

    @abc.abstractmethod
    def initialize(self) -> bool:
        """Initialize the model. Returns True if successful."""
        pass

    @abc.abstractmethod
    def generate(self, request: GenerationRequest) -> GenerationResponse:
        """Generate text based on the request."""
        pass

    @abc.abstractmethod
    def health_check(self) -> bool:
        """Check if the model is healthy and responsive."""
        pass

    @abc.abstractmethod
    def get_model_info(self) -> Dict[str, Any]:
        """Get detailed model information."""
        pass

    def get_performance_metrics(self) -> ModelPerformanceMetrics:
        """Get current performance metrics."""
        return self.metrics

    def _update_metrics(self, response: GenerationResponse, context_length: int):
        """Update performance metrics after a request."""
        if not self.config.performance_monitoring:
            return

        self.metrics.total_requests += 1
        self.metrics.last_request_time = time.time()

        if response.success:
            self.metrics.successful_requests += 1

            # Update running averages
            n = self.metrics.successful_requests
            self.metrics.average_inference_time = (
                (self.metrics.average_inference_time * (n - 1) + response.inference_time) / n
            )
            self.metrics.average_context_length = (
                (self.metrics.average_context_length * (n - 1) + context_length) / n
            )

        self.metrics.error_rate = (
            (self.metrics.total_requests - self.metrics.successful_requests) /
            self.metrics.total_requests
        )


class BaseModelEngine(abc.ABC):
    """
    Abstract base class for SAM Engine Upgrade framework.

    This class defines the standard interface for all model engines,
    enabling seamless switching between different base models while
    preserving application logic.
    """

    def __init__(self, engine_id: str, model_name: str, model_path: str):
        self.engine_id = engine_id
        self.model_name = model_name
        self.model_path = model_path
        self.status = ModelStatus.LOADING
        self.is_loaded = False

    @abc.abstractmethod
    def load_model(self) -> bool:
        """
        Load the model into memory.

        Returns:
            True if model loaded successfully, False otherwise
        """
        pass

    @abc.abstractmethod
    def generate(self, prompt: str, **kwargs) -> str:
        """
        Generate text using the loaded model.

        Args:
            prompt: Input text prompt
            **kwargs: Additional generation parameters

        Returns:
            Generated text response
        """
        pass

    def generate_with_logits(self, prompt: str, **kwargs) -> Tuple[str, Optional[Any]]:
        """Optional extended generation API that can return both text and logits.

        Default implementation calls :meth:`generate` and returns ``(text, None)``.
        Engines that support logits (e.g., local transformer models) should override
        this method and return a tuple of ``(text, logits_tensor)`` where
        ``logits_tensor`` has shape ``[vocab_size]`` or ``[batch_size, vocab_size]``.
        """
        text = self.generate(prompt, **kwargs)
        return text, None

    @abc.abstractmethod
    def embed(self, text: str) -> List[float]:
        """
        Generate embeddings for the given text.

        Args:
            text: Input text to embed

        Returns:
            List of embedding values
        """
        pass

    @abc.abstractmethod
    def unload_model(self) -> bool:
        """
        Unload the model from memory.

        Returns:
            True if model unloaded successfully, False otherwise
        """
        pass

    def reload_adapter(self, adapter_path: str) -> bool:
        """
        Reload the LoRA adapter for the model.

        Args:
            adapter_path: Path to the new LoRA adapter

        Returns:
            True if reload successful, False otherwise
        """
        logger.warning(f"Engine {self.engine_id} does not support reload_adapter.")
        return False

    def get_engine_info(self) -> Dict[str, Any]:
        """Get engine information."""
        return {
            "engine_id": self.engine_id,
            "model_name": self.model_name,
            "model_path": self.model_path,
            "status": self.status.value,
            "is_loaded": self.is_loaded
        }
    
    def supports_context_length(self, length: int) -> bool:
        """Check if the model supports the given context length."""
        return length <= self.config.max_context_length

class TransformerModelWrapper(ModelInterface):
    """Wrapper for the current Transformer-based model (Ollama)."""
    
    def __init__(self, config: ModelConfig):
        super().__init__(config)
        self.model_type = ModelType.TRANSFORMER
        
    def initialize(self) -> bool:
        """Initialize the Transformer model."""
        try:
            # Check Ollama availability
            response = requests.get(f"{self.config.api_url}/api/tags", timeout=5)
            if response.status_code == 200:
                self.status = ModelStatus.READY
                logger.info(f"✅ Transformer model initialized: {self.config.model_name}")
                return True
            else:
                self.status = ModelStatus.ERROR
                logger.error(f"❌ Ollama not responding: {response.status_code}")
                return False
        except Exception as e:
            self.status = ModelStatus.ERROR
            logger.error(f"❌ Failed to initialize Transformer model: {e}")
            return False
    
    def generate(self, request: GenerationRequest) -> GenerationResponse:
        """Generate text using Ollama API."""
        start_time = time.time()
        # Truncate prompt if it exceeds context limit (roughly 3 chars per token)
        # Leave 4000 tokens for the response
        response_buffer = 4000
        max_prompt_tokens = max(1000, self.config.max_context_length - response_buffer)
        safe_char_limit = int(max_prompt_tokens * 3.5)
        
        if len(request.prompt) > safe_char_limit:
            logger.warning(f"⚠️ Prompt length ({len(request.prompt)}) exceeds safe limit ({safe_char_limit} chars). Truncating.")
            prompt = request.prompt[:safe_char_limit] + "\n[TRUNCATED]"
        else:
            prompt = request.prompt

        context_length = len(prompt.split())
        
        try:
            # Prepare request parameters
            temperature = request.temperature or self.config.temperature
            max_tokens = request.max_tokens or self.config.max_tokens
            # Ensure context window is large enough for code snippets
            num_ctx = self.config.max_context_length
            
            # Model Relay Race: use override model if specified
            active_model = request.model_override or self.config.model_name
            if request.model_override:
                logger.info(f"🔀 [RELAY] Model override active: {active_model} (default: {self.config.model_name})")
            
            # Make API request
            stream_flag = bool(request.stream)
            if request.tools:
                # Use Ollama's chat endpoint for tool-aware generation
                api_endpoint = f"{self.config.api_url}/api/chat"
                payload = {
                    "model": active_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                    "tools": request.tools,
                    "options": {
                        "temperature": temperature,
                        "top_p": request.top_p or 0.9,
                        "num_predict": max_tokens,
                        "num_ctx": num_ctx
                    }
                }
                if request.tool_choice:
                    payload["tool_choice"] = request.tool_choice
            else:
                # Use standard generation endpoint
                api_endpoint = f"{self.config.api_url}/api/generate"
                payload = {
                    "model": active_model,
                    "prompt": prompt,
                    "stream": stream_flag,
                    "options": {
                        "temperature": temperature,
                        "top_p": request.top_p or 0.9,
                        "num_predict": max_tokens,
                        "num_ctx": num_ctx,
                        "logprobs": 1 if request.include_logprobs else 0
                    }
                }
            
            # Model Relay Race: include keep_alive for lifecycle control
            if request.keep_alive is not None:
                payload["keep_alive"] = request.keep_alive
                logger.info(f"🏁 [RELAY] keep_alive={request.keep_alive} for {active_model}")
            
            # Ensure num_ctx is set for tool calls as well
            if request.tools:
                payload["options"]["num_ctx"] = num_ctx

            logger.info(f"📡 Sending request to Ollama: {api_endpoint} (Payload: {len(json.dumps(payload))} chars, Timeout: {request.request_timeout or self.config.timeout_seconds}s)")
            response = requests.post(
                api_endpoint,
                json=payload,
                timeout=request.request_timeout or self.config.timeout_seconds,
                stream=stream_flag,
            )
            
            inference_time = time.time() - start_time
            logger.info(f"💾 Ollama response received: Status {response.status_code} in {inference_time:.2f}s")
            
            if response.status_code == 200:
                if stream_flag and not request.tools:
                    parts: List[str] = []
                    logprobs_data = None
                    for line in response.iter_lines(decode_unicode=True):
                        if not line:
                            continue
                        try:
                            chunk = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if "response" in chunk:
                            parts.append(chunk.get("response", ""))
                        if chunk.get("done") is True:
                            break
                    generated_text = "".join(parts)
                else:
                    result = response.json()
                    if request.tools:
                        # Parse message format from chat endpoint
                        message = result.get('message', {})
                        generated_text = message.get('content', '')
                        # If tool calls were made, they are in message.get('tool_calls')
                        # We should preserve them in the text for TIR to detect if they aren't content
                        tool_calls = message.get('tool_calls', [])
                        if tool_calls and not generated_text:
                            # Convert tool calls to TIR-compatible XML format if content is empty
                            tool_parts = []
                            for tc in tool_calls:
                                func = tc.get('function', {})
                                name = func.get('name', 'unknown_tool')
                                params = json.dumps(func.get('arguments', {}))
                                tool_parts.append(f"<tool_call><tool_name>{name}</tool_name><parameters>{params}</parameters></tool_call>")
                            generated_text = "\n".join(tool_parts)
                    else:
                        generated_text = result.get('response', '')

                    logprobs_data = result.get('logprobs')
                
                # Calculate entropy if logprobs are available
                entropy_score = None
                if logprobs_data:
                    entropy_score = self._calculate_shannon_entropy(logprobs_data)

                gen_response = GenerationResponse(
                    text=generated_text,
                    model_type=self.model_type,
                    inference_time=inference_time,
                    context_length=context_length,
                    success=True,
                    performance_metrics={
                        'api_response_time': inference_time,
                        'context_tokens': context_length
                    },
                    logprobs=logprobs_data,
                    entropy=entropy_score
                )
                
                self._update_metrics(gen_response, context_length)
                return gen_response
            else:
                error_msg = f"API error: {response.status_code} - {response.text}"
                logger.error(f"❌ Ollama API Error: {error_msg}")
                gen_response = GenerationResponse(
                    text="",
                    model_type=self.model_type,
                    inference_time=inference_time,
                    context_length=context_length,
                    success=False,
                    error_message=error_msg
                )
                
                self._update_metrics(gen_response, context_length)
                return gen_response
                
        except Exception as e:
            inference_time = time.time() - start_time
            error_msg = f"Generation failed: {str(e)}"
            
            gen_response = GenerationResponse(
                text="",
                model_type=self.model_type,
                inference_time=inference_time,
                context_length=context_length,
                success=False,
                error_message=error_msg
            )
            
            self._update_metrics(gen_response, context_length)
            return gen_response
    
    def _calculate_shannon_entropy(self, logprobs: List[Any]) -> float:
        """Calculate Shannon Entropy from token log probabilities."""
        import math
        if not logprobs:
            return 0.0
        
        # Ollama logprobs format: list of tokens with their logprobs
        # We calculate H = -sum(p * log(p))
        
        total_entropy = 0.0
        token_count = 0
        
        for entry in logprobs:
            top_choices = entry.get('top_logprobs', [])
            if not top_choices:
                lp = entry.get('logprob', 0.0)
                continue
            
            token_entropy = 0.0
            for choice_lp in top_choices:
                lp = choice_lp.get('logprob', -100.0)
                p = math.exp(lp)
                if p > 1e-6:
                    token_entropy -= p * lp
            
            total_entropy += token_entropy
            token_count += 1
            
        return total_entropy / token_count if token_count > 0 else 0.0

    def health_check(self) -> bool:
        """Check Transformer model health."""
        try:
            response = requests.get(f"{self.config.api_url}/api/tags", timeout=5)
            return response.status_code == 200
        except:
            return False
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get Transformer model information."""
        try:
            response = requests.post(
                f"{self.config.api_url}/api/show",
                json={"name": self.config.model_name},
                timeout=10
            )
            if response.status_code == 200:
                return response.json()
            else:
                return {"error": f"Failed to get model info: {response.status_code}"}
        except Exception as e:
            return {"error": f"Failed to get model info: {str(e)}"}

class HybridModelWrapper(ModelInterface):
    """Wrapper for the new Hybrid Linear Attention model."""
    
    def __init__(self, config: ModelConfig):
        super().__init__(config)
        self.model_type = ModelType.HYBRID_LINEAR
        self.model = None  # Will hold the actual hybrid model
        
    def initialize(self) -> bool:
        """Initialize the Hybrid model."""
        try:
            logger.info("🔄 Initializing SAM Hybrid model framework...")

            # Import hybrid model components
            try:
                # from sam.models.sam_hybrid_model import SAMHybridModel  # SAM-specific, not available in ForgeWorks
                # from sam.models.hybrid_config import HybridModelConfigs  # SAM-specific, not available in ForgeWorks

                # Use debug-sized model for initial startup to prevent OOM on 8GB machines
                # The full 8B model requires ~13GB-26GB RAM, which is allocated instantly.
                logger.info("⚠️ Using sam_debug_hybrid configuration for service stabilization")
                hybrid_config = HybridModelConfigs.sam_debug_hybrid()
                
                # Override context length for debug model compatibility
                hybrid_config.max_context_length = min(self.config.max_context_length, 2048)

                # Initialize the hybrid model (debug scale)
                # This ensures SSRL and TIR integration points are valid without the memory crash
                self.model = SAMHybridModel(hybrid_config)
                logger.info(f"✅ Hybrid model framework ready with {self.model.get_parameter_count():,} parameters")

                # Set model to evaluation mode
                self.model.eval()

                self.status = ModelStatus.READY
                return True

            except ImportError as e:
                logger.warning(f"Hybrid model components not available: {e}")
                logger.info("🔄 Using placeholder implementation for Phase 1 development")

                # Placeholder for development
                self.model = "placeholder_hgrn2_model"
                self.status = ModelStatus.READY
                return True

        except Exception as e:
            self.status = ModelStatus.ERROR
            logger.error(f"❌ Failed to initialize Hybrid model: {e}")
            return False
    
    def generate(self, request: GenerationRequest) -> GenerationResponse:
        """Generate text using Hybrid model."""
        start_time = time.time()
        context_length = len(request.prompt.split())
        
        try:
            # TODO: Implement actual hybrid model generation
            # For now, return a placeholder response
            
            # Simulate processing time based on context length
            # Hybrid models should scale better than transformers
            simulated_time = 0.01 + (context_length * 0.00001)  # Linear scaling
            time.sleep(simulated_time)
            
            generated_text = f"[Hybrid Model Response] Processed {context_length} tokens efficiently."
            inference_time = time.time() - start_time
            
            gen_response = GenerationResponse(
                text=generated_text,
                model_type=self.model_type,
                inference_time=inference_time,
                context_length=context_length,
                success=True,
                performance_metrics={
                    'hybrid_processing_time': inference_time,
                    'context_tokens': context_length,
                    'linear_attention_ratio': 0.75  # 3:1 ratio
                }
            )
            
            self._update_metrics(gen_response, context_length)
            return gen_response
            
        except Exception as e:
            inference_time = time.time() - start_time
            error_msg = f"Hybrid generation failed: {str(e)}"
            
            gen_response = GenerationResponse(
                text="",
                model_type=self.model_type,
                inference_time=inference_time,
                context_length=context_length,
                success=False,
                error_message=error_msg
            )
            
            self._update_metrics(gen_response, context_length)
            return gen_response
    
    def health_check(self) -> bool:
        """Check Hybrid model health."""
        # TODO: Implement actual health check
        return self.status == ModelStatus.READY
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get Hybrid model information."""
        return {
            "model_type": "hybrid_linear_attention",
            "architecture": "HGRN-2",
            "ratio": "3:1 (linear:full)",
            "max_context_length": self.config.max_context_length,
            "status": self.status.value,
            "implementation": "placeholder"  # Will be updated in Phase 1
        }

class ModelManager:
    """Manages multiple model instances with fallback support."""
    
    def __init__(self):
        self.models: Dict[str, ModelInterface] = {}
        self.primary_model: Optional[str] = None
        self.fallback_model: Optional[str] = None
        
    def register_model(self, name: str, model: ModelInterface) -> bool:
        """Register a model instance."""
        if model.initialize():
            self.models[name] = model
            logger.info(f"✅ Model registered: {name}")
            return True
        else:
            logger.error(f"❌ Failed to register model: {name}")
            return False
    
    def set_primary_model(self, name: str):
        """Set the primary model for generation."""
        if name in self.models:
            self.primary_model = name
            logger.info(f"🎯 Primary model set to: {name}")
        else:
            raise ValueError(f"Model {name} not registered")
    
    def set_fallback_model(self, name: str):
        """Set the fallback model."""
        if name in self.models:
            self.fallback_model = name
            logger.info(f"🛡️ Fallback model set to: {name}")
        else:
            raise ValueError(f"Model {name} not registered")
    
    def generate(self, request: GenerationRequest) -> GenerationResponse:
        """Generate text with automatic fallback support."""
        # Try primary model first
        if self.primary_model and self.primary_model in self.models:
            primary = self.models[self.primary_model]
            
            if primary.health_check():
                response = primary.generate(request)
                if response.success:
                    return response
                else:
                    logger.warning(f"Primary model failed: {response.error_message}")
        
        # Fallback to secondary model
        if self.fallback_model and self.fallback_model in self.models:
            fallback = self.models[self.fallback_model]
            
            if fallback.health_check():
                logger.info("🛡️ Using fallback model")
                response = fallback.generate(request)
                return response
        
        # No working models available
        return GenerationResponse(
            text="",
            model_type=ModelType.MOCK,
            inference_time=0.0,
            context_length=0,
            success=False,
            error_message="No working models available"
        )
    
    def get_model_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all registered models."""
        status = {}
        for name, model in self.models.items():
            status[name] = {
                "type": model.model_type.value,
                "status": model.status.value,
                "health": model.health_check(),
                "metrics": model.get_performance_metrics(),
                "config": {
                    "max_context_length": model.config.max_context_length,
                    "timeout_seconds": model.config.timeout_seconds
                }
            }
        return status

# Global model manager instance
_model_manager = None

def get_model_manager() -> ModelManager:
    """Get the global model manager instance."""
    global _model_manager
    if _model_manager is None:
        _model_manager = ModelManager()
    return _model_manager

def initialize_sam_models() -> ModelManager:
    """Initialize SAM's model configuration based on SAM config."""
    # from sam.config import get_sam_config, get_current_model_backend, ModelBackend  # SAM-specific

    manager = get_model_manager()
    sam_config = get_sam_config()
    current_backend = get_current_model_backend()

    # Configure Transformer model
    transformer_config = ModelConfig(
        model_type=ModelType.TRANSFORMER,
        model_name=sam_config.model.transformer_model_name,
        api_url=sam_config.model.transformer_api_url,
        max_context_length=min(sam_config.model.max_context_length, 16000),
        timeout_seconds=sam_config.model.timeout_seconds,
        temperature=sam_config.model.temperature,
        max_tokens=sam_config.model.max_tokens,
        fallback_enabled=True
    )

    # Configure Hybrid model
    hybrid_config = ModelConfig(
        model_type=ModelType.HYBRID_LINEAR,
        model_name=f"sam-hybrid-{sam_config.model.size.value}",
        api_url="http://localhost:11435",  # Different port for hybrid model
        max_context_length=sam_config.model.max_context_length,
        timeout_seconds=sam_config.model.timeout_seconds,
        temperature=sam_config.model.temperature,
        max_tokens=sam_config.model.max_tokens,
        fallback_enabled=True
    )

    # Register models
    transformer_model = TransformerModelWrapper(transformer_config)
    hybrid_model = HybridModelWrapper(hybrid_config)

    manager.register_model("transformer", transformer_model)
    manager.register_model("hybrid", hybrid_model)

    # Set primary model based on configuration
    if current_backend == ModelBackend.HYBRID:
        manager.set_primary_model("hybrid")
        manager.set_fallback_model("transformer")
        logger.info("🔄 SAM configured for hybrid model with transformer fallback")
    else:
        manager.set_primary_model("transformer")
        manager.set_fallback_model("transformer")
        logger.info("🔄 SAM configured for transformer model")

    return manager

# Utility functions for SAM integration
def switch_to_hybrid_model():
    """Switch SAM to use the hybrid model as primary."""
    manager = get_model_manager()
    manager.set_primary_model("hybrid")
    manager.set_fallback_model("transformer")
    logger.info("🔄 Switched to hybrid model with transformer fallback")

def switch_to_transformer_model():
    """Switch SAM to use the transformer model as primary."""
    manager = get_model_manager()
    manager.set_primary_model("transformer")
    logger.info("🔄 Switched to transformer model")

def get_current_model_info() -> Dict[str, Any]:
    """
    Get information about the currently active model.

    This function bridges to ModelManagerIntegration to get the active model
    from the Core Engines Framework (Phases 1-4).

    Returns:
        Dictionary with active model information from ModelManagerIntegration,
        or fallback to old ModelManager if integration not available
    """
    try:
        # Try to get active model from ModelManagerIntegration (Phases 1-4)
        from forgeworks.core_engines.integration.model_manager_integration import ModelManagerIntegration

        integration = ModelManagerIntegration.get_instance()
        active_model_info = integration.get_active_model_info()

        if active_model_info:
            return {
                "primary_model": active_model_info.get("model_id"),
                "display_name": active_model_info.get("display_name"),
                "model_family": active_model_info.get("model_family"),
                "context_length": active_model_info.get("context_length"),
                "quantization": active_model_info.get("quantization"),
                "is_active": active_model_info.get("is_active", True),
                "source": "ModelManagerIntegration"
            }
    except Exception as e:
        logger.debug(f"Could not get model info from ModelManagerIntegration: {e}")

    # Fallback to old ModelManager if integration not available
    manager = get_model_manager()
    status = manager.get_model_status()

    return {
        "primary_model": manager.primary_model,
        "fallback_model": manager.fallback_model,
        "model_status": status,
        "total_models": len(manager.models),
        "source": "ModelManager"
    }


class JambaEngine(BaseModelEngine):
    """
    Concrete implementation of BaseModelEngine for Jamba hybrid models.

    This engine uses Hugging Face transformers to load and run Jamba models,
    which combine Transformer and Mamba (SSM) layers for efficient long-context processing.
    """

    def __init__(self, engine_id: str = "jamba", model_name: str = None, model_path: str = None):
        # Use Jamba default if not specified
        if model_name is None:
            model_name = "ai21labs/Jamba-v0.1"
        if model_path is None:
            model_path = model_name  # For HF models, path is the repo name

        super().__init__(engine_id, model_name, model_path)
        self.model = None
        self.tokenizer = None
        self.device = "auto"

    def load_model(self) -> bool:
        """Load the Jamba model via Hugging Face transformers."""
        try:
            logger.info(f"🔄 Loading Jamba model: {self.model_name}")

            # Import required libraries
            try:
                from transformers import AutoTokenizer, AutoModelForCausalLM
                import torch
            except ImportError as e:
                logger.error(f"❌ Required libraries not installed: {e}")
                logger.error("Install with: pip install transformers torch accelerate")
                return False

            # Load tokenizer
            self.tokenizer = AutoTokenizer.from_pretrained(
                self.model_path,
                trust_remote_code=True
            )

            # Add pad token if not present
            if self.tokenizer.pad_token is None:
                self.tokenizer.pad_token = self.tokenizer.eos_token

            # Load model with appropriate settings for Jamba
            model_kwargs = {
                "torch_dtype": torch.float16 if torch.cuda.is_available() else torch.float32,
                "device_map": self.device,
                "trust_remote_code": True,
                "attn_implementation": "flash_attention_2" if torch.cuda.is_available() else "eager"
            }

            self.model = AutoModelForCausalLM.from_pretrained(
                self.model_path,
                **model_kwargs
            )

            self.status = ModelStatus.READY
            self.is_loaded = True
            logger.info(f"✅ Jamba engine loaded successfully: {self.model_name}")
            return True

        except Exception as e:
            self.status = ModelStatus.ERROR
            logger.error(f"❌ Failed to load Jamba engine: {e}")
            return False

    def generate(self, prompt: str, **kwargs) -> str:
        """Generate text using the loaded Jamba model."""
        if not self.is_loaded or self.model is None:
            raise RuntimeError("Jamba model not loaded. Call load_model() first.")

        try:
            # Import torch lazily to avoid hard dependency at module import time
            import torch

            # Set default generation parameters
            generation_kwargs = {
                "max_new_tokens": kwargs.get("max_tokens", 1000),
                "temperature": kwargs.get("temperature", 0.7),
                "do_sample": kwargs.get("temperature", 0.7) > 0,
                "pad_token_id": self.tokenizer.pad_token_id,
                "eos_token_id": self.tokenizer.eos_token_id,
            }

            # Tokenize input
            inputs = self.tokenizer(prompt, return_tensors="pt", padding=True)
            if torch.cuda.is_available():
                inputs = {k: v.cuda() for k, v in inputs.items()}

            # Generate
            with torch.no_grad():
                outputs = self.model.generate(
                    inputs["input_ids"],
                    attention_mask=inputs["attention_mask"],
                    **generation_kwargs
                )

            # Decode only the new tokens
            input_length = inputs["input_ids"].shape[1]
            generated_tokens = outputs[0][input_length:]
            response = self.tokenizer.decode(generated_tokens, skip_special_tokens=True)

            return response.strip()

        except Exception as e:
            logger.error(f"❌ Jamba generation error: {e}")
            raise

    def generate_with_logits(self, prompt: str, **kwargs) -> Tuple[str, Optional[Any]]:
        """Generate text and return logits for dissonance monitoring.

        This uses Hugging Face generation with ``output_scores=True`` and
        ``return_dict_in_generate=True`` so callers (e.g., TPV/DissonanceMonitor)
        can consume real model logits instead of simulated ones.
        """
        if not self.is_loaded or self.model is None:
            raise RuntimeError("Jamba model not loaded. Call load_model() first.")

        try:
            # Import torch lazily to avoid hard dependency at module import time
            import torch

            # Keep generation very short for telemetry use-cases (typically a single token).
            generation_kwargs = {
                "max_new_tokens": kwargs.get("max_tokens", 1),
                "temperature": kwargs.get("temperature", 0.0),
                "do_sample": kwargs.get("temperature", 0.0) > 0,
                "pad_token_id": self.tokenizer.pad_token_id,
                "eos_token_id": self.tokenizer.eos_token_id,
                "output_scores": True,
                "return_dict_in_generate": True,
            }

            inputs = self.tokenizer(prompt, return_tensors="pt", padding=True)
            if torch.cuda.is_available():
                inputs = {k: v.cuda() for k, v in inputs.items()}

            with torch.no_grad():
                outputs = self.model.generate(
                    inputs["input_ids"],
                    attention_mask=inputs.get("attention_mask"),
                    **generation_kwargs,
                )

            sequences = outputs.sequences
            scores = getattr(outputs, "scores", None)

            input_length = inputs["input_ids"].shape[1]
            generated_tokens = sequences[0][input_length:]
            response = self.tokenizer.decode(generated_tokens, skip_special_tokens=True)

            logits = None
            if scores is not None and len(scores) > 0:
                last_scores = scores[-1]
                try:
                    # scores entries are typically [batch_size, vocab_size]
                    logits = last_scores[0]
                except Exception:
                    logits = None

            return response.strip(), logits

        except Exception as e:
            logger.error(f"❌ Jamba generate_with_logits error: {e}")
            # Fall back to plain generation without logits if anything goes wrong
            text = self.generate(prompt, **kwargs)
            return text, None

    def embed(self, text: str) -> List[float]:
        """Generate embeddings using the current embedding system."""
        try:
            # Use existing SAM embedding infrastructure
            # from sam.embedding.embedding_manager import get_embedding_manager  # SAM-specific

            embedding_manager = get_embedding_manager()
            embeddings = embedding_manager.embed_text(text)

            return embeddings.tolist() if hasattr(embeddings, 'tolist') else embeddings

        except Exception as e:
            logger.error(f"❌ Jamba embedding error: {e}")
            raise

    def unload_model(self) -> bool:
        """Unload the Jamba model from memory."""
        try:
            if self.model is not None:
                del self.model
                self.model = None

            if self.tokenizer is not None:
                del self.tokenizer
                self.tokenizer = None

            # Clear CUDA cache if available
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except ImportError:
                pass

            self.status = ModelStatus.LOADING
            self.is_loaded = False
            logger.info(f"✅ Jamba engine unloaded: {self.model_name}")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to unload Jamba engine: {e}")
            return False

    def reload_adapter(self, adapter_path: str) -> bool:
        """Reload the LoRA adapter for the Jamba model."""
        if not self.is_loaded or self.model is None:
            logger.error("Cannot reload adapter: Jamba model not loaded.")
            return False

        try:
            from peft import PeftModel
            import torch

            logger.info(f"🔄 Reloading LoRA adapter from {adapter_path}...")

            # If it's already a PeftModel, we can use load_adapter or set_adapter
            if isinstance(self.model, PeftModel):
                # Load new adapter
                self.model.load_adapter(adapter_path, adapter_name="micro_dose")
                self.model.set_adapter("micro_dose")
            else:
                # Wrap base model with adapter for the first time
                self.model = PeftModel.from_pretrained(
                    self.model,
                    adapter_path,
                    adapter_name="micro_dose"
                )

            logger.info(f"✅ Successfully reloaded LoRA adapter: {adapter_path}")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to reload Jamba adapter: {e}")
            return False


class DeepSeekEngine(BaseModelEngine):
    """
    Concrete implementation of BaseModelEngine for DeepSeek models.

    This engine encapsulates the current model-loading and inference logic
    for DeepSeek models, providing a standardized interface.
    """

    def __init__(self, engine_id: str = "deepseek", model_name: str = None, model_path: str = None):
        # Use current SAM default if not specified
        if model_name is None:
            try:
                from forgeworks.core_engines.config.model_config_manager import ModelConfigManager

                config = ModelConfigManager().load_config()
                model_name = (
                    config.get("reasoning_model")
                    or config.get("default_model")
                    or "hf.co/unsloth/DeepSeek-R1-Distill-Qwen-32B-GGUF:Q4_K_M"
                )
            except Exception:
                model_name = "hf.co/unsloth/DeepSeek-R1-Distill-Qwen-32B-GGUF:Q4_K_M"
        if model_path is None:
            model_path = "http://localhost:11434"  # Ollama API endpoint

        super().__init__(engine_id, model_name, model_path)
        self.api_url = model_path
        self.model_interface = None

    def load_model(self) -> bool:
        """Load the DeepSeek model via existing ModelInterface."""
        try:
            # Create model config for current DeepSeek setup
            model_config = ModelConfig(
                model_type=ModelType.TRANSFORMER,
                model_name=self.model_name,
                api_url=self.api_url,
                max_context_length=16000,
                timeout_seconds=300,
                temperature=0.7,
                max_tokens=1000,
                fallback_enabled=True
            )

            # Create and initialize the model interface
            self.model_interface = TransformerModelWrapper(model_config)

            if self.model_interface.initialize():
                self.status = ModelStatus.READY
                self.is_loaded = True
                logger.info(f"✅ DeepSeek engine loaded: {self.model_name}")
                return True
            else:
                self.status = ModelStatus.ERROR
                logger.error(f"❌ Failed to load DeepSeek engine: {self.model_name}")
                return False

        except Exception as e:
            self.status = ModelStatus.ERROR
            logger.error(f"❌ Error loading DeepSeek engine: {e}")
            return False

    def generate(self, prompt: str, **kwargs) -> str:
        """Generate text using the DeepSeek model."""
        if not self.is_loaded or self.model_interface is None:
            raise RuntimeError("Model not loaded. Call load_model() first.")

        try:
            request = GenerationRequest(
                prompt=prompt,
                max_tokens=kwargs.get('max_tokens', 1000),
                temperature=kwargs.get('temperature', 0.7),
                system_prompt=kwargs.get('system_prompt', ''),
                context=kwargs.get('context', []),
                tools=kwargs.get('tools'),
                tool_choice=kwargs.get('tool_choice'),
                stream=kwargs.get('stream')
            )

            # Generate response
            response = self.model_interface.generate(request)

            if response.success:
                return response.text
            else:
                raise RuntimeError(f"Generation failed: {response.error}")

        except Exception as e:
            logger.error(f"❌ DeepSeek generation error: {e}")
            raise

    def embed(self, text: str) -> List[float]:
        """Generate embeddings using the current embedding system."""
        try:
            # Use existing SAM embedding infrastructure
            # from sam.embedding.embedding_manager import get_embedding_manager  # SAM-specific

            embedding_manager = get_embedding_manager()
            embeddings = embedding_manager.embed_text(text)

            return embeddings.tolist() if hasattr(embeddings, 'tolist') else embeddings

        except Exception as e:
            logger.error(f"❌ DeepSeek embedding error: {e}")
            raise

    def unload_model(self) -> bool:
        """Unload the DeepSeek model."""
        try:
            if self.model_interface:
                self.model_interface = None

            self.status = ModelStatus.UNAVAILABLE
            self.is_loaded = False
            logger.info(f"✅ DeepSeek engine unloaded: {self.model_name}")
            return True

        except Exception as e:
            logger.error(f"❌ Error unloading DeepSeek engine: {e}")
            return False


class GLMEngine(BaseModelEngine):
    """
    Concrete implementation of BaseModelEngine for GLM-OCR models.
    """

    def __init__(self, engine_id: str = "glm-ocr", model_name: str = None, model_path: str = None):
        if model_name is None:
            model_name = "glm-ocr"
        if model_path is None:
            model_path = "http://localhost:11434"

        super().__init__(engine_id, model_name, model_path)
        self.api_url = model_path
        self.model_interface = None

    def load_model(self) -> bool:
        """Load the GLM model via Ollama."""
        try:
            model_config = ModelConfig(
                model_type=ModelType.TRANSFORMER,
                model_name=self.model_name,
                api_url=self.api_url,
                max_context_length=8000,
                timeout_seconds=300,
                temperature=0.2,
                max_tokens=2048,
                fallback_enabled=False
            )

            self.model_interface = TransformerModelWrapper(model_config)

            if self.model_interface.initialize():
                self.status = ModelStatus.READY
                self.is_loaded = True
                logger.info(f"✅ GLM engine loaded: {self.model_name}")
                return True
            else:
                self.status = ModelStatus.ERROR
                return False
        except Exception as e:
            self.status = ModelStatus.ERROR
            logger.error(f"❌ Error loading GLM engine: {e}")
            return False

    def generate(self, prompt: str, **kwargs) -> str:
        if not self.is_loaded or self.model_interface is None:
            raise RuntimeError("Model not loaded.")
        
        request = GenerationRequest(
            prompt=prompt,
            max_tokens=kwargs.get('max_tokens', 2048),
            temperature=kwargs.get('temperature', 0.2),
            tools=kwargs.get('tools'),
            tool_choice=kwargs.get('tool_choice'),
            stream=kwargs.get('stream')
        )
        response = self.model_interface.generate(request)
        if response.success:
            return response.text
        raise RuntimeError(f"GLM generation failed: {response.error_message}")

    def embed(self, text: str) -> List[float]:
        raise NotImplementedError("GLM engine does not support embedding.")

    def unload_model(self) -> bool:
        """Unload the GLM model."""
        try:
            self.model_interface = None
            self.status = ModelStatus.UNAVAILABLE
            self.is_loaded = False
            logger.info(f"✅ GLM engine unloaded: {self.model_name}")
            return True
        except Exception as e:
            logger.error(f"❌ Error unloading GLM engine: {e}")
            return False


class QwenEngine(BaseModelEngine):
    """
    Concrete implementation of BaseModelEngine for Qwen-Coder models.
    """

    def __init__(self, engine_id: str = "qwen-coder", model_name: str = None, model_path: str = None):
        if model_name is None:
            model_name = "qwen3-coder:30b"
        if model_path is None:
            model_path = "http://localhost:11434"

        super().__init__(engine_id, model_name, model_path)
        self.api_url = model_path
        self.model_interface = None

    def load_model(self) -> bool:
        """Load the Qwen model via Ollama."""
        try:
            model_config = ModelConfig(
                model_type=ModelType.TRANSFORMER,
                model_name=self.model_name,
                api_url=self.api_url,
                max_context_length=32000,
                timeout_seconds=600,
                temperature=0.0,
                max_tokens=4096,
                fallback_enabled=True
            )

            self.model_interface = TransformerModelWrapper(model_config)

            if self.model_interface.initialize():
                self.status = ModelStatus.READY
                self.is_loaded = True
                logger.info(f"✅ Qwen engine loaded: {self.model_name}")
                return True
            else:
                self.status = ModelStatus.ERROR
                return False
        except Exception as e:
            self.status = ModelStatus.ERROR
            logger.error(f"❌ Error loading Qwen engine: {e}")
            return False

    def generate(self, prompt: str, **kwargs) -> str:
        if not self.is_loaded or self.model_interface is None:
            raise RuntimeError("Model not loaded.")
        
        request = GenerationRequest(
            prompt=prompt,
            max_tokens=kwargs.get('max_tokens', 4096),
            temperature=kwargs.get('temperature', 0.0),
            tools=kwargs.get('tools'),
            tool_choice=kwargs.get('tool_choice'),
            stream=kwargs.get('stream')
        )
        response = self.model_interface.generate(request)
        if response.success:
            return response.text
        raise RuntimeError(f"Qwen generation failed: {response.error_message}")

    def embed(self, text: str) -> List[float]:
        # Reuse DeepSeek's embedding infrastructure if needed, or raise
        raise NotImplementedError("Qwen engine does not support embedding.")

    def unload_model(self) -> bool:
        """Unload the Qwen model."""
        try:
            self.model_interface = None
            self.status = ModelStatus.UNAVAILABLE
            self.is_loaded = False
            logger.info(f"✅ Qwen engine unloaded: {self.model_name}")
            return True
        except Exception as e:
            logger.error(f"❌ Error unloading Qwen engine: {e}")
            return False


class LlamaEngine(BaseModelEngine):
    """
    Concrete implementation of BaseModelEngine for Llama-3.x models.
    """

    def __init__(self, engine_id: str = "llama", model_name: str = None, model_path: str = None):
        if model_name is None:
            model_name = "llama-3.1-8b-q4"
        if model_path is None:
            model_path = "http://localhost:11434"

        super().__init__(engine_id, model_name, model_path)
        self.api_url = model_path
        self.model_interface = None

    def load_model(self) -> bool:
        """Load the Llama model via Ollama."""
        try:
            model_config = ModelConfig(
                model_type=ModelType.TRANSFORMER,
                model_name=self.model_name,
                api_url=self.api_url,
                max_context_length=128000,
                timeout_seconds=600,
                temperature=0.7,
                max_tokens=4096,
                fallback_enabled=True
            )

            self.model_interface = TransformerModelWrapper(model_config)

            if self.model_interface.initialize():
                self.status = ModelStatus.READY
                self.is_loaded = True
                logger.info(f"✅ Llama engine loaded: {self.model_name}")
                return True
            else:
                self.status = ModelStatus.ERROR
                return False
        except Exception as e:
            self.status = ModelStatus.ERROR
            logger.error(f"❌ Error loading Llama engine: {e}")
            return False

    def generate(self, prompt: str, **kwargs) -> str:
        if not self.is_loaded or self.model_interface is None:
            raise RuntimeError("Model not loaded.")
        
        request = GenerationRequest(
            prompt=prompt,
            max_tokens=kwargs.get('max_tokens', 4096),
            temperature=kwargs.get('temperature', 0.7),
            tools=kwargs.get('tools'),
            tool_choice=kwargs.get('tool_choice'),
            stream=kwargs.get('stream')
        )
        response = self.model_interface.generate(request)
        if response.success:
            return response.text
        raise RuntimeError(f"Llama generation failed: {response.error_message}")

    def embed(self, text: str) -> List[float]:
        """Generate embeddings using the current embedding system."""
        try:
            # from sam.embedding.embedding_manager import get_embedding_manager  # SAM-specific
            embedding_manager = get_embedding_manager()
            embeddings = embedding_manager.embed_text(text)
            return embeddings.tolist() if hasattr(embeddings, 'tolist') else embeddings
        except Exception as e:
            logger.error(f"❌ Llama embedding error: {e}")
            raise

    def unload_model(self) -> bool:
        """Unload the Llama model."""
        try:
            self.model_interface = None
            self.status = ModelStatus.UNAVAILABLE
            self.is_loaded = False
            logger.info(f"✅ Llama engine unloaded: {self.model_name}")
            return True
        except Exception as e:
            logger.error(f"❌ Error unloading Llama engine: {e}")
            return False
