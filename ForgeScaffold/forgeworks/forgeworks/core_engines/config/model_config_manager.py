"""
Model Configuration Manager for SAM

Provides unified model configuration management across SmartModelSelector,
Core Engines UI, and other SAM components. Synchronizes models.conf with
runtime model selection.

Author: SAM Development Team
Created: 2026-01-20
"""

import logging
import configparser
import requests
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
import threading

logger = logging.getLogger(__name__)

@dataclass
class ModelConfig:
    """Configuration for a specific model role."""
    model_name: str
    role: str  # 'reasoning', 'code', 'general', 'default'
    is_available: bool
    family: Optional[str] = None
    size: Optional[str] = None
    parameter_count: Optional[str] = None

class ModelConfigManager:
    """
    Manages unified model configuration across SAM.
    
    Responsibilities:
    - Load/save models.conf
    - Query Ollama for available models
    - Validate model availability
    - Sync with SmartModelSelector
    - Thread-safe configuration updates
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize the model configuration manager.
        
        Args:
            config_path: Path to models.conf (default: config/models.conf)
        """
        if config_path is None:
            # Default to SAM's config directory
            config_path = Path(__file__).parent.parent / "config" / "models.conf"
        
        self.config_path = config_path
        self.config = configparser.ConfigParser()
        self._ollama_cache = None
        self._cache_timestamp = 0
        self._cache_ttl = 60  # Cache Ollama models for 60 seconds
        
        logger.info(f"📋 ModelConfigManager initialized with config: {self.config_path}")
    
    @classmethod
    def get_instance(cls, config_path: Optional[Path] = None) -> 'ModelConfigManager':
        """Get or create singleton instance (thread-safe)."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(config_path)
        return cls._instance
    
    def load_config(self) -> Dict[str, Any]:
        """
        Load configuration from models.conf.
        
        Returns:
            Dictionary with model configuration
        """
        try:
            if not self.config_path.exists():
                logger.warning(f"⚠️ Config file not found: {self.config_path}")
                return self._get_default_config()
            
            self.config.read(self.config_path)
            
            config_dict = {
                # LLM models
                'default_model': self.config.get('llm_model', 'default_model', fallback='ministral-3:8b').strip('"'),
                'reasoning_model': self.config.get('llm_model', 'reasoning_model', 
                    fallback='hf.co/unsloth/DeepSeek-R1-Distill-Qwen-32B-GGUF:Q4_K_M').strip('"'),
                'code_model': self.config.get('llm_model', 'code_model', fallback='qwen2.5-coder:7b').strip('"'),
                'general_model': self.config.get('llm_model', 'general_model', fallback='ministral-3:8b').strip('"'),
                'vision_model': self.config.get('llm_model', 'vision_model', fallback='glm-ocr').strip('"'),
                'embedding_model': self.config.get('embedding_model', 'name', fallback='nomic-embed-text').strip('"'),
                'embedding_dimension': self.config.getint('embedding_model', 'dimension', fallback=384),
                
                # Ollama settings
                'api_url': self.config.get('llm_model', 'api_url', fallback='http://localhost:11434').strip('"'),
                'smart_selection': self.config.getboolean('llm_model', 'smart_selection', fallback=True),
                
                # Model settings
                'max_context_length': self.config.getint('model_settings', 'max_context_length', fallback=4096),
                'temperature': self.config.getfloat('model_settings', 'temperature', fallback=0.7),
                'max_tokens': self.config.getint('model_settings', 'max_tokens', fallback=1000),
                'timeout_seconds': self.config.getint('model_settings', 'timeout_seconds', fallback=60),
            }
            
            logger.info("✅ Loaded model configuration:")
            logger.info(f"   Reasoning: {config_dict['reasoning_model']}")
            logger.info(f"   Code: {config_dict['code_model']}")
            logger.info(f"   General: {config_dict['general_model']}")
            logger.info(f"   Vision: {config_dict['vision_model']}")
            logger.info(f"   Embedding: {config_dict['embedding_model']}")
            
            return config_dict
            
        except Exception as e:
            logger.error(f"❌ Error loading config: {e}")
            return self._get_default_config()
    
    def save_config(self, config: Dict[str, str]) -> bool:
        """
        Save configuration to models.conf.
        
        Args:
            config: Dictionary with model names for each role
            
        Returns:
            True if saved successfully
        """
        try:
            with self._lock:
                # Read current config
                if self.config_path.exists():
                    self.config.read(self.config_path)
                
                # Ensure sections exist
                if not self.config.has_section('llm_model'):
                    self.config.add_section('llm_model')
                
                # Update model selections
                if 'reasoning_model' in config:
                    self.config.set('llm_model', 'reasoning_model', f'"{config["reasoning_model"]}"')
                if 'code_model' in config:
                    self.config.set('llm_model', 'code_model', f'"{config["code_model"]}"')
                if 'general_model' in config:
                    self.config.set('llm_model', 'general_model', f'"{config["general_model"]}"')
                if 'vision_model' in config:
                    self.config.set('llm_model', 'vision_model', f'"{config["vision_model"]}"')
                if 'embedding_model' in config:
                    if not self.config.has_section('embedding_model'):
                        self.config.add_section('embedding_model')
                    self.config.set('embedding_model', 'name', f'"{config["embedding_model"]}"')
                if 'default_model' in config:
                    self.config.set('llm_model', 'default_model', f'"{config["default_model"]}"')
                
                # Write to file
                with open(self.config_path, 'w') as f:
                    self.config.write(f)
                
                logger.info("✅ Saved model configuration to models.conf")
                return True
                
        except Exception as e:
            logger.error(f"❌ Error saving config: {e}")
            return False
    
    def get_ollama_models(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """
        Get list of available models from Ollama.
        
        Args:
            force_refresh: Force refresh cache
            
        Returns:
            List of model dictionaries with metadata
        """
        import time
        
        # Check cache
        current_time = time.time()
        if not force_refresh and self._ollama_cache and (current_time - self._cache_timestamp) < self._cache_ttl:
            return self._ollama_cache
        
        try:
            config = self.load_config()
            api_url = config.get('api_url', 'http://localhost:11434')
            
            response = requests.get(f"{api_url}/api/tags", timeout=5)
            if response.status_code == 200:
                models_data = response.json()
                models = []
                
                for model in models_data.get('models', []):
                    model_info = {
                        'name': model.get('name'),
                        'size': model.get('size', 0),
                        'modified': model.get('modified_at'),
                        'family': model.get('details', {}).get('family', 'Unknown'),
                        'parameter_size': model.get('details', {}).get('parameter_size', 'N/A'),
                        'quantization': model.get('details', {}).get('quantization_level', 'Unknown')
                    }
                    models.append(model_info)
                
                # Update cache
                self._ollama_cache = models
                self._cache_timestamp = current_time
                
                logger.info(f"✅ Found {len(models)} models in Ollama")
                return models
            else:
                logger.error(f"❌ Ollama API returned status {response.status_code}")
                return []
                
        except Exception as e:
            logger.error(f"❌ Error fetching Ollama models: {e}")
            return []
    
    def validate_model(self, model_name: str) -> bool:
        """
        Check if a model is available in Ollama.
        
        Args:
            model_name: Name of the model to validate
            
        Returns:
            True if model is available
        """
        models = self.get_ollama_models()
        return any(model['name'] == model_name for model in models)
    
    def get_model_details(self, model_name: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed information about a specific model.
        
        Args:
            model_name: Name of the model
            
        Returns:
            Model details dictionary or None if not found
        """
        models = self.get_ollama_models()
        for model in models:
            if model['name'] == model_name:
                return model
        return None
    
    def sync_to_smart_selector(self) -> bool:
        """
        Trigger SmartModelSelector to reload configuration.
        
        Returns:
            True if sync successful
        """
        try:
            from services.smart_model_selector import get_model_selector
            selector = get_model_selector()
            selector.reload_config()
            logger.info("✅ Synced configuration to SmartModelSelector")
            return True
        except Exception as e:
            logger.error(f"❌ Error syncing to SmartModelSelector: {e}")
            return False
    
    def get_current_selection(self) -> Dict[str, ModelConfig]:
        """
        Get current model selection with availability status.
        
        Returns:
            Dictionary mapping role to ModelConfig
        """
        config = self.load_config()
        models = self.get_ollama_models()
        model_map = {m['name']: m for m in models}
        
        result = {}
        for role in ['reasoning', 'code', 'general', 'vision', 'embedding', 'default']:
            if role == 'embedding':
                key = 'embedding_model'
            else:
                key = f"{role}_model"
            
            model_name = config.get(key, '')
            
            if model_name:
                is_available = model_name in model_map
                model_info = model_map.get(model_name, {})
                
                result[role] = ModelConfig(
                    model_name=model_name,
                    role=role,
                    is_available=is_available,
                    family=model_info.get('family'),
                    size=model_info.get('parameter_size'),
                    parameter_count=model_info.get('parameter_size')
                )
        
        return result
    
    def check_model_status(self, model_name: str) -> Dict[str, Any]:
        """
        Check if a model is currently loaded in Ollama memory.
        
        Args:
            model_name: Name of the model to check
            
        Returns:
            Dictionary with status information:
            {
                'loaded': bool,
                'size': str,
                'modified': str
            }
        """
        try:
            config = self.load_config()
            api_url = config.get('api_url', 'http://localhost:11434')
            
            response = requests.get(f"{api_url}/api/ps", timeout=5)
            if response.status_code == 200:
                running_models = response.json().get('models', [])
                for model in running_models:
                    if model.get('name') == model_name:
                        return {
                            'loaded': True,
                            'size': model.get('size', 'Unknown'),
                            'size_vram': model.get('size_vram', 0),
                            'modified': model.get('modified_at', 'Unknown')
                        }
            return {'loaded': False}
        except Exception as e:
            logger.error(f"❌ Error checking model status: {e}")
            return {'loaded': False, 'error': str(e)}
    
    def get_active_models(self) -> List[Dict[str, Any]]:
        """
        Get list of currently loaded models.
        
        Returns:
            List of loaded model dictionaries
        """
        try:
            config = self.load_config()
            api_url = config.get('api_url', 'http://localhost:11434')
            
            response = requests.get(f"{api_url}/api/ps", timeout=5)
            if response.status_code == 200:
                models = response.json().get('models', [])
                logger.info(f"📊 Found {len(models)} active models")
                return models
            return []
        except Exception as e:
            logger.error(f"❌ Error getting active models: {e}")
            return []
    
    def load_model(self, model_name: str, keep_alive: int = -1) -> bool:
        """
        Load a model into Ollama memory.
        
        Args:
            model_name: Name of the model to load
            keep_alive: How long to keep model loaded (-1 = forever, 0 = unload immediately)
            
        Returns:
            True if model loaded successfully
        """
        try:
            config = self.load_config()
            api_url = config.get('api_url', 'http://localhost:11434')
            
            logger.info(f"🔄 Loading model: {model_name}")
            
            # Use generate API with empty prompt to load model
            response = requests.post(
                f"{api_url}/api/generate",
                json={
                    'model': model_name,
                    'prompt': '',
                    'keep_alive': keep_alive,
                    'stream': False
                },
                timeout=120  # Loading can take time
            )
            
            if response.status_code == 200:
                logger.info(f"✅ Model loaded: {model_name}")
                return True
            else:
                logger.error(f"❌ Failed to load model {model_name}: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error loading model {model_name}: {e}")
            return False
    
    def unload_model(self, model_name: str) -> bool:
        """
        Unload a model from Ollama memory.
        
        Args:
            model_name: Name of the model to unload
            
        Returns:
            True if model unloaded successfully
        """
        try:
            config = self.load_config()
            api_url = config.get('api_url', 'http://localhost:11434')
            
            logger.info(f"🔄 Unloading model: {model_name}")
            
            # [FIX] Check if model is actually active before attempting unload to avoid 404s
            status = self.check_model_status(model_name)
            if not status.get('loaded'):
                logger.info(f"ℹ️ Model {model_name} is not currently active. Skipping unload.")
                return True

            # Use generate API with keep_alive=0 to unload
            response = requests.post(
                f"{api_url}/api/generate",
                json={
                    'model': model_name,
                    'prompt': '',
                    'keep_alive': 0,
                    'stream': False
                },
                timeout=30
            )
            
            if response.status_code == 200:
                logger.info(f"✅ Model unloaded: {model_name}")
                return True
            elif response.status_code == 404:
                # [FIX] If Ollama returns 404, the model doesn't exist or isn't loaded - treat as success
                logger.warning(f"⚠️ Model {model_name} not found by Ollama (404). Treating as successfully unloaded.")
                return True
            else:
                logger.error(f"❌ Failed to unload model {model_name}: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error unloading model {model_name}: {e}")
            return False
    
    def switch_model(self, new_model: str, old_model: Optional[str] = None) -> Dict[str, Any]:
        """
        Switch from one model to another with automatic load/unload.
        
        Args:
            new_model: Model to load
            old_model: Model to unload (optional)
            
        Returns:
            Dictionary with switch results:
            {
                'success': bool,
                'new_model_loaded': bool,
                'old_model_unloaded': bool,
                'message': str
            }
        """
        result = {
            'success': False,
            'new_model_loaded': False,
            'old_model_unloaded': False,
            'message': ''
        }
        
        try:
            # Validate new model exists
            if not self.validate_model(new_model):
                result['message'] = f"Model '{new_model}' not found in Ollama"
                return result
            
            # Load new model
            logger.info(f"🔄 Switching to model: {new_model}")
            if self.load_model(new_model):
                result['new_model_loaded'] = True
                
                # Wait a moment for model to fully load
                import time
                time.sleep(2)
                
                # Verify it loaded
                status = self.check_model_status(new_model)
                if not status.get('loaded'):
                    result['message'] = f"Model {new_model} loaded but not showing as active"
                    return result
                
                # Unload old model if specified and differs from new model
                if old_model and old_model != new_model:
                    if self.unload_model(old_model):
                        result['old_model_unloaded'] = True
                    else:
                        result['message'] = f"Loaded {new_model} but failed to unload {old_model}"
                        result['success'] = True  # Partial success
                        return result
                
                result['success'] = True
                result['message'] = f"Successfully switched to {new_model}"
                logger.info(f"✅ Model switch complete: {new_model}")
                return result
            else:
                result['message'] = f"Failed to load {new_model}"
                return result
                
        except Exception as e:
            result['message'] = f"Error during switch: {str(e)}"
            logger.error(f"❌ Model switch failed: {e}")
            return result
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration when models.conf is missing."""
        return {
            'default_model': 'ministral-3:8b',
            'reasoning_model': 'hf.co/unsloth/DeepSeek-R1-Distill-Qwen-32B-GGUF:Q4_K_M',
            'code_model': 'qwen2.5-coder:7b',
            'general_model': 'ministral-3:8b',
            'vision_model': 'glm-ocr',
            'embedding_model': 'nomic-embed-text',
            'embedding_dimension': 384,
            'api_url': 'http://127.0.0.1:11434',
            'smart_selection': True,
            'max_context_length': 4096,
            'temperature': 0.7,
            'max_tokens': 1000,
            'timeout_seconds': 60,
        }


# Global instance accessor
_manager_instance = None

def get_model_config_manager() -> ModelConfigManager:
    """Get or create global ModelConfigManager instance."""
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = ModelConfigManager.get_instance()
    return _manager_instance
