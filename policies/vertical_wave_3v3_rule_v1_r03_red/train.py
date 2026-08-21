from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare a checkpoint for the vertical_wave_3v3 rule policy.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--seed", required=True, type=int)
    parser.add_argument("--output_dir", required=True)
    parser.add_argument("--max_steps", required=True, type=int)
    parser.add_argument("--wall_time_limit", required=True, type=int)
    parser.add_argument("--resume_from")
    parser.add_argument("--log_interval", type=int, default=100)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        config_path = Path(args.config)
        scenario_path = Path(args.scenario)
        if not config_path.is_file() or not scenario_path.exists():
            return 1
        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        checkpoint = {
            "policy_id": "vertical_wave_3v3_rule_v1_r03_red",
            "algorithm_family": "rule_based_safe_swarm",
            "optimization_mode": "red",
            "seed": args.seed,
            "max_steps": args.max_steps,
            "wall_time_limit": args.wall_time_limit,
            "resume_from": args.resume_from,
            "log_interval": args.log_interval,
            "config": config,
        }
        (output_dir / "checkpoint.json").write_text(json.dumps(checkpoint, indent=2), encoding="utf-8")
        return 0
    except MemoryError:
        return 3
    except Exception as error:
        print(f"training setup failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
