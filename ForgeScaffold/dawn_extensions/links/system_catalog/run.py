import json
import os
from pathlib import Path
from typing import Any, Dict, List, MutableMapping, Optional

try:
    import yaml
except ImportError:
    yaml = None

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None


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


def readable_relpath(project_root: Path, target: Path) -> str:
    try:
        return str(target.relative_to(project_root))
    except ValueError:
        return str(target)


def collect_python_units(project_root: Path, project_id: str) -> Dict[str, Dict[str, Any]]:
    modules: Dict[str, Dict[str, Any]] = {}
    src_root = project_root / "src"
    if not src_root.exists():
        return modules

    def add_unit(unit_id: str, path: Path, entrypoint: Optional[Path]) -> None:
        modules[unit_id] = {
            "id": unit_id,
            "type": "module",
            "path": readable_relpath(project_root, path),
            "entrypoint": readable_relpath(project_root, entrypoint) if entrypoint else None,
            "language": "python",
            "owner_tag": project_id,
            "risk_tags": [],
            "exports": [],
            "observability": {"logs": f"{unit_id}.log", "tracing": "auto"},
        }

    for init_file in sorted(src_root.rglob("__init__.py")):
        pkg_dir = init_file.parent
        unit_id = pkg_dir.relative_to(project_root).as_posix().replace("/", ".")
        if unit_id in modules:
            continue
        add_unit(unit_id, pkg_dir, init_file)

    for py_file in sorted(src_root.rglob("*.py")):
        if py_file.name == "__init__.py":
            continue
        pkg_path = py_file.parent
        pkg_has_init = (pkg_path / "__init__.py").exists()
        unit_id = py_file.with_suffix("").relative_to(project_root).as_posix().replace("/", ".")
        if pkg_has_init:
            namespace = pkg_path.relative_to(project_root).as_posix().replace("/", ".")
            if namespace in modules:
                continue
        if unit_id in modules:
            continue
        add_unit(unit_id, py_file, py_file)

    return modules


def collect_service_units(project_root: Path, project_id: str) -> Dict[str, Dict[str, Any]]:
    services: Dict[str, Dict[str, Any]] = {}
    compose_candidates = []
    for pattern in ["docker-compose.yml", "docker-compose.yaml", "compose.yaml", "compose.yml"]:
        for match in project_root.rglob(pattern):
            compose_candidates.append(match)

    if yaml is None:
        return services

    compose_candidates.sort()
    for compose_file in compose_candidates:
        try:
            raw = yaml.safe_load(compose_file) or {}
        except Exception:
            continue
        svc_map = raw.get("services") or {}
        for svc_name in sorted(svc_map.keys()):
            details = svc_map[svc_name] or {}
            unit_id = f"service.{svc_name}"
            services[unit_id] = {
                "id": unit_id,
                "type": "service",
                "path": readable_relpath(project_root, compose_file),
                "entrypoint": details.get("command") or details.get("image"),
                "language": "container",
                "owner_tag": details.get("labels", {}).get("owner", project_id),
                "risk_tags": ["network", "runtime"],
                "exports": [],
                "observability": {
                    "ports": details.get("ports", []),
                    "logging": details.get("logging", {}).get("driver"),
                },
            }

    # Kubernetes deployments
    for yaml_path in sorted(project_root.rglob("*.yaml")) + sorted(project_root.rglob("*.yml")):
        if yaml_path.name in ["docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"]:
            continue
        try:
            doc = yaml.safe_load(yaml_path)
        except Exception:
            continue
        if not isinstance(doc, dict):
            continue
        kind = (doc.get("kind") or "").lower()
        if kind not in {"deployment", "statefulset", "service"}:
            continue
        metadata = doc.get("metadata", {})
        name = metadata.get("name")
        if not name:
            continue
        unit_id = f"service.{name}"
        if unit_id in services:
            continue
        spec = doc.get("spec", {})
        services[unit_id] = {
            "id": unit_id,
            "type": "service",
            "path": readable_relpath(project_root, yaml_path),
            "entrypoint": spec.get("template", {}).get("spec", {}).get("containers", [{}])[0].get("image"),
            "language": "container",
            "owner_tag": metadata.get("labels", {}).get("owner", project_id),
            "risk_tags": ["k8s", "event"],
            "exports": [],
            "observability": {
                "ports": spec.get("ports", []),
                "logging": metadata.get("annotations", {}).get("logging", "default"),
            },
        }

    return services


def collect_agent_units(project_root: Path, project_id: str) -> Dict[str, Dict[str, Any]]:
    agents: Dict[str, Dict[str, Any]] = {}
    candidates = ["agents", "agent_steps", "workflows", "pipeline", "flows", "skills", "tools"]
    for folder in candidates:
        candidate_dir = project_root / folder
        if not candidate_dir.exists():
            continue
        for data_file in sorted(candidate_dir.rglob("*") if candidate_dir.is_dir() else []):
            if not data_file.is_file():
                continue
            suffix = data_file.suffix.lower()
            if suffix not in {".yaml", ".yml", ".json", ".py"}:
                continue
            unit_id = f"agent_step.{folder}.{data_file.stem}"
            agents[unit_id] = {
                "id": unit_id,
                "type": "agent_step",
                "path": readable_relpath(project_root, data_file),
                "entrypoint": readable_relpath(project_root, data_file),
                "language": "python" if suffix == ".py" else "yaml",
                "owner_tag": project_id,
                "risk_tags": ["automation"],
                "exports": [],
                "observability": {"signal": "event"},
            }
    return agents


