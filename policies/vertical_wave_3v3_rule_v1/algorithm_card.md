# vertical_wave_3v3_rule_v1 Algorithm Card

## Family

Rule-based safe swarm controller built on top of the repository's `SafeRulePolicy`.
The policy package exposes explicit `RedPolicy` and `BluePolicy` wrappers. `PolicyClass` only dispatches by team/role, clips actions, and provides the Policy ABC adapter.

## Compatible Scenarios

- 3D `swarm_combat`-style environments wrapped inside the current ScenarioPackage contract.
- Multi-racer / single-defender team layouts.
- Fixed observation dimension 94 and action dimension 3 for the `vertical_wave_3v3` scenario.

## Assumptions

- The scenario exposes a `base_env` compatible with `SwarmCombatEnv`.
- Team score is driven by effective gate passes.
- Safe braking and lane separation are more important than maximizing raw speed.
- Shared parameters use the `shared_` prefix because they describe geometry or safety mechanisms common to both teams. Team-specific speed, lane spacing, risk margin, and defender mode use `red_` / `blue_` prefixes.
- Utility source: `red_utility=avg_red_score`, `blue_utility=avg_blue_score` from evaluator score outputs.

## Input/Output

- Input: per-agent fixed-length observation for `act()`, or full environment state for `compute_actions(env)`.
- Output: bounded 3D acceleration action per agent.

## Training Method

No gradient training. `train.py` serializes the chosen config into a checkpoint for deterministic replay.

## Safety Mechanism

- All actions are clipped to scenario bounds.
- Native `SafeRulePolicy` performs lane assignment, lookahead collision checks, boundary protection and full-brake fallback.
- Red and blue sides own separate `SafeRulePolicy` instances so best-response rounds can tune one side while freezing the other.
- `act()` has a zero-action fallback on any exception.

## Known Limitations

- `act()` alone is only a contract-compatible fallback; best performance requires full-environment batch execution through `compute_actions(env)`.
- This controller is tuned for the repository's `vertical_wave` geometry and may generalize poorly to unrelated layouts without retuning.

## Expected Failure Modes

- Excessive desired speed may cause gate-frame contact.
- Too-small lane spacing may induce intra-team congestion.
- `defender_mode=intercept` can overcommit and expose racers if the map is narrow.

## Computational Requirements

CPU-only deterministic rollout. No training GPU is required.
