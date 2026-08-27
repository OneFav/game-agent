const API_ROOT = "/api";
const FALLBACK_SCENARIO_ID = "DEMO-01";
const DEFAULT_FRAME_LIMIT = 200;
const DEFAULT_SPEEDS = [0.5, 1, 1.5, 2, 3];
const RECOGNIZED_LAYER_SOURCES = new Set([
  "entities",
  "entity_goals",
  "relations",
  "fields",
  "events",
  "trajectories",
  "static_primitives",
  "boundaries",
  "rings",
]);

const dom = {
  announcement: document.getElementById("announcement"),
  canvas: document.getElementById("sceneCanvas"),
  connectionStatus: document.getElementById("connectionStatus"),
  connectionStatusText: document.getElementById("connectionStatusText"),
  scenarioStatus: document.getElementById("scenarioStatus"),
  frameStatus: document.getElementById("frameStatus"),
  scenarioFilter: document.getElementById("scenarioFilter"),
  scenarioSelect: document.getElementById("scenarioSelect"),
  scenarioList: document.getElementById("scenarioList"),
  roleSelect: document.getElementById("roleSelect"),
  seedSelect: document.getElementById("seedSelect"),
  projectionSelect: document.getElementById("projectionSelect"),
  reloadButton: document.getElementById("reloadButton"),
  playButton: document.getElementById("playButton"),
  stepBackButton: document.getElementById("stepBackButton"),
  stepForwardButton: document.getElementById("stepForwardButton"),
  slowerButton: document.getElementById("slowerButton"),
  fasterButton: document.getElementById("fasterButton"),
  frameSlider: document.getElementById("frameSlider"),
  timelineStart: document.getElementById("timelineStart"),
  timelineMid: document.getElementById("timelineMid"),
  timelineEnd: document.getElementById("timelineEnd"),
  canvasTitle: document.getElementById("canvasTitle"),
  canvasSubtitle: document.getElementById("canvasSubtitle"),
  agentCount: document.getElementById("agentCount"),
  eventCount: document.getElementById("eventCount"),
  dimensionLabel: document.getElementById("dimensionLabel"),
  speedValue: document.getElementById("speedValue"),
  liveFrameValue: document.getElementById("liveFrameValue"),
  liveFrameCaption: document.getElementById("liveFrameCaption"),
  layerToggles: document.getElementById("layerToggles"),
  metricsGrid: document.getElementById("metricsGrid"),
  eventList: document.getElementById("eventList"),
  disclosureList: document.getElementById("disclosureList"),
  rawWarnings: document.getElementById("rawWarnings"),
  rawData: document.getElementById("rawData"),
  projectTitle: document.getElementById("projectTitle"),
  projectCount: document.getElementById("projectCount"),
  suiteProjectCount: document.getElementById("suiteProjectCount"),
  workflowSteps: document.getElementById("workflowSteps"),
  baselineRoleButton: document.getElementById("baselineRoleButton"),
  candidateRoleButton: document.getElementById("candidateRoleButton"),
  emptyProjectPanel: document.getElementById("emptyProjectPanel"),
  metricChart: document.getElementById("metricChart"),
  chartTitle: document.getElementById("chartTitle"),
  primaryMetricLabel: document.getElementById("primaryMetricLabel"),
  baselineValue: document.getElementById("baselineValue"),
  candidateValue: document.getElementById("candidateValue"),
  deltaValue: document.getElementById("deltaValue"),
  constraintCard: document.getElementById("constraintCard"),
  constraintSummary: document.getElementById("constraintSummary"),
  constraintEvidence: document.getElementById("constraintEvidence"),
  promotionValue: document.getElementById("promotionValue"),
  jumpEvidenceButton: document.getElementById("jumpEvidenceButton"),
  currentMethod: document.getElementById("currentMethod"),
  newProjectButton: document.getElementById("newProjectButton"),
  newProjectDialog: document.getElementById("newProjectDialog"),
  newProjectForm: document.getElementById("newProjectForm"),
  closeProjectDialog: document.getElementById("closeProjectDialog"),
  cancelProjectDialog: document.getElementById("cancelProjectDialog"),
  newProjectTitle: document.getElementById("newProjectTitle"),
  newProjectGoal: document.getElementById("newProjectGoal"),
  newProjectError: document.getElementById("newProjectError"),
  newProjectSubmit: document.getElementById("newProjectSubmit"),
  agentMessageForm: document.getElementById("agentMessageForm"),
  agentMessageInput: document.getElementById("agentMessageInput"),
  actionFeedback: document.getElementById("actionFeedback"),
  pauseProjectButton: document.getElementById("pauseProjectButton"),
};

const state = {
  scenarios: [],
  scenarioIndex: new Map(),
  currentProject: null,
  selectedScenarioId: null,
  selectedScenario: null,
  visualization: null,
  replays: [],
  replayBundle: null,
  selectedRole: "candidate",
  selectedSeed: 0,
  selectedProjection: "3d",
  frameWindow: [],
  frameWindowStart: 0,
  totalFrames: 0,
  currentFrameIndex: 0,
  layers: new Map(),
  layerMeta: [],
  warnings: [],
  loading: false,
  connection: "connecting",
  error: "",
  playState: {
    playing: false,
    speed: 1,
    lastTick: performance.now(),
    accumulator: 0,
  },
  requestEpoch: 0,
  useDemo: false,
};

let renderer = null;
const resizeObserver = new ResizeObserver(() => {
  if (!renderer) {
    return;
  }
  renderer.resize();
  renderScene();
});

dom.canvas.setAttribute("tabindex", "0");

window.addEventListener("DOMContentLoaded", () => {
  init().catch((error) => {
    console.error(error);
    setConnectionState("bad", `初始化失败：${error.message}`);
    showError(error.message);
  });
});

async function init() {
  renderer = new SceneRenderer(dom.canvas);
  resizeObserver.observe(dom.canvas);
  bindEvents();
  applyQueryState();
  renderer.resize();
  setConnectionState("warn", "连接实验数据");
  await loadScenarioCatalog();
  startPlaybackLoop();
  startProjectPolling();
}

function bindEvents() {
  dom.scenarioFilter.addEventListener("input", () => renderScenarioCatalog());
  dom.scenarioSelect.addEventListener("change", () => {
    selectScenario(dom.scenarioSelect.value);
  });
  dom.roleSelect.addEventListener("change", () => {
    state.selectedRole = dom.roleSelect.value;
    syncSeedOptions();
    loadSelectedReplay();
  });
  dom.seedSelect.addEventListener("change", () => {
    state.selectedSeed = Number.parseInt(dom.seedSelect.value, 10) || 0;
    loadSelectedReplay();
  });
  dom.projectionSelect.addEventListener("change", () => {
    state.selectedProjection = dom.projectionSelect.value;
    renderScene();
    pushQueryState();
  });
  dom.reloadButton.addEventListener("click", reloadCurrentScenario);
  dom.playButton.addEventListener("click", togglePlayback);
  dom.stepBackButton.addEventListener("click", () => stepFrame(-1));
  dom.stepForwardButton.addEventListener("click", () => stepFrame(1));
  dom.slowerButton.addEventListener("click", () => adjustSpeed(-0.5));
  dom.fasterButton.addEventListener("click", () => adjustSpeed(0.5));
  dom.frameSlider.addEventListener("input", () => {
    setFrameIndex(Number.parseInt(dom.frameSlider.value, 10) || 0);
  });

  dom.baselineRoleButton.addEventListener("click", () => selectReplayRole("baseline"));
  dom.candidateRoleButton.addEventListener("click", () => selectReplayRole("candidate"));
  dom.newProjectButton.addEventListener("click", openNewProjectDialog);
  dom.closeProjectDialog.addEventListener("click", () => dom.newProjectDialog.close());
  dom.cancelProjectDialog.addEventListener("click", () => dom.newProjectDialog.close());
  dom.newProjectForm.addEventListener("submit", createWorkbenchProject);
  dom.agentMessageForm.addEventListener("submit", submitAgentMessage);
  dom.jumpEvidenceButton.addEventListener("click", jumpToEvidenceFrame);
  document.querySelectorAll("[data-intervention]").forEach((button) => {
    button.addEventListener("click", () => {
      const action = button.getAttribute("data-intervention");
      if (!action) {
        return;
      }
      const value = button.getAttribute("data-value");
      if (!value && ["change_method", "adjust_budget"].includes(action)) {
        beginStructuredIntervention(action);
        return;
      }
      submitIntervention(action, {
        value: value || undefined,
      });
    });
  });

  window.addEventListener("keydown", (event) => {
    if (event.target instanceof HTMLInputElement || event.target instanceof HTMLSelectElement) {
      return;
    }
    if (event.code === "Space") {
      event.preventDefault();
      togglePlayback();
      return;
    }
    if (event.code === "ArrowLeft") {
      event.preventDefault();
      stepFrame(-1);
      return;
    }
    if (event.code === "ArrowRight") {
      event.preventDefault();
      stepFrame(1);
      return;
    }
    if (event.key === "[") {
      adjustSpeed(-0.5);
      return;
    }
    if (event.key === "]") {
      adjustSpeed(0.5);
    }
  });

  window.addEventListener("resize", () => {
    renderer.resize();
    renderMetricChart();
  });
  window.addEventListener("popstate", () => {
    applyQueryState();
  });
}

async function loadScenarioCatalog() {
  const epoch = ++state.requestEpoch;
  try {
    const response = await fetchJson(`${API_ROOT}/projects`);
    if (epoch !== state.requestEpoch) {
      return;
    }
    const scenarios = normalizeScenarioList(response);
    state.scenarios = scenarios;
    state.scenarioIndex = new Map(scenarios.map((scenario) => [scenario.scenario_id, scenario]));
    state.useDemo = false;
    setConnectionState("good", "实验已连接");
    if (!state.selectedScenarioId || !state.scenarioIndex.has(state.selectedScenarioId)) {
      const preferred = getQueryParam("scenario");
      const nextScenario =
        (preferred && state.scenarioIndex.has(preferred) && preferred) ||
        scenarios.find((scenario) => scenario.scenario_id === "S47")?.scenario_id ||
        scenarios.find((scenario) => scenario.metadata?.attention)?.scenario_id ||
        scenarios[0]?.scenario_id ||
        null;
      state.selectedScenarioId = nextScenario;
    }
    renderScenarioCatalog();
    if (state.selectedScenarioId) {
      await loadScenarioBundle(state.selectedScenarioId);
    } else {
      bootstrapDemo("No scenarios returned by API.");
    }
  } catch (error) {
    console.warn("Scenario catalog fetch failed", error);
    state.useDemo = true;
    setConnectionState("warn", "实验数据不可用");
    bootstrapDemo("API unreachable. Rendering demo telemetry.");
  }
}

async function loadScenarioBundle(scenarioId) {
  if (!scenarioId) {
    return;
  }
  state.selectedScenarioId = scenarioId;
  pushQueryState();
  const epoch = ++state.requestEpoch;
  setLoading(true, "载入项目");
  clearWarnings();
  try {
    const projectResponse = await fetchJson(
      `${API_ROOT}/projects/${encodeURIComponent(scenarioId)}`
    );
    if (epoch !== state.requestEpoch) {
      return;
    }
    state.currentProject = projectResponse;
    if (projectResponse.source_kind === "local") {
      state.selectedScenario = normalizeScenarioDetail(projectResponse, scenarioId);
      state.visualization = createEmptyVisualization();
      state.replays = [];
      state.replayBundle = null;
      state.frameWindow = [];
      state.totalFrames = 0;
      state.currentFrameIndex = 0;
      state.layers = new Map();
      state.layerMeta = [];
      state.error = "";
      dom.emptyProjectPanel.hidden = false;
      renderScenarioCatalog();
      renderScenarioContext();
      renderProjectSurface();
      syncFrameSlider();
      renderScene();
      setLoading(false);
      return;
    }
    const [detailResponse, visualizationResponse, replayResponse] = await Promise.all([
      fetchJson(`${API_ROOT}/scenarios/${encodeURIComponent(scenarioId)}`),
      fetchJson(`${API_ROOT}/scenarios/${encodeURIComponent(scenarioId)}/visualization`),
      fetchJson(`${API_ROOT}/scenarios/${encodeURIComponent(scenarioId)}/replays`),
    ]);
    if (epoch !== state.requestEpoch) {
      return;
    }
    state.selectedScenario = normalizeScenarioDetail(detailResponse, scenarioId);
    state.visualization = normalizeVisualization(visualizationResponse);
    state.replays = normalizeReplayList(replayResponse);
    dom.emptyProjectPanel.hidden = true;
    syncSelectionFromQuery();
    syncLayerState();
    renderScenarioCatalog();
    renderScenarioContext();
    renderProjectSurface();
    syncRoleOptions();
    syncSeedOptions();
    await loadSelectedReplay();
    renderProjectSurface();
    state.error = "";
    setLoading(false);
  } catch (error) {
    if (epoch !== state.requestEpoch) {
      return;
    }
    console.warn("Scenario bundle fetch failed", error);
    setLoading(false, "项目载入失败");
    showError(error.message);
  }
}

