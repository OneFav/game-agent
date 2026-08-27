from __future__ import annotations

import argparse
import csv
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import torch
import yaml

from game_agent.envs.drone_ring_game import DroneRingEnv

from policy import (
    AGENT_COUNT,
    LEARNED_ACTION_DIM,
    METHOD_NAME,
    OBS_DIM,
    PREPROCESSING_ID,
    SCENARIO_ACTION_DIM,
    build_ppo,
    frozen_blue_action,
    normalize_observation,
    red_action_from_normalized,
)


def _read_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"YAML root must be a mapping: {path}")
    return data


def _episode(
    algorithm: Any,
    env: DroneRingEnv,
    spec: dict[str, Any],
    config: dict[str, Any],
    seed: int,
    *,
    collect: bool,
    step_budget: int | None = None,
) -> tuple[float, dict[str, Any], int]:
    observations, info = env.reset(seed=seed)
    total_reward = 0.0
    steps = 0
    latest_metrics = dict(info.get("metrics", {}))
    max_steps = int(spec.get("env_config", {}).get("max_steps", env.max_steps))
    if step_budget is not None:
        max_steps = min(max_steps, step_budget)

    for _ in range(max_steps):
        red_observation = normalize_observation(observations["red_0"])
        normalized_action, log_prob, value = algorithm.select_action(
            red_observation,
            deterministic=not collect,
        )
        actions = {
            "red_0": red_action_from_normalized(normalized_action, spec),
            "blue_0": frozen_blue_action(observations["blue_0"], config, spec),
        }
        next_observations, rewards, terminated, truncated, info = env.step(actions)
        latest_metrics = dict(info.get("metrics", {}))
        done = bool(all(terminated.values()) or all(truncated.values()))

        before = np.asarray(observations["red_0"], dtype=np.float32)
        after = np.asarray(next_observations["red_0"], dtype=np.float32)
        passed_ring = bool(after[8] < before[8] - 1e-6)
        distance_progress = 0.0 if passed_ring else float(before[11] - after[11])
        shaped_reward = float(rewards["red_0"])
        shaped_reward += float(config.get("progress_reward_weight", 1.0)) * distance_progress
        shaped_reward -= float(config.get("control_penalty", 0.001)) * float(
            np.mean(np.square(normalized_action))
        )
        if latest_metrics.get("collision", False):
            shaped_reward -= float(config.get("collision_penalty", 2.0))
        if latest_metrics.get("out_of_bounds", False):
            shaped_reward -= float(config.get("out_of_bounds_penalty", 2.0))

        if collect:
            algorithm.buffer.add(
                red_observation,
                normalized_action,
                shaped_reward,
                normalize_observation(next_observations["red_0"]),
                done,
                log_prob,
                value,
            )
        total_reward += shaped_reward
        observations = next_observations
        steps += 1
        if done:
            break
    return total_reward, latest_metrics, steps


def _evaluate_primary(
    algorithm: Any,
    spec: dict[str, Any],
    config: dict[str, Any],
    seeds: list[int],
) -> float:
    successes = []
    for seed in seeds:
        env = DroneRingEnv(spec.get("env_config", {}))
        _reward, metrics, _steps = _episode(
            algorithm,
            env,
            spec,
            config,
            seed,
            collect=False,
        )
        successes.append(1.0 if metrics.get("success", False) else 0.0)
    return float(np.mean(successes))


