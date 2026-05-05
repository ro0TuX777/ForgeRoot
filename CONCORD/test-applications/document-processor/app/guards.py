from __future__ import annotations

import os
from typing import Any, Dict

from app.registry import register_guard


def service_healthy(parameters: Dict[str, Any], session: Any, action_contract: Any) -> Dict[str, Any]:
    return {"passed": True, "guard_name": "service_healthy"}


def file_accessible(parameters: Dict[str, Any], session: Any, action_contract: Any) -> Dict[str, Any]:
    document_path = parameters.get("document_path")
    if not document_path:
        return {
            "passed": False,
            "guard_name": "file_accessible",
            "reason": "document_path is required",
        }
    if not os.path.exists(document_path):
        return {
            "passed": False,
            "guard_name": "file_accessible",
            "reason": f"Document path not found: {document_path}",
        }
    if not os.access(document_path, os.R_OK):
        return {
            "passed": False,
            "guard_name": "file_accessible",
            "reason": f"Document path not readable: {document_path}",
        }
    return {"passed": True, "guard_name": "file_accessible"}


def register_guards() -> None:
    register_guard("service_healthy", service_healthy)
    register_guard("file_accessible", file_accessible)
