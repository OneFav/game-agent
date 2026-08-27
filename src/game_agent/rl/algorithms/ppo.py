from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import torch
from torch.nn import functional as functional
from torch.nn.utils import clip_grad_norm_
from torch.optim import Adam

from game_agent.rl.algorithms.base import BaseRLAlgorithm
from game_agent.rl.algorithms.buffer import TrajectoryBuffer
from game_agent.rl.algorithms.networks import GaussianActor, ValueCritic
from game_agent.rl.algorithms.utils import compute_gae


class PPO(BaseRLAlgorithm):
    """使用轨迹中已执行动作计算概率比的连续动作 PPO。"""

    def __init__(
        self,
        obs_dim: int,
        action_dim: int,
        hidden_dims: Sequence[int] = (256, 256),
        lr_actor: float = 3e-4,
        lr_critic: float = 3e-4,
        gamma: float = 0.99,
        gae_lambda: float = 0.95,
        clip_ratio: float = 0.2,
        ppo_epochs: int = 10,
        batch_size: int = 64,
        target_kl: float = 0.01,
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
            device=device,
        )
        self.gae_lambda = float(gae_lambda)
        self.clip_ratio = float(clip_ratio)
        self.ppo_epochs = int(ppo_epochs)
        self.batch_size = int(batch_size)
        self.target_kl = float(target_kl)
        self.max_action = float(max_action)
        self.actor = GaussianActor(
            obs_dim,
            action_dim,
            self.hidden_dims,
            max_action,
            activation=activation,
        ).to(self.device)
        self.critic = ValueCritic(obs_dim, self.hidden_dims, activation).to(self.device)
        self.actor_optimizer = Adam(self.actor.parameters(), lr=lr_actor)
        self.critic_optimizer = Adam(self.critic.parameters(), lr=lr_critic)
        self.buffer = TrajectoryBuffer()

    def select_action(
        self,
        obs: np.ndarray,
        deterministic: bool = False,
    ) -> tuple[np.ndarray, float, float]:
        with torch.no_grad():
            observation = torch.as_tensor(
                obs,
                dtype=torch.float32,
                device=self.device,
            ).unsqueeze(0)
            action, log_prob, _ = self.actor(observation, deterministic)
            value = self.critic(observation)
        log_prob_value = 0.0 if log_prob is None else float(log_prob.item())
        return action.cpu().numpy()[0], log_prob_value, float(value.item())

    def update(self) -> dict[str, float]:
        if len(self.buffer) == 0:
            return {}
        data = self.buffer.get(self.device)
        with torch.no_grad():
            next_values = self.critic(data["next_obs"]).squeeze(-1)
            advantages, returns = compute_gae(
                data["reward"],
                data["value"],
                next_values,
                data["done"],
                self.gamma,
                self.gae_lambda,
            )
            advantages = (advantages - advantages.mean()) / (
                advantages.std(unbiased=False) + 1e-8
            )

        total_actor_loss = 0.0
        total_critic_loss = 0.0
        total_kl = 0.0
        update_count = 0
        epochs_completed = 0
        for epoch in range(self.ppo_epochs):
            indices = torch.randperm(len(data["obs"]), device=self.device)
            epoch_kl = 0.0
            epoch_updates = 0
            for start in range(0, len(indices), self.batch_size):
                batch_indices = indices[start : start + self.batch_size]
                batch_obs = data["obs"][batch_indices]
                batch_actions = data["action"][batch_indices]
                old_log_prob = data["log_prob"][batch_indices]
                batch_advantages = advantages[batch_indices]
                batch_returns = returns[batch_indices]

                new_log_prob, _ = self.actor.evaluate_actions(batch_obs, batch_actions)
                new_log_prob = new_log_prob.squeeze(-1)
                values = self.critic(batch_obs).squeeze(-1)
                log_ratio = new_log_prob - old_log_prob
                ratio = log_ratio.exp()
                unclipped = ratio * batch_advantages
                clipped = torch.clamp(
                    ratio,
                    1.0 - self.clip_ratio,
                    1.0 + self.clip_ratio,
                ) * batch_advantages
                actor_loss = -torch.minimum(unclipped, clipped).mean()
                critic_loss = functional.mse_loss(values, batch_returns)

                self.actor_optimizer.zero_grad()
                actor_loss.backward()
                clip_grad_norm_(self.actor.parameters(), 0.5)
                self.actor_optimizer.step()
                self.critic_optimizer.zero_grad()
                critic_loss.backward()
                clip_grad_norm_(self.critic.parameters(), 0.5)
                self.critic_optimizer.step()

                approximate_kl = float((-log_ratio).mean().detach().cpu())
                total_actor_loss += actor_loss.item()
                total_critic_loss += critic_loss.item()
                total_kl += abs(approximate_kl)
                epoch_kl += abs(approximate_kl)
                update_count += 1
                epoch_updates += 1
            epochs_completed = epoch + 1
            if epoch_updates and epoch_kl / epoch_updates > 1.5 * self.target_kl:
                break

        self.train_step += 1
        return {
            "actor_loss": total_actor_loss / update_count,
            "critic_loss": total_critic_loss / update_count,
            "kl_divergence": total_kl / update_count,
            "ppo_epochs": float(epochs_completed),
        }

    def save(self, path: str) -> None:
        torch.save(
            {
                "metadata": self._checkpoint_metadata("ppo"),
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
        self._validate_checkpoint_metadata(checkpoint, algorithm="ppo")
        self.actor.load_state_dict(checkpoint["actor"])
        self.critic.load_state_dict(checkpoint["critic"])
        self.actor_optimizer.load_state_dict(checkpoint["actor_optimizer"])
        self.critic_optimizer.load_state_dict(checkpoint["critic_optimizer"])
        self.train_step = int(checkpoint.get("train_step", 0))
