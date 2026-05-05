"""
Merge Graphify semantic chunks from Cursor subagent .jsonl transcripts + AST,
then write .graphify_semantic.json and .graphify_extract.json (CONCORD root).

Usage (from CONCORD directory):
  python tools/merge_graphify_semantic_from_subagents.py
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRANSCRIPT_ROOT = Path(r"C:\Users\vin\.cursor\projects\f-ForgedRoot\agent-transcripts")
# Subagent UUIDs from this CONCORD semantic run (resolved newest transcript per id).
SUBAGENT_IDS = [
    "fbf2d0bd-9d19-47cc-b850-3cc69023bb56",
    "0a150e32-d2e1-42ed-ba73-f106e2414004",
    "b084d7a9-dfb2-49ec-b0d6-92e0aff32f4e",
    "fde48b3c-5c40-4388-801f-12009a960632",
]


def _resolve_subagent_jsonl(agent_id: str) -> Path:
    matches = list(TRANSCRIPT_ROOT.rglob(f"{agent_id}.jsonl"))
    if not matches:
        raise SystemExit(f"No transcript found for subagent {agent_id} under {TRANSCRIPT_ROOT}")
    return max(matches, key=lambda p: p.stat().st_mtime)


CHUNK_JSONL = [_resolve_subagent_jsonl(aid) for aid in SUBAGENT_IDS]


def _iter_assistant_texts(jsonl_path: Path) -> list[str]:
    texts: list[str] = []
    raw = jsonl_path.read_text(encoding="utf-8", errors="replace")
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("role") != "assistant":
            continue
        msg = row.get("message") or {}
        for block in msg.get("content") or []:
            if isinstance(block, dict) and block.get("type") == "text":
                t = block.get("text") or ""
                if t:
                    texts.append(t)
    return texts


def _extract_json_object(text: str) -> dict | None:
    """Pull first top-level {...} that looks like a graph fragment."""
    if '{"nodes"' in text:
        start = text.index('{"nodes"')
    elif text.strip().startswith("{"):
        start = text.index("{")
    else:
        return None
    depth = 0
    for i, c in enumerate(text[start:], start=start):
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                blob = text[start : i + 1]
                try:
                    return json.loads(blob)
                except json.JSONDecodeError:
                    return None
    return None


def _load_chunk_from_jsonl(path: Path) -> dict:
    texts = _iter_assistant_texts(path)
    for t in reversed(texts):
        frag = _extract_json_object(t)
        if frag and isinstance(frag.get("nodes"), list):
            return frag
    raise SystemExit(f"No graph JSON found in {path}")


def _norm_pdf_chunk(frag: dict) -> dict:
    """Chunk D: PDF subgraph uses non-Graphify edge schema."""
    nodes_out = []
    node_ids: set[str] = set()
    for n in frag.get("nodes", []):
        nid = n.get("id")
        if not nid:
            continue
        label = n.get("label") or nid
        ft = n.get("file_type") or "paper"
        if ft not in ("code", "document", "paper", "image", "rationale", "concept"):
            ft = "paper"
        src = n.get("source_file") or "CONCORD_v0_3_Core_Specification.pdf"
        nodes_out.append(
            {
                "id": nid,
                "label": label,
                "file_type": ft,
                "source_file": src,
                "source_location": None,
                "source_url": None,
                "captured_at": None,
                "author": None,
                "contributor": None,
            }
        )
        node_ids.add(nid)

    edges_out = []
    for e in frag.get("edges", []):
        s, t = e.get("source"), e.get("target")
        if s not in node_ids or t not in node_ids:
            continue
        rel = e.get("relation") or "conceptually_related_to"
        inf = (e.get("inference") or "").upper()
        raw_conf = e.get("confidence")
        if raw_conf in ("EXTRACTED", "INFERRED", "AMBIGUOUS"):
            conf = raw_conf
        elif inf == "STATED" or raw_conf == 1.0:
            conf = "EXTRACTED"
        else:
            conf = "INFERRED"
        cs = float(e.get("confidence_score", 0.85 if inf == "INFERRED" else 1.0))
        src_f = (
            frag.get("nodes", [{}])[0].get("source_file")
            if frag.get("nodes")
            else "CONCORD_v0_3_Core_Specification.pdf"
        )
        edges_out.append(
            {
                "source": s,
                "target": t,
                "relation": rel,
                "confidence": conf,
                "confidence_score": cs,
                "source_file": src_f,
                "source_location": None,
                "weight": 1.0,
            }
        )

    hyper_out = []
    for h in frag.get("hyperedges", []):
        members = h.get("nodes") or h.get("member_node_ids") or []
        if not members:
            continue
        hyper_out.append(
            {
                "id": h.get("id", "hyper"),
                "label": h.get("label", ""),
                "nodes": members,
                "relation": h.get("relation", "participate_in"),
                "confidence": h.get("confidence", "INFERRED"),
                "confidence_score": float(h.get("confidence_score", 0.8)),
                "source_file": h.get("source_file", "CONCORD_v0_3_Core_Specification.pdf"),
            }
        )

    return {
        "nodes": nodes_out,
        "edges": edges_out,
        "hyperedges": hyper_out,
        "input_tokens": int(frag.get("input_tokens", 0)),
        "output_tokens": int(frag.get("output_tokens", 0)),
    }


def _norm_code_chunk(frag: dict) -> dict:
    """Chunk C: add required fields; map file_type markdown -> document."""
    node_by_id = {}
    for n in frag.get("nodes", []):
        nid = n.get("id")
        if not nid:
            continue
        ft = n.get("file_type") or "code"
        if ft == "markdown":
            ft = "document"
        if ft not in ("code", "document", "paper", "image", "rationale", "concept"):
            ft = "code"
        label = n.get("label") or nid
        src = n.get("source_file") or "unknown"
        node_by_id[nid] = {
            "id": nid,
            "label": label,
            "file_type": ft,
            "source_file": src,
            "source_location": None,
            "source_url": None,
            "captured_at": None,
            "author": None,
            "contributor": None,
        }

    edges_out = []
    for e in frag.get("edges", []):
        s, t = e.get("source"), e.get("target")
        if s not in node_by_id or t not in node_by_id:
            continue
        cs = e.get("confidence_score", 0.85)
        edges_out.append(
            {
                "source": s,
                "target": t,
                "relation": e.get("relation") or "conceptually_related_to",
                "confidence": "INFERRED",
                "confidence_score": float(cs),
                "source_file": node_by_id[s]["source_file"],
                "source_location": None,
                "weight": float(e.get("weight", 1.0)),
            }
        )

    hyper_out = []
    for h in frag.get("hyperedges", []):
        members = h.get("nodes") or h.get("member_node_ids") or []
        if not members:
            continue
        ok = [m for m in members if m in node_by_id]
        if len(ok) < 2:
            continue
        hyper_out.append(
            {
                "id": h.get("id", "hyper"),
                "label": h.get("label", ""),
                "nodes": ok,
                "relation": h.get("relation", "participate_in"),
                "confidence": "INFERRED",
                "confidence_score": float(h.get("confidence_score", 0.85)),
                "source_file": node_by_id[ok[0]]["source_file"],
            }
        )

    return {
        "nodes": list(node_by_id.values()),
        "edges": edges_out,
        "hyperedges": hyper_out,
        "input_tokens": int(frag.get("input_tokens", 0)),
        "output_tokens": int(frag.get("output_tokens", 0)),
    }


def _norm_doc_chunk(frag: dict) -> dict:
    """Ensure hyperedges have string confidence; drop invalid rationale_for if needed."""
    for e in frag.get("edges", []):
        if "confidence" not in e:
            e["confidence"] = "INFERRED"
        if e["confidence"] not in ("EXTRACTED", "INFERRED", "AMBIGUOUS"):
            e["confidence"] = "INFERRED"
        if "confidence_score" not in e:
            e["confidence_score"] = 0.8
        if "source_file" not in e:
            e["source_file"] = "CONCORD_Integration_Lessons.md"
    for n in frag.get("nodes", []):
        if n.get("file_type") not in ("code", "document", "paper", "image", "rationale", "concept"):
            n["file_type"] = "document"
    for h in frag.get("hyperedges", []):
        if isinstance(h.get("confidence"), float):
            h["confidence"] = "INFERRED"
    return frag


def merge_semantic(frags: list[dict]) -> dict:
    nodes_dedup: dict[str, dict] = {}
    edges_all: list = []
    hyper_all: list = []
    inp = outp = 0
    for frag in frags:
        for n in frag.get("nodes", []):
            if n.get("id"):
                nodes_dedup[n["id"]] = n
        edges_all.extend(frag.get("edges", []))
        hyper_all.extend(frag.get("hyperedges", []))
        inp += int(frag.get("input_tokens", 0))
        outp += int(frag.get("output_tokens", 0))
    return {
        "nodes": list(nodes_dedup.values()),
        "edges": edges_all,
        "hyperedges": hyper_all,
        "input_tokens": inp,
        "output_tokens": outp,
    }


def main() -> None:
    ast = json.loads((ROOT / ".graphify_ast.json").read_text(encoding="utf-8"))
    out_dir = ROOT / "graphify-out" / "semantic_chunks"
    out_dir.mkdir(parents=True, exist_ok=True)
    frags: list[dict] = []
    for i, p in enumerate(CHUNK_JSONL):
        if not p.exists():
            raise SystemExit(f"Missing transcript: {p}")
        raw = _load_chunk_from_jsonl(p)
        if i == 3:
            raw = _norm_pdf_chunk(raw)
        elif i == 2:
            raw = _norm_code_chunk(raw)
        else:
            raw = _norm_doc_chunk(raw)
        (out_dir / f"chunk_{i + 1:02d}.json").write_text(
            json.dumps(raw, indent=2), encoding="utf-8"
        )
        frags.append(raw)
        print(f"Chunk {i + 1}: {len(raw['nodes'])} nodes, {len(raw['edges'])} edges")

    sem = merge_semantic(frags)
    (ROOT / ".graphify_semantic.json").write_text(json.dumps(sem, indent=2), encoding="utf-8")
    print(f"Semantic merged: {len(sem['nodes'])} nodes, {len(sem['edges'])} edges")

    seen = {n["id"] for n in ast["nodes"]}
    merged_nodes = list(ast["nodes"])
    for n in sem["nodes"]:
        if n["id"] not in seen:
            merged_nodes.append(n)
            seen.add(n["id"])
    merged = {
        "nodes": merged_nodes,
        "edges": ast["edges"] + sem["edges"],
        "hyperedges": sem.get("hyperedges", []),
        "input_tokens": sem.get("input_tokens", 0),
        "output_tokens": sem.get("output_tokens", 0),
    }
    (ROOT / ".graphify_extract.json").write_text(json.dumps(merged, indent=2), encoding="utf-8")
    print(f"Extract: {len(merged['nodes'])} nodes, {len(merged['edges'])} edges")


if __name__ == "__main__":
    main()
