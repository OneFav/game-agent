from __future__ import annotations

import copy
from collections.abc import Sequence
from typing import Any

import numpy as np
import torch
from torch.nn import functional as functional
from torch.nn.utils import clip_grad_norm_
from torch.optim import Adam

from game_agent.rl.algorithms.base import BaseRLAlgorithm
from game_agent.rl.algorithms.buffer import ReplayBuffer
from game_agent.rl.algorithms.networks import Critic, DeterministicActor


class MADDPG(BaseRLAlgorithm):
    """集中训练、分散执行的多智能体 DDPG。"""

    def __init__(
        self,
        obs_dim: int,
        action_dim: int,
        n_agents: int,
        hidden_dims: Sequence[int] = (256, 256),
        lr_actor: float = 1e-4,
        lr_critic: float = 3e-4,
        gamma: float = 0.99,
        tau: float = 0.005,
        buffer_size: int = 1_000_000,
        noise_std: float = 0.1,
        max_action: float = 1.0,
        share_params: bool = True,
        activation: str = "relu",
        device: str | None = None,
    ) -> None:
        super().__init__(
            obs_dim,
            action_dim,
            hidden_dims,
            lr_actor,
            lr_critic,
            gamma,
            tau,
            device,
        )
        if n_agents <= 0:
            raise ValueError("n_agents must be positive")
        self.n_agents = int(n_agents)
        self.max_action = float(max_action)
        self.noise_std = float(noise_std)
        self.share_params = bool(share_params)
        global_obs_dim = obs_dim * n_agents
        global_action_dim = action_dim * n_agents

        if self.share_params:
            self.actor = DeterministicActor(
                obs_dim,
                action_dim,
                self.hidden_dims,
                max_action,
                activation,
            ).to(self.device)
            self.actor_target = copy.deepcopy(self.actor)
            self.critic = Critic(
                global_obs_dim,
                global_action_dim,
                self.hidden_dims,
                activation,
            ).to(self.device)
            self.critic_target = copy.deepcopy(self.critic)
            self.actor_optimizer = Adam(self.actor.parameters(), lr=lr_actor)
            self.critic_optimizer = Adam(self.critic.parameters(), lr=lr_critic)
        else:
            self.actors = [
                DeterministicActor(
                    obs_dim,
                    action_dim,
                    self.hidden_dims,
                    max_action,
                    activation,
                ).to(self.device)
                for _ in range(n_agents)
            ]
            self.actor_targets = [copy.deepcopy(actor) for actor in self.actors]
            self.critics = [
                Critic(
                    global_obs_dim,
                    global_action_dim,
                    self.hidden_dims,
                    activation,
                ).to(self.device)
                for _ in range(n_agents)
            ]
            self.critic_targets = [copy.deepcopy(critic) for critic in self.critics]
            self.actor_optimizers = [
                Adam(actor.parameters(), lr=lr_actor) for actor in self.actors
            ]
            self.critic_optimizers = [
                Adam(critic.parameters(), lr=lr_critic) for critic in self.critics
            ]
        self.buffer = ReplayBuffer(buffer_size, global_obs_dim, global_action_dim)

    def select_action(
        self,
        obs: np.ndarray,
        deterministic: bool = False,
        *,
        agent_id: int = 0,
    ) -> np.ndarray:
        if not 0 <= agent_id < self.n_agents:
            raise ValueError("agent_id is out of range")
        with torch.no_grad():
            observation = torch.as_tensor(
                obs,
                dtype=torch.float32,
                device=self.device,
            ).unsqueeze(0)
            actor = self.actor if self.share_params else self.actors[agent_id]
            action = actor(observation).cpu().numpy()[0]
        if not deterministic:
            action += np.random.normal(0.0, self.noise_std, size=self.action_dim)
        return np.clip(action, -self.max_action, self.max_action)

    def select_actions(
        self,
        observations: Sequence[np.ndarray],
        deterministic: bool = False,
    ) -> list[np.ndarray]:
        if len(observations) != self.n_agents:
            raise ValueError("observations must contain one item per agent")
        return [
            self.select_action(obs, deterministic, agent_id=agent_id)
            for agent_id, obs in enumerate(observations)
        ]

    def update(self, batch_size: int = 256) -> dict[str, float]:
        if len(self.buffer) < batch_size:
            return {}
        batch = self.buffer.sample(batch_size, self.device)
        if self.share_params:
            return self._update_shared(batch)
        return self._update_independent(batch)

    def _split_observations(self, global_obs: torch.Tensor) -> list[torch.Tensor]:
        return list(torch.split(global_obs, self.obs_dim, dim=-1))

    def _update_shared(self, batch: dict[str, torch.Tensor]) -> dict[str, float]:
        with torch.no_grad():
            next_actions = [
                self.actor_target(obs)
                for obs in self._split_observations(batch["next_obs"])
            ]
            next_global_action = torch.cat(next_actions, dim=-1)
            target_q = self.critic_target(batch["next_obs"], next_global_action)
            target_q = batch["reward"] + (
                1.0 - batch["done"]
            ) * self.gamma * target_q
        current_q = self.critic(batch["obs"], batch["action"])
        critic_loss = functional.mse_loss(current_q, target_q)
        self.critic_optimizer.zero_grad()
        critic_loss.backward()
        clip_grad_norm_(self.critic.parameters(), 1.0)
        self.critic_optimizer.step()

        predicted_actions = [
            self.actor(obs) for obs in self._split_observations(batch["obs"])
        ]
        actor_loss = -self.critic(
            batch["obs"],
            torch.cat(predicted_actions, dim=-1),
        ).mean()
        self.actor_optimizer.zero_grad()
        actor_loss.backward()
        clip_grad_norm_(self.actor.parameters(), 1.0)
        self.actor_optimizer.step()
        self._soft_update(self.actor_target, self.actor)
        self._soft_update(self.critic_target, self.critic)
        self.train_step += 1
        return {
            "critic_loss": critic_loss.item(),
            "actor_loss": actor_loss.item(),
            "q_value": current_q.mean().item(),
        }

    def _update_independent(
        self,
        batch: dict[str, torch.Tensor],
    ) -> dict[str, float]:
        observations = self._split_observations(batch["obs"])
        next_observations = self._split_observations(batch["next_obs"])
        total_critic_loss = 0.0
        total_actor_loss = 0.0
        for agent_id in range(self.n_agents):
            with torch.no_grad():
                next_actions = [
                    actor_target(obs)
                    for actor_target, obs in zip(
                        self.actor_targets,
                        next_observations,
                        strict=True,
                    )
                ]
                target_q = self.critic_targets[agent_id](
                    batch["next_obs"],
                    torch.cat(next_actions, dim=-1),
                )
                target_q = batch["reward"] + (
                    1.0 - batch["done"]
                ) * self.gamma * target_q
            current_q = self.critics[agent_id](batch["obs"], batch["action"])
            critic_loss = functional.mse_loss(current_q, target_q)
            self.critic_optimizers[agent_id].zero_grad()
            critic_loss.backward()
            clip_grad_norm_(self.critics[agent_id].parameters(), 1.0)
            self.critic_optimizers[agent_id].step()

            predicted_actions = []
            for index, (actor, obs) in enumerate(
                zip(self.actors, observations, strict=True)
            ):
                predicted = actor(obs)
                if index != agent_id:
                    predicted = predicted.detach()
                predicted_actions.append(predicted)
            actor_loss = -self.critics[agent_id](
                batch["obs"],
                torch.cat(predicted_actions, dim=-1),
            ).mean()
            self.actor_optimizers[agent_id].zero_grad()
            actor_loss.backward()
            clip_grad_norm_(self.actors[agent_id].parameters(), 1.0)
            self.actor_optimizers[agent_id].step()
            self._soft_update(
                self.actor_targets[agent_id],
                self.actors[agent_id],
            )
            self._soft_update(
                self.critic_targets[agent_id],
                self.critics[agent_id],
            )
            total_critic_loss += critic_loss.item()
            total_actor_loss += actor_loss.item()
        self.train_step += 1
        return {
            "critic_loss": total_critic_loss / self.n_agents,
            "actor_loss": total_actor_loss / self.n_agents,
        }

    def _metadata(self) -> dict[str, Any]:
        return {
            **self._checkpoint_metadata("maddpg"),
            "n_agents": self.n_agents,
            "share_params": self.share_params,
        }

    def save(self, path: str) -> None:
        checkpoint: dict[str, Any] = {
            "metadata": self._metadata(),
            "train_step": self.train_step,
        }
        if self.share_params:
            checkpoint.update(
                {
                    "actor": self.actor.state_dict(),
                    "critic": self.critic.state_dict(),
                }
            )
        else:
            checkpoint.update(
                {
                    "actors": [actor.state_dict() for actor in self.actors],
                    "critics": [critic.state_dict() for critic in self.critics],
                }
            )
        torch.save(checkpoint, path)

    def load(self, path: str) -> None:
        checkpoint = torch.load(path, map_location=self.device)
        self._validate_checkpoint_metadata(checkpoint, algorithm="maddpg")
        metadata = checkpoint.get("metadata", {})
        if metadata.get("n_agents", self.n_agents) != self.n_agents:
            raise ValueError("checkpoint n_agents mismatch")
        if metadata.get("share_params", self.share_params) != self.share_params:
            raise ValueError("checkpoint share_params mismatch")
        self.train_step = int(checkpoint.get("train_step", 0))
        if self.share_params:
            self.actor.load_state_dict(checkpoint["actor"])
            self.critic.load_state_dict(checkpoint["critic"])
            self.actor_target = copy.deepcopy(self.actor)
            self.critic_target = copy.deepcopy(self.critic)
        else:
            for actor, state in zip(self.actors, checkpoint["actors"], strict=True):
                actor.load_state_dict(state)
            for critic, state in zip(self.critics, checkpoint["critics"], strict=True):
                critic.load_state_dict(state)
            self.actor_targets = [copy.deepcopy(actor) for actor in self.actors]
            self.critic_targets = [copy.deepcopy(critic) for critic in self.critics]
