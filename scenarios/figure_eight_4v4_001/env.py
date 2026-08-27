from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import yaml

from game_agent.envs.swarm_combat import EnvConfig, SwarmCombatEnv
from game_agent.envs.swarm_combat.entities import Team


class Box:
    def __init__(self, low: np.ndarray, high: np.ndarray, shape: tuple[int, ...], dtype: Any = np.float32) -> None:
        self.low = low
        self.high = high
        self.shape = shape
        self.dtype = dtype

    def sample(self) -> np.ndarray:
        return np.zeros(self.shape, dtype=self.dtype)


AGENT_IDS = [
    "red_racer_0",
    "red_racer_1",
    "red_defender_0",
    "red_defender_1",
    "blue_racer_0",
    "blue_racer_1",
    "blue_defender_0",
    "blue_defender_1",
]
AGENT_INDEX = {name: idx for idx, name in enumerate(AGENT_IDS)}
AGENT_TEAM = {name: ("red" if name.startswith("red") else "blue") for name in AGENT_IDS}
DEFAULT_OBS_DIM = 110
DEFAULT_ACTION_LOW = np.array([-10.0, -10.0, -10.0], dtype=np.float32)
DEFAULT_ACTION_HIGH = np.array([10.0, 10.0, 10.0], dtype=np.float32)
DEFAULT_RED_POSITIONS = [
    [-22.0, -6.0, 4.0],
    [-22.0, -2.0, 5.0],
    [-24.0, -8.0, 4.5],
    [-24.0, 0.0, 5.5],
]
DEFAULT_BLUE_POSITIONS = [
    [22.0, 6.0, 4.0],
    [22.0, 2.0, 5.0],
    [24.0, 8.0, 4.5],
    [24.0, 0.0, 5.5],
]


