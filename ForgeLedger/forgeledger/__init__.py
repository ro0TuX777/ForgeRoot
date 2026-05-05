"""
ForgeLedger — immutable, tamper-evident audit event ledger for ForgeRoot.

Public surface:
  - LedgerEvent and sub-types (schema)
  - LedgerBackend ABC + JsonlBackend + WormBackend (backend)
  - LedgerEmitter, LedgerWriteFailedError (emitter)
  - attach_integrity, verify_chain (hash_chain)
  - ForgeLedgerClient SDK (sdk)
  - sign_event, verify_signature (signing)
  - ReplayProtector, ReplayDetectedError (replay_protection)
"""
from forgeledger.schema import (
    LEDGER_VERSION,
    EventType,
    RetentionClass,
    Actor,
    Tenant,
    SystemContext,
    Decision,
    EvidenceGap,
    Evidence,
    Policy,
    Integrity,
    LedgerEvent,
    RedactionReceipt,
    event_from_dict,
)
from forgeledger.redaction import IngestRedactor, RedactionPolicy
from forgeledger.backend import (
    AppendResult,
    LedgerQuery,
    HoldSelector,
    HoldResult,
    ChainValidationReport,
    ExportSelector,
    LedgerBackend,
)
from forgeledger.hash_chain import attach_integrity, verify_chain, compute_event_hash
from forgeledger.emitter import LedgerEmitter, LedgerWriteFailedError
from forgeledger.audit import emit_audit_event
from forgeledger.audited_backend import AuditedLedgerBackend
from forgeledger.jsonl_backend import JsonlBackend
from forgeledger.worm_backend import WormBackend, WormViolationError
from forgeledger.worm_object_backend import (
    AzureImmutableBlobBackend,
    LocalWormObjectBackend,
    S3ObjectLockBackend,
    WasabiWormBucketBackend,
    WormObjectBackend,
    WormObjectManifest,
    WormVerificationReport,
)
from forgeledger.signing import sign_event, verify_signature
from forgeledger.replay_protection import ReplayProtector, ReplayDetectedError
from forgeledger.durable_replay import DurableReplayProtector
from forgeledger.retention_lifecycle import (
    RetentionAction,
    RetentionApplyResult,
    RetentionLifecycleManager,
    RetentionScanReport,
)
from forgeledger.key_management import (
    EnvironmentKeyProvider,
    FileKeyProvider,
    HsmKeyProvider,
    KeyMaterial,
    KeyProvider,
    KmsKeyProvider,
    StaticKeyProvider,
)
from forgeledger.checkpoint import (
    ChainCheckpoint,
    CheckpointManager,
    CheckpointVerificationReport,
)
from forgeledger.anchoring import (
    AnchorBackend,
    AnchorRecord,
    AnchorVerificationReport,
    CloudImmutableAnchorBackend,
    LocalAnchorBackend,
)
from forgeledger.sdk import ForgeLedgerClient, InvalidEventError, TenantBoundaryViolationError

__all__ = [
    # schema
    "LEDGER_VERSION",
    "EventType",
    "RetentionClass",
    "Actor",
    "Tenant",
    "SystemContext",
    "Decision",
    "EvidenceGap",
    "Evidence",
    "Policy",
    "Integrity",
    "LedgerEvent",
    "RedactionReceipt",
    "event_from_dict",
    # redaction
    "IngestRedactor",
    "RedactionPolicy",
    # backend
    "AppendResult",
    "LedgerQuery",
    "HoldSelector",
    "HoldResult",
    "ChainValidationReport",
    "ExportSelector",
    "LedgerBackend",
    "JsonlBackend",
    "WormBackend",
    "WormViolationError",
    "WormObjectBackend",
    "WormObjectManifest",
    "WormVerificationReport",
    "LocalWormObjectBackend",
    "S3ObjectLockBackend",
    "AzureImmutableBlobBackend",
    "WasabiWormBucketBackend",
    # hash chain
    "attach_integrity",
    "verify_chain",
    "compute_event_hash",
    # emitter
    "LedgerEmitter",
    "LedgerWriteFailedError",
    "emit_audit_event",
    "AuditedLedgerBackend",
    # signing
    "sign_event",
    "verify_signature",
    # replay protection
    "ReplayProtector",
    "ReplayDetectedError",
    "DurableReplayProtector",
    # retention lifecycle
    "RetentionAction",
    "RetentionApplyResult",
    "RetentionLifecycleManager",
    "RetentionScanReport",
    # key management
    "EnvironmentKeyProvider",
    "FileKeyProvider",
    "HsmKeyProvider",
    "KeyMaterial",
    "KeyProvider",
    "KmsKeyProvider",
    "StaticKeyProvider",
    # checkpoints
    "ChainCheckpoint",
    "CheckpointManager",
    "CheckpointVerificationReport",
    # anchors
    "AnchorBackend",
    "AnchorRecord",
    "AnchorVerificationReport",
    "CloudImmutableAnchorBackend",
    "LocalAnchorBackend",
    # SDK
    "ForgeLedgerClient",
    "InvalidEventError",
    "TenantBoundaryViolationError",
]
