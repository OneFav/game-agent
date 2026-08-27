from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import yaml


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate 3D trajectory figures for compliant vertical_wave_3v3 rounds.")
    parser.add_argument("--seed", type=int, default=23)
    parser.add_argument("--round", dest="round_id", type=int, help="Optional single round id to render.")
    return parser.parse_args()


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def load_module(path: Path, module_name: str) -> Any:
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def load_rounds(game_dir: Path, selected_round: int | None) -> list[dict[str, Any]]:
    with (game_dir / "round_history.json").open("r", encoding="utf-8") as handle:
        rounds = json.load(handle)
    rendered = [row for row in rounds if row.get("status") in {"PASS", "FAIL_STOP"}]
    if selected_round is not None:
        rendered = [row for row in rendered if int(row["round_id"]) == selected_round]
    return rendered


def rollout_and_save(root: Path, round_row: dict[str, Any], seed: int, out_dir: Path) -> Path:
    scenario_dir = root / "scenarios" / "vertical_wave_3v3_001"
    policy_dir = root / round_row["policy_dir"]
    exp_dir = root / round_row["exp_dir"]

    env_module = load_module(scenario_dir / "env.py", f"vertical_wave_env_r{round_row['round_id']}")
    policy_module = load_module(policy_dir / "policy.py", f"vertical_wave_policy_r{round_row['round_id']}")

    task_spec = yaml.safe_load((scenario_dir / "task_spec.yaml").read_text(encoding="utf-8")) or {}
    config = yaml.safe_load((exp_dir / "best_config.yaml").read_text(encoding="utf-8")) or {}
    policy = policy_module.PolicyClass(config, task_spec)
    env = env_module.make_env()

    policy.reset(seed)
    env.reset(seed=seed)
    for _ in range(int(getattr(env, "max_steps", 800))):
        actions = policy.compute_actions(env)
        _obs, _rewards, terminated, truncated, _infos = env.step(actions)
        if all(terminated.values()) or all(truncated.values()):
            break

    sys.path.insert(0, str(root / "src"))
    from game_agent.envs.swarm_combat.visualizer import save_trajectory_figure

    round_id = int(round_row["round_id"])
    side = str(round_row["target_side"])
    status = str(round_row["status"]).lower()
    out_path = out_dir / f"trajectory_3d_round{round_id:02d}_{side}_{status}_seed{seed}.png"
    title = f"vertical_wave_3v3 Round {round_id} ({side}, {round_row['status']}) seed {seed}"
    save_trajectory_figure(env.base_env, str(out_path), title=title)
    return out_path


def main() -> int:
    args = parse_args()
    root = repo_root()
    sys.path.insert(0, str(root / "src"))
    game_dir = root / "game" / "vertical_wave_3v3"
    out_dir = game_dir / "figures"
    out_dir.mkdir(parents=True, exist_ok=True)

    rounds = load_rounds(game_dir, args.round_id)
    if not rounds:
        raise RuntimeError("no compliant executed rounds found")

    outputs = [rollout_and_save(root, row, args.seed, out_dir) for row in rounds]
    for output in outputs:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
