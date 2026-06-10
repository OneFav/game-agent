---
name: scenario-spec-compiler
description: Compile semi-free drone task text into validated ScenarioPackage directories.
---

# Scenario Spec Compiler

Use this skill when converting natural-language drone task descriptions into a concrete scenario package. The workflow performs natural-language extraction for task family, agent roles, ring count, communication constraints, timeout, formalism, action space, observation space, termination, and evaluation metrics.

## Required Outputs

Produce one ScenarioPackage under `scenarios/<task_id>/` with at least:

- `task_spec.yaml` as the canonical scenario contract.
- `env_config.yaml` with environment parameters derived from the spec.
- `env.py`, `model.md`, generated package tests, and `manifest.json`.
- `assumptions.md` recording all assumptions.

## Assumptions Rule

every default must be written to `assumptions.md`. If the source text omits a value, choose the project default only when required for a runnable package, then document the field name, chosen value, and why the default was necessary. Do not hide defaults in generated YAML without a matching assumption entry.

## Validation

## Codex Subagent

This skill is executed as the **scenario_compiler** Codex subagent defined in `.codex/agents/scenario_compiler.toml`. The subagent's `developer_instructions` contain the complete work boundary matrix (Allowed/Forbidden Edits), the Policy ABC calling convention, and all key constraints. All file-system operations are restricted to `scenarios/<task_id>/`.

## Validation

After generation, run `python src/hooks/post_scenario_compile.py --scenario scenarios/<task_id>`. The skill is complete only when the ScenarioPackage exists, assumptions are auditable, and validation passes.
