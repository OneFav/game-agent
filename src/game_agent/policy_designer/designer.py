from __future__ import annotations

from pathlib import Path
from typing import Any

from game_agent.policy_designer.templates import (
    ACTION_BOUNDS_TEST_PY,
    INFER_PY,
    INFERENCE_LATENCY_TEST_PY,
    POLICY_INTERFACE_TEST_PY,
    POLICY_PY,
    SMOKE_ROLLOUT_TEST_PY,
    TRAIN_PY,
    algorithm_card,
)
from game_agent.utils.fs import ensure_empty_output_dir, read_yaml, write_json, write_yaml
from game_agent.utils.manifest import build_manifest

DEFAULT_CONFIG: dict[str, Any] = {
    "policy_type": "rule_ring_navigation",
    "speed_scale": 1.0,
    "intercept_gain": 1.0,
    "safety_margin": 0.2,
}

SEARCH_SPACE: dict[str, Any] = {
    "parameters": {
        "speed_scale": {"values": [0.8, 1.0, 1.2]},
        "intercept_gain": {"values": [0.8, 1.0, 1.2]},
        "safety_margin": {"values": [0.1, 0.2]},
    },
    "budget": {"max_trials": 18, "seeds_per_trial": 3},
}


class PolicyDesigner:
    def __init__(self, project_root: Path) -> None:
        self.project_root = Path(project_root)

    def build(self, scenario_dir: Path, policy_id: str) -> Path:
        scenario_dir = Path(scenario_dir)
        task_spec = read_yaml(scenario_dir / "task_spec.yaml")
        task_id = str(task_spec.get("task_id", scenario_dir.name))

        policy_dir = self.project_root / "policies" / policy_id
        ensure_empty_output_dir(policy_dir)

        self._write_static_files(policy_dir, policy_id, task_id)
        write_yaml(policy_dir / "default_config.yaml", DEFAULT_CONFIG)
        write_yaml(policy_dir / "search_space.yaml", SEARCH_SPACE)
        write_json(policy_dir / "metadata.json", self._metadata(policy_id, scenario_dir, task_spec))
        write_json(policy_dir / "manifest.json", build_manifest(policy_dir, "policy", policy_id))
        return policy_dir

    def _write_static_files(self, policy_dir: Path, policy_id: str, task_id: str) -> None:
        (policy_dir / "policy.py").write_text(POLICY_PY, encoding="utf-8")
        (policy_dir / "train.py").write_text(TRAIN_PY, encoding="utf-8")
        (policy_dir / "infer.py").write_text(INFER_PY, encoding="utf-8")
        (policy_dir / "algorithm_card.md").write_text(algorithm_card(policy_id, task_id), encoding="utf-8")
        (policy_dir / "requirements.txt").write_text("numpy>=1.24\nPyYAML>=6.0\n", encoding="utf-8")

        tests_dir = policy_dir / "tests"
        tests_dir.mkdir(parents=True, exist_ok=True)
        (tests_dir / "test_policy_interface.py").write_text(POLICY_INTERFACE_TEST_PY, encoding="utf-8")
        (tests_dir / "test_action_bounds.py").write_text(ACTION_BOUNDS_TEST_PY, encoding="utf-8")
        (tests_dir / "test_inference_latency.py").write_text(INFERENCE_LATENCY_TEST_PY, encoding="utf-8")
        (tests_dir / "test_smoke_rollout.py").write_text(SMOKE_ROLLOUT_TEST_PY, encoding="utf-8")

    def _metadata(self, policy_id: str, scenario_dir: Path, task_spec: dict[str, Any]) -> dict[str, Any]:
        return {
            "schema_version": "1.1",
            "policy_id": policy_id,
            "policy_type": DEFAULT_CONFIG["policy_type"],
            "scenario_dir": scenario_dir.as_posix(),
            "task_id": task_spec.get("task_id"),
            "task_family": task_spec.get("task_family"),
            "formalism": task_spec.get("formalism"),
            "method": {
                "family": "rule_based",
                "name": DEFAULT_CONFIG["policy_type"],
                "learning_paradigm": "none",
                "execution_mode": "decentralized",
                "trained_parties": [],
                "frozen_parties": ["all"],
                "parameter_sharing": "not_applicable",
                "training_privileged_state": False,
                "explicit_opponent_model": False,
                "selection_rationale": (
                    "The scenario exposes direct geometric direction fields, so a "
                    "bounded rule controller is simpler and more reproducible than "
                    "learning or receding-horizon optimization for this baseline."
                ),
            },
            "method_hypothesis": {
                "statement": (
                    "A bounded geometric controller is sufficient when ring-relative "
                    "direction and interception direction dominate the decision."
                ),
                "suspected_bottlenecks": [
                    "speed versus maneuverability trade-off",
                    "interception pressure near the active ring",
                    "safety margin near action and arena boundaries",
                ],
                "optimization_guidance": [
                    "Tune motion and interception gains before changing policy code.",
                    "Treat safety_margin as a constraint-oriented parameter, not a reward proxy.",
                ],
            },
            "immutable_boundaries": {
                "scenario_id": task_spec.get("task_id"),
                "evaluation_source": "scenario.evaluation_metrics",
                "method_invariants": [
                    "Keep the rule_ring_navigation method family.",
                    "Keep execution observations within the scenario observation contract.",
                    "Clip every returned action to the scenario action bounds.",
                ],
                "forbidden_changes": [
                    "Do not modify the frozen scenario package.",
                    "Do not rank candidates by training reward.",
                    "Do not switch to another method family inside AutoResearch.",
                ],
            },
            "checkpoint_binding": {
                "method": DEFAULT_CONFIG["policy_type"],
                "observation_contract": "scenario.observation_space",
                "action_contract": "scenario.action_space",
                "preprocessing": "none",
            },
        }
