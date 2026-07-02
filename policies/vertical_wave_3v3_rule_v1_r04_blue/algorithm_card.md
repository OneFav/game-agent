# vertical_wave_3v3_rule_v1_r04_blue Algorithm Card

## Family

Rule-based safe swarm controller built on the repository `SafeRulePolicy`.
The package exports explicit `RedPolicy` and `BluePolicy` classes, with `PolicyClass` acting as the Policy ABC adapter, team dispatcher, exception fallback, and final action clipper.

## Compatible Scenarios

- `vertical_wave_3v3_001` with `formalism=POSG`.
- 3D `swarm_combat` wrappers with six agents: two racers and one defender per side.
- Observation shape `[94]` and action shape `[3]` with acceleration bounds `[-10, 10]`.

## Assumptions

- Round 4 is `mode=blue`; red is the frozen opponent.
- Red behavior is copied from Round 3 and red parameters are locked to `experiments/vertical_wave_3v3_exp_001_r03_red/best_config.yaml`: `red_desired_speed=6.4`, `red_risk_margin=0.8`, `red_lane_spacing=1.6`, `red_defender_mode=escort`.
- Shared geometry and safety parameters are also fixed to the Round 3 values because changing them would alter red-side behavior.
- Only `blue_` parameters are intended for this round's best-response search.
- Utility source is the policy package optimization target: `red_utility=avg_red_score`, `blue_utility=avg_blue_score`.

## Input/Output

- Input: per-agent fixed-length observation for `act()`, or full environment state for `compute_actions(env)`.
- Output: bounded 3D acceleration action per agent.

## Training Method

No gradient training is used. `train.py` validates the scenario/config inputs and serializes the selected deterministic config into `checkpoint.json`.

## Safety Mechanism

- `PolicyClass.act()` and `compute_actions()` clip final actions to scenario bounds.
- `act()` returns a zero action on exceptions and performs no file writes or logging.
- `SafeRulePolicy` provides lane assignment, lookahead collision checks, boundary protection, and braking fallback.
- The frozen red side keeps the Round 3 inter-team buffer unchanged.
- The blue side adds a blue-only intercept pressure layer: the blue defender pressures the leading red racer within a tunable radius, while blue racers use a small near-opponent safety buffer.
- Round 4 iteration 4 adds a blue-only defender gate-frame guard after blue pressure/escort actions to avoid gate-frame contacts without changing frozen red behavior.

## Known Limitations

- `act()` is a contract fallback based on the local observation; strongest behavior uses full-state `compute_actions(env)`.
- The blue pressure layer is geometric and does not optimize over long horizons.
- This package is specific to the vertical-wave 3v3 layout and should be retuned before use on unrelated maps.

## Expected Failure Modes

- Too high `blue_intercept_gain` can trigger braking or near misses when the defender overcommits.
- Too small `blue_lane_spacing` can create blue racer congestion around gates.
- Too low `blue_risk_margin` can improve pressure but may violate hard safety constraints.

## Computational Requirements

CPU-only deterministic rollout. No training GPU or learned-model dependency is required.
