from __future__ import annotations

import copy
from collections.abc import Sequence

import numpy as np
import torch
from torch.nn import functional as functional
from torch.optim import Adam

from game_agent.rl.algorithms.base import BaseRLAlgorithm
from game_agent.rl.algorithms.buffer import ReplayBuffer
from game_agent.rl.algorithms.networks import GaussianActor, TwinCritic


class SAC(BaseRLAlgorithm):
    """带双 Q 网络和可选自动温度调节的 Soft Actor-Critic。"""

    def __init__(
        self,
        obs_dim: int,
        action_dim: int,
        hidden_dims: Sequence[int] = (256, 256),
        lr_actor: float = 3e-4,
        lr_critic: float = 3e-4,
        lr_alpha: float = 3e-4,
        gamma: float = 0.99,
        tau: float = 0.005,
        buffer_size: int = 1_000_000,
        alpha: float = 0.2,
        auto_alpha: bool = True,
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
        self.auto_alpha = bool(auto_alpha)
        self.actor = GaussianActor(
            obs_dim,
            action_dim,
            self.hidden_dims,
            max_action,
            activation=activation,
        ).to(self.device)
        self.critic = TwinCritic(
            obs_dim,
            action_dim,
            self.hidden_dims,
            activation,
        ).to(self.device)
        self.critic_target = copy.deepcopy(self.critic)
        self.actor_optimizer = Adam(self.actor.parameters(), lr=lr_actor)
        self.critic_optimizer = Adam(self.critic.parameters(), lr=lr_critic)
        if self.auto_alpha:
            self.target_entropy = -float(action_dim)
            self.log_alpha = torch.zeros(1, requires_grad=True, device=self.device)
            self.alpha_optimizer = Adam([self.log_alpha], lr=lr_alpha)
            self.alpha: float | torch.Tensor = self.log_alpha.exp()
        else:
            self.alpha = float(alpha)
        self.buffer = ReplayBuffer(buffer_size, obs_dim, action_dim)

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
            action, _, _ = self.actor(observation, deterministic)
        return action.cpu().numpy()[0]

    def update(self, batch_size: int = 256) -> dict[str, float]:
        if len(self.buffer) < batch_size:
            return {}
        batch = self.buffer.sample(batch_size, self.device)
        alpha = self.alpha if isinstance(self.alpha, float) else self.alpha.detach()
        with torch.no_grad():
            next_action, next_log_prob, _ = self.actor(batch["next_obs"])
            assert next_log_prob is not None
            next_q1, next_q2 = self.critic_target(batch["next_obs"], next_action)
            next_q = torch.minimum(next_q1, next_q2)
            target_q = batch["reward"] + (1.0 - batch["done"]) * self.gamma * (
                next_q - alpha * next_log_prob
            )

        q1, q2 = self.critic(batch["obs"], batch["action"])
        critic_loss = functional.mse_loss(q1, target_q) + functional.mse_loss(q2, target_q)
        self.critic_optimizer.zero_grad()
        critic_loss.backward()
        self.critic_optimizer.step()

        new_action, new_log_prob, _ = self.actor(batch["obs"])
        assert new_log_prob is not None
        new_q1, new_q2 = self.critic(batch["obs"], new_action)
        new_q = torch.minimum(new_q1, new_q2)
        actor_alpha = self.alpha if isinstance(self.alpha, float) else self.alpha.detach()
        actor_loss = (actor_alpha * new_log_prob - new_q).mean()
        self.actor_optimizer.zero_grad()
        actor_loss.backward()
        self.actor_optimizer.step()

        alpha_loss_value = 0.0
        if self.auto_alpha:
            alpha_loss = -(
                self.log_alpha * (new_log_prob + self.target_entropy).detach()
            ).mean()
            self.alpha_optimizer.zero_grad()
            alpha_loss.backward()
            self.alpha_optimizer.step()
            self.alpha = self.log_alpha.exp()
            alpha_loss_value = alpha_loss.item()

        self._soft_update(self.critic_target, self.critic)
        self.train_step += 1
        alpha_value = self.alpha if isinstance(self.alpha, float) else self.alpha.item()
        return {
            "critic_loss": critic_loss.item(),
            "actor_loss": actor_loss.item(),
            "alpha": float(alpha_value),
            "alpha_loss": alpha_loss_value,
            "q_value": q1.mean().item(),
        }

    def save(self, path: str) -> None:
        checkpoint = {
            "metadata": self._checkpoint_metadata("sac"),
            "actor": self.actor.state_dict(),
            "critic": self.critic.state_dict(),
            "actor_optimizer": self.actor_optimizer.state_dict(),
            "critic_optimizer": self.critic_optimizer.state_dict(),
            "train_step": self.train_step,
        }
        if self.auto_alpha:
            checkpoint["log_alpha"] = self.log_alpha.detach().cpu()
            checkpoint["alpha_optimizer"] = self.alpha_optimizer.state_dict()
        torch.save(checkpoint, path)

    def load(self, path: str) -> None:
        checkpoint = torch.load(path, map_location=self.device)
        self._validate_checkpoint_metadata(checkpoint, algorithm="sac")
        self.actor.load_state_dict(checkpoint["actor"])
        self.critic.load_state_dict(checkpoint["critic"])
        self.actor_optimizer.load_state_dict(checkpoint["actor_optimizer"])
        self.critic_optimizer.load_state_dict(checkpoint["critic_optimizer"])
        self.train_step = int(checkpoint.get("train_step", 0))
        if self.auto_alpha and "log_alpha" in checkpoint:
            with torch.no_grad():
                self.log_alpha.copy_(checkpoint["log_alpha"].to(self.device))
            self.alpha_optimizer.load_state_dict(checkpoint["alpha_optimizer"])
            self.alpha = self.log_alpha.exp()
        self.critic_target = copy.deepcopy(self.critic)
