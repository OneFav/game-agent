from __future__ import annotations

import csv
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from game_agent.visualization.repository import RepositoryError, RunRepository
from game_agent.visualization.executor import AgentRuntimeUnavailable, ProjectExecutor
from game_agent.visualization.workbench import WorkbenchStore
from game_agent.utils.fs import read_json, read_yaml


class ViewerRequestHandler(BaseHTTPRequestHandler):
    repository: RunRepository
    workbench: WorkbenchStore
    executor: ProjectExecutor
    static_root: Path

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler protocol
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/health":
                self._send_json({"status": "ok", "agent": self.executor.status()})
                return
            if parsed.path.startswith("/api/"):
                self._handle_api(parsed.path, parse_qs(parsed.query))
                return
            self._serve_static(parsed.path)
        except RepositoryError as error:
            self._send_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
        except AgentRuntimeUnavailable as error:
            self._send_json(
                {
                    "error": str(error),
                    "code": "agent_runtime_unavailable",
                    "agent": error.status,
                },
                HTTPStatus.SERVICE_UNAVAILABLE,
            )
        except (TypeError, ValueError) as error:
            self._send_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
        except FileNotFoundError:
            self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)

    def do_HEAD(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler protocol
        try:
            self._serve_static(urlparse(self.path).path, head_only=True)
        except FileNotFoundError:
            self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler protocol
        parsed = urlparse(self.path)
        try:
            self._handle_post(parsed.path, self._read_json_body())
        except RepositoryError as error:
            self._send_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
        except AgentRuntimeUnavailable as error:
            self._send_json(
                {
                    "error": str(error),
                    "code": "agent_runtime_unavailable",
                    "agent": error.status,
                },
                HTTPStatus.SERVICE_UNAVAILABLE,
            )
        except (TypeError, ValueError) as error:
            self._send_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
        except FileNotFoundError:
            self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)

    def do_PUT(self) -> None:  # noqa: N802
        self._method_not_allowed()

    do_PATCH = do_PUT
    do_DELETE = do_PUT

    def _handle_api(self, path: str, query: dict[str, list[str]]) -> None:
        if path == "/api/projects":
            self._send_json({"projects": self._list_projects()})
            return
        project_prefix = "/api/projects/"
        if path.startswith(project_prefix):
            remainder = unquote(path[len(project_prefix) :])
            parts = remainder.split("/")
            if len(parts) == 1 and parts[0]:
                self._send_json(self._load_project(parts[0]))
                return
            if len(parts) == 2 and parts[0] and parts[1] == "events":
                self._assert_project(parts[0])
                self._send_json(
                    {
                        "project_id": parts[0],
                        "events": self.workbench.list_events(parts[0]),
                    }
                )
                return
            raise RepositoryError("invalid project API path")
        if path == "/api/scenarios":
            self._send_json({"scenarios": self.repository.list_scenarios()})
            return
        prefix = "/api/scenarios/"
        if not path.startswith(prefix):
            raise FileNotFoundError
        remainder = unquote(path[len(prefix) :])
        parts = remainder.split("/")
        if len(parts) == 1 and parts[0]:
            self._send_json(self.repository.load_descriptor(parts[0]))
            return
        if len(parts) != 2 or not parts[0]:
            raise RepositoryError("invalid scenario API path")
        scenario_id, resource = parts
        if resource == "visualization":
            self._send_json(self.repository.load_visualization(scenario_id))
            return
        if resource == "replays":
            self._send_json(self.repository.load_replay_index(scenario_id))
            return
        if resource == "frames":
            role = _single_query(query, "role", "candidate")
            seed = int(_single_query(query, "seed", "0"))
            start = int(_single_query(query, "start", "0"))
            limit = int(_single_query(query, "limit", "200"))
            self._send_json(
                self.repository.load_frames(
                    scenario_id, role, seed, start=start, limit=limit
                )
            )
            return
        raise FileNotFoundError

    def _handle_post(self, path: str, payload: dict[str, Any]) -> None:
        if path == "/api/projects":
            self.executor.require_ready()
            project = self.workbench.create_project(
                payload.get("title", ""), payload.get("goal", "")
            )
            self.executor.start(project["project_id"])
            self._send_json(project, HTTPStatus.CREATED)
            return
        prefix = "/api/projects/"
        if not path.startswith(prefix):
            self._method_not_allowed()
            return
        remainder = unquote(path[len(prefix) :])
        parts = remainder.split("/")
        if len(parts) != 2 or not parts[0] or parts[1] != "interventions":
            self._method_not_allowed()
            return
        project_id = parts[0]
        self._assert_project(project_id)
        action = payload.get("action")
        details = payload.get("payload", {})
        if not isinstance(action, str):
            raise ValueError("intervention action must be a string")
        if not isinstance(details, dict):
            raise ValueError("intervention payload must be an object")
        if (
            action == "resume"
            and self.workbench.load_local_project(project_id) is not None
        ):
            self.executor.require_ready()
        event = self.workbench.append_intervention(project_id, action, details)
        if self.workbench.load_local_project(project_id) is not None:
            self.executor.intervene(project_id, action, details)
        self._send_json({"event": event}, HTTPStatus.CREATED)

    def _list_projects(self) -> list[dict[str, Any]]:
        projects = list(self.workbench.list_local_projects())
        for scenario in self.repository.list_scenarios():
            projects.append(
                {
                    **scenario,
                    "project_id": scenario["scenario_id"],
                    "title": f"{scenario['scenario_id']} {scenario['name']}",
                    "status": "attention" if scenario.get("attention") else "complete",
                    "execution_mode": "autonomous",
                }
            )
        return projects

    def _load_project(self, project_id: str) -> dict[str, Any]:
        local = self.workbench.load_local_project(project_id)
        if local is not None:
            return self._load_local_project_detail(local)
        project = self.repository.load_project(project_id)
        project["events"] = self.workbench.list_events(project_id)
        return project

    def _load_local_project_detail(self, project: dict[str, Any]) -> dict[str, Any]:
        project_id = str(project["project_id"])
        events = self.workbench.list_events(project_id)
        artifacts = project.get("artifacts", {})
        if not isinstance(artifacts, dict):
            artifacts = {}
        method = _local_method(self.repository.project_root, artifacts)
        results = _local_results(self.repository.project_root, artifacts)
        agent_result = _local_agent_result(self.repository.project_root, artifacts)
        if agent_result is not None:
            raw_method = agent_result.get("method")
            if isinstance(raw_method, dict):
                method = raw_method
            results = {
                "primary_metric": agent_result.get("primary_metric"),
                "metric_series": agent_result.get("metric_series", {}),
                "constraint_evidence": agent_result.get(
                    "constraint_evidence", []
                ),
                "comparison": agent_result.get("comparison", {}),
            }
        return {
            **project,
            "workflow": _local_workflow(events, str(project.get("status", "active"))),
            "method": method,
            "primary_metric": results["primary_metric"],
            "metric_series": results["metric_series"],
            "constraint_evidence": results["constraint_evidence"],
            "comparison": results["comparison"],
            "outcome": (
                agent_result.get("objective_status")
                if agent_result is not None
                else project.get("outcome")
            ),
            "agent_summary": (
                agent_result.get("summary")
                if agent_result is not None
                else project.get("agent_summary")
            ),
            "agent_activity": _local_agent_activity(events),
            "available_interventions": [
                "change_method",
                "adjust_budget",
                "pause",
                "resume",
                "stop",
                "message",
            ],
            "events": events,
        }

    def _assert_project(self, project_id: str) -> None:
        if self.workbench.load_local_project(project_id) is not None:
            return
        self.repository.load_project(project_id)

    def _read_json_body(self) -> dict[str, Any]:
        raw_length = self.headers.get("Content-Length", "0")
        try:
            length = int(raw_length)
        except ValueError as error:
            raise ValueError("invalid Content-Length") from error
        if length < 0 or length > 64_000:
            raise ValueError("request body is too large")
        raw = self.rfile.read(length)
        if not raw:
            return {}
        value = json.loads(raw.decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("request body must be a JSON object")
        return value

    def _serve_static(self, path: str, *, head_only: bool = False) -> None:
        relative = (
            "index.html"
            if path in {"", "/", "/index.html"}
            else unquote(path).lstrip("/")
        )
        requested = (self.static_root / relative).resolve()
        if not requested.is_relative_to(self.static_root) or not requested.is_file():
            raise FileNotFoundError
        content_type = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "text/javascript; charset=utf-8",
            ".svg": "image/svg+xml",
        }.get(requested.suffix.lower(), "application/octet-stream")
        content = requested.read_bytes()
        self.send_response(HTTPStatus.OK)
        self._security_headers()
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        if not head_only:
            self.wfile.write(content)

    def _send_json(
        self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK
    ) -> None:
        content = json.dumps(
            payload, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
        self.send_response(status)
        self._security_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _method_not_allowed(self) -> None:
        self._send_json(
            {"error": "viewer API is read-only"}, HTTPStatus.METHOD_NOT_ALLOWED
        )

    def _security_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; connect-src 'self'",
        )

    def log_message(self, format: str, *args: object) -> None:
        return


