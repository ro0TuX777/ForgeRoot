"""Hybrid fuel LLM gateway with local/cloud routing and reasoning traces."""

from __future__ import annotations

import base64
import json
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional
from urllib import error, request


class GatewayError(RuntimeError):
    """Raised when all provider attempts fail."""


@dataclass(frozen=True)
class ReasoningTrace:
    """Trace metadata returned for every gateway request."""

    model_used: str
    task_tier: str
    reasoning_steps: list[str]
    confidence_score: float
    raw_response_path: str


@dataclass(frozen=True)
class GatewayResponse:
    """Model response plus audit trace."""

    text: str
    trace: ReasoningTrace
    provider_payload: Dict[str, Any]


@dataclass
class GatewayConfig:
    """Runtime config sourced from environment variables."""

    forge_root: Path
    trace_dir: Path
    timeout_sec: float = 25.0

    vllm_endpoint: str = "http://localhost:8000/v1"
    vllm_model: str = "meta-llama/Llama-3-70b-instruct"

    ollama_endpoint: str = "http://localhost:11434"
    ollama_scan_model: str = "llama4:17b-scout-16e-instruct-q4_K_M"
    ollama_reasoning_model: str = "hf.co/unsloth/DeepSeek-R1-Distill-Qwen-32B-GGUF:Q4_K_M"
    ollama_verdict_model: str = "hf.co/unsloth/Qwen3-Coder-Next-GGUF:UD-Q4_K_M"
    ollama_embedding_model: str = "nomic-embed-text:latest"
    ollama_ocr_model: str = "glm-ocr:latest"
    ollama_num_predict: int = 256
    ollama_num_ctx: int = 8192

    frontier_provider: str = "anthropic"
    frontier_api_key: str = ""

    openai_api_key: str = ""
    openai_model: str = "gpt-4o"

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-3-5-sonnet-latest"

    scan_fallback_order: list[str] = field(
        default_factory=lambda: ["ollama", "frontier", "vllm"]
    )
    reasoning_fallback_order: list[str] = field(
        default_factory=lambda: ["ollama", "frontier", "vllm"]
    )
    verdict_fallback_order: list[str] = field(
        default_factory=lambda: ["ollama", "frontier", "vllm"]
    )
    embedding_fallback_order: list[str] = field(default_factory=lambda: ["ollama", "vllm"])
    ocr_fallback_order: list[str] = field(default_factory=lambda: ["ollama"])

    @classmethod
    def from_env(cls) -> "GatewayConfig":
        forge_root = Path(os.environ.get("FORGE_ROOT", Path.cwd())).resolve()
        trace_dir = Path(
            os.environ.get("FORGE_TRACE_DIR", str(forge_root / "forge_output" / "traces"))
        ).resolve()
        trace_dir.mkdir(parents=True, exist_ok=True)

        frontier_provider = os.environ.get("FRONTIER_PROVIDER", "anthropic").strip().lower()
        local_legacy_order = os.environ.get("LLM_LOCAL_ORDER", "ollama,frontier,vllm")
        return cls(
            forge_root=forge_root,
            trace_dir=trace_dir,
            timeout_sec=float(os.environ.get("LLM_GATEWAY_TIMEOUT_SEC", "25")),
            vllm_endpoint=os.environ.get("VLLM_ENDPOINT", "http://localhost:8000/v1"),
            vllm_model=os.environ.get("VLLM_MODEL", "meta-llama/Llama-3-70b-instruct"),
            ollama_endpoint=os.environ.get("OLLAMA_ENDPOINT", "http://localhost:11434"),
            ollama_scan_model=os.environ.get(
                "OLLAMA_SCAN_MODEL",
                os.environ.get("OLLAMA_MODEL", "llama4:17b-scout-16e-instruct-q4_K_M"),
            ),
            ollama_reasoning_model=os.environ.get(
                "OLLAMA_REASONING_MODEL",
                "hf.co/unsloth/DeepSeek-R1-Distill-Qwen-32B-GGUF:Q4_K_M",
            ),
            ollama_verdict_model=os.environ.get(
                "OLLAMA_VERDICT_MODEL",
                "hf.co/unsloth/Qwen3-Coder-Next-GGUF:UD-Q4_K_M",
            ),
            ollama_embedding_model=os.environ.get(
                "OLLAMA_EMBEDDING_MODEL",
                "nomic-embed-text:latest",
            ),
            ollama_ocr_model=os.environ.get("OLLAMA_OCR_MODEL", "glm-ocr:latest"),
            ollama_num_predict=max(1, int(os.environ.get("OLLAMA_NUM_PREDICT", "256"))),
            ollama_num_ctx=max(1024, int(os.environ.get("OLLAMA_NUM_CTX", "8192"))),
            frontier_provider=frontier_provider,
            frontier_api_key=os.environ.get("FRONTIER_API_KEY", ""),
            openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
            openai_model=os.environ.get("OPENAI_MODEL", "gpt-4o"),
            anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
            anthropic_model=os.environ.get("ANTHROPIC_MODEL", "claude-3-5-sonnet-latest"),
            scan_fallback_order=[
                p.strip().lower()
                for p in os.environ.get("LLM_SCAN_ORDER", local_legacy_order).split(",")
                if p.strip()
            ],
            reasoning_fallback_order=[
                p.strip().lower()
                for p in os.environ.get("LLM_REASONING_ORDER", local_legacy_order).split(",")
                if p.strip()
            ],
            verdict_fallback_order=[
                p.strip().lower()
                for p in os.environ.get("LLM_VERDICT_ORDER", "ollama,frontier,vllm").split(",")
                if p.strip()
            ],
            embedding_fallback_order=[
                p.strip().lower()
                for p in os.environ.get("LLM_EMBEDDING_ORDER", "ollama,vllm").split(",")
                if p.strip()
            ],
            ocr_fallback_order=[
                p.strip().lower()
                for p in os.environ.get("LLM_OCR_ORDER", "ollama").split(",")
                if p.strip()
            ],
        )


