"""实验运行、日志记录与汇总评估。"""
from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from game_agent.envs.swarm_combat.entities import Team
from game_agent.envs.swarm_combat.matplotlib_compat import patch_matplotlib_cbook


def team_value(mapping: dict, team_name: str, default=0):
    for key, value in mapping.items():
        key_name = key.name if hasattr(key, "name") else str(key)
        if key_name == team_name:
            return value
    return default


def serializable(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {
            key.name if hasattr(key, "name") else str(key): serializable(val)
            for key, val in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [serializable(v) for v in value]
    return value


def run_one_episode(env, policy, episode_idx: int, seed: Optional[int] = None, collect_steps: bool = True):
    """运行一局，返回 episode 汇总与逐步曲线。"""
    if seed is not None:
        env.rng = np.random.default_rng(seed)

    env.reset()
    policy.reset(env)

    total_rewards = {d.id: 0.0 for d in env.drones}
    step_rows: List[dict] = []
    last_info = {}
    final_step = env.cfg.max_steps

    for t in range(env.cfg.max_steps):
        actions = policy.compute_actions(env)
        _, rewards, terminated, _, info = env.step(actions)
        for k, v in rewards.items():
            total_rewards[k] += float(v)
        last_info = info

        if collect_steps:
            step_rows.append({
                "episode": episode_idx,
                "step": info["step"],
                "red_score": team_value(info["team_scores"], "RED"),
                "blue_score": team_value(info["team_scores"], "BLUE"),
                "red_passes": team_value(info["team_pass_count"], "RED"),
                "blue_passes": team_value(info["team_pass_count"], "BLUE"),
                "reward_sum": float(sum(rewards.values())),
                "pass_events": serializable(info.get("pass_events", [])),
                "collision_events": serializable(info.get("collision_events", [])),
            })

        if terminated:
            final_step = t + 1
            break

    term_info = last_info.get("termination", {})
    scores = last_info.get("team_scores", {})
    passes = last_info.get("team_pass_count", {})
    result = {
        "episode": episode_idx,
        "steps": final_step,
        "red_score": team_value(scores, "RED"),
        "blue_score": team_value(scores, "BLUE"),
        "red_passes": team_value(passes, "RED"),
        "blue_passes": team_value(passes, "BLUE"),
        "winner": term_info.get("winner", "UNKNOWN"),
        "reason": term_info.get("reason", "unknown"),
        "collision_count": len(env.collision_events),
        "total_rewards": serializable(total_rewards),
    }
    return result, step_rows


def summarize_results(results: List[dict]) -> dict:
    winners = {"RED": 0, "BLUE": 0, "DRAW": 0, "DOUBLE_LOSS": 0, "UNKNOWN": 0}
    for row in results:
        winners[row["winner"]] = winners.get(row["winner"], 0) + 1

    n = max(len(results), 1)
    return {
        "episodes": len(results),
        "win_count": winners,
        "red_win_rate": winners.get("RED", 0) / n,
        "blue_win_rate": winners.get("BLUE", 0) / n,
        "draw_rate": winners.get("DRAW", 0) / n,
        "double_loss_rate": winners.get("DOUBLE_LOSS", 0) / n,
        "collision_rate": sum(1 for r in results if r["collision_count"] > 0) / n,
        "avg_steps": float(np.mean([r["steps"] for r in results])) if results else 0.0,
        "avg_red_score": float(np.mean([r["red_score"] for r in results])) if results else 0.0,
        "avg_blue_score": float(np.mean([r["blue_score"] for r in results])) if results else 0.0,
        "avg_red_passes": float(np.mean([r["red_passes"] for r in results])) if results else 0.0,
        "avg_blue_passes": float(np.mean([r["blue_passes"] for r in results])) if results else 0.0,
    }


class ExperimentRecorder:
    """把实验结果保存成 CSV / JSON，并可生成奖励和比分曲线。"""

    def __init__(self, root_dir: str | Path = "runs", run_name: Optional[str] = None):
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.run_dir = Path(root_dir) / (run_name or f"run-{timestamp}")
        self.run_dir.mkdir(parents=True, exist_ok=True)

    def save(self, results: List[dict], step_rows: List[dict], summary: dict):
        self._write_csv(self.run_dir / "episodes.csv", results)
        self._write_csv(self.run_dir / "steps.csv", step_rows)
        (self.run_dir / "summary.json").write_text(
            json.dumps(serializable(summary), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (self.run_dir / "episodes.json").write_text(
            json.dumps(serializable(results), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self.plot_curves(step_rows)

    def plot_curves(self, step_rows: List[dict]):
        if not step_rows:
            return
        patch_matplotlib_cbook()
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(2, 1, figsize=(10, 7), sharex=True)
        for ep in sorted({row["episode"] for row in step_rows}):
            rows = [row for row in step_rows if row["episode"] == ep]
            steps = [row["step"] for row in rows]
            axes[0].plot(steps, [row["red_score"] for row in rows], color="#d62728", alpha=0.35)
            axes[0].plot(steps, [row["blue_score"] for row in rows], color="#1f77b4", alpha=0.35)
            axes[1].plot(steps, [row["reward_sum"] for row in rows], color="#333333", alpha=0.35)
        axes[0].set_ylabel("Team score")
        axes[1].set_ylabel("Reward sum")
        axes[1].set_xlabel("Step")
        axes[0].set_title("Score curves")
        axes[1].set_title("Reward curves")
        fig.tight_layout()
        fig.savefig(self.run_dir / "curves.png", dpi=180)
        plt.close(fig)

    @staticmethod
    def _write_csv(path: Path, rows: List[dict]):
        if not rows:
            path.write_text("", encoding="utf-8")
            return
        fieldnames = list(rows[0].keys())
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow({k: json.dumps(serializable(v), ensure_ascii=False) if isinstance(v, (dict, list)) else v
                                 for k, v in row.items()})


def run_experiment(env, policy, episodes: int, seed: int, recorder: Optional[ExperimentRecorder] = None):
    results = []
    step_rows = []
    for ep in range(episodes):
        result, rows = run_one_episode(env, policy, ep, seed=seed + ep * 1000)
        results.append(result)
        step_rows.extend(rows)
    summary = summarize_results(results)
    if recorder is not None:
        recorder.save(results, step_rows, summary)
    return results, summary, step_rows