def create_viewer_server(
    project_root: Path,
    run_root: Path,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    execute_projects: bool = True,
) -> ThreadingHTTPServer:
    repository = RunRepository(project_root, run_root)
    workbench = WorkbenchStore(project_root, run_root)
    executor = ProjectExecutor(project_root, workbench, enabled=execute_projects)
    static_root = (Path(__file__).parent / "static").resolve()
    if not static_root.is_dir():
        raise FileNotFoundError(f"viewer static assets are missing: {static_root}")

    class BoundViewerRequestHandler(ViewerRequestHandler):
        pass

    BoundViewerRequestHandler.repository = repository
    BoundViewerRequestHandler.workbench = workbench
    BoundViewerRequestHandler.executor = executor
    BoundViewerRequestHandler.static_root = static_root
    server = ThreadingHTTPServer((host, port), BoundViewerRequestHandler)
    executor.resume_pending()
    return server


def serve_viewer(
    project_root: Path,
    run_root: Path,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
) -> None:
    server = create_viewer_server(project_root, run_root, host=host, port=port)
    print(f"workbench: http://{host}:{server.server_port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def _single_query(
    query: dict[str, list[str]], key: str, default: str
) -> str:
    values = query.get(key)
    if not values:
        return default
    if len(values) != 1:
        raise RepositoryError(f"query parameter {key} must occur once")
    return values[0]


