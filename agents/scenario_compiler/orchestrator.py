from __future__ import annotations

from pathlib import Path

from game_agent.scenario_compiler import ScenarioCompiler


def run(task_text: str, task_id: str, project_root: str = ".") -> Path:
    """Compile a natural-language task into a scenario package."""
    return ScenarioCompiler(Path(project_root)).compile(task_text, task_id)
