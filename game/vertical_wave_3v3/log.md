# vertical_wave_3v3 Execution Log

## Scope

- Request: continue `$game-main vertical_wave_3v3 --rounds 5` after raising the controlled policy-code iteration limit from 3 to 10.
- Rule source updated: `.codex/agents/experiment_autoresearch.toml`
- Scenario package stayed frozen: `scenarios/vertical_wave_3v3_001/`

## Subagent Calls After Limit Change

| Call | Round | Subagent | Agent ID | Status |
|---:|---:|---|---|---|
| 1 | 4 | experiment_autoresearch | `019f208c-667e-7fd0-84b6-4c0a176a5abb` | PASS |
| 2 | 5 | policy_designer | `019f209d-084c-7a73-a949-bad1ab0331d5` | PASS |
| 3 | 5 | experiment_autoresearch | `019f20b7-c3c7-7f51-9022-1b46f7502d66` | FAIL_STOP |

## Round 4 Continued Experiment

- Target side: blue
- Policy: `policies/vertical_wave_3v3_rule_v1_r04_blue/`
- Experiment: `experiments/vertical_wave_3v3_exp_001_r04_blue/`
- Best trial: `trial_0007`
- Result: PASS
- Metrics: `blue_utility=8.333`, `red_utility=5.000`, `blue-red=3.333`
- Hard constraints: `collision_rate=0.000`, `out_of_bounds_rate=0.000`, `action_violation_rate=0.000`
- Coupling load: `Delta_B=5.667`
- Best-response gain: `best_response_gain_blue=0.333`
- Code iterations: `4/10` total, with one new blue-only code iteration after the limit change.
- Validation:
  - `python src/hooks/post_policy_submit.py --policy policies/vertical_wave_3v3_rule_v1_r04_blue`
  - `python -m pytest policies/vertical_wave_3v3_rule_v1_r04_blue/tests -q`
  - `python src/hooks/post_experiment_run.py --exp experiments/vertical_wave_3v3_exp_001_r04_blue`

## Round 5 Policy Design

- Target side: red
- Policy: `policies/vertical_wave_3v3_rule_v1_r05_red/`
- Frozen opponent: Round 4 blue best trial `trial_0007`
- Result: PASS for package construction and validation.
- Open red parameters: `red_desired_speed`, `red_risk_margin`, `red_lane_spacing`, `red_breakout_gain`, `red_escape_gain`, `red_screen_gain`, `red_defender_mode`
- Frozen blue parameters: `blue_desired_speed=6.4`, `blue_risk_margin=1.4`, `blue_lane_spacing=1.4`, `blue_defender_mode=escort`, `blue_intercept_gain=2.6`, `blue_intercept_radius=5.0`, `blue_pressure_buffer=1.0`
- Validation:
  - `python src/hooks/post_policy_submit.py --policy policies/vertical_wave_3v3_rule_v1_r05_red`
  - `python -m pytest policies/vertical_wave_3v3_rule_v1_r05_red/tests -q`

## Round 5 Experiment

- Target side: red
- Experiment: `experiments/vertical_wave_3v3_exp_001_r05_red/`
- Best trial: `trial_0012`
- Result: FAIL_STOP
- Metrics: `red_utility=9.000`, `blue_utility=9.333`, `red-blue=-0.333`
- Hard constraints: `collision_rate=0.000`, `out_of_bounds_rate=0.000`, `action_violation_rate=0.000`
- Coupling load: `Delta_R=1.000`
- Best-response gain: `best_response_gain_red=4.000`
- Final package trials: 18
- Cumulative full trial evaluations: 198 (`11` sweeps x `18` trials)
- Code iterations: `10/10`
- Stop reason: reached 10 controlled red policy-code iterations, but the best feasible trial still did not satisfy `red_utility - blue_utility > 0`.
- Validation:
  - `python src/hooks/post_policy_submit.py --policy policies/vertical_wave_3v3_rule_v1_r05_red`
  - `python -m pytest policies/vertical_wave_3v3_rule_v1_r05_red/tests -q`
  - `python src/hooks/post_experiment_run.py --exp experiments/vertical_wave_3v3_exp_001_r05_red`

## Final State

The workflow continued past the previous Round 4 failure and reached Round 5. Round 5 failed after exhausting the updated 10-code-iteration limit, so the full `--rounds 5` run cannot be marked successful.
