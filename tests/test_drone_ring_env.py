import numpy as np
import pytest

from game_agent.envs.drone_ring_game.env import DroneRingEnv


def test_reset_is_deterministic_for_same_seed() -> None:
    env = DroneRingEnv({"ring_count": 2, "max_steps": 50})
    obs_a, info_a = env.reset(seed=7)
    obs_b, info_b = env.reset(seed=7)
    assert set(obs_a) == {"red_0", "blue_0"}
    for agent_id in {"red_0", "blue_0"}:
        assert np.allclose(obs_a[agent_id], obs_b[agent_id])
    assert info_a["seed"] == info_b["seed"] == 7


def test_step_returns_parallel_api_shapes() -> None:
    env = DroneRingEnv({"ring_count": 1, "max_steps": 10})
    obs, _ = env.reset(seed=0)
    actions = {agent_id: np.zeros(4, dtype=np.float32) for agent_id in obs}
    next_obs, rewards, terminated, truncated, info = env.step(actions)
    assert next_obs["red_0"].shape == (12,)
    assert rewards.keys() == next_obs.keys()
    assert terminated.keys() == next_obs.keys()
    assert truncated.keys() == next_obs.keys()
    assert "metrics" in info
    assert {"success", "collision", "out_of_bounds", "episode_length"}.issubset(info["metrics"])
    for agent_obs in next_obs.values():
        assert agent_obs.shape == (12,)
        assert agent_obs.dtype == np.float32


def test_timeout_only_truncates_without_terminating() -> None:
    env = DroneRingEnv({"ring_count": 1, "max_steps": 1})
    obs, _ = env.reset(seed=0)
    actions = {agent_id: np.zeros(4, dtype=np.float32) for agent_id in obs}
    _, _, terminated, truncated, info = env.step(actions)
    assert all(value is False for value in terminated.values())
    assert all(value is True for value in truncated.values())
    assert info["metrics"]["timeout"] is True


def test_terminal_on_last_step_is_not_truncated() -> None:
    env = DroneRingEnv({"ring_count": 1, "max_steps": 1, "ring_radius": 99.0})
    obs, _ = env.reset(seed=0)
    actions = {agent_id: np.zeros(4, dtype=np.float32) for agent_id in obs}
    _, _, terminated, truncated, info = env.step(actions)
    assert all(value is True for value in terminated.values())
    assert all(value is False for value in truncated.values())
    assert info["metrics"]["success"] is True
    assert info["metrics"]["timeout"] is False


def test_invalid_action_shape_raises_value_error() -> None:
    env = DroneRingEnv({"ring_count": 1, "max_steps": 10})
    obs, _ = env.reset(seed=0)
    actions = {agent_id: np.zeros(4, dtype=np.float32) for agent_id in obs}
    actions["red_0"] = np.zeros(3, dtype=np.float32)
    with pytest.raises(ValueError):
        env.step(actions)
