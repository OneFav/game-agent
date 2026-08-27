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
        "config_path": str(config_path),
        "config": config_used,
        "scenario": str(scenario_path),
        "resume_from": str(resume_path) if resume_path else None,
    }
    checkpoint_path = output_dir / "checkpoint_final.pt"
    checkpoint_path.write_text(json.dumps(checkpoint, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
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
    (output_dir / "training_curves.csv").write_text("step,reward,loss\n0,0.0,0.0\n", encoding="utf-8")
    (output_dir / "training_log.json").write_text(json.dumps(log, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (output_dir / "stdout.log").write_text("no-op training completed\n", encoding="utf-8")
    return 2 if timed_out else 0


if __name__ == "__main__":
    raise SystemExit(main())