# ---------------------------------------------------------------------------
# Intent classification — maps natural language task descriptions to tiers.
# Ordered from most specific to most general so the first strong match wins.
# ---------------------------------------------------------------------------
_INTENT_TIER_MAP: list[tuple[frozenset[str], str]] = [
    (
        frozenset({
            "embed", "embedding", "vector", "semantic", "similarity",
            "index", "nearest", "search",
        }),
        "TIER_EMBEDDING",
    ),
    (
        frozenset({
            "ocr", "image", "visual", "diagram", "screenshot",
            "photo", "extract", "vision",
        }),
        "TIER_OCR",
    ),
    (
        frozenset({
            "verdict", "govern", "decide", "decision", "approve", "reject",
            "deny", "allow", "gate", "judge", "judgment", "compliance",
            "policy", "adjudicate",
        }),
        "TIER_VERDICT",
    ),
    (
        frozenset({
            "reason", "reasoning", "analyze", "analysis", "explain",
            "deep", "complex", "review", "audit", "plan", "strategic",
            "remediat", "investigate", "evaluate", "architect",
        }),
        "TIER_REASONING",
    ),
    (
        frozenset({
            "scan", "detect", "check", "triage", "assess", "lint",
            "quick", "pattern", "risk", "flag", "classify",
        }),
        "TIER_SCAN",
    ),
]

_DEFAULT_INTENT_TIER = "TIER_SCAN"


