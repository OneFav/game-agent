# Current Round Visualization Summary

## Data Scope

The figures use `game/vertical_wave_3v3/round_history.json` after the 10-code-iteration-limit continuation.
Rounds 2, 3, 4, and 5 are visualized. Round 4 is now `PASS`; Round 5 is `FAIL_STOP`.
Legacy experiment folders outside this execution record are intentionally excluded.

## Generated Files

- `current_round_dashboard.pdf` / `current_round_dashboard.png`: multi-panel overview of red/blue utilities, target-side margin, coupling load, best-response gain, and hard safety constraints.
- `trial_advantage_distribution.pdf` / `trial_advantage_distribution.png`: trial-level advantage score distribution for each executed round.
- `trajectory_3d_round02_blue_pass_seed23.png`: Round 2 best-config rollout trajectory.
- `trajectory_3d_round03_red_pass_seed23.png`: Round 3 best-config rollout trajectory.
- `trajectory_3d_round04_blue_pass_seed23.png`: current Round 4 best-config rollout trajectory after the continued blue PASS.
- `trajectory_3d_round05_red_fail_stop_seed23.png`: Round 5 best-config rollout trajectory after red failed to reach positive advantage.
- `current_round_metrics.csv`: compact tabular data used by the dashboard.
- `generate_round_visualizations.py`: reproducible plotting script.
- `generate_trajectory_3d.py`: reproducible 3D trajectory plotting script.

## Superseded Artifact

- `trajectory_3d_round04_blue_fail_stop_seed23.png` is a stale pre-continuation artifact from the earlier Round 4 failure. It is not used by the current summary.

## Key Reading

- Round 2 passed for blue: `blue_utility - red_utility = 4.000`.
- Round 3 passed for red: `red_utility - blue_utility = 0.667`.
- Round 4 passed for blue after one additional code iteration: `blue_utility - red_utility = 3.333`.
- Round 5 failed for red after 10 red code iterations: `red_utility - blue_utility = -0.333`.
- Hard constraints stayed at zero for all executed rounds: collision rate, out-of-bounds rate, and action violation rate.

## Rebuild Command

```powershell
python "game/vertical_wave_3v3/figures/generate_round_visualizations.py"
python "game/vertical_wave_3v3/figures/generate_trajectory_3d.py" --seed 23
```
