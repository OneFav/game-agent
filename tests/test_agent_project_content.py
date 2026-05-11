from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path
from types import ModuleType
from typing import Any


REQUIRED_AGENT_SECTIONS = [
    "## Mission",
    "## Allowed Edits",
    "## Forbidden Edits",
    "## Required Validation Command",
    "## Done Definition",
]

AGENT_REQUIREMENTS = {
    "scenario_compiler": {
        "mission": "convert semi-free natural-language drone tasks into `scenarios/<task_id>/`",
        "allowed": ["`scenarios/<task_id>/`"],
        "forbidden": ["`policies/`", "`experiments/`", "`contracts/`", "`hooks/`"],
        "validation": "python hooks/post_scenario_compile.py --scenario scenarios/<task_id>",
    },
    "policy_designer": {
        "mission": "convert a validated scenario into `policies/<policy_id>/`",
        "allowed": ["`policies/<policy_id>/`"],
        "forbidden": ["`scenarios/`", "`experiments/`", "`contracts/`", "`hooks/`"],
        "validation": "python hooks/post_policy_submit.py --policy policies/<policy_id>",
    },
    "experiment_autoresearch": {
        "mission": "run deterministic sweeps for frozen scenario/policy inputs",
        "allowed": ["`experiments/<exp_id>/`"],
        "forbidden": ["`scenarios/`", "`policies/`", "`contracts/`", "`hooks/`"],
        "validation": "python hooks/post_experiment_run.py --exp experiments/<exp_id>",
    },
}

SKILL_REQUIREMENTS = {
    "scenario-spec-compiler": [
        "natural-language extraction",
        "assumptions",
        "ScenarioPackage",
        "assumptions.md",
        "every default",
    ],
    "policy-interface-builder": [
        "policy package generation",
        "action bounds",
        "train.py",
        "infer.py",
        "actions clipped",
    ],
    "autoresearch-loop": [
        "deterministic sweep",
        "multi-seed metrics",
        "leaderboard",
        "best config",
        "evaluation_metrics",
        "reward components",
    ],
}


def _load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _assert_substantive_markdown(path: Path, required_terms: list[str], min_chars: int = 240) -> str:
    assert path.exists(), f"missing {path}"
    text = path.read_text(encoding="utf-8")
    assert len(text.strip()) >= min_chars, f"{path} is too small to be useful"
    for term in required_terms:
        assert term in text, f"{path} missing required content: {term}"
    return text


def test_agent_directories_have_required_substantive_files() -> None:
    for agent, requirements in AGENT_REQUIREMENTS.items():
        root = Path("agents") / agent
        assert root.is_dir(), f"missing agent directory: {root}"
        agents_text = _assert_substantive_markdown(
            root / "AGENTS.md",
            [
                *REQUIRED_AGENT_SECTIONS,
                requirements["mission"],
                *requirements["allowed"],
                *requirements["forbidden"],
                requirements["validation"],
            ],
        )
        assert "must not edit" in agents_text.lower()

        prompt_text = _assert_substantive_markdown(root / "prompt.md", [requirements["validation"]])
        assert any(path_fragment in prompt_text for path_fragment in requirements["allowed"])
        assert (root / "orchestrator.py").exists(), f"missing orchestrator for {agent}"


def test_core_skills_have_required_operational_guidance() -> None:
    for skill, required_terms in SKILL_REQUIREMENTS.items():
        path = Path(".agents") / "skills" / skill / "SKILL.md"
        text = _assert_substantive_markdown(path, required_terms, min_chars=320)
        assert text.startswith("---\n"), f"{path} should include skill front matter"
        assert "##" in text, f"{path} should be structured with markdown headings"


def test_scenario_compiler_orchestrator_is_thin_wrapper(monkeypatch: Any, tmp_path: Path) -> None:
    module = _load_module(Path("agents/scenario_compiler/orchestrator.py"), "scenario_compiler_orchestrator")
    signature = inspect.signature(module.run)
    assert list(signature.parameters) == ["task_text", "task_id", "project_root"]
    assert signature.parameters["project_root"].default == "."
    assert signature.return_annotation in (Path, "Path")

    calls: dict[str, Any] = {}

    class FakeCompiler:
        def __init__(self, project_root: Path) -> None:
            calls["project_root"] = project_root

        def compile(self, task_text: str, task_id: str) -> Path:
            calls["task_text"] = task_text
            calls["task_id"] = task_id
            return Path("scenario-out")

    monkeypatch.setattr(module, "ScenarioCompiler", FakeCompiler)

    assert module.run("task", "task_001", str(tmp_path)) == Path("scenario-out")
    assert calls == {"project_root": tmp_path, "task_text": "task", "task_id": "task_001"}


def test_policy_designer_orchestrator_is_thin_wrapper(monkeypatch: Any, tmp_path: Path) -> None:
    module = _load_module(Path("agents/policy_designer/orchestrator.py"), "policy_designer_orchestrator")
    signature = inspect.signature(module.run)
    assert list(signature.parameters) == ["scenario_dir", "policy_id", "project_root"]
    assert signature.parameters["project_root"].default == "."
    assert signature.return_annotation in (Path, "Path")

    calls: dict[str, Any] = {}

    class FakeDesigner:
        def __init__(self, project_root: Path) -> None:
            calls["project_root"] = project_root

        def build(self, scenario_dir: Path, policy_id: str) -> Path:
            calls["scenario_dir"] = scenario_dir
            calls["policy_id"] = policy_id
            return Path("policy-out")

    monkeypatch.setattr(module, "PolicyDesigner", FakeDesigner)

    assert module.run("scenarios/task_001", "policy_001", str(tmp_path)) == Path("policy-out")
    assert calls == {
        "project_root": tmp_path,
        "scenario_dir": Path("scenarios/task_001"),
        "policy_id": "policy_001",
    }


def test_autoresearch_orchestrator_is_thin_wrapper(monkeypatch: Any, tmp_path: Path) -> None:
    module = _load_module(Path("agents/experiment_autoresearch/orchestrator.py"), "autoresearch_orchestrator")
    signature = inspect.signature(module.run)
    assert list(signature.parameters) == ["scenario_dir", "policy_dir", "exp_id", "project_root"]
    assert signature.parameters["project_root"].default == "."
    assert signature.return_annotation in (Path, "Path")

    calls: dict[str, Any] = {}

    class FakeRunner:
        def __init__(self, project_root: Path) -> None:
            calls["project_root"] = project_root

        def run(self, scenario_dir: Path, policy_dir: Path, exp_id: str) -> Path:
            calls["scenario_dir"] = scenario_dir
            calls["policy_dir"] = policy_dir
            calls["exp_id"] = exp_id
            return Path("exp-out")

    monkeypatch.setattr(module, "AutoResearchRunner", FakeRunner)

    assert module.run("scenarios/task_001", "policies/policy_001", "exp_001", str(tmp_path)) == Path("exp-out")
    assert calls == {
        "project_root": tmp_path,
        "scenario_dir": Path("scenarios/task_001"),
        "policy_dir": Path("policies/policy_001"),
        "exp_id": "exp_001",
    }
