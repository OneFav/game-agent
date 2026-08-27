from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import yaml


def _add_src_to_path() -> None:
    current = Path(__file__).resolve()
    for parent in current.parents:
        src = parent / "src"
        if (src / "game_agent" / "envs" / "swarm_combat" / "env.py").is_file():
            if str(src) not in sys.path:
                sys.path.insert(0, str(src))
            return


_add_src_to_path()

from game_agent.envs.swarm_combat import EnvConfig, SwarmCombatEnv


AGENT_ORDER = ["red_racer_0", "red_defender_0", "blue_racer_0", "blue_defender_0"]
AGENT_TO_ID = {name: index for index, name in enumerate(AGENT_ORDER)}
ID_TO_AGENT = {index: name for name, index in AGENT_TO_ID.items()}


@dataclass
class Box:
    low: np.ndarray
    high: np.ndarray
    shape: tuple[int, ...]
    dtype: Any = np.float32

    def sample(self) -> np.ndarray:
        return np.zeros(self.shape, dtype=self.dtype)


class SwarmCombatScenarioEnv:
    metadata = {"render_modes": ["human", "rgb_array"], "name": "wide_slalom_2v2_swarm_v1"}

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._raw_config = _load_config(config)
        self._cfg = _build_env_config(self._raw_config)
        self._base_env = SwarmCombatEnv(self._cfg)
        initial_obs, _ = self._base_env.reset(seed=int(self._raw_config.get("seed", self._cfg.seed)))
        obs_dim = len(next(iter(initial_obs.values()))) if initial_obs else 0
        self.observation_shape = (obs_dim,)
        self.action_shape = (4,)
        self.max_steps = self._cfg.max_steps
        self.agents = AGENT_ORDER[:]
        self.possible_agents = AGENT_ORDER[:]
        self._action_low = np.full(self.action_shape, -1.0, dtype=np.float32)
        self._action_high = np.full(self.action_shape, 1.0, dtype=np.float32)
        self._observation_box = Box(
            low=np.full(self.observation_shape, -100.0, dtype=np.float32),
            high=np.full(self.observation_shape, 100.0, dtype=np.float32),
            shape=self.observation_shape,
        )
        self._action_box = Box(low=self._action_low, high=self._action_high, shape=self.action_shape)
        self._accel_scale = self._current_accel_scale()
        self._last_action_clipped = {agent_id: False for agent_id in AGENT_ORDER}

    @property
    def raw_env(self) -> SwarmCombatEnv:
        return self._base_env

    @property
    def history(self) -> list[dict[str, Any]]:
        return self._base_env.history

    def reset(self, seed: int | None = None, options: dict[str, Any] | None = None):
        del options
        actual_seed = int(self._raw_config.get("seed", self._cfg.seed) if seed is None else seed)
        observations, _ = self._base_env.reset(seed=actual_seed)
        self.agents = AGENT_ORDER[:]
        self._accel_scale = self._current_accel_scale()
        self._last_action_clipped = {agent_id: False for agent_id in AGENT_ORDER}
        infos = {agent_id: self._build_info(agent_id, {}) for agent_id in AGENT_ORDER}
        return self._map_observations(observations), infos

    def step(self, actions: dict[str, np.ndarray]):
        mapped_actions: dict[int, np.ndarray] = {}
        for agent_id in AGENT_ORDER:
            raw_action = np.asarray(actions.get(agent_id, np.zeros(self.action_shape, dtype=np.float32)), dtype=np.float32)
            if raw_action.shape != self.action_shape:
                raise ValueError(f"Action shape for {agent_id} must be {self.action_shape}, got {raw_action.shape}")
            clipped = np.clip(raw_action, self._action_low, self._action_high)
            self._last_action_clipped[agent_id] = bool(np.any(clipped != raw_action))
            mapped_actions[AGENT_TO_ID[agent_id]] = clipped[:3] * self._accel_scale[agent_id]

        observations, rewards, terminations, truncations, global_info = self._base_env.step(mapped_actions)
        mapped_obs = self._map_observations(observations)
        mapped_rewards = {ID_TO_AGENT[agent_id]: float(value) for agent_id, value in rewards.items()}
        mapped_terminations = {ID_TO_AGENT[agent_id]: bool(value) for agent_id, value in terminations.items()}
        mapped_truncations = {ID_TO_AGENT[agent_id]: bool(value) for agent_id, value in truncations.items()}
        infos = {agent_id: self._build_info(agent_id, global_info) for agent_id in AGENT_ORDER}
        return mapped_obs, mapped_rewards, mapped_terminations, mapped_truncations, infos

    def observation_space(self, agent: str) -> Box:
        del agent
        return self._observation_box

    def action_space(self, agent: str) -> Box:
        del agent
        return self._action_box

    def render(self):
        return None

    def close(self) -> None:
        return None

    def _current_accel_scale(self) -> dict[str, float]:
        scale: dict[str, float] = {}
        for drone in self._base_env.drones:
            scale[ID_TO_AGENT[drone.id]] = float(getattr(drone.dynamics, "max_accel", self._cfg.drone.max_accel))
        return scale

    def _map_observations(self, observations: dict[int, np.ndarray]) -> dict[str, np.ndarray]:
        return {ID_TO_AGENT[agent_id]: np.asarray(obs, dtype=np.float32) for agent_id, obs in observations.items()}

    def _build_info(self, agent_id: str, global_info: dict[str, Any]) -> dict[str, Any]:
        drone = next(drone for drone in self._base_env.drones if drone.id == AGENT_TO_ID[agent_id])
        collision_events = list(global_info.get("collision_events", []))
        collision = any(event.get("type") != "out_of_bounds" for event in collision_events)
        out_of_bounds = any(event.get("type") == "out_of_bounds" for event in collision_events)
        return {
            "collision": collision,
            "out_of_bounds": out_of_bounds,
            "ring_passed_count": int(drone.gate_pass_count),
            "gate_passed_count": int(drone.gate_pass_count),
            "communication_dropped": False,
            "action_clipped": bool(self._last_action_clipped.get(agent_id, False)),
            "team": "red" if agent_id.startswith("red") else "blue",
            "role": "racer" if "racer" in agent_id else "defender",
            "team_scores": _enum_map_to_names(global_info.get("team_scores", self._base_env.team_scores)),
            "team_pass_count": _enum_map_to_names(global_info.get("team_pass_count", self._base_env.team_pass_count)),
            "termination": _enum_map_to_names(global_info.get("termination", {})),
            "raw_env": self._base_env,
            "raw_info": global_info,
        }


