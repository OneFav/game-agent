import sys
from pathlib import Path

import yaml


def _ensure_project_root_on_path():
    current = Path(__file__).resolve()
    for candidate in (current.parent, *current.parents):
        if (candidate / "game_agent").is_dir():
            sys.path.insert(0, str(candidate))
            return


_ensure_project_root_on_path()

from game_agent.envs.drone_ring_game.env import DroneRingEnv


def make_env(config=None):
    config_path = Path(__file__).with_name("env_config.yaml")
    base = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    base.update(config or {})
    return DroneRingEnv(base)
