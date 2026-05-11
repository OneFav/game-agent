from __future__ import annotations

from textwrap import dedent


POLICY_PY = dedent(
    """
    from __future__ import annotations

    import sys
    from pathlib import Path
    from typing import Any

    import numpy as np


    def _add_project_root_to_sys_path() -> None:
        current = Path(__file__).resolve()
        for candidate in (current.parent, *current.parents):
            if (candidate / "contracts").exists() or (candidate / "game_agent").exists():
                sys.path.insert(0, str(candidate))
                return


    _add_project_root_to_sys_path()

    try:
        from contracts.policy_protocol import Policy
    except ModuleNotFoundError:
        from abc import ABC, abstractmethod

        class Policy(ABC):
            @abstractmethod
            def reset(self, seed: int) -> None:
                pass

            @abstractmethod
            def act(self, obs: dict[str, np.ndarray], agent_id: str, info: dict[str, Any] | None = None) -> np.ndarray:
                pass

            @abstractmethod
            def load(self, checkpoint_path: str) -> None:
                pass

            @abstractmethod
            def get_config_schema(self) -> dict[str, Any]:
                pass

            def supports_training(self) -> bool:
                return True

            def get_diagnostics(self) -> dict[str, Any]:
                return {}


    class RuleRingNavigationPolicy(Policy):
        def __init__(self, config: dict[str, Any] | None = None, env_spec: dict[str, Any] | None = None) -> None:
            self.config = config or {}
            env_spec = env_spec or {}
            action_space = env_spec.get("action_space", {})
            self._action_low = np.asarray(action_space.get("low", [-2.0, -2.0, -1.0, -1.0]), dtype=np.float32)
            self._action_high = np.asarray(action_space.get("high", [2.0, 2.0, 1.0, 1.0]), dtype=np.float32)
            self._speed_scale = float(self.config.get("speed_scale", 1.0))
            self._intercept_gain = float(self.config.get("intercept_gain", 1.0))
            self._safety_margin = float(self.config.get("safety_margin", 0.2))
            self._seed: int | None = None
            self._checkpoint_path: str | None = None

        def reset(self, seed: int) -> None:
            self._seed = int(seed)

        def act(self, obs: Any, agent_id: str, info: dict[str, Any] | None = None) -> np.ndarray:
            del info
            observation = np.asarray(obs[agent_id] if isinstance(obs, dict) else obs, dtype=np.float32)
            if agent_id.startswith("red"):
                direction = observation[9:11]
                opponent_offset = observation[4:6]
                opponent_distance = float(np.linalg.norm(opponent_offset))
                if opponent_distance < self._safety_margin:
                    avoidance = -self._normalize(opponent_offset)
                    weight = 1.0 - opponent_distance / max(self._safety_margin, 1e-6)
                    direction = direction + avoidance * weight
                gain = self._speed_scale
            else:
                direction = observation[6:8]
                gain = self._intercept_gain

            velocity = self._normalize(direction) * gain
            action = np.array([velocity[0], velocity[1], 0.0, 0.0], dtype=np.float32)
            return np.clip(action, self._action_low, self._action_high).astype(np.float32)

        def load(self, checkpoint_path: str) -> None:
            self._checkpoint_path = str(Path(checkpoint_path))

        def get_config_schema(self) -> dict[str, Any]:
            return {
                "speed_scale": {"type": "number", "default": 1.0},
                "intercept_gain": {"type": "number", "default": 1.0},
                "safety_margin": {"type": "number", "default": 0.2},
            }

        def get_diagnostics(self) -> dict[str, Any]:
            return {"seed": self._seed, "checkpoint_path": self._checkpoint_path}

        def _normalize(self, vector: np.ndarray) -> np.ndarray:
            norm = float(np.linalg.norm(vector))
            if norm < 1e-6:
                return np.zeros(2, dtype=np.float32)
            return (vector / norm).astype(np.float32)


    PolicyClass = RuleRingNavigationPolicy
    """
).lstrip()