def _load_config(overrides: dict[str, Any] | None) -> dict[str, Any]:
    config_path = Path(__file__).with_name("env_config.yaml")
    base = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    return _deep_update(base, overrides or {})


def _deep_update(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_update(merged[key], value)
        else:
            merged[key] = value
    return merged


def _build_env_config(raw: dict[str, Any]) -> EnvConfig:
    cfg = EnvConfig()
    teams = raw.get("teams", {})
    red = teams.get("red", {})
    blue = teams.get("blue", {})
    cfg = cfg.with_updates(
        dt=float(raw.get("dt", cfg.dt)),
        max_steps=int(raw.get("max_steps", cfg.max_steps)),
        n_red=int(red.get("count", cfg.n_red)),
        n_red_racers=int(red.get("racers", cfg.n_red_racers)),
        n_blue=int(blue.get("count", cfg.n_blue)),
        n_blue_racers=int(blue.get("racers", cfg.n_blue_racers)),
        seed=int(raw.get("seed", cfg.seed)),
        gate_layout=str(raw.get("gate_layout", cfg.gate_layout)),
    )

    field = raw.get("field", {})
    cfg.field.x_range = tuple(float(value) for value in field.get("x_range", cfg.field.x_range))
    cfg.field.y_range = tuple(float(value) for value in field.get("y_range", cfg.field.y_range))
    cfg.field.z_range = tuple(float(value) for value in field.get("z_range", cfg.field.z_range))

    drone = raw.get("drone", {})
    cfg.drone.max_speed = float(drone.get("max_speed", cfg.drone.max_speed))
    cfg.drone.max_accel = float(drone.get("max_accel", cfg.drone.max_accel))
    cfg.drone.safety_radius = float(drone.get("safety_radius", cfg.drone.safety_radius))
    cfg.drone.inter_team_safe_dist = float(drone.get("inter_team_safe_dist", cfg.drone.inter_team_safe_dist))
    cfg.drone.intra_team_safe_dist = float(drone.get("intra_team_safe_dist", cfg.drone.intra_team_safe_dist))

    drone_types = raw.get("drone_types", {})
    for type_name in ("racer", "defender"):
        if type_name not in drone_types:
            continue
        type_cfg = drone_types[type_name]
        cfg.drone_types[type_name].dynamics = str(type_cfg.get("dynamics", cfg.drone_types[type_name].dynamics))
        cfg.drone_types[type_name].max_speed = float(type_cfg.get("max_speed", cfg.drone_types[type_name].max_speed))
        cfg.drone_types[type_name].max_accel = float(type_cfg.get("max_accel", cfg.drone_types[type_name].max_accel))
        cfg.drone_types[type_name].drag = float(type_cfg.get("drag", cfg.drone_types[type_name].drag))

    cfg.rewards.gate_pass = float(raw.get("gate_pass_reward", cfg.rewards.gate_pass))
    cfg.rules.target_score = raw.get("target_score", cfg.rules.target_score)

    for spawn_name, target in (("spawn_red", cfg.spawn_red), ("spawn_blue", cfg.spawn_blue)):
        spawn_cfg = raw.get(spawn_name, {})
        target.mode = str(spawn_cfg.get("mode", target.mode))
        if "fixed_positions" in spawn_cfg:
            target.fixed_positions = [list(map(float, point)) for point in spawn_cfg.get("fixed_positions", [])]
    return cfg


def _enum_map_to_names(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key.name if hasattr(key, "name") else str(key): _enum_map_to_names(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_enum_map_to_names(item) for item in value]
    return value


def make_env(config: dict[str, Any] | None = None) -> SwarmCombatScenarioEnv:
    return SwarmCombatScenarioEnv(config)