def collect_datastores(project_root: Path, project_id: str) -> Dict[str, Dict[str, Any]]:
    storages: Dict[str, Dict[str, Any]] = {}
    base_dirs = ["data", "storage", "databases", "db", "state", "cache"]
    for base_name in base_dirs:
        candidate_dir = project_root / base_name
        if not candidate_dir.exists():
            continue
        if candidate_dir.is_dir():
            unit_id = f"datastore.{base_name}"
            storages[unit_id] = {
                "id": unit_id,
                "type": "datastore",
                "path": readable_relpath(project_root, candidate_dir),
                "entrypoint": None,
                "language": "config",
                "owner_tag": project_id,
                "risk_tags": ["persistent"],
                "exports": [],
                "observability": {"metrics": "enabled"},
            }
            for db_file in sorted(candidate_dir.rglob("*")):
                if not db_file.is_file():
                    continue
                if db_file.suffix.lower() not in {".db", ".sqlite", ".sqlite3", ".json", ".yaml", ".yml"}:
                    continue
                inner_id = f"datastore.{base_name}.{db_file.stem}"
                storages.setdefault(inner_id, {
                    "id": inner_id,
                    "type": "datastore",
                    "path": readable_relpath(project_root, db_file),
                    "entrypoint": readable_relpath(project_root, db_file),
                    "language": db_file.suffix.lstrip("."),
                    "owner_tag": project_id,
                    "risk_tags": ["persistent"],
                    "exports": [],
                    "observability": {"metrics": "enabled"},
                })
    return storages


def collect_external_deps(project_root: Path, project_id: str) -> Dict[str, Dict[str, Any]]:
    externals: Dict[str, Dict[str, Any]] = {}

    def add_dep(dep_name: str, source: str, language: str) -> None:
        artifact_id = f"external.{dep_name}"
        if artifact_id in externals:
            return
        externals[artifact_id] = {
            "id": artifact_id,
            "type": "external_dependency",
            "path": source,
            "entrypoint": dep_name,
            "language": language,
            "owner_tag": project_id,
            "risk_tags": ["third_party"],
            "exports": [],
            "observability": {"trust": "unknown"},
        }

    requirements = project_root / "requirements.txt"
    if requirements.exists():
        for line in requirements.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            name = line.split("==")[0].split("<=")[0].split("<")[0].strip()
            if name:
                add_dep(name, readable_relpath(project_root, requirements), "python")

    poetry = project_root / "pyproject.toml"
    if tomllib and poetry.exists():
        try:
            with poetry.open("rb") as fh:
                data = tomllib.load(fh)
            deps = data.get("tool", {}).get("poetry", {}).get("dependencies", {}) or {}
            for name in deps:
                if name == "python":
                    continue
                add_dep(name, readable_relpath(project_root, poetry), "python")
        except Exception:
            pass

    package_json = project_root / "package.json"
    if package_json.exists():
        try:
            payload = json.loads(package_json.read_text())
            for section in ("dependencies", "devDependencies", "peerDependencies"):
                for name in payload.get(section, {}).keys():
                    add_dep(name, readable_relpath(project_root, package_json), "javascript")
        except Exception:
            pass

    for extra in ("requests", "httpx", "grpc", "subprocess", "vectorstore", "pinecone"):
        add_dep(extra, "detected", "python")

    return externals


def assemble_units(project_root: Path, project_id: str) -> List[Dict[str, Any]]:
    units: Dict[str, Dict[str, Any]] = {}
    for collector in (
        collect_python_units,
        collect_service_units,
        collect_agent_units,
        collect_datastores,
        collect_external_deps,
    ):
        gathered = collector(project_root, project_id)
        units.update(gathered)
    return [units[key] for key in sorted(units.keys())]


def run(project_context: Dict[str, Any], link_config: Dict[str, Any]) -> Dict[str, Any]:
    project_id = project_context["project_id"]
    sandbox = project_context.get("sandbox")
    artifact_store = project_context.get("artifact_store")
    project_root = Path(project_context["project_root"])

    schema_path = Path(__file__).resolve().parents[2] / "schemas" / "system_catalog.schema.json"
    register_schema("forgescaffold.system_catalog", schema_path)

    units = assemble_units(project_root, project_id)
    payload = {"project_id": project_id, "units": units}

    if not sandbox or not artifact_store:
        raise RuntimeError("Sandbox or artifact store missing in context")

    artifact_path = sandbox.publish(
        "forgescaffold.system_catalog.json",
        "system_catalog.json",
        payload,
        schema="forgescaffold.system_catalog",
    )

    return {
        "status": "SUCCEEDED",
        "outputs": {"forgescaffold.system_catalog.json": {"path": artifact_path}},
        "metrics": {"unitCount": len(units)}
    }
