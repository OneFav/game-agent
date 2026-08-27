# Game Agent M1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a lightweight but runnable three-agent M1 vertical slice for semi-free natural-language drone-ring tasks, generated policies, deterministic sweep experiments, and root capability/roadmap documentation.

**Architecture:** Keep three boundaries real: Scenario Compiler writes `scenarios/<task_id>/`, Policy Designer writes `policies/<policy_id>/`, and AutoResearch writes `experiments/<exp_id>/`. Shared runtime code lives in `game_agent/`; contracts live in `contracts/`; validation gates live in `hooks/`; CLI is the only user-facing entry point.

**Tech Stack:** Python 3.10+, standard library, `numpy`, `PyYAML`, `pytest`; no PettingZoo, Gymnasium, RL framework, MCP server, or git workflow in M1.

---

## Scope Check

The approved spec covers several subsystems, but they form one testable M1 vertical slice. Implement in this order: package base, contracts, environment, Scenario Compiler, Policy Designer, AutoResearch, hooks, CLI, agent/skill content, full verification.

Project instructions say not to plan git operations unless explicitly requested, so this plan uses verification checkpoints instead of commit steps.

## File Structure Map

```text
game_agent/
├─ __init__.py
├─ __main__.py
├─ cli.py
├─ scenario_compiler/{__init__.py,compiler.py,templates.py}
├─ policy_designer/{__init__.py,designer.py,templates.py}
├─ autoresearch/{__init__.py,runner.py,metrics.py}
├─ envs/{__init__.py,drone_ring_game/__init__.py,drone_ring_game/env.py}
└─ utils/{__init__.py,errors.py,fs.py,manifest.py}

agents/
├─ scenario_compiler/{AGENTS.md,prompt.md,orchestrator.py}
├─ policy_designer/{AGENTS.md,prompt.md,orchestrator.py}
└─ experiment_autoresearch/{AGENTS.md,prompt.md,orchestrator.py}

.agents/skills/
├─ scenario-spec-compiler/SKILL.md
├─ policy-interface-builder/SKILL.md
└─ autoresearch-loop/SKILL.md

contracts/{scenario_schema.yaml,policy_protocol.py}
hooks/{post_scenario_compile.py,post_policy_submit.py,post_experiment_run.py}
tests/{test_utils.py,test_contracts.py,test_drone_ring_env.py,test_scenario_compiler.py,test_policy_designer.py,test_autoresearch.py,test_hooks.py,test_cli_smoke.py,test_agent_project_content.py}
pyproject.toml
report.md
task.md
```

---

### Task 1: Project package base and shared utilities

**Files:**
- Create: `pyproject.toml`
- Create: `game_agent/__init__.py`
- Create: `game_agent/__main__.py`
- Create: `game_agent/utils/__init__.py`
- Create: `game_agent/utils/errors.py`
- Create: `game_agent/utils/fs.py`
- Create: `game_agent/utils/manifest.py`
- Test: `tests/test_utils.py`

- [ ] **Step 1: Write failing utility tests**

Create `tests/test_utils.py`:

```python
from pathlib import Path

from game_agent.utils.fs import ensure_empty_output_dir, read_yaml, write_yaml
from game_agent.utils.manifest import build_manifest


def test_yaml_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "sample.yaml"
    write_yaml(path, {"name": "drone_ring", "value": 3})
    assert read_yaml(path) == {"name": "drone_ring", "value": 3}


def test_ensure_empty_output_dir_rejects_existing_content(tmp_path: Path) -> None:
    out = tmp_path / "scenario"
    out.mkdir()
    (out / "existing.txt").write_text("content", encoding="utf-8")
    try:
        ensure_empty_output_dir(out)
    except FileExistsError as exc:
        assert "Refusing to overwrite" in str(exc)
    else:
        raise AssertionError("expected FileExistsError")


def test_build_manifest_hash_changes_with_content(tmp_path: Path) -> None:
    root = tmp_path / "package"
    root.mkdir()
    file_path = root / "a.txt"
    file_path.write_text("one", encoding="utf-8")
    first = build_manifest(root, package_type="scenario", package_id="demo")
    file_path.write_text("two", encoding="utf-8")
    second = build_manifest(root, package_type="scenario", package_id="demo")
    assert first["freeze_hash"] != second["freeze_hash"]
    assert first["package_type"] == "scenario"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_utils.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'game_agent'`.

- [ ] **Step 3: Create package metadata and entry stub**

Create `pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "game-agent"
version = "0.1.0"
description = "M1 vertical slice for a three-agent drone game research workflow"
requires-python = ">=3.10"
dependencies = ["numpy>=1.24", "PyYAML>=6.0"]

[project.optional-dependencies]
dev = ["pytest>=7.4"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
```

