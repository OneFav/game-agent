from __future__ import annotations

import importlib.util
import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:  # pragma: no cover - Python 3.10 compatibility
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib

from game_agent.utils.fs import read_json
from game_agent.visualization.workbench import WorkbenchStore


REQUIRED_AGENT_CONFIGS = (
    ".codex/agents/scenario_compiler.toml",
    ".codex/agents/policy_designer.toml",
    ".codex/agents/experiment_autoresearch.toml",
)


@dataclass(frozen=True)
class _Stage:
    node_id: str
    label: str
    config: str
    artifact_kind: str
    required_files: tuple[str, ...]


_STAGES = (
    _Stage(
        "scenario",
        "构造环境",
        REQUIRED_AGENT_CONFIGS[0],
        "scenario",
        ("task_spec.yaml", "manifest.json"),
    ),
    _Stage(
        "method",
        "选择方法",
        REQUIRED_AGENT_CONFIGS[1],
        "policy",
        ("policy.py", "metadata.json", "manifest.json"),
    ),
    _Stage(
        "run",
        "运行实验",
        REQUIRED_AGENT_CONFIGS[2],
        "experiment",
        ("agent_result.json", "report.md", "manifest.json"),
    ),
)


class AgentRuntimeUnavailable(RuntimeError):
    def __init__(self, message: str, status: dict[str, Any]) -> None:
        super().__init__(message)
        self.status = status


class _ExecutionPaused(RuntimeError):
    pass


class _ExecutionStopped(RuntimeError):
    pass


