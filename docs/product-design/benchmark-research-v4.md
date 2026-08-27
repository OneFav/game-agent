# AutoGame V4 — Benchmark Research and Product Direction

## Product position

AutoGame should be an evidence-first experiment workbench:

- the default surface explains what happened in the simulated world;
- replay, events, metrics, and decisions share one time or round selection;
- human attention is requested only for an existing failure or constraint conflict;
- the UI reads repository artifacts and does not ask agents to maintain a parallel progress model.

## Reference products

### Rerun — visualization kernel

Borrow:

- one recording timeline drives 2D, 3D, time-series, state, and log views;
- the same entity selection is highlighted across views;
- layouts can be prescribed by code instead of configured by every user;
- the Web Viewer can be embedded in a React application.

Sources:

- https://rerun.io/docs/reference/viewer/overview
- https://rerun.io/docs/reference/types/views
- https://rerun.io/docs/reference/viewer/timeline
- https://rerun.io/docs/howto/integrations/embed-web

### Foxglove — physical experiment investigation

Borrow:

- replay, 3D/image panels, plots, and event/state panels share playback time;
- current playback time is visible inside plots;
- baseline and candidate recordings can be aligned on one timeline;
- comparison supports overlay for plots and source-specific spatial/media views.

Sources:

- https://docs.foxglove.dev/docs/visualization
- https://docs.foxglove.dev/docs/visualization/panels/plot
- https://docs.foxglove.dev/docs/visualization/comparison-mode
- https://docs.foxglove.dev/docs/visualization/panels/image

### Weights & Biases — experiment and media comparison

Borrow:

- baseline and candidate are stable comparison identities;
- media comparison links run, step, and index selections;
- a focused manual workspace shows intentionally selected evidence;
- curves from several runs can share one plot and one cursor.

Do not borrow the automatic wall of metric cards.

Sources:

- https://docs.wandb.ai/models/app/features/panels/media
- https://docs.wandb.ai/models/app/features/panels/line-plot
- https://docs.wandb.ai/models/runs/compare-runs

### MLflow and Braintrust — run hierarchy and regression triage

Borrow:

- Experiment → Run → Artifact as the navigation model;
- align cases against a baseline and sort by delta/regression;
- keep immutable results directly inspectable.

Sources:

- https://mlflow.org/docs/latest/tracking
- https://www.braintrust.dev/docs/evaluate/compare-experiments

### LangSmith — exception-only human review

Borrow only the focused review pattern: one failed run and its evidence at a time.

Do not add annotation-queue progress or reviewer state to AutoGame until collaboration requires it. The initial trigger is derived only from existing result fields.

Source:

- https://docs.langchain.com/langsmith/annotation-queues

## AutoGame V4 surfaces

### 1. Investigate — default experiment page

- Spatial replay occupies most of the canvas.
- A single bottom timeline contains frame position and event markers.
- Metric charts use the same cursor as the replay.
- Selecting an entity highlights its trajectory, reward, action, messages, and events.
- The result rail shows only primary metric, comparison delta, constraints, and final decision.

### 2. Compare — baseline versus candidate

- Two synchronized replay panes share the same camera and time cursor.
- A compact difference view shows changed trajectories or metric deltas.
- The scenario list is ordered by regression or constraint failure, not by agent activity.
- The selected scenario shows the exact evidence that caused promotion or rejection.

### 3. Suite — the 50-scenario index

- The suite page is an index into experiments, not a dashboard destination.
- Each row contains scenario, primary metric, baseline, candidate, delta, constraints, and promotion.
- Opening a row always leads to Investigate or Compare.

## Existing-data mapping

| Product content | Existing source |
|---|---|
| World, bounds, camera, default layers | `ScenarioDescriptor.visualization` / `VisualizationSpec` |
| Spatial replay | `FramePacket.entities`, `relations`, `fields` |
| Timeline and event marks | `scenario_time`, `episode_step`, `events` |
| Entity inspection | `observations`, `actions`, `messages`, `rewards` |
| Live and final plots | `FramePacket.metrics` |
| Baseline/candidate comparison | `state.json`, `comparison.json`, paired replay files |
| Round comparison | `game/*/round_history.json` |
| Human-review trigger | `FAIL_STOP`, `ERROR`, or `constraints_passed == false` |

## Implementation direction

Use a thin AutoGame product shell with prescribed layouts. Prototype the replay kernel with Rerun's Python SDK and embedded Web Viewer, because the current `FramePacket` and `VisualizationSpec` already map to its entity, spatial, scalar, and timeline concepts. Keep AutoGame's suite comparison, promotion decision, and exception review outside the embedded viewer.

This avoids rebuilding a general-purpose 2D/3D/timeline renderer while preserving a low-complexity product experience.
