"""
SAM Model Library Manager
========================

Manages the library of downloaded core models for the Engine Upgrade framework.
Handles model downloading, storage, validation, and metadata management.

Author: SAM Development Team
Version: 1.0.0
"""

import os
import json
import logging
import hashlib
import requests
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, asdict
from huggingface_hub import hf_hub_download, HfApi
import threading

logger = logging.getLogger(__name__)


@dataclass
class ModelInfo:
    """Information about a downloadable model."""
    model_id: str
    display_name: str
    description: str
    model_family: str  # e.g., "deepseek", "llama", "qwen"
    huggingface_repo: str
    filename: str
    file_size: int  # in bytes
    quantization: str  # e.g., "Q4_K_M", "Q8_0"
    context_length: int
    recommended: bool = False
    tags: List[str] = None
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = []


@dataclass
class DownloadedModel:
    """Information about a downloaded model."""
    model_id: str
    local_path: str
    downloaded_at: datetime
    file_size: int
    checksum: str
    model_info: ModelInfo
    status: str = "downloaded"  # "downloaded", "corrupted", "missing"
    is_active: bool = False  # Whether this model is currently active


class ModelLibraryManager:
    """
    Manages the library of core models for SAM Engine Upgrade.
    
    Handles downloading, storage, validation, and metadata for core models.
    """
    
    def __init__(self, models_dir: str = "./sam/assets/core_models"):
        """
        Initialize the model library manager.
        
        Args:
            models_dir: Directory to store downloaded models
        """
        self.logger = logging.getLogger(f"{__name__}.ModelLibraryManager")
        self.models_dir = Path(models_dir)
        self.models_dir.mkdir(parents=True, exist_ok=True)
        
        # Metadata files
        self.catalog_file = self.models_dir / "model_catalog.json"
        self.downloads_file = self.models_dir / "downloaded_models.json"
        
        # Model catalog and downloads
        self.available_models: Dict[str, ModelInfo] = {}
        self.downloaded_models: Dict[str, DownloadedModel] = {}
        
        # Download tracking
        self.active_downloads: Dict[str, threading.Thread] = {}
        self.download_progress: Dict[str, Dict[str, Any]] = {}

        # Phase 3: Model switching listeners
        self.model_switch_listeners: List[Callable[[str, Any], None]] = []
        self.active_model_id: Optional[str] = None

        # Phase 4: Model validator
        from forgeworks.core_engines.validation.model_validator import ModelValidator
        self.validator = ModelValidator()
        self.validation_reports: Dict[str, Any] = {}

        # Load existing data
        self.load_model_catalog()
        self.load_downloaded_models()

        self.logger.info("Model Library Manager initialized")
    
    def load_model_catalog(self):
        """Load the catalog of available models."""
        try:
            if self.catalog_file.exists():
                with open(self.catalog_file, 'r') as f:
                    catalog_data = json.load(f)
                
                for model_id, model_data in catalog_data.get('models', {}).items():
                    model_info = ModelInfo(**model_data)
                    self.available_models[model_id] = model_info
                    
                self.logger.info(f"Loaded {len(self.available_models)} models from catalog")
            else:
                # Create default catalog with SAM-compatible models
                self._create_default_catalog()
                
        except Exception as e:
            self.logger.error(f"Failed to load model catalog: {e}")
            self._create_default_catalog()
    
    def _create_default_catalog(self):
        """Create a default catalog with SAM-compatible models."""
        default_models = [
            ModelInfo(
                model_id="deepseek-r1-8b-q4",
                display_name="DeepSeek R1 8B (Q4_K_M)",
                description="Current SAM default model - DeepSeek R1 with Q4_K_M quantization",
                model_family="deepseek",
                huggingface_repo="unsloth/DeepSeek-R1-0528-Qwen3-8B-GGUF",
                filename="DeepSeek-R1-0528-Qwen3-8B-Q4_K_M.gguf",
                file_size=4800000000,  # ~4.8GB
                quantization="Q4_K_M",
                context_length=16000,
                recommended=True,
                tags=["current", "default", "reasoning"]
            ),
            ModelInfo(
                model_id="deepseek-r1-8b-q8",
                display_name="DeepSeek R1 8B (Q8_0)",
                description="Higher quality DeepSeek R1 with Q8_0 quantization",
                model_family="deepseek",
                huggingface_repo="unsloth/DeepSeek-R1-0528-Qwen3-8B-GGUF",
                filename="DeepSeek-R1-0528-Qwen3-8B-Q8_0.gguf",
                file_size=8500000000,  # ~8.5GB
                quantization="Q8_0",
                context_length=16000,
                recommended=False,
                tags=["high-quality", "reasoning"]
            ),
            ModelInfo(
                model_id="llama-3.1-8b-q4",
                display_name="Llama 3.1 8B Instruct (Q4_K_M)",
                description="Meta's Llama 3.1 8B Instruct model with Q4_K_M quantization",
                model_family="llama",
                huggingface_repo="bartowski/Meta-Llama-3.1-8B-Instruct-GGUF",
                filename="Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf",
                file_size=4700000000,  # ~4.7GB
                quantization="Q4_K_M",
                context_length=128000,
                recommended=True,
                tags=["long-context", "instruct"]
            )
        ]
        
        # Convert to dict and save
        catalog_data = {
            "version": "1.0.0",
            "updated_at": datetime.now().isoformat(),
            "models": {model.model_id: asdict(model) for model in default_models}
        }
        
        for model in default_models:
            self.available_models[model.model_id] = model
        
        self.save_model_catalog(catalog_data)
        self.logger.info("Created default model catalog")
    
    def save_model_catalog(self, catalog_data: Dict[str, Any]):
        """Save the model catalog to disk."""
        try:
            with open(self.catalog_file, 'w') as f:
                json.dump(catalog_data, f, indent=2)
        except Exception as e:
            self.logger.error(f"Failed to save model catalog: {e}")
    
    def load_downloaded_models(self):
        """Load information about downloaded models."""
        try:
            if self.downloads_file.exists():
                with open(self.downloads_file, 'r') as f:
                    downloads_data = json.load(f)
                
                for model_id, model_data in downloads_data.get('models', {}).items():
                    # Convert datetime strings back to datetime objects
                    model_data['downloaded_at'] = datetime.fromisoformat(model_data['downloaded_at'])
                    model_data['model_info'] = ModelInfo(**model_data['model_info'])
                    
                    downloaded_model = DownloadedModel(**model_data)
                    self.downloaded_models[model_id] = downloaded_model
                    
                self.logger.info(f"Loaded {len(self.downloaded_models)} downloaded models")
                
        except Exception as e:
            self.logger.error(f"Failed to load downloaded models: {e}")
    
    def save_downloaded_models(self):
        """Save downloaded models information to disk."""
        try:
            downloads_data = {
                "version": "1.0.0",
                "updated_at": datetime.now().isoformat(),
                "models": {}
            }
            
            for model_id, downloaded_model in self.downloaded_models.items():
                model_data = asdict(downloaded_model)
                model_data['downloaded_at'] = downloaded_model.downloaded_at.isoformat()
                model_data['model_info'] = asdict(downloaded_model.model_info)
                downloads_data['models'][model_id] = model_data
            
            with open(self.downloads_file, 'w') as f:
                json.dump(downloads_data, f, indent=2)
                
        except Exception as e:
            self.logger.error(f"Failed to save downloaded models: {e}")
    
    def get_available_models(self) -> List[ModelInfo]:
        """Get list of available models for download."""
        return list(self.available_models.values())
    
    def get_downloaded_models(self) -> List[DownloadedModel]:
        """Get list of downloaded models."""
        return list(self.downloaded_models.values())
    
    def get_model_status(self, model_id: str) -> str:
        """
        Get the status of a model.

        Returns:
            "not_downloaded", "downloading", "downloaded", "corrupted", "missing"
        """
        if model_id in self.active_downloads:
            return "downloading"
        elif model_id in self.downloaded_models:
            downloaded_model = self.downloaded_models[model_id]
            if Path(downloaded_model.local_path).exists():
                return downloaded_model.status
            else:
                return "missing"
        else:
            return "not_downloaded"

    def download_model(self, model_id: str) -> bool:
        """
        Download a model from the catalog.

        Args:
            model_id: ID of the model to download

        Returns:
            True if download started successfully, False otherwise
        """
        if model_id not in self.available_models:
            self.logger.error(f"Model not found in catalog: {model_id}")
            return False

        if model_id in self.active_downloads:
            self.logger.warning(f"Model already downloading: {model_id}")
            return False

        model_info = self.available_models[model_id]

        # Create download directory
        model_dir = self.models_dir / model_id
        model_dir.mkdir(parents=True, exist_ok=True)

        local_path = model_dir / model_info.filename

        # Initialize progress tracking
        self.download_progress[model_id] = {
            "status": "starting",
            "progress": 0.0,
            "downloaded_bytes": 0,
            "total_bytes": model_info.file_size,
            "speed": 0.0,
            "eta": None,
            "error": None
        }

        # Start download in background thread
        download_thread = threading.Thread(
            target=self._download_model_worker,
            args=(model_id, model_info, local_path),
            daemon=True
        )

        self.active_downloads[model_id] = download_thread
        download_thread.start()

        self.logger.info(f"Started downloading model: {model_id}")
        return True

    def _download_model_worker(self, model_id: str, model_info: ModelInfo, local_path: Path):
        """Worker function for downloading a model."""
        try:
            self.download_progress[model_id]["status"] = "downloading"

            # Download from Hugging Face Hub
            downloaded_path = hf_hub_download(
                repo_id=model_info.huggingface_repo,
                filename=model_info.filename,
                local_dir=local_path.parent,
                local_dir_use_symlinks=False,
                resume_download=True
            )

            # Verify download
            if Path(downloaded_path).exists():
                file_size = Path(downloaded_path).stat().st_size
                checksum = self._calculate_checksum(downloaded_path)

                # Create downloaded model record
                downloaded_model = DownloadedModel(
                    model_id=model_id,
                    local_path=str(downloaded_path),
                    downloaded_at=datetime.now(),
                    file_size=file_size,
                    checksum=checksum,
                    model_info=model_info,
                    status="downloaded"
                )

                self.downloaded_models[model_id] = downloaded_model
                self.save_downloaded_models()

                self.download_progress[model_id]["status"] = "completed"
                self.download_progress[model_id]["progress"] = 100.0

                self.logger.info(f"✅ Model downloaded successfully: {model_id}")
            else:
                raise Exception("Downloaded file not found")

        except Exception as e:
            self.download_progress[model_id]["status"] = "failed"
            self.download_progress[model_id]["error"] = str(e)
            self.logger.error(f"❌ Failed to download model {model_id}: {e}")

        finally:
            # Clean up active download tracking
            if model_id in self.active_downloads:
                del self.active_downloads[model_id]

    def _calculate_checksum(self, file_path: str) -> str:
        """Calculate SHA256 checksum of a file."""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()

    def get_download_progress(self, model_id: str) -> Optional[Dict[str, Any]]:
        """Get download progress for a model."""
        return self.download_progress.get(model_id)

    def cancel_download(self, model_id: str) -> bool:
        """Cancel an active download."""
        if model_id not in self.active_downloads:
            return False

        try:
            # Note: This is a simple cancellation - in a production system
            # you'd want more sophisticated cancellation handling
            self.download_progress[model_id]["status"] = "cancelled"

            if model_id in self.active_downloads:
                del self.active_downloads[model_id]

            self.logger.info(f"Cancelled download: {model_id}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to cancel download {model_id}: {e}")
            return False

    def register_model_switch_listener(self, callback: Callable[[str, Any], None]) -> None:
        """
        Register a listener for model switch events.

        Phase 3: Enables Core Engines to be notified when models switch.

        Args:
            callback: Function to call when model switches (model_id, model_info)
        """
        if callback not in self.model_switch_listeners:
            self.model_switch_listeners.append(callback)
            self.logger.debug(f"Registered model switch listener: {callback.__name__}")

    def _notify_model_switched(self, model_id: str, model_info: ModelInfo) -> None:
        """
        Notify all listeners that a model has switched.

        Args:
            model_id: ID of the new active model
            model_info: ModelInfo of the new active model
        """
        for listener in self.model_switch_listeners:
            try:
                listener(model_id, model_info)
            except Exception as e:
                self.logger.error(f"Error calling model switch listener: {e}")

    def activate_model(self, model_id: str, skip_validation: bool = False) -> bool:
        """
        Activate a downloaded model as the primary SAM model.

        Phase 3: Implements actual model switching with listener notifications.
        Phase 4: Includes model validation before switching.

        Args:
            model_id: Model identifier to activate
            skip_validation: Skip validation tests (for testing/emergency)

        Returns:
            True if activated successfully
        """
        try:
            # Validate model exists
            if model_id not in self.available_models:
                self.logger.error(f"❌ Model not found in catalog: {model_id}")
                return False

            # Validate model is downloaded
            if model_id not in self.downloaded_models:
                self.logger.error(f"❌ Model not downloaded: {model_id}")
                return False

            model_info = self.available_models[model_id]
            downloaded_model = self.downloaded_models[model_id]

            # Validate model status
            if downloaded_model.status != "downloaded":
                self.logger.error(f"❌ Model status is {downloaded_model.status}, not downloaded: {model_id}")
                return False

            # Phase 4: Validate model before switching
            if not skip_validation:
                self.logger.info(f"🔍 Running validation tests for {model_id}...")
                if not self._validate_model_before_switch(model_id, model_info):
                    self.logger.error(f"❌ Model validation failed: {model_id}")
                    return False

            # Deactivate current active model
            if self.active_model_id and self.active_model_id in self.downloaded_models:
                old_model = self.downloaded_models[self.active_model_id]
                old_model.is_active = False
                self.logger.info(f"   Deactivated previous model: {self.active_model_id}")

            # Activate the new model
            downloaded_model.is_active = True
            self.active_model_id = model_id

            # Save the updated state
            self.save_downloaded_models()

            self.logger.info(f"✅ Activated model: {model_id}")
            self.logger.info(f"   Model family: {model_info.model_family}")
            self.logger.info(f"   Context length: {model_info.context_length}")
            self.logger.info(f"   Quantization: {model_info.quantization}")

            # Phase 3: Notify all listeners (Core Engines) of model switch
            self.logger.info(f"   Notifying {len(self.model_switch_listeners)} listeners of model switch...")
            self._notify_model_switched(model_id, model_info)

            self.logger.info(f"✅ Model switch complete: {model_id}")
            return True

        except Exception as e:
            self.logger.error(f"❌ Error activating model {model_id}: {e}")
            return False

    def _validate_model_before_switch(self, model_id: str, model_info: ModelInfo) -> bool:
        """
        Validate a model before switching to it.

        Phase 4: Runs validation tests to ensure model works with SAM.

        Args:
            model_id: ID of the model to validate
            model_info: ModelInfo of the model

        Returns:
            True if validation passed, False otherwise
        """
        try:
            # Get the model engine from ModelManagerIntegration
            from forgeworks.core_engines.integration.model_manager_integration import ModelManagerIntegration
            integration = ModelManagerIntegration.get_instance()

            # Create engine for validation
            engine = integration._create_engine_for_model(model_id)

            if engine is None:
                self.logger.error(f"❌ Failed to create engine for validation: {model_id}")
                return False

            # Load the model
            if not engine.load_model():
                self.logger.error(f"❌ Failed to load model for validation: {model_id}")
                return False

            # Run validation tests
            report = self.validator.validate_model(engine, model_id, model_info.model_family)

            # Store validation report
            self.validation_reports[model_id] = report

            # Log validation results
            self.logger.info(f"📊 Validation Report for {model_id}:")
            for result in report.results:
                status_icon = "✅" if result.status.value == "passed" else "⚠️" if result.status.value == "warning" else "❌"
                self.logger.info(f"   {status_icon} {result.test_name}: {result.message} ({result.duration_ms:.0f}ms)")

            # Check if validation passed
            if report.is_valid():
                self.logger.info(f"✅ Model validation PASSED: {model_id}")
                return True
            else:
                self.logger.error(f"❌ Model validation FAILED: {model_id}")
                self.logger.error(f"   Failed tests: {report.failed_tests}")
                return False

        except Exception as e:
            self.logger.error(f"❌ Error during model validation: {e}")
            return False

    def get_validation_report(self, model_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the validation report for a model.

        Args:
            model_id: ID of the model

        Returns:
            Validation report or None if not available
        """
        if model_id not in self.validation_reports:
            return None

        report = self.validation_reports[model_id]
        return {
            "model_id": report.model_id,
            "model_family": report.model_family,
            "overall_status": report.overall_status.value,
            "passed_tests": report.passed_tests,
            "failed_tests": report.failed_tests,
            "warning_tests": report.warning_tests,
            "total_tests": report.total_tests,
            "total_duration_ms": report.total_duration_ms,
            "summary": report.get_summary()
        }

    def get_active_model(self) -> Optional[Dict[str, Any]]:
        """
        Get information about the currently active model.

        Returns:
            Dictionary with model info or None if no model is active
        """
        if not self.active_model_id or self.active_model_id not in self.downloaded_models:
            return None

        downloaded_model = self.downloaded_models[self.active_model_id]
        model_info = downloaded_model.model_info

        return {
            "model_id": self.active_model_id,
            "display_name": model_info.display_name,
            "model_family": model_info.model_family,
            "local_path": downloaded_model.local_path,
            "context_length": model_info.context_length,
            "quantization": model_info.quantization,
            "is_active": downloaded_model.is_active
        }

    def delete_model(self, model_id: str) -> bool:
        """Delete a downloaded model."""
        if model_id not in self.downloaded_models:
            return False

        try:
            downloaded_model = self.downloaded_models[model_id]
            model_path = Path(downloaded_model.local_path)

            # Delete the model file
            if model_path.exists():
                model_path.unlink()

            # Delete the model directory if empty
            model_dir = model_path.parent
            if model_dir.exists() and not any(model_dir.iterdir()):
                model_dir.rmdir()

            # Remove from downloaded models
            del self.downloaded_models[model_id]
            self.save_downloaded_models()

            self.logger.info(f"✅ Deleted model: {model_id}")
            return True

        except Exception as e:
            self.logger.error(f"❌ Failed to delete model {model_id}: {e}")
            return False


# Global instance
_model_library_manager = None

def get_model_library_manager() -> ModelLibraryManager:
    """Get the global model library manager instance."""
    global _model_library_manager
    if _model_library_manager is None:
        _model_library_manager = ModelLibraryManager()
    return _model_library_manager
