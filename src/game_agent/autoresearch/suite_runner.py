from __future__ import annotations

import csv
import json
import math
import time
from dataclasses import asdict
from pathlib import Path
from statistics import fmean, pstdev
from typing import Any

import numpy as np

from game_agent.scenarios import (
    CAPABILITY_COLUMNS,
    catalog_by_id,
    create_runtime,
)
from game_agent.utils.fs import read_json, read_yaml, write_json, write_yaml
from game_agent.utils.manifest import build_manifest
from game_agent.utils.policy_loader import load_policy


_CONSTRAINT_METRICS = (
    "collision_rate",
    "out_of_bounds_rate",
    "action_violation_rate",
)


def load_suite(suite_path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    suite = read_yaml(suite_path)
    errors = validate_suite(suite)
    if errors:
        raise ValueError("; ".join(errors))
    catalog = catalog_by_id()
    specs = [catalog[scenario_id] for scenario_id in suite["scenarios"]]
    max_steps = int(suite.get("budget", {}).get("max_steps", 48))
    for spec in specs:
        configured = int(spec["runtime_config"].get("max_steps", max_steps))
        spec["runtime_config"]["max_steps"] = min(configured, max_steps)
    return suite, specs


def validate_suite(suite: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if suite.get("schema_version") != "scenario_suite/v1":
        errors.append("schema_version must be scenario_suite/v1")
    if suite.get("catalog") != "max_space_50_v1":
        errors.append("catalog must be max_space_50_v1")
    scenario_ids = suite.get("scenarios")
    if not isinstance(scenario_ids, list) or not scenario_ids:
        errors.append("scenarios must be a non-empty list")
        return errors
    if len(scenario_ids) != len(set(scenario_ids)):
        errors.append("scenario ids must be unique")
    known = catalog_by_id()
    unknown = sorted(set(scenario_ids) - set(known))
    if unknown:
        errors.append(f"unknown scenarios: {', '.join(unknown)}")
    seeds = suite.get("seeds")
    if not isinstance(seeds, list) or not seeds or not all(
        isinstance(seed, int) for seed in seeds
    ):
        errors.append("seeds must be a non-empty integer list")
    replay_interval = suite.get("budget", {}).get("replay_interval", 4)
    if not isinstance(replay_interval, int) or replay_interval < 1:
        errors.append("budget.replay_interval must be a positive integer")
    return errors


class ScenarioSuiteRunner:
    """Execute independent reference evaluations for a frozen scenario suite."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = Path(project_root).resolve()

    def run(
        self,
        suite_path: Path,
        output_dir: Path,
        *,
        resume: bool = False,
    ) -> Path:
        suite_path = Path(suite_path).resolve()
        output_dir = Path(output_dir).resolve()
        suite, specs = load_suite(suite_path)
        self._prepare_output(output_dir, resume=resume)
        state = self._load_or_create_state(output_dir, suite, specs)
        seeds = [int(seed) for seed in suite["seeds"]]
        replay_interval = int(suite.get("budget", {}).get("replay_interval", 4))

        for spec in specs:
            scenario_id = spec["scenario_id"]
            existing = state["scenarios"].get(scenario_id, {})
            if resume and existing.get("status") in {"PASS", "FAIL"}:
                continue
            started = time.perf_counter()
            try:
                result = self._evaluate_scenario(
                    output_dir, spec, seeds, replay_interval
                )
                result["walltime_seconds"] = round(time.perf_counter() - started, 6)
                state["scenarios"][scenario_id] = result
            except Exception as error:  # isolate one scenario from the suite
                state["scenarios"][scenario_id] = {
                    "scenario_id": scenario_id,
                    "name": spec["name"],
                    "task_family": spec["task_family"],
                    "status": "ERROR",
                    "error": f"{type(error).__name__}: {error}",
                    "walltime_seconds": round(time.perf_counter() - started, 6),
                }
            state["completed_count"] = len(state["scenarios"])
            state["status"] = "RUNNING"
            write_json(output_dir / "state.json", _jsonable(state))

        self._write_aggregate_artifacts(output_dir, suite, specs, state)
        state["completed_count"] = len(state["scenarios"])
        state["status"] = "COMPLETE"
        write_json(output_dir / "state.json", _jsonable(state))
        write_json(
            output_dir / "manifest.json",
            build_manifest(output_dir, "scenario_suite_run", suite["suite_id"]),
        )
        return output_dir

    def render_existing(self, output_dir: Path) -> tuple[Path, ...]:
        output_dir = Path(output_dir).resolve()
        state = read_json(output_dir / "state.json")
        return self._render_figures(output_dir, state)

    @staticmethod
    def _prepare_output(output_dir: Path, *, resume: bool) -> None:
        if output_dir.exists() and not output_dir.is_dir():
            raise FileExistsError(f"output path is not a directory: {output_dir}")
        if output_dir.exists() and any(output_dir.iterdir()) and not resume:
            raise FileExistsError(f"refusing to overwrite non-empty output: {output_dir}")
        output_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _load_or_create_state(
        output_dir: Path,
        suite: dict[str, Any],
        specs: list[dict[str, Any]],
    ) -> dict[str, Any]:
        path = output_dir / "state.json"
        if path.exists():
            state = read_json(path)
            if state.get("suite_id") != suite["suite_id"]:
                raise ValueError("resume suite_id does not match existing state")
            return state
        state = {
            "schema_version": "scenario_suite_state/v1",
            "suite_id": suite["suite_id"],
            "status": "PENDING",
            "scenario_count": len(specs),
            "completed_count": 0,
            "scenarios": {},
        }
        write_json(path, state)
        return state

    def _evaluate_scenario(
        self,
        output_dir: Path,
        spec: dict[str, Any],
        seeds: list[int],
        replay_interval: int,
    ) -> dict[str, Any]:
        scenario_dir = output_dir / "scenarios" / spec["scenario_id"]
        scenario_dir.mkdir(parents=True, exist_ok=True)
        write_yaml(scenario_dir / "spec.yaml", spec)
        descriptor_runtime = create_runtime(spec)
        try:
            descriptor = descriptor_runtime.describe()
        finally:
            descriptor_runtime.close()
        descriptor_data = _jsonable(asdict(descriptor))
        visualization = descriptor_data.get("visualization")
        if not isinstance(visualization, dict):
            raise ValueError(
                f"{spec['scenario_id']} runtime does not declare a visualization spec"
            )
        write_json(scenario_dir / "descriptor.json", descriptor_data)
        write_yaml(scenario_dir / "visualization.yaml", visualization)
        outcomes: dict[str, dict[str, Any]] = {}
        replay_entries: list[dict[str, Any]] = []
        policy_ids = {
            "baseline": str(spec["baseline_policy_id"]),
            "candidate": str(spec["candidate_policy_id"]),
        }
        policy_binding: dict[str, Any] = {
            "schema_version": "suite_policy_binding/v1",
            "scenario_id": spec["scenario_id"],
            "policies": {},
        }
        for policy_role, policy_id in policy_ids.items():
            policy_dir = self.project_root / "policies" / policy_id
            manifest = read_json(policy_dir / "manifest.json")
            metadata = read_json(policy_dir / "metadata.json")
            policy_binding["policies"][policy_role] = {
                "policy_id": policy_id,
                "freeze_hash": manifest["freeze_hash"],
                "method": metadata["method"],
            }
        write_json(scenario_dir / "policy_binding.json", policy_binding)
        for policy_name, policy_id in policy_ids.items():
            per_seed: list[dict[str, Any]] = []
            for seed in seeds:
                episode = self._run_episode(
                    spec, seed, policy_id, policy_name, replay_interval
                )
                per_seed.append(episode["metrics"])
                replay_path = Path("replays") / f"{policy_name}_seed_{seed}.json"
                write_json(
                    scenario_dir / replay_path,
                    episode,
                )
                frames = episode.get("frames", [])
                replay_entries.append(
                    {
                        "policy_role": policy_name,
                        "policy_id": policy_id,
                        "seed": seed,
                        "path": replay_path.as_posix(),
                        "frame_count": len(frames),
                        "duration": _replay_duration(frames),
                    }
                )
            outcomes[policy_name] = _aggregate_metrics(per_seed)
            write_json(
                scenario_dir / f"{policy_name}_metrics.json",
                outcomes[policy_name],
            )

        write_json(
            scenario_dir / "replay_index.json",
            {
                "schema_version": "scenario_replay_index/v1",
                "scenario_id": spec["scenario_id"],
                "descriptor": "descriptor.json",
                "visualization": "visualization.yaml",
                "replays": replay_entries,
            },
        )

        primary = spec["primary_metric"]
        baseline_mean = outcomes["baseline"]["statistics"][primary]["mean"]
        candidate_mean = outcomes["candidate"]["statistics"][primary]["mean"]
        constraints_passed = all(
            outcomes["candidate"]["statistics"][metric]["mean"] <= 0.0
            for metric in _CONSTRAINT_METRICS
        )
        promoted = bool(candidate_mean > baseline_mean + 1e-9 and constraints_passed)
        comparison = {
            "scenario_id": spec["scenario_id"],
            "primary_metric": primary,
            "metric_direction": spec["metric_direction"],
            "baseline_mean": baseline_mean,
            "candidate_mean": candidate_mean,
            "delta": candidate_mean - baseline_mean,
            "constraints_passed": constraints_passed,
            "promoted": promoted,
            "promotion_rule": "strict primary improvement and zero candidate constraint violations",
            "evaluation_kind": "explicit_policy_package_evaluation",
            "baseline_policy_id": policy_ids["baseline"],
            "candidate_policy_id": policy_ids["candidate"],
        }
        write_json(scenario_dir / "comparison.json", comparison)
        return {
            "scenario_id": spec["scenario_id"],
            "name": spec["name"],
            "task_family": spec["task_family"],
            "primary_metric": primary,
            "baseline_mean": baseline_mean,
            "candidate_mean": candidate_mean,
            "delta": comparison["delta"],
            "constraints_passed": constraints_passed,
            "promoted": promoted,
            "baseline_policy_id": policy_ids["baseline"],
            "candidate_policy_id": policy_ids["candidate"],
            "status": "PASS",
        }

    def _run_episode(
        self,
        spec: dict[str, Any],
        seed: int,
        policy_id: str,
        policy_role: str,
        replay_interval: int,
    ) -> dict[str, Any]:
        runtime = create_runtime(spec)
        descriptor = runtime.describe()
        first_agent = descriptor.agents[0]
        env_spec = {
            "scenario_id": spec["scenario_id"],
            "task_family": spec["task_family"],
            "scenario": spec,
            "action_space": descriptor.action_spaces[first_agent],
            "observation_space": descriptor.observation_spaces[first_agent],
        }
        policy, policy_config = load_policy(
            self.project_root / "policies" / policy_id,
            env_spec,
        )
        policy.reset(seed)
        observations, reset_info = runtime.reset(seed=seed)
        runtime_info = reset_info
        policy_info: dict[str, Any] = {"episode_step": 0}
        initial_observation_agents = sorted(observations)
        frames = [_jsonable(asdict(runtime.snapshot()))]
        events = list(reset_info.get("events", []))
        try:
            for _ in range(int(spec["runtime_config"]["max_steps"])):
                actions = {
                    agent: policy.act(observations, agent, policy_info)
                    for agent in runtime.agents
                }
                observations, _, terminations, truncations, runtime_info = runtime.step(
                    actions
                )
                events.extend(runtime_info.get("events", []))
                done = (
                    (bool(terminations) and all(terminations.values()))
                    or (bool(truncations) and all(truncations.values()))
                    or not runtime.agents
                )
                step_number = int(runtime.get_metrics()["episode_length"])
                policy_info = {"episode_step": step_number}
                if step_number % replay_interval == 0 or done:
                    frames.append(_jsonable(asdict(runtime.snapshot())))
                if done:
                    break
            metrics = _jsonable(runtime.get_metrics())
            return {
                "schema_version": "scenario_replay/v2",
                "scenario_id": spec["scenario_id"],
                "descriptor_ref": "../descriptor.json",
                "visualization_ref": "../visualization.yaml",
                "seed": seed,
                "policy": policy_role,
                "policy_id": policy_id,
                "policy_config": policy_config,
                "policy_information_boundary": [
                    "per-agent execution observation",
                    "episode_step",
                ],
                "evaluation_kind": "explicit_policy_package_evaluation",
                "initial_observation_agents": initial_observation_agents,
                "frames": frames,
                "events": _jsonable(events),
                "metrics": metrics,
                "disclosures": list(spec["disclosures"]),
            }
        finally:
            runtime.close()

    def _write_aggregate_artifacts(
        self,
        output_dir: Path,
        suite: dict[str, Any],
        specs: list[dict[str, Any]],
        state: dict[str, Any],
    ) -> None:
        ordered = [state["scenarios"].get(spec["scenario_id"], {}) for spec in specs]
        fieldnames = (
            "scenario_id",
            "name",
            "task_family",
            "baseline_policy_id",
            "candidate_policy_id",
            "primary_metric",
            "baseline_mean",
            "candidate_mean",
            "delta",
            "constraints_passed",
            "promoted",
            "status",
            "walltime_seconds",
            "error",
        )
        _write_csv(output_dir / "scenario_results.csv", ordered, fieldnames)
        coverage_rows = []
        for spec in specs:
            coverage_rows.append(
                {
                    "scenario_id": spec["scenario_id"],
                    "task_family": spec["task_family"],
                    **{
                        capability: int(bool(spec["capabilities"].get(capability)))
                        for capability in CAPABILITY_COLUMNS
                    },
                }
            )
        _write_csv(
            output_dir / "coverage_matrix.csv",
            coverage_rows,
            ("scenario_id", "task_family", *CAPABILITY_COLUMNS),
        )
        pass_count = sum(item.get("status") == "PASS" for item in ordered)
        promoted_count = sum(bool(item.get("promoted")) for item in ordered)
        error_count = sum(item.get("status") == "ERROR" for item in ordered)
        summary = {
            "schema_version": "scenario_suite_summary/v1",
            "suite_id": suite["suite_id"],
            "evaluation_kind": "explicit_policy_package_evaluation",
            "scenario_count": len(specs),
            "policy_package_count": len(
                {
                    policy_id
                    for spec in specs
                    for policy_id in (
                        spec["baseline_policy_id"],
                        spec["candidate_policy_id"],
                    )
                }
            ),
            "execution_pass_count": pass_count,
            "execution_error_count": error_count,
            "candidate_promoted_count": promoted_count,
            "all_scenarios_executed": pass_count == len(specs),
            "all_constraints_passed": all(
                bool(item.get("constraints_passed")) for item in ordered
            ),
            "disclosures": [
                "本次执行验证 50 类场景的统一协议、确定性评估、证据落盘与可视化链路。",
                "本次不是 50 次强化学习训练；baseline 与 candidate 均来自显式冻结 policy 包。",
                "S10/S50 使用本地 loopback adapter，S49 使用合成 8×8 图像观测。",
            ],
        }
        write_json(output_dir / "summary.json", summary)
        self._write_report(output_dir, summary, ordered)
        self._render_figures(output_dir, state)

    @staticmethod
    def _write_report(
        output_dir: Path,
        summary: dict[str, Any],
        ordered: list[dict[str, Any]],
    ) -> None:
        rows = [
            "# 最大场景空间 50 任务执行报告",
            "",
            "## 结论",
            "",
            f"- 执行通过：{summary['execution_pass_count']}/{summary['scenario_count']}",
            f"- 执行错误：{summary['execution_error_count']}",
            f"- 显式策略包：{summary['policy_package_count']}",
            f"- 候选参考策略晋级：{summary['candidate_promoted_count']}/{summary['scenario_count']}",
            f"- 约束全部通过：{'是' if summary['all_constraints_passed'] else '否'}",
            "",
            "## 证据边界",
            "",
        ]
        rows.extend(f"- {item}" for item in summary["disclosures"])
        rows.extend(
            [
                "",
                "## 场景结果",
                "",
                "| ID | 场景 | 执行 | 基线 | 候选 | 差值 | 晋级 |",
                "|---|---|---:|---:|---:|---:|---:|",
            ]
        )
        for item in ordered:
            rows.append(
                "| {scenario_id} | {name} | {status} | {baseline} | {candidate} | {delta} | {promoted} |".format(
                    scenario_id=item.get("scenario_id", "?"),
                    name=item.get("name", "?"),
                    status=item.get("status", "MISSING"),
                    baseline=_format_number(item.get("baseline_mean")),
                    candidate=_format_number(item.get("candidate_mean")),
                    delta=_format_number(item.get("delta")),
                    promoted="是" if item.get("promoted") else "否",
                )
            )
        (output_dir / "report.md").write_text("\n".join(rows) + "\n", encoding="utf-8")

    @staticmethod
    def _render_figures(output_dir: Path, state: dict[str, Any]) -> tuple[Path, ...]:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        scenario_items = sorted(
            state.get("scenarios", {}).values(), key=lambda item: item["scenario_id"]
        )
        ids = [item["scenario_id"] for item in scenario_items]
        baseline = [float(item.get("baseline_mean", math.nan)) for item in scenario_items]
        candidate = [float(item.get("candidate_mean", math.nan)) for item in scenario_items]
        figures_dir = output_dir / "figures"
        figures_dir.mkdir(parents=True, exist_ok=True)

        fig, axis = plt.subplots(figsize=(18, 7))
        x = np.arange(len(ids))
        axis.plot(x, baseline, color="#9ca3af", linewidth=1.4, marker="o", markersize=3, label="baseline")
        axis.plot(x, candidate, color="#2563eb", linewidth=1.5, marker="o", markersize=3, label="candidate")
        axis.fill_between(x, baseline, candidate, color="#93c5fd", alpha=0.22)
        axis.set_xticks(x)
        axis.set_xticklabels(ids, rotation=90)
        axis.set_ylim(-0.03, 1.05)
        axis.set_ylabel("normalized primary metric")
        axis.set_title("50-scenario explicit-policy evaluation")
        axis.grid(axis="y", alpha=0.25)
        axis.legend()
        fig.tight_layout()
        result_path = figures_dir / "scenario_results_overview.png"
        fig.savefig(result_path, dpi=160)
        plt.close(fig)

        catalog = catalog_by_id()
        matrix = np.array(
            [
                [int(bool(catalog[item_id]["capabilities"].get(column))) for column in CAPABILITY_COLUMNS]
                for item_id in ids
            ],
            dtype=float,
        )
        fig, axis = plt.subplots(figsize=(13, 15))
        image = axis.imshow(matrix, aspect="auto", cmap="Blues", vmin=0, vmax=1)
        axis.set_xticks(np.arange(len(CAPABILITY_COLUMNS)))
        axis.set_xticklabels(CAPABILITY_COLUMNS, rotation=45, ha="right")
        axis.set_yticks(np.arange(len(ids)))
        axis.set_yticklabels(ids)
        axis.set_title("Scenario capability coverage matrix")
        fig.colorbar(image, ax=axis, fraction=0.02, pad=0.02, ticks=[0, 1])
        fig.tight_layout()
        coverage_path = figures_dir / "coverage_matrix.png"
        fig.savefig(coverage_path, dpi=160)
        plt.close(fig)

        manifest = {
            "schema_version": "visualization_manifest/v1",
            "figures": [
                {"path": result_path.relative_to(output_dir).as_posix(), "kind": "suite_results"},
                {"path": coverage_path.relative_to(output_dir).as_posix(), "kind": "capability_coverage"},
            ],
        }
        write_json(figures_dir / "visualization_manifest.json", manifest)
        return result_path, coverage_path


def _aggregate_metrics(per_seed: list[dict[str, Any]]) -> dict[str, Any]:
    metric_names = sorted(
        {
            key
            for metrics in per_seed
            for key, value in metrics.items()
            if isinstance(value, (bool, int, float))
        }
    )
    statistics: dict[str, dict[str, float]] = {}
    for metric in metric_names:
        values = [float(metrics[metric]) for metrics in per_seed]
        statistics[metric] = {
            "mean": fmean(values),
            "std": pstdev(values) if len(values) > 1 else 0.0,
            "min": min(values),
            "max": max(values),
        }
    primary_name = str(per_seed[0]["primary_metric"])
    if primary_name not in statistics:
        primary_values = [float(metrics["primary_value"]) for metrics in per_seed]
        statistics[primary_name] = {
            "mean": fmean(primary_values),
            "std": pstdev(primary_values) if len(primary_values) > 1 else 0.0,
            "min": min(primary_values),
            "max": max(primary_values),
        }
    return {"per_seed": per_seed, "statistics": statistics}


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: tuple[str, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def _jsonable(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _replay_duration(frames: Any) -> float:
    if not isinstance(frames, list) or not frames:
        return 0.0
    first = frames[0] if isinstance(frames[0], dict) else {}
    last = frames[-1] if isinstance(frames[-1], dict) else {}
    return round(
        max(
            0.0,
            float(last.get("scenario_time", 0.0))
            - float(first.get("scenario_time", 0.0)),
        ),
        6,
    )


def _format_number(value: Any) -> str:
    return "—" if value is None else f"{float(value):.4f}"
