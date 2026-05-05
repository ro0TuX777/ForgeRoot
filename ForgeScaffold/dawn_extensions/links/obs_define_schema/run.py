import json
from pathlib import Path
from typing import Any, Dict


def register_schema(schema_name: str, schema_path: Path) -> None:
    try:
        from dawn.runtime import schemas as runtime_schemas
    except ImportError:
        return

    if schema_name in runtime_schemas.SCHEMA_REGISTRY:
        return

    if not schema_path.exists():
        return

    with schema_path.open("r") as fh:
        schema_data = json.load(fh)

    runtime_schemas.SCHEMA_REGISTRY[schema_name] = schema_data


def build_recommendations() -> str:
    return """# ForgeScaffold Observability Recommendations (Phase 2)

These recommendations align the Phase 2 log envelope with common stacks while keeping payloads safe-by-default.

## Python (stdlib logging or structlog)

- Prefer structured JSON logs with the log envelope fields.
- If using stdlib logging, attach a JSON formatter that enforces `schema_version`, `run_id`, `unit_id`, `operation`, and `result`.
- If using structlog, add a processor chain that normalizes fields and emits `timestamp` in RFC3339 format.

## Node / TypeScript (pino / winston)

- Use pino or winston JSON logger with a top-level formatter mapping the envelope fields.
- Ensure `trace_id` and `span_id` are propagated from incoming requests or worker context.
- Keep input/output payloads hashed (`sha256:<hex>`) rather than raw values.

## Distributed Tracing (OpenTelemetry)

- The envelope `trace_id`, `span_id`, and `parent_span_id` are OpenTelemetry-compatible.
- Use OTEL SDKs to bind logs and spans. Emit `trace_id`/`span_id` into logs via context propagation.
- Keep sampling policies consistent across services; do not log raw prompts or secrets.

## Agent Execution

- Populate `agent.step_id`, `agent.tool_call_id`, and `agent.prompt_hash`.
- Keep retrieval references as IDs (`retrieval_ids`) only.
- Store full prompts or data in secure stores, not log envelopes.
"""


def run(project_context: Dict[str, Any], link_config: Dict[str, Any]) -> Dict[str, Any]:
    sandbox = project_context.get("sandbox")
    if not sandbox:
        raise RuntimeError("Sandbox missing in context")

    schema_path = Path(__file__).resolve().parents[2] / "schemas" / "log_envelope.schema.json"
    register_schema("forgescaffold.log_envelope", schema_path)

    with schema_path.open("r") as fh:
        schema_payload = json.load(fh)

    schema_artifact_path = sandbox.publish(
        "forgescaffold.log_envelope.schema.json",
        "log_envelope.schema.json",
        schema_payload,
        schema="json",
    )

    recommendations = build_recommendations()
    rec_path = sandbox.publish_text(
        "forgescaffold.observability_recommendations.md",
        "observability_recommendations.md",
        recommendations,
        schema="text",
    )

    return {
        "status": "SUCCEEDED",
        "outputs": {
            "forgescaffold.log_envelope.schema.json": {"path": schema_artifact_path},
            "forgescaffold.observability_recommendations.md": {"path": rec_path},
        },
        "metrics": {"recommendations_bytes": len(recommendations)},
    }