Create `game_agent/__init__.py`:

```python
"""Game Agent M1 package."""

__version__ = "0.1.0"
```

Create `game_agent/__main__.py`:

```python
from game_agent.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
```

Create `game_agent/utils/__init__.py`:

```python
"""Shared utility helpers for Game Agent M1."""
```

Create `game_agent/utils/errors.py`:

```python
class GameAgentError(Exception):
    """Base exception for user-facing Game Agent errors."""


class ContractError(GameAgentError):
    """Raised when a generated package violates an interface contract."""


class InputError(GameAgentError):
    """Raised when user input cannot be compiled safely."""
```

- [ ] **Step 4: Create filesystem and manifest helpers**

Create `game_agent/utils/fs.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml


def ensure_empty_output_dir(path: Path) -> None:
    path = path.resolve()
    if path.exists() and any(path.iterdir()):
        raise FileExistsError(f"Refusing to overwrite non-empty directory: {path}")
    path.mkdir(parents=True, exist_ok=True)


def read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"YAML root must be a mapping: {path}")
    return data


def write_yaml(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(data, handle, sort_keys=False, allow_unicode=True)


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return data


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False, sort_keys=True)
        handle.write("\n")
```

Create `game_agent/utils/manifest.py`:

```python
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def build_manifest(root: Path, package_type: str, package_id: str) -> dict[str, Any]:
    root = root.resolve()
    digest = hashlib.sha256()
    files: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name == "manifest.json" or "__pycache__" in path.parts:
            continue
        rel = path.relative_to(root).as_posix()
        files.append(rel)
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return {
        "schema_version": "1.0",
        "package_type": package_type,
        "package_id": package_id,
        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "files": files,
        "freeze_hash": digest.hexdigest(),
    }
```

- [ ] **Step 5: Run utility tests**

Run: `python -m pytest tests/test_utils.py -v`

Expected: PASS.

---

### Task 2: Contracts and lightweight environment

**Files:**
- Create: `contracts/scenario_schema.yaml`
- Create: `contracts/policy_protocol.py`
- Create: `game_agent/envs/__init__.py`
- Create: `game_agent/envs/drone_ring_game/__init__.py`
- Create: `game_agent/envs/drone_ring_game/env.py`
- Test: `tests/test_contracts.py`
- Test: `tests/test_drone_ring_env.py`

- [ ] **Step 1: Write failing contract and environment tests**

Create `tests/test_contracts.py`:

```python
from pathlib import Path

import yaml

from contracts.policy_protocol import Policy


def test_scenario_schema_declares_required_top_level_fields() -> None:
    data = yaml.safe_load(Path("contracts/scenario_schema.yaml").read_text(encoding="utf-8"))
    assert {"task_id", "task_family", "reward_structure", "evaluation_metrics"}.issubset(set(data["required"]))


def test_policy_protocol_defines_required_methods() -> None:
    for method in {"reset", "act", "load", "get_config_schema"}:
        assert method in Policy.__abstractmethods__
```

Create `tests/test_drone_ring_env.py`:

```python
import numpy as np

from game_agent.envs.drone_ring_game.env import DroneRingEnv


def test_reset_is_deterministic_for_same_seed() -> None:
    env = DroneRingEnv({"ring_count": 2, "max_steps": 50})
    obs_a, info_a = env.reset(seed=7)
    obs_b, info_b = env.reset(seed=7)
    assert set(obs_a) == {"red_0", "blue_0"}
    assert np.allclose(obs_a["red_0"], obs_b["red_0"])
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_contracts.py tests/test_drone_ring_env.py -v`

Expected: FAIL because contracts and env files are absent.

- [ ] **Step 3: Add contracts**

Create `contracts/scenario_schema.yaml`:

```yaml
schema_version: "1.0"
type: object
required:
  - schema_version
  - task_id
  - task_family
  - formalism
  - agents
  - observation_space
  - action_space
  - reward_structure
  - evaluation_metrics
  - termination_conditions
  - splits
properties:
  task_family:
    enum: [drone_ring_game]
  formalism:
    enum: [MDP, MarkovGame, POSG, Dec-POMDP]
```

Create `contracts/policy_protocol.py`:

```python
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import numpy as np


class Policy(ABC):
    """All generated policies must implement this protocol."""

    @abstractmethod
    def reset(self, seed: int) -> None:
        """Reset deterministic internal state."""

    @abstractmethod
    def act(self, obs: dict[str, np.ndarray], agent_id: str, info: dict[str, Any] | None = None) -> np.ndarray:
        """Return one bounded action for one agent."""

    @abstractmethod
    def load(self, checkpoint_path: str) -> None:
        """Load policy parameters."""

    @abstractmethod
    def get_config_schema(self) -> dict[str, Any]:
        """Return fields AutoResearch may vary."""

    def supports_training(self) -> bool:
        return True

    def get_diagnostics(self) -> dict[str, Any]:
        return {}
```

