# vertical_wave_3v3_rule_v1_r03_red Algorithm Card

## Family

Rule-based safe swarm controller built on the repository `SafeRulePolicy`.
The package exposes explicit `RedPolicy` and `BluePolicy` wrappers. `PolicyClass` dispatches by team, handles exception fallback, and clips final actions.
This Round 3 package is a red-side best response against the frozen Round 2 blue policy.

## Compatible Scenarios

- `vertical_wave_3v3_001` with `formalism=POSG`.
- 3D `swarm_combat` wrappers with two racers and one defender per team.
- Fixed observation dimension 94 and 3D acceleration action bounds.

## Assumptions

- The scenario package is frozen and consumed read-only.
- Utility source is evaluator score output: `red_utility=avg_red_score`, `blue_utility=avg_blue_score`.
- The Round 3 optimization target is `red_utility - blue_utility > 0`.
- Blue is the frozen opponent from `experiments/vertical_wave_3v3_exp_001_r02_blue/best_config.yaml`: `blue_desired_speed=6.6`, `blue_risk_margin=1.0`, `blue_lane_spacing=1.6`, `blue_defender_mode=intercept`.
- `shared_` parameters are fixed because they encode geometry and safety mechanisms common to both teams.

## Input/Output

- Input: per-agent observation for `act()`, or full environment state for `compute_actions(env)`.
- Output: bounded `[ax, ay, az]` acceleration command for each drone.

## Training Method

No gradient training is used. `train.py` validates inputs and serializes the selected config into `checkpoint.json` for deterministic replay.
Round 3 tuning only searches `red_desired_speed`, `red_risk_margin`, `red_lane_spacing`, and optionally `red_defender_mode`.

## Safety Mechanism

- `act()` and `compute_actions()` clip every returned action to scenario action bounds.
- `SafeRulePolicy` applies lane assignment, lookahead collision checks, boundary protection, and braking fallback.
- Blue-side decision logic is unchanged and parameter-frozen for this red round.
- `act()` returns a zero action if any exception occurs.

## Known Limitations

- `act()` is a contract-compatible fallback; strongest behavior requires `compute_actions(env)`.
- Rule parameters are specialized for the `vertical_wave` geometry.
- Aggressive red speed and tighter red risk margin may require experiment sweeps to retain hard-constraint margins.

## Expected Failure Modes

- High `red_desired_speed` can increase gate-frame and boundary risk.
- Low `red_risk_margin` can reduce braking time near the intercepting blue defender.
- `red_defender_mode=intercept` can abandon escort coverage and expose red racers.

## Computational Requirements

CPU-only deterministic rollout. No GPU is required. Expected training wall time is under one second because training is checkpoint serialization only.
