import shutil
from pathlib import Path

from ..base import AdapterError


REQUIRED_FILES = ["ci_log_01.txt", "repo_snapshot_manifest.json", "failing_tests.json"]


def ingest(source_path: str, out_raw_dir: str) -> None:
    src = Path(source_path)
    if not src.exists():
        raise AdapterError(f"source path not found: {source_path}")
    dst = Path(out_raw_dir)
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    for name in REQUIRED_FILES:
        if not (dst / name).exists():
            raise AdapterError(f"missing required raw file: {name}")
