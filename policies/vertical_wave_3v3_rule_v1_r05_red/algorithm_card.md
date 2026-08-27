# vertical_wave_3v3_rule_v1_r05_red Algorithm Card

## Family

Rule-based safe swarm best response for Round 5 red. The package keeps explicit `RedPolicy` and `BluePolicy` classes; `PolicyClass` is the Policy ABC adapter that dispatches by team, handles fallback behavior, and clips final actions to the scenario action bounds.

## Compatible Scenarios

- `vertical_wave_3v3_001` with `formalism=POSG`.
- 3D `swarm_combat` environments with two racers and one defender per side.
- Observation shape `[94]` and acceleration action shape `[3]`.

## Assumptions

- The scenario remains frozen at `scenarios/vertical_wave_3v3_001`.
- Blue is the frozen Round 4 opponent using `experiments/vertical_wave_3v3_exp_001_r04_blue/trials/trial_0007/config.yaml`.
- Shared parameters are fixed because changing them would also change frozen blue behavior.
- Utility source: evaluator score outputs, with `red_utility=avg_red_score` and `blue_utility=avg_blue_score`.
- Optimization target: `red_utility - blue_utility > 0`.

## Input/Output

- Input: per-agent observations for `act()`, or a full environment object for `compute_actions(env)`.
- Output: bounded `[ax, ay, az]` acceleration commands as `np.float32`.

## Training Method

No gradient training is used. `train.py` validates paths and writes a deterministic checkpoint containing the selected config. The search space only opens red-side parameters for AutoResearch sweeps.

## Safety Mechanism

- Every returned action is clipped to `[action_space.low, action_space.high]`.
- The base `SafeRulePolicy` provides lane assignment, braking, collision lookahead, gate-frame checks, and boundary protection.
- Round 5 red post-processing adds an explicit red gate-frame guard after red-only action adjustments.
- Red-only Round 5 additions are racer breakout drive, vertical split-lane racer drive, blue-pressure escape, defender screen behavior, and an unused experimental defender standoff helper retained for regression traceability.
- Blue logic is copied from Round 4 and receives frozen best-trial blue/shared config values after any user overrides.
- `act()` catches exceptions and returns a zero action.

## Known Limitations

- `act()` is a contract fallback; competitive behavior relies on `compute_actions(env)`.
- The red defender screen is geometry-specific and may overcommit on layouts outside vertical-wave gates.
- This package does not claim Round 5 promotion before downstream experiment evaluation.

## Expected Failure Modes

- High red breakout gain can increase near misses around crowded gate entries.
- Low red risk margin may improve speed but reduce safety margin against the Round 4 blue pressure policy.
- Intercept-mode red defender may reduce escort coverage if blue racers separate widely.
- Vertical split lanes can reduce blue pressure but may reduce speed if the lane offset is too close to the gate aperture edge.

## Computational Requirements

CPU-only deterministic rollouts. No GPU or learning framework is required.
