from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
from pathlib import Path

import yaml


POLICY_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = POLICY_DIR.parents[1]
SCENARIO_DIR = PROJECT_ROOT / "scenarios" / "drone_ring_delay_2_001"


def test_short_training_emits_loadable_multistep_checkpoint(tmp_path: Path) -> None:
    config = yaml.safe_load((POLICY_DIR / "default_config.yaml").read_text(encoding="utf-8"))
    config["rollout_steps"] = 64
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    environment = os.environ.copy()
    source_root = str(PROJECT_ROOT / "src")
    environment["PYTHONPATH"] = os.pathsep.join(
        [source_root, environment.get("PYTHONPATH", "")]
    )
    completed = subprocess.run(
        [
            sys.executable,
            str(POLICY_DIR / "train.py"),
            "--config",
            str(config_path),
            "--scenario",
            str(SCENARIO_DIR),
            "--seed",
            "3",
            "--output_dir",
            str(tmp_path / "run"),
            "--max_steps",
            "128",
            "--wall_time_limit",
            "60",
            "--log_interval",
            "64",
        ],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=90,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    run_dir = tmp_path / "run"
    log = json.loads((run_dir / "training_log.json").read_text(encoding="utf-8"))
    assert log["algorithm"] == "ppo"
    assert log["total_steps"] == 128
    with (run_dir / "training_curves.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) >= 2
    assert len({row["step"] for row in rows}) >= 2
    events = {row["event"] for row in rows}
    assert {"episode", "optimizer_update", "evaluation"} <= events
    assert sum(row["event"] == "evaluation" for row in rows) >= 2
    assert log["telemetry_counts"]["episode"] >= 1
    assert log["telemetry_counts"]["optimizer_update"] >= 1
    assert (run_dir / log["checkpoint_path"]).is_file()
