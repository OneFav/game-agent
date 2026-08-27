from __future__ import annotations

from typing import Any

import numpy as np
import torch


class ReplayBuffer:
    def __init__(self, capacity: int, obs_dim: int, action_dim: int) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self.capacity = int(capacity)
        self.pointer = 0
        self.size = 0
        self.obs = np.zeros((capacity, obs_dim), dtype=np.float32)
        self.action = np.zeros((capacity, action_dim), dtype=np.float32)
        self.reward = np.zeros((capacity, 1), dtype=np.float32)
        self.next_obs = np.zeros((capacity, obs_dim), dtype=np.float32)
        self.done = np.zeros((capacity, 1), dtype=np.float32)

    def add(
        self,
        obs: Any,
        action: Any,
        reward: float,
        next_obs: Any,
        done: bool | float,
    ) -> None:
        self.obs[self.pointer] = obs
        self.action[self.pointer] = action
        self.reward[self.pointer] = reward
        self.next_obs[self.pointer] = next_obs
        self.done[self.pointer] = done
        self.pointer = (self.pointer + 1) % self.capacity
        self.size = min(self.size + 1, self.capacity)

    def sample(
        self,
        batch_size: int,
        device: str | torch.device = "cpu",
    ) -> dict[str, torch.Tensor]:
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        if self.size < batch_size:
            raise ValueError("not enough transitions to sample the requested batch")
        indices = np.random.randint(0, self.size, size=batch_size)
        return {
            "obs": torch.as_tensor(self.obs[indices], device=device),
            "action": torch.as_tensor(self.action[indices], device=device),
            "reward": torch.as_tensor(self.reward[indices], device=device),
            "next_obs": torch.as_tensor(self.next_obs[indices], device=device),
            "done": torch.as_tensor(self.done[indices], device=device),
        }

    def __len__(self) -> int:
        return self.size


class TrajectoryBuffer:
    def __init__(self) -> None:
        self.obs: list[Any] = []
        self.action: list[Any] = []
        self.reward: list[float] = []
        self.next_obs: list[Any] = []
        self.done: list[bool | float] = []
        self.log_prob: list[Any] = []
        self.value: list[Any] = []

    def add(
        self,
        obs: Any,
        action: Any,
        reward: float,
        next_obs: Any,
        done: bool | float,
        log_prob: Any,
        value: Any,
    ) -> None:
        self.obs.append(obs)
        self.action.append(action)
        self.reward.append(reward)
        self.next_obs.append(next_obs)
        self.done.append(done)
        self.log_prob.append(log_prob)
        self.value.append(value)

    def get(self, device: str | torch.device = "cpu") -> dict[str, torch.Tensor]:
        data = {
            "obs": torch.as_tensor(np.asarray(self.obs), dtype=torch.float32, device=device),
            "action": torch.as_tensor(np.asarray(self.action), dtype=torch.float32, device=device),
            "reward": torch.as_tensor(np.asarray(self.reward), dtype=torch.float32, device=device),
            "next_obs": torch.as_tensor(
                np.asarray(self.next_obs),
                dtype=torch.float32,
                device=device,
            ),
            "done": torch.as_tensor(np.asarray(self.done), dtype=torch.float32, device=device),
            "log_prob": torch.as_tensor(
                np.asarray(self.log_prob),
                dtype=torch.float32,
                device=device,
            ).reshape(-1),
            "value": torch.as_tensor(
                np.asarray(self.value),
                dtype=torch.float32,
                device=device,
            ).reshape(-1),
        }
        self.clear()
        return data

    def clear(self) -> None:
        self.obs.clear()
        self.action.clear()
        self.reward.clear()
        self.next_obs.clear()
        self.done.clear()
        self.log_prob.clear()
        self.value.clear()

    def __len__(self) -> int:
        return len(self.obs)
