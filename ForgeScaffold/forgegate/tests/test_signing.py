import json
from pathlib import Path

import pytest

crypto = pytest.importorskip("cryptography")
from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import ed25519  # noqa: E402

from forgegate.cli.main import cmd_validate_bundle, cmd_verify_bundle
from forgegate.core.bundle_signing import sign_bundle, verify_bundle
from forgegate.core.ledger_signing import sign_ledger, verify_ledger


def _write_keypair(tmp_path: Path):
    sk = ed25519.Ed25519PrivateKey.generate()
    pk = sk.public_key()
    sk_bytes = sk.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pk_bytes = pk.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    sk_path = tmp_path / "ed25519_private.pem"
    pk_path = tmp_path / "ed25519_public.pem"
    sk_path.write_bytes(sk_bytes)
    pk_path.write_bytes(pk_bytes)
    return sk_path, pk_path


def _write_bundle(tmp_path: Path) -> Path:
    bundle = tmp_path / "IntentBundle"
    (bundle / "catalogs").mkdir(parents=True)
    (bundle / "intent").mkdir(parents=True)
    (bundle / "tests" / "scenarios").mkdir(parents=True)
    (bundle / "meta.yaml").write_text("owners: []\n")
    (bundle / "catalogs" / "action_catalog.json").write_text('{"schema_version":"0.1","actions":[]}')
    (bundle / "catalogs" / "signal_catalog.json").write_text('{"schema_version":"0.1","signals":[]}')
    (bundle / "intent" / "intent_spec.json").write_text('{"intent_id":"demo","intent_version":"1"}')
    (bundle / "tests" / "scenarios" / "01.json").write_text(
        json.dumps(
            {
                "proposed_action": {"schema_version": "0.1", "action_id": "read", "actor_id": "a", "params": {}},
                "signals": {"schema_version": "0.1", "values": {}},
                "expected": {"decision": "ALLOW"},
            }
        )
    )
    return bundle


def test_sign_and_verify_ok(tmp_path: Path):
    bundle = _write_bundle(tmp_path)
    sk, pk = _write_keypair(tmp_path)
    sign_bundle(str(bundle), str(sk))
    result = verify_bundle(str(bundle), str(pk))
    assert result["status"] == "PASS"
    args = type("Args", (), {"bundle": str(bundle), "pubkey": str(pk)})
    assert cmd_verify_bundle(args) == 0


def test_verify_fails_on_tamper(tmp_path: Path):
    bundle = _write_bundle(tmp_path)
    sk, pk = _write_keypair(tmp_path)
    sign_bundle(str(bundle), str(sk))
    (bundle / "intent" / "intent_spec.json").write_text('{"intent_id":"demo","intent_version":"2"}')
    args = type("Args", (), {"bundle": str(bundle), "pubkey": str(pk)})
    assert cmd_verify_bundle(args) == 20


def test_validate_bundle_require_signature_missing(tmp_path: Path):
    bundle = _write_bundle(tmp_path)
    sk, pk = _write_keypair(tmp_path)
    args = type("Args", (), {"bundle": str(bundle), "require_signature": True, "pubkey": str(pk)})
    assert cmd_validate_bundle(args) != 0


def test_validate_bundle_require_signature_invalid(tmp_path: Path):
    bundle = _write_bundle(tmp_path)
    sk, pk = _write_keypair(tmp_path)
    sign_bundle(str(bundle), str(sk))
    (bundle / "intent" / "intent_spec.json").write_text('{"intent_id":"demo","intent_version":"2"}')
    args = type("Args", (), {"bundle": str(bundle), "require_signature": True, "pubkey": str(pk)})
    assert cmd_validate_bundle(args) != 0


def test_verify_missing_signature(tmp_path: Path):
    bundle = _write_bundle(tmp_path)
    _, pk = _write_keypair(tmp_path)
    args = type("Args", (), {"bundle": str(bundle), "pubkey": str(pk)})
    assert cmd_verify_bundle(args) == 21


def test_ledger_sign_verify(tmp_path: Path):
    ledger = tmp_path / "ledger.jsonl"
    entry = {
        "schema_version": "0.1",
        "timestamp": "2026-01-01T00:00:00Z",
        "intent_id": "demo",
        "intent_version": "1",
        "decision": "ALLOW",
        "decision_id": "a" * 64,
        "input_hash": "b" * 64,
        "action_id": "read",
        "actor_id": "agent",
        "decision_record": {"reasons": {"triggered_rules": []}},
    }
    ledger.write_text(__import__("json").dumps(entry) + "\n")
    sk, pk = _write_keypair(tmp_path)
    sign_ledger(str(ledger), str(sk))
    result = verify_ledger(str(ledger), str(pk))
    assert result["status"] == "PASS"