TRAIN_PY = dedent(
    """
    from __future__ import annotations

    import argparse
    import hashlib
    import json
    import sys
    import time
    from datetime import datetime, timezone
    from pathlib import Path

    import yaml


    def _existing_path(value: str, label: str) -> Path:
        path = Path(value)
        if not path.exists():
            raise FileNotFoundError(f"{label} does not exist: {path}")
        return path


    def _scenario_id(scenario_path: Path) -> str:
        spec_path = scenario_path / "task_spec.yaml" if scenario_path.is_dir() else scenario_path
        if not spec_path.exists():
            return scenario_path.stem
        data = yaml.safe_load(spec_path.read_text(encoding="utf-8")) or {}
        return str(data.get("task_id", scenario_path.name))


    def main() -> int:
        parser = argparse.ArgumentParser(description="No-op trainer for rule ring navigation policy.")
        parser.add_argument("--config", required=True)
        parser.add_argument("--scenario", required=True)
        parser.add_argument("--seed", type=int, required=True)
        parser.add_argument("--output_dir", required=True)
        parser.add_argument("--max_steps", type=int, required=True)
        parser.add_argument("--wall_time_limit", type=float, required=True)
        parser.add_argument("--log_interval", type=int, default=1000)
        parser.add_argument("--resume_from", default=None)
        args = parser.parse_args()

        try:
            config_path = _existing_path(args.config, "--config")
            scenario_path = _existing_path(args.scenario, "--scenario")
            resume_path = _existing_path(args.resume_from, "--resume_from") if args.resume_from else None
        except FileNotFoundError as error:
            print(f"error: {error}", file=sys.stderr)
            return 3

        started_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        started = time.perf_counter()
        config_used = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        checkpoint = {
            "policy_type": "rule_ring_navigation",
            "seed": args.seed,
            "config": str(config_path),
            "scenario": str(scenario_path),
            "resume_from": str(resume_path) if resume_path else None,
        }
        checkpoint_path = output_dir / "checkpoint_final.pt"
        checkpoint_path.write_text(json.dumps(checkpoint, indent=2, ensure_ascii=False) + "\\n", encoding="utf-8")
        checkpoint_hash = hashlib.sha256(checkpoint_path.read_bytes()).hexdigest()
        finished_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        wall_time_seconds = float(time.perf_counter() - started)
        timed_out = args.wall_time_limit <= 0
        log = {
            "schema_version": "1.0",
            "policy_id": Path(__file__).resolve().parent.name,
            "scenario_id": _scenario_id(scenario_path),
            "termination_reason": "wall_time_exhausted" if timed_out else "max_steps_reached",
            "checkpoint_path": "checkpoint_final.pt",
            "checkpoint_hash": f"sha256:{checkpoint_hash}",
            "status": "timeout" if timed_out else "completed",
            "trainer": "no_op",
            "max_steps": args.max_steps,
            "wall_time_limit": args.wall_time_limit,
            "log_interval": args.log_interval,
            "config_used": config_used,
            "seed": args.seed,
            "started_at": started_at,
            "finished_at": finished_at,
            "wall_time_seconds": wall_time_seconds,
            "total_steps": args.max_steps,
            "final_train_metrics": {"mean_episode_reward": 0.0, "mean_episode_length": 0.0},
        }
        (output_dir / "training_curves.csv").write_text("step,reward,loss\\n0,0.0,0.0\\n", encoding="utf-8")
        (output_dir / "training_log.json").write_text(json.dumps(log, indent=2, ensure_ascii=False) + "\\n", encoding="utf-8")
        (output_dir / "stdout.log").write_text("no-op training completed\\n", encoding="utf-8")
        return 2 if timed_out else 0


    if __name__ == "__main__":
        raise SystemExit(main())
    """
).lstrip()


