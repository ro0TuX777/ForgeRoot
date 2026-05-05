"""
ForgeScaffold Test Matrix Validator
=====================================

Enforces TDD at the infrastructure level:
  - BEFORE code is written: generate_test_matrix() produces L0-L3 success criteria
  - AFTER code is proposed: validate_code_proposal() gates PENDING_APPROVAL

This makes "define success before coding" a hard contract, not a suggestion.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Levels mirror ForgeScaffold's canonical test hierarchy
LEVELS = ["L0_contract", "L1_slice", "L2_smoke", "L3_nonfunctional"]

LEVEL_DESCRIPTIONS = {
    "L0_contract": "Schema/interface stability — importing the module works and its public API is unchanged",
    "L1_slice": "Dependency-light integration — the unit + 1 direct dependency behave correctly together",
    "L2_smoke": "End-to-end smoke — a minimal run produces expected output without errors",
    "L3_nonfunctional": "Performance/security/reliability — latency, memory, and error-handling checks",
}


def generate_test_matrix(
    ticket_id: str,
    ticket_name: str,
    target_file: str,
    relevant_units: Optional[List[Dict[str, Any]]] = None,
    impact_units: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Generate a ForgeScaffold-style test matrix for a SAM coding ticket.

    Returns a structured artifact with:
      - success_criteria: human-readable list of what done looks like
      - test_levels: L0-L3 test specifications per relevant unit
      - validation_contract: what the code proposal MUST contain
    """
    relevant_units = relevant_units or []
    impact_units = impact_units or []

    target_module = Path(target_file).stem
    target_package = str(Path(target_file).parent).replace("/", ".").replace("\\", ".")

    # ─── High-level success criteria ─────────────────────────────────────────
    success_criteria = [
        f"The modified `{target_module}` module imports without errors (L0)",
        f"All existing public functions/methods in `{target_module}` retain their signatures (L0)",
        f"The change achieves the stated goal: {ticket_name} (L1)",
        f"No modules in the impact radius raise new import or runtime errors (L1)",
        f"A smoke test (minimal invocation) of the modified unit succeeds (L2)",
        "No new unbounded loops, uncaught exceptions, or hard-coded credentials are introduced (L3)",
    ]

    # ─── Per-unit test specs ──────────────────────────────────────────────────
    test_levels: Dict[str, List[Dict[str, Any]]] = {level: [] for level in LEVELS}

    all_units = relevant_units + impact_units[:5]  # cap impact units for brevity
    for unit in all_units:
        uid = unit.get("id", target_module)
        path = unit.get("path", target_file)
        lang = unit.get("language", "python")

        test_levels["L0_contract"].append({
            "unit_id": uid,
            "description": LEVEL_DESCRIPTIONS["L0_contract"],
            "command": f"python3 -c \"import {uid.replace('/', '.')}; print('✅ {uid} importable')\"",
            "success_condition": f"Exit code 0, no ImportError",
        })

        test_levels["L1_slice"].append({
            "unit_id": uid,
            "description": LEVEL_DESCRIPTIONS["L1_slice"],
            "command": f"python3 -m pytest {path} -x -q --tb=short 2>&1 | head -30",
            "success_condition": "No test failures",
        })

        test_levels["L2_smoke"].append({
            "unit_id": uid,
            "description": LEVEL_DESCRIPTIONS["L2_smoke"],
            "command": f"python3 {path} 2>&1 | head -10" if lang == "python" else f"echo 'TODO: smoke {uid}'",
            "success_condition": "Runs without unhandled exception",
        })

        test_levels["L3_nonfunctional"].append({
            "unit_id": uid,
            "description": LEVEL_DESCRIPTIONS["L3_nonfunctional"],
            "command": f"echo 'TODO: perf/security check for {uid}'",
            "success_condition": "No obvious regressions or security smells",
        })

    # ─── Validation contract (what the code proposal MUST include) ───────────
    validation_contract = {
        "required_fields": ["success_criteria", "test_evidence"],
        "min_success_criteria": 2,
        "forbidden_patterns": [
            "assert True",       # anti-gaming
            "# TODO: test",      # incomplete
            "pass  # placeholder",
        ],
        "description": (
            "The Coder LLM's response MUST include a 'success_criteria' list and 'test_evidence' "
            "field before the proposal can advance to PENDING_APPROVAL status."
        ),
    }

    matrix = {
        "schema_version": "1.0.0",
        "ticket_id": ticket_id,
        "ticket_name": ticket_name,
        "target_file": target_file,
        "target_package": target_package,
        "success_criteria": success_criteria,
        "test_levels": test_levels,
        "validation_contract": validation_contract,
        "impact_unit_count": len(impact_units),
        "relevant_unit_count": len(relevant_units),
    }

    logger.info(
        f"📋 ForgeScaffold test matrix generated for ticket {ticket_id}: "
        f"{len(success_criteria)} criteria, {sum(len(v) for v in test_levels.values())} tests"
    )
    return matrix


