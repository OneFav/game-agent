from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest

from game_agent.rl import (
    SUPPORTED_ALGORITHMS,
    get_algorithm_class,
    scale_action,
    unscale_action,
)
from game_agent.rl.provenance import QUARANTINED_ALGORITHMS, SOURCE_REPOSITORY

torch = pytest.importorskip("torch")


def _fill_replay_buffer(algorithm, obs_dim: int, action_dim: int) -> None:
    rng = np.random.default_rng(7)
    for index in range(8):
        obs = rng.normal(size=obs_dim).astype(np.float32)
        action = rng.uniform(-1.0, 1.0, size=action_dim).astype(np.float32)
        next_obs = rng.normal(size=obs_dim).astype(np.float32)
        algorithm.buffer.add(obs, action, float(index % 3), next_obs, index == 7)


def _assert_finite_metrics(metrics: dict[str, float]) -> None:
    assert metrics
    assert all(math.isfinite(float(value)) for value in metrics.values())


def test_registry_is_lazy_and_mappo_is_quarantined() -> None:
    assert SUPPORTED_ALGORITHMS == ("ddpg", "maddpg", "ppo", "sac")
    assert get_algorithm_class("SAC").__name__ == "SAC"
    assert SOURCE_REPOSITORY == "Sailero/mvp_inner_loop"
    assert "mappo" in QUARANTINED_ALGORITHMS
    with pytest.raises(ValueError, match="unsupported RL algorithm"):
        get_algorithm_class("mappo")


def test_action_scaling_round_trip_and_clipping() -> None:
    low = np.array([-2.0, 0.0], dtype=np.float32)
    high = np.array([2.0, 4.0], dtype=np.float32)
    scaled = scale_action(np.array([-2.0, 0.5], dtype=np.float32), low, high)
    np.testing.assert_allclose(scaled, [-2.0, 3.0])
    np.testing.assert_allclose(unscale_action(scaled, low, high), [-1.0, 0.5])
    with pytest.raises(ValueError, match="identical shapes"):
        scale_action([0.0], low, high)


@pytest.mark.parametrize("algorithm_name", ["ddpg", "sac"])
def test_off_policy_algorithms_complete_cpu_update(algorithm_name: str) -> None:
    algorithm_class = get_algorithm_class(algorithm_name)
    algorithm = algorithm_class(
        obs_dim=4,
        action_dim=2,
        hidden_dims=(8, 8),
        buffer_size=16,
        device="cpu",
    )
    _fill_replay_buffer(algorithm, obs_dim=4, action_dim=2)

    action = algorithm.select_action(np.zeros(4, dtype=np.float32), deterministic=True)
    assert action.shape == (2,)
    assert np.all(np.abs(action) <= 1.0)
    _assert_finite_metrics(algorithm.update(batch_size=4))


def test_maddpg_completes_shared_cpu_update() -> None:
    algorithm_class = get_algorithm_class("maddpg")
    algorithm = algorithm_class(
        obs_dim=4,
        action_dim=2,
        n_agents=2,
        hidden_dims=(8, 8),
        buffer_size=16,
        device="cpu",
    )
    _fill_replay_buffer(algorithm, obs_dim=8, action_dim=4)

    actions = algorithm.select_actions(
        [np.zeros(4, dtype=np.float32), np.ones(4, dtype=np.float32)],
        deterministic=True,
    )
    assert len(actions) == 2
    assert all(action.shape == (2,) for action in actions)
    _assert_finite_metrics(algorithm.update(batch_size=4))


def test_ppo_uses_stored_actions_and_completes_cpu_update() -> None:
    algorithm_class = get_algorithm_class("ppo")
    algorithm = algorithm_class(
        obs_dim=4,
        action_dim=2,
        hidden_dims=(8, 8),
        ppo_epochs=2,
        batch_size=4,
        target_kl=10.0,
        device="cpu",
    )
    rng = np.random.default_rng(11)
    for index in range(8):
        obs = rng.normal(size=4).astype(np.float32)
        action, log_prob, value = algorithm.select_action(obs)
        next_obs = rng.normal(size=4).astype(np.float32)
        algorithm.buffer.add(
            obs,
            action,
            float(index % 2),
            next_obs,
            index == 7,
            log_prob,
            value,
        )

    metrics = algorithm.update()

    _assert_finite_metrics(metrics)
    assert len(algorithm.buffer) == 0


def test_checkpoint_rejects_observation_dimension_mismatch(tmp_path: Path) -> None:
    algorithm_class = get_algorithm_class("ddpg")
    source = algorithm_class(obs_dim=4, action_dim=2, hidden_dims=(8, 8), device="cpu")
    checkpoint = tmp_path / "ddpg.pt"
    source.save(str(checkpoint))
    incompatible = algorithm_class(
        obs_dim=5,
        action_dim=2,
        hidden_dims=(8, 8),
        device="cpu",
    )

    with pytest.raises(ValueError, match="obs_dim mismatch"):
        incompatible.load(str(checkpoint))