class LLMGateway:
    """Routes requests by task tier with deterministic fallback ordering."""

    def __init__(self, config: Optional[GatewayConfig] = None):
        self.config = config or GatewayConfig.from_env()

    def health(self) -> Dict[str, Dict[str, str]]:
        """Return lightweight provider health for cockpit ignition checks."""
        return {
            "vllm": self._check_vllm(),
            "ollama": self._check_ollama(),
            "frontier": self._check_frontier(),
        }

    def complete(
        self,
        *,
        task_tier: str,
        prompt: str,
        system_prompt: str = "",
        reasoning_steps: Optional[list[str]] = None,
        confidence_score: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> GatewayResponse:
        """Generate text with model routing by tier."""
        task_tier = task_tier.strip().upper()
        provider_order = self._provider_order(task_tier)
        ollama_model = self._ollama_model_for_tier(task_tier)
        errors: list[str] = []

        for provider in provider_order:
            try:
                if provider == "vllm":
                    payload = self._call_openai_compatible(
                        endpoint=self.config.vllm_endpoint,
                        api_key="",
                        model=self.config.vllm_model,
                        prompt=prompt,
                        system_prompt=system_prompt,
                    )
                    model_used = f"vllm/{self.config.vllm_model}"
                elif provider == "ollama":
                    payload = self._call_ollama(
                        endpoint=self.config.ollama_endpoint,
                        model=ollama_model,
                        prompt=prompt,
                        system_prompt=system_prompt,
                    )
                    actual_model = (
                        (payload.get("_meta") or {}).get("model_used")
                        or ollama_model
                    )
                    model_used = f"ollama/{actual_model}"
                elif provider == "frontier":
                    payload, model_used = self._call_frontier(
                        prompt=prompt,
                        system_prompt=system_prompt,
                    )
                else:
                    raise GatewayError(f"Unsupported provider '{provider}'")

                text = self._extract_text(provider=provider, payload=payload)
                trace_path = self._write_raw_trace(
                    provider=provider,
                    task_tier=task_tier,
                    payload=payload,
                    metadata=metadata or {},
                )
                trace = ReasoningTrace(
                    model_used=model_used,
                    task_tier=task_tier,
                    reasoning_steps=self._build_reasoning_steps(
                        task_tier=task_tier,
                        provider=provider,
                        custom_steps=reasoning_steps or [],
                    ),
                    confidence_score=confidence_score
                    if confidence_score is not None
                    else (0.9 if provider == "frontier" else 0.76),
                    raw_response_path=str(trace_path),
                )
                return GatewayResponse(text=text, trace=trace, provider_payload=payload)
            except Exception as exc:  # intentionally broad for fallback behavior
                errors.append(f"{provider}: {exc}")

        raise GatewayError(
            f"All providers failed for {task_tier}. Attempts: " + " | ".join(errors)
        )

    @staticmethod
    def classify_intent(intent: str) -> str:
        """Map a natural language intent description to the best task tier.

        Allows callers to describe what they need without coupling to
        ForgedRoot's internal tier naming scheme.  Falls back to
        ``TIER_SCAN`` when no keywords match.

        Examples::

            classify_intent("deep reasoning about a governance decision")
            # → "TIER_REASONING"

            classify_intent("embed these code snippets for semantic search")
            # → "TIER_EMBEDDING"

            classify_intent("quick risk scan of changed files")
            # → "TIER_SCAN"
        """
        tokens = frozenset(re.sub(r"[^a-z0-9 ]", " ", intent.lower()).split())
        best_tier = _DEFAULT_INTENT_TIER
        best_score = 0
        for keywords, tier in _INTENT_TIER_MAP:
            score = len(tokens & keywords)
            if score > best_score:
                best_score = score
                best_tier = tier
        return best_tier

    def complete_by_intent(
        self,
        *,
        intent: str,
        prompt: str,
        system_prompt: str = "",
        reasoning_steps: Optional[list[str]] = None,
        confidence_score: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> GatewayResponse:
        """Generate text routed by intent description rather than explicit tier.

        Callers describe what they need in plain language and the gateway
        classifies the intent to the appropriate tier automatically.  This is
        the preferred entry point for external systems or new components that
        should not be coupled to ForgedRoot's tier naming scheme.

        The resolved tier and original intent string are injected into the
        returned ``ReasoningTrace`` for auditability.
        """
        task_tier = self.classify_intent(intent)
        enriched_metadata: Dict[str, Any] = dict(metadata or {})
        enriched_metadata["intent"] = intent
        enriched_metadata["classified_tier"] = task_tier
        return self.complete(
            task_tier=task_tier,
            prompt=prompt,
            system_prompt=system_prompt,
            reasoning_steps=reasoning_steps,
            confidence_score=confidence_score,
            metadata=enriched_metadata,
        )

    def embed_texts(
        self,
        texts: list[str],
        *,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Generate embeddings for ForgeAtlas indexing via configured providers."""
        if not texts:
            raise GatewayError("embed_texts requires at least one input string")
        errors: list[str] = []
        model = self._ollama_model_for_tier("TIER_EMBEDDING")

        for provider in self._provider_order("TIER_EMBEDDING"):
            try:
                if provider == "ollama":
                    payload = self._call_ollama_embed(
                        endpoint=self.config.ollama_endpoint,
                        model=model,
                        texts=texts,
                    )
                    model_used = f"ollama/{model}"
                elif provider == "vllm":
                    payload = self._call_openai_compatible_embeddings(
                        endpoint=self.config.vllm_endpoint,
                        api_key="",
                        model=self.config.vllm_model,
                        texts=texts,
                    )
                    model_used = f"vllm/{self.config.vllm_model}"
                elif provider == "frontier":
                    payload = self._call_frontier_embeddings(texts=texts)
                    if self.config.frontier_provider == "openai":
                        model_used = f"openai/{self.config.openai_model}"
                    else:
                        model_used = f"{self.config.frontier_provider}/unsupported"
                else:
                    raise GatewayError(f"Unsupported provider '{provider}' for embeddings")

                embeddings = self._extract_embeddings(payload)
                trace_path = self._write_raw_trace(
                    provider=provider,
                    task_tier="TIER_EMBEDDING",
                    payload=payload,
                    metadata=metadata or {},
                )
                return {
                    "embeddings": embeddings,
                    "model_used": model_used,
                    "raw_response_path": str(trace_path),
                }
            except Exception as exc:  # intentionally broad for fallback behavior
                errors.append(f"{provider}: {exc}")

        raise GatewayError(
            "All providers failed for TIER_EMBEDDING. Attempts: " + " | ".join(errors)
        )

    def ocr_image(
        self,
        *,
        image_bytes: bytes,
        prompt: str,
        system_prompt: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> GatewayResponse:
        """Extract architecture diagram text/structure using the OCR tier model."""
        if not image_bytes:
            raise GatewayError("ocr_image requires non-empty image bytes")

        task_tier = "TIER_OCR"
        provider_order = self._provider_order(task_tier)
        model = self._ollama_model_for_tier(task_tier)
        errors: list[str] = []

        for provider in provider_order:
            try:
                if provider != "ollama":
                    raise GatewayError("OCR is currently supported through Ollama models only")
                payload = self._call_ollama_ocr(
                    endpoint=self.config.ollama_endpoint,
                    model=model,
                    image_bytes=image_bytes,
                    prompt=prompt,
                    system_prompt=system_prompt,
                )
                model_used = f"ollama/{model}"
                text = self._extract_text(provider=provider, payload=payload)
                trace_path = self._write_raw_trace(
                    provider=provider,
                    task_tier=task_tier,
                    payload=payload,
                    metadata=metadata or {},
                )
                trace = ReasoningTrace(
                    model_used=model_used,
                    task_tier=task_tier,
                    reasoning_steps=self._build_reasoning_steps(
                        task_tier=task_tier,
                        provider=provider,
                        custom_steps=["Extracted OCR text from uploaded architecture image"],
                    ),
                    confidence_score=0.72,
                    raw_response_path=str(trace_path),
                )
                return GatewayResponse(text=text, trace=trace, provider_payload=payload)
            except Exception as exc:  # intentionally broad for fallback behavior
                errors.append(f"{provider}: {exc}")

        raise GatewayError(f"All providers failed for {task_tier}. Attempts: " + " | ".join(errors))

    def _provider_order(self, task_tier: str) -> list[str]:
        if task_tier == "TIER_SCAN":
            return self._dedupe(self.config.scan_fallback_order)
        if task_tier == "TIER_REASONING":
            return self._dedupe(self.config.reasoning_fallback_order)
        if task_tier == "TIER_VERDICT":
            return self._dedupe(self.config.verdict_fallback_order)
        if task_tier == "TIER_EMBEDDING":
            return self._dedupe(self.config.embedding_fallback_order)
        if task_tier == "TIER_OCR":
            return self._dedupe(self.config.ocr_fallback_order)
        return self._dedupe(self.config.scan_fallback_order)

    def _ollama_model_for_tier(self, task_tier: str) -> str:
        if task_tier == "TIER_SCAN":
            return self.config.ollama_scan_model
        if task_tier == "TIER_REASONING":
            return self.config.ollama_reasoning_model
        if task_tier == "TIER_VERDICT":
            return self.config.ollama_verdict_model
        if task_tier == "TIER_EMBEDDING":
            return self.config.ollama_embedding_model
        if task_tier == "TIER_OCR":
            return self.config.ollama_ocr_model
        return self.config.ollama_scan_model

    @staticmethod
    def _dedupe(items: list[str]) -> list[str]:
        out: list[str] = []
        for item in items:
            if item not in out:
                out.append(item)
        return out

    def _call_frontier(
        self,
        *,
        prompt: str,
        system_prompt: str,
    ) -> tuple[Dict[str, Any], str]:
        provider = self.config.frontier_provider
        if provider == "anthropic":
            payload = self._call_anthropic(prompt=prompt, system_prompt=system_prompt)
            return payload, f"anthropic/{self.config.anthropic_model}"

        payload = self._call_openai_compatible(
            endpoint="https://api.openai.com/v1",
            api_key=self.config.frontier_api_key or self.config.openai_api_key,
            model=self.config.openai_model,
            prompt=prompt,
            system_prompt=system_prompt,
        )
        return payload, f"openai/{self.config.openai_model}"

    def _call_openai_compatible(
        self,
        *,
        endpoint: str,
        api_key: str,
        model: str,
        prompt: str,
        system_prompt: str,
    ) -> Dict[str, Any]:
        base = endpoint.rstrip("/")
        if not base.endswith("/v1"):
            base = f"{base}/v1"
        url = f"{base}/chat/completions"
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0.2,
        }
        return self._request_json("POST", url, headers, payload)

    def _call_anthropic(self, *, prompt: str, system_prompt: str) -> Dict[str, Any]:
        api_key = self.config.frontier_api_key or self.config.anthropic_api_key
        if not api_key:
            raise GatewayError("Missing anthropic api key")
        payload = {
            "model": self.config.anthropic_model,
            "max_tokens": 1200,
            "temperature": 0.2,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system_prompt:
            payload["system"] = system_prompt
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        return self._request_json(
            "POST",
            "https://api.anthropic.com/v1/messages",
            headers,
            payload,
        )

    def _call_ollama(
        self,
        *,
        endpoint: str,
        model: str,
        prompt: str,
        system_prompt: str,
    ) -> Dict[str, Any]:
        full_prompt = prompt if not system_prompt else f"{system_prompt}\n\n{prompt}"
        req_payload = {
            "model": model,
            "prompt": full_prompt,
            "stream": False,
            "options": {
                "temperature": 0.2,
                "num_predict": self.config.ollama_num_predict,
                "num_ctx": self.config.ollama_num_ctx,
            },
        }
        url = f"{endpoint.rstrip('/')}/api/generate"
        try:
            response = self._request_json(
                "POST",
                url,
                {"Content-Type": "application/json"},
                req_payload,
            )
            response["_meta"] = {"model_used": model}
            return response
        except GatewayError as exc:
            # Common local-dev scenario: configured model missing. Fall back to an
            # installed non-embedding model so the cockpit can still operate.
            if "not found" not in str(exc).lower():
                raise
            fallback_model = self._select_ollama_fallback_model(
                endpoint=endpoint,
                blocked_substrings=("embed", "ocr"),
            )
            if not fallback_model or fallback_model == model:
                raise
            req_payload["model"] = fallback_model
            response = self._request_json(
                "POST",
                url,
                {"Content-Type": "application/json"},
                req_payload,
            )
            response["_meta"] = {"model_used": fallback_model}
            return response

    def _call_ollama_embed(
        self,
        *,
        endpoint: str,
        model: str,
        texts: list[str],
    ) -> Dict[str, Any]:
        url = f"{endpoint.rstrip('/')}/api/embed"
        req_payload = {
            "model": model,
            "input": texts,
        }
        try:
            response = self._request_json(
                "POST",
                url,
                {"Content-Type": "application/json"},
                req_payload,
            )
            response["_meta"] = {"model_used": model}
            return response
        except GatewayError as exc:
            # Older Ollama versions used /api/embeddings and single-prompt payload.
            if "404" not in str(exc):
                raise
            fallback_text = texts[0] if texts else ""
            old_payload = {
                "model": model,
                "prompt": fallback_text,
            }
            response = self._request_json(
                "POST",
                f"{endpoint.rstrip('/')}/api/embeddings",
                {"Content-Type": "application/json"},
                old_payload,
            )
            if "embedding" in response:
                response = {"embeddings": [response["embedding"]]}
            response["_meta"] = {"model_used": model}
            return response

    def _call_ollama_ocr(
        self,
        *,
        endpoint: str,
        model: str,
        image_bytes: bytes,
        prompt: str,
        system_prompt: str,
    ) -> Dict[str, Any]:
        full_prompt = prompt if not system_prompt else f"{system_prompt}\n\n{prompt}"
        image_b64 = base64.b64encode(image_bytes).decode("ascii")
        req_payload = {
            "model": model,
            "prompt": full_prompt,
            "images": [image_b64],
            "stream": False,
            "options": {
                "temperature": 0.1,
                "num_predict": self.config.ollama_num_predict,
                "num_ctx": self.config.ollama_num_ctx,
            },
        }
        url = f"{endpoint.rstrip('/')}/api/generate"
        response = self._request_json(
            "POST",
            url,
            {"Content-Type": "application/json"},
            req_payload,
        )
        response["_meta"] = {"model_used": model}
        return response

    def _call_openai_compatible_embeddings(
        self,
        *,
        endpoint: str,
        api_key: str,
        model: str,
        texts: list[str],
    ) -> Dict[str, Any]:
        base = endpoint.rstrip("/")
        if not base.endswith("/v1"):
            base = f"{base}/v1"
        url = f"{base}/embeddings"
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        payload = {"model": model, "input": texts}
        return self._request_json("POST", url, headers, payload)

    def _call_frontier_embeddings(self, *, texts: list[str]) -> Dict[str, Any]:
        if self.config.frontier_provider != "openai":
            raise GatewayError("Frontier embeddings currently require FRONTIER_PROVIDER=openai")
        return self._call_openai_compatible_embeddings(
            endpoint="https://api.openai.com/v1",
            api_key=self.config.frontier_api_key or self.config.openai_api_key,
            model=self.config.openai_model,
            texts=texts,
        )

    def _extract_embeddings(self, payload: Dict[str, Any]) -> list[list[float]]:
        if "embeddings" in payload and isinstance(payload["embeddings"], list):
            return [
                [float(value) for value in embedding]
                for embedding in payload["embeddings"]
                if isinstance(embedding, list)
            ]

        data = payload.get("data")
        if isinstance(data, list):
            out: list[list[float]] = []
            for item in data:
                if isinstance(item, dict) and isinstance(item.get("embedding"), list):
                    out.append([float(value) for value in item["embedding"]])
            if out:
                return out
        raise GatewayError("Embedding payload did not include vectors")

    def _select_ollama_fallback_model(
        self,
        *,
        endpoint: str,
        blocked_substrings: tuple[str, ...] = ("embed",),
    ) -> str:
        tags = self._request_json(
            "GET",
            f"{endpoint.rstrip('/')}/api/tags",
            {},
            None,
        )
        models = tags.get("models") or []
        names: list[str] = []
        for item in models:
            if isinstance(item, dict):
                name = str(item.get("name") or item.get("model") or "").strip()
                if name:
                    names.append(name)

        # Prefer chat/code-capable models over purpose-specific endpoints.
        for name in names:
            lowered = name.lower()
            if any(blocked in lowered for blocked in blocked_substrings):
                continue
            return name
        return names[0] if names else ""

    def _request_json(
        self,
        method: str,
        url: str,
        headers: Dict[str, str],
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        req = request.Request(url=url, method=method, data=body, headers=headers)
        try:
            with request.urlopen(req, timeout=self.config.timeout_sec) as resp:
                raw = resp.read().decode("utf-8")
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise GatewayError(f"HTTP {exc.code} for {url}: {detail}") from exc
        except OSError as exc:
            raise GatewayError(f"Network error for {url}: {exc}") from exc

        try:
            return json.loads(raw) if raw else {}
        except json.JSONDecodeError as exc:
            raise GatewayError(f"Invalid JSON from {url}: {raw[:220]}") from exc

    def _extract_text(self, *, provider: str, payload: Dict[str, Any]) -> str:
        if provider == "ollama":
            return str(payload.get("response", "")).strip()
        if provider == "frontier" and self.config.frontier_provider == "anthropic":
            content = payload.get("content") or []
            if content and isinstance(content[0], dict):
                return str(content[0].get("text", "")).strip()
            return ""
        choices = payload.get("choices") or []
        if choices and isinstance(choices[0], dict):
            msg = choices[0].get("message") or {}
            content = msg.get("content", "")
            if isinstance(content, list):
                return "".join(
                    part.get("text", "") for part in content if isinstance(part, dict)
                ).strip()
            return str(content).strip()
        return ""

    def _write_raw_trace(
        self,
        *,
        provider: str,
        task_tier: str,
        payload: Dict[str, Any],
        metadata: Dict[str, Any],
    ) -> Path:
        trace_id = f"{int(time.time())}-{uuid.uuid4().hex[:12]}"
        path = self.config.trace_dir / f"{trace_id}.txt"
        content = {
            "provider": provider,
            "task_tier": task_tier,
            "metadata": metadata,
            "payload": payload,
        }
        path.write_text(json.dumps(content, indent=2), encoding="utf-8")
        return path

    def _build_reasoning_steps(
        self,
        *,
        task_tier: str,
        provider: str,
        custom_steps: list[str],
    ) -> list[str]:
        steps = [
            f"Task tier resolved: {task_tier}",
            f"Provider selected by router: {provider}",
        ]
        steps.extend(custom_steps)
        return steps

    def _check_vllm(self) -> Dict[str, str]:
        try:
            base = self.config.vllm_endpoint.rstrip("/")
            if not base.endswith("/v1"):
                base = f"{base}/v1"
            self._request_json("GET", f"{base}/models", {}, None)
            return {"status": "running", "detail": "vLLM endpoint reachable"}
        except Exception as exc:
            return {"status": "stopped", "detail": str(exc)}

    def _check_ollama(self) -> Dict[str, str]:
        try:
            self._request_json(
                "GET",
                f"{self.config.ollama_endpoint.rstrip('/')}/api/tags",
                {},
                None,
            )
            return {"status": "running", "detail": "Ollama endpoint reachable"}
        except Exception as exc:
            return {"status": "stopped", "detail": str(exc)}

    def _check_frontier(self) -> Dict[str, str]:
        provider = self.config.frontier_provider
        if provider == "anthropic":
            key_present = bool(self.config.frontier_api_key or self.config.anthropic_api_key)
            return {
                "status": "configured" if key_present else "stopped",
                "detail": "Anthropic key present" if key_present else "Missing Anthropic key",
            }
        key_present = bool(self.config.frontier_api_key or self.config.openai_api_key)
        return {
            "status": "configured" if key_present else "stopped",
            "detail": "OpenAI key present" if key_present else "Missing OpenAI key",
        }
