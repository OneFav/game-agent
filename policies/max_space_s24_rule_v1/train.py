from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml


POLICY_ID = 'max_space_s24_rule_v1'
SCENARIO_ID = 'S24'
METHOD = 'role_aware_escort_defense_rule'
DIMENSION = 3
PREPROCESSING = 'max_space_local_obs_v1'
CHECKPOINT_BINDING = {'method': 'role_aware_escort_defense_rule',
 'observation_contract': 'scenario.observation_space:vector',
 'action_contract': 'scenario.action_space:continuous:3d',
 'preprocessing': 'max_space_local_obs_v1',
 'scenario_id': 'S24',
 'agent_count': 8,
 'parameter_sharing': 'side_specific_dispatch'}


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
        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        if not isinstance(config, dict):
            raise ValueError("config root must be a mapping")
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        checkpoint = {
            "schema_version": "rule_checkpoint/v1",
            "policy_id": POLICY_ID,
            "action_shape": [DIMENSION],
            "config": config,
            "checkpoint_binding": CHECKPOINT_BINDING,
        }
        checkpoint_path = output_dir / "checkpoint_final.pt"
        checkpoint_path.write_text(json.dumps(checkpoint, indent=2) + "\n", encoding="utf-8")
        checkpoint_hash = hashlib.sha256(checkpoint_path.read_bytes()).hexdigest()
        with (output_dir / "training_curves.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["step", "episode", "reward_mean", "actor_loss", "critic_loss", "evaluation_primary"])
            writer.writerow([0, 0, 0.0, 0.0, 0.0, ""])
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        log = {
            "schema_version": "1.0",
            "policy_id": POLICY_ID,
            "scenario_id": SCENARIO_ID,
            "termination_reason": "rule_policy_materialized",
            "checkpoint_path": checkpoint_path.name,
            "checkpoint_hash": f"sha256:{checkpoint_hash}",
            "status": "completed",
            "trainer": "no_op_rule_parameter_materializer",
            "convergence_evidence": False,
            "curve_interpretation": "schema-only row; not convergence evidence",
            "config_used": config,
            "seed": args.seed,
            "started_at": now,
            "finished_at": now,
            "total_steps": 0,
        }
        (output_dir / "training_log.json").write_text(json.dumps(log, indent=2) + "\n", encoding="utf-8")
        (output_dir / "stdout.log").write_text("rule policy materialized; not convergence evidence\n", encoding="utf-8")
        return 0
    except MemoryError:
        return 3
    except Exception as error:
        print(f"training configuration error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