def _save_checkpoint(algorithm: Any, path: Path) -> None:
    algorithm.save(str(path))
    checkpoint = torch.load(path, map_location="cpu", weights_only=False)
    checkpoint["policy_binding"] = {
        "method": METHOD_NAME,
        "observation_dim": OBS_DIM,
        "scenario_action_dim": SCENARIO_ACTION_DIM,
        "learned_action_dim": LEARNED_ACTION_DIM,
        "agent_count": AGENT_COUNT,
        "parameter_sharing": "none",
        "preprocessing": PREPROCESSING_ID,
    }
    torch.save(checkpoint, path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Train red_0 with online PPO against a frozen blue interceptor.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--output_dir", required=True)
    parser.add_argument("--max_steps", type=int, required=True)
    parser.add_argument("--wall_time_limit", type=float, required=True)
    parser.add_argument("--log_interval", type=int, default=1000)
    parser.add_argument("--resume_from", default=None)
    args = parser.parse_args()

    config_path = Path(args.config)
    scenario_dir = Path(args.scenario)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    config = _read_yaml(config_path)
    spec = _read_yaml(scenario_dir / "task_spec.yaml")

    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    torch.use_deterministic_algorithms(True)
    algorithm = build_ppo(config, device="cpu")
    if args.resume_from:
        algorithm.load(str(Path(args.resume_from)))

    started_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    started = time.perf_counter()
    rollout_steps = int(config.get("rollout_steps", 512))
    evaluation_seeds = [10_000 + args.seed + offset for offset in range(3)]
    rows: list[dict[str, Any]] = []
    episode_rewards: list[float] = []
    total_steps = 0
    episode = 0
    last_losses = {"actor_loss": 0.0, "critic_loss": 0.0}

    initial_evaluation = _evaluate_primary(
        algorithm,
        spec,
        config,
        evaluation_seeds,
    )
    rows.append(
        {
            "event": "evaluation",
            "step": 0,
            "episode": 0,
            "evaluation_primary": initial_evaluation,
        }
    )
    evaluation_interval = max(int(args.log_interval), 1)
    next_evaluation = evaluation_interval
    last_evaluation_step = 0
    last_evaluation_primary = initial_evaluation
    timed_out = False
    while total_steps < args.max_steps:
        if time.perf_counter() - started >= args.wall_time_limit:
            timed_out = True
            break
        remaining = args.max_steps - total_steps
        env = DroneRingEnv(spec.get("env_config", {}))
        reward, episode_metrics, used_steps = _episode(
            algorithm,
            env,
            spec,
            config,
            args.seed + episode,
            collect=True,
            step_budget=remaining,
        )
        total_steps += used_steps
        episode += 1
        episode_rewards.append(reward)
        rows.append(
            {
                "event": "episode",
                "step": total_steps,
                "episode": episode,
                "reward_mean": float(np.mean(episode_rewards[-10:])),
                "episode_reward": reward,
                "episode_length": used_steps,
                "episode_success": int(bool(episode_metrics.get("success", False))),
            }
        )

        if len(algorithm.buffer) >= rollout_steps or total_steps >= args.max_steps:
            updated = algorithm.update()
            if updated:
                last_losses = updated
                rows.append(
                    {
                        "event": "optimizer_update",
                        "step": total_steps,
                        "episode": episode,
                        "actor_loss": float(updated.get("actor_loss", 0.0)),
                        "critic_loss": float(updated.get("critic_loss", 0.0)),
                        "kl_divergence": float(updated.get("kl_divergence", 0.0)),
                    }
                )

        if total_steps >= next_evaluation or total_steps >= args.max_steps:
            last_evaluation_primary = _evaluate_primary(
                algorithm,
                spec,
                config,
                evaluation_seeds,
            )
            rows.append(
                {
                    "event": "evaluation",
                    "step": total_steps,
                    "episode": episode,
                    "evaluation_primary": last_evaluation_primary,
                }
            )
            last_evaluation_step = total_steps
            next_evaluation = (
                total_steps // evaluation_interval + 1
            ) * evaluation_interval

    if len(algorithm.buffer):
        updated = algorithm.update()
        if updated:
            last_losses = updated
            rows.append(
                {
                    "event": "optimizer_update",
                    "step": total_steps,
                    "episode": episode,
                    "actor_loss": float(updated.get("actor_loss", 0.0)),
                    "critic_loss": float(updated.get("critic_loss", 0.0)),
                    "kl_divergence": float(updated.get("kl_divergence", 0.0)),
                }
            )

    if last_evaluation_step != total_steps:
        last_evaluation_primary = _evaluate_primary(
            algorithm,
            spec,
            config,
            evaluation_seeds,
        )
        rows.append(
            {
                "event": "evaluation",
                "step": total_steps,
                "episode": episode,
                "evaluation_primary": last_evaluation_primary,
            }
        )

    checkpoint_path = output_dir / "checkpoint_final.pt"
    _save_checkpoint(algorithm, checkpoint_path)
    checkpoint_hash = hashlib.sha256(checkpoint_path.read_bytes()).hexdigest()
    curve_path = output_dir / "training_curves.csv"
    with curve_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "event",
                "step",
                "episode",
                "reward_mean",
                "actor_loss",
                "critic_loss",
                "evaluation_primary",
                "episode_reward",
                "episode_length",
                "episode_success",
                "kl_divergence",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    finished_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    training_log = {
        "schema_version": "1.0",
        "policy_id": Path(__file__).resolve().parent.name,
        "scenario_id": str(spec.get("task_id", scenario_dir.name)),
        "algorithm": "ppo",
        "learning_paradigm": "online_rl",
        "trained_parties": ["red_0"],
        "frozen_parties": ["blue_0"],
        "seed": args.seed,
        "evaluation_seeds": evaluation_seeds,
        "config_used": config,
        "checkpoint_path": checkpoint_path.name,
        "checkpoint_hash": f"sha256:{checkpoint_hash}",
        "curve_path": curve_path.name,
        "termination_reason": "wall_time_exhausted" if timed_out else "max_steps_reached",
        "status": "timeout" if timed_out else "completed",
        "total_steps": total_steps,
        "episodes": episode,
        "evaluation_interval_steps": evaluation_interval,
        "telemetry_counts": {
            event: sum(1 for row in rows if row.get("event") == event)
            for event in ("episode", "optimizer_update", "evaluation")
        },
        "started_at": started_at,
        "finished_at": finished_at,
        "wall_time_seconds": float(time.perf_counter() - started),
        "final_train_metrics": {
            "reward_mean": float(np.mean(episode_rewards[-10:])) if episode_rewards else 0.0,
            "actor_loss": float(last_losses.get("actor_loss", 0.0)),
            "critic_loss": float(last_losses.get("critic_loss", 0.0)),
            "evaluation_primary": float(last_evaluation_primary),
        },
    }
    (output_dir / "training_log.json").write_text(
        json.dumps(training_log, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return 2 if timed_out else 0


if __name__ == "__main__":
    raise SystemExit(main())