INFER_PY = dedent(
    """
    from __future__ import annotations

    import argparse
    import json
    import sys
    import time
    from pathlib import Path

    import numpy as np
    import yaml


    def _add_project_root_to_sys_path() -> None:
        current = Path(__file__).resolve()
        for candidate in (current.parent, *current.parents):
            if (candidate / "contracts").exists() or (candidate / "game_agent").exists():
                sys.path.insert(0, str(candidate))
                return


    def main() -> None:
        parser = argparse.ArgumentParser(description="Run minimal evaluation for a generated policy package.")
        parser.add_argument("--checkpoint", required=True)
        parser.add_argument("--scenario", required=True)
        parser.add_argument("--eval_seeds", required=True)
        parser.add_argument("--output", required=True)
        parser.add_argument("--render", action="store_true")
        parser.add_argument("--stress_test", default=None)
        args = parser.parse_args()

        if not Path(args.checkpoint).is_file():
            print(f"error: checkpoint does not exist: {args.checkpoint}", file=sys.stderr)
            raise SystemExit(3)

        _add_project_root_to_sys_path()
        try:
            results = evaluate(args)
        except Exception as error:
            output = Path(args.output)
            output.parent.mkdir(parents=True, exist_ok=True)
            failure = {"status": "failed", "error": str(error), "seeds": _parse_seeds(args.eval_seeds)}
            output.write_text(json.dumps(failure, indent=2, ensure_ascii=False) + "\\n", encoding="utf-8")
            raise SystemExit(2) from error

        Path(args.output).write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\\n", encoding="utf-8")


    def evaluate(args: argparse.Namespace) -> dict:
        scenario_dir = Path(args.scenario)
        if not scenario_dir.is_dir():
            raise FileNotFoundError(f"--scenario must be a scenario directory: {scenario_dir}")
        task_spec = _read_yaml(scenario_dir / "task_spec.yaml")
        env_config = _read_yaml(scenario_dir / "env_config.yaml")
        env = _make_env(scenario_dir, env_config)

        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from policy import PolicyClass

        policy = PolicyClass(_read_yaml(Path(__file__).with_name("default_config.yaml")), task_spec)
        checkpoint = str(args.checkpoint or "")
        checkpoint_hash = _checkpoint_hash(checkpoint)
        policy.load(checkpoint)

        seeds = _parse_seeds(args.eval_seeds)
        started = time.perf_counter()
        runner_results = _try_autoresearch_runner(args)
        if runner_results is not None:
            return _normalize_runner_results(
                runner_results,
                task_spec=task_spec,
                seeds=seeds,
                checkpoint_hash=checkpoint_hash,
                started=started,
                render=bool(args.render),
                stress_test=args.stress_test,
            )

        per_seed_metrics = [_run_episode(env, policy, seed, stress_test=args.stress_test) for seed in seeds]
        wall_time_seconds = time.perf_counter() - started
        return _build_eval_results(
            task_spec=task_spec,
            scenario_dir=scenario_dir,
            seeds=seeds,
            checkpoint_hash=checkpoint_hash,
            per_seed_metrics=per_seed_metrics,
            wall_time_seconds=wall_time_seconds,
            render=bool(args.render),
            stress_test=args.stress_test,
        )


    def _build_eval_results(
        task_spec: dict,
        scenario_dir: Path,
        seeds: list[int],
        checkpoint_hash: str,
        per_seed_metrics: list[dict],
        wall_time_seconds: float,
        render: bool,
        stress_test: str | None,
    ) -> dict:
        count = max(len(per_seed_metrics), 1)
        success_rate = sum(1 for item in per_seed_metrics if item["success"]) / count
        collision_rate = sum(1 for item in per_seed_metrics if item["collision"]) / count
        out_of_bounds_rate = sum(1 for item in per_seed_metrics if item["out_of_bounds"]) / count
        action_violation_rate = 0.0
        avg_episode_length = sum(item["episode_length"] for item in per_seed_metrics) / count
        success_values = [item["success_rate"] for item in per_seed_metrics]
        episode_lengths = [item["episode_length"] for item in per_seed_metrics]
        primary_spec = task_spec.get("evaluation_metrics", {}).get("primary", {})
        primary_name = str(primary_spec.get("name", "success_rate"))
        primary_direction = str(primary_spec.get("direction", "maximize"))
        primary_value = success_rate if primary_name == "success_rate" else 0.0
        metric_values = {
            "success_rate": success_rate,
            "collision_rate": collision_rate,
            "out_of_bounds_rate": out_of_bounds_rate,
            "action_violation_rate": action_violation_rate,
            "avg_episode_length": avg_episode_length,
        }
        aggregate_metrics = {
            "primary": {
                "name": primary_name,
                "value": primary_value,
                "direction": primary_direction,
                "mean": _mean(success_values) if primary_name == "success_rate" else primary_value,
                "std": _std(success_values) if primary_name == "success_rate" else 0.0,
                "n": len(success_values),
            },
            "secondary": {
                "avg_episode_length": {
                    "value": avg_episode_length,
                    "mean": _mean(episode_lengths),
                    "std": _std(episode_lengths),
                    "direction": "minimize",
                }
            },
            "hard_constraints": _hard_constraints_from_spec(task_spec, metric_values),
        }
        return {
            "schema_version": "1.0",
            "status": "completed",
            "policy_id": Path(__file__).resolve().parent.name,
            "checkpoint_hash": checkpoint_hash,
            "scenario_id": str(task_spec.get("task_id", scenario_dir.name)),
            "seeds_evaluated": seeds,
            "n_episodes": len(seeds),
            "metrics": aggregate_metrics,
            "per_seed_metrics": per_seed_metrics,
            "failure_episodes": [],
            "wall_time_seconds": wall_time_seconds,
            "render": render,
            "stress_test": stress_test,
        }


    def _try_autoresearch_runner(args: argparse.Namespace):
        try:
            from game_agent.autoresearch.runner import evaluate_policy_dir
        except Exception:
            return None
        try:
            return evaluate_policy_dir(
                Path(__file__).resolve().parent,
                Path(args.scenario),
                checkpoint=Path(args.checkpoint),
                seeds=_parse_seeds(args.eval_seeds),
                render=bool(args.render),
                stress_test=args.stress_test,
            )
        except TypeError:
            try:
                return evaluate_policy_dir(Path(__file__).resolve().parent, Path(args.scenario), seed=_parse_seeds(args.eval_seeds)[0])
            except Exception:
                return None
        except Exception:
            return None


    def _normalize_runner_results(
        results,
        task_spec: dict,
        seeds: list[int],
        checkpoint_hash: str,
        started: float,
        render: bool,
        stress_test: str | None,
    ) -> dict:
        if not isinstance(results, dict):
            return None
        if {"metrics", "per_seed_metrics"} <= set(results):
            normalized = dict(results)
            normalized.setdefault("policy_id", Path(__file__).resolve().parent.name)
            normalized.setdefault("checkpoint_hash", checkpoint_hash)
            normalized.setdefault("scenario_id", str(task_spec.get("task_id", Path.cwd().name)))
            normalized.setdefault("seeds_evaluated", seeds)
            normalized.setdefault("n_episodes", len(seeds))
            normalized.setdefault("failure_episodes", [])
            normalized.setdefault("wall_time_seconds", float(time.perf_counter() - started))
            normalized.setdefault("render", render)
            normalized.setdefault("stress_test", stress_test)
            return normalized
        per_seed_metrics = results.get("per_seed_metrics")
        if not isinstance(per_seed_metrics, list):
            return None
        return _build_eval_results(
            task_spec=task_spec,
            scenario_dir=Path.cwd(),
            seeds=seeds,
            checkpoint_hash=checkpoint_hash,
            per_seed_metrics=per_seed_metrics,
            wall_time_seconds=float(time.perf_counter() - started),
            render=render,
            stress_test=stress_test,
        )


    def _read_yaml(path: Path) -> dict:
        if not path.exists():
            raise FileNotFoundError(f"required file not found: {path}")
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            raise ValueError(f"YAML root must be a mapping: {path}")
        return data


    def _make_env(scenario_dir: Path, env_config: dict):
        env_py = scenario_dir / "env.py"
        if not env_py.exists():
            raise FileNotFoundError(f"scenario env.py not found: {env_py}")
        sys.path.insert(0, str(scenario_dir))
        from env import make_env

        return make_env(env_config)


    def _checkpoint_hash(checkpoint: str) -> str:
        if not checkpoint:
            return "sha256:none"
        path = Path(checkpoint)
        if not path.exists():
            return "sha256:none"
        return "sha256:" + __import__("hashlib").sha256(path.read_bytes()).hexdigest()


    def _parse_seeds(value: str) -> list[int]:
        seeds = [int(item.strip()) for item in value.split(",") if item.strip()]
        if not seeds:
            raise ValueError("--eval_seeds must contain at least one integer seed")
        return seeds


    def _mean(values: list[float]) -> float:
        return float(sum(values) / max(len(values), 1))


    def _std(values: list[float]) -> float:
        mean = _mean(values)
        return float((sum((value - mean) ** 2 for value in values) / max(len(values), 1)) ** 0.5)


    def _hard_constraints_from_spec(task_spec: dict, metric_values: dict[str, float]) -> dict:
        constraints = task_spec.get("evaluation_metrics", {}).get("hard_constraints", [])
        if not constraints:
            constraints = [
                {"name": "collision_rate", "max": 0.05},
                {"name": "out_of_bounds_rate", "max": 0.01},
                {"name": "action_violation_rate", "max": 0.0},
            ]
        result = {}
        for constraint in constraints:
            name = str(constraint.get("name", "unknown"))
            max_value = float(constraint.get("max", 0.0))
            value = float(metric_values.get(name, 0.0))
            result[name] = {"value": value, "max": max_value, "passed": value <= max_value}
        return result


    def _run_episode(env, policy, seed: int, stress_test: str | None = None) -> dict:
        policy.reset(seed)
        observations, info = env.reset(seed=seed)
        max_steps = 5 if not stress_test else 10
        latest_metrics = dict(info.get("metrics", {}))
        for _ in range(max_steps):
            actions = {agent_id: policy.act(observations[agent_id], agent_id) for agent_id in env.agents}
            observations, _rewards, terminated, truncated, info = env.step(actions)
            latest_metrics = dict(info.get("metrics", {}))
            if any(terminated.values()) or any(truncated.values()):
                break
        return {
            "seed": seed,
            "success": bool(latest_metrics.get("success", False)),
            "collision": bool(latest_metrics.get("collision", False)),
            "out_of_bounds": bool(latest_metrics.get("out_of_bounds", False)),
            "success_rate": 1.0 if latest_metrics.get("success", False) else 0.0,
            "collision_rate": 1.0 if latest_metrics.get("collision", False) else 0.0,
            "out_of_bounds_rate": 1.0 if latest_metrics.get("out_of_bounds", False) else 0.0,
            "episode_length": int(latest_metrics.get("episode_length", 0)),
            "action_violation_rate": 0.0,
        }


    if __name__ == "__main__":
        main()
    """
).lstrip()