async function reloadCurrentScenario() {
  if (!state.selectedScenarioId) {
    bootstrapDemo("No live scenario selected; demo fallback refreshed.");
    return;
  }
  await loadScenarioBundle(state.selectedScenarioId);
}

async function loadSelectedReplay() {
  const scenarioId = state.selectedScenarioId;
  if (!scenarioId) {
    return;
  }
  const replay = resolveReplay(state.selectedRole, state.selectedSeed);
  if (!replay) {
    return;
  }
  const epoch = ++state.requestEpoch;
  setLoading(true, `Loading replay ${replay.policy_role || replay.role || state.selectedRole}`);
  try {
    const response = await loadReplayFrames(scenarioId, replay);
    if (epoch !== state.requestEpoch) {
      return;
    }
    applyReplayResponse(response, replay);
    setFrameIndex(Math.floor(Math.max(state.frameWindow.length - 1, 0) / 2));
    setConnectionState("good", "Replay loaded");
    state.error = "";
  } catch (error) {
    console.warn("Replay fetch failed", error);
    state.error = error.message;
    setConnectionState("bad", `Replay load failed: ${error.message}`);
    if (!state.useDemo) {
      bootstrapDemo(`Replay fetch failed: ${error.message}`);
      return;
    }
  } finally {
    setLoading(false, state.useDemo ? "Demo active" : "Replay ready");
  }
}

async function loadReplayFrames(scenarioId, replay) {
  const role = encodeURIComponent(replay.policy_role || replay.role || state.selectedRole);
  const seed = Number.parseInt(replay.seed ?? state.selectedSeed, 10) || 0;
  const expected = Number.parseInt(replay.frame_count ?? replay.frames ?? 0, 10) || 0;
  const total = expected > 0 ? expected : DEFAULT_FRAME_LIMIT;
  const frames = [];
  let start = 0;
  let fetched = 0;
  let firstBundleResponse = null;
  while (start < total || (total === DEFAULT_FRAME_LIMIT && start === 0)) {
    const limit = Math.min(DEFAULT_FRAME_LIMIT, Math.max(total - start, DEFAULT_FRAME_LIMIT));
    const page = await fetchJson(
      `${API_ROOT}/scenarios/${encodeURIComponent(scenarioId)}/frames?role=${role}&seed=${seed}&start=${start}&limit=${limit}`
    );
    if (!firstBundleResponse) {
      firstBundleResponse = page;
    }
    const items = normalizeFramePage(page);
    if (!items.length) {
      break;
    }
    frames.push(...items);
    fetched += items.length;
    if (items.length < limit) {
      break;
    }
    start += items.length;
    if (expected > 0 && fetched >= expected) {
      break;
    }
    if (expected === 0 && fetched >= DEFAULT_FRAME_LIMIT) {
      break;
    }
  }
  const firstBundle = normalizeReplayBundle(firstBundleResponse || { frames }, scenarioId);
  return {
    frames,
    total: Number.parseInt(firstBundle.total ?? expected ?? frames.length, 10) || frames.length,
    events: firstBundle.events,
    metrics: firstBundle.metrics,
    disclosures: firstBundle.disclosures,
    replay,
    raw: firstBundle.raw,
  };
}

function applyReplayResponse(response, replay) {
  state.frameWindow = Array.isArray(response.frames) ? response.frames : [];
  state.frameWindowStart = 0;
  state.replayBundle = response;
  state.totalFrames = Math.max(response.total || response.expectedFrameCount || 0, state.frameWindow.length);
  if (state.totalFrames === 0) {
    state.totalFrames = state.frameWindow.length;
  }
  const label = replayLabel(replay);
  dom.canvasTitle.textContent = label;
  dom.canvasSubtitle.textContent = describeReplay(replay);
  state.currentFrameIndex = Math.min(state.currentFrameIndex, Math.max(state.totalFrames - 1, 0));
  syncFrameSlider();
  rebuildLayerState();
  renderScene();
  renderPanels();
}

function bootstrapDemo(message) {
  state.useDemo = true;
  state.selectedScenario = createDemoScenario();
  state.selectedScenarioId = state.selectedScenario.scenario_id;
  state.visualization = createDemoVisualization();
  state.replays = createDemoReplays();
  state.scenarios = [state.selectedScenario];
  state.scenarioIndex = new Map([[state.selectedScenario.scenario_id, state.selectedScenario]]);
  state.selectedRole = "candidate";
  state.selectedSeed = 0;
  state.selectedProjection = "3d";
  state.frameWindow = createDemoFrames();
  state.frameWindowStart = 0;
  state.totalFrames = state.frameWindow.length;
  state.currentFrameIndex = 0;
  state.replayBundle = {
    total: state.totalFrames,
    events: [],
    metrics: {},
    disclosures: [],
    raw: {},
  };
  state.layers = new Map(
    state.visualization.dynamic_layers.map((layer) => [layer.id, layer.enabled_by_default !== false])
  );
  state.layerMeta = buildLayerMeta(state.visualization);
  dom.projectionSelect.value = "3d";
  syncRoleOptions();
  syncSeedOptions();
  syncLayerState();
  setConnectionState("warn", message || "Demo mode");
  renderScenarioCatalog();
  renderScenarioContext();
  renderPanels();
  syncFrameSlider();
  renderScene();
  pushQueryState();
}

function createDemoScenario() {
  return {
    scenario_id: FALLBACK_SCENARIO_ID,
    task_family: "telemetry_demo",
    name: "Telemetry corridor demo",
    summary: "Synthetic live-replay sample for offline inspection.",
    disclosures: ["Demo mode uses synthetic data when the API is unavailable."],
    capabilities: { entities: true, trajectories: true, relations: true, fields: true },
    agents: ["alpha", "beta", "gamma"],
    observation_spaces: {},
    action_spaces: {},
  };
}

function createEmptyVisualization() {
  return {
    schema_version: "scenario_visualization/v1",
    world: {
      dimension: 2,
      bounds: { minimum: [-1, -1], maximum: [1, 1] },
      units: "abstract",
      axis_labels: ["x", "y"],
    },
    static_primitives: [],
    dynamic_layers: [],
    views: [{ id: "empty", projection: "2d", layer_ids: [], camera: {} }],
    disclosures: [],
  };
}

function createDemoVisualization() {
  return {
    schema_version: "visualization/v1",
    world: {
      dimension: 3,
      coordinate_system: "normalized",
      bounds: {
        minimum: [-1.6, -1.1, -0.9],
        maximum: [1.6, 1.1, 0.9],
      },
      units: {
        length: "normalized",
        time: "second",
      },
      axis_labels: ["x", "y", "z"],
    },
    static_primitives: [
      {
        id: "perimeter",
        kind: "ring",
        center: [0, 0, 0],
        radius: 1.25,
        points: [],
        style: { stroke: "#56d6e6", alpha: 0.38 },
        metadata: { role: "boundary" },
      },
      {
        id: "gate",
        kind: "polyline",
        points: [[-1.2, -0.7, 0], [1.2, -0.7, 0]],
        style: { stroke: "#efb15c", alpha: 0.55 },
        metadata: { role: "gate" },
      },
    ],
    dynamic_layers: [
      { id: "entities", kind: "entity_markers", source: "entities", attribute: "entity", enabled_by_default: true },
      { id: "targets", kind: "goal_markers", source: "entity_goals", attribute: "goal", enabled_by_default: true },
      { id: "relations", kind: "relations", source: "relations", attribute: "links", enabled_by_default: true },
      { id: "trajectories", kind: "trajectories", source: "trajectories", attribute: "history", enabled_by_default: true },
      { id: "fields", kind: "vector_fields", source: "fields", attribute: "field", enabled_by_default: true },
      { id: "events", kind: "events", source: "events", attribute: "timeline", enabled_by_default: true },
    ],
    views: [
      {
        id: "default",
        projection: "3d",
        layer_ids: ["entities", "targets", "relations", "trajectories", "fields", "events"],
        camera: { yaw: 35, pitch: 28 },
      },
    ],
    timeline_event_types: ["entity_spawned", "target_reached", "capture", "episode_terminated"],
    disclosures: ["Synthetic offline demo data", "No write APIs are available in the viewer"],
  };
}

function createDemoReplays() {
  return [
    { policy_role: "baseline", seed: 0, frame_count: 14, duration: 7.2, policy_id: "demo.baseline" },
    { policy_role: "candidate", seed: 0, frame_count: 14, duration: 7.2, policy_id: "demo.candidate" },
  ];
}

function createDemoFrames() {
  const frames = [];
  const positions = [
    [-1.1, -0.45, -0.18],
    [-0.2, 0.45, 0.02],
    [0.65, -0.18, 0.14],
  ];
  const goals = [
    [1.05, 0.55, 0.26],
    [1.18, -0.36, 0.16],
    [1.14, 0.25, -0.04],
  ];
  for (let step = 0; step < 14; step += 1) {
    const tick = step / 13;
    const entities = positions.map((base, index) => ({
      id: `agent_${index + 1}`,
      position: [
        base[0] + tick * (goals[index][0] - base[0]) * 0.78,
        base[1] + Math.sin(tick * Math.PI + index * 0.45) * 0.14,
        base[2] + tick * (goals[index][2] - base[2]) * 0.48,
      ],
      velocity: [0.18 + tick * 0.04, 0.12 - tick * 0.03, 0.04],
      goal: goals[index],
      team: index === 0 ? "red" : "blue",
      role: index === 0 ? "navigator" : index === 1 ? "escort" : "interceptor",
      active: true,
    }));
    frames.push({
      schema_version: "scenario_replay/v1",
      scenario_time: Number((step * 0.55).toFixed(2)),
      episode_step: step,
      entities,
      relations: [
        { kind: "communication_neighbor", source: "agent_1", target: "agent_2", mode: "perfect" },
        { kind: "communication_neighbor", source: "agent_2", target: "agent_3", mode: "perfect" },
      ],
      fields: [
        { kind: "vector_field", vector: [0.04 + tick * 0.01, 0.025 - tick * 0.008, 0] },
      ],
      observations: {},
      actions: {},
      messages: step % 3 === 0 ? [{ sender: "agent_1", receiver: "agent_2", age_steps: 0 }] : [],
      events:
        step === 0
          ? [
              { event_type: "entity_spawned", step: 0, time: 0, participants: ["agent_1"], attributes: { role: "navigator" } },
              { event_type: "entity_spawned", step: 0, time: 0, participants: ["agent_2"], attributes: { role: "escort" } },
              { event_type: "entity_spawned", step: 0, time: 0, participants: ["agent_3"], attributes: { role: "interceptor" } },
            ]
          : step === 9
          ? [
              { event_type: "target_reached", step, time: step * 0.55, participants: ["agent_1"], attributes: { mean_distance: 0.13 } },
            ]
          : [],
      rewards: { agent_1: 0.02 + tick * 0.02, agent_2: 0.018 + tick * 0.018, agent_3: 0.015 + tick * 0.015 },
      metrics: {
        primary_metric: "task_success_rate",
        primary_value: step >= 9 ? 1 : tick * 0.92,
        task_success_rate: step >= 9 ? 1 : tick * 0.92,
        collision_rate: 0,
        out_of_bounds_rate: 0,
        action_violation_rate: 0,
        communication_delivery_rate: 1,
        message_drop_rate: 0,
        episode_length: step,
        task_progress: step >= 9 ? 1 : tick * 0.92,
      },
    });
  }
  return frames;
}

function normalizeScenarioList(response) {
  const items = extractArray(response, ["projects", "scenarios", "items", "data"]);
  if (!items.length && response && typeof response === "object" && response.scenario_id) {
    return [normalizeScenarioDetail(response, response.scenario_id)];
  }
  return items.map((item, index) =>
    normalizeScenarioDetail(item, item?.project_id || item?.scenario_id || `PROJECT-${index + 1}`)
  );
}

function normalizeScenarioDetail(item, fallbackId) {
  const scenario = item && typeof item === "object" ? item : {};
  const id = String(scenario.project_id || scenario.scenario_id || scenario.id || fallbackId || FALLBACK_SCENARIO_ID);
  return {
    scenario_id: id,
    task_family: String(scenario.task_family || scenario.family || scenario.kind || "unknown"),
    name: String(scenario.title || scenario.name || id),
    summary: String(scenario.summary || scenario.description || ""),
    disclosures: normalizeStringList(scenario.disclosures),
    capabilities: scenario.capabilities && typeof scenario.capabilities === "object" ? scenario.capabilities : {},
    agents: normalizeStringList(scenario.agents),
    observation_spaces: scenario.observation_spaces && typeof scenario.observation_spaces === "object" ? scenario.observation_spaces : {},
    action_spaces: scenario.action_spaces && typeof scenario.action_spaces === "object" ? scenario.action_spaces : {},
    metadata: scenario,
  };
}

