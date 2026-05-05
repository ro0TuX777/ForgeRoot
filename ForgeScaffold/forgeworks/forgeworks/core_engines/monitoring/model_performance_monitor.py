"""
Model Performance Monitor - Phase 5 Implementation

Tracks performance metrics for different models to enable:
- Model comparison and evaluation
- Performance baselines per model
- A/B testing capabilities
- Performance degradation detection
- Optimization recommendations

Author: SAM Development Team
Date: 2025-11-02
"""

import time
import threading
import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path
from collections import defaultdict
import statistics

logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetric:
    """Single performance metric data point."""
    timestamp: float
    model_id: str
    metric_name: str
    value: float
    context_length: Optional[int] = None
    tokens_generated: Optional[int] = None
    success: bool = True
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelPerformanceStats:
    """Aggregated performance statistics for a model."""
    model_id: str
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    
    # Inference time metrics (ms)
    avg_inference_time_ms: float = 0.0
    min_inference_time_ms: float = float('inf')
    max_inference_time_ms: float = 0.0
    p50_inference_time_ms: float = 0.0
    p95_inference_time_ms: float = 0.0
    p99_inference_time_ms: float = 0.0
    
    # Throughput metrics
    avg_tokens_per_second: float = 0.0
    total_tokens_generated: int = 0
    
    # Quality metrics
    success_rate: float = 0.0
    error_rate: float = 0.0
    
    # Context metrics
    avg_context_length: float = 0.0
    max_context_length: int = 0
    
    # Timestamps
    first_request_time: Optional[float] = None
    last_request_time: Optional[float] = None
    
    # Error tracking
    error_counts: Dict[str, int] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


