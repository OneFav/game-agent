---
name: autoresearch-loop
description: Run deterministic sweeps and promote configurations by evaluation metrics.
---

# AutoResearch Loop

Use this skill when evaluating a frozen scenario and policy package. The workflow runs a deterministic sweep over the policy search space, records multi-seed metrics for every trial, writes a leaderboard, and emits the best config for the top-ranked trial.

## Sweep Requirements

- Treat `scenarios/<task_id>/` and `policies/<policy_id>/` as immutable inputs.
- Use deterministic seeds from the scenario split or the project default.
- Store each trial config, metrics, and log under `experiments/<exp_id>/trials/`.
- Sort `leaderboard.csv` deterministically and write `best_config.yaml` from the first ranked row.

## Promotion Rule

Promotion must use `evaluation_metrics` from the scenario specification rather than reward components. Reward components can explain environment incentives, but they are not the source of truth for ranking, hard constraints, or best config selection.

## Validation

## Codex Subagent

This skill is executed as the **experiment_autoresearch** Codex subagent defined in `.codex/agents/experiment_autoresearch.toml`. The subagent's `developer_instructions` contain the complete work boundary matrix (Allowed/Forbidden Edits), the anti-reward-hacking rules (4 gates), the promotion gate pipeline, and the deterministic sweep protocol. Strict ranking by `evaluation_metrics` (not reward components) + multi-seed verification + promotion gate are enforced.

## Validation

After generation, run `python src/hooks/post_experiment_run.py --exp experiments/<exp_id>`. The loop is complete only when multi-seed metrics, leaderboard, best config, report, and manifest are present and validation passes.
