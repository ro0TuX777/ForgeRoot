"""
Ingest-time redaction for ForgeTranscript segments.

Redaction runs BEFORE hash chain attachment so the chain covers exactly
the form of the segment that is persisted. This mirrors ForgeLedger's
redaction model.

Redaction policy is trust-tier-aware:
    T1 agents: all content-bearing fields redacted by default
    T2 agents: configurable redaction based on content classification
    T3 agents: minimal redaction (high-trust operators)

Redacted segments retain their chain position and hash integrity.
The redaction itself is recorded as an auditable event.
"""
from __future__ import annotations

import dataclasses
import hashlib
from dataclasses import dataclass, field
from typing import Optional

from forgetranscript.schema import SegmentType, TranscriptSegment


# Segment types whose content is always preserved (governance metadata).
# These are never redacted because they carry structural information
# needed for compliance auditing (UC2) and forensic reconstruction (UC1).
_GOVERNANCE_SEGMENT_TYPES = frozenset({
    SegmentType.DECISION_REF,
    SegmentType.SYSTEM_EVENT,
})


@dataclass
class TranscriptRedactionPolicy:
    """Policy controlling what gets redacted from transcript segments.

    Attributes:
        allow_raw_storage: If True, no redaction is applied (testing only).
        trust_tier_threshold: Minimum trust tier below which all content is redacted.
        sensitive_patterns: Substrings that trigger redaction when found in content.
        content_segment_types: Segment types whose content field is subject to redaction.
        metadata_fields_to_redact: Metadata keys to redact (e.g., "tool_args", "credentials").
    """
    allow_raw_storage: bool = False
    trust_tier_threshold: str = "T1"
    sensitive_patterns: list[str] = field(
        default_factory=lambda: ["password", "api_key", "token", "secret", "credential"]
    )
    content_segment_types: list[SegmentType] = field(
        default_factory=lambda: [
            SegmentType.REASONING,
            SegmentType.TOOL_CALL,
            SegmentType.TOOL_RESULT,
            SegmentType.USER_EXCHANGE,
        ]
    )
    metadata_fields_to_redact: list[str] = field(
        default_factory=lambda: ["tool_args", "credentials", "auth_headers"]
    )


@dataclass
class SegmentRedactionReceipt:
    """Record of a redaction action on a specific segment."""
    segment_id: str
    field_path: str           # "content" or "metadata.<key>"
    sha256_of_original: str   # Hex SHA-256 of the raw value before redaction
    redacted_at: str          # ISO 8601 UTC timestamp


class SegmentRedactor:
    """Applies ingest-time redaction to transcript segments.

    Pipeline position:
        TranscriptEmitter captures raw segment
        → SegmentRedactor.redact()      (this class)
        → attach_segment_hash()          (chain covers redacted form)
        → TranscriptStore.append()       (persist)

    Thread-safe: this class is stateless.
    """

    def __init__(
        self,
        policy: Optional[TranscriptRedactionPolicy] = None,
    ) -> None:
        self._policy = policy or TranscriptRedactionPolicy()

    def redact(
        self,
        segment: TranscriptSegment,
        trust_tier: str,
        timestamp: Optional[str] = None,
    ) -> tuple[TranscriptSegment, list[SegmentRedactionReceipt]]:
        """Redact sensitive content from a segment based on policy and trust tier.

        Returns:
            Tuple of (redacted_segment, list_of_redaction_receipts).
            If no redaction occurred, returns (original_segment, []).
        """
        if self._policy.allow_raw_storage:
            return segment, []

        # Governance segment types are never redacted
        if segment.segment_type in _GOVERNANCE_SEGMENT_TYPES:
            return segment, []

        from datetime import datetime, timezone
        redacted_at = timestamp or datetime.now(timezone.utc).isoformat()

        receipts: list[SegmentRedactionReceipt] = []
        new_content = segment.content
        new_metadata = dict(segment.metadata) if segment.metadata else None

        # Redact content field if segment type is in the policy scope
        if segment.segment_type in self._policy.content_segment_types:
            if self._should_redact_content(segment.content, trust_tier):
                sha = hashlib.sha256(segment.content.encode("utf-8")).hexdigest()
                new_content = f"[REDACTED:sha256:{sha}]"
                receipts.append(SegmentRedactionReceipt(
                    segment_id=segment.segment_id,
                    field_path="content",
                    sha256_of_original=sha,
                    redacted_at=redacted_at,
                ))

        # Redact specific metadata fields
        if new_metadata:
            for field_name in self._policy.metadata_fields_to_redact:
                if field_name in new_metadata:
                    original = str(new_metadata[field_name])
                    sha = hashlib.sha256(original.encode("utf-8")).hexdigest()
                    new_metadata[field_name] = f"[REDACTED:sha256:{sha}]"
                    receipts.append(SegmentRedactionReceipt(
                        segment_id=segment.segment_id,
                        field_path=f"metadata.{field_name}",
                        sha256_of_original=sha,
                        redacted_at=redacted_at,
                    ))

        if not receipts:
            return segment, []

        redacted_segment = dataclasses.replace(
            segment,
            content=new_content,
            metadata=new_metadata,
            redacted=True,
            redaction_receipt_hash=receipts[0].sha256_of_original if receipts else None,
        )
        return redacted_segment, receipts

    def _should_redact_content(self, content: str, trust_tier: str) -> bool:
        """Determine if content should be redacted based on trust tier and patterns."""
        tier_order = {"T1": 1, "T2": 2, "T3": 3}
        threshold_level = tier_order.get(self._policy.trust_tier_threshold, 1)
        agent_level = tier_order.get(trust_tier, 1)

        # Low-trust agents always get content redacted
        if agent_level <= threshold_level:
            return True

        # Check for sensitive patterns in content
        content_lower = content.lower()
        return any(pattern in content_lower for pattern in self._policy.sensitive_patterns)