function normalizeVisualization(response) {
  const source = response && typeof response === "object" ? response : {};
  const world = source.world && typeof source.world === "object" ? source.world : {};
  const staticPrimitives = extractArray(source, ["static_primitives", "static", "primitives"]).map((item, index) =>
    normalizePrimitive(item, index)
  );
  const dynamicLayers = extractArray(source, ["dynamic_layers", "layers"]).map((item, index) =>
    normalizeLayer(item, index)
  );
  const views = extractArray(source, ["views"]).map((item, index) => normalizeView(item, index));
  const bounds = normalizeWorldBounds(world.bounds || source.bounds, world.bounds_min || source.bounds_min, world.bounds_max || source.bounds_max);
  return {
    schema_version: String(source.schema_version || "visualization/v1"),
    world: {
      dimension: clampInteger(world.dimension ?? source.dimension ?? 2, 2, 3),
      coordinate_system: String(world.coordinate_system || source.coordinate_system || "normalized"),
      bounds,
      bounds_min: bounds.minimum,
      bounds_max: bounds.maximum,
      units: normalizeUnits(world.units || source.units),
      axis_labels: normalizeStringList(world.axis_labels || source.axis_labels),
      length_unit: String(world.length_unit || world.units?.length || source.length_unit || "normalized"),
      time_unit: String(world.time_unit || world.units?.time || source.time_unit || "second"),
    },
    static_primitives: staticPrimitives,
    dynamic_layers: dynamicLayers,
    views,
    timeline_event_types: normalizeStringList(source.timeline_event_types),
    disclosures: normalizeStringList(source.disclosures),
    raw: source,
  };
}

function normalizePrimitive(item, index) {
  const primitive = item && typeof item === "object" ? item : {};
  const geometry = primitive.geometry && typeof primitive.geometry === "object" ? primitive.geometry : {};
  return {
    primitive_id: String(primitive.primitive_id || primitive.id || `primitive-${index + 1}`),
    kind: String(primitive.kind || primitive.type || "unknown"),
    points: normalizePointList(primitive.points || geometry.points || []),
    center: normalizePointTuple(primitive.center || geometry.center || null),
    radius: Number.parseFloat(primitive.radius ?? geometry.radius ?? 0) || 0,
    geometry,
    semantic_tags: normalizeStringList(primitive.semantic_tags),
    style: primitive.style && typeof primitive.style === "object" ? primitive.style : {},
    metadata: primitive.metadata && typeof primitive.metadata === "object" ? primitive.metadata : {},
  };
}

function normalizeLayer(item, index) {
  const layer = item && typeof item === "object" ? item : {};
  const source = String(layer.source || layer.layer_source || layer.kind || "unknown");
  const id = String(layer.layer_id || layer.id || source || `layer-${index + 1}`);
  return {
    layer_id: id,
    id,
    kind: String(layer.kind || layer.layer_type || layer.type || "dynamic"),
    layer_type: String(layer.layer_type || layer.type || layer.kind || "dynamic"),
    source: normalizeLayerSource(source, layer.kind),
    attribute: String(layer.attribute || ""),
    enabled_by_default: layer.enabled_by_default !== false,
    visible: layer.enabled_by_default !== false && layer.visible !== false,
    style: layer.style && typeof layer.style === "object" ? layer.style : {},
    metadata: layer.metadata && typeof layer.metadata === "object" ? layer.metadata : {},
  };
}

function normalizeView(item, index) {
  const view = item && typeof item === "object" ? item : {};
  return {
    view_id: String(view.view_id || view.id || `view-${index + 1}`),
    id: String(view.id || view.view_id || `view-${index + 1}`),
    camera: view.camera && typeof view.camera === "object" ? normalizeCamera(view.camera) : normalizeCamera({ kind: view.camera }),
    projection: view.projection === "2d" || view.projection === "3d" ? view.projection : "3d",
    layers: normalizeStringList(view.layers || view.layer_ids),
    layer_ids: normalizeStringList(view.layer_ids || view.layers),
    camera_config: view.camera_config && typeof view.camera_config === "object" ? view.camera_config : {},
  };
}

function normalizeReplayList(response) {
  const items = extractArray(response, ["replays", "items", "data"]);
  return items.map((item, index) => ({
    policy_role: String(item.policy_role || item.role || item.policy || "candidate"),
    seed: Number.parseInt(item.seed ?? 0, 10) || 0,
    frame_count: Number.parseInt(item.frame_count ?? item.frames ?? item.frameCount ?? 0, 10) || 0,
    duration: Number.parseFloat(item.duration ?? item.seconds ?? 0) || 0,
    path: String(item.path || ""),
    policy_id: String(item.policy_id || item.id || `policy-${index + 1}`),
    raw: item,
  }));
}

function normalizeFramePage(response) {
  if (Array.isArray(response)) {
    return response.map(normalizeFrame);
  }
  const items = extractArray(response, ["frames", "items", "data"]);
  if (items.length) {
    return items.map(normalizeFrame);
  }
  if (response && typeof response === "object" && response.episode_step !== undefined) {
    return [normalizeFrame(response)];
  }
  return [];
}

function normalizeReplayBundle(response, fallbackScenarioId) {
  const source = response && typeof response === "object" ? response : {};
  const frames = normalizeFramePage(source);
  return {
    scenario_id: String(source.scenario_id || fallbackScenarioId || FALLBACK_SCENARIO_ID),
    frames,
    total: Number.parseInt(source.total ?? source.frame_count ?? source.frameCount ?? frames.length, 10) || frames.length,
    events: normalizeFrameEvents(source.events),
    metrics: source.metrics && typeof source.metrics === "object" ? source.metrics : {},
    disclosures: normalizeStringList(source.disclosures),
    raw: source,
  };
}

function normalizeFrame(frame) {
  const item = frame && typeof frame === "object" ? frame : {};
  return {
    schema_version: String(item.schema_version || "scenario_replay/v1"),
    scenario_time: Number.parseFloat(item.scenario_time ?? item.time ?? 0) || 0,
    episode_step: Number.parseInt(item.episode_step ?? item.step ?? 0, 10) || 0,
    entities: normalizeFrameEntities(item.entities),
    relations: normalizeFrameRelations(item.relations),
    fields: normalizeFrameFields(item.fields),
    observations: item.observations && typeof item.observations === "object" ? item.observations : {},
    actions: item.actions && typeof item.actions === "object" ? item.actions : {},
    messages: normalizeFrameMessages(item.messages),
    events: normalizeFrameEvents(item.events),
    rewards: item.rewards && typeof item.rewards === "object" ? item.rewards : {},
    metrics: item.metrics && typeof item.metrics === "object" ? item.metrics : {},
    raw: item,
  };
}

function normalizeFrameEntities(items) {
  return normalizeArray(items).map((item, index) => ({
    id: String(item.id || item.entity_id || `entity-${index + 1}`),
    position: normalizeNumericTuple(item.position || item.pos || item.xyz, 3, 0),
    velocity: normalizeNumericTuple(item.velocity || item.vel || [0, 0, 0], 3, 0),
    goal: normalizeNumericTuple(item.goal || item.target || null, 3, 0),
    team: String(item.team || "shared"),
    role: String(item.role || "agent"),
    active: item.active !== false,
    raw: item,
  }));
}

function normalizeFrameRelations(items) {
  return normalizeArray(items).map((item) => ({
    kind: String(item.kind || "relation"),
    source: String(item.source || item.from || ""),
    target: String(item.target || item.to || ""),
    mode: String(item.mode || ""),
    raw: item,
  }));
}

function normalizeFrameFields(items) {
  return normalizeArray(items).map((item) => ({
    kind: String(item.kind || "field"),
    vector: normalizeNumericTuple(item.vector || item.value || [0, 0, 0], 3, 0),
    raw: item,
  }));
}

function normalizeFrameMessages(items) {
  return normalizeArray(items).map((item) => ({
    sender: String(item.sender || ""),
    receiver: String(item.receiver || ""),
    age_steps: Number.parseFloat(item.age_steps ?? item.age ?? 0) || 0,
    raw: item,
  }));
}

function normalizeFrameEvents(items) {
  return normalizeArray(items).map((item) => ({
    event_type: String(item.event_type || item.type || "event"),
    step: Number.parseInt(item.step ?? 0, 10) || 0,
    time: Number.parseFloat(item.time ?? 0) || 0,
    participants: normalizeStringList(item.participants),
    attributes: item.attributes && typeof item.attributes === "object" ? item.attributes : {},
    raw: item,
  }));
}

function syncLayerState() {
  if (!state.visualization) {
    return;
  }
  const selectedView = state.visualization.views[0] || null;
  const viewLayerIds = selectedView ? new Set(selectedView.layer_ids || selectedView.layers || []) : null;
  state.layers = new Map();
  state.layerMeta = buildLayerMeta(state.visualization, viewLayerIds);
  for (const meta of state.layerMeta) {
    state.layers.set(meta.layerId, meta.visible);
  }
  if (selectedView) {
    const preferred = selectedView.projection === "2d" ? "2d" : "3d";
    if (!state.useDemo) {
      state.selectedProjection = preferred;
      dom.projectionSelect.value = preferred;
    }
  }
}

function buildLayerMeta(visualization, viewLayerIds = null) {
  const raw = [];
  const dynamicLayers = visualization?.dynamic_layers || [];
  for (const layer of dynamicLayers) {
    const source = normalizeLayerSource(layer.source || layer.kind, layer.kind);
    const layerId = layer.layer_id || layer.id || source;
    const declaredByView = viewLayerIds === null || viewLayerIds.has(layerId);
    const visible = declaredByView && layer.enabled_by_default !== false && layer.visible !== false;
    raw.push({
      layerId,
      layerIdDisplay: layerId,
      label: sourceToLabel(source),
      source,
      layerType: layer.layer_type || layer.kind || "dynamic",
      visible,
      known: RECOGNIZED_LAYER_SOURCES.has(source),
      style: layer.style || {},
      attribute: layer.attribute || "",
      description: layerDescription(source, layer.layer_type || layer.kind, layer.attribute || ""),
    });
  }
  const staticPrimitives = visualization?.static_primitives || [];
  if (staticPrimitives.length) {
    const visible =
      viewLayerIds === null ||
      staticPrimitives.some((primitive) => viewLayerIds.has(primitive.primitive_id || primitive.id));
    raw.push({
      layerId: "static_primitives",
      layerIdDisplay: "static_primitives",
      label: sourceToLabel("static_primitives"),
      source: "static_primitives",
      layerType: "static_primitives",
      visible,
      known: true,
      style: {},
      description: layerDescription("static_primitives", "static_primitives"),
    });
  }
  return raw;
}

function rebuildLayerState() {
  if (!state.layerMeta.length) {
    state.layerMeta = buildLayerMeta(state.visualization);
  }
  for (const meta of state.layerMeta) {
    if (!state.layers.has(meta.layerId)) {
      state.layers.set(meta.layerId, meta.visible);
    }
  }
  renderLayerControls();
}

function renderScenarioCatalog() {
  const term = String(dom.scenarioFilter.value || "").trim().toLowerCase();
  const filtered = state.scenarios.filter((scenario) => {
    if (!term) {
      return true;
    }
    return (
      scenario.scenario_id.toLowerCase().includes(term) ||
      scenario.name.toLowerCase().includes(term) ||
      scenario.task_family.toLowerCase().includes(term)
    );
  });
  dom.projectCount.textContent = String(state.scenarios.length);
  dom.suiteProjectCount.textContent = String(
    state.scenarios.filter((scenario) => scenario.metadata?.source_kind === "scenario").length
  );
  dom.scenarioSelect.innerHTML = filtered
    .map(
      (scenario) =>
        `<option value="${escapeHtml(scenario.scenario_id)}"${scenario.scenario_id === state.selectedScenarioId ? " selected" : ""}>${escapeHtml(
          scenario.scenario_id
        )} / ${escapeHtml(scenario.name)}</option>`
    )
    .join("");
  dom.scenarioList.innerHTML = filtered.length
    ? filtered
        .map((scenario) => {
          const active = scenario.scenario_id === state.selectedScenarioId;
          const metadata = scenario.metadata || {};
          const attention = metadata.attention === true || metadata.status === "attention";
          const secondary =
            metadata.source_kind === "local"
              ? "新建项目"
              : metadata.task_family || scenario.task_family || "实验项目";
          return `
            <button class="scenario-item" type="button" data-active="${active}" data-scenario-id="${escapeHtml(
              scenario.scenario_id
            )}">
              <span class="scenario-id">${escapeHtml(scenario.scenario_id)}</span>
              <span class="scenario-name">${escapeHtml(scenario.name)}</span>
              <span class="scenario-family">${escapeHtml(secondary)}</span>
              ${attention ? '<span class="attention-dot" title="需要关注"></span>' : ""}
            </button>
          `;
        })
        .join("")
    : `<div class="warning-item">没有匹配的项目</div>`;
  dom.scenarioList.querySelectorAll(".scenario-item").forEach((button) => {
    button.addEventListener("click", () => {
      const scenarioId = button.getAttribute("data-scenario-id");
      if (scenarioId) {
        selectScenario(scenarioId);
      }
    });
  });
}

