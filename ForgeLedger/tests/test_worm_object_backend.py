"""Phase 8b WORM object backend tests."""
import hashlib
import json

import pytest

from forgeledger.worm_backend import WormViolationError
from forgeledger.worm_object_backend import (
    AzureImmutableBlobBackend,
    LocalWormObjectBackend,
    S3ObjectLockBackend,
)


def test_local_worm_write_once_object(tmp_path):
    backend = LocalWormObjectBackend(tmp_path / "objects")

    manifest = backend.write_object("evidence-001.json", b'{"ok":true}')

    assert manifest.object_id == "evidence-001.json"
    assert (tmp_path / "objects" / "evidence-001.json").read_bytes() == b'{"ok":true}'


def test_local_worm_rejects_overwrite_existing_object(tmp_path):
    backend = LocalWormObjectBackend(tmp_path / "objects")
    backend.write_object("evidence-001.json", "first")

    with pytest.raises(WormViolationError):
        backend.write_object("evidence-001.json", "second")


def test_local_worm_rejects_delete(tmp_path):
    backend = LocalWormObjectBackend(tmp_path / "objects")
    backend.write_object("evidence-001.json", "content")

    with pytest.raises(WormViolationError):
        backend.delete_object("evidence-001.json")


def test_local_worm_rejects_mutation(tmp_path):
    backend = LocalWormObjectBackend(tmp_path / "objects")
    backend.write_object("evidence-001.json", "content")

    with pytest.raises(WormViolationError):
        backend.mutate_object("evidence-001.json", "changed")

    with pytest.raises(WormViolationError):
        backend.update_object("evidence-001.json", "changed")


def test_worm_manifest_records_sha256(tmp_path):
    backend = LocalWormObjectBackend(tmp_path / "objects")

    manifest = backend.write_object("evidence-001.json", "content")

    assert manifest.sha256 == hashlib.sha256(b"content").hexdigest()


def test_worm_manifest_records_retention_until(tmp_path):
    backend = LocalWormObjectBackend(tmp_path / "objects")

    manifest = backend.write_object(
        "evidence-001.json",
        "content",
        retention_until="2033-04-30T00:00:00+00:00",
    )

    assert manifest.retention_until == "2033-04-30T00:00:00+00:00"


def test_worm_manifest_records_legal_hold(tmp_path):
    backend = LocalWormObjectBackend(tmp_path / "objects")

    manifest = backend.write_object("evidence-001.json", "content", legal_hold=True)

    assert manifest.legal_hold is True


def test_verify_manifest_passes_for_untampered_objects(tmp_path):
    backend = LocalWormObjectBackend(tmp_path / "objects")
    backend.write_object("evidence-001.json", "content")

    report = backend.verify_manifest()

    assert report.valid is True
    assert report.object_count == 1
    assert report.mismatched_objects == []
    assert report.missing_objects == []


def test_verify_manifest_detects_tampered_object(tmp_path):
    backend = LocalWormObjectBackend(tmp_path / "objects")
    backend.write_object("evidence-001.json", "content")
    (tmp_path / "objects" / "evidence-001.json").write_text("tampered", encoding="utf-8")

    report = backend.verify_manifest()

    assert report.valid is False
    assert report.mismatched_objects == ["evidence-001.json"]


def test_verify_manifest_detects_missing_object(tmp_path):
    backend = LocalWormObjectBackend(tmp_path / "objects")
    backend.write_object("evidence-001.json", "content")
    (tmp_path / "objects" / "evidence-001.json").unlink()

    report = backend.verify_manifest()

    assert report.valid is False
    assert report.missing_objects == ["evidence-001.json"]


def test_s3_object_lock_backend_stub_is_explicitly_not_implemented():
    with pytest.raises(NotImplementedError):
        S3ObjectLockBackend().verify_manifest()


def test_azure_immutable_blob_backend_stub_is_explicitly_not_implemented():
    with pytest.raises(NotImplementedError):
        AzureImmutableBlobBackend().verify_manifest()


def test_worm_manifest_is_append_only_jsonl(tmp_path):
    manifest_path = tmp_path / "worm_manifest.jsonl"
    backend = LocalWormObjectBackend(tmp_path / "objects", manifest_path=manifest_path)
    first = backend.write_object("evidence-001.json", "first")
    second = backend.write_object("evidence-002.json", "second")

    lines = manifest_path.read_text(encoding="utf-8").splitlines()

    assert len(lines) == 2
    assert json.loads(lines[0])["object_id"] == first.object_id
    assert json.loads(lines[1])["object_id"] == second.object_id


def test_worm_backend_type_labels_local_simulation(tmp_path):
    backend = LocalWormObjectBackend(tmp_path / "objects")

    manifest = backend.write_object("evidence-001.json", "content")

    assert manifest.backend_type == "local_worm_simulation"


def test_verify_manifest_fails_closed_on_corrupt_manifest_line(tmp_path):
    manifest_path = tmp_path / "worm_manifest.jsonl"
    backend = LocalWormObjectBackend(tmp_path / "objects", manifest_path=manifest_path)
    backend.write_object("evidence-001.json", "content")
    with open(manifest_path, "a", encoding="utf-8") as f:
        f.write("{not-json}\n")

    report = backend.verify_manifest()

    assert report.valid is False
    assert "Invalid WORM manifest JSONL" in (report.error or "")
