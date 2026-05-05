from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from app.models import ExecutionResult
from app.registry import register_executor


BASE_DIR = Path(__file__).resolve().parents[1]
SAMPLE_DOCS_DIR = BASE_DIR / "data" / "sample_docs"


def execute_scan_pdf(parameters: Dict[str, Any], session: Any, action_contract: Any) -> ExecutionResult:
    document_path = parameters.get("document_path")
    if not document_path:
        return ExecutionResult(success=False, error_code="INVALID_PARAMETERS", error_detail="document_path missing")

    try:
        with open(document_path, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
    except FileNotFoundError as e:
        return ExecutionResult(success=False, error_code="FILE_NOT_FOUND", error_detail=str(e))
    except Exception as e:
        return ExecutionResult(success=False, error_code="EXECUTION_FAILED", error_detail=str(e))

    max_pages = parameters.get("max_pages", 0)
    if max_pages and max_pages > len(lines):
        max_pages = len(lines)

    text = "\n".join(lines[:max_pages or len(lines)])
    raw = {
        "num_pages": max_pages or len(lines),
        "extracted_text": text,
        "extraction_confidence": 0.87,
        "processing_warnings": []
    }
    return ExecutionResult(success=True, result_summary=raw)


def execute_extract_text(parameters: Dict[str, Any], session: Any, action_contract: Any) -> ExecutionResult:
    document_path = parameters.get("document_path")
    if not document_path:
        return ExecutionResult(success=False, error_code="INVALID_PARAMETERS", error_detail="document_path missing")

    try:
        with open(document_path, "r", encoding=parameters.get("encoding", "utf-8")) as f:
            text = f.read()
    except FileNotFoundError as e:
        return ExecutionResult(success=False, error_code="FILE_NOT_FOUND", error_detail=str(e))
    except Exception as e:
        return ExecutionResult(success=False, error_code="EXECUTION_FAILED", error_detail=str(e))

    words = text.split()
    raw = {
        "text": text,
        "word_count": len(words)
    }
    return ExecutionResult(success=True, result_summary=raw)


def execute_convert_format(parameters: Dict[str, Any], session: Any, action_contract: Any) -> ExecutionResult:
    document_path = parameters.get("document_path")
    target_format = parameters.get("target_format")
    if not document_path or not target_format:
        return ExecutionResult(success=False, error_code="INVALID_PARAMETERS", error_detail="document_path and target_format are required")

    try:
        with open(document_path, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError as e:
        return ExecutionResult(success=False, error_code="FILE_NOT_FOUND", error_detail=str(e))
    except Exception as e:
        return ExecutionResult(success=False, error_code="EXECUTION_FAILED", error_detail=str(e))

    base = Path(document_path).stem
    output_path = str(Path(document_path).parent / f"{base}.converted.{target_format}")
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            if target_format == "md":
                f.write(content)
            elif target_format == "json":
                json.dump({"content": content}, f, indent=2)
            else:
                f.write(content)
    except Exception as e:
        return ExecutionResult(success=False, error_code="EXECUTION_FAILED", error_detail=str(e))

    raw = {
        "conversion_success": True,
        "output_path": output_path,
        "bytes_written": Path(output_path).stat().st_size,
        "warnings": []
    }
    return ExecutionResult(success=True, result_summary=raw)


def execute_validate_schema(parameters: Dict[str, Any], session: Any, action_contract: Any) -> ExecutionResult:
    document_path = parameters.get("document_path")
    schema_name = parameters.get("schema_name")
    if not document_path or not schema_name:
        return ExecutionResult(success=False, error_code="INVALID_PARAMETERS", error_detail="document_path and schema_name are required")

    if schema_name not in {"basic", "strict"}:
        return ExecutionResult(success=False, error_code="INVALID_PARAMETERS", error_detail="unsupported schema_name")

    try:
        with open(document_path, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError as e:
        return ExecutionResult(success=False, error_code="FILE_NOT_FOUND", error_detail=str(e))
    except Exception as e:
        return ExecutionResult(success=False, error_code="EXECUTION_FAILED", error_detail=str(e))

    errors = []
    if schema_name == "strict" and len(content) < 20:
        errors.append("Document is too short for strict validation")

    raw = {
        "valid": len(errors) == 0,
        "errors": errors,
        "schema_name": schema_name
    }
    return ExecutionResult(success=True, result_summary=raw)


def execute_process_chain(parameters: Dict[str, Any], session: Any, action_contract: Any) -> ExecutionResult:
    document_path = parameters.get("document_path")
    target_format = parameters.get("target_format", "md")
    if not document_path:
        return ExecutionResult(success=False, error_code="INVALID_PARAMETERS", error_detail="document_path is required")

    artifacts = []
    chain_success = True

    # Step 1: Scan the document
    scan_result = execute_scan_pdf({"document_path": document_path, "max_pages": 10}, session, action_contract)
    if not scan_result.success:
        chain_success = False
        scan_summary = {"error": scan_result.error_detail}
    else:
        scan_summary = scan_result.result_summary
        artifacts.append(f"scanned: {document_path}")

    # Step 2: Extract text
    extract_result = execute_extract_text({"document_path": document_path}, session, action_contract)
    if not extract_result.success:
        chain_success = False
        extract_summary = {"error": extract_result.error_detail}
    else:
        extract_summary = extract_result.result_summary
        artifacts.append(f"extracted: {document_path}")

    # Step 3: Convert format
    convert_result = execute_convert_format({"document_path": document_path, "target_format": target_format}, session, action_contract)
    if not convert_result.success:
        chain_success = False
        convert_summary = {"error": convert_result.error_detail}
    else:
        convert_summary = convert_result.result_summary
        artifacts.append(f"converted: {convert_result.result_summary.get('output_path', 'unknown')}")

    # Step 4: Validate the converted file
    if convert_result.success:
        validate_path = convert_result.result_summary.get("output_path", document_path)
        validate_result = execute_validate_schema({"document_path": validate_path, "schema_name": "basic"}, session, action_contract)
        if not validate_result.success:
            chain_success = False
            validate_summary = {"error": validate_result.error_detail}
        else:
            validate_summary = validate_result.result_summary
    else:
        validate_summary = {"error": "Conversion failed, skipping validation"}

    raw = {
        "scan_result": scan_summary,
        "extract_result": extract_summary,
        "convert_result": convert_summary,
        "validate_result": validate_summary,
        "chain_success": chain_success,
        "artifacts": artifacts
    }
    return ExecutionResult(success=True, result_summary=raw)  # Chain always succeeds, but reports internal failures


def register_executors() -> None:
    register_executor("document.scan_pdf", execute_scan_pdf)
    register_executor("document.extract_text", execute_extract_text)
    register_executor("document.convert_format", execute_convert_format)
    register_executor("document.validate_schema", execute_validate_schema)
    register_executor("document.process_chain", execute_process_chain)