def _local_workflow(
    events: list[dict[str, Any]], project_status: str
) -> list[dict[str, str]]:
    labels = [
        ("goal", "定义目标"),
        ("scenario", "构造环境"),
        ("method", "选择方法"),
        ("run", "运行"),
        ("evaluate", "评估"),
    ]
    completed = {"goal"}
    entered: list[str] = []
    for event in events:
        payload = event.get("payload", {})
        node_id = payload.get("node_id") if isinstance(payload, dict) else None
        if not isinstance(node_id, str):
            continue
        if event.get("event_type") == "node.entered":
            entered.append(node_id)
        elif event.get("event_type") == "node.completed":
            completed.add(node_id)
    active = next((node for node in reversed(entered) if node not in completed), None)
    if active is None and project_status in {"active", "paused"}:
        active = next((node_id for node_id, _ in labels if node_id not in completed), None)
    workflow: list[dict[str, str]] = []
    for node_id, label in labels:
        status = "complete" if node_id in completed else "pending"
        if node_id == active:
            status = "attention" if project_status == "error" else "active"
        workflow.append({"id": node_id, "label": label, "status": status})
    return workflow


def _local_method(project_root: Path, artifacts: dict[str, Any]) -> dict[str, Any]:
    policy = _artifact_dir(project_root, artifacts.get("policy"))
    metadata_path = policy / "metadata.json" if policy is not None else None
    if metadata_path is None or not metadata_path.is_file():
        return {"name": "Agent 正在选择", "family": "pending", "policy_id": None}
    metadata = read_json(metadata_path)
    method = metadata.get("method", {})
    if not isinstance(method, dict):
        method = {}
    return {
        "name": method.get("name", metadata.get("policy_type", policy.name)),
        "family": method.get("family", "unknown"),
        "policy_id": metadata.get("policy_id", policy.name),
        "selection_rationale": method.get("selection_rationale"),
    }


