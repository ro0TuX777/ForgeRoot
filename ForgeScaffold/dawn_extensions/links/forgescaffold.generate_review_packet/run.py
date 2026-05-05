import difflib
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, List

import yaml


def _load_artifact(artifact_store, artifact_id: str) -> Dict[str, Any]:
    meta = artifact_store.get(artifact_id)
    if not meta:
        raise RuntimeError(f"Missing required artifact: {artifact_id}")
    with open(meta["path"], "r") as fh:
        return json.load(fh)


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _load_policy(project_root: Path) -> Dict[str, Any]:
    repo_root = Path(__file__).resolve().parents[3]
    policy_path = repo_root / "dawn" / "policy" / "runtime_policy.yaml"
    if not policy_path.exists():
        policy_path = project_root / "policy" / "runtime_policy.yaml"
    if not policy_path.exists():
        return {}
    return yaml.safe_load(policy_path.read_text()) or {}


def _risk_for_path(path: str, op: str, hunk_count: int, rules: Dict[str, Any]) -> str:
    sensitive_prefixes = rules.get("sensitive_path_prefixes", [])
    high_risk_ops = set(rules.get("high_risk_ops", []))
    high_risk_patterns = rules.get("high_risk_path_match", [])

    if any(path.startswith(prefix) for prefix in sensitive_prefixes):
        return "high"
    if any(re.search(pattern, path) for pattern in high_risk_patterns):
        return "high"
    if op in high_risk_ops:
        return "high"
    if path.startswith("src/"):
        return "medium" if hunk_count <= 5 else "high"
    if path.startswith("tests/") or path.startswith("observability/"):
        return "low"
    return "medium"


def _overall_risk(ops: List[Dict[str, Any]]) -> str:
    order = {"low": 0, "medium": 1, "high": 2}
    highest = "low"
    for op in ops:
        risk = op.get("risk", "low")
        if order.get(risk, 0) > order.get(highest, 0):
            highest = risk
    return highest


def _required_signatures(overall_risk: str, policy: Dict[str, Any]) -> int:
    defaults = {"low": 1, "medium": 1, "high": 2}
    rules = policy.get("forgescaffold", {}).get("min_signatures_by_risk", {})
    merged = {**defaults, **(rules or {})}
    return int(merged.get(overall_risk, 1))


def _diff_preview(path: Path, content: str) -> str:
    try:
        before = path.read_text().splitlines(keepends=True)
    except Exception:
        before = []
    after = content.splitlines(keepends=True)
    return "".join(difflib.unified_diff(before, after, fromfile=str(path), tofile=str(path)))


def run(project_context: Dict[str, Any], link_config: Dict[str, Any]) -> Dict[str, Any]:
    artifact_store = project_context.get("artifact_store")
    sandbox = project_context.get("sandbox")
    project_root = Path(project_context["project_root"])
    if not artifact_store or not sandbox:
        raise RuntimeError("Sandbox or artifact store missing")

    patchset = _load_artifact(artifact_store, "forgescaffold.instrumentation.patchset.json")
    system_catalog = artifact_store.get("forgescaffold.system_catalog.json")
    dataflow_map = artifact_store.get("forgescaffold.dataflow_map.json")
    apply_report = artifact_store.get("forgescaffold.apply_report.json")

    policy = _load_policy(project_root)
    risk_rules = policy.get("forgescaffold", {}).get("risk_rules", {})

    operations = patchset.get("operations", [])
    op_summaries = []
    diff_previews = []

    for op in operations:
        op_type = op.get("op")
        path = op.get("path", "")
        hunks = op.get("patch") or []
        hunk_summary = [
            {
                "anchor_type": hunk.get("anchor", {}).get("type"),
                "action": hunk.get("action"),
            }
            for hunk in hunks
        ]
        risk = _risk_for_path(path, op_type, len(hunks), risk_rules)

        summary = {
            "path": path,
            "op": op_type,
            "hunks": hunk_summary,
            "risk": risk,
        }
        op_summaries.append(summary)

        if op_type in {"add", "modify"} and op.get("content"):
            preview = _diff_preview(project_root / path, op["content"])
            if preview:
                diff_previews.append({"path": path, "diff": preview})

    overall_risk = _overall_risk(op_summaries)
    required_signatures = _required_signatures(overall_risk, policy)

    md_lines = [
        "# ForgeScaffold Review Packet",
        "",
        f"Patchset ID: {patchset.get('patchset_id')}",
        f"Bundle Content SHA256: {patchset.get('target', {}).get('bundle_content_sha256')}",
        f"Overall Risk: {overall_risk}",
        f"Required Signatures: {required_signatures}",
        "",
        "## Operations",
    ]

    for summary in op_summaries:
        md_lines.append(f"- {summary['op']} {summary['path']} (risk: {summary['risk']})")
        for hunk in summary.get("hunks", []):
            md_lines.append(f"  - hunk: {hunk.get('anchor_type')} / {hunk.get('action')}")

    if diff_previews:
        md_lines.append("\n## Diff Previews")
        for preview in diff_previews:
            md_lines.append(f"\n### {preview['path']}")
            md_lines.append("```")
            md_lines.append(preview["diff"])
            md_lines.append("```")

    md_text = "\n".join(md_lines)
    review_sha = _sha256_text(md_text)

    review_json = {
        "schema_version": "1.0.0",
        "patchset_id": patchset.get("patchset_id"),
        "bundle_content_sha256": patchset.get("target", {}).get("bundle_content_sha256"),
        "operations": op_summaries,
        "overall_risk": overall_risk,
        "required_signatures": required_signatures,
        "review_packet_sha256": review_sha,
        "system_catalog_path": system_catalog["path"] if system_catalog else None,
        "dataflow_map_path": dataflow_map["path"] if dataflow_map else None,
        "apply_report_path": apply_report["path"] if apply_report else None,
    }

    md_path = sandbox.write_text("review_packet.md", md_text)
    json_path = sandbox.publish("forgescaffold.review_packet.json", "review_packet.json", review_json, schema="json")

    return {
        "status": "SUCCEEDED",
        "outputs": {
            "forgescaffold.review_packet.md": {"path": md_path},
            "forgescaffold.review_packet.json": {"path": json_path},
        },
        "metrics": {"operations": len(op_summaries)},
    }
