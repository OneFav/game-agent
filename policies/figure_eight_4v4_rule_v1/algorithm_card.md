# figure_eight_4v4_rule_v1 Algorithm Card

## Family

Rule-based safe swarm controller built on top of `game_agent.policy_designer.reference_policies.safe_rule_policy.SafeRulePolicy`.

## Compatible Scenarios

- `scenarios/figure_eight_4v4_001/`
- 3D `swarm_combat` wrappers that expose `base_env` and per-agent acceleration bounds compatible with the 8-agent figure-eight contract

## Assumptions

- The scenario wrapper exposes `base_env` backed by `SwarmCombatEnv`.
- `gate_pass_reward = 1.0`, so `team_score` is directly interpretable as effective red gate-pass count.
- Perfect communication and fixed spawn positions are part of the frozen scenario, so the sweep focuses only on control gains and lane geometry.

## Input/Output

- Input: per-agent fixed-length observation for `act()`, or the full wrapped environment for `compute_actions(env)`.
- Output: clipped 3D acceleration command `[ax, ay, az]`.

## Training Method

No gradient training. `train.py` only materializes a checkpoint that stores the selected deterministic rule configuration.

## Safety Mechanism

- `SafeRulePolicy` predicts short-horizon collision and gate-frame risks before issuing commands.
- All actions are clipped to the environment bounds before leaving `PolicyClass`.
- Boundary repulsion and separation control remain active even when the nominal gate-following target changes.

## Known Limitations

- The current M1 controller uses one shared escort-style defender mode for both teams. That is sufficient to satisfy the red-side `team_score` target but does not fully model aggressive blue interception.
- `act()` is a contract-compatible fallback only. Best performance comes from `compute_actions(env)` because the controller reasons over full swarm geometry.

## Expected Failure Modes

- Raising `desired_speed` too far causes earlier crossover collisions in the center of the figure-eight.
- Shrinking `lane_spacing` too far increases same-team gate contention.
- Excessive `turn_lookahead` can slow down re-entry after the crossover and cap team score at 3.

## Computational Requirements

- CPU only
- Deterministic rollouts
- Typical evaluation cost: about 20-25 seconds for one 3-seed 1200-step sweep trial on the current workspace machine