class ModelPerformanceMonitor:
    """
    Monitors and tracks performance metrics for different models.
    
    Features:
    - Per-model performance tracking
    - Real-time metrics collection
    - Historical data storage
    - Performance comparison
    - Baseline establishment
    - Alert generation for performance degradation
    """
    
    def __init__(self, storage_dir: str = "sam/assets/model_performance"):
        """
        Initialize the performance monitor.
        
        Args:
            storage_dir: Directory to store performance metrics
        """
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        # Metrics storage
        self.metrics: List[PerformanceMetric] = []
        self.stats: Dict[str, ModelPerformanceStats] = {}
        
        # Thread safety
        self._lock = threading.Lock()
        
        # Monitoring state
        self.is_monitoring = False
        self.monitor_thread: Optional[threading.Thread] = None
        
        # Performance baselines per model
        self.baselines: Dict[str, Dict[str, float]] = {}
        
        # Alert thresholds
        self.alert_thresholds = {
            "inference_time_degradation_percent": 20.0,  # 20% slower
            "success_rate_drop_percent": 10.0,  # 10% drop
            "error_rate_increase_percent": 50.0,  # 50% increase
        }
        
        # Alert callbacks
        self.alert_callbacks: List[callable] = []
        
        logger.info("✅ ModelPerformanceMonitor initialized")
    
    def record_metric(self, metric: PerformanceMetric):
        """
        Record a performance metric.
        
        Args:
            metric: PerformanceMetric to record
        """
        with self._lock:
            self.metrics.append(metric)
            self._update_stats(metric)
            
            # Check for alerts
            self._check_alerts(metric)
    
    def record_inference(
        self,
        model_id: str,
        inference_time_ms: float,
        tokens_generated: int,
        context_length: int,
        success: bool = True,
        error_message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Record an inference operation.
        
        Args:
            model_id: ID of the model
            inference_time_ms: Time taken for inference in milliseconds
            tokens_generated: Number of tokens generated
            context_length: Length of input context
            success: Whether inference was successful
            error_message: Error message if failed
            metadata: Additional metadata
        """
        metric = PerformanceMetric(
            timestamp=time.time(),
            model_id=model_id,
            metric_name="inference",
            value=inference_time_ms,
            context_length=context_length,
            tokens_generated=tokens_generated,
            success=success,
            error_message=error_message,
            metadata=metadata or {}
        )
        self.record_metric(metric)
    
    def _update_stats(self, metric: PerformanceMetric):
        """Update aggregated statistics for a model."""
        model_id = metric.model_id
        
        if model_id not in self.stats:
            self.stats[model_id] = ModelPerformanceStats(model_id=model_id)
        
        stats = self.stats[model_id]
        stats.total_requests += 1
        
        if metric.success:
            stats.successful_requests += 1
        else:
            stats.failed_requests += 1
            if metric.error_message:
                stats.error_counts[metric.error_message] = \
                    stats.error_counts.get(metric.error_message, 0) + 1
        
        # Update inference time stats
        if metric.metric_name == "inference":
            inference_times = [
                m.value for m in self.metrics
                if m.model_id == model_id and m.metric_name == "inference"
            ]
            
            if inference_times:
                stats.avg_inference_time_ms = statistics.mean(inference_times)
                stats.min_inference_time_ms = min(inference_times)
                stats.max_inference_time_ms = max(inference_times)
                
                if len(inference_times) >= 2:
                    stats.p50_inference_time_ms = statistics.median(inference_times)
                    stats.p95_inference_time_ms = \
                        statistics.quantiles(inference_times, n=20)[18] if len(inference_times) > 20 else stats.p50_inference_time_ms
                    stats.p99_inference_time_ms = \
                        statistics.quantiles(inference_times, n=100)[98] if len(inference_times) > 100 else stats.p95_inference_time_ms
        
        # Update throughput stats
        if metric.tokens_generated:
            stats.total_tokens_generated += metric.tokens_generated
            inference_time_sec = metric.value / 1000.0
            if inference_time_sec > 0:
                tokens_per_sec = metric.tokens_generated / inference_time_sec
                stats.avg_tokens_per_second = \
                    (stats.avg_tokens_per_second * (stats.total_requests - 1) + tokens_per_sec) / stats.total_requests
        
        # Update context stats
        if metric.context_length:
            context_lengths = [
                m.context_length for m in self.metrics
                if m.model_id == model_id and m.context_length
            ]
            if context_lengths:
                stats.avg_context_length = statistics.mean(context_lengths)
                stats.max_context_length = max(context_lengths)
        
        # Update success/error rates
        stats.success_rate = (stats.successful_requests / stats.total_requests * 100) if stats.total_requests > 0 else 0.0
        stats.error_rate = (stats.failed_requests / stats.total_requests * 100) if stats.total_requests > 0 else 0.0
        
        # Update timestamps
        if stats.first_request_time is None:
            stats.first_request_time = metric.timestamp
        stats.last_request_time = metric.timestamp
    
    def _check_alerts(self, metric: PerformanceMetric):
        """Check if metric triggers any alerts."""
        model_id = metric.model_id
        
        # Check if baseline exists
        if model_id not in self.baselines:
            return
        
        baseline = self.baselines[model_id]
        
        # Check inference time degradation
        if metric.metric_name == "inference" and "avg_inference_time_ms" in baseline:
            baseline_time = baseline["avg_inference_time_ms"]
            degradation_percent = ((metric.value - baseline_time) / baseline_time * 100)
            
            if degradation_percent > self.alert_thresholds["inference_time_degradation_percent"]:
                self._trigger_alert(
                    f"⚠️ Inference time degradation for {model_id}: "
                    f"{degradation_percent:.1f}% slower than baseline"
                )
    
    def _trigger_alert(self, message: str):
        """Trigger an alert."""
        logger.warning(message)
        for callback in self.alert_callbacks:
            try:
                callback(message)
            except Exception as e:
                logger.error(f"Error in alert callback: {e}")
    
    def set_baseline(self, model_id: str):
        """
        Set performance baseline for a model based on current stats.
        
        Args:
            model_id: ID of the model
        """
        if model_id not in self.stats:
            logger.warning(f"No stats available for model {model_id}")
            return
        
        stats = self.stats[model_id]
        self.baselines[model_id] = {
            "avg_inference_time_ms": stats.avg_inference_time_ms,
            "success_rate": stats.success_rate,
            "error_rate": stats.error_rate,
            "avg_tokens_per_second": stats.avg_tokens_per_second,
        }
        
        logger.info(f"✅ Baseline set for model {model_id}")
    
    def get_stats(self, model_id: str) -> Optional[ModelPerformanceStats]:
        """Get performance statistics for a model."""
        with self._lock:
            return self.stats.get(model_id)
    
    def get_all_stats(self) -> Dict[str, ModelPerformanceStats]:
        """Get performance statistics for all models."""
        with self._lock:
            return dict(self.stats)
    
    def compare_models(self, model_ids: List[str]) -> Dict[str, Any]:
        """
        Compare performance of multiple models.
        
        Args:
            model_ids: List of model IDs to compare
            
        Returns:
            Comparison dictionary
        """
        comparison = {
            "timestamp": datetime.now().isoformat(),
            "models": {},
            "winner": None,
            "metrics": {}
        }
        
        with self._lock:
            for model_id in model_ids:
                if model_id in self.stats:
                    stats = self.stats[model_id]
                    comparison["models"][model_id] = stats.to_dict()
            
            # Determine winner (highest success rate, lowest inference time)
            if comparison["models"]:
                best_model = max(
                    comparison["models"].items(),
                    key=lambda x: (x[1]["success_rate"], -x[1]["avg_inference_time_ms"])
                )
                comparison["winner"] = best_model[0]
        
        return comparison
    
    def save_metrics(self, filename: Optional[str] = None) -> str:
        """
        Save metrics to file.
        
        Args:
            filename: Optional filename (default: timestamp-based)
            
        Returns:
            Path to saved file
        """
        if filename is None:
            filename = f"metrics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        filepath = self.storage_dir / filename
        
        with self._lock:
            data = {
                "timestamp": datetime.now().isoformat(),
                "metrics_count": len(self.metrics),
                "models": {
                    model_id: stats.to_dict()
                    for model_id, stats in self.stats.items()
                },
                "baselines": self.baselines
            }
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
        
        logger.info(f"✅ Metrics saved to {filepath}")
        return str(filepath)
    
    def load_metrics(self, filename: str):
        """Load metrics from file."""
        filepath = self.storage_dir / filename
        
        if not filepath.exists():
            logger.warning(f"Metrics file not found: {filepath}")
            return
        
        with open(filepath, 'r') as f:
            data = json.load(f)
        
        with self._lock:
            self.baselines = data.get("baselines", {})
        
        logger.info(f"✅ Metrics loaded from {filepath}")
    
    def add_alert_callback(self, callback: callable):
        """Add a callback for alerts."""
        self.alert_callbacks.append(callback)
    
    def get_performance_report(self) -> Dict[str, Any]:
        """Get comprehensive performance report."""
        with self._lock:
            report = {
                "timestamp": datetime.now().isoformat(),
                "total_metrics_recorded": len(self.metrics),
                "models_tracked": len(self.stats),
                "models": {
                    model_id: stats.to_dict()
                    for model_id, stats in self.stats.items()
                },
                "baselines": self.baselines
            }
        
        return report


# Global instance
_monitor_instance: Optional[ModelPerformanceMonitor] = None
_monitor_lock = threading.Lock()


def get_performance_monitor() -> ModelPerformanceMonitor:
    """Get or create the global performance monitor instance."""
    global _monitor_instance
    
    if _monitor_instance is None:
        with _monitor_lock:
            if _monitor_instance is None:
                _monitor_instance = ModelPerformanceMonitor()
    
    return _monitor_instance

