from pathlib import Path
from typing import Dict, Optional

from .ledger import compute_ledger_hash, compute_last_entry_hash, load_entries, write_checkpoint
from .signing import load_ed25519_private_key, load_ed25519_public_key, sign_bytes, verify_bytes


class LedgerSignatureError(Exception):
    pass


def sign_ledger(ledger_path: str, key_path: str, checkpoints_dir: Optional[str] = None, every_n: Optional[int] = None) -> Dict[str, str]:
    ledger = Path(ledger_path)
    if not ledger.exists():
        raise LedgerSignatureError("ledger missing")
    hash_value = compute_ledger_hash(ledger_path)
    private_key = load_ed25519_private_key(key_path)
    signature = sign_bytes(private_key, hash_value.encode("utf-8"))
    hash_path = ledger.with_suffix(ledger.suffix + ".hash")
    sig_path = ledger.with_suffix(ledger.suffix + ".sig")
    hash_path.write_text(hash_value)
    sig_path.write_text(signature)

    if checkpoints_dir and every_n:
        entries = load_entries(ledger_path)
        if entries:
            count = len(entries)
            if count % every_n == 0:
                last_hash = compute_last_entry_hash(ledger_path)
                if last_hash:
                    checkpoint_path = write_checkpoint(Path(checkpoints_dir), last_hash, count)
                    checkpoint_hash = compute_ledger_hash(str(checkpoint_path))
                    checkpoint_sig = sign_bytes(private_key, checkpoint_hash.encode("utf-8"))
                    checkpoint_path.with_suffix(checkpoint_path.suffix + ".sig").write_text(checkpoint_sig)

    return {"hash": hash_value, "signature": signature}


def verify_ledger(ledger_path: str, pubkey_path: str, checkpoints_dir: Optional[str] = None) -> Dict[str, str]:
    ledger = Path(ledger_path)
    if not ledger.exists():
        raise LedgerSignatureError("ledger missing")
    hash_path = ledger.with_suffix(ledger.suffix + ".hash")
    sig_path = ledger.with_suffix(ledger.suffix + ".sig")
    if not hash_path.exists() or not sig_path.exists():
        raise LedgerSignatureError("ledger signature files missing")

    expected_hash = compute_ledger_hash(ledger_path)
    stored_hash = hash_path.read_text().strip()
    if expected_hash != stored_hash:
        raise LedgerSignatureError("ledger hash mismatch")

    public_key = load_ed25519_public_key(pubkey_path)
    if not verify_bytes(public_key, stored_hash.encode("utf-8"), sig_path.read_text().strip()):
        raise LedgerSignatureError("ledger signature invalid")

    if checkpoints_dir:
        _verify_checkpoints(ledger_path, Path(checkpoints_dir), pubkey_path)

    return {"status": "PASS", "hash": stored_hash}


def _verify_checkpoints(ledger_path: str, checkpoints_dir: Path, pubkey_path: str) -> None:
    if not checkpoints_dir.exists():
        raise LedgerSignatureError("checkpoints directory missing")
    checkpoints = sorted(checkpoints_dir.glob("checkpoint_*.json"))
    if not checkpoints:
        raise LedgerSignatureError("no checkpoints")
    last_entry_hash = compute_last_entry_hash(ledger_path)
    last_checkpoint = checkpoints[-1]
    data = last_checkpoint.read_text().strip()
    expected_last = None
    try:
        import json

        expected_last = json.loads(data).get("last_entry_hash")
    except Exception:
        raise LedgerSignatureError("checkpoint invalid")
    if expected_last != last_entry_hash:
        raise LedgerSignatureError("checkpoint last_entry_hash mismatch")

    sig_path = last_checkpoint.with_suffix(last_checkpoint.suffix + ".sig")
    if not sig_path.exists():
        raise LedgerSignatureError("checkpoint signature missing")
    checkpoint_hash = compute_ledger_hash(str(last_checkpoint))
    public_key = load_ed25519_public_key(pubkey_path)
    if not verify_bytes(public_key, checkpoint_hash.encode("utf-8"), sig_path.read_text().strip()):
        raise LedgerSignatureError("checkpoint signature invalid")
