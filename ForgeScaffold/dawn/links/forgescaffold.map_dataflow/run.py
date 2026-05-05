import ast
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


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


def load_catalog(artifact_store) -> Dict[str, Any]:
    artifact_meta = artifact_store.get("forgescaffold.system_catalog.json")
    if not artifact_meta:
        raise RuntimeError("Missing system catalog artifact")
    with open(artifact_meta["path"], "r") as fh:
        return json.load(fh)


def readable_relpath(project_root: Path, target: Path) -> str:
    try:
        return str(target.relative_to(project_root))
    except ValueError:
        return str(target)


def gather_module_sources(project_root: Path, module_units: Dict[str, Dict[str, Any]]) -> Dict[str, List[Path]]:
    sources: Dict[str, List[Path]] = {}
    for module_id, unit in module_units.items():
        paths: Set[Path] = set()
        candidate = project_root / unit.get("path", "")
        entry = unit.get("entrypoint")
        if candidate.is_dir():
            for child in candidate.rglob("*.py"):
                if child.is_file():
                    paths.add(child)
        elif candidate.is_file():
            paths.add(candidate)
        if entry:
            entry_path = project_root / entry
            if entry_path.exists():
                paths.add(entry_path)
        sources[module_id] = sorted(paths)
    return sources


def extract_imports_from_file(file_path: Path) -> List[Tuple[str, int]]:
    try:
        tree = ast.parse(file_path.read_text(), filename=str(file_path))
    except (SyntaxError, UnicodeDecodeError):
        return []

    imports: List[Tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append((alias.name, node.lineno))
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                name = module or alias.name
                imports.append((name, node.lineno))
    return imports


def add_edge(edges: List[Dict[str, Any]], seen: Set[Tuple[str, str, str, str, Optional[int]]],
             from_id: str, to_id: str, edge_type: str, evidence: Dict[str, Any]) -> None:
    key = (from_id, to_id, edge_type, evidence.get("file", ""), evidence.get("line"))
    if key in seen:
        return
    seen.add(key)
    edges.append({
        "from": from_id,
        "to": to_id,
        "type": edge_type,
        "evidence": [evidence],
    })


def match_module(import_name: str, module_ids: Set[str]) -> Optional[str]:
    candidate = import_name
    while candidate:
        if candidate in module_ids:
            return candidate
        if "." not in candidate:
            break
        candidate = candidate.rsplit(".", 1)[0]
    return None


def build_external_index(units: Dict[str, Dict[str, Any]]) -> Dict[str, str]:
    index: Dict[str, str] = {}
    for unit_id, unit in units.items():
        dep_name = (unit.get("entrypoint") or unit_id).lower()
        cleaned = dep_name.split(".")[0]
        index[cleaned] = unit_id
        index[unit_id.lower()] = unit_id
    return index


def load_text(file_path: Path) -> str:
    try:
        return file_path.read_text().lower()
    except Exception:
        return ""


def run(project_context: Dict[str, Any], link_config: Dict[str, Any]) -> Dict[str, Any]:
    project_root = Path(project_context["project_root"])
    sandbox = project_context.get("sandbox")
    artifact_store = project_context.get("artifact_store")
    if not sandbox or not artifact_store:
        raise RuntimeError("Sandbox or artifact store missing")

    schema_path = Path(__file__).resolve().parents[2] / "schemas" / "dataflow_map.schema.json"
    register_schema("forgescaffold.dataflow_map", schema_path)

    catalog = load_catalog(artifact_store)
    units = {unit["id"]: unit for unit in catalog.get("units", [])}

    module_units = {uid: unit for uid, unit in units.items() if unit.get("type") == "module"}
    datastore_units = {uid: unit for uid, unit in units.items() if unit.get("type") == "datastore"}
    service_units = {uid: unit for uid, unit in units.items() if unit.get("type") == "service"}
    agent_units = {uid: unit for uid, unit in units.items() if unit.get("type") == "agent_step"}
    external_units = {uid: unit for uid, unit in units.items() if unit.get("type") == "external_dependency"}

    external_index = build_external_index(external_units)
    module_sources = gather_module_sources(project_root, module_units)

    edges: List[Dict[str, Any]] = []
    seen: Set[Tuple[str, str, str, str, Optional[int]]] = set()

    http_keywords = {"requests": "http", "httpx": "http", "urllib": "http", "fetch": "http", "axios": "http"}
    grpc_keywords = {"grpc": "grpc"}
    spawn_keywords = {"subprocess": "spawns", "os.system": "spawns", "multiprocess": "spawns"}
    retrieve_keywords = {"vectorstore": "retrieves", "pinecone": "retrieves", "faiss": "retrieves", "llama": "retrieves"}

    module_ids = set(module_units.keys())
    for module_id, file_paths in module_sources.items():
        for src_file in file_paths:
            text = load_text(src_file)
            imports = extract_imports_from_file(src_file)
            for import_name, lineno in imports:
                target = match_module(import_name, module_ids)
                edge_type = "imports"
                evidence = {"file": readable_relpath(project_root, src_file), "line": lineno, "note": import_name}
                if target:
                    add_edge(edges, seen, module_id, target, edge_type, evidence)
                else:
                    key = import_name.split(".")[0].lower()
                    ext_target = external_index.get(key)
                    if ext_target:
                        add_edge(edges, seen, module_id, ext_target, edge_type, evidence)

            for keyword, edge_cat in http_keywords.items():
                if keyword in text:
                    evidence = {"file": readable_relpath(project_root, src_file), "line": None, "note": f"uses {keyword}"}
                    matched = False
                    for service_id, service_unit in service_units.items():
                        entry = (service_unit.get("entrypoint") or "").lower()
                        if keyword in entry or keyword in service_id:
                            add_edge(edges, seen, module_id, service_id, edge_cat, evidence)
                            matched = True
                            break
                    if not matched:
                        target_ext = external_index.get(keyword)
                        if target_ext:
                            add_edge(edges, seen, module_id, target_ext, edge_cat, evidence)

            for keyword, edge_cat in grpc_keywords.items():
                if keyword in text:
                    target_ext = external_index.get(keyword)
                    if target_ext:
                        evidence = {"file": readable_relpath(project_root, src_file), "line": None, "note": f"uses {keyword}"}
                        add_edge(edges, seen, module_id, target_ext, edge_cat, evidence)

            for keyword, edge_cat in spawn_keywords.items():
                if keyword in text:
                    target_ext = external_index.get(keyword)
                    if target_ext:
                        evidence = {"file": readable_relpath(project_root, src_file), "line": None, "note": f"spawns via {keyword}"}
                        add_edge(edges, seen, module_id, target_ext, edge_cat, evidence)

            for keyword, edge_cat in retrieve_keywords.items():
                if keyword in text:
                    target_ext = external_index.get(keyword) or module_id
                    evidence = {"file": readable_relpath(project_root, src_file), "line": None, "note": f"retrieves {keyword}"}
                    add_edge(edges, seen, module_id, target_ext, edge_cat, evidence)

            for datastore_id, datastore_unit in datastore_units.items():
                datastore_path = datastore_unit.get("path", "").lower()
                if not datastore_path:
                    continue
                if datastore_path in text:
                    edge_type = "reads" if "read" in text else "writes"
                    evidence = {"file": readable_relpath(project_root, src_file), "line": None, "note": f"touches {datastore_path}"}
                    add_edge(edges, seen, module_id, datastore_id, edge_type, evidence)

            for service_id, service_unit in service_units.items():
                name = service_id.split(".", 1)[-1].lower()
                if name and name in text:
                    evidence = {"file": readable_relpath(project_root, src_file), "line": None, "note": f"calls {name}"}
                    add_edge(edges, seen, module_id, service_id, "http", evidence)

    agent_list = sorted(agent_units.keys())
    for idx in range(len(agent_list) - 1):
        first = agent_list[idx]
        second = agent_list[idx + 1]
        evidence = {
            "file": agent_units[first].get("path"),
            "line": None,
            "note": "sequence"}
        add_edge(edges, seen, first, second, "event", evidence)

    nodes = []
    for unit_id, unit in sorted(units.items()):
        nodes.append({"id": unit_id, "type": unit.get("type"), "path": unit.get("path"), "language": unit.get("language")})

    payload = {"project_id": project_context["project_id"], "nodes": nodes, "edges": edges}
    artifact_path = sandbox.publish(
        "forgescaffold.dataflow_map.json",
        "dataflow_map.json",
        payload,
        schema="forgescaffold.dataflow_map",
    )

    return {
        "status": "SUCCEEDED",
        "outputs": {"forgescaffold.dataflow_map.json": {"path": artifact_path}},
        "metrics": {"edges": len(edges), "nodes": len(nodes)},
    }
