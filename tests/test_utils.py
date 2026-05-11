from pathlib import Path

import pytest

from game_agent.utils.fs import ensure_empty_output_dir, read_yaml, write_yaml
from game_agent.utils.manifest import build_manifest


def test_yaml_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "sample.yaml"
    write_yaml(path, {"name": "drone_ring", "value": 3})
    assert read_yaml(path) == {"name": "drone_ring", "value": 3}


def test_ensure_empty_output_dir_rejects_existing_content(tmp_path: Path) -> None:
    out = tmp_path / "scenario"
    out.mkdir()
    (out / "existing.txt").write_text("content", encoding="utf-8")
    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        ensure_empty_output_dir(out)


def test_ensure_empty_output_dir_rejects_existing_file(tmp_path: Path) -> None:
    out = tmp_path / "scenario"
    out.write_text("content", encoding="utf-8")
    with pytest.raises(FileExistsError, match="Refusing to overwrite non-directory path"):
        ensure_empty_output_dir(out)


def test_build_manifest_hash_changes_with_content(tmp_path: Path) -> None:
    root = tmp_path / "package"
    root.mkdir()
    file_path = root / "a.txt"
    file_path.write_text("one", encoding="utf-8")
    first = build_manifest(root, package_type="scenario", package_id="demo")
    file_path.write_text("two", encoding="utf-8")
    second = build_manifest(root, package_type="scenario", package_id="demo")
    assert first["freeze_hash"] != second["freeze_hash"]
    assert first["package_type"] == "scenario"


def test_build_manifest_uses_posix_relative_paths_and_ignores_generated_files(tmp_path: Path) -> None:
    root = tmp_path / "package"
    nested = root / "nested"
    cache = root / "__pycache__"
    nested.mkdir(parents=True)
    cache.mkdir(parents=True)
    (nested / "a.txt").write_text("tracked", encoding="utf-8")
    (root / "manifest.json").write_text("ignored-one", encoding="utf-8")
    (cache / "module.pyc").write_bytes(b"ignored-two")

    first = build_manifest(root, package_type="scenario", package_id="demo")

    assert first["files"] == ["nested/a.txt"]
    assert all(not Path(file).is_absolute() for file in first["files"])
    assert "manifest.json" not in first["files"]
    assert "__pycache__/module.pyc" not in first["files"]

    (root / "manifest.json").write_text("ignored-one-changed", encoding="utf-8")
    (cache / "module.pyc").write_bytes(b"ignored-two-changed")
    second = build_manifest(root, package_type="scenario", package_id="demo")

    assert second["freeze_hash"] == first["freeze_hash"]
