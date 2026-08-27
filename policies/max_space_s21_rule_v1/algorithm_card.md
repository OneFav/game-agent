# Algorithm Card: max_space_s21_rule_v1

## Family

Rule-based / `role_aware_escort_defense_rule`. Learning is unnecessary for this stage because the package is an explicit, deterministic reference used to test protocol conformance and same-seed improvement over a zero-action baseline. It is not a claim that learning or MPC is unnecessary for a final high-fidelity solution.

## Compatible Scenarios

- Suite: `max_space_50_v1`
- Scenario: `S21` — 单护航者保护移动目标
- Task family: `escort_defense`
- Representative distinction: `protected_entity`

## Assumptions

- The execution observation follows `max_space_local_obs_v1`: position, velocity, target delta, progress, normalized step, message age, and role code.
- Graph and image observations expose scenario-declared `proprioception`/`self_state`; raw graph/image data is not treated as privileged state.
- RedPolicy and BluePolicy are separate frozen branches.
- No explicit opponent model and no training-only privileged global state are used.

## Input/Output

Input is the current agent's scenario-declared local observation plus non-privileged `info`. Output is one finite `2D` continuous control vector; hybrid scenarios consume this vector through their declared control projection.

## Training Method

`supports_training()` is false. `train.py` only validates/materializes configuration and emits a checkpoint, `training_log.json`, and one schema-valid `training_curves.csv` row. That row is explicitly not learning or convergence evidence. Training reward is not used.

## Method Hypothesis

For `S21`, `role_aware_escort_defense_rule` should improve `escort_success_rate` over `max_space_zero_v1` on the same seeds while preserving hard constraints. Suspected bottlenecks are `protected_entity`, observation modality `vector`, and the gain/damping safety trade-off.

Optimization guidance: tune gain and damping first, then action cap; tune role or communication parameters only after safety passes. This guidance is soft and never overrides immutable boundaries or scenario evaluation metrics.

## Optimization Target and Utility Source

Mode is `initial`; primary utility is the cross-seed mean of scenario evaluator metric `escort_success_rate`. Baseline and candidate use the same evaluator metric and seeds. Reward components are never substituted for the score.

## Immutable Boundaries

- Keep method `role_aware_escort_defense_rule` and its rule-based paradigm.
- Keep execution information inside `scenario.observation_space`; do not consume simulator/global state.
- Keep final action clipping to `scenario.action_space` and preserve the declared action projection.
- Do not modify scenario, evaluator, hidden tests, or switch method families in AutoResearch.
- Evaluation authority is `scenario.evaluation_metrics`.

## Safety Mechanism

Configuration is schema bounded. The controller uses finite-value checks, a configured action cap, an O(1) local computation path, exception-to-zero fallback, and final `numpy.clip` against environment action bounds.

## Known Limitations

The rule uses only compact execution fields and does not learn obstacle maps, graph plans, visual features, opponent dynamics, or external simulator residuals. It is intentionally a minimal reference, not a universal optimal controller.

## Expected Failure Modes

Partial observations may hide decisive geometry; delayed/lossy communication can make coordination stale; dense swarms can require explicit separation; hybrid task selection and external dynamics may exceed a local goal-vector rule.

## Computational Requirements

CPU-only NumPy; O(action dimension) per `act()` call, constant policy memory, expected latency well below 50 ms, and no accelerator or network dependency.
