# AutoGame Workbench V2 — UI State Mapping

## Principles

- The interface is a daily tool, not an explanatory presentation.
- The UI reads existing artifacts; agents do not maintain a second UI state.
- Show labels, values, and actions. Avoid explanatory microcopy.
- Human intervention appears only when existing results require a decision.

## Existing-state mapping

| UI element | Existing source | Existing fields |
|---|---|---|
| Suite status | `suite_runs/*/state.json` | `status` |
| Suite progress | `suite_runs/*/state.json` | `completed_count`, `scenario_count` |
| Scenario cell | `state.json.scenarios[id]` | `scenario_id`, `status`, `task_family` |
| Scenario comparison | `state.json.scenarios[id]` | `baseline_mean`, `candidate_mean`, `delta` |
| Promotion state | `state.json.scenarios[id]` | `promoted`, `constraints_passed` |
| Scenario result details | `scenario_results.csv`, `comparison.json` | existing result columns |
| Replay action | `replay_index.json` | `replays`, `path`, `frame_count`, `duration` |
| Research level | `experiments/*/research_state.json` | `stage`, `history` |
| Trial result | `leaderboard.csv`, `trials/*/metrics.json` | existing metric columns |
| Game rounds | `game/*/round_history.json` | `round_id`, `target_side`, `status` |
| Round metrics | `round_history.json` | utility, margin, constraints, trial count |
| Artifact availability | filesystem | scenario, policy, and experiment directory existence |

## Human intervention

Show a decision action only when one of these existing conditions is true:

- `status == "FAIL_STOP"`
- `status == "ERROR"`
- `constraints_passed == false`

Do not create or persist additional agent activity, explanation, or progress state for the UI.