async function selectScenario(scenarioId) {
  if (!scenarioId || scenarioId === state.selectedScenarioId) {
    return;
  }
  state.selectedScenarioId = scenarioId;
  syncSelectionFromScenario();
  pushQueryState();
  await loadScenarioBundle(scenarioId);
}

async function createWorkbenchProject(event) {
  event.preventDefault();
  clearProjectDialogError();
  const title = dom.newProjectTitle.value.trim();
  const goal = dom.newProjectGoal.value.trim();
  if (!title || !goal) {
    return;
  }
  const submitButton = dom.newProjectForm.querySelector('button[type="submit"]');
  submitButton.disabled = true;
  try {
    const project = await postJson(`${API_ROOT}/projects`, { title, goal });
    dom.newProjectDialog.close();
    dom.newProjectForm.reset();
    state.selectedScenarioId = project.project_id;
    await loadScenarioCatalog();
    showActionFeedback("项目已创建，Agent 将按自主流程推进");
  } catch (error) {
    showProjectDialogError(error.message);
  } finally {
    if (dom.newProjectError.dataset.visible !== "true") {
      submitButton.disabled = false;
    }
  }
}

async function openNewProjectDialog() {
  clearProjectDialogError();
  dom.newProjectSubmit.disabled = true;
  dom.newProjectDialog.showModal();
  try {
    const health = await fetchJson("/health");
    const agent = health.agent || {};
    if (!agent.ready) {
      showProjectDialogError(agent.message || "Agent 未配置，无法启动项目");
      return;
    }
    dom.newProjectSubmit.disabled = false;
  } catch (error) {
    showProjectDialogError(`无法检查 Agent 状态：${error.message}`);
  }
}

function showProjectDialogError(message) {
  dom.newProjectError.textContent = message;
  dom.newProjectError.dataset.visible = "true";
  dom.newProjectSubmit.disabled = true;
}

function clearProjectDialogError() {
  dom.newProjectError.textContent = "";
  dom.newProjectError.dataset.visible = "false";
}

async function submitAgentMessage(event) {
  event.preventDefault();
  const message = dom.agentMessageInput.value.trim();
  if (!message) {
    return;
  }
  const pendingAction = dom.agentMessageForm.dataset.pendingIntervention;
  dom.agentMessageInput.value = "";
  delete dom.agentMessageForm.dataset.pendingIntervention;
  dom.agentMessageInput.placeholder = "告诉 Agent 要改变什么…";
  await submitIntervention(pendingAction || "message", {
    [pendingAction ? "request" : "message"]: message,
  });
}

function beginStructuredIntervention(action) {
  dom.agentMessageForm.dataset.pendingIntervention = action;
  dom.agentMessageInput.placeholder =
    action === "change_method"
      ? "输入希望采用的方法、处理方式或冻结项…"
      : "输入预算、trial、seed 或训练步数…";
  dom.agentMessageInput.focus();
}

async function submitIntervention(action, payload = {}) {
  const projectId = state.currentProject?.project_id || state.selectedScenarioId;
  if (!projectId) {
    showActionFeedback("请先选择项目", true);
    return;
  }
  try {
    const response = await postJson(
      `${API_ROOT}/projects/${encodeURIComponent(projectId)}/interventions`,
      { action, payload }
    );
    if (state.currentProject) {
      const events = Array.isArray(state.currentProject.events)
        ? state.currentProject.events
        : [];
      events.push(response.event);
      state.currentProject.events = events;
      renderProjectStatus(state.currentProject);
    }
    showActionFeedback(interventionFeedback(action, payload));
  } catch (error) {
    showActionFeedback(error.message, true);
  }
}

function interventionFeedback(action, payload) {
  const labels = {
    change_method: "方法覆盖请求已记录",
    adjust_budget: "预算调整请求已记录",
    pause: "已暂停后续执行",
    resume: "已恢复自主执行",
    stop: "已停止后续执行",
    message: "指令已写入项目事件",
    rerun: "重新运行请求已记录",
  };
  return labels[action] || "干预已记录";
}

function showActionFeedback(message, isError = false) {
  dom.actionFeedback.textContent = message;
  dom.actionFeedback.dataset.visible = "true";
  dom.actionFeedback.dataset.tone = isError ? "bad" : "good";
  window.clearTimeout(showActionFeedback.timeoutId);
  showActionFeedback.timeoutId = window.setTimeout(() => {
    dom.actionFeedback.dataset.visible = "false";
  }, 4000);
}

async function jumpToEvidenceFrame() {
  const evidence = state.currentProject?.constraint_evidence?.[0];
  if (!evidence) {
    return;
  }
  if (Number.isInteger(evidence.seed)) {
    state.selectedSeed = evidence.seed;
  }
  await selectReplayRole("candidate");
  const metric = evidence.metric;
  const frameIndex = state.frameWindow.findIndex((frame) => {
    const value = frame?.metrics?.[metric];
    return typeof value === "number" && value > Number(evidence.limit || 0);
  });
  setFrameIndex(frameIndex >= 0 ? frameIndex : Math.max(state.totalFrames - 1, 0));
}

function syncSelectionFromScenario() {
  const scenario = state.scenarioIndex.get(state.selectedScenarioId);
  if (scenario) {
    state.selectedScenario = scenario;
  }
}

function renderScenarioContext() {
  const scenario = state.selectedScenario || state.scenarioIndex.get(state.selectedScenarioId) || createDemoScenario();
  const visualization = state.visualization || createDemoVisualization();
  const world = visualization.world || {};
  const labels = [];
  labels.push(`${scenario.scenario_id}`);
  if (scenario.name && scenario.name !== scenario.scenario_id) {
    labels.push(scenario.name);
  }
  dom.scenarioStatus.textContent = labels.join(" / ");
  dom.canvasTitle.textContent = scenario.name || scenario.scenario_id;
  dom.canvasSubtitle.textContent = [
    scenario.task_family,
    `${world.dimension}D world`,
    `${visualization.dynamic_layers.length} layers`,
  ].join(" / ");
  dom.agentCount.textContent = String(scenario.agents?.length || 0);
  dom.dimensionLabel.textContent = String(world.dimension || 2);
}

function renderProjectSurface() {
  const project = state.currentProject;
  if (!project) {
    return;
  }
  dom.projectTitle.textContent = project.title || project.name || project.project_id;
  renderWorkflow(project.workflow || []);
  renderProjectStatus(project);
  renderComparison(project);
  renderConstraints(project);
  const method = project.method || {};
  dom.currentMethod.textContent = formatMethod(method);
  if (project.source_kind === "local") {
    const emptyTitle = dom.emptyProjectPanel.querySelector("strong");
    const emptyText = dom.emptyProjectPanel.querySelector("span");
    const latestActivity = Array.isArray(project.agent_activity)
      ? project.agent_activity.at(-1)
      : null;
    if (project.status === "error") {
      emptyTitle.textContent = "Agent 执行失败";
      emptyText.textContent = project.error || "查看项目事件了解失败原因。";
    } else if (project.status === "paused") {
      emptyTitle.textContent = "Agent 已暂停";
      emptyText.textContent = describeAgentActivity(latestActivity) || "可继续运行或发送新指令。";
    } else if (project.status === "stopped") {
      emptyTitle.textContent = "Agent 已停止";
      emptyText.textContent = project.agent_summary || "可继续运行或创建新项目。";
    } else if (project.status === "complete") {
      emptyTitle.textContent = objectiveStatusLabel(project.outcome);
      emptyText.textContent = project.agent_summary || "结果与证据见右侧。";
    } else {
      emptyTitle.textContent = "Agent 正在自主执行";
      emptyText.textContent = describeAgentActivity(latestActivity) || "正在启动 Codex thread…";
    }
  }
  renderMetricChart();
}

function startProjectPolling() {
  window.setInterval(async () => {
    const project = state.currentProject;
    if (!project || project.source_kind !== "local") {
      return;
    }
    if (!["active", "paused"].includes(project.status)) {
      return;
    }
    try {
      const updated = await fetchJson(
        `${API_ROOT}/projects/${encodeURIComponent(project.project_id)}`
      );
      if (state.currentProject?.project_id !== updated.project_id) {
        return;
      }
      state.currentProject = updated;
      renderProjectSurface();
    } catch (error) {
      console.warn("Project refresh failed", error);
    }
  }, 1500);
}

function renderWorkflow(workflow) {
  dom.workflowSteps.innerHTML = workflow.length
    ? workflow
        .map((node) => {
          const status = node.status || "pending";
          const marker = status === "complete" ? "✓" : status === "attention" ? "!" : "";
          return `
            <div class="workflow-step" data-status="${escapeHtml(status)}">
              <span class="workflow-step-marker">${marker}</span>
              <span class="workflow-step-label">${escapeHtml(node.label || node.id)}</span>
            </div>
          `;
        })
        .join("")
    : "";
}

function renderProjectStatus(project) {
  const lastEvent = Array.isArray(project.events) ? project.events.at(-1) : null;
  const eventType = lastEvent?.event_type || "";
  if (project.status === "error") {
    setConnectionState("bad", "执行失败");
    return;
  }
  if (project.status === "stopped") {
    setConnectionState("bad", "执行已停止");
    dom.pauseProjectButton.textContent = "继续";
    dom.pauseProjectButton.dataset.intervention = "resume";
    return;
  }
  if (project.status === "paused") {
    setConnectionState("warn", "人工已暂停");
    dom.pauseProjectButton.textContent = "继续";
    dom.pauseProjectButton.dataset.intervention = "resume";
    return;
  }
  if (eventType === "human.pause") {
    setConnectionState("warn", "人工已暂停");
    dom.pauseProjectButton.textContent = "继续";
    dom.pauseProjectButton.dataset.intervention = "resume";
    return;
  }
  if (eventType === "human.stop") {
    setConnectionState("bad", "后续运行已停止");
    dom.pauseProjectButton.textContent = "继续";
    dom.pauseProjectButton.dataset.intervention = "resume";
    return;
  }
  dom.pauseProjectButton.textContent = "暂停";
  dom.pauseProjectButton.dataset.intervention = "pause";
  if (project.status === "active") {
    setConnectionState("good", "自主运行中");
  } else if (project.attention || project.status === "attention") {
    setConnectionState("warn", "结果需要关注");
  } else if (project.status === "complete" && project.outcome === "met") {
    setConnectionState("good", "目标已达成");
  } else if (project.status === "complete" && project.outcome === "not_met") {
    setConnectionState("warn", "目标未达成");
  } else if (project.status === "complete" && ["inconclusive", "blocked"].includes(project.outcome)) {
    setConnectionState("warn", project.outcome === "blocked" ? "实验受阻" : "证据不足");
  } else {
    setConnectionState("good", "流程已完成");
  }
}

function renderComparison(project) {
  const comparison = project.comparison || {};
  dom.primaryMetricLabel.textContent = project.primary_metric || "尚无指标";
  dom.chartTitle.textContent = metricDisplayName(project.primary_metric);
  dom.baselineValue.textContent = formatResultValue(comparison.baseline_mean);
  dom.candidateValue.textContent = formatResultValue(comparison.candidate_mean);
  dom.deltaValue.textContent = formatResultValue(comparison.delta, true);
}

function renderConstraints(project) {
  const evidence = Array.isArray(project.constraint_evidence)
    ? project.constraint_evidence
    : [];
  const comparison = project.comparison || {};
  const violations = evidence.filter((item) => {
    if (item?.passed === false) {
      return true;
    }
    if (typeof item?.passed === "boolean") {
      return false;
    }
    return comparison.constraints_passed !== true;
  });
  const failed = comparison.constraints_passed === false || violations.length > 0;
  const known = typeof comparison.constraints_passed === "boolean";
  const displayedEvidence = failed ? violations : evidence;
  dom.constraintCard.dataset.tone = failed ? "warn" : "neutral";
  dom.constraintSummary.textContent = failed
    ? `${violations.length || 1} 项未通过`
    : known
    ? "全部通过"
    : "尚无结论";
  dom.constraintEvidence.innerHTML = displayedEvidence.length
    ? displayedEvidence
        .slice(0, 3)
        .map(
          (item) => `
            <div class="constraint-evidence-row">
              <span>${escapeHtml(item.label || item.metric || item.name || "约束")}</span>
              <strong>${escapeHtml(formatConstraintEvidence(item))}</strong>
            </div>
          `
        )
        .join("")
    : known
    ? '<div class="constraint-evidence-empty">没有发现约束违规</div>'
    : '<div class="constraint-evidence-empty">等待真实实验数据</div>';
  dom.jumpEvidenceButton.hidden = !failed;
  dom.promotionValue.textContent =
    comparison.promoted === true ? "已晋级" : comparison.promoted === false ? "未晋级" : "--";
}

