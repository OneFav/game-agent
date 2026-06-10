# Wide Slalom 2v2 Rule Policy

## Family

Rule-based geometric navigation policy.

## Compatible Scenarios

Designed for `wide_slalom_2v2_001` in the `drone_ring_game` family. It expects the frozen 32-dimensional scenario observation and 4-dimensional actions with bounds from the scenario action space. The implementation also accepts legacy 12-dimensional smoke-test observations for hook compatibility.

## Assumptions

The policy uses the frozen 32-dimensional observation contract: self state, teammate relative state, both opponent relative states, next-gate direction/distance, team/role one-hot features, nearest-opponent state, gate index, and normalized step. It does not require hidden environment state.

## Input/Output

Input is one per-agent observation. Output is a `(4,)` float32 action. Entries 0 and 1 are velocity setpoints. Entries 2 and 3 are reserved by the M1-compatible interface and are fixed to zero.

## Training Method

No learning is required. `train.py` validates inputs and writes a JSON checkpoint containing the selected configuration.

## Safety Mechanism

Configuration values are checked against the JSON-schema-like bounds returned by `get_config_schema()`. `act()` handles exceptions by returning a zero action, applies a geofence shield at 1.2 times positive action bounds, and returns only the final `np.clip(action, low, high)` result.

## Known Limitations

The 2v2 roles are geometric rules rather than learned coordination. `red_defender_0` uses teammate/opponent-relative state for escorting and avoidance. Blue agents use lane offsets plus nearest-opponent state to apply pressure without hard-collision blocking.

## Expected Failure Modes

The policy can fail when nearest-opponent identity differs from the intended target, when escort spacing requires unavailable teammate coordinates, or when narrow timing around gates requires planning beyond the next-gate direction.

## Computational Requirements

CPU-only. `act()` performs a few vector operations and is expected to run well below 50 ms per call.
