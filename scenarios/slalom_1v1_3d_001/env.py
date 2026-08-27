from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import yaml


def _ensure_src_on_path() -> None:
    current = Path(__file__).resolve()
    for parent in current.parents:
        src = parent / "src"
        if (src / "game_agent" / "envs" / "swarm_combat" / "env.py").is_file():
            if str(src) not in sys.path:
                sys.path.insert(0, str(src))
            return
    raise RuntimeError("Cannot locate project src/ directory for swarm_combat imports.")


_ensure_src_on_path()

from game_agent.envs.swarm_combat import EnvConfig, SwarmCombatEnv
from game_agent.envs.swarm_combat.entities import Team


@dataclass
class Box:
    low: np.ndarray
    high: np.ndarray
    shape: tuple[int, ...]
    dtype: Any = np.float32

    def sample(self) -> np.ndarray:
        return np.zeros(self.shape, dtype=self.dtype)


class Slalom1v13DEnv:
    metadata = {"render_modes": ["human", "rgb_array"], "name": "slalom_1v1_3d_001_v0"}

    agents = ["red_racer_0", "blue_racer_0"]
    possible_agents = agents[:]
    observation_shape = (64,)
    action_shape = (3,)

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = _load_config(config)
        self.max_steps = int(self._config.get("max_steps", 400))
        self._action_low = np.array([-1.0, -1.0, -1.0], dtype=np.float32)
        self._action_high = np.array([1.0, 1.0, 1.0], dtype=np.float32)
        self._obs_space = Box(low=_obs_low(), high=_obs_high(), shape=self.observation_shape)
        self._act_space = Box(low=self._action_low, high=self._action_high, shape=self.action_shape)
        self._native_env = self._build_native_env(self._config)
        self._id_to_native = {"red_racer_0": 0, "blue_racer_0": 1}
        self._native_to_id = {value: key for key, value in self._id_to_native.items()}
        self._ordered_gate_indices = {"red_racer_0": 0, "blue_racer_0": len(self._native_env.gates) - 1}
        self._team_scores = {"red_racer_0": 0.0, "blue_racer_0": 0.0}
        self._action_violation_count = 0
        self._step_count = 0
        self._last_metrics = {}

    @property
    def native_env(self) -> SwarmCombatEnv:
        return self._native_env

    def observation_space(self, agent: str) -> Box:
        del agent
        return self._obs_space

    def action_space(self, agent: str) -> Box:
        del agent
        return self._act_space

    def reset(self, seed: int | None = None, options: dict[str, Any] | None = None):
        del options
        self._native_env = self._build_native_env(self._config)
        native_obs, _ = self._native_env.reset(seed=seed)
        self._ordered_gate_indices = {"red_racer_0": 0, "blue_racer_0": len(self._native_env.gates) - 1}
        self._team_scores = {"red_racer_0": 0.0, "blue_racer_0": 0.0}
        self._action_violation_count = 0
        self._step_count = 0
        self._sync_native_scores()
        self._last_metrics = self._build_metrics(collision=False, out_of_bounds=False)
        observations = {agent_id: self._observation(agent_id) for agent_id in self.agents}
        infos = {
            agent_id: self._info(agent_id, collision=False, out_of_bounds=False, action_clipped=False)
            for agent_id in self.agents
        }
        return observations, infos

    def step(self, actions: dict[str, np.ndarray]):
        native_actions: dict[int, np.ndarray] = {}
        clipped_flags: dict[str, bool] = {}

        for agent_id in self.agents:
            raw = np.asarray(actions.get(agent_id, np.zeros(self.action_shape, dtype=np.float32)), dtype=np.float32).reshape(-1)
            clipped = False
            if raw.shape != self.action_shape:
                raw = np.zeros(self.action_shape, dtype=np.float32)
                clipped = True
            bounded = np.clip(raw, self._action_low, self._action_high).astype(np.float32)
            if np.any(bounded != raw):
                clipped = True
            if clipped:
                self._action_violation_count += 1
            native_actions[self._id_to_native[agent_id]] = bounded * float(self._config["dynamics"]["racer_max_accel"])
            clipped_flags[agent_id] = clipped

        native_obs, rewards, terminated, truncated, info = self._native_env.step(native_actions)
        self._step_count = int(self._native_env.step_count)
        self._update_sequential_scores(info.get("pass_events", []))
        self._sync_native_scores()

        collision = bool(info.get("termination", {}).get("winner") == "DOUBLE_LOSS")
        out_of_bounds = bool(info.get("termination", {}).get("reason") == "out_of_bounds")
        target_score = self._config.get("rules", {}).get("target_score")
        sequential_complete = any(score >= len(self._native_env.gates) for score in self._team_scores.values())
        target_score_reached = target_score is not None and any(score >= float(target_score) for score in self._team_scores.values())
        if sequential_complete or target_score_reached:
            terminated = {native_id: True for native_id in native_obs}

        self._last_metrics = self._build_metrics(collision=collision, out_of_bounds=out_of_bounds)
        observations = {agent_id: self._observation(agent_id) for agent_id in self.agents}
        reward_map = {self._native_to_id[native_id]: float(reward) for native_id, reward in rewards.items()}
        terminations = {self._native_to_id[native_id]: bool(value) for native_id, value in terminated.items()}
        truncations = {self._native_to_id[native_id]: bool(value) for native_id, value in truncated.items()}
        infos = {
            agent_id: self._info(
                agent_id,
                collision=collision,
                out_of_bounds=out_of_bounds,
                action_clipped=clipped_flags[agent_id],
            )
            for agent_id in self.agents
        }
        return observations, reward_map, terminations, truncations, infos

    def render(self):
        return None

    def close(self) -> None:
        return None

    def _build_native_env(self, config: dict[str, Any]) -> SwarmCombatEnv:
        cfg = EnvConfig()
        cfg.dt = float(config.get("dt", 0.05))
        cfg.max_steps = int(config.get("max_steps", 400))
        cfg.n_red = 1
        cfg.n_red_racers = 1
        cfg.n_blue = 1
        cfg.n_blue_racers = 1
        cfg.field.x_range = tuple(config["field"]["x_range"])
        cfg.field.y_range = tuple(config["field"]["y_range"])
        cfg.field.z_range = tuple(config["field"]["z_range"])
        cfg.drone.safety_radius = float(config["drone"]["safety_radius"])
        cfg.drone.inter_team_safe_dist = float(config["drone"]["inter_team_safe_dist"])
        cfg.drone.intra_team_safe_dist = float(config["drone"]["intra_team_safe_dist"])
        cfg.drone.max_speed = float(config["dynamics"]["racer_max_speed"])
        cfg.drone.max_accel = float(config["dynamics"]["racer_max_accel"])
        cfg.drone_types["racer"].dynamics = "double_integrator"
        cfg.drone_types["racer"].max_speed = float(config["dynamics"]["racer_max_speed"])
        cfg.drone_types["racer"].max_accel = float(config["dynamics"]["racer_max_accel"])
        cfg.rewards.gate_pass = float(config["reward_weights"]["gate_pass"])
        cfg.rewards.interception = float(config["reward_weights"]["interception"])
        cfg.rewards.formation_tight = float(config["reward_weights"]["formation_tight"])
        cfg.rewards.protection = float(config["reward_weights"]["protection"])
        cfg.rewards.safety_violation = float(config["reward_weights"]["safety_violation"])
        cfg.rewards.collision = float(config["reward_weights"]["collision"])
        cfg.rewards.out_of_bounds = float(config["reward_weights"]["out_of_bounds"])
        cfg.rewards.time_penalty = float(config["reward_weights"]["time_penalty"])
        cfg.rules.target_score = config["rules"].get("target_score")
        cfg.rules.collision_ends_episode = bool(config["rules"]["collision_ends_episode"])
        cfg.rules.out_of_bounds_ends_episode = bool(config["rules"]["out_of_bounds_ends_episode"])
        cfg.spawn_red.mode = config["spawn_red"]["mode"]
        cfg.spawn_red.fixed_positions = config["spawn_red"]["fixed_positions"]
        cfg.spawn_blue.mode = config["spawn_blue"]["mode"]
        cfg.spawn_blue.fixed_positions = config["spawn_blue"]["fixed_positions"]
        cfg.set_gate_layout(str(config.get("gate_layout", "slalom")))
        return SwarmCombatEnv(cfg)

    def _observation(self, agent_id: str) -> np.ndarray:
        drone = self._get_drone(agent_id)
        opponent_id = "blue_racer_0" if agent_id == "red_racer_0" else "red_racer_0"
        opponent = self._get_drone(opponent_id)
        gate = self._current_gate(agent_id)
        team_forward = gate.normal.copy() if agent_id.startswith("red") else (-gate.normal).copy()
        field_margin = self._field_margin(drone.position)
        gate_centers = [gate_item.center - drone.position for gate_item in self._native_env.gates]
        gate_red_cd = [gate_item.cooldown_remaining[Team.RED] / max(gate_item.cooldown_steps, 1) for gate_item in self._native_env.gates]
        gate_blue_cd = [gate_item.cooldown_remaining[Team.BLUE] / max(gate_item.cooldown_steps, 1) for gate_item in self._native_env.gates]
        gate_forward = [float(np.dot(gate_item.center - drone.position, team_forward)) for gate_item in self._native_env.gates]
        target_vector = gate.center - drone.position
        opponent_rel_pos = opponent.position - drone.position
        opponent_rel_vel = opponent.velocity - drone.velocity
        remaining_ratio = (len(self._native_env.gates) - self._team_scores[agent_id]) / max(len(self._native_env.gates), 1)

        obs = np.zeros(self.observation_shape, dtype=np.float32)
        obs[0:3] = drone.position
        obs[3:6] = drone.velocity
        obs[6:9] = opponent_rel_pos
        obs[9:12] = opponent_rel_vel
        obs[12:15] = target_vector
        obs[15:18] = team_forward
        obs[18] = float(np.linalg.norm(target_vector))
        obs[19] = float(remaining_ratio)
        obs[20] = float(self._team_scores[agent_id])
        obs[21] = float(self._team_scores[opponent_id])
        obs[22] = float(self._team_scores[agent_id])
        obs[23] = float(self._team_scores[opponent_id])
        obs[24] = float(self._step_count) / max(float(self.max_steps), 1.0)
        obs[25] = float(field_margin)
        obs[26] = float(self._ordered_gate_indices[agent_id]) / max(float(len(self._native_env.gates) - 1), 1.0)
        obs[27] = float(np.linalg.norm(opponent_rel_pos))
        line = opponent_rel_pos / max(float(np.linalg.norm(opponent_rel_pos)), 1e-6)
        obs[28] = float(np.dot(opponent_rel_vel, line))
        obs[29] = float(np.linalg.norm(drone.velocity))
        obs[30] = 1.0 if agent_id.startswith("red") else 0.0
        obs[31] = 1.0 if agent_id.startswith("blue") else 0.0
        obs[32:35] = gate_centers[0]
        obs[35:38] = gate_centers[1]
        obs[38:41] = gate_centers[2]
        obs[41:44] = gate_centers[3]
        obs[44:47] = gate_centers[4]
        obs[47:52] = np.asarray(gate_red_cd, dtype=np.float32)
        obs[52:57] = np.asarray(gate_blue_cd, dtype=np.float32)
        obs[57:62] = np.asarray(gate_forward, dtype=np.float32)
        obs[62] = 1.0
        obs[63] = 0.0
        return obs

    def _build_metrics(self, collision: bool, out_of_bounds: bool) -> dict[str, Any]:
        red_score = float(self._team_scores["red_racer_0"])
        blue_score = float(self._team_scores["blue_racer_0"])
        return {
            "team_score": red_score,
            "blue_team_score": blue_score,
            "collision": bool(collision),
            "out_of_bounds": bool(out_of_bounds),
            "red_win": bool(red_score > blue_score),
            "gate_pass_balance": float(red_score - blue_score),
            "episode_length": int(self._step_count),
            "action_violation_rate": float(self._action_violation_count / max(self._step_count * len(self.agents), 1)),
        }

    def _info(self, agent_id: str, collision: bool, out_of_bounds: bool, action_clipped: bool) -> dict[str, Any]:
        metrics = dict(self._last_metrics)
        metrics["gate_passed_count"] = int(self._team_scores[agent_id])
        return {
            "collision": bool(collision),
            "out_of_bounds": bool(out_of_bounds),
            "ring_passed_count": int(self._team_scores[agent_id]),
            "gate_passed_count": int(self._team_scores[agent_id]),
            "communication_dropped": False,
            "action_clipped": bool(action_clipped),
            "team": "red" if agent_id.startswith("red") else "blue",
            "role": "racer",
            "metrics": metrics,
        }

    def _get_drone(self, agent_id: str):
        native_id = self._id_to_native[agent_id]
        return next(drone for drone in self._native_env.drones if drone.id == native_id)

    def _current_gate(self, agent_id: str):
        index = int(np.clip(self._ordered_gate_indices[agent_id], 0, len(self._native_env.gates) - 1))
        return self._native_env.gates[index]

    def _update_sequential_scores(self, pass_events: list[dict[str, Any]]) -> None:
        for event in pass_events:
            if not event.get("scored", False):
                continue
            agent_id = self._native_to_id.get(int(event["drone_id"]))
            if agent_id is None:
                continue
            expected_gate = self._ordered_gate_indices[agent_id]
            if int(event["gate_id"]) != expected_gate:
                continue
            self._team_scores[agent_id] += 1.0
            if agent_id.startswith("red"):
                self._ordered_gate_indices[agent_id] = min(expected_gate + 1, len(self._native_env.gates) - 1)
            else:
                self._ordered_gate_indices[agent_id] = max(expected_gate - 1, 0)

    def _sync_native_scores(self) -> None:
        self._native_env.team_scores[Team.RED] = float(self._team_scores["red_racer_0"])
        self._native_env.team_scores[Team.BLUE] = float(self._team_scores["blue_racer_0"])
        self._native_env.team_pass_count[Team.RED] = int(self._team_scores["red_racer_0"])
        self._native_env.team_pass_count[Team.BLUE] = int(self._team_scores["blue_racer_0"])
        if self._native_env.history:
            self._native_env.history[-1]["scores"] = {"RED": float(self._team_scores["red_racer_0"]), "BLUE": float(self._team_scores["blue_racer_0"])}

    def _field_margin(self, position: np.ndarray) -> float:
        x_gap = min(position[0] - self._native_env.cfg.field.x_range[0], self._native_env.cfg.field.x_range[1] - position[0])
        y_gap = min(position[1] - self._native_env.cfg.field.y_range[0], self._native_env.cfg.field.y_range[1] - position[1])
        z_gap = min(position[2] - self._native_env.cfg.field.z_range[0], self._native_env.cfg.field.z_range[1] - position[2])
        scale = max(
            self._native_env.cfg.field.x_range[1] - self._native_env.cfg.field.x_range[0],
            self._native_env.cfg.field.y_range[1] - self._native_env.cfg.field.y_range[0],
            self._native_env.cfg.field.z_range[1] - self._native_env.cfg.field.z_range[0],
        )
        return float(max(min(x_gap, y_gap, z_gap) / max(scale, 1e-6), 0.0))


def _load_config(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    base = yaml.safe_load(Path(__file__).with_name("env_config.yaml").read_text(encoding="utf-8")) or {}
    if overrides:
        for key, value in overrides.items():
            if isinstance(base.get(key), dict) and isinstance(value, dict):
                base[key] = {**base[key], **value}
            else:
                base[key] = value
    return base


def _obs_low() -> np.ndarray:
    return np.asarray(yaml.safe_load(Path(__file__).with_name("task_spec.yaml").read_text(encoding="utf-8"))["observation_space"]["low"], dtype=np.float32)


def _obs_high() -> np.ndarray:
    return np.asarray(yaml.safe_load(Path(__file__).with_name("task_spec.yaml").read_text(encoding="utf-8"))["observation_space"]["high"], dtype=np.float32)


def make_env(config: dict[str, Any] | None = None) -> Slalom1v13DEnv:
    return Slalom1v13DEnv(config)