- [ ] **Step 4: Add lightweight environment**

Create `game_agent/envs/__init__.py`:

```python
"""Environment implementations used by generated scenarios."""
```

Create `game_agent/envs/drone_ring_game/__init__.py`:

```python
from game_agent.envs.drone_ring_game.env import DroneRingEnv

__all__ = ["DroneRingEnv"]
```

Create `game_agent/envs/drone_ring_game/env.py` with this behavior:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass
class AgentState:
    position: np.ndarray
    velocity: np.ndarray


class DroneRingEnv:
    observation_shape = (12,)
    action_shape = (4,)

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        config = config or {}
        self.ring_count = int(config.get("ring_count", 2))
        self.max_steps = int(config.get("max_steps", 200))
        self.bounds = float(config.get("bounds", 10.0))
        self.dt = float(config.get("dt", 0.2))
        self.collision_radius = float(config.get("collision_radius", 0.35))
        self.ring_radius = float(config.get("ring_radius", 0.5))
        self.action_low = np.array([-2.0, -2.0, -1.0, -1.0], dtype=np.float32)
        self.action_high = np.array([2.0, 2.0, 1.0, 1.0], dtype=np.float32)
        self.agents = ["red_0", "blue_0"]
        self.rings = [np.array([2.5 + i * 2.0, 0.0], dtype=np.float32) for i in range(max(1, self.ring_count))]
        self.step_count = 0
        self.current_ring = 0
        self.states: dict[str, AgentState] = {}

    def reset(self, seed: int | None = None) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
        rng = np.random.default_rng(seed)
        self.step_count = 0
        self.current_ring = 0
        self.states = {
            "red_0": AgentState(np.array([0.0, float(rng.uniform(-0.2, 0.2))], dtype=np.float32), np.zeros(2, dtype=np.float32)),
            "blue_0": AgentState(np.array([-1.5, float(rng.uniform(1.4, 1.8))], dtype=np.float32), np.zeros(2, dtype=np.float32)),
        }
        return self._obs(), {"seed": seed, "current_ring": self.current_ring}

    def step(self, actions: dict[str, np.ndarray]) -> tuple[dict[str, np.ndarray], dict[str, float], dict[str, bool], dict[str, bool], dict[str, Any]]:
        self.step_count += 1
        for agent_id in self.agents:
            raw_action = np.asarray(actions.get(agent_id, np.zeros(4)), dtype=np.float32)
            clipped = np.clip(raw_action, self.action_low, self.action_high)
            self.states[agent_id].velocity = clipped[:2]
            self.states[agent_id].position = self.states[agent_id].position + clipped[:2] * self.dt

        red = self.states["red_0"].position
        blue = self.states["blue_0"].position
        if self.current_ring < len(self.rings) and float(np.linalg.norm(red - self.rings[self.current_ring])) <= self.ring_radius:
            self.current_ring += 1
        success = self.current_ring >= len(self.rings)
        collision = float(np.linalg.norm(red - blue)) <= self.collision_radius
        out_of_bounds = any(float(np.max(np.abs(state.position))) > self.bounds for state in self.states.values())
        timeout = self.step_count >= self.max_steps
        done = success or collision or out_of_bounds
        truncated_flag = timeout and not done
        info = {"current_ring": self.current_ring, "metrics": {"success": success, "collision": collision, "out_of_bounds": out_of_bounds, "episode_length": self.step_count}}
        return self._obs(), {"red_0": float(success), "blue_0": float(collision)}, {agent: done for agent in self.agents}, {agent: truncated_flag for agent in self.agents}, info

    def _obs(self) -> dict[str, np.ndarray]:
        return {"red_0": self._one_obs("red_0", "blue_0"), "blue_0": self._one_obs("blue_0", "red_0")}

    def _one_obs(self, self_id: str, other_id: str) -> np.ndarray:
        self_state = self.states[self_id]
        other_state = self.states[other_id]
        rel_pos = other_state.position - self_state.position
        rel_vel = other_state.velocity - self_state.velocity
        ring = self.rings[min(self.current_ring, len(self.rings) - 1)]
        rel_ring = ring - self_state.position
        return np.array([self_state.position[0], self_state.position[1], 0.0, self_state.velocity[0], self_state.velocity[1], 0.0, rel_pos[0], rel_pos[1], 0.0, rel_vel[0] + rel_ring[0] * 0.1, rel_vel[1] + rel_ring[1] * 0.1, 0.0], dtype=np.float32)
