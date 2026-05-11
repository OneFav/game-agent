from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def build_manifest(root: Path, package_type: str, package_id: str) -> dict[str, Any]:
    root = root.resolve()
    digest = hashlib.sha256()
    files: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name == "manifest.json" or "__pycache__" in path.parts:
            continue
        rel = path.relative_to(root).as_posix()
        files.append(rel)
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return {
        "schema_version": "1.0",
        "package_type": package_type,
        "package_id": package_id,
        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "files": files,
        "freeze_hash": digest.hexdigest(),
    }
