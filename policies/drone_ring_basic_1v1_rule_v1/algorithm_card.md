# Algorithm Card: drone_ring_basic_1v1_rule_v1

## Scenario
- Task id: `drone_ring_basic_1v1_001`
- Policy type: `rule_ring_navigation`

## Method
Deterministic rule policy. The red agent moves toward the active ring direction from the observation. The blue
agent uses the configured interception direction field. Actions are clipped to the scenario action bounds.

## Trainability
`train.py` is a no-op trainer that emits a reproducible checkpoint placeholder for AutoResearch integration.

## AutoResearch knobs
- `speed_scale`
- `intercept_gain`
- `safety_margin`
