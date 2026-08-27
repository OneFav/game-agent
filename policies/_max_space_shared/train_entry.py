from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import yaml

from .policy_core import PREPROCESSING_ID


def main(package_dir: Path, package_spec: Mapping[str, Any], argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Materialize a deterministic rule-policy checkpoint.")
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
            raise ValueError("--resume_from must be an existing checkpoint")
        if args.max_steps < 0 or args.wall_time_limit <= 0 or args.log_interval <= 0:
            raise ValueError("budgets and log_interval must be positive (max_steps may be zero)")
        config = _read_yaml(config_path)
        PolicyClass = _load_policy_class(package_dir)
        policy = PolicyClass(config, _training_env_spec(package_spec))
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        checkpoint = {
            "schema_version": "rule_checkpoint/v1",
            "policy_id": str(package_spec["policy_id"]),
            "config": policy.config,
            "checkpoint_binding": {
                "policy_id": str(package_spec["policy_id"]),
                "method": str(package_spec["method_name"]),
                "action_dimension": int(package_spec["dimension"]),
                "preprocessing": PREPROCESSING_ID,
            },
        }
        checkpoint_path = output_dir / "checkpoint_final.pt"
        checkpoint_path.write_text(
            json.dumps(checkpoint, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        checkpoint_hash = hashlib.sha256(checkpoint_path.read_bytes()).hexdigest()
        with (output_dir / "training_curves.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["step", "episode", "reward_mean", "actor_loss", "critic_loss", "evaluation_primary"])
            writer.writerow([0, 0, 0.0, 0.0, 0.0, ""])
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        training_log = {
            "schema_version": "1.0",
            "policy_id": str(package_spec["policy_id"]),
            "scenario_id": str(package_spec["scenario_id"]),
            "termination_reason": "rule_policy_materialized",
            "checkpoint_path": checkpoint_path.name,
            "checkpoint_hash": f"sha256:{checkpoint_hash}",
            "status": "completed",
            "trainer": "no_op_rule_parameter_materializer",
            "convergence_evidence": False,
            "curve_interpretation": "schema-only row; not evidence of learning or convergence",
            "config_used": policy.config,
            "seed": args.seed,
            "max_steps": args.max_steps,
            "wall_time_limit": args.wall_time_limit,
            "log_interval": args.log_interval,
            "resume_from": args.resume_from,
            "started_at": now,
            "finished_at": now,
            "total_steps": 0,
        }
        (output_dir / "training_log.json").write_text(
            json.dumps(training_log, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        (output_dir / "stdout.log").write_text(
            "rule policy materialized; the single curve row is not convergence evidence\n",
            encoding="utf-8",
        )
        return 0
    except MemoryError:
        return 3
    except (OSError, TypeError, ValueError, yaml.YAMLError) as error:
        print(f"training configuration error: {error}", file=sys.stderr)
        return 1


def _read_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(value, dict):
        raise ValueError(f"YAML root must be a mapping: {path}")
    return value


def _load_policy_class(package_dir: Path) -> type:
    policy_path = package_dir / "policy.py"
    module_name = f"_max_space_train_policy_{abs(hash(policy_path.resolve()))}"
    spec = importlib.util.spec_from_file_location(module_name, policy_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load policy: {policy_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.PolicyClass


def _training_env_spec(package_spec: Mapping[str, Any]) -> dict[str, Any]:
    dimension = int(package_spec["dimension"])
    return {
        "action_space": {
            "shape": [dimension],
            "low": [-1.0] * dimension,
            "high": [1.0] * dimension,
        }
    }
