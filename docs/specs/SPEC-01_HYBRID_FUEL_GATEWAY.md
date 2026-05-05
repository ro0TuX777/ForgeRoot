# SPEC-01_HYBRID_FUEL_GATEWAY

## Goal
Implement a unified LLM gateway that routes tasks between Local (vLLM/Ollama) and Frontier (API) models.

## 1. The Smart Router Logic
- The Abstraction: Create `warden/llm_gateway.py`.
- Provider Support: OpenAI, Anthropic, Ollama, and vLLM (OpenAI-compatible).
- Task Tiers (Default Configuration):
  - `TIER_SCAN`: (Llama-3-70B / DeepSeek) -> Routes to `VLLM_ENDPOINT` or `OLLAMA_ENDPOINT`.
  - `TIER_VERDICT`: (GPT-4o / Claude-3.5) -> Routes to `FRONTIER_API_KEY`.
- Reference Implementation: AI Dev should refer to the local app provided by the user to copy the routing/fallback logic.

## 2. Reasoning Trace Format
Every call must return a `ReasoningTrace` object:

```json
{
  "model_used": "vllm/llama-3-70b",
  "task_tier": "TIER_SCAN",
  "reasoning_steps": ["Mapped dataflow for src.app", "Identified 3 subprocess calls"],
  "confidence_score": 0.92,
  "raw_response_path": "/forge_output/traces/<id>.txt"
}
```
