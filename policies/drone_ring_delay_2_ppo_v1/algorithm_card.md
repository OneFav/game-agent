# Algorithm Card: drone_ring_delay_2_ppo_v1

## Method decision

- Method: independent PPO for `red_0` against a deterministic frozen `blue_0` interceptor.
- Learning mode: online reinforcement learning; one learned policy in a two-agent Markov game.
- Execution: decentralized. The actor sees only the current 12-dimensional local observation.
- Privileged training state: none.
- Explicit opponent model: none.

Fixed geometric rules are a useful baseline, but delayed continuous pursuit creates avoidance and timing decisions that vary with the trajectory. MPC would require a trusted model for the opponent response, which is not part of the frozen scenario contract. The falsifiable hypothesis is that PPO plus bounded distance-progress shaping improves the scenario `success_rate` while satisfying every hard constraint.

## Trained and frozen roles

- Trained: `red_0`.
- Frozen: `blue_0`, using a deterministic proportional pursuit rule.
- Parameter sharing: none.

## Reward intent

Environment ring progress, terminal success, and timeout terms remain present. Training additionally uses bounded ring-distance progress, control effort, collision, and out-of-bounds shaping. These terms train the actor and critic only. Promotion is determined solely by `scenario.evaluation_metrics`.

## Optimization guidance

1. Stage 1 tunes actor learning rate and the dense progress reward weight.
2. If stage 1 plateaus, stage 2 may adjust the PPO training recipe and bounded reward formulation.
3. Stage 3 may change policy-local network implementation while retaining PPO and every invariant below.

## Immutable boundaries

- PPO is the algorithm family.
- Only `red_0` learns; `blue_0` remains frozen.
- Inference uses local observation only, with no future action or global state.
- The frozen scenario, evaluation metrics, and safety thresholds cannot change.
- Normalized learned actions are mapped to the scenario bounds and clipped.

## Checkpoint contract

Every checkpoint binds the method name, observation dimension 12, scenario action dimension 4, learned action dimension 2, agent count 2, no parameter sharing, and preprocessing identifier `drone_ring_obs_scale_v1`. Loading rejects a mismatch.

## Training telemetry

`training_curves.csv` is an event stream rather than a repeated snapshot table. It records every completed episode, every PPO optimizer update, and fixed-seed evaluation at the configured environment-step interval. The single process figure overlays raw episode reward with its rolling mean and keeps evaluation metrics separate from the training signal.

## Source provenance

The PPO, trajectory-buffer, action-scaling, and checkpoint-validation components were reviewed and adapted from `Sailero/mvp_inner_loop` revision `8aa6a22f055312b7970bf073f1e4af65560aef27`. The policy does not depend on an external checkout at runtime.
