from __future__ import annotations

from pathlib import Path

import pytest

from game_agent.visualization.executor import (
    REQUIRED_AGENT_CONFIGS,
    AgentRuntimeUnavailable,
    ProjectExecutor,
    _validate_agent_result,
)
from game_agent.visualization.workbench import WorkbenchStore


def test_project_executor_rejects_m1_fallback_without_codex_runtime(
    tmp_path: Path,
) -> None:
    run_root = tmp_path / "suite_runs" / "sample"
    run_root.mkdir(parents=True)
    store = WorkbenchStore(tmp_path, run_root)
    project = store.create_project(
        "两环策略实验",
        "红方无人机穿过两个圆环，蓝方追击拦截，超时 40 步。",
    )
    executor = ProjectExecutor(tmp_path, store)

    with pytest.raises(AgentRuntimeUnavailable) as captured:
        executor.start(project["project_id"])

    status = captured.value.status
    assert status["ready"] is False
    assert status["fallback_enabled"] is False
    assert status["runtime_connected"] is False
    assert status["missing_configs"]
    current = store.load_local_project(project["project_id"])
    assert current is not None
    assert current["status"] == "active"
    assert not (tmp_path / "scenarios").exists()
    assert not (tmp_path / "policies").exists()
    assert not (tmp_path / "experiments").exists()


def test_project_executor_reports_ready_with_sdk_and_all_profiles(
    tmp_path: Path,
) -> None:
    run_root = tmp_path / "suite_runs" / "sample"
    run_root.mkdir(parents=True)
    for relative in REQUIRED_AGENT_CONFIGS:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("developer_instructions = 'real agent'\n", encoding="utf-8")

    executor = ProjectExecutor(tmp_path, WorkbenchStore(tmp_path, run_root))

    status = executor.status()
    assert status["ready"] is True
    assert status["runtime"] == "codex-sdk"
    assert status["fallback_enabled"] is False
    assert status["message"] == "Codex Agent 已就绪"


def test_project_executor_forwards_human_message_to_active_turn(
    tmp_path: Path,
) -> None:
    class FakeTurn:
        steered: list[str] = []
        interrupted = False

        def steer(self, prompt: str) -> None:
            self.steered.append(prompt)

        def interrupt(self) -> None:
            self.interrupted = True

    run_root = tmp_path / "suite_runs" / "sample"
    run_root.mkdir(parents=True)
    store = WorkbenchStore(tmp_path, run_root)
    project = store.create_project("可干预实验", "运行时接受人的方向调整")
    project_id = str(project["project_id"])
    executor = ProjectExecutor(tmp_path, store)
    turn = FakeTurn()
    executor._turns[project_id] = turn

    executor.intervene(project_id, "message", {"message": "保留 seed 101"})
    executor.intervene(project_id, "pause", {})

    assert "保留 seed 101" in turn.steered[0]
    assert turn.interrupted is True


def test_agent_result_distinguishes_execution_from_objective() -> None:
    result = {
        "schema_version": "autogame_agent_result/v1",
        "project_id": "local-test",
        "execution_status": "completed",
        "objective_status": "not_met",
        "summary": "实验已执行，但候选方法没有超过基线。",
        "method": {},
        "comparison": {},
        "metric_series": {},
        "artifacts": {},
        "constraint_evidence": [],
        "failed_seeds": [],
        "commands": [],
        "limitations": [],
    }

    _validate_agent_result(result, "local-test")

    result["objective_status"] = "completed"
    with pytest.raises(ValueError, match="objective_status"):
        _validate_agent_result(result, "local-test")
