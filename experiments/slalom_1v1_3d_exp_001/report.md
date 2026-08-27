# AutoResearch Report: slalom_1v1_3d_exp_001

## Sweep Summary

- Trials: 13
- Eval seeds: [100, 101, 102]
- Best trial: `trial_0007`
- Best team_score: 1.000
- Best blue_team_score: 0.000
- Best red_win_rate: 1.000
- Best collision_rate: 0.000

## Iteration Notes

- Round 1 fixed `avoidance_gain=0.46` and scanned `racer_gain × intercept_gain` to establish a stable score/safety baseline.
- Round 2 fixed the best round-1 `(racer_gain, intercept_gain)` pair and refined `avoidance_gain` plus `boundary_gain` to reduce collisions and keep score above target.

## Leaderboard Top 3

1. `trial_0007` | round=round1 | team_score=1.000 | collision_rate=0.000 | decision=promote
2. `trial_0008` | round=round1 | team_score=1.000 | collision_rate=0.000 | decision=promote
3. `trial_0009` | round=round1 | team_score=1.000 | collision_rate=0.000 | decision=promote

## Conclusion

- README target `team_score >= 1.0` 已满足。
- 排名仅使用 evaluation_metrics 与硬约束，没有使用 reward components 做晋级判断。
