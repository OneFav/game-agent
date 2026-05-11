# Experiment AutoResearch Agent

## Mission
run deterministic sweeps for frozen scenario/policy inputs and write one reproducible experiment package under `experiments/<exp_id>/`.

## Allowed Edits
- You may create or replace files only under `experiments/<exp_id>/` for the requested experiment id.
- Generated files should include trial configs, per-trial metrics and logs, leaderboard, best config, report, and manifest.

## Forbidden Edits
- You must not edit `scenarios/`.
- You must not edit `policies/`.
- You must not edit `contracts/`.
- You must not edit `hooks/`.
- You must not modify frozen scenario or policy inputs while running sweeps.

## Required Validation Command
Run this command before marking the experiment complete:

```bash
python hooks/post_experiment_run.py --exp experiments/<exp_id>
```

## Done Definition
- The experiment package exists at `experiments/<exp_id>/`.
- All sweep trials are reproducible from recorded configs and seeds.
- `leaderboard.csv`, `best_config.yaml`, `report.md`, and `manifest.json` are present.
- The required validation command succeeds without errors.
