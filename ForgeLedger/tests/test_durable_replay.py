"""Phase 7b durable replay protection tests."""
import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from forgeledger.durable_replay import DurableReplayProtector
from forgeledger.replay_protection import ReplayDetectedError


def test_durable_replay_rejects_duplicate_in_same_session(tmp_path):
    protector = DurableReplayProtector(tmp_path / "replay.jsonl")
    protector.check_and_register("evt-001")

    with pytest.raises(ReplayDetectedError):
        protector.check_and_register("evt-001")


def test_durable_replay_rejects_duplicate_after_reload(tmp_path):
    path = tmp_path / "replay.jsonl"
    DurableReplayProtector(path).check_and_register("evt-001")
    reloaded = DurableReplayProtector(path)

    with pytest.raises(ReplayDetectedError):
        reloaded.check_and_register("evt-001")


def test_durable_replay_persists_seen_id_to_file_immediately(tmp_path):
    path = tmp_path / "replay.jsonl"
    protector = DurableReplayProtector(path)

    protector.check_and_register("evt-001")

    assert "evt-001" in path.read_text(encoding="utf-8")


def test_durable_replay_loads_existing_ids_on_init(tmp_path):
    path = tmp_path / "replay.jsonl"
    path.write_text('{"event_id":"evt-existing","registered_at":"2026-04-29T00:00:00+00:00"}\n', encoding="utf-8")

    protector = DurableReplayProtector(path)

    assert protector.is_seen("evt-existing") is True


def test_fresh_protector_with_no_file_starts_empty(tmp_path):
    protector = DurableReplayProtector(tmp_path / "missing.jsonl")

    assert protector.is_seen("evt-001") is False


def test_concurrent_events_with_distinct_ids_all_accepted(tmp_path):
    protector = DurableReplayProtector(tmp_path / "replay.jsonl")
    event_ids = [f"evt-{index:03d}" for index in range(20)]

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(protector.check_and_register, event_ids))

    assert all(protector.is_seen(event_id) for event_id in event_ids)


def test_store_file_format_is_append_only_jsonl(tmp_path):
    path = tmp_path / "replay.jsonl"
    protector = DurableReplayProtector(path)
    protector.check_and_register("evt-001")
    protector.check_and_register("evt-002")

    lines = path.read_text(encoding="utf-8").splitlines()

    assert len(lines) == 2
    assert [json.loads(line)["event_id"] for line in lines] == ["evt-001", "evt-002"]


def test_corrupted_store_file_raises_on_init(tmp_path):
    path = tmp_path / "replay.jsonl"
    path.write_text("{not-json}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid durable replay JSONL"):
        DurableReplayProtector(path)