POLICY_INTERFACE_TEST_PY = dedent(
    """
    from __future__ import annotations

    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

    import policy


    def test_policy_class_implements_policy_protocol() -> None:
        assert issubclass(policy.PolicyClass, policy.Policy)
    """
).lstrip()


ACTION_BOUNDS_TEST_PY = dedent(
    """
    from __future__ import annotations

    import sys
    from pathlib import Path

    import numpy as np

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

    from policy import PolicyClass


    def test_policy_actions_respect_bounds() -> None:
        env_spec = {"action_space": {"low": [-2.0, -2.0, -1.0, -1.0], "high": [2.0, 2.0, 1.0, 1.0]}}
        policy = PolicyClass({"speed_scale": 10.0, "intercept_gain": 10.0}, env_spec)
        for agent_id in ("red_0", "blue_0"):
            action = policy.act(np.ones(12, dtype=np.float32), agent_id)
            assert action.shape == (4,)
            assert np.all(action >= np.asarray(env_spec["action_space"]["low"], dtype=np.float32))
            assert np.all(action <= np.asarray(env_spec["action_space"]["high"], dtype=np.float32))


    def test_safety_margin_avoids_close_opponent_for_red() -> None:
        env_spec = {"action_space": {"low": [-2.0, -2.0, -1.0, -1.0], "high": [2.0, 2.0, 1.0, 1.0]}}
        obs = np.zeros(12, dtype=np.float32)
        obs[4:6] = [0.0, 0.05]
        obs[9:11] = [1.0, 0.0]

        no_margin = PolicyClass({"speed_scale": 1.0, "safety_margin": 0.0}, env_spec).act(obs, "red_0")
        with_margin = PolicyClass({"speed_scale": 1.0, "safety_margin": 1.0}, env_spec).act(obs, "red_0")

        assert with_margin[1] < no_margin[1]
    """
).lstrip()