function objectiveStatusLabel(outcome) {
  const labels = {
    met: "目标已达成",
    not_met: "运行完成，目标未达成",
    inconclusive: "运行完成，证据不足",
    blocked: "运行完成，实验受阻",
  };
  return labels[outcome] || "流程已完成";
}

function describeAgentActivity(activity) {
  if (!activity || typeof activity !== "object") {
    return "";
  }
  if (activity.event_type === "execution.failed") {
    return activity.message || "执行失败";
  }
  if (activity.event_type === "execution.agent_message") {
    return activity.text || "";
  }
  if (activity.kind === "command") {
    return activity.command ? `正在执行：${activity.command}` : "正在执行验证命令";
  }
  if (activity.kind === "files") {
    const paths = Array.isArray(activity.paths) ? activity.paths : [];
    return paths.length ? `已更新：${paths.slice(0, 3).join("、")}` : "正在生成实验产物";
  }
  return "";
}

function renderMetricChart() {
  const canvas = dom.metricChart;
  const project = state.currentProject;
  if (!canvas || !project) {
    return;
  }
  const bounds = canvas.getBoundingClientRect();
  const width = Math.max(Math.round(bounds.width), 280);
  const height = Math.max(Math.round(bounds.height), 150);
  const ratio = Math.min(window.devicePixelRatio || 1, 2);
  canvas.width = Math.round(width * ratio);
  canvas.height = Math.round(height * ratio);
  const context = canvas.getContext("2d");
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  context.clearRect(0, 0, width, height);

  const series = project.metric_series || {};
  const baseline = Array.isArray(series.baseline) ? series.baseline : [];
  const candidate = Array.isArray(series.candidate) ? series.candidate : [];
  const all = [...baseline, ...candidate];
  const inset = { left: 38, right: 12, top: 10, bottom: 26 };
  const plotWidth = Math.max(width - inset.left - inset.right, 1);
  const plotHeight = Math.max(height - inset.top - inset.bottom, 1);
  const maxStep = Math.max(...all.map((point) => Number(point.step) || 0), 1);
  const values = all.map((point) => Number(point.value)).filter(Number.isFinite);
  const maxValue = Math.max(...values, 1);
  const minValue = Math.min(...values, 0);
  const span = Math.max(maxValue - minValue, 1e-6);

  context.font = '10px Inter, "PingFang SC", sans-serif';
  context.lineWidth = 1;
  for (let index = 0; index <= 4; index += 1) {
    const y = inset.top + (plotHeight * index) / 4;
    const value = maxValue - (span * index) / 4;
    context.strokeStyle = "#e8ebef";
    context.beginPath();
    context.moveTo(inset.left, y);
    context.lineTo(width - inset.right, y);
    context.stroke();
    context.fillStyle = "#9aa3af";
    context.textAlign = "right";
    context.textBaseline = "middle";
    context.fillText(formatAxisValue(value), inset.left - 7, y);
  }

  drawMetricSeries(context, baseline, "#28b7dc", inset, plotWidth, plotHeight, maxStep, minValue, span);
  drawMetricSeries(context, candidate, "#ff6b17", inset, plotWidth, plotHeight, maxStep, minValue, span);

  const progress = state.totalFrames > 1 ? state.currentFrameIndex / (state.totalFrames - 1) : 0;
  const cursorX = inset.left + plotWidth * progress;
  context.strokeStyle = "rgba(39, 103, 243, 0.5)";
  context.setLineDash([3, 3]);
  context.beginPath();
  context.moveTo(cursorX, inset.top);
  context.lineTo(cursorX, inset.top + plotHeight);
  context.stroke();
  context.setLineDash([]);

  context.fillStyle = "#8f99a8";
  context.textBaseline = "top";
  context.textAlign = "left";
  context.fillText("0", inset.left, inset.top + plotHeight + 8);
  context.textAlign = "right";
  context.fillText(String(Math.round(maxStep)), width - inset.right, inset.top + plotHeight + 8);
}

function drawMetricSeries(context, points, color, inset, width, height, maxStep, minValue, span) {
  if (!points.length) {
    return;
  }
  context.strokeStyle = color;
  context.lineWidth = 2;
  context.lineJoin = "round";
  context.lineCap = "round";
  context.beginPath();
  points.forEach((point, index) => {
    const x = inset.left + ((Number(point.step) || 0) / maxStep) * width;
    const y = inset.top + (1 - ((Number(point.value) || 0) - minValue) / span) * height;
    if (index === 0) {
      context.moveTo(x, y);
    } else {
      context.lineTo(x, y);
    }
  });
  context.stroke();
}

function metricDisplayName(metric) {
  if (!metric) {
    return "主要指标";
  }
  const names = {
    large_swarm_shape_success_rate: "Shape Success",
    route_completion_rate: "Route Completion",
    goal_reach_rate: "Goal Reach",
    success_rate: "Success Rate",
    task_progress: "Task Progress",
  };
  return names[metric] || String(metric).replaceAll("_", " ");
}

function formatMethod(method) {
  const family = method.family === "rule_based" ? "规则策略" : method.family;
  const name = String(method.name || "尚未产生").replaceAll("_", " ");
  return [name, family, method.policy_id].filter(Boolean).join(" · ");
}

function formatResultValue(value, signed = false) {
  const number = Number(value);
  if (!Number.isFinite(number)) {
    return "--";
  }
  const formatted = Math.abs(number) <= 1 ? `${(number * 100).toFixed(1)}%` : number.toFixed(3);
  return signed && number > 0 ? `+${formatted}` : formatted;
}

function formatConstraintValue(value) {
  if (typeof value === "boolean") {
    return value ? "通过" : "未通过";
  }
  const number = Number(value);
  if (!Number.isFinite(number)) {
    return String(value ?? "--");
  }
  return number < 0.01 && number !== 0 ? number.toExponential(2) : number.toFixed(3).replace(/0+$/, "").replace(/\.$/, "");
}

function formatConstraintEvidence(item) {
  const value = item?.observed ?? item?.value;
  const formatted = formatConstraintValue(value);
  if (item?.passed === true) {
    return `${formatted} ✓`;
  }
  if (item?.passed === false) {
    return `${formatted} !`;
  }
  return formatted;
}

function formatAxisValue(value) {
  if (Math.abs(value) <= 1) {
    return value.toFixed(1);
  }
  return value.toFixed(0);
}

function syncRoleOptions() {
  const roles = uniqueStrings(
    state.replays.map((replay) => replay.policy_role || replay.role || "candidate").concat(["candidate"])
  );
  dom.roleSelect.innerHTML = roles
    .map((role) => `<option value="${escapeHtml(role)}"${role === state.selectedRole ? " selected" : ""}>${escapeHtml(role)}</option>`)
    .join("");
  if (!roles.includes(state.selectedRole)) {
    state.selectedRole = roles[0] || "candidate";
    dom.roleSelect.value = state.selectedRole;
  }
  syncRoleButtons();
  renderReplayStatus();
}

async function selectReplayRole(role) {
  if (!state.replays.some((replay) => (replay.policy_role || replay.role) === role)) {
    showActionFeedback(`${role} 暂无可用回放`, true);
    return;
  }
  state.selectedRole = role;
  dom.roleSelect.value = role;
  syncSeedOptions();
  syncRoleButtons();
  await loadSelectedReplay();
  if (state.currentProject) {
    renderProjectStatus(state.currentProject);
  }
}

function syncRoleButtons() {
  dom.baselineRoleButton.dataset.active = String(state.selectedRole === "baseline");
  dom.candidateRoleButton.dataset.active = String(state.selectedRole === "candidate");
}

function syncSeedOptions() {
  const seeds = uniqueNumbers(
    state.replays
      .filter((replay) => (replay.policy_role || replay.role || "candidate") === state.selectedRole)
      .map((replay) => Number.parseInt(replay.seed, 10) || 0)
  );
  dom.seedSelect.innerHTML = seeds
    .map((seed) => `<option value="${seed}"${seed === state.selectedSeed ? " selected" : ""}>${seed}</option>`)
    .join("");
  if (!seeds.includes(state.selectedSeed)) {
    state.selectedSeed = seeds[0] ?? 0;
    dom.seedSelect.value = String(state.selectedSeed);
  }
  renderReplayStatus();
}

function resolveReplay(role, seed) {
  return (
    state.replays.find(
      (replay) => (replay.policy_role || replay.role || "candidate") === role && Number.parseInt(replay.seed, 10) === Number.parseInt(seed, 10)
    ) ||
    state.replays.find((replay) => (replay.policy_role || replay.role || "candidate") === role) ||
    state.replays[0] ||
    null
  );
}

function loadSelectedReplayIfReady() {
  if (state.selectedScenarioId && state.replays.length) {
    return loadSelectedReplay();
  }
  return Promise.resolve();
}

function renderReplayStatus() {
  const replay = resolveReplay(state.selectedRole, state.selectedSeed);
  if (!replay) {
    dom.frameStatus.textContent = "0 / 0";
    return;
  }
  const frameCount = state.totalFrames || replay.frame_count || 0;
  dom.frameStatus.textContent = `${Math.min(state.currentFrameIndex + 1, frameCount || 0)} / ${frameCount || 0}`;
}

function applyQueryState() {
  const scenario = getQueryParam("scenario");
  const role = getQueryParam("role");
  const seed = Number.parseInt(getQueryParam("seed") || "0", 10) || 0;
  const projection = getQueryParam("mode");
  if (scenario) {
    state.selectedScenarioId = scenario;
  }
  if (role) {
    state.selectedRole = role;
  }
  if (Number.isFinite(seed)) {
    state.selectedSeed = seed;
  }
  if (projection === "2d" || projection === "3d") {
    state.selectedProjection = projection;
  }
  dom.projectionSelect.value = state.selectedProjection;
  syncSelectionFromScenario();
}

function syncSelectionFromQuery() {
  const role = getQueryParam("role");
  const seed = Number.parseInt(getQueryParam("seed") || `${state.selectedSeed}`, 10) || 0;
  const projection = getQueryParam("mode");
  if (role) {
    state.selectedRole = role;
  }
  if (Number.isFinite(seed)) {
    state.selectedSeed = seed;
  }
  if (projection === "2d" || projection === "3d") {
    state.selectedProjection = projection;
  }
  dom.projectionSelect.value = state.selectedProjection;
  dom.roleSelect.value = state.selectedRole;
  dom.seedSelect.value = String(state.selectedSeed);
}

function pushQueryState() {
  const params = new URLSearchParams(window.location.search);
  if (state.selectedScenarioId) {
    params.set("scenario", state.selectedScenarioId);
  }
  if (state.selectedRole) {
    params.set("role", state.selectedRole);
  }
  params.set("seed", String(state.selectedSeed || 0));
  params.set("mode", state.selectedProjection);
  const next = `${window.location.pathname}?${params.toString()}${window.location.hash}`;
  window.history.replaceState({}, "", next);
}

function syncFrameSlider() {
  dom.frameSlider.min = "0";
  dom.frameSlider.max = String(Math.max(state.totalFrames - 1, 0));
  dom.frameSlider.value = String(clampInteger(state.currentFrameIndex, 0, Math.max(state.totalFrames - 1, 0)));
  dom.timelineStart.textContent = "0";
  dom.timelineMid.textContent = String(Math.max(Math.floor((state.totalFrames - 1) / 2), 0));
  dom.timelineEnd.textContent = String(Math.max(state.totalFrames - 1, 0));
  renderReplayStatus();
}

function setFrameIndex(index) {
  const bounded = clampInteger(index, 0, Math.max(state.totalFrames - 1, 0));
  state.currentFrameIndex = bounded;
  dom.frameSlider.value = String(bounded);
  renderScene();
  renderPanels();
  renderReplayStatus();
  pushQueryState();
}

function stepFrame(delta) {
  if (!state.totalFrames) {
    return;
  }
  const next = clampInteger(state.currentFrameIndex + delta, 0, Math.max(state.totalFrames - 1, 0));
  setFrameIndex(next);
}

function togglePlayback() {
  state.playState.playing = !state.playState.playing;
  dom.playButton.textContent = state.playState.playing ? "Ⅱ" : "▶";
  dom.playButton.setAttribute("aria-pressed", String(state.playState.playing));
  announce(state.playState.playing ? "Playback started" : "Playback paused");
}

function adjustSpeed(delta) {
  const current = state.playState.speed;
  const candidate = clampNumber(current + delta, 0.25, 4);
  state.playState.speed = roundTo(candidate, 2);
  dom.speedValue.textContent = `${state.playState.speed.toFixed(1)}x`;
  announce(`Playback speed ${state.playState.speed.toFixed(1)}x`);
}

