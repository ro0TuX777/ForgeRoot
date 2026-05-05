#!/usr/bin/env bash
# scripts/setup_env.sh

FORGE_ROOT="${FORGE_ROOT:-/Users/vinsoncornejo/ForgedRoot}"
export FORGE_ROOT

# Unified PYTHONPATH so root/DAWN/Azul/ForgeAtlas/ForgeScaffold imports resolve.
export PYTHONPATH="$FORGE_ROOT:$FORGE_ROOT/DAWN:$FORGE_ROOT/Azul:$FORGE_ROOT/ForgeAtlas:$FORGE_ROOT/ForgeScaffold:$FORGE_ROOT/ForgeScaffold/forgeworks:$FORGE_ROOT/ForgeScaffold/forgegate:${PYTHONPATH:-}"

# Framework integration overrides
export DAWN_ROOT="$FORGE_ROOT/DAWN"
export FORGE_SCAFFOLD_ROOT="$FORGE_ROOT/ForgeScaffold"
export FORGE_SCAFFOLD_SYSTEM_CATALOG_PATH="$FORGE_ROOT/DAWN/dawn/links/forgescaffold.system_catalog/run.py"
export FORGE_ATLAS_RUN_PATH="$FORGE_ROOT/ForgeAtlas/action_discovery_service/run.py"
export FORGE_WORKS_SERVICE_WRAPPER_PATH="$FORGE_ROOT/ForgeScaffold/forgeworks/forgeworks/sam/service_wrapper.py"
export FORGE_HARBOR_DAEMON_PATH="$FORGE_ROOT/ForgeHarbor/daemon.py"
export FORGE_ATLAS_CATALOG_PATH="$FORGE_ROOT/action_catalogs"
export FORGEWORKS_ROOT="$FORGE_ROOT/ForgeScaffold/forgeworks"
export FORGE_TRACE_DIR="${FORGE_TRACE_DIR:-$FORGE_ROOT/forge_output/traces}"
export AZUL_DATA_DIR="${AZUL_DATA_DIR:-$FORGE_ROOT/azul_data}"
export FORGE_LOOP_ENABLED="${FORGE_LOOP_ENABLED:-true}"
export FORGE_WARDEN_AUTO_VERIFY="${FORGE_WARDEN_AUTO_VERIFY:-true}"
export FORGE_WARDEN_VERIFY_DOMAIN="${FORGE_WARDEN_VERIFY_DOMAIN:-system_operations}"
export FORGE_WARDEN_REMEDIATE_MAX_ATTEMPTS="${FORGE_WARDEN_REMEDIATE_MAX_ATTEMPTS:-3}"
export AZUL_FORGEWORKS_DEGRADED_FALLBACK="${AZUL_FORGEWORKS_DEGRADED_FALLBACK:-0}"
export AZUL_NO_DESTRUCTIVE_REMEDIATION_GUARD_ENABLED="${AZUL_NO_DESTRUCTIVE_REMEDIATION_GUARD_ENABLED:-true}"
export AZUL_CI_STATUS_POST_ENABLED="${AZUL_CI_STATUS_POST_ENABLED:-true}"
export AZUL_CI_STATUS_FAIL_CLOSED="${AZUL_CI_STATUS_FAIL_CLOSED:-true}"
export AZUL_AUDIT_SIGNING_KEY_ID="${AZUL_AUDIT_SIGNING_KEY_ID:-local-dev}"
export AZUL_AUDIT_SIGNING_KEY="${AZUL_AUDIT_SIGNING_KEY:-dev-insecure-key-change-me}"
export LLM_GATEWAY_TIMEOUT_SEC="${LLM_GATEWAY_TIMEOUT_SEC:-1200}"
export OLLAMA_WARMUP_MODEL="${OLLAMA_WARMUP_MODEL:-llama4:17b-scout-16e-instruct-q4_K_M}"
export OLLAMA_WARMUP_PROMPT="${OLLAMA_WARMUP_PROMPT:-warmup}"
export OLLAMA_WARMUP_TIMEOUT_SEC="${OLLAMA_WARMUP_TIMEOUT_SEC:-1200}"
export FORGE_OLLAMA_WARMUP_ON_START="${FORGE_OLLAMA_WARMUP_ON_START:-true}"
export FORGE_LOCAL_ONLY="${FORGE_LOCAL_ONLY:-true}"