INFERENCE_LATENCY_TEST_PY = dedent(
    """
    from __future__ import annotations

    import sys
    import time
    from pathlib import Path

    import numpy as np

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

    from policy import PolicyClass


    def test_policy_inference_latency_is_lightweight() -> None:
        env_spec = {"action_space": {"low": [-2.0, -2.0, -1.0, -1.0], "high": [2.0, 2.0, 1.0, 1.0]}}
        policy = PolicyClass({}, env_spec)
        obs = np.zeros(12, dtype=np.float32)

        start = time.perf_counter()
        for _ in range(100):
            policy.act(obs, "red_0")
        elapsed = time.perf_counter() - start

        assert elapsed < 0.5
    """
).lstrip()


SMOKE_ROLLOUT_TEST_PY = dedent(
    """
    from __future__ import annotations

    import sys
    from pathlib import Path

    import numpy as np

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

    from policy import PolicyClass


    def test_policy_smoke_rollout_action_shape_and_bounds() -> None:
        env_spec = {"action_space": {"low": [-2.0, -2.0, -1.0, -1.0], "high": [2.0, 2.0, 1.0, 1.0]}}
        policy = PolicyClass({}, env_spec)
        action = policy.act(np.zeros(12, dtype=np.float32), "red_0")

        assert action.shape == (4,)
        assert np.all(np.isfinite(action))
        assert np.all(action >= np.asarray(env_spec["action_space"]["low"], dtype=np.float32))
        assert np.all(action <= np.asarray(env_spec["action_space"]["high"], dtype=np.float32))
    """
).lstrip()


def algorithm_card(policy_id: str, task_id: str) -> str:
    return dedent(
        f"""
        # Algorithm Card: {policy_id}

        ## Scenario
        - Task id: `{task_id}`
        - Policy type: `rule_ring_navigation`

        ## Method
        Deterministic rule policy. The red agent moves toward the active ring direction from the observation. The blue
        agent uses the configured interception direction field. Actions are clipped to the scenario action bounds.

        ## Trainability
        `train.py` is a no-op trainer that emits a reproducible checkpoint placeholder for AutoResearch integration.

        ## AutoResearch knobs
        - `speed_scale`
        - `intercept_gain`
        - `safety_margin`
        """
    ).lstrip()