function startPlaybackLoop() {
  const tick = (now) => {
    const elapsed = now - state.playState.lastTick;
    state.playState.lastTick = now;
    if (state.playState.playing && state.totalFrames > 1) {
      state.playState.accumulator += elapsed;
      const stepMs = 80 / Math.max(state.playState.speed, 0.25);
      let advanced = false;
      while (state.playState.accumulator >= stepMs) {
        state.playState.accumulator -= stepMs;
        if (state.currentFrameIndex >= state.totalFrames - 1) {
          state.playState.playing = false;
          dom.playButton.textContent = "▶";
          dom.playButton.setAttribute("aria-pressed", "false");
          break;
        }
        state.currentFrameIndex += 1;
        advanced = true;
      }
      if (advanced) {
        dom.frameSlider.value = String(state.currentFrameIndex);
        renderScene();
        renderPanels();
        renderReplayStatus();
      }
    }
    requestAnimationFrame(tick);
  };
  requestAnimationFrame((now) => {
    state.playState.lastTick = now;
    requestAnimationFrame(tick);
  });
}

function renderPanels() {
  const frame = getCurrentFrame();
  const scenario = state.selectedScenario || createDemoScenario();
  const visualization = state.visualization || createDemoVisualization();
  const world = visualization.world || {};
  dom.frameStatus.textContent = `${Math.min(state.currentFrameIndex + 1, state.totalFrames || 0)} / ${state.totalFrames || 0}`;
  dom.liveFrameValue.textContent = `#${frame?.episode_step ?? 0} @ ${formatTime(frame?.scenario_time ?? 0)}s`;
  dom.liveFrameCaption.textContent = frame
    ? `${frame.entities.length} entities / ${frame.events.length} events / ${frame.relations.length} relations`
    : "No frame loaded.";
  dom.speedValue.textContent = `${state.playState.speed.toFixed(1)}x`;
  dom.dimensionLabel.textContent = String(world.dimension || 2);
  dom.agentCount.textContent = String(scenario.agents?.length || frame?.entities.length || 0);
  dom.eventCount.textContent = String(frame?.events.length || 0);
  renderMetrics(frame);
  renderEvents(frame);
  renderDisclosures();
  renderRawData(frame);
  renderLayerControls();
  renderReplayStatus();
  renderMetricChart();
}

function renderMetrics(frame) {
  const metrics = {
    ...(state.replayBundle?.metrics || {}),
    ...(frame?.metrics || {}),
  };
  const orderedKeys = prioritizeMetricKeys(Object.keys(metrics));
  dom.metricsGrid.innerHTML = orderedKeys.length
    ? orderedKeys
        .map((key) => {
          const value = metrics[key];
          const meta = metricMetaLabel(key, value);
          return `
            <div class="metric-card">
              <div class="metric-label">${escapeHtml(key)}</div>
              <div class="metric-value">${escapeHtml(formatMetricValue(value))}</div>
              <div class="metric-meta">${escapeHtml(meta)}</div>
            </div>
          `;
        })
        .join("")
    : `<div class="warning-item">No metrics in current frame.</div>`;
}

function renderEvents(frame) {
  const events = uniqueEvents([...(state.replayBundle?.events || []), ...(frame?.events || [])]);
  dom.eventList.innerHTML = events.length
    ? events
        .map((event) => {
          const summary = summarizeEvent(event);
          const participants = event.participants?.length ? event.participants.join(", ") : "none";
          return `
            <article class="event-item">
              <div class="event-title">
                <strong>${escapeHtml(event.event_type)}</strong>
                <span>${escapeHtml(formatTime(event.time))}s</span>
              </div>
              <div class="event-body">${escapeHtml(summary)}</div>
              <div class="event-body">${escapeHtml(participants)}</div>
            </article>
          `;
        })
        .join("")
    : `<div class="warning-item">No events emitted on this frame.</div>`;
}

function renderDisclosures() {
  const scenarioDisclosure = state.selectedScenario?.disclosures || [];
  const visualizationDisclosure = state.visualization?.disclosures || [];
  const replayDisclosure = state.replayBundle?.disclosures || [];
  const combined = uniqueStrings([...scenarioDisclosure, ...visualizationDisclosure, ...replayDisclosure]);
  dom.disclosureList.innerHTML = combined.length
    ? combined.map((item) => `<div class="bullet-item">${escapeHtml(item)}</div>`).join("")
    : `<div class="warning-item">No disclosures provided.</div>`;
}

function renderRawData(frame) {
  const warnings = [];
  const unsupportedLayers = state.layerMeta.filter((layer) => !layer.known);
  if (unsupportedLayers.length) {
    warnings.push(
      ...unsupportedLayers.map(
        (layer) => `Unsupported layer source: ${layer.source} (${layer.layerType}) kept as raw metadata`
      )
    );
  }
  const unknownFrameKeys = frame ? diffKeys(frame.raw || frame, new Set(["schema_version", "scenario_time", "episode_step", "entities", "relations", "fields", "observations", "actions", "messages", "events", "rewards", "metrics", "raw"])) : [];
  if (unknownFrameKeys.length) {
    warnings.push(`Extra frame keys: ${unknownFrameKeys.join(", ")}`);
  }
  dom.rawWarnings.innerHTML = warnings.length
    ? warnings.map((item) => `<div class="warning-item">${escapeHtml(item)}</div>`).join("")
    : `<div class="warning-item">No raw-data warnings.</div>`;
  dom.rawData.textContent = JSON.stringify(
    {
      scenario: state.selectedScenario?.metadata || state.selectedScenario,
      visualization: state.visualization?.raw || state.visualization,
      replay_bundle: state.replayBundle?.raw || state.replayBundle,
      frame: frame?.raw || frame,
      layers: state.layerMeta,
    },
    null,
    2
  );
}

function renderLayerControls() {
  if (!state.layerMeta.length) {
    dom.layerToggles.innerHTML = `<div class="warning-item">No layer metadata available.</div>`;
    return;
  }
  dom.layerToggles.innerHTML = state.layerMeta
    .map((layer) => {
      const checked = state.layers.get(layer.layerId) !== false;
      const statusLabel = layer.known ? "rendered" : "raw";
      return `
        <label class="layer-toggle">
          <span class="layer-name">
            <strong>${escapeHtml(layer.label)}</strong>
            <span>${escapeHtml(layer.description)}</span>
          </span>
          <span class="layer-pill">${escapeHtml(statusLabel)}</span>
          <input type="checkbox" data-layer-id="${escapeHtml(layer.layerId)}"${checked ? " checked" : ""}${layer.known ? "" : " disabled"} />
        </label>
      `;
    })
    .join("");
  dom.layerToggles.querySelectorAll('input[type="checkbox"]').forEach((checkbox) => {
    checkbox.addEventListener("change", (event) => {
      const layerId = event.currentTarget.getAttribute("data-layer-id");
      if (!layerId) {
        return;
      }
      state.layers.set(layerId, event.currentTarget.checked);
      renderScene();
    });
  });
}

function renderScenarioContextSafe() {
  renderScenarioContext();
}

function renderScene() {
  renderer.resize();
  const frame = getCurrentFrame();
  const visualization = state.visualization || createDemoVisualization();
  const world = visualization.world || {};
  const activeView = visualization.views?.[0] || { camera: "orbit", layers: [] };
  const canvasData = {
    scenarioId: state.selectedScenarioId,
    scenarioName: state.selectedScenario?.name || state.selectedScenarioId,
    projection: state.selectedProjection,
    world,
    frame,
    visualization,
    layers: state.layerMeta,
    layerState: state.layers,
    camera: activeView.camera,
    history: buildHistory(),
    warnings: state.warnings,
  };
  renderer.render(canvasData);
  const title = state.selectedScenario?.name || state.selectedScenarioId || "No scenario loaded";
  dom.canvasTitle.textContent = title;
  dom.canvasSubtitle.textContent = buildCanvasSubtitle(canvasData);
}

function buildCanvasSubtitle({ world, frame, visualization }) {
  const parts = [];
  parts.push(`${world.dimension || 2}D`);
  parts.push(frame ? `step ${frame.episode_step}` : "no frame");
  parts.push(`${visualization.static_primitives.length} static primitives`);
  if (state.useDemo) {
    parts.push("demo mode");
  }
  return parts.join(" / ");
}

function buildHistory() {
  const history = new Map();
  for (const frame of state.frameWindow) {
    for (const entity of frame.entities || []) {
      const list = history.get(entity.id) || [];
      list.push({
        frame: frame.episode_step,
        time: frame.scenario_time,
        position: entity.position,
        goal: entity.goal,
        active: entity.active,
      });
      history.set(entity.id, list);
    }
  }
  return history;
}

function getCurrentFrame() {
  if (!state.frameWindow.length) {
    return null;
  }
  const index = clampInteger(state.currentFrameIndex, 0, state.frameWindow.length - 1);
  return state.frameWindow[index] || null;
}

function showError(message) {
  dom.rawWarnings.innerHTML = `<div class="warning-item">${escapeHtml(message)}</div>`;
  announce(message);
}

function setConnectionState(tone, text) {
  dom.connectionStatus.dataset.tone = tone;
  dom.connectionStatusText.textContent = text;
  state.connection = tone;
}

function setLoading(isLoading, label) {
  state.loading = isLoading;
  dom.connectionStatus.dataset.tone = isLoading ? "warn" : state.connection;
  if (label) {
    dom.connectionStatusText.textContent = label;
  }
}

function clearWarnings() {
  state.warnings = [];
  dom.rawWarnings.innerHTML = "";
}

function announce(message) {
  dom.announcement.textContent = message;
}

function summarizeEvent(event) {
  const attrs = event.attributes && typeof event.attributes === "object" ? event.attributes : {};
  const attributePairs = Object.entries(attrs)
    .slice(0, 3)
    .map(([key, value]) => `${key}=${formatCompactValue(value)}`);
  return attributePairs.length ? attributePairs.join(" / ") : "No extra attributes.";
}

function metricMetaLabel(key, value) {
  if (typeof value === "boolean") {
    return value ? "flag: true" : "flag: false";
  }
  if (typeof value === "number") {
    return Number.isInteger(value) ? "numeric" : "float";
  }
  if (Array.isArray(value)) {
    return `array(${value.length})`;
  }
  if (value && typeof value === "object") {
    return "mapping";
  }
  return "value";
}

function formatMetricValue(value) {
  if (typeof value === "number") {
    return Number.isInteger(value) ? String(value) : value.toFixed(4).replace(/0+$/, "").replace(/\.$/, "");
  }
  if (typeof value === "boolean") {
    return value ? "true" : "false";
  }
  if (Array.isArray(value)) {
    return `[${value.map((item) => formatCompactValue(item)).join(", ")}]`;
  }
  if (value && typeof value === "object") {
    return "{...}";
  }
  return String(value ?? "--");
}

function formatCompactValue(value) {
  if (typeof value === "number") {
    return Number.isInteger(value) ? String(value) : value.toFixed(3).replace(/0+$/, "").replace(/\.$/, "");
  }
  if (Array.isArray(value)) {
    return `[${value.map((item) => formatCompactValue(item)).join(", ")}]`;
  }
  if (value && typeof value === "object") {
    return "{...}";
  }
  return String(value);
}

function formatTime(value) {
  const numeric = Number.parseFloat(value);
  if (!Number.isFinite(numeric)) {
    return "0.00";
  }
  return numeric.toFixed(2).replace(/0+$/, "").replace(/\.$/, ".0");
}

function uniqueEvents(events) {
  const seen = new Set();
  const result = [];
  for (const event of events) {
    const key = [
      event.event_type || event.type || "event",
      event.step ?? "",
      event.time ?? "",
      normalizeStringList(event.participants).join(","),
    ].join("|");
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    result.push(event);
  }
  return result;
}

function replayLabel(replay) {
  return `${replay.policy_role || replay.role || "candidate"} / seed ${replay.seed ?? 0}`;
}

function describeReplay(replay) {
  const parts = [];
  if (replay.policy_id) {
    parts.push(replay.policy_id);
  }
  if (replay.frame_count) {
    parts.push(`${replay.frame_count} frames`);
  }
  if (replay.duration) {
    parts.push(`${replay.duration.toFixed(2)}s`);
  }
  return parts.join(" / ") || "Replay selection";
}

function sourceToLabel(source) {
  return source
    .replace(/_/g, " ")
    .replace(/\b\w/g, (match) => match.toUpperCase());
}

function layerDescription(source, layerType) {
  const descriptions = {
    entities: "Entity bodies, tags, and activity state",
    entity_goals: "Goal markers and target connections",
    relations: "Relation graph and directional links",
    fields: "Static or dynamic vector fields",
    events: "Discrete event markers and pulses",
    trajectories: "Historical motion paths",
    static_primitives: "Perimeter rings, gates, and fixed geometry",
    boundaries: "World boundary primitives",
    rings: "Ring geometry from adapter metadata",
  };
  return descriptions[source] || descriptions[layerType] || "Renderer-managed layer";
}

