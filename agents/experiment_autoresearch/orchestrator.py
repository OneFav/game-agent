from __future__ import annotations

from pathlib import Path

from game_agent.autoresearch import AutoResearchRunner


def run(scenario_dir: str, policy_dir: str, exp_id: str, project_root: str = ".") -> Path:
    """Run AutoResearch for frozen scenario and policy packages."""
    return AutoResearchRunner(Path(project_root)).run(Path(scenario_dir), Path(policy_dir), exp_id)
