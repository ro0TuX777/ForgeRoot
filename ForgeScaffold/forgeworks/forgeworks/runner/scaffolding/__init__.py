"""
ForgeWorks Scaffolding Helpers
================================
Pre-flight coding context, patchset adapter, and test matrix validator
ported from SAM's ForgeScaffold integration layer.
"""
from .forgescaffold_coding_context import ForgeScaffoldCodingContext
from .forgescaffold_test_validator import (
    generate_test_matrix,
    validate_code_proposal,
    format_test_matrix_for_prompt,
)
from .forgescaffold_adapter import (
    create_patchset,
    stamp_ticket_event,
    get_ticket_evidence,
)

__all__ = [
    "ForgeScaffoldCodingContext",
    "generate_test_matrix",
    "validate_code_proposal",
    "format_test_matrix_for_prompt",
    "create_patchset",
    "stamp_ticket_event",
    "get_ticket_evidence",
]