class FigureEight4v4Env:
    metadata = {"render_modes": ["human", "rgb_array"], "name": "figure_eight_4v4_001_v0"}
    possible_agents = AGENT_IDS[:]

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        merged = _load_config()
        if config:
            merged.update(config)
        self.config = merged
        self.agents = AGENT_IDS[:]
        self.observation_shape = (int(merged.get("observation_dim", DEFAULT_OBS_DIM)),)
        self.action_shape = (3,)
        self._action_low = np.asarray(merged.get("action_low", DEFAULT_ACTION_LOW.tolist()), dtype=np.float32)
        self._action_high = np.asarray(merged.get("action_high", DEFAULT_ACTION_HIGH.tolist()), dtype=np.float32)
        self._obs_space = Box(
            low=np.full(self.observation_shape, -50.0, dtype=np.float32),
            high=np.full(self.observation_shape, 50.0, dtype=np.float32),
            shape=self.observation_shape,
        )
        self._act_space = Box(low=self._action_low, high=self._action_high, shape=self.action_shape)
        self._action_clipped = {agent_id: False for agent_id in self.agents}
        self._env = self._build_env(merged)
        self.max_steps = int(self._env.cfg.max_steps)

    def reset(self, seed: int | None = None, options: dict[str, Any] | None = None):
        del options
        self._action_clipped = {agent_id: False for agent_id in self.agents}
        observations, _info = self._env.reset(seed=seed)
        return self._map_observations(observations), self._info_dict()

    def step(self, actions: dict[str, np.ndarray]):
        mapped_actions: dict[int, np.ndarray] = {}
        for agent_id in self.agents:
            raw = np.asarray(actions.get(agent_id, np.zeros(self.action_shape, dtype=np.float32)), dtype=np.float32)
            if raw.shape != self.action_shape:
                raw = np.zeros(self.action_shape, dtype=np.float32)
            clipped = np.clip(raw, self._action_low, self._action_high).astype(np.float32)
            self._action_clipped[agent_id] = bool(np.any(np.abs(clipped - raw) > 1e-6))
            mapped_actions[AGENT_INDEX[agent_id]] = clipped

        observations, rewards, terminated, truncated, _info = self._env.step(mapped_actions)
        return (
            self._map_observations(observations),
            self._map_scalars(rewards),
            self._map_bools(terminated),
            self._map_bools(truncated),
            self._info_dict(),
        )

    def observation_space(self, agent: str) -> Box:
        del agent
        return self._obs_space

    def action_space(self, agent: str) -> Box:
        del agent
        return self._act_space

    def render(self):
        return None

    def close(self) -> None:
        return None

    @property
    def base_env(self) -> SwarmCombatEnv:
        return self._env

    def _map_observations(self, observations: dict[int, np.ndarray]) -> dict[str, np.ndarray]:
        return {
            agent_id: np.asarray(observations[AGENT_INDEX[agent_id]], dtype=np.float32).reshape(self.observation_shape)
            for agent_id in self.agents
        }

    def _map_scalars(self, values: dict[int, float]) -> dict[str, float]:
        return {agent_id: float(values[AGENT_INDEX[agent_id]]) for agent_id in self.agents}

    def _map_bools(self, values: dict[int, bool]) -> dict[str, bool]:
        return {agent_id: bool(values[AGENT_INDEX[agent_id]]) for agent_id in self.agents}

    def _info_dict(self) -> dict[str, dict[str, Any]]:
        collision_events = list(self._env.collision_events)
        pass_events = list(self._env.last_pass_events)
        red_score = float(self._env.team_scores[Team.RED])
        blue_score = float(self._env.team_scores[Team.BLUE])
        red_pass = int(self._env.team_pass_count[Team.RED])
        blue_pass = int(self._env.team_pass_count[Team.BLUE])
        out_of_bounds = any(event.get("type") == "out_of_bounds" for event in collision_events)
        collision = any(event.get("type") != "out_of_bounds" for event in collision_events)
        red_win = red_score > blue_score and not collision and not out_of_bounds
        blue_win = blue_score > red_score and not collision and not out_of_bounds

        infos: dict[str, dict[str, Any]] = {}
        for agent_id in self.agents:
            team = AGENT_TEAM[agent_id]
            infos[agent_id] = {
                "collision": collision,
                "out_of_bounds": out_of_bounds,
                "ring_passed_count": red_pass if team == "red" else blue_pass,
                "gate_passed_count": red_pass if team == "red" else blue_pass,
                "communication_dropped": False,
                "action_clipped": bool(self._action_clipped[agent_id]),
                "team_score": red_score if team == "red" else blue_score,
                "blue_team_score": blue_score if team == "red" else red_score,
                "opponent_team_score": blue_score if team == "red" else red_score,
                "score_margin": red_score - blue_score if team == "red" else blue_score - red_score,
                "red_win": red_win,
                "blue_win": blue_win,
                "pass_events": pass_events,
                "step": int(self._env.step_count),
            }
        return infos

    def _build_env(self, merged: dict[str, Any]) -> SwarmCombatEnv:
        cfg = EnvConfig().with_updates(
            dt=float(merged.get("dt", 0.05)),
            max_steps=int(merged.get("max_steps", 1200)),
            n_red=int(merged.get("n_red", 4)),
            n_red_racers=int(merged.get("n_red_racers", 2)),
            n_blue=int(merged.get("n_blue", 4)),
            n_blue_racers=int(merged.get("n_blue_racers", 2)),
            gate_layout=str(merged.get("gate_layout", "figure_eight")),
            rewards__gate_pass=float(merged.get("gate_pass_reward", 1.0)),
            drone__safety_radius=float(merged.get("safety_radius", 0.45)),
            drone__inter_team_safe_dist=float(merged.get("inter_team_safe_dist", 0.8)),
            drone__intra_team_safe_dist=float(merged.get("intra_team_safe_dist", 0.7)),
            spawn_red__mode=str(merged.get("spawn_mode", "fixed")),
            spawn_blue__mode=str(merged.get("spawn_mode", "fixed")),
            spawn_red__fixed_positions=merged.get("spawn_red_positions", DEFAULT_RED_POSITIONS),
            spawn_blue__fixed_positions=merged.get("spawn_blue_positions", DEFAULT_BLUE_POSITIONS),
            rules__collision_ends_episode=bool(merged.get("collision_ends_episode", True)),
            rules__out_of_bounds_ends_episode=bool(merged.get("out_of_bounds_ends_episode", True)),
        )
        cfg.drone_types["racer"].dynamics = str(merged.get("racer_dynamics", "damped_double_integrator"))
        cfg.drone_types["racer"].max_speed = float(merged.get("racer_max_speed", 8.0))
        cfg.drone_types["racer"].max_accel = float(merged.get("racer_max_accel", 9.0))
        cfg.drone_types["racer"].drag = float(merged.get("racer_drag", 0.12))
        cfg.drone_types["defender"].dynamics = str(merged.get("defender_dynamics", "damped_double_integrator"))
        cfg.drone_types["defender"].max_speed = float(merged.get("defender_max_speed", 7.0))
        cfg.drone_types["defender"].max_accel = float(merged.get("defender_max_accel", 8.0))
        cfg.drone_types["defender"].drag = float(merged.get("defender_drag", 0.18))
        target_score = merged.get("target_score")
        cfg.rules.target_score = None if target_score in (None, "null") else float(target_score)
        seed = merged.get("seed")
        if seed is not None:
            cfg.seed = int(seed)
        return SwarmCombatEnv(cfg)


def _load_config() -> dict[str, Any]:
    path = Path(__file__).with_name("env_config.yaml")
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def make_env(config: dict[str, Any] | None = None) -> FigureEight4v4Env:
    return FigureEight4v4Env(config)
