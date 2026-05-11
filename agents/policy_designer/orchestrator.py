from __future__ import annotations

from pathlib import Path

from game_agent.policy_designer import PolicyDesigner


def run(scenario_dir: str, policy_id: str, project_root: str = ".") -> Path:
    """Build a policy package for an existing validated scenario."""
    return PolicyDesigner(Path(project_root)).build(Path(scenario_dir), policy_id)