class ProjectExecutor:
    """Run workbench projects in persistent Codex SDK threads."""

    def __init__(
        self,
        project_root: Path,
        workbench: WorkbenchStore,
        *,
        enabled: bool = True,
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.workbench = workbench
        self.enabled = enabled
        self._workers: dict[str, threading.Thread] = {}
        self._turns: dict[str, Any] = {}
        self._lock = threading.Lock()

    def status(self) -> dict[str, Any]:
        missing_configs = [
            relative
            for relative in REQUIRED_AGENT_CONFIGS
            if not (self.project_root / relative).is_file()
        ]
        sdk_available = importlib.util.find_spec("openai_codex") is not None
        runtime_connected = bool(
            self.enabled and sdk_available and not missing_configs
        )
        status = {
            "ready": runtime_connected,
            "enabled": self.enabled,
            "sdk_available": sdk_available,
            "runtime_connected": runtime_connected,
            "missing_configs": missing_configs,
            "fallback_enabled": False,
            "runtime": "codex-sdk" if sdk_available else None,
        }
        if runtime_connected:
            status["message"] = "Codex Agent 已就绪"
        elif not self.enabled:
            status["message"] = "工作台 Agent 执行已关闭"
        elif missing_configs:
            status["message"] = "缺少 Agent 配置：" + ", ".join(missing_configs)
        else:
            status["message"] = "未安装 Codex Python SDK（openai-codex）"
        return status

    def require_ready(self) -> dict[str, Any]:
        status = self.status()
        if status["ready"]:
            return status
        reasons: list[str] = []
        if not self.enabled:
            reasons.append("工作台 Agent 执行已关闭")
        if status["missing_configs"]:
            reasons.append(
                "缺少 Agent 配置：" + ", ".join(status["missing_configs"])
            )
        if not status["sdk_available"]:
            reasons.append("未安装 Codex Python SDK（openai-codex）")
        reasons.append("M1 固定规则回退已禁用")
        raise AgentRuntimeUnavailable("Agent 无法启动：" + "；".join(reasons), status)

    def start(self, project_id: str) -> bool:
        self.require_ready()
        with self._lock:
            current = self._workers.get(project_id)
            if current is not None and current.is_alive():
                return False
            worker = threading.Thread(
                target=self._run,
                args=(project_id,),
                name=f"autogame-agent-{project_id}",
                daemon=True,
            )
            self._workers[project_id] = worker
            worker.start()
        return True

    def resume_pending(self) -> None:
        if not self.status()["ready"]:
            return
        for project in self.workbench.list_local_projects():
            if project.get("status") == "active":
                self.start(str(project["project_id"]))

    def intervene(self, project_id: str, action: str, details: dict[str, Any]) -> None:
        if action == "resume":
            self.workbench.update_project(project_id, status="active", error=None)
            self.start(project_id)
            return
        with self._lock:
            turn = self._turns.get(project_id)
        if turn is None:
            return
        if action in {"pause", "stop"}:
            turn.interrupt()
            return
        if action in {"message", "change_method", "adjust_budget"}:
            turn.steer(_intervention_prompt(action, details))

    def _run(self, project_id: str) -> None:
        project = self.workbench.load_local_project(project_id)
        if project is None:
            return
        try:
            self.workbench.update_project(project_id, status="active", error=None)
            self._check_control(project_id)
            self._run_codex(project_id)
        except _ExecutionPaused:
            self.workbench.update_project(project_id, status="paused")
            self._event(project_id, "execution.paused", {})
        except _ExecutionStopped:
            self.workbench.update_project(project_id, status="stopped")
            self._event(project_id, "execution.stopped", {})
        except Exception as error:  # background task boundary
            message = str(error).strip() or type(error).__name__
            self.workbench.update_project(project_id, status="error", error=message)
            self._event(
                project_id,
                "execution.failed",
                {"message": _truncate(message, 1_000)},
            )
        finally:
            with self._lock:
                self._turns.pop(project_id, None)
                self._workers.pop(project_id, None)

    def _run_codex(self, project_id: str) -> None:
        from openai_codex import ApprovalMode, Codex, CodexConfig, Sandbox

        project = self.workbench.load_local_project(project_id)
        if project is None:
            raise ValueError(f"unknown local project: {project_id}")
        instructions = self._developer_instructions()
        config = CodexConfig(cwd=str(self.project_root))
        with Codex(config) as codex:
            existing_thread_id = project.get("agent_thread_id")
            if isinstance(existing_thread_id, str) and existing_thread_id:
                thread = codex.thread_resume(
                    existing_thread_id,
                    approval_mode=ApprovalMode.auto_review,
                    cwd=str(self.project_root),
                    developer_instructions=instructions,
                    sandbox=Sandbox.workspace_write,
                )
                self._event(
                    project_id,
                    "execution.thread_resumed",
                    {"thread_id": thread.id},
                )
            else:
                thread = codex.thread_start(
                    approval_mode=ApprovalMode.auto_review,
                    cwd=str(self.project_root),
                    developer_instructions=instructions,
                    sandbox=Sandbox.workspace_write,
                )
                thread.set_name(f"AutoGame · {project.get('title', project_id)}")
                self.workbench.update_project(project_id, agent_thread_id=thread.id)
                self._event(
                    project_id,
                    "execution.thread_started",
                    {"thread_id": thread.id},
                )

            for stage in _STAGES:
                self._check_control(project_id)
                artifact = self._artifact_path(project_id, stage.artifact_kind)
                if self._artifact_complete(artifact, stage.required_files):
                    self._record_artifact(project_id, stage.artifact_kind, artifact)
                    if not self._node_completed(project_id, stage.node_id):
                        self._event(
                            project_id,
                            "node.completed",
                            {"node_id": stage.node_id, "reused": True},
                        )
                    continue
                self._event(
                    project_id,
                    "node.entered",
                    {"node_id": stage.node_id, "label": stage.label},
                )
                artifact.mkdir(parents=True, exist_ok=True)
                self._run_turn(
                    project_id,
                    thread,
                    stage,
                    self._stage_prompt(project, stage, artifact),
                    Sandbox.workspace_write,
                    ApprovalMode.auto_review,
                )
                self._check_control(project_id)
                self._validate_artifact(stage, artifact)
                self._record_artifact(project_id, stage.artifact_kind, artifact)
                self._event(
                    project_id,
                    "node.completed",
                    {"node_id": stage.node_id},
                )

            self._finish(project_id)

    def _run_turn(
        self,
        project_id: str,
        thread: Any,
        stage: _Stage,
        prompt: str,
        sandbox: Any,
        approval_mode: Any,
    ) -> None:
        turn = thread.turn(
            prompt,
            approval_mode=approval_mode,
            cwd=str(self._artifact_path(project_id, stage.artifact_kind)),
            effort="medium",  # type: ignore[arg-type] - SDK enum is not public
            sandbox=sandbox,
        )
        self.workbench.update_project(project_id, active_turn_id=turn.id)
        with self._lock:
            self._turns[project_id] = turn
        self._event(
            project_id,
            "execution.turn_started",
            {"node_id": stage.node_id, "turn_id": turn.id},
        )
        completed: Any | None = None
        try:
            for notification in turn.stream():
                payload = notification.payload
                if notification.method in {"item/started", "item/completed"}:
                    item = getattr(payload, "item", None)
                    self._record_item(project_id, stage.node_id, item)
                elif notification.method == "turn/completed":
                    completed = getattr(payload, "turn", None)
        finally:
            with self._lock:
                self._turns.pop(project_id, None)
            self.workbench.update_project(project_id, active_turn_id=None)

        self._check_control(project_id)
        if completed is None:
            raise RuntimeError(f"{stage.label}未收到 Codex 完成事件")
        status = _enum_value(getattr(completed, "status", None))
        if status == "interrupted":
            self._check_control(project_id)
            raise RuntimeError(f"{stage.label}被中断")
        if status != "completed":
            error = getattr(completed, "error", None)
            message = getattr(error, "message", None)
            raise RuntimeError(message or f"{stage.label}执行失败：{status}")
        self._event(
            project_id,
            "execution.turn_completed",
            {
                "node_id": stage.node_id,
                "turn_id": turn.id,
                "duration_ms": getattr(completed, "duration_ms", None),
            },
        )

    def _record_item(self, project_id: str, node_id: str, wrapped: Any) -> None:
        item = getattr(wrapped, "root", wrapped)
        item_type = getattr(item, "type", None)
        if item_type == "agentMessage":
            text = str(getattr(item, "text", "")).strip()
            if text:
                self._event(
                    project_id,
                    "execution.agent_message",
                    {"node_id": node_id, "text": _truncate(text, 800)},
                )
            return
        if item_type == "commandExecution":
            self._event(
                project_id,
                "execution.activity",
                {
                    "node_id": node_id,
                    "kind": "command",
                    "command": _truncate(str(getattr(item, "command", "")), 500),
                    "status": _enum_value(getattr(item, "status", None)),
                    "exit_code": getattr(item, "exit_code", None),
                    "duration_ms": getattr(item, "duration_ms", None),
                },
            )
            return
        if item_type == "fileChange":
            paths = [
                str(getattr(change, "path", ""))
                for change in getattr(item, "changes", [])
                if getattr(change, "path", None)
            ]
            self._event(
                project_id,
                "execution.activity",
                {
                    "node_id": node_id,
                    "kind": "files",
                    "paths": paths[:20],
                    "status": _enum_value(getattr(item, "status", None)),
                },
            )

    def _finish(self, project_id: str) -> None:
        self._event(project_id, "node.entered", {"node_id": "evaluate"})
        result_path = self._artifact_path(project_id, "experiment") / "agent_result.json"
        result = read_json(result_path)
        _validate_agent_result(result, project_id)
        objective_status = str(result["objective_status"])
        summary = str(result["summary"])
        self.workbench.update_project(
            project_id,
            status="complete",
            outcome=objective_status,
            agent_summary=summary,
        )
        self._event(
            project_id,
            "node.completed",
            {"node_id": "evaluate", "objective_status": objective_status},
        )
        self._event(
            project_id,
            "execution.completed",
            {
                "execution_status": "completed",
                "objective_status": objective_status,
                "summary": _truncate(summary, 1_000),
            },
        )

    def _developer_instructions(self) -> str:
        sections = [
            """# AutoGame Workbench Orchestrator

You are the execution runtime behind an experiment workbench. Work autonomously, but keep every action auditable through real commands and files. Never use or recreate an M1 fixed-rule fallback. Workflow completion is not evidence that the user's objective was met. Only write inside the exact stage directory named by the current prompt; do not edit src/, tests/, .codex/, existing scenarios, policies, experiments, or workbench state. Do not expose private reasoning; report actions, evidence, results, and limitations."""
        ]
        for relative in REQUIRED_AGENT_CONFIGS:
            with (self.project_root / relative).open("rb") as handle:
                data = tomllib.load(handle)
            instructions = data.get("developer_instructions")
            if not isinstance(instructions, str) or not instructions.strip():
                raise ValueError(f"Agent 配置缺少 developer_instructions：{relative}")
            sections.append(instructions.strip())
        return "\n\n---\n\n".join(sections)

    def _stage_prompt(
        self, project: dict[str, Any], stage: _Stage, artifact: Path
    ) -> str:
        project_id = str(project["project_id"])
        output = artifact.relative_to(self.project_root).as_posix()
        prior = self.workbench.list_events(project_id)
        interventions = [
            event
            for event in prior
            if str(event.get("event_type", "")).startswith("human.")
        ][-12:]
        context = json.dumps(interventions, ensure_ascii=False, separators=(",", ":"))
        shared = f"""仓库根目录：{self.project_root}
项目 ID：{project_id}
项目标题：{project.get('title', '')}
用户目标：{project.get('goal', '')}
当前阶段：{stage.label}
当前工作目录即本阶段唯一允许写入的目录：{artifact}
面向产品记录的相对产物路径：{output}/
项目 Python 解释器：{self.project_root / '.venv/bin/python'}（存在时优先使用，不要调用系统旧版 python3）
最近的人类干预：{context}

请把本阶段文件直接写入当前工作目录，不要在其中再次创建 {output}/。只能读取仓库其他内容；不得修改当前工作目录之外的任何文件。必须执行实际验证命令，并在最终答复中简洁报告产生的文件、运行的命令、证据和限制。若无法诚实完成，明确失败原因，不得用演示数据或固定规则替代。"""
        if stage.node_id == "scenario":
            return shared + f"""

请作为 Scenario Researcher 完成本阶段。场景 ID 必须为 {project_id}-scenario。把用户目标编译成最小但真实、可复现、可测试的场景包；不得默认穿环或 drone_ring_game。至少生成 task_spec.yaml、env_config.yaml、assumptions.md、manifest.json、可运行 runtime 绑定/实现和目标相关测试。"""
        if stage.node_id == "method":
            scenario_path = self._artifact_path(project_id, "scenario")
            scenario = scenario_path.relative_to(self.project_root).as_posix()
            return shared + f"""

请作为 Method Researcher 完成本阶段。先读取冻结场景 {scenario_path}（记录路径 {scenario}/）。策略 ID 必须为 {project_id}-policy。比较可行方法后动态选择，并实现真实可运行的 Baseline/Candidate；不得复制 rule_ring_nav 或使用 no-op 训练伪装学习。至少生成 policy.py、metadata.json、manifest.json、配置、算法卡和真实 smoke/契约测试。"""
        scenario_path = self._artifact_path(project_id, "scenario")
        policy_path = self._artifact_path(project_id, "policy")
        scenario = scenario_path.relative_to(self.project_root).as_posix()
        policy = policy_path.relative_to(self.project_root).as_posix()
        return shared + f"""

请作为 Experiment Researcher 完成本阶段。冻结输入为 {scenario_path} 与 {policy_path}（记录路径 {scenario}/ 与 {policy}/）。在合理的小预算内真实运行相同条件下的 Baseline/Candidate，严禁手写指标。至少生成 agent_result.json、report.md、manifest.json、leaderboard.csv、baseline_metrics.json、best_config.yaml 和实际 trial 日志。

agent_result.json 必须是合法 JSON，严格包含：
{{
  "schema_version": "autogame_agent_result/v1",
  "project_id": "{project_id}",
  "execution_status": "completed",
  "objective_status": "met|not_met|inconclusive|blocked",
  "summary": "面向人的真实结论",
  "method": {{"name": "...", "family": "...", "policy_id": "{project_id}-policy", "selection_rationale": "..."}},
  "primary_metric": "指标名或 null",
  "comparison": {{"baseline_mean": "number|null", "candidate_mean": "number|null", "delta": "number|null", "constraints_passed": "boolean|null", "promoted": "boolean|null"}},
  "metric_series": {{"baseline": [{{"step": 0, "time": 0, "value": 0.0}}], "candidate": [{{"step": 0, "time": 0, "value": 0.0}}]}},
  "constraint_evidence": [],
  "failed_seeds": [],
  "artifacts": {{"scenario": "{scenario}", "policy": "{policy}", "experiment": "{output}", "report": "{output}/report.md"}},
  "commands": [],
  "limitations": []
}}
没有真实数据时用 null 或空数组，不能伪造。objective_status 依据用户原目标而不是流程是否跑完；预算内未达成应写 not_met，能力/依赖阻塞写 blocked，证据不足写 inconclusive。"""

    def _artifact_path(self, project_id: str, kind: str) -> Path:
        base = {"scenario": "scenarios", "policy": "policies", "experiment": "experiments"}[kind]
        suffix = {"scenario": "scenario", "policy": "policy", "experiment": "experiment"}[kind]
        return self.project_root / base / f"{project_id}-{suffix}"

    def _validate_artifact(self, stage: _Stage, artifact: Path) -> None:
        missing = [name for name in stage.required_files if not (artifact / name).is_file()]
        if missing:
            raise RuntimeError(
                f"{stage.label}没有产生必需文件：" + ", ".join(missing)
            )
        if stage.artifact_kind == "experiment":
            _validate_agent_result(
                read_json(artifact / "agent_result.json"),
                artifact.name.removesuffix("-experiment"),
            )

    @staticmethod
    def _artifact_complete(artifact: Path, required: tuple[str, ...]) -> bool:
        return artifact.is_dir() and all((artifact / name).is_file() for name in required)

    def _record_artifact(self, project_id: str, kind: str, artifact: Path) -> None:
        project = self.workbench.load_local_project(project_id) or {}
        artifacts = project.get("artifacts", {})
        artifacts = dict(artifacts) if isinstance(artifacts, dict) else {}
        relative = artifact.relative_to(self.project_root).as_posix()
        artifacts[kind] = relative
        self.workbench.update_project(project_id, artifacts=artifacts)
        self._event(
            project_id,
            "artifact.produced",
            {"kind": kind, "path": relative},
        )

    def _node_completed(self, project_id: str, node_id: str) -> bool:
        return any(
            event.get("event_type") == "node.completed"
            and isinstance(event.get("payload"), dict)
            and event["payload"].get("node_id") == node_id
            for event in self.workbench.list_events(project_id)
        )

    def _check_control(self, project_id: str) -> None:
        state = self.workbench.control_state(project_id)
        if state == "pause":
            raise _ExecutionPaused
        if state == "stop":
            raise _ExecutionStopped

    def _event(self, project_id: str, event_type: str, payload: dict[str, Any]) -> None:
        self.workbench.append_system_event(project_id, event_type, payload)


def _validate_agent_result(result: dict[str, Any], project_id: str) -> None:
    if result.get("schema_version") != "autogame_agent_result/v1":
        raise ValueError("agent_result.json schema_version 无效")
    if result.get("project_id") != project_id:
        raise ValueError("agent_result.json project_id 不匹配")
    if result.get("execution_status") != "completed":
        raise ValueError("agent_result.json execution_status 必须为 completed")
    if result.get("objective_status") not in {
        "met",
        "not_met",
        "inconclusive",
        "blocked",
    }:
        raise ValueError("agent_result.json objective_status 无效")
    if not isinstance(result.get("summary"), str) or not result["summary"].strip():
        raise ValueError("agent_result.json 缺少 summary")
    for key in ("method", "comparison", "metric_series", "artifacts"):
        if not isinstance(result.get(key), dict):
            raise ValueError(f"agent_result.json {key} 必须是对象")
    for key in ("constraint_evidence", "failed_seeds", "commands", "limitations"):
        if not isinstance(result.get(key), list):
            raise ValueError(f"agent_result.json {key} 必须是数组")


def _intervention_prompt(action: str, details: dict[str, Any]) -> str:
    labels = {
        "message": "人类补充信息",
        "change_method": "人类要求调整方法",
        "adjust_budget": "人类要求调整预算",
    }
    payload = json.dumps(details, ensure_ascii=False, separators=(",", ":"))
    return f"{labels[action]}：{payload}\n请立即纳入当前工作，并在可审计结果中说明影响。"


def _enum_value(value: Any) -> str | None:
    if value is None:
        return None
    return str(getattr(value, "value", value))


def _truncate(value: str, maximum: int) -> str:
    value = value.strip()
    return value if len(value) <= maximum else value[: maximum - 1] + "…"