def _local_results(project_root: Path, artifacts: dict[str, Any]) -> dict[str, Any]:
    empty = {
        "primary_metric": None,
        "comparison": {},
        "metric_series": {},
        "constraint_evidence": [],
    }
    scenario = _artifact_dir(project_root, artifacts.get("scenario"))
    experiment = _artifact_dir(project_root, artifacts.get("experiment"))
    if scenario is None or experiment is None:
        return empty
    spec_path = scenario / "task_spec.yaml"
    leaderboard_path = experiment / "leaderboard.csv"
    if not spec_path.is_file() or not leaderboard_path.is_file():
        return empty
    spec = read_yaml(spec_path)
    evaluation = spec.get("evaluation_metrics", {})
    primary = evaluation.get("primary", {}) if isinstance(evaluation, dict) else {}
    primary_metric = primary.get("name") if isinstance(primary, dict) else None
    if not isinstance(primary_metric, str):
        return empty
    with leaderboard_path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        return empty
    candidate_values = [
        _float_or_none(row.get(primary_metric)) for row in rows
    ]
    candidate_values = [value for value in candidate_values if value is not None]
    candidate = candidate_values[0] if candidate_values else None
    baseline_path = experiment / "baseline_metrics.json"
    baseline_payload = read_json(baseline_path) if baseline_path.is_file() else {}
    baseline_metrics = baseline_payload.get("metrics", baseline_payload)
    baseline = (
        _float_or_none(baseline_metrics.get(primary_metric))
        if isinstance(baseline_metrics, dict)
        else None
    )
    constraints = evaluation.get("hard_constraints", []) if isinstance(evaluation, dict) else []
    evidence: list[dict[str, Any]] = []
    best = rows[0]
    if isinstance(constraints, list):
        for constraint in constraints:
            if not isinstance(constraint, dict):
                continue
            name = constraint.get("name")
            limit = constraint.get("max")
            value = _float_or_none(best.get(name)) if isinstance(name, str) else None
            if isinstance(value, float) and isinstance(limit, (int, float)) and value > float(limit):
                evidence.append(
                    {"metric": name, "label": str(name).replace("_", " "), "value": value, "limit": float(limit)}
                )
    constraints_passed = not evidence
    return {
        "primary_metric": primary_metric,
        "comparison": {
            "baseline_mean": baseline,
            "candidate_mean": candidate,
            "delta": candidate - baseline if candidate is not None and baseline is not None else None,
            "constraints_passed": constraints_passed,
            "promoted": bool(
                constraints_passed
                and candidate is not None
                and baseline is not None
                and candidate > baseline
            ),
        },
        "metric_series": {
            "baseline": [
                {"step": float(index), "time": float(index), "value": baseline}
                for index in range(len(candidate_values))
                if baseline is not None
            ],
            "candidate": [
                {"step": float(index), "time": float(index), "value": value}
                for index, value in enumerate(candidate_values)
            ],
        },
        "constraint_evidence": evidence,
    }


def _local_agent_result(
    project_root: Path, artifacts: dict[str, Any]
) -> dict[str, Any] | None:
    experiment = _artifact_dir(project_root, artifacts.get("experiment"))
    result_path = experiment / "agent_result.json" if experiment is not None else None
    if result_path is None or not result_path.is_file():
        return None
    result = read_json(result_path)
    if result.get("schema_version") != "autogame_agent_result/v1":
        return None
    return result


def _local_agent_activity(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    activities: list[dict[str, Any]] = []
    for event in events:
        event_type = str(event.get("event_type", ""))
        if event_type not in {
            "execution.activity",
            "execution.agent_message",
            "execution.failed",
        }:
            continue
        payload = event.get("payload")
        if isinstance(payload, dict):
            activities.append(
                {
                    "event_type": event_type,
                    "created_at": event.get("created_at"),
                    **payload,
                }
            )
    return activities[-30:]


def _artifact_dir(project_root: Path, value: Any) -> Path | None:
    if not isinstance(value, str):
        return None
    resolved = (project_root / value).resolve()
    if not resolved.is_relative_to(project_root) or not resolved.is_dir():
        return None
    return resolved


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
