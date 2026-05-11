---
name: policy-interface-builder
description: Build policy packages with stable train/infer entrypoints and bounded actions.
---

# Policy Interface Builder

Use this skill when turning a validated scenario package into a policy package. The workflow covers policy package generation for `policies/<policy_id>/`, including the policy implementation, configuration files, search space, metadata, package tests, and manifest.

## Interface Requirements

A valid package exposes:

- `policy.py` with the policy class used by evaluation.
- `train.py` as the training or configuration-preparation entrypoint.
- `infer.py` as the inference/evaluation entrypoint.
- `default_config.yaml` and `search_space.yaml` for downstream sweeps.

## Action Safety

Read action bounds from the scenario contract and keep the policy output compatible with those bounds. Generated tests must cover action bounds, and runtime actions clipped behavior must be explicit: actions clipped to the scenario low/high limits before they are returned to the environment.

## Validation

After generation, run `python hooks/post_policy_submit.py --policy policies/<policy_id>`. The package is complete only when train/infer entrypoints exist, action clipping is documented and tested, and validation passes.
