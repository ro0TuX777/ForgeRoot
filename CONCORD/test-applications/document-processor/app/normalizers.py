from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.models import NormalizationResult
from app.registry import register_normalizer


def normalize_scan_pdf(raw_output: Any, action_contract: Any) -> NormalizationResult:
    result = NormalizationResult(normalized=None, success=True, warnings=[])
    try:
        if not isinstance(raw_output, dict):
            return NormalizationResult(success=False, warnings=[], error_detail="Expected dict raw_output")

        normalized = {
            "pages_analyzed": int(raw_output.get("num_pages", 0)),
            "text_content": str(raw_output.get("extracted_text", "")),
            "confidence_score": float(raw_output.get("extraction_confidence", 0.0)),
            "warnings": list(raw_output.get("processing_warnings", []))
        }
        result.normalized = normalized
        return result
    except Exception as e:
        return NormalizationResult(success=False, warnings=[], error_detail=str(e))


def normalize_extract_text(raw_output: Any, action_contract: Any) -> NormalizationResult:
    result = NormalizationResult(normalized=None, success=True, warnings=[])
    try:
        if not isinstance(raw_output, dict):
            return NormalizationResult(success=False, warnings=[], error_detail="Expected dict raw_output")

        normalized = {
            "text": str(raw_output.get("text", "")),
            "word_count": int(raw_output.get("word_count", 0))
        }
        result.normalized = normalized
        return result
    except Exception as e:
        return NormalizationResult(success=False, warnings=[], error_detail=str(e))


def normalize_convert_format(raw_output: Any, action_contract: Any) -> NormalizationResult:
    result = NormalizationResult(normalized=None, success=True, warnings=[])
    try:
        if not isinstance(raw_output, dict):
            return NormalizationResult(success=False, warnings=[], error_detail="Expected dict raw_output")

        normalized = {
            "conversion_success": bool(raw_output.get("conversion_success", False)),
            "output_path": str(raw_output.get("output_path", "")),
            "bytes_written": int(raw_output.get("bytes_written", 0)),
            "warnings": list(raw_output.get("warnings", []))
        }
        result.normalized = normalized
        return result
    except Exception as e:
        return NormalizationResult(success=False, warnings=[], error_detail=str(e))


def normalize_validate_schema(raw_output: Any, action_contract: Any) -> NormalizationResult:
    result = NormalizationResult(normalized=None, success=True, warnings=[])
    try:
        if not isinstance(raw_output, dict):
            return NormalizationResult(success=False, warnings=[], error_detail="Expected dict raw_output")

        normalized = {
            "valid": bool(raw_output.get("valid", False)),
            "errors": list(raw_output.get("errors", [])),
            "schema_name": str(raw_output.get("schema_name", ""))
        }
        result.normalized = normalized
        return result
    except Exception as e:
        return NormalizationResult(success=False, warnings=[], error_detail=str(e))


def normalize_process_chain(raw_output: Any, action_contract: Any) -> NormalizationResult:
    result = NormalizationResult(normalized=None, success=True, warnings=[])
    try:
        if not isinstance(raw_output, dict):
            return NormalizationResult(success=False, warnings=[], error_detail="Expected dict raw_output")

        # Normalize each sub-result
        scan_norm = normalize_scan_pdf(raw_output.get("scan_result", {}), action_contract)
        extract_norm = normalize_extract_text(raw_output.get("extract_result", {}), action_contract)
        convert_norm = normalize_convert_format(raw_output.get("convert_result", {}), action_contract)
        validate_norm = normalize_validate_schema(raw_output.get("validate_result", {}), action_contract)

        # Collect warnings from all sub-normalizations
        all_warnings = []
        if scan_norm.warnings:
            all_warnings.extend([f"scan: {w}" for w in scan_norm.warnings])
        if extract_norm.warnings:
            all_warnings.extend([f"extract: {w}" for w in extract_norm.warnings])
        if convert_norm.warnings:
            all_warnings.extend([f"convert: {w}" for w in convert_norm.warnings])
        if validate_norm.warnings:
            all_warnings.extend([f"validate: {w}" for w in validate_norm.warnings])

        # Check if any normalization failed
        if not (scan_norm.success and extract_norm.success and convert_norm.success and validate_norm.success):
            return NormalizationResult(success=False, warnings=all_warnings, error_detail="Sub-normalization failed")

        normalized = {
            "scan_result": scan_norm.normalized,
            "extract_result": extract_norm.normalized,
            "convert_result": convert_norm.normalized,
            "validate_result": validate_norm.normalized,
            "chain_success": bool(raw_output.get("chain_success", False)),
            "artifacts": list(raw_output.get("artifacts", []))
        }
        result.normalized = normalized
        result.warnings = all_warnings
        return result
    except Exception as e:
        return NormalizationResult(success=False, warnings=[], error_detail=str(e))


def register_normalizers() -> None:
    register_normalizer("document.scan_pdf", normalize_scan_pdf)
    register_normalizer("document.extract_text", normalize_extract_text)
    register_normalizer("document.convert_format", normalize_convert_format)
    register_normalizer("document.validate_schema", normalize_validate_schema)
    register_normalizer("document.process_chain", normalize_process_chain)