```

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/test_contracts.py tests/test_drone_ring_env.py -v`

Expected: PASS.

---

### Task 3: Scenario Compiler

**Files:**
- Create: `game_agent/scenario_compiler/__init__.py`
- Create: `game_agent/scenario_compiler/templates.py`
- Create: `game_agent/scenario_compiler/compiler.py`
- Test: `tests/test_scenario_compiler.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_scenario_compiler.py`:

```python
from pathlib import Path

from game_agent.scenario_compiler import ScenarioCompiler
from game_agent.utils.fs import read_yaml


def test_compile_creates_scenario_package(tmp_path: Path) -> None:
    scenario_dir = ScenarioCompiler(project_root=tmp_path).compile(
        task_text="红方无人机穿过两个圆环，蓝方追击拦截，通信延迟 2 步，超时 80 步",
        task_id="drone_ring_001",
    )
    assert (scenario_dir / "task_spec.yaml").exists()
    assert (scenario_dir / "model.md").exists()
    assert (scenario_dir / "env.py").exists()
    assert (scenario_dir / "assumptions.md").exists()
    assert (scenario_dir / "manifest.json").exists()
    spec = read_yaml(scenario_dir / "task_spec.yaml")
    assert spec["task_family"] == "drone_ring_game"
    assert spec["env_config"]["ring_count"] == 2
    assert spec["env_config"]["max_steps"] == 80
    assert spec["communication"]["mode"] == "delayed"


def test_compile_records_assumptions_for_missing_values(tmp_path: Path) -> None:
    scenario_dir = ScenarioCompiler(project_root=tmp_path).compile("红蓝无人机追逃穿环", "drone_ring_002")
    assumptions = (scenario_dir / "assumptions.md").read_text(encoding="utf-8")
    assert "ring_count" in assumptions
    assert "max_steps" in assumptions
    assert "communication.mode" in assumptions
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_scenario_compiler.py -v`

Expected: FAIL because `ScenarioCompiler` is not defined.

- [ ] **Step 3: Implement Scenario Compiler**

Implementation requirements:

- `ScenarioCompiler(project_root).compile(task_text, task_id) -> Path`
- Write only to `project_root/scenarios/<task_id>/`.
- Use `ensure_empty_output_dir`.
- Generate `task_spec.yaml`, `env_config.yaml`, `env.py`, `model.md`, `assumptions.md`, `tests/test_reset_deterministic.py`, `tests/test_obs_action_shape.py`, `manifest.json`.
- Parse Chinese numerals `一/二/两/三/四/五` and Arabic numerals for ring count.
- Parse timeout from text such as `超时 80 步`.
- Parse communication mode: `延迟` -> `delayed`, `丢包` -> `lossy`, missing -> `perfect` plus assumption.
- Use `formalism: POSG` when task text contains `对抗`、`追击`、`拦截`、`红蓝`、`局部`; otherwise `MarkovGame`.
- Include `reward_structure` and `evaluation_metrics` as separate fields.

Create `game_agent/scenario_compiler/__init__.py`:

```python
from game_agent.scenario_compiler.compiler import ScenarioCompiler

__all__ = ["ScenarioCompiler"]
```

Create `game_agent/scenario_compiler/templates.py` with generated file helpers:

```python
SCENARIO_ENV_PY = """from game_agent.envs.drone_ring_game.env import DroneRingEnv


def make_env(config=None):
    return DroneRingEnv(config)
"""


def model_md(task_id: str, formalism: str) -> str:
    return f"# Scenario Model: {task_id}\n\n## Formalism\n\n{formalism}\n\n## Summary\n\nSimplified red-blue drone ring game for M1 contract testing.\n"


def assumptions_md(assumptions: list[str]) -> str:
    lines = ["# Assumptions", ""]
    lines.extend(f"- {item}" for item in assumptions)
    if not assumptions:
        lines.append("- No missing task parameters were filled by defaults.")
    return "\n".join(lines) + "\n"
```

Create `game_agent/scenario_compiler/compiler.py` with the parser and package writer. Keep helpers private (`_parse`, `_build_spec`, `_extract_count`, `_extract_number_before_unit`, `_extract_number_near`) and keep generated spec fields exactly as listed in the approved design.

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_scenario_compiler.py -v`

Expected: PASS.

---

### Task 4: Policy Designer

**Files:**
- Create: `game_agent/policy_designer/__init__.py`
- Create: `game_agent/policy_designer/templates.py`
- Create: `game_agent/policy_designer/designer.py`
- Test: `tests/test_policy_designer.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_policy_designer.py`:

```python
from pathlib import Path

from game_agent.policy_designer import PolicyDesigner
from game_agent.scenario_compiler import ScenarioCompiler
from game_agent.utils.fs import read_yaml


