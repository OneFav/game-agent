from __future__ import annotations

import tomllib
from pathlib import Path

# ── Codex subagent (.codex/agents/*.toml) 验证 ──────────────────────────

CODEX_AGENT_REQUIREMENTS = {
    "scenario_compiler": {
        "name": "scenario_compiler",
        "required_di_terms": [
            "Scenario Researcher",
            "scenarios/<project-id>-scenario/",
            "用户目标",
            "runtime",
            "task_spec.yaml",
            "env_config.yaml",
            "assumptions.md",
            "manifest.json",
            "训练 reward",
            "不得伪造",
        ],
    },
    "policy_designer": {
        "name": "policy_designer",
        "required_di_terms": [
            "Method Researcher",
            "policies/<project-id>-policy/",
            "方法假设",
            "Baseline",
            "Candidate",
            "policy.py",
            "default_config.yaml",
            "search_space.yaml",
            "algorithm_card.md",
            "metadata.json",
            "supports_training=false",
            "不能复制固定",
        ],
    },
    "experiment_autoresearch": {
        "name": "experiment_autoresearch",
        "required_di_terms": [
            "Experiment Researcher",
            "experiments/<project-id>-experiment/",
            "真实实验",
            "Baseline",
            "Candidate",
            "hard constraints",
            "trial",
            "leaderboard.csv",
            "baseline_metrics.json",
            "best_config.yaml",
            "agent_result.json",
            "objective_not_met",
        ],
    },
}


# ── Codex subagent TOML 测试 ────────────────────────────────────────────

def test_codex_agent_toml_files_exist() -> None:
    """验证三个 .codex/agents/*.toml 文件存在且 TOML 格式有效."""
    for agent_name in CODEX_AGENT_REQUIREMENTS:
        path = Path(".codex") / "agents" / f"{agent_name}.toml"
        assert path.exists(), f"missing .codex/agents/{agent_name}.toml"
        assert path.stat().st_size > 0, f"empty .codex/agents/{agent_name}.toml"


def test_codex_agent_toml_valid_format() -> None:
    """验证所有 .codex/agents/*.toml 文件可被 Python tomllib 解析."""
    agents_dir = Path(".codex") / "agents"
    for toml_file in sorted(agents_dir.glob("*.toml")):
        with open(toml_file, "rb") as fh:
            config = tomllib.load(fh)
        assert "name" in config, f"{toml_file} missing required field: name"
        assert "description" in config, f"{toml_file} missing required field: description"
        assert (
            "instructions" in config or "developer_instructions" in config
        ), f"{toml_file} missing instructions or developer_instructions"


def test_codex_agent_developer_instructions_contain_required_content() -> None:
    """验证每个 Codex subagent 的 developer_instructions 包含必需的操作内容."""
    agents_dir = Path(".codex") / "agents"
    for agent_name, requirements in CODEX_AGENT_REQUIREMENTS.items():
        path = agents_dir / f"{agent_name}.toml"
        with open(path, "rb") as fh:
            config = tomllib.load(fh)

        # 获取 instructions 内容（优先 developer_instructions，其次 instructions）
        di = config.get("developer_instructions") or config.get("instructions") or ""
        assert len(di) >= 500, (
            f"{agent_name}.toml developer_instructions is too short "
            f"({len(di)} chars, expected >= 500)"
        )

        for term in requirements["required_di_terms"]:
            assert term in di, f"{agent_name}.toml developer_instructions missing: {term}"


def test_codex_agent_no_stale_agents_dir() -> None:
    """验证旧的 agents/ 目录已删除，不再使用旧格式."""
    assert not Path("agents").exists(), (
        "stale agents/ directory detected — content has been migrated to .codex/agents/*.toml; "
        "delete agents/ before committing"
    )


def test_legacy_project_skills_are_removed() -> None:
    """工作台直接使用 Codex SDK Agent 配置，不再发布旧命令式技能。"""
    assert not (Path(".agents") / "skills").exists()
