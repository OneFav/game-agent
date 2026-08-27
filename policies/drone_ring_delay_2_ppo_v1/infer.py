from __future__ import annotations

import argparse
import json
from pathlib import Path

from game_agent.autoresearch.runner import evaluate_policy_dir


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate a trained PPO checkpoint.")
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--config", default=None)
    parser.add_argument("--seeds", default="0,1,2")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    result = evaluate_policy_dir(
        policy_dir=Path(__file__).resolve().parent,
        scenario_dir=Path(args.scenario),
        config_path=Path(args.config) if args.config else None,
        checkpoint=Path(args.checkpoint),
        seeds=[int(value) for value in args.seeds.split(",") if value.strip()],
    )
    text = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
