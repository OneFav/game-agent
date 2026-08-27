from __future__ import annotations

import numpy as np
import torch


class OUNoise:
    def __init__(
        self,
        action_dim: int,
        mu: float = 0.0,
        theta: float = 0.15,
        sigma: float = 0.2,
    ) -> None:
        self.action_dim = action_dim
        self.mu = mu
        self.theta = theta
        self.sigma = sigma
        self.state = np.full(action_dim, mu, dtype=np.float32)

    def reset(self) -> None:
        self.state.fill(self.mu)

    def sample(self) -> np.ndarray:
        delta = self.theta * (self.mu - self.state)
        delta += self.sigma * np.random.randn(self.action_dim)
        self.state += delta
        return self.state.copy()


def compute_gae(
    rewards: torch.Tensor,
    values: torch.Tensor,
    next_values: torch.Tensor,
    dones: torch.Tensor,
    gamma: float = 0.99,
    gae_lambda: float = 0.95,
) -> tuple[torch.Tensor, torch.Tensor]:
    advantages = torch.zeros_like(rewards)
    last_gae = torch.zeros((), dtype=rewards.dtype, device=rewards.device)
    for index in reversed(range(rewards.shape[0])):
        next_value = next_values[index] if index == rewards.shape[0] - 1 else values[index + 1]
        not_done = 1.0 - dones[index]
        delta = rewards[index] + gamma * next_value * not_done - values[index]
        last_gae = delta + gamma * gae_lambda * not_done * last_gae
        advantages[index] = last_gae
    return advantages, advantages + values


class ObservationNormalizer:
    def __init__(self, obs_dim: int, clip_range: float = 10.0) -> None:
        self.clip_range = clip_range
        self.mean = np.zeros(obs_dim, dtype=np.float32)
        self.var = np.ones(obs_dim, dtype=np.float32)
        self.count = 1e-4

    def update(self, obs: np.ndarray) -> None:
        observations = np.atleast_2d(obs)
        batch_mean = observations.mean(axis=0)
        batch_var = observations.var(axis=0)
        batch_count = observations.shape[0]
        delta = batch_mean - self.mean
        total_count = self.count + batch_count
        self.mean += delta * batch_count / total_count
        first_moment = self.var * self.count
        second_moment = batch_var * batch_count
        combined = (
            first_moment
            + second_moment
            + delta**2 * self.count * batch_count / total_count
        )
        self.var = combined / total_count
        self.count = total_count

    def normalize(self, obs: np.ndarray) -> np.ndarray:
        normalized = (obs - self.mean) / (np.sqrt(self.var) + 1e-8)
        return np.clip(normalized, -self.clip_range, self.clip_range)