function prioritizeMetricKeys(keys) {
  const priority = [
    "primary_value",
    "primary_metric",
    "task_success_rate",
    "success_rate",
    "task_progress",
    "collision_rate",
    "out_of_bounds_rate",
    "action_violation_rate",
    "communication_delivery_rate",
    "message_drop_rate",
    "episode_length",
    "timeout",
  ];
  return [...keys].sort((a, b) => {
    const ai = priority.indexOf(a);
    const bi = priority.indexOf(b);
    if (ai === -1 && bi === -1) {
      return a.localeCompare(b);
    }
    if (ai === -1) {
      return 1;
    }
    if (bi === -1) {
      return -1;
    }
    return ai - bi;
  });
}

function renderScenarioContextIfReady() {
  if (state.selectedScenarioId) {
    renderScenarioContext();
  }
}

function extractArray(response, keys) {
  if (Array.isArray(response)) {
    return response;
  }
  if (!response || typeof response !== "object") {
    return [];
  }
  for (const key of keys) {
    const candidate = response[key];
    if (Array.isArray(candidate)) {
      return candidate;
    }
  }
  return [];
}

function normalizeArray(value) {
  return Array.isArray(value) ? value : [];
}

function normalizeStringList(value) {
  return Array.isArray(value) ? value.map((item) => String(item)) : [];
}

function normalizeNumericTuple(value, dimension, fallback) {
  const list = Array.isArray(value) ? value : [];
  const result = [];
  for (let index = 0; index < dimension; index += 1) {
    const item = Number.parseFloat(list[index]);
    result.push(Number.isFinite(item) ? item : fallback);
  }
  return result;
}

function normalizeWorldBounds(bounds, legacyMinimum, legacyMaximum) {
  const source = bounds && typeof bounds === "object" ? bounds : {};
  const minimum = normalizePointTuple(source.minimum || source.min || legacyMinimum || [-1, -1, -1]);
  const maximum = normalizePointTuple(source.maximum || source.max || legacyMaximum || [1, 1, 1]);
  return { minimum, maximum };
}

function normalizeUnits(units) {
  const source = units && typeof units === "object" ? units : {};
  return {
    length: String(source.length || "normalized"),
    time: String(source.time || "second"),
    angle: String(source.angle || "radian"),
  };
}

function normalizePointTuple(value) {
  const tuple = Array.isArray(value) ? value : [];
  return [
    Number.parseFloat(tuple[0]) || 0,
    Number.parseFloat(tuple[1]) || 0,
    Number.parseFloat(tuple[2]) || 0,
  ];
}

function normalizePointList(value) {
  return Array.isArray(value) ? value.map((item) => normalizePointTuple(item)) : [];
}

function normalizeLayerSource(source, kind) {
  const sourceMap = {
    entity_markers: "entities",
    goal_markers: "entity_goals",
    trajectories: "trajectories",
    relations: "relations",
    vector_fields: "fields",
    events: "events",
    messages: "messages",
    static_geometry: "static_primitives",
  };
  const mapped = sourceMap[String(kind || "")];
  if (mapped) {
    return mapped;
  }
  if (source && source !== "unknown") {
    return source;
  }
  return "unknown";
}

function normalizeCamera(camera) {
  const source = camera && typeof camera === "object" ? camera : {};
  return {
    kind: String(source.kind || source.type || source.projection || "orbit"),
    yaw: Number.parseFloat(source.yaw ?? source.azimuth ?? 35) || 35,
    pitch: Number.parseFloat(source.pitch ?? source.elevation ?? 28) || 28,
    distance: Number.parseFloat(source.distance ?? 2.6) || 2.6,
    focal_length: Number.parseFloat(source.focal_length ?? 1.0) || 1.0,
  };
}

function uniqueStrings(values) {
  return [...new Set(values.filter(Boolean).map((value) => String(value)))];
}

function uniqueNumbers(values) {
  return [...new Set(values.filter((value) => Number.isFinite(value)))].sort((a, b) => a - b);
}

