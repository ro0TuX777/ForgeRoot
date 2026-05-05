import os
import subprocess
from typing import Any, Dict, Iterable, List, Optional

import requests

from ..core_engines.config.model_config_manager import ModelConfigManager


class PreflightError(Exception):
    pass


def _as_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str):
        return [v.strip() for v in value.split(",") if v.strip()]
    return []


def _docker_running_containers() -> List[str]:
    result = subprocess.run(
        ["docker", "ps", "--format", "{{.Names}}"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise PreflightError("docker ps failed; ensure Docker is running")
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _ollama_tags(api_url: str) -> List[str]:
    resp = requests.get(f"{api_url}/api/tags", timeout=5)
    if resp.status_code != 200:
        raise PreflightError(f"ollama not responding at {api_url} (status {resp.status_code})")
    payload = resp.json()
    return [m.get("name") for m in payload.get("models", []) if m.get("name")]


def _ollama_ping(api_url: str, model: str, timeout: int = 10) -> None:
    try:
        resp = requests.post(
            f"{api_url}/api/generate",
            json={"model": model, "prompt": "ping", "stream": False},
            timeout=timeout,
        )
    except requests.Timeout as exc:
        raise PreflightError(
            f"ollama generate timed out for model '{model}' (>{timeout}s)"
        ) from exc
    if resp.status_code != 200:
        raise PreflightError(
            f"ollama generate failed for model '{model}' (status {resp.status_code})"
        )


def run_preflight(run_config: Dict[str, Any]) -> None:
    preflight = run_config.get("preflight", {}) if isinstance(run_config, dict) else {}

    # Docker container checks (only if configured)
    containers = _as_list(preflight.get("docker_containers") or os.getenv("FORGEWORKS_DOCKER_CONTAINERS"))
    if containers:
        running = set(_docker_running_containers())
        missing = [name for name in containers if name not in running]
        if missing:
            raise PreflightError(f"missing required docker containers: {', '.join(missing)}")

    # Ollama checks (enabled by default for non-stub runs)
    check_ollama = preflight.get("check_ollama", True)
    if check_ollama:
        config = ModelConfigManager().load_config()
        api_url = config.get("api_url", "http://localhost:11434")
        tags = _ollama_tags(api_url)

        required_models = _as_list(preflight.get("ollama_models"))
        if not required_models:
            required_models = [
                m for m in [
                    config.get("reasoning_model"),
                    config.get("code_model"),
                    config.get("general_model"),
                ]
                if m
            ]

        missing_models = [m for m in required_models if m not in tags]
        if missing_models:
            raise PreflightError(f"missing required Ollama models: {', '.join(missing_models)}")

        if preflight.get("check_generate", True):
            ping_model = preflight.get("ping_model") or config.get("reasoning_model")
            if ping_model:
                _ollama_ping(api_url, ping_model, timeout=int(preflight.get("generate_timeout_seconds", 10)))
