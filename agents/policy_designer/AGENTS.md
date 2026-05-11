# Policy Designer Agent

## Mission
convert a validated scenario into `policies/<policy_id>/` packages with a stable training and inference interface for downstream evaluation.

## Allowed Edits
- You may create or replace files only under `policies/<policy_id>/` for the requested policy id.
- Generated files should include policy code, train/infer entrypoints, default configuration, search space, algorithm card, tests, metadata, and manifest.

## Forbidden Edits
- You must not edit `scenarios/`.
- You must not edit `experiments/`.
- You must not edit `contracts/`.
- You must not edit `hooks/`.
- You must not modify shared source code unless a maintainer explicitly expands the task scope.

## Required Validation Command
Run this command before marking the policy complete:

```bash
python hooks/post_policy_submit.py --policy policies/<policy_id>
```

## Done Definition
- The policy package exists at `policies/<policy_id>/`.
- The package exposes compatible train and inference entrypoints.
- Action bounds are enforced by generated tests and implementation.
- The required validation command succeeds without errors.
