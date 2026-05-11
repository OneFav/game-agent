# Scenario Compiler Agent

## Mission
convert semi-free natural-language drone tasks into `scenarios/<task_id>/` packages that can be validated and consumed by downstream policy and experiment agents.

## Allowed Edits
- You may create or replace files only under `scenarios/<task_id>/` for the requested task id.
- Generated files should include the scenario specification, environment configuration, assumptions, model notes, package tests, and manifest produced by the project compiler.

## Forbidden Edits
- You must not edit `policies/`.
- You must not edit `experiments/`.
- You must not edit `contracts/`.
- You must not edit `hooks/`.
- You must not modify shared source code unless a maintainer explicitly expands the task scope.

## Required Validation Command
Run this command before marking the scenario complete:

```bash
python hooks/post_scenario_compile.py --scenario scenarios/<task_id>
```

## Done Definition
- The scenario package exists at `scenarios/<task_id>/`.
- Every inferred default is documented in `assumptions.md`.
- The package manifest and generated tests are present.
- The required validation command succeeds without errors.