function diffKeys(object, allowed) {
  return Object.keys(object || {}).filter((key) => !allowed.has(key));
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function getQueryParam(key) {
  return new URLSearchParams(window.location.search).get(key);
}

function clampInteger(value, min, max) {
  return Math.min(Math.max(Number.isFinite(value) ? Math.trunc(value) : min, min), max);
}

function clampNumber(value, min, max) {
  return Math.min(Math.max(Number.isFinite(value) ? value : min, min), max);
}

function roundTo(value, decimals) {
  const scale = 10 ** decimals;
  return Math.round(value * scale) / scale;
}

async function fetchJson(url) {
  const response = await fetch(url, {
    headers: {
      Accept: "application/json",
    },
  });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText} for ${url}`);
  }
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return response.json();
  }
  const text = await response.text();
  try {
    return JSON.parse(text);
  } catch (error) {
    throw new Error(`Expected JSON from ${url}`);
  }
}

async function postJson(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(body.error || `${response.status} ${response.statusText}`);
  }
  return body;
}

function syncSelectionFromScenarioAndReload() {
  syncSelectionFromScenario();
  renderScenarioContextIfReady();
  renderScenarioCatalog();
}

class SceneRenderer {
  constructor(canvas) {
    this.canvas = canvas;
    this.context = canvas.getContext("2d", { alpha: false });
    this.devicePixelRatio = Math.max(window.devicePixelRatio || 1, 1);
    this.width = 0;
    this.height = 0;
    this.bounds = { min: [-1, -1, -1], max: [1, 1, 1] };
    this.aspect = 1;
    this.cameraYaw = 35;
    this.cameraPitch = 28;
    this.dragOrigin = null;
    canvas.addEventListener("pointerdown", (event) => {
      this.dragOrigin = { x: event.clientX, y: event.clientY };
      canvas.setPointerCapture(event.pointerId);
      canvas.classList.add("is-dragging");
    });
    canvas.addEventListener("pointermove", (event) => {
      if (!this.dragOrigin || state.selectedProjection !== "3d") {
        return;
      }
      const deltaX = event.clientX - this.dragOrigin.x;
      const deltaY = event.clientY - this.dragOrigin.y;
      this.cameraYaw = (this.cameraYaw + deltaX * 0.35) % 360;
      this.cameraPitch = clampNumber(this.cameraPitch - deltaY * 0.25, -70, 70);
      this.dragOrigin = { x: event.clientX, y: event.clientY };
      renderScene();
    });
    const finishDrag = (event) => {
      if (this.dragOrigin && canvas.hasPointerCapture(event.pointerId)) {
        canvas.releasePointerCapture(event.pointerId);
      }
      this.dragOrigin = null;
      canvas.classList.remove("is-dragging");
    };
    canvas.addEventListener("pointerup", finishDrag);
    canvas.addEventListener("pointercancel", finishDrag);
  }

  resize() {
    const rect = this.canvas.getBoundingClientRect();
    const width = Math.max(Math.floor(rect.width), 1);
    const height = Math.max(Math.floor(rect.height), 1);
    const dpr = Math.max(window.devicePixelRatio || 1, 1);
    if (width === this.width && height === this.height && dpr === this.devicePixelRatio) {
      return;
    }
    this.width = width;
    this.height = height;
    this.devicePixelRatio = dpr;
    this.canvas.width = Math.floor(width * dpr);
    this.canvas.height = Math.floor(height * dpr);
    this.context.setTransform(dpr, 0, 0, dpr, 0, 0);
    this.aspect = width / Math.max(height, 1);
  }

  render(payload) {
    const ctx = this.context;
    const width = this.width || this.canvas.width / this.devicePixelRatio;
    const height = this.height || this.canvas.height / this.devicePixelRatio;
    ctx.save();
    ctx.clearRect(0, 0, width, height);
    this.drawBackground(ctx, width, height);
    this.bounds = this.resolveBounds(payload);
    const frame = payload.frame;
    const history = payload.history || new Map();
    const projectionMode = payload.projection || "3d";
    const entities = frame?.entities || [];
    const visibleLayers = payload.layerState || new Map();

    if (this.layerEnabled(visibleLayers, payload.layers, "static_primitives")) {
      this.drawStaticPrimitives(ctx, payload.visualization?.static_primitives || [], payload);
    }
    if (this.layerEnabled(visibleLayers, payload.layers, "fields")) {
      this.drawVectorField(ctx, frame, payload);
    }
    if (this.layerEnabled(visibleLayers, payload.layers, "trajectories")) {
      this.drawTrajectories(ctx, history, payload);
    }
    if (this.layerEnabled(visibleLayers, payload.layers, "relations")) {
      this.drawRelations(ctx, frame, payload);
    }
    if (this.layerEnabled(visibleLayers, payload.layers, "entity_goals")) {
      this.drawGoals(ctx, entities, payload);
    }
    if (this.layerEnabled(visibleLayers, payload.layers, "entities")) {
      this.drawEntities(ctx, entities, payload, projectionMode);
    }
    if (this.layerEnabled(visibleLayers, payload.layers, "events")) {
      this.drawEvents(ctx, frame, payload);
    }
    this.drawFrameChrome(ctx, payload);
    ctx.restore();
  }

  layerEnabled(layerState, layers, source) {
    const meta = (layers || []).find((layer) => layer.source === source || layer.layerId === source);
    if (!meta) {
      return false;
    }
    return layerState.get(meta.layerId) !== false;
  }

  resolveBounds(payload) {
    const world = payload.world || {};
    const min = normalizeNumericTuple(world.bounds_min || [-1, -1, -1], 3, -1);
    const max = normalizeNumericTuple(world.bounds_max || [1, 1, 1], 3, 1);
    const frames = payload.history ? [...payload.history.values()].flat() : [];
    const entities = payload.frame?.entities || [];
    const sources = entities.concat(
      frames.flatMap((entry) => [{ position: entry.position }, { goal: entry.goal }])
    );
    for (const item of sources) {
      if (!item) {
        continue;
      }
      const position = item.position || item.goal;
      if (!Array.isArray(position)) {
        continue;
      }
      for (let index = 0; index < 3; index += 1) {
        const value = Number.parseFloat(position[index]);
        if (!Number.isFinite(value)) {
          continue;
        }
        min[index] = Math.min(min[index], value);
        max[index] = Math.max(max[index], value);
      }
    }
    for (let index = 0; index < 3; index += 1) {
      if (Math.abs(max[index] - min[index]) < 0.05) {
        max[index] += 0.5;
        min[index] -= 0.5;
      }
    }
    return { min, max };
  }

  drawBackground(ctx, width, height) {
    const gradient = ctx.createLinearGradient(0, 0, 0, height);
    gradient.addColorStop(0, "#05080b");
    gradient.addColorStop(0.6, "#081015");
    gradient.addColorStop(1, "#040607");
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, width, height);

    ctx.save();
    ctx.globalAlpha = 0.2;
    ctx.strokeStyle = "rgba(255,255,255,0.07)";
    ctx.lineWidth = 1;
    const gridStep = 48;
    for (let x = 0; x <= width; x += gridStep) {
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, height);
      ctx.stroke();
    }
    for (let y = 0; y <= height; y += gridStep) {
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(width, y);
      ctx.stroke();
    }
    ctx.restore();
  }

  drawStaticPrimitives(ctx, primitives, payload) {
    for (const primitive of primitives) {
      const color = primitive.style?.stroke || primitive.style?.color || "#56d6e6";
      const alpha = primitive.style?.alpha ?? 0.35;
      const geometry = primitive.geometry || {};
      ctx.save();
      ctx.globalAlpha = alpha;
      ctx.strokeStyle = color;
      ctx.fillStyle = color;
      ctx.lineWidth = primitive.style?.width || 2;
      if (primitive.kind === "ring") {
        const center = primitive.center || geometry.center || [0, 0, 0];
        const radius = Number.parseFloat(primitive.radius ?? geometry.radius ?? 1) || 1;
        const projected = this.projectPoint(center, payload);
        const edge = this.projectDistance(radius, payload);
        ctx.beginPath();
        ctx.arc(projected.x, projected.y, Math.max(edge, 8), 0, Math.PI * 2);
        ctx.stroke();
      } else if (primitive.kind === "boundary_box") {
        const minimum = normalizePointTuple(
          primitive.metadata?.minimum || payload.world?.bounds_min || [-1, -1, -1]
        );
        const maximum = normalizePointTuple(
          primitive.metadata?.maximum || payload.world?.bounds_max || [1, 1, 1]
        );
        const is3d = (payload.world?.dimension || 2) === 3;
        const corners = is3d
          ? [
              [minimum[0], minimum[1], minimum[2]],
              [maximum[0], minimum[1], minimum[2]],
              [maximum[0], maximum[1], minimum[2]],
              [minimum[0], maximum[1], minimum[2]],
              [minimum[0], minimum[1], maximum[2]],
              [maximum[0], minimum[1], maximum[2]],
              [maximum[0], maximum[1], maximum[2]],
              [minimum[0], maximum[1], maximum[2]],
            ]
          : [
              [minimum[0], minimum[1], 0],
              [maximum[0], minimum[1], 0],
              [maximum[0], maximum[1], 0],
              [minimum[0], maximum[1], 0],
            ];
        const edges = is3d
          ? [[0, 1], [1, 2], [2, 3], [3, 0], [4, 5], [5, 6], [6, 7], [7, 4], [0, 4], [1, 5], [2, 6], [3, 7]]
          : [[0, 1], [1, 2], [2, 3], [3, 0]];
        ctx.beginPath();
        for (const [startIndex, endIndex] of edges) {
          const start = this.projectPoint(corners[startIndex], payload);
          const end = this.projectPoint(corners[endIndex], payload);
          ctx.moveTo(start.x, start.y);
          ctx.lineTo(end.x, end.y);
        }
        ctx.stroke();
      } else if (primitive.kind === "polyline") {
        const points = primitive.points?.length ? primitive.points : geometry.points || [];
        const projected = points.map((point) => this.projectPoint(point, payload));
        if (projected.length) {
          ctx.beginPath();
          ctx.moveTo(projected[0].x, projected[0].y);
          for (let index = 1; index < projected.length; index += 1) {
            ctx.lineTo(projected[index].x, projected[index].y);
          }
          ctx.stroke();
        }
      } else if (primitive.kind === "point") {
        const point = primitive.center || primitive.points?.[0] || geometry.point || [0, 0, 0];
        const projected = this.projectPoint(point, payload);
        ctx.beginPath();
        ctx.arc(projected.x, projected.y, 4, 0, Math.PI * 2);
        ctx.fill();
      } else if (primitive.kind === "line") {
        const start = geometry.start || [-1, -1, 0];
        const end = geometry.end || [1, 1, 0];
        const a = this.projectPoint(start, payload);
        const b = this.projectPoint(end, payload);
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.stroke();
      } else if (primitive.kind === "polygon" && Array.isArray(geometry.vertices)) {
        const vertices = geometry.vertices.map((vertex) => this.projectPoint(vertex, payload));
        if (vertices.length) {
          ctx.beginPath();
          ctx.moveTo(vertices[0].x, vertices[0].y);
          for (let index = 1; index < vertices.length; index += 1) {
            ctx.lineTo(vertices[index].x, vertices[index].y);
          }
          ctx.closePath();
          ctx.stroke();
        }
      }
      ctx.restore();
    }
  }

  drawVectorField(ctx, frame, payload) {
    const field = frame?.fields?.find((item) => item.kind === "vector_field" || Array.isArray(item.vector));
    if (!field) {
      return;
    }
    const [vx, vy, vz] = normalizeNumericTuple(field.vector || [0, 0, 0], 3, 0);
    const cellsX = 6;
    const cellsY = 4;
    for (let gx = 0; gx < cellsX; gx += 1) {
      for (let gy = 0; gy < cellsY; gy += 1) {
        const worldPoint = this.interpolateWorldPoint(gx / Math.max(cellsX - 1, 1), gy / Math.max(cellsY - 1, 1), 0.25, payload);
        const origin = this.projectPoint(worldPoint, payload);
        const target = this.projectPoint([worldPoint[0] + vx, worldPoint[1] + vy, worldPoint[2] + vz], payload);
        ctx.save();
        ctx.strokeStyle = "rgba(86, 214, 230, 0.26)";
        ctx.fillStyle = "rgba(86, 214, 230, 0.26)";
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(origin.x, origin.y);
        ctx.lineTo(target.x, target.y);
        ctx.stroke();
        drawArrowHead(ctx, origin.x, origin.y, target.x, target.y, 5);
        ctx.restore();
      }
    }
  }

  drawTrajectories(ctx, history, payload) {
    for (const [entityId, samples] of history.entries()) {
      if (samples.length < 2) {
        continue;
      }
      ctx.save();
      ctx.strokeStyle = "rgba(239, 177, 92, 0.36)";
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      for (let index = 0; index < samples.length; index += 1) {
        const point = this.projectPoint(samples[index].position, payload);
        if (index === 0) {
          ctx.moveTo(point.x, point.y);
        } else {
          ctx.lineTo(point.x, point.y);
        }
      }
      ctx.stroke();
      ctx.restore();
    }
  }

  drawRelations(ctx, frame, payload) {
    const entityById = new Map((frame?.entities || []).map((entity) => [entity.id, entity]));
    for (const relation of frame?.relations || []) {
      const source = entityById.get(relation.source);
      const target = entityById.get(relation.target);
      if (!source || !target) {
        continue;
      }
      const a = this.projectPoint(source.position, payload);
      const b = this.projectPoint(target.position, payload);
      ctx.save();
      ctx.strokeStyle = relation.kind === "communication_neighbor" ? "rgba(86, 214, 230, 0.38)" : "rgba(255,255,255,0.14)";
      ctx.lineWidth = relation.kind === "communication_neighbor" ? 1.8 : 1.1;
      ctx.setLineDash(relation.kind === "communication_neighbor" ? [8, 6] : [4, 4]);
      ctx.beginPath();
      ctx.moveTo(a.x, a.y);
      ctx.lineTo(b.x, b.y);
      ctx.stroke();
      drawArrowHead(ctx, a.x, a.y, b.x, b.y, 4.5);
      ctx.restore();
    }
  }

  drawGoals(ctx, entities, payload) {
    for (const entity of entities) {
      if (!entity.goal) {
        continue;
      }
      const start = this.projectPoint(entity.position, payload);
      const goal = this.projectPoint(entity.goal, payload);
      ctx.save();
      ctx.setLineDash([3, 5]);
      ctx.strokeStyle = "rgba(239, 177, 92, 0.25)";
      ctx.lineWidth = 1.2;
      ctx.beginPath();
      ctx.moveTo(start.x, start.y);
      ctx.lineTo(goal.x, goal.y);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = "rgba(239, 177, 92, 0.78)";
      ctx.beginPath();
      ctx.arc(goal.x, goal.y, 4, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
    }
  }

  drawEntities(ctx, entities, payload, projectionMode) {
    const denseMode = entities.length > 12;
    const sorted = entities
      .map((entity) => ({
        entity,
        projected: this.projectPoint(entity.position, payload),
        depth: this.projectPoint(entity.position, payload).depth,
      }))
      .sort((a, b) => a.depth - b.depth);
    for (const { entity, projected } of sorted) {
      const color = teamColor(entity.team, entity.role);
      const radius = denseMode ? (entity.active ? 4.5 : 3.5) : entity.active ? 8.5 : 6;
      ctx.save();
      ctx.shadowColor = color;
      ctx.shadowBlur = denseMode ? 4 : 10;
      ctx.fillStyle = color;
      ctx.strokeStyle = "rgba(240, 248, 255, 0.8)";
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.arc(projected.x, projected.y, radius, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();

      ctx.shadowBlur = 0;
      if (!denseMode) {
        ctx.fillStyle = "#eef6ff";
        ctx.font = `600 11px ${getComputedStyle(document.documentElement).getPropertyValue("--mono-font")}`;
        ctx.textAlign = "center";
        ctx.textBaseline = "bottom";
        ctx.fillText(entity.id, projected.x, projected.y - radius - 3);

        ctx.fillStyle = "rgba(7,10,13,0.92)";
        ctx.fillRect(projected.x - 18, projected.y + radius + 3, 36, 12);
        ctx.fillStyle = "#f8fbfe";
        ctx.font = `10px ${getComputedStyle(document.documentElement).getPropertyValue("--mono-font")}`;
        ctx.fillText(entity.role, projected.x, projected.y + radius + 12);
      }
      if (projectionMode === "3d" && Array.isArray(entity.position) && entity.position.length >= 3) {
        const height = clampNumber((entity.position[2] || 0) * 24, -18, 18);
        ctx.strokeStyle = "rgba(86, 214, 230, 0.24)";
        ctx.beginPath();
        ctx.moveTo(projected.x, projected.y);
        ctx.lineTo(projected.x, projected.y - height);
        ctx.stroke();
      }
      ctx.restore();
    }
  }

  drawEvents(ctx, frame, payload) {
    for (const event of frame?.events || []) {
      const primary = event.participants?.[0];
      const entity = (frame.entities || []).find((item) => item.id === primary);
      if (!entity) {
        continue;
      }
      const point = this.projectPoint(entity.position, payload);
      ctx.save();
      ctx.globalAlpha = 0.75;
      ctx.strokeStyle = "rgba(255, 120, 104, 0.75)";
      ctx.fillStyle = "rgba(255, 120, 104, 0.15)";
      ctx.lineWidth = 1.4;
      ctx.beginPath();
      ctx.arc(point.x, point.y, 16, 0, Math.PI * 2);
      ctx.stroke();
      ctx.fill();
      ctx.restore();
    }
  }

  drawFrameChrome(ctx, payload) {
    const width = this.width || this.canvas.width / this.devicePixelRatio;
    const height = this.height || this.canvas.height / this.devicePixelRatio;
    ctx.save();
    ctx.strokeStyle = "rgba(255,255,255,0.08)";
    ctx.lineWidth = 1;
    ctx.strokeRect(0.5, 0.5, width - 1, height - 1);
    ctx.fillStyle = "rgba(86, 214, 230, 0.14)";
    ctx.fillRect(0, 0, width, 2);
    ctx.fillStyle = "rgba(239, 177, 92, 0.12)";
    ctx.fillRect(0, height - 2, width, 2);
    ctx.restore();
  }

  projectDistance(distance, payload) {
    const min = this.bounds.min;
    const max = this.bounds.max;
    const spanX = Math.max(max[0] - min[0], 0.001);
    const scale = Math.min(this.width / spanX, this.height / Math.max(max[1] - min[1], 0.001));
    return distance * scale * 0.5;
  }

  projectPoint(point, payload) {
    const [x = 0, y = 0, z = 0] = Array.isArray(point) ? point : [0, 0, 0];
    const min = this.bounds.min;
    const max = this.bounds.max;
    const width = this.width || this.canvas.width / this.devicePixelRatio;
    const height = this.height || this.canvas.height / this.devicePixelRatio;
    const pad = 44;
    const plotWidth = Math.max(width - pad * 2, 1);
    const plotHeight = Math.max(height - pad * 2, 1);
    if ((payload.projection || "3d") === "2d" || (payload.world?.dimension || 2) === 2) {
      const sx = (x - min[0]) / Math.max(max[0] - min[0], 0.001);
      const sy = (y - min[1]) / Math.max(max[1] - min[1], 0.001);
      return {
        x: pad + sx * plotWidth,
        y: height - pad - sy * plotHeight,
        depth: z,
      };
    }
    const nx = ((x - min[0]) / Math.max(max[0] - min[0], 0.001)) * 2 - 1;
    const ny = ((y - min[1]) / Math.max(max[1] - min[1], 0.001)) * 2 - 1;
    const nz = ((z - min[2]) / Math.max(max[2] - min[2], 0.001)) * 2 - 1;
    const yaw = toRadians(this.cameraYaw);
    const pitch = toRadians(this.cameraPitch);
    const cosYaw = Math.cos(yaw);
    const sinYaw = Math.sin(yaw);
    const cosPitch = Math.cos(pitch);
    const sinPitch = Math.sin(pitch);
    const rx = nx * cosYaw - ny * sinYaw;
    const ry = nx * sinYaw + ny * cosYaw;
    const rz = nz;
    const sy = ry * cosPitch - rz * sinPitch;
    const depth = ry * sinPitch + rz * cosPitch;
    const scale = Math.min(plotWidth, plotHeight) * 0.34;
    return {
      x: width * 0.5 + rx * scale,
      y: height * 0.55 - sy * scale,
      depth,
    };
  }

  interpolateWorldPoint(tx, ty, tz, payload) {
    const min = this.bounds.min;
    const max = this.bounds.max;
    return [
      min[0] + (max[0] - min[0]) * tx,
      min[1] + (max[1] - min[1]) * ty,
      min[2] + (max[2] - min[2]) * tz,
    ];
  }
}

function drawArrowHead(ctx, x1, y1, x2, y2, size) {
  const angle = Math.atan2(y2 - y1, x2 - x1);
  ctx.beginPath();
  ctx.moveTo(x2, y2);
  ctx.lineTo(x2 - size * Math.cos(angle - Math.PI / 6), y2 - size * Math.sin(angle - Math.PI / 6));
  ctx.lineTo(x2 - size * Math.cos(angle + Math.PI / 6), y2 - size * Math.sin(angle + Math.PI / 6));
  ctx.closePath();
  ctx.fill();
}

function teamColor(team, role) {
  if (team === "red") {
    return "rgba(239, 177, 92, 0.96)";
  }
  if (team === "blue") {
    return "rgba(86, 214, 230, 0.96)";
  }
  if (role === "asset") {
    return "rgba(112, 219, 152, 0.96)";
  }
  return "rgba(212, 223, 231, 0.92)";
}

function toRadians(value) {
  return (Number(value) * Math.PI) / 180;
}

function renderScenarioContextSafeAgain() {}

// Keep the interface responsive after the initial async boot sequence.
setInterval(() => {
  if (state.loading) {
    dom.connectionStatus.dataset.tone = "warn";
  }
}, 1500);
