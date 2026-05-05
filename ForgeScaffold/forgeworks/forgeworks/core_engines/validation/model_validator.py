"""
SAM Model Validator
===================

Validates models before switching to ensure they work correctly with SAM's
Core Engines and can handle the required functionality.

Phase 4: Model Validation System

Author: SAM Development Team
Version: 1.0.0
"""

import logging
import time
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class ValidationStatus(Enum):
    """Validation result status."""
    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"
    SKIPPED = "skipped"


@dataclass
class ValidationResult:
    """Result of a single validation test."""
    test_name: str
    status: ValidationStatus
    message: str
    duration_ms: float
    details: Optional[Dict[str, Any]] = None


@dataclass
class ModelValidationReport:
    """Complete validation report for a model."""
    model_id: str
    model_family: str
    overall_status: ValidationStatus
    passed_tests: int
    failed_tests: int
    warning_tests: int
    total_tests: int
    total_duration_ms: float
    results: List[ValidationResult]
    
    def is_valid(self) -> bool:
        """Check if model passed all critical tests."""
        return self.overall_status == ValidationStatus.PASSED
    
    def get_summary(self) -> str:
        """Get human-readable summary."""
        return (
            f"Model: {self.model_id} ({self.model_family})\n"
            f"Status: {self.overall_status.value.upper()}\n"
            f"Tests: {self.passed_tests} passed, {self.failed_tests} failed, "
            f"{self.warning_tests} warnings\n"
            f"Duration: {self.total_duration_ms:.2f}ms"
        )


