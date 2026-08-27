from __future__ import annotations

import numpy as np


def _validated_bounds(
    low: np.ndarray | list[float],
    high: np.ndarray | list[float],
) -> tuple[np.ndarray, np.ndarray]:
    low_array = np.asarray(low, dtype=np.float32)
    high_array = np.asarray(high, dtype=np.float32)
    if low_array.shape != high_array.shape:
        raise ValueError("action bounds must have identical shapes")
    if np.any(~np.isfinite(low_array)) or np.any(~np.isfinite(high_array)):
        raise ValueError("action bounds must be finite")
    if np.any(high_array <= low_array):
        raise ValueError("every action high bound must be greater than its low bound")
    return low_array, high_array


def scale_action(
    normalized_action: np.ndarray | list[float],
    low: np.ndarray | list[float],
    high: np.ndarray | list[float],
) -> np.ndarray:
    """将策略的 ``[-1, 1]`` 输出映射到场景动作边界。"""

    low_array, high_array = _validated_bounds(low, high)
    normalized = np.asarray(normalized_action, dtype=np.float32)
    if normalized.shape != low_array.shape:
        raise ValueError("action and bounds must have identical shapes")
    normalized = np.clip(normalized, -1.0, 1.0)
    return low_array + (normalized + 1.0) * 0.5 * (high_array - low_array)


def unscale_action(
    action: np.ndarray | list[float],
    low: np.ndarray | list[float],
    high: np.ndarray | list[float],
) -> np.ndarray:
    """将场景动作转换回策略使用的 ``[-1, 1]`` 坐标。"""

    low_array, high_array = _validated_bounds(low, high)
    action_array = np.asarray(action, dtype=np.float32)
    if action_array.shape != low_array.shape:
        raise ValueError("action and bounds must have identical shapes")
    normalized = 2.0 * (action_array - low_array) / (high_array - low_array) - 1.0
    return np.clip(normalized, -1.0, 1.0)
