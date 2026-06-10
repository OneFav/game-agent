from __future__ import annotations

import tomllib
from pathlib import Path

# ── Codex subagent (.codex/agents/*.toml) 验证 ──────────────────────────

CODEX_AGENT_REQUIREMENTS = {
    "scenario_compiler": {
        "name": "scenario_compiler",
        "required_di_terms": [
            "Scenario Compiler",
            "scenarios/<task_id>/",
            "compile",
            "task_text",
            "task_id",
            "task_spec.yaml",
            "env_config.yaml",
            "env.py",
            "model.md",
            "assumptions.md",
            "manifest.json",
            "post_scenario_compile.py",
            # Chinese boundary terms
            "允许写入",
            "绝对禁止",
            "Done Definition",
            # Work boundary
            "policies/",
            "experiments/",
            "contracts/",
        ],
    },
    "policy_designer": {
        "name": "policy_designer",
        "required_di_terms": [
            "Policy Designer",
            "policies/<policy_id>/",
            "build",
            "scenario_dir",
            "policy_id",
            "Policy ABC",
            "policy.py",
            "train.py",
            "infer.py",
            "default_config.yaml",
            "search_space.yaml",
            "algorithm_card.md",
            "post_policy_submit.py",
            # Chinese boundary terms
            "允许写入",
            "绝对禁止",
            "Done Definition",
            # Work boundary
            "scenarios/",
            "experiments/",
            "contracts/",
            "act(",
        ],
    },
    "experiment_autoresearch": {
        "name": "experiment_autoresearch",
        "required_di_terms": [
            "AutoResearch",
            "experiments/<exp_id>/",
            "run",
            "sweep",
            "leaderboard",
            "best_config",
            "evaluation_metrics",
            "hard_constraints",
            "trial",
            "post_experiment_run.py",
            # Chinese boundary terms
            "允许写入",
            "绝对禁止",
            "Done Definition",
            # Work boundary
            "scenarios/",
            "policies/",
            "contracts/",
            "reward",
        ],
    },
}

# ── Skill (.agents/skills/*/SKILL.md) 验证 ──────────────────────────

SKILL_REQUIREMENTS = {
    "scenario-spec-compiler": [
        "natural-language",
        "ScenarioPackage",
        "assumptions.md",
        "every default",
    ],
    "policy-interface-builder": [
        "policy package",
        "action bounds",
        "train.py",
        "infer.py",
    ],
    "autoresearch-loop": [
        "deterministic sweep",
        "multi-seed",
        "leaderboard",
        "best config",
        "evaluation_metrics",
    ],
    "game-init": [
        "plan.md",
        "场景",
        "game/",
    ],
    "game-main": [
        "subagent",
        "scenario_compiler",
        "policy_designer",
        "experiment_autoresearch",
        "summary.md",
    ],
}


def _assert_substantive_markdown(path: Path, required_terms: list[str], min_chars: int = 240) -> str:
    assert path.exists(), f"missing {path}"
    text = path.read_text(encoding="utf-8")
    assert len(text.strip()) >= min_chars, f"{path} is too small to be useful ({len(text.strip())} chars)"
    for term in required_terms:
        assert term in text, f"{path} missing required content: {term}"
    return text


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


# ── Skill 测试 ──────────────────────────────────────────────────────────

def test_all_skills_have_required_operational_guidance() -> None:
    """验证所有 5 个技能（3 个原有 + 2 个新建）的 SKILL.md 完整且包含关键术语."""
    skills_dir = Path(".agents") / "skills"

    for skill, required_terms in SKILL_REQUIREMENTS.items():
        path = skills_dir / skill / "SKILL.md"
        text = _assert_substantive_markdown(path, required_terms, min_chars=320)
        assert text.startswith("---\n"), f"{path} should include YAML front matter (starts with '---')"
        assert "##" in text, f"{path} should be structured with markdown headings"


def test_game_init_skill_is_written_in_chinese() -> None:
    """验证 Game-init 技能使用中文编写."""
    path = Path(".agents") / "skills" / "game-init" / "SKILL.md"
    text = path.read_text(encoding="utf-8")
    chinese_indicators = ["场景", "人物", "描述", "计划", "需求"]
    found = [ci for ci in chinese_indicators if ci in text]
    assert len(found) >= 3, (
        f"game-init SKILL.md should be primarily in Chinese; "
        f"found Chinese indicators: {found}"
    )


def test_game_main_skill_is_written_in_chinese() -> None:
    """验证 Game-main 技能使用中文编写."""
    path = Path(".agents") / "skills" / "game-main" / "SKILL.md"
    text = path.read_text(encoding="utf-8")
    chinese_indicators = ["subagent", "场景", "策略", "实验", "自动科研"]
    found = [ci for ci in chinese_indicators if ci in text]
    assert len(found) >= 3, (
        f"game-main SKILL.md should be primarily in Chinese; "
        f"found Chinese indicators: {found}"
    )
