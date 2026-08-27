from __future__ import annotations

from dataclasses import asdict
from typing import Any

import numpy as np

from contracts.runtime_protocol import FramePacket, ScenarioDescriptor, ScenarioEvent
from game_agent.scenarios.visualization import build_representative_visualization


class RepresentativeScenarioRuntime:
    """Deterministic reference runtime for cross-capability conformance runs.

    This runtime intentionally uses lightweight point-mass dynamics. It exercises
    contracts, information boundaries, lifecycle, communication, observation
    modalities, evidence recording, and suite orchestration. It is not a claim
    of high-fidelity aerodynamics or a connection to an external simulator.
    """

    def __init__(self, spec: dict[str, Any]) -> None:
        self.spec = dict(spec)
        config = dict(spec.get("runtime_config", {}))
        self.scenario_id = str(spec["scenario_id"])
        self.task_family = str(spec.get("task_family", "representative"))
        self.name = str(spec.get("name", self.scenario_id))
        self.capabilities = dict(spec.get("capabilities", {}))
        self.primary_metric = str(spec.get("primary_metric", "task_success_rate"))
        self.dimension = int(config.get("dimension", 2))
        self.n_agents = int(config.get("n_agents", 1))
        self.max_steps = int(config.get("max_steps", 48))
        self.dt = float(config.get("dt", 0.15))
        self.boundary = float(config.get("boundary", 2.0))
        self.task_mode = str(config.get("task_mode", "navigation"))
        self.dynamics = str(config.get("dynamics", "double_integrator"))
        self.observation_type = str(config.get("observation_type", "vector"))
        self.action_type = str(config.get("action_type", "continuous"))
        self.stochasticity = str(config.get("stochasticity", "initial_jitter"))
        self.lifecycle = str(config.get("lifecycle", "fixed"))
        self.communication = dict(config.get("communication", {"mode": "perfect"}))
        self.external_reference = bool(config.get("external_reference", False))
        self.vector_field = bool(config.get("vector_field", False))
        self.agent_ids = [f"agent_{index:02d}" for index in range(self.n_agents)]
        self.possible_agents = list(self.agent_ids)
        self.agents = list(self.agent_ids)
        self.action_shape = (self.dimension,)
        self.action_low = -np.ones(self.dimension, dtype=np.float32)
        self.action_high = np.ones(self.dimension, dtype=np.float32)
        self._rng = np.random.default_rng(0)
        self._positions = np.zeros((self.n_agents, self.dimension), dtype=np.float32)
        self._velocities = np.zeros_like(self._positions)
        self._goals = np.zeros_like(self._positions)
        self._initial_distances = np.ones(self.n_agents, dtype=np.float32)
        self._active = np.ones(self.n_agents, dtype=bool)
        self._roles = self._build_roles()
        self._step_count = 0
        self._last_actions: dict[str, np.ndarray] = {}
        self._last_observations: dict[str, Any] = {}
        self._last_rewards: dict[str, float] = {}
        self._last_events: tuple[ScenarioEvent, ...] = ()
        self._last_messages: tuple[dict[str, Any], ...] = ()
        self._message_queue: list[dict[str, Any]] = []
        self._message_sent = 0
        self._message_delivered = 0
        self._message_dropped = 0
        self._action_violations = 0
        self._collisions = 0
        self._out_of_bounds = False
        self._success = False
        self._timeout = False
        self._progress = 0.0

    def describe(self) -> ScenarioDescriptor:
        observation_spec: dict[str, Any]
        if self.observation_type == "graph":
            observation_spec = {
                "type": "Dict",
                "fields": {
                    "graph": {
                        "type": "Graph",
                        "node_shape": [2 * self.dimension + 2],
                        "edge_shape": [1],
                        "variable_nodes": True,
                    },
                    "proprioception": {
                        "type": "Box",
                        "shape": [3 * self.dimension + 4],
                    },
                },
            }
        elif self.observation_type == "image":
            observation_spec = {
                "type": "Dict",
                "fields": {
                    "depth_image": {"type": "Image", "shape": [8, 8, 1]},
                    "proprioception": {
                        "type": "Box",
                        "shape": [3 * self.dimension + 4],
                    },
                },
            }
        else:
            observation_spec = {
                "type": "Box",
                "shape": [3 * self.dimension + 4],
            }
        action_spec: dict[str, Any] = {
            "type": "Box",
            "shape": [self.dimension],
            "low": self.action_low.tolist(),
            "high": self.action_high.tolist(),
        }
        if self.action_type == "hybrid":
            action_spec = {
                "type": "Dict",
                "fields": {
                    "mode": {"type": "Discrete", "n": 3},
                    "control": action_spec,
                },
                "runtime_projection": "reference adapter consumes control field",
            }
        disclosures = list(self.spec.get("disclosures", []))
        if self.external_reference:
            disclosures.append(
                "Local loopback reference adapter; no real external simulator is connected."
            )
        if self.observation_type == "image":
            disclosures.append(
                "Synthetic 8x8 depth proxy generated from runtime geometry; not camera rendering."
            )
        visualization = build_representative_visualization(
            dimension=self.dimension,
            boundary=self.boundary,
            vector_field=self.vector_field,
            include_messages=self.communication.get("mode", "perfect") != "none",
            disclosures=(
                "Visualization declares only axis-aligned bounds, agent states, goals, relations, and runtime-emitted vector fields.",
            ),
        )
        return ScenarioDescriptor(
            scenario_id=self.scenario_id,
            task_family=self.task_family,
            capabilities=dict(self.capabilities),
            agents=tuple(self.possible_agents),
            observation_spaces={agent: observation_spec for agent in self.possible_agents},
            action_spaces={agent: action_spec for agent in self.possible_agents},
            disclosures=tuple(dict.fromkeys(disclosures)),
            visualization=visualization,
        )

    def reset(self, seed: int | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
        self._rng = np.random.default_rng(seed)
        self._step_count = 0
        self._last_actions = {}
        self._last_rewards = {}
        self._last_messages = ()
        self._message_queue = []
        self._message_sent = 0
        self._message_delivered = 0
        self._message_dropped = 0
        self._action_violations = 0
        self._collisions = 0
        self._out_of_bounds = False
        self._success = False
        self._timeout = False
        self._progress = 0.0
        self._active[:] = True
        if self.lifecycle == "dynamic_spawn" and self.n_agents > 2:
            self._active[2:] = False
        self._positions = self._initial_positions()
        self._velocities.fill(0.0)
        self._goals = self._initial_goals()
        self._initial_distances = np.maximum(
            np.linalg.norm(self._goals - self._positions, axis=1), 1e-6
        ).astype(np.float32)
        self._sync_agents()
        events = tuple(
            self._event("entity_spawned", (agent,), {"role": self._roles[index]})
            for index, agent in enumerate(self.possible_agents)
            if self._active[index]
        )
        if self.external_reference:
            events += (
                self._event(
                    "reference_adapter_started",
                    (),
                    {"adapter": "local_loopback", "external_connected": False},
                ),
            )
        self._last_events = events
        self._last_observations = self._observations()
        return self._last_observations, {
            "seed": seed,
            "events": [asdict(event) for event in events],
            "metrics": self.get_metrics(),
        }

    def step(
        self, actions: dict[str, Any]
    ) -> tuple[
        dict[str, Any],
        dict[str, float],
        dict[str, bool],
        dict[str, bool],
        dict[str, Any],
    ]:
        self._step_count += 1
        events: list[ScenarioEvent] = []
        parsed_actions: dict[str, np.ndarray] = {}
        for agent in list(self.agents):
            raw_action = actions.get(agent, np.zeros(self.action_shape, dtype=np.float32))
            if isinstance(raw_action, dict):
                raw_action = raw_action.get("control", np.zeros(self.action_shape))
            action = np.asarray(raw_action, dtype=np.float32)
            if action.shape != self.action_shape or not np.all(np.isfinite(action)):
                self._action_violations += 1
                events.append(
                    self._event(
                        "constraint_violation",
                        (agent,),
                        {"constraint": "action_structure"},
                    )
                )
                action = np.zeros(self.action_shape, dtype=np.float32)
            if np.any(action < self.action_low) or np.any(action > self.action_high):
                self._action_violations += 1
                events.append(
                    self._event(
                        "constraint_violation",
                        (agent,),
                        {"constraint": "action_bounds"},
                    )
                )
            parsed_actions[agent] = np.clip(
                action, self.action_low, self.action_high
            ).astype(np.float32)
        self._last_actions = parsed_actions
        events.extend(self._advance_messages())
        self._advance_dynamics(parsed_actions)
        events.extend(self._apply_lifecycle())
        events.extend(self._detect_interactions())
        previous_progress = self._progress
        self._progress, success_event = self._task_progress()
        if success_event is not None:
            events.append(success_event)
        self._success = self._success or self._progress >= 0.98
        self._timeout = self._step_count >= self.max_steps and not self._success
        terminated_any = self._success or self._out_of_bounds
        truncated_any = self._timeout and not terminated_any
        if terminated_any or truncated_any:
            events.append(
                self._event(
                    "episode_terminated",
                    (),
                    {
                        "success": self._success,
                        "timeout": self._timeout,
                        "out_of_bounds": self._out_of_bounds,
                    },
                )
            )
        delta = float(self._progress - previous_progress)
        self._last_rewards = {
            agent: delta
            - 0.001
            * float(
                np.square(
                    parsed_actions.get(
                        agent, np.zeros(self.action_shape, dtype=np.float32)
                    )
                ).mean()
            )
            for agent in self.agents
        }
        self._last_events = tuple(events)
        self._last_observations = self._observations()
        metrics = self.get_metrics()
        terminations = {agent: terminated_any for agent in self.agents}
        truncations = {agent: truncated_any for agent in self.agents}
        info = {
            "events": [asdict(event) for event in events],
            "metrics": metrics,
        }
        return (
            self._last_observations,
            dict(self._last_rewards),
            terminations,
            truncations,
            info,
        )

    def snapshot(self) -> FramePacket:
        entities = tuple(
            {
                "id": agent,
                "position": self._positions[index].astype(float).tolist(),
                "velocity": self._velocities[index].astype(float).tolist(),
                "goal": self._goals[index].astype(float).tolist(),
                "team": self._team(index),
                "role": self._roles[index],
                "active": bool(self._active[index]),
            }
            for index, agent in enumerate(self.possible_agents)
        )
        relations = tuple(self._relations())
        fields: tuple[dict[str, Any], ...] = ()
        if self.vector_field:
            fields = (
                {
                    "kind": "vector_field",
                    "vector": self._wind_vector().astype(float).tolist(),
                },
            )
        return FramePacket(
            scenario_time=self._step_count * self.dt,
            episode_step=self._step_count,
            entities=entities,
            relations=relations,
            fields=fields,
            observations=self._last_observations,
            actions={key: value.tolist() for key, value in self._last_actions.items()},
            messages=self._last_messages,
            events=self._last_events,
            rewards=dict(self._last_rewards),
            metrics=self.get_metrics(),
        )

    def get_metrics(self) -> dict[str, Any]:
        active_count = max(int(self._active.sum()), 1)
        action_denominator = max(self._step_count * active_count, 1)
        pair_count = max(active_count * (active_count - 1) // 2, 1)
        collision_denominator = max(self._step_count * pair_count, 1)
        sent = max(self._message_sent, 1)
        primary_value = float(1.0 if self._success else self._progress)
        return {
            "primary_metric": self.primary_metric,
            "primary_value": primary_value,
            self.primary_metric: primary_value,
            "success": bool(self._success),
            "success_rate": 1.0 if self._success else 0.0,
            "task_progress": float(self._progress),
            "collision_rate": float(self._collisions / collision_denominator),
            "collision_count": int(self._collisions),
            "out_of_bounds": bool(self._out_of_bounds),
            "out_of_bounds_rate": float(self._out_of_bounds),
            "action_violation_rate": float(
                self._action_violations / action_denominator
            ),
            "communication_delivery_rate": float(self._message_delivered / sent),
            "message_drop_rate": float(self._message_dropped / sent),
            "episode_length": int(self._step_count),
            "timeout": bool(self._timeout),
            "timeout_rate": float(self._timeout),
        }

    def close(self) -> None:
        return None

    def _build_roles(self) -> list[str]:
        if self.task_mode == "pursuit":
            evaders = int(
                self.spec.get("runtime_config", {}).get(
                    "evader_count", max(1, self.n_agents // 4)
                )
            )
            pursuers = int(
                self.spec.get("runtime_config", {}).get(
                    "pursuer_count", self.n_agents - evaders
                )
            )
            if pursuers < 1 or evaders < 1 or pursuers + evaders != self.n_agents:
                raise ValueError("pursuit role counts must be positive and sum to n_agents")
            return ["pursuer"] * pursuers + ["evader"] * evaders
        if self.task_mode == "escort":
            if self.n_agents == 1:
                return ["asset"]
            split = max(1, self.n_agents // 2)
            return ["escort"] * (split - 1) + ["asset"] + ["interceptor"] * (
                self.n_agents - split
            )
        if self.task_mode == "formation":
            return ["formation_member"] * self.n_agents
        if self.task_mode == "coverage":
            return ["coverage_agent"] * self.n_agents
        if self.task_mode == "hybrid":
            return ["hybrid_agent"] * self.n_agents
        return ["navigator"] * self.n_agents

    def _initial_positions(self) -> np.ndarray:
        positions = np.zeros((self.n_agents, self.dimension), dtype=np.float32)
        columns = max(int(np.ceil(np.sqrt(self.n_agents))), 1)
        rows = max(int(np.ceil(self.n_agents / columns)), 1)
        for index in range(self.n_agents):
            row, column = divmod(index, columns)
            positions[index, 0] = -0.85 + 0.08 * column
            if self.dimension >= 2:
                positions[index, 1] = -0.7 + 1.4 * row / max(rows - 1, 1)
            if self.dimension == 3:
                positions[index, 2] = -0.25 + 0.5 * column / max(columns - 1, 1)
        jitter_scale = 0.0 if self.stochasticity == "none" else 0.015
        positions += self._rng.normal(0.0, jitter_scale, size=positions.shape).astype(
            np.float32
        )
        if self.task_mode == "pursuit":
            for index, role in enumerate(self._roles):
                positions[index, 0] = -0.65 if role == "pursuer" else 0.35
        return positions

    def _initial_goals(self) -> np.ndarray:
        goals = np.zeros((self.n_agents, self.dimension), dtype=np.float32)
        for index in range(self.n_agents):
            goals[index, 0] = 0.82
            if self.dimension >= 2:
                spread = 0.65 if self.task_mode in {"coverage", "formation"} else 0.35
                goals[index, 1] = spread * (
                    -1.0 + 2.0 * index / max(self.n_agents - 1, 1)
                )
            if self.dimension == 3:
                angle = 2.0 * np.pi * index / max(self.n_agents, 1)
                goals[index, 2] = 0.35 * np.cos(angle)
        if self.task_mode == "pursuit":
            for index, role in enumerate(self._roles):
                if role == "evader":
                    goals[index, 0] = 1.35
        return goals

    def _advance_dynamics(self, actions: dict[str, np.ndarray]) -> None:
        wind = self._wind_vector()
        for agent, action in actions.items():
            index = self._index(agent)
            if self.dynamics == "single_integrator":
                self._positions[index] += (0.7 * action + wind) * self.dt
                self._velocities[index] = 0.7 * action + wind
                continue
            drag = (
                0.35
                if self.dynamics in {"damped", "damped_double_integrator"}
                else 0.08
            )
            self._velocities[index] = (
                (1.0 - drag * self.dt) * self._velocities[index]
                + action * self.dt
                + wind * self.dt
            )
            speed = float(np.linalg.norm(self._velocities[index]))
            if speed > 0.85:
                self._velocities[index] *= 0.85 / speed
            self._positions[index] += self._velocities[index] * self.dt

    def _advance_messages(self) -> list[ScenarioEvent]:
        events: list[ScenarioEvent] = []
        mode = str(self.communication.get("mode", "perfect"))
        delay = int(self.communication.get("delay_steps", 0)) if mode == "delayed" else 0
        drop_probability = (
            float(self.communication.get("drop_probability", 0.0))
            if mode == "lossy"
            else 0.0
        )
        budget = int(
            self.communication.get(
                "budget_per_step",
                self.communication.get("messages_per_step", len(self.agents)),
            )
        )
        messages: list[dict[str, Any]] = []
        for sender_index, sender in enumerate(self.agents[: max(budget, 0)]):
            if len(self.agents) < 2:
                break
            receiver = self.agents[(sender_index + 1) % len(self.agents)]
            self._message_sent += 1
            events.append(self._event("message_sent", (sender, receiver), {}))
            if self._rng.random() < drop_probability:
                self._message_dropped += 1
                events.append(self._event("message_dropped", (sender, receiver), {}))
                continue
            self._message_queue.append(
                {
                    "sender": sender,
                    "receiver": receiver,
                    "sent_step": self._step_count,
                    "deliver_step": self._step_count + delay,
                }
            )
        pending: list[dict[str, Any]] = []
        for message in self._message_queue:
            if int(message["deliver_step"]) <= self._step_count:
                self._message_delivered += 1
                delivered = dict(message)
                delivered["age_steps"] = self._step_count - int(message["sent_step"])
                messages.append(delivered)
                events.append(
                    self._event(
                        "message_delivered",
                        (str(message["sender"]), str(message["receiver"])),
                        {"age_steps": delivered["age_steps"]},
                    )
                )
            else:
                pending.append(message)
        self._message_queue = pending
        self._last_messages = tuple(messages)
        return events

    def _apply_lifecycle(self) -> list[ScenarioEvent]:
        events: list[ScenarioEvent] = []
        trigger = max(self.max_steps // 3, 1)
        if self._step_count != trigger:
            return events
        if self.lifecycle == "dynamic_spawn":
            for index in range(2, self.n_agents):
                if not self._active[index]:
                    self._active[index] = True
                    events.append(
                        self._event(
                            "entity_spawned",
                            (self.possible_agents[index],),
                            {"reason": "scheduled_reinforcement"},
                        )
                    )
        elif self.lifecycle == "failure_exit" and self.n_agents > 1:
            index = self.n_agents - 1
            self._active[index] = False
            events.append(
                self._event(
                    "entity_removed",
                    (self.possible_agents[index],),
                    {"reason": "scheduled_failure"},
                )
            )
        elif self.lifecycle == "role_transition":
            index = 0
            previous = self._roles[index]
            self._roles[index] = "relay"
            events.append(
                self._event(
                    "role_changed",
                    (self.possible_agents[index],),
                    {"previous": previous, "current": "relay"},
                )
            )
        self._sync_agents()
        return events

    def _detect_interactions(self) -> list[ScenarioEvent]:
        events: list[ScenarioEvent] = []
        if self.task_mode == "pursuit":
            # Pursuit contact is represented by the task-level ``capture`` event;
            # counting the same contact as a collision would double-book the outcome.
            if np.any(np.abs(self._positions[self._active]) > self.boundary):
                self._out_of_bounds = True
                events.append(self._event("out_of_bounds", (), {}))
            return events
        active_indices = np.flatnonzero(self._active)
        for offset, first in enumerate(active_indices):
            for second in active_indices[offset + 1 :]:
                distance = float(
                    np.linalg.norm(self._positions[first] - self._positions[second])
                )
                if distance < 0.005:
                    self._collisions += 1
                    events.append(
                        self._event(
                            "collision",
                            (self.possible_agents[first], self.possible_agents[second]),
                            {"distance": distance},
                        )
                    )
        if np.any(np.abs(self._positions[self._active]) > self.boundary):
            self._out_of_bounds = True
            events.append(self._event("out_of_bounds", (), {}))
        return events

    def _task_progress(self) -> tuple[float, ScenarioEvent | None]:
        if self.task_mode == "pursuit":
            pursuers = [i for i, role in enumerate(self._roles) if role == "pursuer" and self._active[i]]
            evaders = [i for i, role in enumerate(self._roles) if role == "evader" and self._active[i]]
            if not pursuers or not evaders:
                return self._progress, None
            distance = min(
                float(np.linalg.norm(self._positions[p] - self._positions[e]))
                for p in pursuers
                for e in evaders
            )
            initial = max(float(self._initial_distances[evaders[0]]), 1.0)
            progress = float(np.clip(1.0 - distance / (initial + 0.6), 0.0, 1.0))
            if distance <= 0.12:
                self._success = True
                return 1.0, self._event("capture", (), {"distance": distance})
            return max(self._progress, progress), None
        active_indices = np.flatnonzero(self._active)
        if active_indices.size == 0:
            return self._progress, None
        distances = np.linalg.norm(
            self._goals[active_indices] - self._positions[active_indices], axis=1
        )
        normalized = 1.0 - distances / self._initial_distances[active_indices]
        progress = float(np.clip(normalized.mean(), 0.0, 1.0))
        if np.all(distances <= 0.14):
            self._success = True
            return 1.0, self._event(
                "target_reached", tuple(self.agents), {"mean_distance": float(distances.mean())}
            )
        return max(self._progress, progress), None

    def _observations(self) -> dict[str, Any]:
        observations: dict[str, Any] = {}
        for agent in self.agents:
            index = self._index(agent)
            base = self._proprioception(index)
            if self.observation_type == "image":
                observations[agent] = {
                    "depth_image": self._depth_proxy(index),
                    "proprioception": base,
                }
            elif self.observation_type == "graph":
                observations[agent] = {
                    "graph": self._graph_observation(index),
                    "proprioception": base,
                }
            else:
                observations[agent] = base
        return observations

    def _proprioception(self, index: int) -> np.ndarray:
        agent = self.possible_agents[index]
        return np.concatenate(
            [
                self._positions[index],
                self._velocities[index],
                self._execution_target(index) - self._positions[index],
                np.asarray(
                    [
                        self._progress,
                        self._step_count / max(self.max_steps, 1),
                        self._message_age(agent),
                        self._role_code(self._roles[index]),
                    ],
                    dtype=np.float32,
                ),
            ]
        ).astype(np.float32)

    def _execution_target(self, index: int) -> np.ndarray:
        if self.task_mode == "pursuit" and self._roles[index] == "pursuer":
            evaders = [
                item
                for item, role in enumerate(self._roles)
                if role == "evader" and self._active[item]
            ]
            if evaders:
                return min(
                    (self._positions[item] for item in evaders),
                    key=lambda target: float(
                        np.linalg.norm(target - self._positions[index])
                    ),
                )
        return self._goals[index]

    def _graph_observation(self, observer_index: int) -> dict[str, np.ndarray]:
        indices = np.flatnonzero(self._active)
        nodes = []
        for index in indices:
            relative = self._positions[index] - self._positions[observer_index]
            velocity = self._velocities[index]
            nodes.append(
                np.concatenate(
                    [
                        relative,
                        velocity,
                        np.asarray(
                            [self._role_code(self._roles[index]), float(index == observer_index)],
                            dtype=np.float32,
                        ),
                    ]
                )
            )
        edges: list[list[int]] = []
        edge_features: list[list[float]] = []
        for first in range(len(indices)):
            for second in range(len(indices)):
                if first == second:
                    continue
                distance = float(
                    np.linalg.norm(
                        self._positions[indices[first]] - self._positions[indices[second]]
                    )
                )
                if distance <= 0.75:
                    edges.append([first, second])
                    edge_features.append([distance])
        return {
            "nodes": np.asarray(nodes, dtype=np.float32),
            "edges": np.asarray(edges, dtype=np.int32).reshape(-1, 2),
            "edge_features": np.asarray(edge_features, dtype=np.float32).reshape(-1, 1),
        }

    def _depth_proxy(self, observer_index: int) -> np.ndarray:
        image = np.ones((8, 8, 1), dtype=np.float32)
        goal_delta = self._goals[observer_index] - self._positions[observer_index]
        distance = float(np.linalg.norm(goal_delta))
        x_index = int(np.clip(4 + 3 * goal_delta[0] / max(distance, 1e-6), 0, 7))
        y_component = goal_delta[1] if self.dimension >= 2 else 0.0
        y_index = int(np.clip(4 + 3 * y_component / max(distance, 1e-6), 0, 7))
        image[y_index, x_index, 0] = min(distance / (2 * self.boundary), 1.0)
        return image

    def _relations(self) -> list[dict[str, Any]]:
        relations: list[dict[str, Any]] = []
        for index, agent in enumerate(self.agents):
            next_agent = self.agents[(index + 1) % len(self.agents)] if len(self.agents) > 1 else agent
            relations.append(
                {
                    "kind": "communication_neighbor",
                    "source": agent,
                    "target": next_agent,
                    "mode": self.communication.get("mode", "perfect"),
                }
            )
        return relations

    def _wind_vector(self) -> np.ndarray:
        if not self.vector_field:
            return np.zeros(self.dimension, dtype=np.float32)
        vector = np.zeros(self.dimension, dtype=np.float32)
        vector[0] = 0.04 * np.sin(0.2 * self._step_count)
        if self.dimension >= 2:
            vector[1] = 0.03 * np.cos(0.17 * self._step_count)
        return vector

    def _message_age(self, agent: str) -> float:
        received = [
            message for message in self._last_messages if message.get("receiver") == agent
        ]
        if not received:
            return 1.0
        return float(min(message.get("age_steps", 0) for message in received)) / max(
            self.max_steps, 1
        )

    def _sync_agents(self) -> None:
        self.agents = [
            agent for index, agent in enumerate(self.possible_agents) if self._active[index]
        ]

    def _index(self, agent: str) -> int:
        return int(agent.rsplit("_", 1)[-1])

    def _team(self, index: int) -> str:
        if self.task_mode in {"pursuit", "escort"}:
            return "red" if index < max(self.n_agents // 2, 1) else "blue"
        return "shared"

    @staticmethod
    def _role_code(role: str) -> float:
        roles = {
            "navigator": 0.0,
            "pursuer": 0.2,
            "evader": 0.4,
            "escort": 0.5,
            "asset": 0.6,
            "interceptor": 0.7,
            "formation_member": 0.8,
            "coverage_agent": 0.9,
            "relay": 1.0,
        }
        return roles.get(role, 0.1)

    def _event(
        self,
        event_type: str,
        participants: tuple[str, ...],
        attributes: dict[str, Any],
    ) -> ScenarioEvent:
        return ScenarioEvent(
            event_type=event_type,
            step=self._step_count,
            time=self._step_count * self.dt,
            participants=participants,
            attributes=attributes,
        )


def create_representative_runtime(spec: dict[str, Any]) -> RepresentativeScenarioRuntime:
    return RepresentativeScenarioRuntime(spec)
