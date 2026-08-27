from __future__ import annotations

import argparse
import hashlib
import json
import pprint
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


POLICIES_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = POLICIES_ROOT.parent
SOURCE_ROOT = PROJECT_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from game_agent.scenarios.catalog import build_max_space_50_catalog


STRATEGY_FAMILIES = {
    1: ("goal_vector", "bounded_goal_vector_rule", "geometry_goal_vector"),
    2: ("dynamics_pd", "dynamics_aware_pd_rule", "dynamics_aware_pd"),
    3: ("pursuit_role", "role_aware_pursuit_rule", "red_blue_pursuit"),
    4: ("team_coordination", "decentralized_team_rule", "team_coordination"),
    5: ("escort_defense", "role_aware_escort_defense_rule", "red_blue_escort_defense"),
    6: ("observation_limited", "observation_limited_rule", "observation_limited_control"),
    7: ("communication_aware", "stale_communication_rule", "communication_aware_control"),
    8: ("robust_capped", "robust_capped_pd_rule", "robustness_capped_pd"),
    9: ("lifecycle_role", "lifecycle_role_rule", "lifecycle_role_control"),
    10: ("scalable_adapter", "scalable_modality_rule", "scalable_modality_adapter"),
}

ADVERSARIAL_GROUPS = {3, 5}
PREPROCESSING = "max_space_local_obs_v1"
REQUIRED_TESTS = (
    "test_policy_class.py",
    "test_action_bounds.py",
    "test_deterministic.py",
    "test_no_side_effects.py",
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Materialize explicit max-space policy packages.")
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--all", action="store_true")
    selection.add_argument("--only", choices=[f"S{index:02d}" for index in range(1, 51)] + ["zero"])
    args = parser.parse_args(argv)

    catalog = list(build_max_space_50_catalog())
    if args.all or args.only == "zero":
        materialize_zero_policy()
    for spec in catalog:
        if args.all or spec["scenario_id"] == args.only:
            materialize_candidate(spec)
    return 0


def materialize_candidate(scenario: dict[str, Any]) -> Path:
    scenario_id = str(scenario["scenario_id"])
    index = int(scenario_id[1:])
    group = (index - 1) // 5 + 1
    strategy, method_name, controller_family = STRATEGY_FAMILIES[group]
    policy_id = f"max_space_{scenario_id.lower()}_rule_v1"
    dimension = int(scenario["runtime_config"]["dimension"])
    defaults = _default_config(policy_id, strategy, group, index)
    policy_spec = {
        "policy_id": policy_id,
        "scenario_id": scenario_id,
        "dimension": dimension,
        "method_name": method_name,
        "strategy": strategy,
        "controller_family": controller_family,
        "task_family": scenario["task_family"],
        "primary_metric": scenario["primary_metric"],
        "observation_type": scenario["runtime_config"]["observation_type"],
        "action_type": scenario["runtime_config"]["action_type"],
        "agent_count": int(scenario["runtime_config"]["n_agents"]),
        "adversarial": group in ADVERSARIAL_GROUPS,
        "zero_policy": False,
    }
    package_dir = POLICIES_ROOT / policy_id
    _write_package(package_dir, policy_spec, defaults, scenario)
    return package_dir


def materialize_zero_policy() -> Path:
    policy_id = "max_space_zero_v1"
    defaults = _default_config(policy_id, "zero", 0, 0)
    policy_spec = {
        "policy_id": policy_id,
        "scenario_id": "ALL",
        "dimension": 2,
        "method_name": "explicit_zero_action_rule",
        "strategy": "zero",
        "controller_family": "explicit_zero_baseline",
        "task_family": "max_space_50_v1",
        "primary_metric": "scenario_declared_primary",
        "observation_type": "scenario_declared",
        "action_type": "continuous_control_projection",
        "agent_count": 0,
        "adversarial": False,
        "zero_policy": True,
    }
    scenario = {
        "scenario_id": "ALL",
        "name": "Explicit zero-action baseline for max_space_50_v1",
        "task_family": "max_space_50_v1",
        "representative_distinction": "explicit_shared_baseline",
        "primary_metric": "scenario_declared_primary",
        "runtime_config": {
            "dimension": 2,
            "n_agents": 0,
            "observation_type": "scenario_declared",
            "action_type": "continuous_control_projection",
        },
    }
    package_dir = POLICIES_ROOT / policy_id
    _write_package(package_dir, policy_spec, defaults, scenario)
    return package_dir


def _write_package(
    package_dir: Path,
    policy_spec: dict[str, Any],
    defaults: dict[str, Any],
    scenario: dict[str, Any],
) -> None:
    package_dir.mkdir(parents=True, exist_ok=True)
    tests_dir = package_dir / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    runtime_spec = dict(policy_spec)
    runtime_spec["default_config"] = dict(defaults)
    runtime_spec["checkpoint_binding"] = _checkpoint_binding(policy_spec)
    (package_dir / "policy.py").write_text(_policy_source(runtime_spec), encoding="utf-8")
    (package_dir / "train.py").write_text(_train_source(runtime_spec), encoding="utf-8")
    (package_dir / "infer.py").write_text(_infer_source(policy_spec), encoding="utf-8")
    _write_yaml(package_dir / "default_config.yaml", defaults)
    _write_yaml(package_dir / "search_space.yaml", _search_space(defaults, policy_spec))
    _write_json(package_dir / "metadata.json", _metadata(policy_spec, scenario))
    (package_dir / "algorithm_card.md").write_text(
        _algorithm_card(policy_spec, scenario), encoding="utf-8"
    )
    (package_dir / "requirements.txt").write_text(
        "numpy>=1.24\nPyYAML>=6.0\n", encoding="utf-8"
    )
    for filename, content in _tests().items():
        (tests_dir / filename).write_text(content, encoding="utf-8")
    _write_json(package_dir / "manifest.json", _manifest(package_dir, policy_spec))


def _default_config(
    policy_id: str, strategy: str, group: int, index: int
) -> dict[str, Any]:
    damping = 0.55
    action_cap = 1.0
    communication_decay = 0.0
    role_gain = 0.0
    if index == 6:
        damping = 0.0
    elif index == 7:
        damping = 0.8
        action_cap = 0.82
    elif group == 2:
        damping = 0.45
    elif group in {3, 5}:
        role_gain = 0.18
    elif group == 6:
        action_cap = 0.82
    elif group == 7:
        communication_decay = 0.12
    elif group == 8:
        action_cap = 0.88
    elif group == 10:
        action_cap = 0.92
    if strategy == "zero":
        action_cap = 1.0
    return {
        "strategy": strategy,
        "policy_id": policy_id,
        "gain": 1.0,
        "damping": damping,
        "action_cap": action_cap,
        "rate_limit": 2.0,
        "communication_decay": communication_decay,
        "role_gain": role_gain,
    }


def _policy_source(policy_spec: dict[str, Any]) -> str:
    adversarial_import = ", RedPolicy, BluePolicy" if policy_spec["adversarial"] else ""
    return f'''from __future__ import annotations

import sys
from pathlib import Path


def _add_source_root() -> None:
    for parent in Path(__file__).resolve().parents:
        source_root = parent / "src"
        if (source_root / "game_agent" / "policy_designer" / "max_space_policy.py").is_file():
            if str(source_root) not in sys.path:
                sys.path.insert(0, str(source_root))
            return


_add_source_root()

from game_agent.policy_designer.max_space_policy import MaxSpaceRulePolicy{adversarial_import}


class PolicyClass(MaxSpaceRulePolicy):
    """Stable adapter for {policy_spec['policy_id']} ({policy_spec['scenario_id']})."""

    PACKAGE_SPEC = {pprint.pformat(policy_spec, sort_dicts=False, width=100)}


POLICY_SPEC = {pprint.pformat(policy_spec, sort_dicts=False, width=100)}
'''


def _train_source(policy_spec: dict[str, Any]) -> str:
    return f'''from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml


POLICY_ID = {policy_spec['policy_id']!r}
SCENARIO_ID = {policy_spec['scenario_id']!r}
METHOD = {policy_spec['method_name']!r}
DIMENSION = {int(policy_spec['dimension'])!r}
PREPROCESSING = {PREPROCESSING!r}
CHECKPOINT_BINDING = {pprint.pformat(policy_spec['checkpoint_binding'], sort_dicts=False, width=100)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Materialize a frozen rule-policy checkpoint.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--seed", required=True, type=int)
    parser.add_argument("--output_dir", required=True)
    parser.add_argument("--max_steps", required=True, type=int)
    parser.add_argument("--wall_time_limit", required=True, type=int)
    parser.add_argument("--resume_from")
    parser.add_argument("--log_interval", type=int, default=100)
    args = parser.parse_args(argv)
    try:
        config_path = Path(args.config)
        scenario_path = Path(args.scenario)
        if not config_path.is_file() or not scenario_path.exists():
            raise ValueError("--config and --scenario must exist")
        if args.resume_from and not Path(args.resume_from).is_file():
            raise ValueError("--resume_from must exist")
        if args.max_steps < 0 or args.wall_time_limit <= 0 or args.log_interval <= 0:
            raise ValueError("invalid budget")
        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {{}}
        if not isinstance(config, dict):
            raise ValueError("config root must be a mapping")
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        checkpoint = {{
            "schema_version": "rule_checkpoint/v1",
            "policy_id": POLICY_ID,
            "action_shape": [DIMENSION],
            "config": config,
            "checkpoint_binding": CHECKPOINT_BINDING,
        }}
        checkpoint_path = output_dir / "checkpoint_final.pt"
        checkpoint_path.write_text(json.dumps(checkpoint, indent=2) + "\\n", encoding="utf-8")
        checkpoint_hash = hashlib.sha256(checkpoint_path.read_bytes()).hexdigest()
        with (output_dir / "training_curves.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["step", "episode", "reward_mean", "actor_loss", "critic_loss", "evaluation_primary"])
            writer.writerow([0, 0, 0.0, 0.0, 0.0, ""])
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        log = {{
            "schema_version": "1.0",
            "policy_id": POLICY_ID,
            "scenario_id": SCENARIO_ID,
            "termination_reason": "rule_policy_materialized",
            "checkpoint_path": checkpoint_path.name,
            "checkpoint_hash": f"sha256:{{checkpoint_hash}}",
            "status": "completed",
            "trainer": "no_op_rule_parameter_materializer",
            "convergence_evidence": False,
            "curve_interpretation": "schema-only row; not convergence evidence",
            "config_used": config,
            "seed": args.seed,
            "started_at": now,
            "finished_at": now,
            "total_steps": 0,
        }}
        (output_dir / "training_log.json").write_text(json.dumps(log, indent=2) + "\\n", encoding="utf-8")
        (output_dir / "stdout.log").write_text("rule policy materialized; not convergence evidence\\n", encoding="utf-8")
        return 0
    except MemoryError:
        return 3
    except Exception as error:
        print(f"training configuration error: {{error}}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
'''


def _infer_source(policy_spec: dict[str, Any]) -> str:
    return f'''from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path

import numpy as np
import yaml


EXPECTED_SCENARIO_ID = {policy_spec['scenario_id']!r}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate an explicit max-space rule policy.")
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--eval_seeds", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--render", action="store_true")
    parser.add_argument("--stress_test")
    args = parser.parse_args(argv)
    try:
        checkpoint = Path(args.checkpoint)
        scenario_path = Path(args.scenario)
        if not checkpoint.is_file() or not scenario_path.exists():
            raise ValueError("--checkpoint and --scenario must exist")
        _add_source_root()
        from game_agent.scenarios import catalog_by_id, create_runtime

        scenario_spec = _scenario_spec(scenario_path, catalog_by_id())
        PolicyClass = _load_policy_class()
        config = _read_yaml(Path(__file__).with_name("default_config.yaml"))
        seeds = _parse_seeds(args.eval_seeds)
        per_seed = []
        started = time.perf_counter()
        for seed in seeds:
            runtime = create_runtime(scenario_spec)
            descriptor = runtime.describe()
            env_spec = dict(scenario_spec)
            env_spec["action_space"] = dict(descriptor.action_spaces[descriptor.agents[0]])
            policy = PolicyClass(config, env_spec)
            policy.load(str(checkpoint))
            policy.reset(seed)
            observations, info = runtime.reset(seed=seed)
            for _ in range(int(getattr(runtime, "max_steps", 200))):
                actions = {{agent: policy.act(observations, agent, info) for agent in runtime.agents}}
                observations, _rewards, terminated, truncated, info = runtime.step(actions)
                if all(terminated.values()) or all(truncated.values()):
                    break
            metrics = runtime.get_metrics()
            per_seed.append({{
                "seed": seed,
                "primary_value": float(metrics.get("primary_value", 0.0)),
                "success_rate": float(metrics.get("success_rate", 0.0)),
                "collision_rate": float(metrics.get("collision_rate", 0.0)),
                "out_of_bounds_rate": float(metrics.get("out_of_bounds_rate", 0.0)),
                "action_violation_rate": float(metrics.get("action_violation_rate", 0.0)),
                "episode_length": int(metrics.get("episode_length", 0)),
            }})
            runtime.close()
        primary_values = [item["primary_value"] for item in per_seed]
        hard_constraints = {{}}
        for name in ("collision_rate", "out_of_bounds_rate", "action_violation_rate"):
            value = float(np.mean([item[name] for item in per_seed]))
            hard_constraints[name] = {{"value": value, "max": 0.0, "passed": value <= 0.0}}
        output_data = {{
            "schema_version": "1.0",
            "status": "completed",
            "policy_id": Path(__file__).resolve().parent.name,
            "scenario_id": scenario_spec["scenario_id"],
            "metrics": {{
                "primary": {{
                    "name": scenario_spec["primary_metric"],
                    "value": float(np.mean(primary_values)),
                    "mean": float(np.mean(primary_values)),
                    "std": float(np.std(primary_values)),
                    "n": len(primary_values),
                }},
                "secondary": {{
                    "success_rate": {{"value": float(np.mean([item["success_rate"] for item in per_seed]))}},
                    "avg_episode_length": {{"value": float(np.mean([item["episode_length"] for item in per_seed]))}},
                }},
                "hard_constraints": hard_constraints,
            }},
            "per_seed_metrics": per_seed,
            "failure_episodes": [
                {{"seed": item["seed"], "failure_type": "task_incomplete"}}
                for item in per_seed if item["success_rate"] < 1.0
            ],
            "wall_time_seconds": float(time.perf_counter() - started),
            "render": bool(args.render),
            "stress_test": args.stress_test,
        }}
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(output_data, indent=2) + "\\n", encoding="utf-8")
        return 0
    except MemoryError:
        return 3
    except Exception as error:
        print(f"inference error: {{error}}", file=sys.stderr)
        return 1


def _scenario_spec(path: Path, catalog: dict) -> dict:
    candidate = path / "task_spec.yaml" if path.is_dir() else path
    if candidate.is_file():
        loaded = _read_yaml(candidate)
        if loaded.get("runtime_config"):
            return loaded
    if EXPECTED_SCENARIO_ID == "ALL":
        raise ValueError("zero baseline inference needs one representative scenario spec")
    return catalog[EXPECTED_SCENARIO_ID]


def _load_policy_class() -> type:
    path = Path(__file__).with_name("policy.py")
    spec = importlib.util.spec_from_file_location("_max_space_infer_policy", path)
    if spec is None or spec.loader is None:
        raise ImportError("cannot load policy.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.PolicyClass


def _add_source_root() -> None:
    for parent in Path(__file__).resolve().parents:
        source_root = parent / "src"
        if (source_root / "game_agent").is_dir():
            if str(source_root) not in sys.path:
                sys.path.insert(0, str(source_root))
            return


def _read_yaml(path: Path) -> dict:
    value = yaml.safe_load(path.read_text(encoding="utf-8")) or {{}}
    if not isinstance(value, dict):
        raise ValueError(f"YAML root must be a mapping: {{path}}")
    return value


def _parse_seeds(raw: str) -> list[int]:
    stripped = raw.strip()
    values = json.loads(stripped) if stripped.startswith("[") else stripped.split(",")
    seeds = [int(value) for value in values if str(value).strip()]
    if not seeds:
        raise ValueError("--eval_seeds must contain at least one integer")
    return seeds


if __name__ == "__main__":
    raise SystemExit(main())
'''


def _search_space(defaults: dict[str, Any], policy_spec: dict[str, Any]) -> dict[str, Any]:
    if policy_spec["zero_policy"]:
        parameters: dict[str, Any] = {}
        priority_1: list[str] = []
        priority_2: list[str] = []
    else:
        parameters = {
            "gain": _parameter("number", 0.4, 1.6, defaults["gain"], [0.8, 1.0, 1.2]),
            "damping": _parameter("number", 0.0, 1.2, defaults["damping"], [defaults["damping"], 0.65]),
            "action_cap": _parameter("number", 0.4, 1.0, defaults["action_cap"], [defaults["action_cap"], 1.0]),
        }
        priority_1 = ["gain", "damping", "action_cap"]
        priority_2 = []
        if policy_spec["strategy"] == "communication_aware":
            parameters["communication_decay"] = _parameter(
                "number", 0.0, 0.5, defaults["communication_decay"], [0.06, 0.12, 0.2]
            )
            priority_2.append("communication_decay")
        if policy_spec["adversarial"]:
            parameters["role_gain"] = _parameter(
                "number", 0.0, 0.5, defaults["role_gain"], [0.0, 0.18, 0.3]
            )
            priority_2.append("role_gain")
    tuned = set(parameters)
    return {
        "parameters": parameters,
        "priority_groups": {
            "priority_1": priority_1,
            "priority_2": priority_2,
            "do_not_tune": [name for name in defaults if name not in tuned],
        },
        "budget": {
            "max_trials": 12,
            "seeds_per_trial": 3,
            "max_train_steps": 0,
            "wall_time_limit_seconds": 30,
            "log_interval": 1,
        },
    }


def _parameter(
    kind: str, minimum: float, maximum: float, default: float, values: list[float]
) -> dict[str, Any]:
    return {
        "type": kind,
        "minimum": minimum,
        "maximum": maximum,
        "default": default,
        "values": list(dict.fromkeys(values)),
    }


def _metadata(policy_spec: dict[str, Any], scenario: dict[str, Any]) -> dict[str, Any]:
    adversarial = bool(policy_spec["adversarial"])
    frozen_parties = ["red", "blue"] if adversarial else ["all_agents"]
    implementation_path = SOURCE_ROOT / "game_agent" / "policy_designer" / "max_space_policy.py"
    return {
        "schema_version": "1.2",
        "policy_id": policy_spec["policy_id"],
        "policy_type": "rule_based_reference_baseline",
        "scenario_ref": f"catalog:max_space_50_v1:{policy_spec['scenario_id']}",
        "task_id": policy_spec["scenario_id"],
        "task_family": policy_spec["task_family"],
        "formalism": "POSG" if adversarial else "decentralized_control",
        "optimization_target": {
            "mode": "initial",
            "primary": policy_spec["primary_metric"],
            "threshold": 0.0,
            "definition": f"mean scenario.evaluation_metrics.{policy_spec['primary_metric']}",
            "utility_definition": {
                "candidate_utility": f"scenario metric {policy_spec['primary_metric']}",
                "baseline_utility": f"same-seed scenario metric {policy_spec['primary_metric']}",
            },
        },
        "method": {
            "family": "rule_based",
            "name": policy_spec["method_name"],
            "algorithm_family": policy_spec["controller_family"],
            "learning_paradigm": "none",
            "execution_mode": "decentralized_local_observation",
            "trained_parties": [],
            "frozen_parties": frozen_parties,
            "parameter_sharing": "side_specific_dispatch" if adversarial else "shared_by_all_agents",
            "multi_agent_paradigm": "independent_decentralized" if policy_spec["agent_count"] > 1 else "single_agent",
            "execution_information": [
                "local proprioception",
                "local target_delta",
                "progress, normalized time, message age, and role code when declared",
            ],
            "training_privileged_state": False,
            "explicit_opponent_model": False,
            "reward_design": {
                "intent": "No training reward is used by this frozen rule baseline.",
                "decomposition": [],
            },
            "selection_rationale": (
                "A bounded observation-only rule controller is the smallest executable "
                "reference for protocol and promotion testing; it is not claimed to be "
                "the final high-performance method."
            ),
        },
        "method_hypothesis": {
            "statement": (
                f"For {policy_spec['scenario_id']}, {policy_spec['method_name']} should improve "
                f"{policy_spec['primary_metric']} over the explicit zero-action baseline without "
                "action, collision, or boundary violations."
            ),
            "suspected_bottlenecks": [
                str(scenario["representative_distinction"]),
                f"{policy_spec['observation_type']} execution observations",
                "gain/damping trade-off under scenario hard constraints",
            ],
            "optimization_guidance": [
                "Tune gain and damping before action_cap.",
                "For adversarial or communication tasks, tune role/communication parameters only after safety passes.",
                "Use scenario evaluation metrics for promotion; never substitute training reward.",
            ],
        },
        "immutable_boundaries": {
            "scenario_id": policy_spec["scenario_id"],
            "evaluation_source": "scenario.evaluation_metrics",
            "method_invariants": [
                f"Keep the {policy_spec['method_name']} rule family.",
                "Execute with local scenario observations and non-privileged info only.",
                "Clip every final action to scenario.action_space.",
            ],
            "forbidden_changes": [
                "Do not modify frozen scenario or evaluator files.",
                "Do not consume global simulator state or training-only privileged state.",
                "Do not replace the explicit rule method with a learned method during this search stage.",
            ],
            "information_limits": "scenario observation contract only; graph/image policies use declared proprioception",
            "action_limits": "finite action with scenario shape, norm cap, and final bounds clipping",
        },
        "checkpoint_binding": _checkpoint_binding(policy_spec),
        "implementation_dependency": {
            "path": "src/game_agent/policy_designer/max_space_policy.py",
            "sha256": _sha256(implementation_path),
        },
    }


def _checkpoint_binding(policy_spec: dict[str, Any]) -> dict[str, Any]:
    action_contract = (
        "scenario.action_space:runtime_dimension"
        if policy_spec["zero_policy"]
        else f"scenario.action_space:{policy_spec['action_type']}:{policy_spec['dimension']}d"
    )
    return {
        "method": policy_spec["method_name"],
        "observation_contract": f"scenario.observation_space:{policy_spec['observation_type']}",
        "action_contract": action_contract,
        "preprocessing": PREPROCESSING,
        "scenario_id": policy_spec["scenario_id"],
        "agent_count": policy_spec["agent_count"],
        "parameter_sharing": "side_specific_dispatch" if policy_spec["adversarial"] else "shared_by_all_agents",
    }


def _algorithm_card(policy_spec: dict[str, Any], scenario: dict[str, Any]) -> str:
    adversarial = bool(policy_spec["adversarial"])
    parties = "RedPolicy and BluePolicy are separate frozen branches." if adversarial else "All agents share one frozen local-observation rule."
    return f"""# Algorithm Card: {policy_spec['policy_id']}

## Family

Rule-based / `{policy_spec['method_name']}`. Learning is unnecessary for this stage because the package is an explicit, deterministic reference used to test protocol conformance and same-seed improvement over a zero-action baseline. It is not a claim that learning or MPC is unnecessary for a final high-fidelity solution.

## Compatible Scenarios

- Suite: `max_space_50_v1`
- Scenario: `{policy_spec['scenario_id']}` — {scenario['name']}
- Task family: `{policy_spec['task_family']}`
- Representative distinction: `{scenario['representative_distinction']}`

## Assumptions

- The execution observation follows `{PREPROCESSING}`: position, velocity, target delta, progress, normalized step, message age, and role code.
- Graph and image observations expose scenario-declared `proprioception`/`self_state`; raw graph/image data is not treated as privileged state.
- {parties}
- No explicit opponent model and no training-only privileged global state are used.

## Input/Output

Input is the current agent's scenario-declared local observation plus non-privileged `info`. Output is one finite `{policy_spec['dimension']}D` continuous control vector; hybrid scenarios consume this vector through their declared control projection.

## Training Method

`supports_training()` is false. `train.py` only validates/materializes configuration and emits a checkpoint, `training_log.json`, and one schema-valid `training_curves.csv` row. That row is explicitly not learning or convergence evidence. Training reward is not used.

## Method Hypothesis

For `{policy_spec['scenario_id']}`, `{policy_spec['method_name']}` should improve `{policy_spec['primary_metric']}` over `max_space_zero_v1` on the same seeds while preserving hard constraints. Suspected bottlenecks are `{scenario['representative_distinction']}`, observation modality `{policy_spec['observation_type']}`, and the gain/damping safety trade-off.

Optimization guidance: tune gain and damping first, then action cap; tune role or communication parameters only after safety passes. This guidance is soft and never overrides immutable boundaries or scenario evaluation metrics.

## Optimization Target and Utility Source

Mode is `initial`; primary utility is the cross-seed mean of scenario evaluator metric `{policy_spec['primary_metric']}`. Baseline and candidate use the same evaluator metric and seeds. Reward components are never substituted for the score.

## Immutable Boundaries

- Keep method `{policy_spec['method_name']}` and its rule-based paradigm.
- Keep execution information inside `scenario.observation_space`; do not consume simulator/global state.
- Keep final action clipping to `scenario.action_space` and preserve the declared action projection.
- Do not modify scenario, evaluator, hidden tests, or switch method families in AutoResearch.
- Evaluation authority is `scenario.evaluation_metrics`.

## Safety Mechanism

Configuration is schema bounded. The controller uses finite-value checks, a configured action cap, an O(1) local computation path, exception-to-zero fallback, and final `numpy.clip` against environment action bounds.

## Known Limitations

The rule uses only compact execution fields and does not learn obstacle maps, graph plans, visual features, opponent dynamics, or external simulator residuals. It is intentionally a minimal reference, not a universal optimal controller.

## Expected Failure Modes

Partial observations may hide decisive geometry; delayed/lossy communication can make coordination stale; dense swarms can require explicit separation; hybrid task selection and external dynamics may exceed a local goal-vector rule.

## Computational Requirements

CPU-only NumPy; O(action dimension) per `act()` call, constant policy memory, expected latency well below 50 ms, and no accelerator or network dependency.
"""


def _tests() -> dict[str, str]:
    return {
        "test_policy_class.py": '''from __future__ import annotations

import inspect
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
for parent in Path(__file__).resolve().parents:
    if (parent / "src" / "contracts" / "policy_protocol.py").is_file():
        sys.path.insert(0, str(parent / "src"))
        break

from contracts.policy_protocol import Policy
from policy import PolicyClass


def test_policy_class_implements_contract_and_schema() -> None:
    assert issubclass(PolicyClass, Policy)
    signature = inspect.signature(PolicyClass)
    signature.bind({}, {"action_space": {"shape": [2], "low": [-1, -1], "high": [1, 1]}})
    config = yaml.safe_load((Path(__file__).resolve().parents[1] / "default_config.yaml").read_text(encoding="utf-8"))
    policy = PolicyClass(config, {"action_space": {"shape": [2], "low": [-1, -1], "high": [1, 1]}})
    search = yaml.safe_load((Path(__file__).resolve().parents[1] / "search_space.yaml").read_text(encoding="utf-8"))
    schema = policy.get_config_schema()
    assert set(search["parameters"]) <= set(schema)
    assert set(search["priority_groups"]["do_not_tune"]) <= set(schema)
    assert policy.supports_training() is False
''',
        "test_action_bounds.py": '''from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from policy import PolicyClass


def test_action_shape_finiteness_and_bounds() -> None:
    root = Path(__file__).resolve().parents[1]
    config = yaml.safe_load((root / "default_config.yaml").read_text(encoding="utf-8"))
    env_spec = {"action_space": {"shape": [3], "low": [-0.2, -0.3, -0.4], "high": [0.2, 0.3, 0.4]}}
    policy = PolicyClass(config, env_spec)
    obs = np.zeros(13, dtype=np.float32)
    obs[6:9] = [10.0, -10.0, 10.0]
    action = policy.act({"red_0": obs}, "red_0")
    assert action.shape == (3,)
    assert np.all(np.isfinite(action))
    assert np.all(action >= np.asarray(env_spec["action_space"]["low"], dtype=np.float32))
    assert np.all(action <= np.asarray(env_spec["action_space"]["high"], dtype=np.float32))


def test_exception_falls_back_to_zero() -> None:
    root = Path(__file__).resolve().parents[1]
    config = yaml.safe_load((root / "default_config.yaml").read_text(encoding="utf-8"))
    policy = PolicyClass(config, {"action_space": {"shape": [2], "low": [-1, -1], "high": [1, 1]}})
    assert np.array_equal(policy.act({}, "missing_agent"), np.zeros(2, dtype=np.float32))
''',
        "test_deterministic.py": '''from __future__ import annotations

import sys
from unittest.mock import patch
from pathlib import Path

import numpy as np
import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from policy import PolicyClass


def _policy() -> PolicyClass:
    root = Path(__file__).resolve().parents[1]
    config = yaml.safe_load((root / "default_config.yaml").read_text(encoding="utf-8"))
    return PolicyClass(config, {"action_space": {"shape": [2], "low": [-1, -1], "high": [1, 1]}})


def test_reset_is_deterministic() -> None:
    obs = np.asarray([0, 0, 0.1, -0.2, 1.0, 0.4, 0, 0, 1, 0], dtype=np.float32)
    policy = _policy()
    policy.reset(17)
    first = policy.act({"agent_00": obs}, "agent_00")
    policy.reset(17)
    second = policy.act({"agent_00": obs}, "agent_00")
    assert np.array_equal(first, second)


def test_checkpoint_dimension_mismatch_is_rejected() -> None:
    policy = _policy()
    payload = '{"policy_id": "' + policy.config["policy_id"] + '", "action_shape": [3]}'
    with patch("game_agent.policy_designer.max_space_policy.Path") as path_type:
        path_type.return_value.is_file.return_value = True
        path_type.return_value.read_text.return_value = payload
        with pytest.raises(ValueError, match="shape mismatch"):
            policy.load("synthetic-mismatch.json")
''',
        "test_no_side_effects.py": '''from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from policy import PolicyClass


def test_act_has_no_io_or_input_mutation(capsys) -> None:
    root = Path(__file__).resolve().parents[1]
    config = yaml.safe_load((root / "default_config.yaml").read_text(encoding="utf-8"))
    policy = PolicyClass(config, {"action_space": {"shape": [2], "low": [-1, -1], "high": [1, 1]}})
    obs = {"agent_00": np.asarray([0, 0, 0, 0, 1, 0, 0, 0, 1, 0], dtype=np.float32)}
    snapshot = obs["agent_00"].copy()
    before = {path.relative_to(root) for path in root.rglob("*") if path.is_file() and "__pycache__" not in path.parts}
    started = time.perf_counter()
    for _ in range(100):
        policy.act(obs, "agent_00")
    elapsed = time.perf_counter() - started
    assert np.array_equal(obs["agent_00"], snapshot)
    after = {path.relative_to(root) for path in root.rglob("*") if path.is_file() and "__pycache__" not in path.parts}
    assert after == before
    assert capsys.readouterr().out == ""
    assert elapsed < 5.0
''',
    }


def _manifest(package_dir: Path, policy_spec: dict[str, Any]) -> dict[str, Any]:
    implementation = SOURCE_ROOT / "game_agent" / "policy_designer" / "max_space_policy.py"
    digest = hashlib.sha256()
    files: list[str] = []
    for path in sorted(package_dir.rglob("*")):
        if not path.is_file() or path.name == "manifest.json" or "__pycache__" in path.parts:
            continue
        relative = path.relative_to(package_dir).as_posix()
        files.append(relative)
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return {
        "schema_version": "1.1",
        "package_type": "policy",
        "package_id": policy_spec["policy_id"],
        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "files": files,
        "freeze_hash": digest.hexdigest(),
        "implementation_dependencies": [
            {
                "path": "src/game_agent/policy_designer/max_space_policy.py",
                "sha256": _sha256(implementation),
            }
        ],
        "training_estimate": {
            "supports_training": False,
            "trainer": "no_op_rule_parameter_materializer",
            "cpu_seconds": 1,
            "accelerator": "none",
            "curve_rows": 1,
            "convergence_evidence": False,
        },
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_yaml(path: Path, value: dict[str, Any]) -> None:
    path.write_text(
        yaml.safe_dump(value, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
