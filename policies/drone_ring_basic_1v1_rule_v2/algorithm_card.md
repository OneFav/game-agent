# Algorithm Card: drone_ring_basic_1v1_rule_v2

## Scenario
- Task id: `drone_ring_basic_1v1_001`
- Policy type: `rule_ring_navigation`

## Method
Deterministic rule policy. The red agent moves toward the active ring direction from the observation. The blue
agent uses the configured interception direction field. Actions are clipped to the scenario action bounds.
The direct geometric fields make learning or MPC unnecessary for this reproducible baseline.

## Method hypothesis
Ring-relative direction and interception direction are assumed to contain enough information for a bounded
geometric controller. The likely bottlenecks are the speed/maneuverability trade-off, interception pressure,
and the safety margin rather than the overall method family.

## Hypothesis-driven optimization guidance
1. Tune motion and interception gains before changing policy code.
2. Treat `safety_margin` as a constraint-oriented parameter, not as a reward proxy.
3. Keep this guidance as a soft search priority; scenario evaluation metrics remain the promotion authority.

## Immutable boundaries
- Keep the `rule_ring_navigation` method family.
- Use only observations allowed by the scenario contract during execution.
- Clip actions to scenario bounds.
- Never modify the frozen scenario or rank candidates by training reward.

## Trainability
`train.py` is a no-op trainer that emits a reproducible checkpoint placeholder for AutoResearch integration.

## Initial AutoResearch surface
- `speed_scale`
- `intercept_gain`
- `safety_margin`