def validate_code_proposal(
    proposal: Dict[str, Any],
    test_matrix: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Validate a Coder LLM's code proposal against the ForgeScaffold test matrix.

    Returns:
        {
            "valid": bool,
            "score": float,       # 0.0–1.0
            "violations": [...],  # list of specific failures
            "warnings": [...],    # non-blocking issues
        }
    """
    violations = []
    warnings = []
    contract = test_matrix.get("validation_contract", {})

    # ─── Required fields check ────────────────────────────────────────────────
    for field in contract.get("required_fields", []):
        if not proposal.get(field):
            violations.append(f"Missing required field: `{field}`")

    # ─── Minimum success criteria ─────────────────────────────────────────────
    criteria = proposal.get("success_criteria", [])
    min_criteria = contract.get("min_success_criteria", 2)
    if isinstance(criteria, list) and len(criteria) < min_criteria:
        violations.append(
            f"Too few success_criteria: got {len(criteria)}, need ≥ {min_criteria}"
        )

    # ─── Forbidden pattern guard ──────────────────────────────────────────────
    code_content = proposal.get("optimized_content", "") or proposal.get("code_proposal", "")
    for pattern in contract.get("forbidden_patterns", []):
        if pattern in code_content:
            violations.append(f"Forbidden pattern detected: `{pattern}`")

    # ─── Soft warnings ────────────────────────────────────────────────────────
    if not proposal.get("reasoning"):
        warnings.append("No reasoning provided — blind code changes are discouraged")

    if len(code_content) < 50:
        warnings.append("Code proposal appears very short — confirm this is intentional")

    score = max(0.0, 1.0 - (len(violations) * 0.3) - (len(warnings) * 0.05))

    result = {
        "valid": len(violations) == 0,
        "score": round(score, 2),
        "violations": violations,
        "warnings": warnings,
        "ticket_id": test_matrix.get("ticket_id"),
        "target_file": test_matrix.get("target_file"),
    }

    if result["valid"]:
        logger.info(f"✅ Code proposal validated (score: {score:.2f})")
    else:
        logger.warning(f"❌ Code proposal FAILED validation: {violations}")

    return result


def format_test_matrix_for_prompt(test_matrix: Dict[str, Any]) -> str:
    """
    Format the test matrix as a concise Markdown block for injection into
    the Coder LLM's prompt. Enforces TDD framing.
    """
    lines = ["## 📋 ForgeScaffold Test Matrix — Define Success Before Coding\n"]
    lines.append(f"**Ticket**: {test_matrix.get('ticket_name', 'N/A')}")
    lines.append(f"**Target**: `{test_matrix.get('target_file', 'N/A')}`\n")

    lines.append("### Success Criteria (your code MUST satisfy ALL of these)")
    for i, criterion in enumerate(test_matrix.get("success_criteria", []), 1):
        lines.append(f"{i}. {criterion}")
    lines.append("")

    lines.append("### Contract")
    contract = test_matrix.get("validation_contract", {})
    lines.append(f"> {contract.get('description', '')}")
    lines.append("")
    lines.append("**Your response MUST include:**")
    for field in contract.get("required_fields", []):
        lines.append(f"- `{field}`: ...")
    lines.append("")
    lines.append("**Forbidden patterns (these will block approval):**")
    for pat in contract.get("forbidden_patterns", []):
        lines.append(f"- `{pat}`")

    return "\n".join(lines)
