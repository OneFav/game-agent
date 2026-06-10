# wide_slalom_2v2_001 Model

## Formalism

This scenario is a partially observable stochastic game (POSG). Four agents act simultaneously: `red_racer_0`, `red_defender_0`, `blue_racer_0`, and `blue_defender_0`.

## Roles

Red has one racer and one defender escort. The red racer is the task-progress agent and must pass a six-gate `wide_slalom` sequence. The red defender escorts the racer and is modeled in the scenario contract as a protective teammate.

Blue has one racer and one defender intercept. The blue side opposes red progress. The blue defender is the primary interceptor in the M1 termination semantics.

## State, Observations, and Actions

The frozen M1 interface uses a per-agent observation vector of shape `(32,)` and a per-agent action vector of shape `(4,)`. The observation includes own state, teammate relative state, two opponent relative states, next-gate direction/distance, role one-hot features, nearest-opponent state, gate index, and normalized step. The first two action entries are 2D velocity commands. The last two entries are reserved for compatibility with the current `drone_ring_game` policy interface.

## Transition and Communication

The local environment is deterministic under `reset(seed=...)`. Communication mode is `perfect`, so no delayed or dropped communication is applied and `communication_dropped` is always false.

## Rewards and Metrics

Reward components are training signals only. The primary evaluation metric is `success_rate`, which is intentionally separate from all reward component names. Hard constraints include `collision_rate`, `out_of_bounds_rate`, and `action_violation_rate`.

## Termination

The episode terminates when the red racer passes all gates, when interception/collision occurs, or when any agent leaves bounds. It truncates at `max_steps=600`.

## M1 Compatibility Note

The source plan states that the current 1v1 `drone_ring_game` reference environment cannot fully express this 2v2 wide slalom task. This package therefore freezes the 2v2 semantics in `task_spec.yaml` and `env_config.yaml`, while implementing a compact 2D environment with the plan-required four-agent roles and expanded fixed-length observations.
