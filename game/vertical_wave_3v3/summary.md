# vertical_wave_3v3 Execution Summary

## Result

The run continued after increasing the controlled policy-code iteration limit to 10. Round 4 blue passed after one additional code iteration. Round 5 red was then executed, but stopped after exhausting 10 red code iterations without reaching the red advantage target.

Final status: `FAIL_STOP` at Round 5.

## Subagent Accounting

- Full `X=5` nominal plan: `2*X+1 = 11` subagent calls.
- Calls completed before the limit change: 9 effective calls, including the prior Round 4 failed experiment attempt.
- Calls after the limit change: 3
- Total effective subagent calls in this resumed workflow: 12

| Call scope | Round | Subagent | Agent ID | Status |
|---|---:|---|---|---|
| resumed | 4 | experiment_autoresearch | `019f208c-667e-7fd0-84b6-4c0a176a5abb` | PASS |
| resumed | 5 | policy_designer | `019f209d-084c-7a73-a949-bad1ab0331d5` | PASS |
| resumed | 5 | experiment_autoresearch | `019f20b7-c3c7-7f51-9022-1b46f7502d66` | FAIL_STOP |

## Round Results

| Round | Target | Red Utility | Blue Utility | Target Margin | Coupling | Code Edits | Status |
|---:|---|---:|---:|---:|---:|---:|---|
| 2 | blue | 5.000 | 9.000 | 4.000 | 2.667 | 0 | PASS |
| 3 | red | 8.667 | 8.000 | 0.667 | 3.000 | 1 | PASS |
| 4 | blue | 5.000 | 8.333 | 3.333 | 5.667 | 4 | PASS |
| 5 | red | 9.000 | 9.333 | -0.333 | 1.000 | 10 | FAIL_STOP |

## Key Artifacts

- Round 4 policy: `policies/vertical_wave_3v3_rule_v1_r04_blue/`
- Round 4 experiment: `experiments/vertical_wave_3v3_exp_001_r04_blue/`
- Round 5 policy: `policies/vertical_wave_3v3_rule_v1_r05_red/`
- Round 5 experiment: `experiments/vertical_wave_3v3_exp_001_r05_red/`
- Round history: `game/vertical_wave_3v3/round_history.json`
- Visualizations: `game/vertical_wave_3v3/figures/`

## Final Game Interpretation

- Current best Round 5 result still favors blue by `0.333` utility: `red_utility - blue_utility = -0.333`.
- Red did improve substantially against the frozen Round 4 blue policy: `best_response_gain_red = 4.000`.
- Blue's most recent completed best-response gain was `best_response_gain_blue = 0.333`.
- Empirical approximate Nash stability is not claimed because at least one recent best-response gain remains positive, and Round 5 failed its target under the configured finite search and 10-code-iteration limit.

## Verification

The final Round 5 policy and experiment packages passed:

```powershell
python src/hooks/post_policy_submit.py --policy policies/vertical_wave_3v3_rule_v1_r05_red
python -m pytest policies/vertical_wave_3v3_rule_v1_r05_red/tests -q
python src/hooks/post_experiment_run.py --exp experiments/vertical_wave_3v3_exp_001_r05_red
```