def test_build_policy_package_from_scenario(tmp_path: Path) -> None:
    scenario = ScenarioCompiler(tmp_path).compile("红方穿过两个圆环，蓝方追击拦截", "drone_ring_001")
    policy_dir = PolicyDesigner(tmp_path).build(scenario, "rule_ring_nav_v1")
    for name in ["policy.py", "train.py", "infer.py", "default_config.yaml", "search_space.yaml", "algorithm_card.md", "requirements.txt", "manifest.json"]:
        assert (policy_dir / name).exists()
    assert read_yaml(policy_dir / "default_config.yaml")["policy_type"] == "rule_ring_navigation"


def test_policy_search_space_contains_autoresearch_fields(tmp_path: Path) -> None:
    scenario = ScenarioCompiler(tmp_path).compile("红蓝无人机穿环", "drone_ring_002")
    policy_dir = PolicyDesigner(tmp_path).build(scenario, "rule_ring_nav_v2")
    search_space = read_yaml(policy_dir / "search_space.yaml")
    assert "speed_scale" in search_space["parameters"]
    assert "intercept_gain" in search_space["parameters"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_policy_designer.py -v`

Expected: FAIL because `PolicyDesigner` is not defined.

- [ ] **Step 3: Implement Policy Designer**

Implementation requirements:

- `PolicyDesigner(project_root).build(scenario_dir, policy_id) -> Path`
- Write only to `project_root/policies/<policy_id>/`.
- Generate `policy.py`, `train.py`, `infer.py`, `default_config.yaml`, `search_space.yaml`, `algorithm_card.md`, `requirements.txt`, generated tests, `metadata.json`, `manifest.json`.
- `policy.py` must define `RuleRingNavigationPolicy` implementing `contracts.policy_protocol.Policy` and expose `PolicyClass = RuleRingNavigationPolicy`.
- `act()` uses obs indices `[9:11]` for red ring direction and `[6:8]` for blue intercept direction, then clips to action bounds.
- `get_config_schema()` includes `speed_scale`, `intercept_gain`, `safety_margin`.
- `train.py` is a deterministic no-op trainer that writes `checkpoint.json` and `training_log.json`.
- `infer.py` calls `game_agent.autoresearch.runner.evaluate_policy_dir`.

Create `game_agent/policy_designer/__init__.py`:

```python
from game_agent.policy_designer.designer import PolicyDesigner

__all__ = ["PolicyDesigner"]
```

Create `default_config.yaml` data through `write_yaml`:

```python
{"policy_type": "rule_ring_navigation", "speed_scale": 1.0, "intercept_gain": 1.0, "safety_margin": 0.2}
```

Create `search_space.yaml` data through `write_yaml`:

```python
{
    "parameters": {
        "speed_scale": {"values": [0.8, 1.0, 1.2]},
        "intercept_gain": {"values": [0.8, 1.0, 1.2]},
        "safety_margin": {"values": [0.1, 0.2]},
    },
    "budget": {"max_trials": 18, "seeds_per_trial": 3},
}
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_policy_designer.py -v`

Expected: PASS.

---

### Task 5: AutoResearch deterministic sweep

**Files:**
- Create: `game_agent/autoresearch/__init__.py`
- Create: `game_agent/autoresearch/metrics.py`
- Create: `game_agent/autoresearch/runner.py`
- Test: `tests/test_autoresearch.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_autoresearch.py`:

```python
from pathlib import Path

from game_agent.autoresearch import AutoResearchRunner
from game_agent.policy_designer import PolicyDesigner
from game_agent.scenario_compiler import ScenarioCompiler
from game_agent.utils.fs import read_yaml


def test_autoresearch_generates_experiment_package(tmp_path: Path) -> None:
    scenario = ScenarioCompiler(tmp_path).compile("红方穿过两个圆环，蓝方追击拦截，超时 60 步", "drone_ring_001")
    policy = PolicyDesigner(tmp_path).build(scenario, "rule_ring_nav_v1")
    exp_dir = AutoResearchRunner(tmp_path).run(scenario, policy, "exp_drone_ring_001")
    for name in ["leaderboard.csv", "best_config.yaml", "report.md", "manifest.json"]:
        assert (exp_dir / name).exists()
    assert "speed_scale" in read_yaml(exp_dir / "best_config.yaml")


def test_leaderboard_contains_primary_metric(tmp_path: Path) -> None:
    scenario = ScenarioCompiler(tmp_path).compile("红蓝无人机穿环", "drone_ring_002")
    policy = PolicyDesigner(tmp_path).build(scenario, "rule_ring_nav_v2")
    exp_dir = AutoResearchRunner(tmp_path).run(scenario, policy, "exp_drone_ring_002")
    text = (exp_dir / "leaderboard.csv").read_text(encoding="utf-8")
    assert "success_rate" in text
    assert "collision_rate" in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_autoresearch.py -v`

Expected: FAIL because `AutoResearchRunner` is absent.

- [ ] **Step 3: Implement AutoResearch**

Implementation requirements:

- `AutoResearchRunner(project_root).run(scenario_dir, policy_dir, exp_id) -> Path`
- Write only to `project_root/experiments/<exp_id>/`.
- Read `task_spec.yaml`, `default_config.yaml`, `search_space.yaml`.
- Expand parameter grid from each `parameters.<name>.values`.
- Limit trial count using `budget.max_trials`.
- Use `splits.val_seeds` and `budget.seeds_per_trial`.
- For each trial write `trials/trial_0001/config.yaml`, `metrics.json`, and `log.json`.
- Generate `leaderboard.csv`, `best_config.yaml`, experiment `report.md`, and `manifest.json`.
- Rank feasible trials first using hard constraints, then primary metric, then shorter episode length.
- Export `evaluate_policy_dir(policy_dir, scenario_dir, config_path, seeds)` for generated `infer.py`.

Create `game_agent/autoresearch/__init__.py`:

```python
from game_agent.autoresearch.runner import AutoResearchRunner

__all__ = ["AutoResearchRunner"]
```

Create `game_agent/autoresearch/metrics.py`:

```python
from __future__ import annotations

from typing import Any


def satisfies_hard_constraints(metrics: dict[str, float], evaluation_metrics: dict[str, Any]) -> bool:
    for constraint in evaluation_metrics.get("hard_constraints", []):
        name = constraint["name"]
        if "max" in constraint and metrics.get(name, 0.0) > float(constraint["max"]):
            return False
        if "min" in constraint and metrics.get(name, 0.0) < float(constraint["min"]):
            return False
    return True


def ranking_key(metrics: dict[str, float], evaluation_metrics: dict[str, Any]) -> tuple[int, float, float]:
    feasible = 1 if satisfies_hard_constraints(metrics, evaluation_metrics) else 0
    primary = evaluation_metrics["primary"]
    value = float(metrics.get(primary["name"], 0.0))
    signed_value = value if primary.get("direction") == "maximize" else -value
    episode_penalty = -float(metrics.get("avg_episode_length", 0.0))
    return feasible, signed_value, episode_penalty
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_autoresearch.py -v`

Expected: PASS.

---

### Task 6: Validation hooks

**Files:**
- Create: `hooks/post_scenario_compile.py`
- Create: `hooks/post_policy_submit.py`
- Create: `hooks/post_experiment_run.py`
- Test: `tests/test_hooks.py`

- [ ] **Step 1: Write failing hook tests**

Create `tests/test_hooks.py`:

```python
import subprocess
import sys
from pathlib import Path

from game_agent.autoresearch import AutoResearchRunner
from game_agent.policy_designer import PolicyDesigner
from game_agent.scenario_compiler import ScenarioCompiler


def test_hooks_accept_valid_generated_packages(tmp_path: Path) -> None:
    scenario = ScenarioCompiler(tmp_path).compile("红方穿过两个圆环，蓝方追击拦截", "drone_ring_001")
    policy = PolicyDesigner(tmp_path).build(scenario, "rule_ring_nav_v1")
    exp = AutoResearchRunner(tmp_path).run(scenario, policy, "exp_drone_ring_001")
    commands = [
        [sys.executable, "hooks/post_scenario_compile.py", "--scenario", str(scenario)],
        [sys.executable, "hooks/post_policy_submit.py", "--policy", str(policy)],
        [sys.executable, "hooks/post_experiment_run.py", "--exp", str(exp)],
    ]
    for command in commands:
        result = subprocess.run(command, text=True, capture_output=True, check=False)
        assert result.returncode == 0, result.stderr
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_hooks.py -v`

Expected: FAIL because hook scripts are absent.

- [ ] **Step 3: Implement hooks**

`hooks/post_scenario_compile.py` must:

- require `--scenario`;
- verify required files: `task_spec.yaml`, `model.md`, `env_config.yaml`, `env.py`, `assumptions.md`, `manifest.json`;
- verify required `task_spec.yaml` fields from the design spec;
- fail if `evaluation_metrics.primary.name` directly equals a reward component name;
- print `scenario validation passed` and exit 0 on success.

`hooks/post_policy_submit.py` must:

- require `--policy`;
- verify required files: `policy.py`, `train.py`, `infer.py`, `default_config.yaml`, `search_space.yaml`, `algorithm_card.md`, `requirements.txt`, `manifest.json`;
- import `PolicyClass` from generated `policy.py`;
- verify `issubclass(PolicyClass, contracts.policy_protocol.Policy)`;
- instantiate policy with dummy action bounds and check every search-space field appears in `get_config_schema()`;
- print `policy validation passed` and exit 0 on success.

`hooks/post_experiment_run.py` must:

- require `--exp`;
- verify required files: `leaderboard.csv`, `best_config.yaml`, `report.md`, `manifest.json`;
- verify `trials/` exists;
- verify every trial directory contains `config.yaml`, `metrics.json`, `log.json`;
- verify `leaderboard.csv` has at least one trial row;
- print `experiment validation passed` and exit 0 on success.

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_hooks.py -v`

Expected: PASS.

---

### Task 7: CLI orchestration and root docs

**Files:**
- Create: `game_agent/cli.py`
- Test: `tests/test_cli_smoke.py`

- [ ] **Step 1: Write failing CLI smoke test**

Create `tests/test_cli_smoke.py`:

```python
import subprocess
import sys
from pathlib import Path


def test_cli_run_generates_full_m1_outputs(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable, "-m", "game_agent", "run",
            "--project-root", str(tmp_path),
            "--task", "红方无人机穿过两个圆环，蓝方追击拦截，通信延迟 2 步，超时 60 步",
            "--task-id", "drone_ring_001",
            "--policy-id", "rule_ring_nav_v1",
            "--exp-id", "exp_drone_ring_001",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "scenarios" / "drone_ring_001" / "task_spec.yaml").exists()
    assert (tmp_path / "policies" / "rule_ring_nav_v1" / "policy.py").exists()
    assert (tmp_path / "experiments" / "exp_drone_ring_001" / "leaderboard.csv").exists()
    assert (tmp_path / "report.md").exists()
    assert (tmp_path / "task.md").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cli_smoke.py -v`

Expected: FAIL because `game_agent.cli` is absent.

- [ ] **Step 3: Implement CLI**

Implementation requirements:

- Use `argparse`.
- Commands:
  - `run --task --task-id --policy-id --exp-id --project-root`
  - `compile-scenario --task --task-id --project-root`
  - `build-policy --scenario --policy-id --project-root`
  - `run-experiment --scenario --policy --exp-id --project-root`
- `run` executes Scenario Compiler, scenario hook, Policy Designer, policy hook, AutoResearch, experiment hook, then writes root `report.md` and `task.md`.
- `report.md` states M1 supports simplified `drone_ring_game` red-blue ring traversal, pursuit, and interception tasks, and is not a general drone simulator or full RL framework.
- `task.md` lists remaining work for environment fidelity, parser expansion, real policies, AutoResearch upgrades, validation, and multi-task-family support.
- On exceptions, print `error: <message>` to stderr and return exit code 1.

- [ ] **Step 4: Run CLI smoke test**

Run: `python -m pytest tests/test_cli_smoke.py -v`

Expected: PASS.

---

### Task 8: Agent and skill project content

**Files:**
- Create: `agents/scenario_compiler/AGENTS.md`
- Create: `agents/scenario_compiler/prompt.md`
- Create: `agents/scenario_compiler/orchestrator.py`
- Create: `agents/policy_designer/AGENTS.md`
- Create: `agents/policy_designer/prompt.md`
- Create: `agents/policy_designer/orchestrator.py`
- Create: `agents/experiment_autoresearch/AGENTS.md`
- Create: `agents/experiment_autoresearch/prompt.md`
- Create: `agents/experiment_autoresearch/orchestrator.py`
- Create: `.agents/skills/scenario-spec-compiler/SKILL.md`
- Create: `.agents/skills/policy-interface-builder/SKILL.md`
- Create: `.agents/skills/autoresearch-loop/SKILL.md`
- Test: `tests/test_agent_project_content.py`

- [ ] **Step 1: Write failing content tests**

Create `tests/test_agent_project_content.py`:

```python
from pathlib import Path


def test_three_agent_directories_have_required_files() -> None:
    for agent in ["scenario_compiler", "policy_designer", "experiment_autoresearch"]:
        root = Path("agents") / agent
        assert (root / "AGENTS.md").exists()
        assert (root / "prompt.md").exists()
        assert (root / "orchestrator.py").exists()


def test_core_skills_exist() -> None:
    for skill in ["scenario-spec-compiler", "policy-interface-builder", "autoresearch-loop"]:
        assert (Path(".agents") / "skills" / skill / "SKILL.md").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_agent_project_content.py -v`

Expected: FAIL because agent and skill files are absent.

- [ ] **Step 3: Create three agent directories**

Each `AGENTS.md` must include Mission, Allowed Edits, Forbidden Edits, Required Validation Command, and Done Definition.

Scenario Compiler:

- Mission: convert semi-free natural-language drone tasks into `scenarios/<task_id>/`.
- Allowed edits: `scenarios/<task_id>/`.
- Forbidden edits: `policies/`, `experiments/`, `contracts/`, `hooks/`.
- Validation: `python hooks/post_scenario_compile.py --scenario scenarios/<task_id>`.

Policy Designer:

- Mission: convert a validated scenario into `policies/<policy_id>/`.
- Allowed edits: `policies/<policy_id>/`.
- Forbidden edits: `scenarios/`, `experiments/`, `contracts/`, `hooks/`.
- Validation: `python hooks/post_policy_submit.py --policy policies/<policy_id>`.

Experiment AutoResearch:

- Mission: run deterministic sweeps for frozen scenario/policy inputs.
- Allowed edits: `experiments/<exp_id>/`.
- Forbidden edits: `scenarios/`, `policies/`, `contracts/`, `hooks/`.
- Validation: `python hooks/post_experiment_run.py --exp experiments/<exp_id>`.

Each `orchestrator.py` should expose one concrete function: Scenario Compiler uses `run(task_text: str, task_id: str, project_root: str = ".") -> Path`; Policy Designer uses `run(scenario_dir: str, policy_id: str, project_root: str = ".") -> Path`; AutoResearch uses `run(scenario_dir: str, policy_dir: str, exp_id: str, project_root: str = ".") -> Path`.

- [ ] **Step 4: Create three skill files**

`scenario-spec-compiler/SKILL.md` must describe natural-language extraction, assumptions, ScenarioPackage outputs, and the rule that every default goes to `assumptions.md`.

`policy-interface-builder/SKILL.md` must describe policy package generation, action bounds, train/infer entrypoints, and the rule that actions are clipped.

`autoresearch-loop/SKILL.md` must describe deterministic sweep, multi-seed metrics, leaderboard, best config, and the rule that promotion uses `evaluation_metrics`, not reward components.

- [ ] **Step 5: Run content tests**

Run: `python -m pytest tests/test_agent_project_content.py -v`

Expected: PASS.

---

### Task 9: Full verification pass

**Files:**
- Modify only files needed to fix failing tests from Tasks 1-8.

- [ ] **Step 1: Run complete test suite**

Run: `python -m pytest -v`

Expected: all tests PASS.

- [ ] **Step 2: Run manual CLI smoke in disposable output**

Run:

```powershell
$repo = Resolve-Path ".";
$demo = Join-Path $repo.Path ".tmp-m1-demo";
if (Test-Path -LiteralPath $demo) { Remove-Item -LiteralPath $demo -Recurse -Force }
python -m game_agent run --project-root $demo --task "红方无人机穿过两个圆环，蓝方追击拦截，通信延迟 2 步，超时 60 步" --task-id drone_ring_001 --policy-id rule_ring_nav_v1 --exp-id exp_drone_ring_001
```

Expected: exit code 0 and printed paths for scenario, policy, and experiment.

- [ ] **Step 3: Inspect generated root docs**

Run:

```powershell
Get-Content -LiteralPath ".tmp-m1-demo/report.md" -Encoding UTF8
Get-Content -LiteralPath ".tmp-m1-demo/task.md" -Encoding UTF8
```

Expected:

- `report.md` clearly states the current supported task family is simplified `drone_ring_game`.
- `report.md` states M1 is not a general drone simulator and not a full RL framework.
- `task.md` contains remaining work for environment, scenario compiler, policy designer, AutoResearch, validation, and task family expansion.

- [ ] **Step 4: Clean disposable demo output**

This is a deletion step. Confirm the resolved path is exactly the disposable demo directory before executing:

```powershell
$repo = Resolve-Path ".";
$demo = Resolve-Path ".tmp-m1-demo";
if ($demo.Path -eq (Join-Path $repo.Path ".tmp-m1-demo")) {
  Remove-Item -LiteralPath $demo.Path -Recurse -Force
}
```

Expected: only `.tmp-m1-demo` is removed.

## Self-Review

- Spec coverage: The plan implements the approved M1 architecture, CLI entry, contracts, hooks, ScenarioPackage, PolicyPackage, ExperimentPackage, root `report.md`, and root `task.md`.
- Scope control: The plan excludes PettingZoo, Gymnasium, RL training frameworks, MCP services, GPU orchestration, high-fidelity dynamics, hidden evaluator isolation, and git operations.
- Type consistency: The plan consistently uses `ScenarioCompiler.compile(task_text, task_id)`, `PolicyDesigner.build(scenario_dir, policy_id)`, and `AutoResearchRunner.run(scenario_dir, policy_dir, exp_id)`.
- Verification: Every implementation layer has a test-first task and an exact `pytest` command.
