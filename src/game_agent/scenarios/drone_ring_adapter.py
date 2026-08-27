from __future__ import annotations

from typing import Any

import numpy as np

from contracts.runtime_protocol import FramePacket, ScenarioDescriptor
from game_agent.envs.drone_ring_game import DroneRingEnv
from game_agent.scenarios.visualization import build_drone_ring_visualization


class DroneRingRuntimeAdapter:
    """Expose the legacy drone-ring environment through the shared runtime contract."""

    def __init__(self, spec: dict[str, Any]) -> None:
        self.spec = dict(spec)
        self.env = DroneRingEnv(spec.get("env_config", {}))
        self.agents = list(self.env.agents)
        self.action_shape = self.env.action_shape
        self.max_steps = self.env.max_steps
        self._observations: dict[str, Any] = {}
        self._actions: dict[str, Any] = {}
        self._rewards: dict[str, float] = {}
        self._metrics: dict[str, Any] = {}

    def describe(self) -> ScenarioDescriptor:
        observation = {"type": "Box", "shape": list(self.env.observation_shape)}
        action = {
            "type": "Box",
            "shape": list(self.env.action_shape),
            "low": self.env._ACTION_LOW.astype(float).tolist(),
            "high": self.env._ACTION_HIGH.astype(float).tolist(),
        }
        visualization = build_drone_ring_visualization(
            boundary=float(self.env.boundary),
            ring_radius=float(self.env.ring_radius),
            rings=self.env.rings,
            disclosures=(
                "Visualization includes only the configured axis-aligned bounds and ring centers/radii exposed by DroneRingEnv.",
            ),
        )
        return ScenarioDescriptor(
            scenario_id=str(self.spec.get("task_id", "drone_ring_game")),
            task_family="drone_ring_game",
            capabilities={"legacy_adapter": True, "multi_agent": True},
            agents=tuple(self.agents),
            observation_spaces={agent: observation for agent in self.agents},
            action_spaces={agent: action for agent in self.agents},
            disclosures=("Legacy DroneRingEnv exposed through DroneRingRuntimeAdapter.",),
            visualization=visualization,
        )

    def reset(self, seed: int | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
        observations, info = self.env.reset(seed=seed)
        self.agents = list(self.env.agents)
        self._observations = observations
        self._actions = {}
        self._rewards = {}
        self._metrics = dict(info.get("metrics", {}))
        return observations, info

    def step(
        self, actions: dict[str, Any]
    ) -> tuple[
        dict[str, Any],
        dict[str, float],
        dict[str, bool],
        dict[str, bool],
        dict[str, Any],
    ]:
        result = self.env.step(actions)
        observations, rewards, _, _, info = result
        self._observations = observations
        self._actions = {key: np.asarray(value).tolist() for key, value in actions.items()}
        self._rewards = dict(rewards)
        self._metrics = dict(info.get("metrics", {}))
        return result

    def snapshot(self) -> FramePacket:
        entities = []
        for agent in self.agents:
            observation = np.asarray(self._observations.get(agent, np.zeros(4)))
            entities.append(
                {
                    "id": agent,
                    "position": observation[:2].astype(float).tolist(),
                    "velocity": observation[2:4].astype(float).tolist(),
                    "active": True,
                }
            )
        return FramePacket(
            scenario_time=int(self._metrics.get("episode_length", 0)) * self.env.dt,
            episode_step=int(self._metrics.get("episode_length", 0)),
            entities=tuple(entities),
            observations=self._observations,
            actions=self._actions,
            rewards=self._rewards,
            metrics=self._metrics,
        )

    def get_metrics(self) -> dict[str, Any]:
        return dict(self._metrics)

    def close(self) -> None:
        return None
