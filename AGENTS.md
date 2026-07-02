# Repository Guidelines

## Project Structure & Module Organization

This is a Python 3.10+ project for generating and evaluating drone game research workflows. Core package code lives in `src/game_agent/`, with shared interfaces and schemas in `src/contracts/` and validation hooks in `src/hooks/`. Top-level `tests/` contains repository-level pytest coverage. Generated or reference artifacts are organized by workflow stage: `game/<game-id>/` for plans and logs, `scenarios/<task_id>/` for compiled environments, `policies/<policy_id>/` for train/infer policy packages, and `experiments/<exp_id>/` for sweep outputs, reports, and figures. Keep reusable implementation in `src/`; treat scenario, policy, and experiment folders as bounded artifacts.

## Build, Test, and Development Commands

- `python -m venv .venv` then `.venv\Scripts\Activate.ps1`: create and activate a local virtual environment on Windows.
- `python -m pip install -e ".[dev]"`: install the package in editable mode with pytest.
- `python -m pytest -q`: run the full test suite configured by `pyproject.toml`.
- `python -m pytest tests/test_scenario_compiler.py -q`: run a focused test module.
- `python -m game_agent --help`: inspect CLI entry points such as scenario compilation, policy building, and experiment execution.

## Coding Style & Naming Conventions

Use idiomatic Python with 4-space indentation, type hints where they clarify public contracts, and `snake_case` for modules, functions, variables, scenario IDs, and policy IDs. Prefer small functions with single responsibilities and explicit data structures over implicit string parsing. Keep YAML/JSON manifests deterministic and human-readable. Follow existing package boundaries: environment dynamics belong under `envs/`, workflow orchestration under compiler/designer/autoresearch modules, and filesystem helpers under `utils/`.

## Testing Guidelines

Pytest is the test framework. Name tests `test_*.py` and place shared project tests in `tests/`; artifact-specific tests may live under each generated `scenarios/*/tests/` or `policies/*/tests/`. Add or update tests when changing contracts, CLI behavior, deterministic rollouts, action bounds, or manifest generation. Prefer focused regression tests over broad end-to-end sweeps unless the workflow surface changes.

## Commit & Pull Request Guidelines

Recent history uses concise messages, including Conventional Commit-style prefixes such as `feat:`. Use short, imperative summaries, for example `fix: validate policy action bounds`. Pull requests should describe the changed workflow stage, list verification commands run, and call out generated artifacts or large experiment outputs. Link issues when available and include screenshots only for visualization changes.

## Security & Configuration Tips

Do not commit secrets, local virtual environments, or bulky transient outputs. Keep dependency changes in `pyproject.toml` minimal and justified. Generated experiment files should be reproducible from configs, seeds, and manifests.
