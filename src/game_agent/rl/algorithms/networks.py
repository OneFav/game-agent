from __future__ import annotations

from collections.abc import Sequence

import torch
from torch import nn
from torch.distributions import Normal


def resolve_activation(name: str) -> type[nn.Module]:
    mapping = {"relu": nn.ReLU, "tanh": nn.Tanh, "elu": nn.ELU}
    try:
        return mapping[name.lower()]
    except KeyError as error:
        raise ValueError(f"unsupported activation: {name}") from error


def build_mlp(
    input_dim: int,
    output_dim: int,
    hidden_dims: Sequence[int],
    activation: type[nn.Module] = nn.ReLU,
) -> nn.Sequential:
    layers: list[nn.Module] = []
    previous_dim = input_dim
    for hidden_dim in hidden_dims:
        layers.extend(
            [
                nn.Linear(previous_dim, hidden_dim),
                nn.LayerNorm(hidden_dim),
                activation(),
            ]
        )
        previous_dim = hidden_dim
    layers.append(nn.Linear(previous_dim, output_dim))
    return nn.Sequential(*layers)


class DeterministicActor(nn.Module):
    def __init__(
        self,
        obs_dim: int,
        action_dim: int,
        hidden_dims: Sequence[int],
        max_action: float = 1.0,
        activation: str = "relu",
    ) -> None:
        super().__init__()
        self.net = build_mlp(
            obs_dim,
            action_dim,
            hidden_dims,
            resolve_activation(activation),
        )
        self.max_action = float(max_action)

    def forward(self, obs: torch.Tensor) -> torch.Tensor:
        return torch.tanh(self.net(obs)) * self.max_action


class GaussianActor(nn.Module):
    def __init__(
        self,
        obs_dim: int,
        action_dim: int,
        hidden_dims: Sequence[int],
        max_action: float = 1.0,
        log_std_min: float = -20.0,
        log_std_max: float = 2.0,
        activation: str = "relu",
    ) -> None:
        super().__init__()
        if not hidden_dims:
            raise ValueError("GaussianActor requires at least one hidden layer")
        self.max_action = float(max_action)
        self.log_std_min = float(log_std_min)
        self.log_std_max = float(log_std_max)
        self.backbone = build_mlp(
            obs_dim,
            hidden_dims[-1],
            hidden_dims[:-1],
            resolve_activation(activation),
        )
        self.mean_layer = nn.Linear(hidden_dims[-1], action_dim)
        self.log_std_layer = nn.Linear(hidden_dims[-1], action_dim)

    def distribution(self, obs: torch.Tensor) -> Normal:
        hidden = self.backbone(obs)
        mean = self.mean_layer(hidden)
        log_std = torch.clamp(
            self.log_std_layer(hidden),
            self.log_std_min,
            self.log_std_max,
        )
        return Normal(mean, log_std.exp())

    def forward(
        self,
        obs: torch.Tensor,
        deterministic: bool = False,
    ) -> tuple[torch.Tensor, torch.Tensor | None, Normal | None]:
        distribution = self.distribution(obs)
        if deterministic:
            return torch.tanh(distribution.mean) * self.max_action, None, None
        latent = distribution.rsample()
        normalized_action = torch.tanh(latent)
        action = normalized_action * self.max_action
        log_prob = self._squashed_log_prob(distribution, latent, normalized_action)
        return action, log_prob, distribution

    def evaluate_actions(
        self,
        obs: torch.Tensor,
        actions: torch.Tensor,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        """计算已采样动作的概率；PPO 必须使用轨迹中的动作。"""

        distribution = self.distribution(obs)
        epsilon = 1e-6
        normalized = torch.clamp(
            actions / self.max_action,
            -1.0 + epsilon,
            1.0 - epsilon,
        )
        latent = torch.atanh(normalized)
        log_prob = self._squashed_log_prob(distribution, latent, normalized)
        return log_prob, distribution.entropy().sum(dim=-1, keepdim=True)

    def _squashed_log_prob(
        self,
        distribution: Normal,
        latent: torch.Tensor,
        normalized_action: torch.Tensor,
    ) -> torch.Tensor:
        correction = torch.log(
            self.max_action * (1.0 - normalized_action.pow(2)) + 1e-6
        )
        return (distribution.log_prob(latent) - correction).sum(dim=-1, keepdim=True)


class Critic(nn.Module):
    def __init__(
        self,
        obs_dim: int,
        action_dim: int,
        hidden_dims: Sequence[int],
        activation: str = "relu",
    ) -> None:
        super().__init__()
        self.net = build_mlp(
            obs_dim + action_dim,
            1,
            hidden_dims,
            resolve_activation(activation),
        )

    def forward(self, obs: torch.Tensor, action: torch.Tensor) -> torch.Tensor:
        return self.net(torch.cat([obs, action], dim=-1))


class ValueCritic(nn.Module):
    def __init__(
        self,
        obs_dim: int,
        hidden_dims: Sequence[int],
        activation: str = "relu",
    ) -> None:
        super().__init__()
        self.net = build_mlp(obs_dim, 1, hidden_dims, resolve_activation(activation))

    def forward(self, obs: torch.Tensor) -> torch.Tensor:
        return self.net(obs)


class TwinCritic(nn.Module):
    def __init__(
        self,
        obs_dim: int,
        action_dim: int,
        hidden_dims: Sequence[int],
        activation: str = "relu",
    ) -> None:
        super().__init__()
        self.q1 = Critic(obs_dim, action_dim, hidden_dims, activation)
        self.q2 = Critic(obs_dim, action_dim, hidden_dims, activation)

    def forward(
        self,
        obs: torch.Tensor,
        action: torch.Tensor,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        return self.q1(obs, action), self.q2(obs, action)