# Smart Router defaults (Ollama-local first, Frontier strategic reserve).
export FRONTIER_PROVIDER="${FRONTIER_PROVIDER:-anthropic}"
export ANTHROPIC_MODEL="${ANTHROPIC_MODEL:-claude-3-5-sonnet-latest}"
export OLLAMA_SCAN_MODEL="${OLLAMA_SCAN_MODEL:-llama4:17b-scout-16e-instruct-q4_K_M}"
export OLLAMA_REASONING_MODEL="${OLLAMA_REASONING_MODEL:-hf.co/unsloth/DeepSeek-R1-Distill-Qwen-32B-GGUF:Q4_K_M}"
export OLLAMA_VERDICT_MODEL="${OLLAMA_VERDICT_MODEL:-hf.co/unsloth/Qwen3-Coder-Next-GGUF:UD-Q4_K_M}"
export OLLAMA_EMBEDDING_MODEL="${OLLAMA_EMBEDDING_MODEL:-nomic-embed-text:latest}"
export OLLAMA_OCR_MODEL="${OLLAMA_OCR_MODEL:-glm-ocr:latest}"
export OLLAMA_NUM_PREDICT="${OLLAMA_NUM_PREDICT:-64}"
export OLLAMA_NUM_CTX="${OLLAMA_NUM_CTX:-8192}"
export OLLAMA_WARMUP_NUM_PREDICT="${OLLAMA_WARMUP_NUM_PREDICT:-8}"
if [[ "${FORGE_LOCAL_ONLY}" == "true" ]]; then
  export LLM_SCAN_ORDER="${LLM_SCAN_ORDER:-ollama,vllm}"
  export LLM_REASONING_ORDER="${LLM_REASONING_ORDER:-ollama,vllm}"
  export LLM_VERDICT_ORDER="${LLM_VERDICT_ORDER:-ollama,vllm}"
  export LLM_EMBEDDING_ORDER="${LLM_EMBEDDING_ORDER:-ollama,vllm}"
  export LLM_OCR_ORDER="${LLM_OCR_ORDER:-ollama}"
else
  export LLM_SCAN_ORDER="${LLM_SCAN_ORDER:-ollama,frontier,vllm}"
  export LLM_REASONING_ORDER="${LLM_REASONING_ORDER:-ollama,frontier,vllm}"
  export LLM_VERDICT_ORDER="${LLM_VERDICT_ORDER:-ollama,frontier,vllm}"
  export LLM_EMBEDDING_ORDER="${LLM_EMBEDDING_ORDER:-ollama,vllm}"
  export LLM_OCR_ORDER="${LLM_OCR_ORDER:-ollama}"
fi

# Keep legacy var aligned to scan model for existing wrappers/components.
export OLLAMA_MODEL="${OLLAMA_MODEL:-$OLLAMA_SCAN_MODEL}"

# Prefer DAWN venv interpreter for consistent wrapper runtime.
if [[ -x "$FORGE_ROOT/DAWN/.venv/bin/python" ]]; then
  export FORGE_PYTHON="$FORGE_ROOT/DAWN/.venv/bin/python"
else
  export FORGE_PYTHON="${FORGE_PYTHON:-python3}"
fi

mkdir -p "$FORGE_ROOT/action_catalogs/stubs" "$FORGE_ROOT/action_catalogs/active" "$FORGE_ROOT/warden/state" "$FORGE_TRACE_DIR"

echo "Forge federation environment loaded."