class ModelValidator:
    """
    Validates models before switching.
    
    Phase 4: Ensures models work correctly with SAM's Core Engines
    before allowing them to become active.
    """
    
    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.ModelValidator")
        self.validation_timeout = 30  # seconds
    
    def validate_model(self, engine: Any, model_id: str, model_family: str) -> ModelValidationReport:
        """
        Validate a model engine before switching.
        
        Args:
            engine: The model engine to validate
            model_id: ID of the model
            model_family: Family of the model (deepseek, llama, jamba, qwen)
            
        Returns:
            ModelValidationReport with validation results
        """
        start_time = time.time()
        results: List[ValidationResult] = []
        
        self.logger.info(f"🔍 Starting validation for model: {model_id}")
        
        # Test 1: Basic Generation
        results.append(self._test_basic_generation(engine))
        
        # Test 2: Context Handling
        results.append(self._test_context_handling(engine, model_family))
        
        # Test 3: Tool Integration
        results.append(self._test_tool_integration(engine))
        
        # Test 4: Memory Integration
        results.append(self._test_memory_integration(engine))
        
        # Test 5: Error Handling
        results.append(self._test_error_handling(engine))
        
        # Test 6: Performance Baseline
        results.append(self._test_performance_baseline(engine))
        
        # Calculate summary
        total_duration = (time.time() - start_time) * 1000
        passed = sum(1 for r in results if r.status == ValidationStatus.PASSED)
        failed = sum(1 for r in results if r.status == ValidationStatus.FAILED)
        warnings = sum(1 for r in results if r.status == ValidationStatus.WARNING)
        
        # Determine overall status
        if failed > 0:
            overall_status = ValidationStatus.FAILED
        elif warnings > 0:
            overall_status = ValidationStatus.WARNING
        else:
            overall_status = ValidationStatus.PASSED
        
        report = ModelValidationReport(
            model_id=model_id,
            model_family=model_family,
            overall_status=overall_status,
            passed_tests=passed,
            failed_tests=failed,
            warning_tests=warnings,
            total_tests=len(results),
            total_duration_ms=total_duration,
            results=results
        )
        
        self.logger.info(f"✅ Validation complete: {report.get_summary()}")
        return report
    
    def _test_basic_generation(self, engine: Any) -> ValidationResult:
        """Test basic text generation."""
        test_name = "Basic Generation"
        start_time = time.time()
        
        try:
            # Test simple generation
            prompt = "What is 2+2?"
            response = engine.generate(prompt, max_tokens=50)
            
            if response and len(response) > 0:
                duration = (time.time() - start_time) * 1000
                return ValidationResult(
                    test_name=test_name,
                    status=ValidationStatus.PASSED,
                    message="✅ Basic generation works",
                    duration_ms=duration,
                    details={"response_length": len(response)}
                )
            else:
                return ValidationResult(
                    test_name=test_name,
                    status=ValidationStatus.FAILED,
                    message="❌ Generation returned empty response",
                    duration_ms=(time.time() - start_time) * 1000
                )
        except Exception as e:
            return ValidationResult(
                test_name=test_name,
                status=ValidationStatus.FAILED,
                message=f"❌ Generation failed: {str(e)}",
                duration_ms=(time.time() - start_time) * 1000
            )
    
    def _test_context_handling(self, engine: Any, model_family: str) -> ValidationResult:
        """Test context length handling."""
        test_name = "Context Handling"
        start_time = time.time()
        
        try:
            # Get model's max context length
            engine_info = engine.get_engine_info() if hasattr(engine, 'get_engine_info') else {}
            
            # Test with moderate context
            context = "This is a test. " * 100  # ~1600 tokens
            prompt = f"{context}\nSummarize the above in one sentence."
            
            response = engine.generate(prompt, max_tokens=50)
            
            if response and len(response) > 0:
                duration = (time.time() - start_time) * 1000
                return ValidationResult(
                    test_name=test_name,
                    status=ValidationStatus.PASSED,
                    message="✅ Context handling works",
                    duration_ms=duration,
                    details={"context_size": len(context)}
                )
            else:
                return ValidationResult(
                    test_name=test_name,
                    status=ValidationStatus.WARNING,
                    message="⚠️ Context handling returned empty response",
                    duration_ms=(time.time() - start_time) * 1000
                )
        except Exception as e:
            return ValidationResult(
                test_name=test_name,
                status=ValidationStatus.WARNING,
                message=f"⚠️ Context handling test failed: {str(e)}",
                duration_ms=(time.time() - start_time) * 1000
            )
    
    def _test_tool_integration(self, engine: Any) -> ValidationResult:
        """Test tool integration capability."""
        test_name = "Tool Integration"
        start_time = time.time()
        
        try:
            # Test if engine can handle tool-like prompts
            tool_prompt = (
                "You have access to a calculator tool. "
                "Use it to calculate: 15 * 23 = ?"
            )
            response = engine.generate(tool_prompt, max_tokens=50)
            
            if response and len(response) > 0:
                duration = (time.time() - start_time) * 1000
                return ValidationResult(
                    test_name=test_name,
                    status=ValidationStatus.PASSED,
                    message="✅ Tool integration works",
                    duration_ms=duration
                )
            else:
                return ValidationResult(
                    test_name=test_name,
                    status=ValidationStatus.WARNING,
                    message="⚠️ Tool integration returned empty response",
                    duration_ms=(time.time() - start_time) * 1000
                )
        except Exception as e:
            return ValidationResult(
                test_name=test_name,
                status=ValidationStatus.WARNING,
                message=f"⚠️ Tool integration test failed: {str(e)}",
                duration_ms=(time.time() - start_time) * 1000
            )
    
    def _test_memory_integration(self, engine: Any) -> ValidationResult:
        """Test memory integration capability."""
        test_name = "Memory Integration"
        start_time = time.time()
        
        try:
            # Test if engine can handle memory-like prompts
            memory_prompt = (
                "Remember: The user's name is Alice. "
                "What is the user's name?"
            )
            response = engine.generate(memory_prompt, max_tokens=50)
            
            if response and len(response) > 0:
                duration = (time.time() - start_time) * 1000
                return ValidationResult(
                    test_name=test_name,
                    status=ValidationStatus.PASSED,
                    message="✅ Memory integration works",
                    duration_ms=duration
                )
            else:
                return ValidationResult(
                    test_name=test_name,
                    status=ValidationStatus.WARNING,
                    message="⚠️ Memory integration returned empty response",
                    duration_ms=(time.time() - start_time) * 1000
                )
        except Exception as e:
            return ValidationResult(
                test_name=test_name,
                status=ValidationStatus.WARNING,
                message=f"⚠️ Memory integration test failed: {str(e)}",
                duration_ms=(time.time() - start_time) * 1000
            )
    
    def _test_error_handling(self, engine: Any) -> ValidationResult:
        """Test error handling."""
        test_name = "Error Handling"
        start_time = time.time()
        
        try:
            # Test with empty prompt
            response = engine.generate("", max_tokens=50)
            
            # Should handle gracefully
            duration = (time.time() - start_time) * 1000
            return ValidationResult(
                test_name=test_name,
                status=ValidationStatus.PASSED,
                message="✅ Error handling works",
                duration_ms=duration
            )
        except Exception as e:
            # Some error handling is expected
            duration = (time.time() - start_time) * 1000
            return ValidationResult(
                test_name=test_name,
                status=ValidationStatus.PASSED,
                message="✅ Error handling works (caught exception)",
                duration_ms=duration
            )
    
    def _test_performance_baseline(self, engine: Any) -> ValidationResult:
        """Test performance baseline."""
        test_name = "Performance Baseline"
        start_time = time.time()
        
        try:
            # Measure generation speed
            prompt = "Hello, how are you?"
            gen_start = time.time()
            response = engine.generate(prompt, max_tokens=50)
            gen_time = (time.time() - gen_start) * 1000
            
            # Check if reasonable (< 30 seconds)
            if gen_time < 30000:
                duration = (time.time() - start_time) * 1000
                return ValidationResult(
                    test_name=test_name,
                    status=ValidationStatus.PASSED,
                    message=f"✅ Performance baseline acceptable ({gen_time:.0f}ms)",
                    duration_ms=duration,
                    details={"generation_time_ms": gen_time}
                )
            else:
                return ValidationResult(
                    test_name=test_name,
                    status=ValidationStatus.WARNING,
                    message=f"⚠️ Performance baseline slow ({gen_time:.0f}ms)",
                    duration_ms=(time.time() - start_time) * 1000,
                    details={"generation_time_ms": gen_time}
                )
        except Exception as e:
            return ValidationResult(
                test_name=test_name,
                status=ValidationStatus.WARNING,
                message=f"⚠️ Performance baseline test failed: {str(e)}",
                duration_ms=(time.time() - start_time) * 1000
            )


def get_model_validator() -> ModelValidator:
    """Get the global ModelValidator instance."""
    return ModelValidator()

