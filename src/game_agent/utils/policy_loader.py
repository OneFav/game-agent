from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

from contracts.policy_protocol import Policy
from game_agent.utils.fs import read_yaml


def load_policy(
    policy_dir: Path,
    env_spec: dict[str, Any],
) -> tuple[Policy, dict[str, Any]]:
    """Load one frozen policy package without depending on the current directory."""

    policy_dir = Path(policy_dir).resolve()
    policy_path = policy_dir / "policy.py"
    config_path = policy_dir / "default_config.yaml"
    if not policy_path.is_file():
        raise FileNotFoundError(f"policy.py does not exist: {policy_path}")
    if not config_path.is_file():
        raise FileNotFoundError(f"default_config.yaml does not exist: {config_path}")

    module_name = f"_suite_policy_{policy_dir.name}_{abs(hash(policy_path))}"
    module_spec = importlib.util.spec_from_file_location(module_name, policy_path)
    if module_spec is None or module_spec.loader is None:
        raise ImportError(f"cannot load policy module: {policy_path}")
    module = importlib.util.module_from_spec(module_spec)
    old_sys_path = list(sys.path)
    try:
        sys.path = [str(policy_dir), *old_sys_path]
        module_spec.loader.exec_module(module)
    finally:
        sys.path = old_sys_path

    policy_class = getattr(module, "PolicyClass", None)
    if not isinstance(policy_class, type) or not issubclass(policy_class, Policy):
        raise TypeError(f"{policy_path} must expose a PolicyClass subclass")
    config = read_yaml(config_path)
    return policy_class(config, env_spec), config
