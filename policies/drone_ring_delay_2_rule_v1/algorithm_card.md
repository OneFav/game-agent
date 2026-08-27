# Algorithm Card: drone_ring_delay_2_rule_v1

## Scenario
- Task id: `drone_ring_delay_2_001`
- Policy type: `rule_ring_navigation`
- Communication condition: `delayed`, `delay_steps = 2`

## Method
Deterministic rule policy. The red agent moves toward the active ring direction and injects a short-range
avoidance vector when the blue interceptor is too close. The blue agent keeps a per-agent observation buffer and
uses a 2-step delayed estimate of red relative position/velocity for pursuit, then brakes away at very short range
to reduce hard-constraint failures. Actions are clipped to the scenario action bounds.

## Trainability
`train.py` is a no-op trainer that emits a reproducible checkpoint placeholder for AutoResearch integration.

## AutoResearch knobs
- `speed_scale`
- `intercept_gain`
- `safety_margin`

## Fixed Safety Parameters
- `delay_steps = 2`
- `pursuit_brake_distance = 0.35`
