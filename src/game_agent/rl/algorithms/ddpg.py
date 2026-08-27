from __future__ import annotations

import copy
from collections.abc import Sequence

import numpy as np
import torch
from torch.nn import functional as functional
from torch.nn.utils import clip_grad_norm_
from torch.optim import Adam

from game_agent.rl.algorithms.base import BaseRLAlgorithm
from game_agent.rl.algorithms.buffer import ReplayBuffer
from game_agent.rl.algorithms.networks import Critic, DeterministicActor
from game_agent.rl.algorithms.utils import OUNoise


class DDPG(BaseRLAlgorithm):
    """用于连续动作空间的确定性 off-policy 算法。"""

    def __init__(
        self,
        obs_dim: int,
        action_dim: int,
        hidden_dims: Sequence[int] = (256, 256),
        lr_actor: float = 1e-4,
        lr_critic: float = 3e-4,
        gamma: float = 0.99,
        tau: float = 0.005,
        buffer_size: int = 1_000_000,
        noise_std: float = 0.1,
        max_action: float = 1.0,
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
        self.max_action = float(max_action)
        self.noise_std = float(noise_std)
        self.actor = DeterministicActor(
            obs_dim,
            action_dim,
            self.hidden_dims,
            max_action,
            activation,
        ).to(self.device)
        self.actor_target = copy.deepcopy(self.actor)
        self.critic = Critic(obs_dim, action_dim, self.hidden_dims, activation).to(self.device)
        self.critic_target = copy.deepcopy(self.critic)
        self.actor_optimizer = Adam(self.actor.parameters(), lr=lr_actor)
        self.critic_optimizer = Adam(self.critic.parameters(), lr=lr_critic)
        self.buffer = ReplayBuffer(buffer_size, obs_dim, action_dim)
        self.noise = OUNoise(action_dim, sigma=noise_std)

    def set_noise_std(self, sigma: float) -> None:
        self.noise_std = float(sigma)
        self.noise.sigma = self.noise_std

    def select_action(
        self,
        obs: np.ndarray,
        deterministic: bool = False,
    ) -> np.ndarray:
        with torch.no_grad():
            observation = torch.as_tensor(
                obs,
                dtype=torch.float32,
                device=self.device,
            ).unsqueeze(0)
            action = self.actor(observation).cpu().numpy()[0]
        if not deterministic:
            action = action + self.noise.sample()
        return np.clip(action, -self.max_action, self.max_action)

    def update(self, batch_size: int = 256) -> dict[str, float]:
        if len(self.buffer) < batch_size:
            return {}
        batch = self.buffer.sample(batch_size, self.device)
        with torch.no_grad():
            next_action = self.actor_target(batch["next_obs"])
            target_q = self.critic_target(batch["next_obs"], next_action)
            target_q = batch["reward"] + (
                1.0 - batch["done"]
            ) * self.gamma * target_q

        current_q = self.critic(batch["obs"], batch["action"])
        critic_loss = functional.mse_loss(current_q, target_q)
        self.critic_optimizer.zero_grad()
        critic_loss.backward()
        clip_grad_norm_(self.critic.parameters(), 1.0)
        self.critic_optimizer.step()

        actor_loss = -self.critic(batch["obs"], self.actor(batch["obs"])).mean()
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

    def save(self, path: str) -> None:
        torch.save(
            {
                "metadata": self._checkpoint_metadata("ddpg"),
                "actor": self.actor.state_dict(),
                "critic": self.critic.state_dict(),
                "actor_optimizer": self.actor_optimizer.state_dict(),
                "critic_optimizer": self.critic_optimizer.state_dict(),
                "train_step": self.train_step,
            },
            path,
        )

    def load(self, path: str) -> None:
        checkpoint = torch.load(path, map_location=self.device)
        self._validate_checkpoint_metadata(checkpoint, algorithm="ddpg")
        self.actor.load_state_dict(checkpoint["actor"])
        self.critic.load_state_dict(checkpoint["critic"])
        self.actor_optimizer.load_state_dict(checkpoint["actor_optimizer"])
        self.critic_optimizer.load_state_dict(checkpoint["critic_optimizer"])
        self.train_step = int(checkpoint.get("train_step", 0))
        self.actor_target = copy.deepcopy(self.actor)
        self.critic_target = copy.deepcopy(self.critic)
