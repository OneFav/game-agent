# Wide Slalom 2v2 Swarm Rule Policy

## Family

Rule-based team-aware escort/intercept policy.

## Compatible Scenarios

Designed for `wide_slalom_2v2_001` in the `swarm_combat` family. The scenario wrapper exposes normalized `(4,)` actions while forwarding the first three dimensions to the shared 3D `SwarmCombatEnv`.

## Assumptions

The runtime `info` payload includes a `raw_env` handle so the policy can reuse the shared `SafeRulePolicy` batch-control logic on the real 3D environment. If `raw_env` is unavailable, the policy falls back to a lightweight observation-only heuristic for local hook tests.

## Input/Output

Input is one per-agent observation plus per-agent `info`. Output is a `(4,)` float32 action in `[-1, 1]`; dimensions `0:3` are normalized XYZ acceleration and dimension `3` is reserved.

## Training Method

No gradient training is required. `train.py` only materializes a checkpoint JSON with the selected configuration so AutoResearch can replay deterministic trials.

## Safety Mechanism

The shared `SafeRulePolicy` handles lookahead collision checks, boundary repulsion, gate-frame avoidance, and emergency braking. The local wrapper normalizes every command by the drone-specific acceleration limit and clips the final action to the declared bounds.

## Known Limitations

`team_score` is evaluated from the red team perspective. Blue-team score is tracked as a secondary metric rather than the primary ranking key. The fallback observation-only mode is intentionally simple and is not meant to match the full shared-environment controller.

## Expected Failure Modes

Large `desired_speed` with too-small `risk_margin` can still produce late gate-frame collisions. Overly conservative `risk_margin` can keep both teams safe but reduce gate throughput.

## Computational Requirements

CPU-only. One rollout over three seeds and 600 steps is lightweight enough for deterministic local sweep execution.
