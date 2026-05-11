from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from game_agent.scenario_compiler.templates import (
    SCENARIO_ENV_PY,
    assumptions_md,
    model_md,
    obs_action_shape_test_py,
    reset_deterministic_test_py,
)
from game_agent.utils.fs import ensure_empty_output_dir, write_json, write_yaml
from game_agent.utils.manifest import build_manifest

_CHINESE_NUMBERS = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5}
_FORMALISM_POSG_TERMS = ("对抗", "追击", "拦截", "红蓝", "局部")


@dataclass(frozen=True)
class ParsedScenario:
    ring_count: int
    max_steps: int
    communication: dict[str, Any]
    formalism: str
    assumptions: list[str]


class ScenarioCompiler:
    def __init__(self, project_root: Path) -> None:
        self.project_root = Path(project_root)

    def compile(self, task_text: str, task_id: str) -> Path:
        parsed = self._parse(task_text)
        scenario_dir = self.project_root / "scenarios" / task_id
        ensure_empty_output_dir(scenario_dir)

        spec = self._build_spec(task_id, parsed)
        write_yaml(scenario_dir / "task_spec.yaml", spec)
        write_yaml(scenario_dir / "env_config.yaml", spec["env_config"])
        (scenario_dir / "env.py").write_text(SCENARIO_ENV_PY, encoding="utf-8")
        (scenario_dir / "model.md").write_text(model_md(task_id, parsed.formalism), encoding="utf-8")
        (scenario_dir / "assumptions.md").write_text(assumptions_md(parsed.assumptions), encoding="utf-8")
        tests_dir = scenario_dir / "tests"
        tests_dir.mkdir(parents=True, exist_ok=True)
        (tests_dir / "test_reset_deterministic.py").write_text(reset_deterministic_test_py(), encoding="utf-8")
        (tests_dir / "test_obs_action_shape.py").write_text(obs_action_shape_test_py(), encoding="utf-8")
        write_json(scenario_dir / "manifest.json", build_manifest(scenario_dir, "scenario", task_id))
        return scenario_dir

    def _parse(self, task_text: str) -> ParsedScenario:
        assumptions: list[str] = []

        ring_count = self._extract_count(task_text)
        if ring_count is None:
            ring_count = 2
            assumptions.append("ring_count defaulted to 2 because no explicit ring count was provided.")

        max_steps = self._extract_max_steps(task_text)
        if max_steps is None:
            max_steps = 200
            assumptions.append("max_steps defaulted to 200 because no timeout step count was provided.")

        communication = self._extract_communication(task_text, assumptions)
        formalism = "POSG" if any(term in task_text for term in _FORMALISM_POSG_TERMS) else "MarkovGame"

        return ParsedScenario(
            ring_count=ring_count,
            max_steps=max_steps,
            communication=communication,
            formalism=formalism,
            assumptions=assumptions,
        )

    def _build_spec(self, task_id: str, parsed: ParsedScenario) -> dict[str, Any]:
        env_config = {
            "ring_count": parsed.ring_count,
            "max_steps": parsed.max_steps,
            "ring_radius": 0.45,
            "collision_radius": 0.25,
            "boundary": 10.0,
        }
        return {
            "schema_version": "1.0",
            "task_id": task_id,
            "task_family": "drone_ring_game",
            "formalism": parsed.formalism,
            "agents": [
                {"id": "red_0", "role": "runner"},
                {"id": "blue_0", "role": "interceptor"},
            ],
            "communication": parsed.communication,
            "observation_space": {
                "type": "box",
                "shape": [12],
                "dtype": "float32",
                "low": [-10.0] * 12,
                "high": [10.0] * 12,
            },
            "action_space": {
                "type": "box",
                "shape": [4],
                "dtype": "float32",
                "low": [-2.0, -2.0, -1.0, -1.0],
                "high": [2.0, 2.0, 1.0, 1.0],
                "semantics": "velocity_setpoint",
                "description": "[0] vx (m/s); [1] vy (m/s); [2] vz (m/s); [3] yaw_rate (rad/s).",
            },
            "reward_structure": {
                "components": [
                    {"name": "ring_progress", "agent": "red_0"},
                    {"name": "interception", "agent": "blue_0"},
                    {"name": "timeout_penalty", "agent": "red_0"},
                ]
            },
            "evaluation_metrics": {
                "primary": {
                    "name": "success_rate",
                    "direction": "maximize",
                    "description": "Fraction of episodes where red passes all rings.",
                },
                "secondary": [
                    {"name": "collision_rate", "direction": "minimize"},
                    {"name": "timeout_rate", "direction": "minimize"},
                    {"name": "episode_length", "direction": "minimize"},
                ],
                "hard_constraints": [
                    {"name": "collision_rate", "direction": "minimize", "max": 0.05},
                    {"name": "out_of_bounds_rate", "direction": "minimize", "max": 0.01},
                    {"name": "action_violation_rate", "direction": "minimize", "max": 0.0},
                ],
            },
            "termination_conditions": ["red_passes_all_rings", "blue_intercepts_red", "out_of_bounds"],
            "splits": {"train": {"episodes": 100}, "eval": {"episodes": 20}},
            "env_config": env_config,
        }

    def _extract_count(self, task_text: str) -> int | None:
        match = re.search(r"([一二两三四五]|\d+)\s*(?:个|道|只)?\s*(?:圆环|环)", task_text)
        if not match:
            return None
        return self._parse_number(match.group(1))

    def _extract_max_steps(self, task_text: str) -> int | None:
        timeout_match = re.search(r"(?:超时|timeout)\s*([一二两三四五]|\d+)\s*步", task_text, re.IGNORECASE)
        if timeout_match:
            value = self._parse_number(timeout_match.group(1))
            return value if value is not None and value >= 10 else None
        return None

    def _extract_communication(self, task_text: str, assumptions: list[str]) -> dict[str, Any]:
        if "延迟" in task_text:
            delay_steps = self._extract_delay_steps(task_text)
            if delay_steps is None:
                delay_steps = 1
                assumptions.append("communication.delay_steps defaulted to 1 because delay was mentioned without a step count.")
            return {"mode": "delayed", "delay_steps": delay_steps}
        if "丢包" in task_text:
            drop_probability = self._extract_drop_probability(task_text)
            if drop_probability is None:
                drop_probability = 0.1
                assumptions.append(
                    "communication.drop_probability defaulted to 0.1 because packet loss was mentioned without a rate."
                )
            return {"mode": "lossy", "drop_probability": drop_probability}
        assumptions.append("communication.mode defaulted to perfect because no communication condition was provided.")
        return {"mode": "perfect"}

    def _extract_delay_steps(self, task_text: str) -> int | None:
        match = re.search(r"延迟\s*([一二两三四五]|\d+)\s*步", task_text)
        if not match:
            return None
        return self._parse_number(match.group(1))

    def _extract_drop_probability(self, task_text: str) -> float | None:
        match = re.search(r"丢包\s*(\d+(?:\.\d+)?)\s*%", task_text)
        if not match:
            return None
        return float(match.group(1)) / 100.0

    def _parse_number(self, token: str) -> int | None:
        if token.isdigit():
            return int(token)
        return _CHINESE_NUMBERS.get(token)
