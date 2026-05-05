from __future__ import annotations

import tempfile
from pathlib import Path

from warden.daemon import FederationWarden, WardenConfig
from warden.llm_gateway import GatewayError
from warden.llm_gateway import GatewayConfig, LLMGateway


def test_gateway_provider_order():
    cfg = GatewayConfig(
        forge_root=Path(".").resolve(),
        trace_dir=Path(tempfile.mkdtemp()).resolve(),
        scan_fallback_order=["ollama", "frontier", "vllm"],
        reasoning_fallback_order=["ollama", "frontier"],
        verdict_fallback_order=["ollama", "frontier"],
    )
    gw = LLMGateway(cfg)
    assert gw._provider_order("TIER_SCAN") == ["ollama", "frontier", "vllm"]
    assert gw._provider_order("TIER_REASONING") == ["ollama", "frontier"]
    assert gw._provider_order("TIER_VERDICT") == ["ollama", "frontier"]


def test_gateway_falls_back_and_writes_success_trace(monkeypatch):
    trace_dir = Path(tempfile.mkdtemp()).resolve()
    cfg = GatewayConfig(
        forge_root=Path(".").resolve(),
        trace_dir=trace_dir,
        scan_fallback_order=["ollama", "vllm"],
    )
    gw = LLMGateway(cfg)
    attempts = []

    def fake_ollama(**_kwargs):
        attempts.append("ollama")
        raise GatewayError("local model unavailable")

    def fake_openai(**_kwargs):
        attempts.append("vllm")
        return {"choices": [{"message": {"content": "fallback response"}}]}

    monkeypatch.setattr(gw, "_call_ollama", fake_ollama)
    monkeypatch.setattr(gw, "_call_openai_compatible", fake_openai)

    response = gw.complete(
        task_tier="TIER_SCAN",
        prompt="scan this change",
        metadata={"request_id": "qa-fallback"},
    )

    assert attempts == ["ollama", "vllm"]
    assert response.text == "fallback response"
    assert response.trace.model_used == f"vllm/{cfg.vllm_model}"
    trace_path = Path(response.trace.raw_response_path)
    assert trace_path.exists()
    assert "qa-fallback" in trace_path.read_text(encoding="utf-8")


def test_daemon_yaml_helpers():
    cfg = WardenConfig(
        forge_root=Path(".").resolve(),
        project_root=Path(".").resolve(),
        project_id="test_project",
    )
    daemon = FederationWarden(config=cfg)
    text = """```yaml
unit_id: external.subprocess
actions:
  - id: check_call
```"""
    extracted = daemon._extract_yaml_block(text)
    assert "unit_id: external.subprocess" in extracted
    assert daemon._is_stub_valid(extracted, expected_unit_id="external.subprocess")
