from __future__ import annotations

import json
import threading
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from game_agent.visualization.service import create_viewer_server
from test_visualization_repository import _write_run


def test_viewer_service_serves_static_assets_and_read_only_api(
    tmp_path: Path,
) -> None:
    run_dir = _write_run(tmp_path)
    server = create_viewer_server(tmp_path, run_dir, port=0, execute_projects=False)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        health = _get_json(f"{base_url}/health")
        scenarios = _get_json(f"{base_url}/api/scenarios")
        projects = _get_json(f"{base_url}/api/projects")
        project = _get_json(f"{base_url}/api/projects/S01")
        frames = _get_json(
            f"{base_url}/api/scenarios/S01/frames?role=candidate&seed=0&start=1&limit=1"
        )
        with urlopen(f"{base_url}/", timeout=2) as response:
            html = response.read().decode("utf-8")

        assert health["status"] == "ok"
        assert health["agent"]["ready"] is False
        assert health["agent"]["fallback_enabled"] is False
        assert scenarios["scenarios"][0]["scenario_id"] == "S01"
        assert projects["projects"][0]["project_id"] == "S01"
        assert project["execution_mode"] == "autonomous"
        assert frames["total"] == 2
        assert frames["frames"][0]["episode_step"] == 4
        assert "canvas" in html.lower()

        request = Request(f"{base_url}/api/scenarios", method="POST", data=b"{}")
        try:
            urlopen(request, timeout=2)
            raise AssertionError("POST must be rejected")
        except HTTPError as error:
            assert error.code == 405
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_workbench_creates_projects_and_appends_interventions(tmp_path: Path) -> None:
    run_dir = _write_run(tmp_path)
    from game_agent.visualization.workbench import WorkbenchStore

    store = WorkbenchStore(tmp_path, run_dir)
    created = store.create_project("延迟策略实验", "比较两种策略")
    server = create_viewer_server(tmp_path, run_dir, port=0, execute_projects=False)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        project_id = str(created["project_id"])
        intervention = _post_json(
            f"{base_url}/api/projects/{project_id}/interventions",
            {"action": "pause", "payload": {"reason": "检查预算"}},
        )
        events = _get_json(f"{base_url}/api/projects/{project_id}/events")

        assert intervention["event"]["event_type"] == "human.pause"
        assert [event["event_type"] for event in events["events"]] == [
            "project.created",
            "workflow.declared",
            "human.pause",
        ]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_workbench_rejects_new_project_without_codex_runtime(tmp_path: Path) -> None:
    run_dir = _write_run(tmp_path)
    server = create_viewer_server(tmp_path, run_dir, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        body = json.dumps(
            {"title": "必须由 Agent 执行", "goal": "不得使用固定规则回退"}
        ).encode("utf-8")
        request = Request(
            f"{base_url}/api/projects",
            method="POST",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        try:
            urlopen(request, timeout=2)
            raise AssertionError("project creation must fail without Codex runtime")
        except HTTPError as error:
            payload = json.loads(error.read().decode("utf-8"))
            assert error.code == 503
            assert payload["code"] == "agent_runtime_unavailable"
            assert payload["agent"]["fallback_enabled"] is False
            assert "M1 固定规则回退已禁用" in payload["error"]

        assert _get_json(f"{base_url}/api/projects")["projects"][0]["project_id"] == "S01"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_viewer_service_rejects_invalid_scenario_paths(tmp_path: Path) -> None:
    run_dir = _write_run(tmp_path)
    server = create_viewer_server(tmp_path, run_dir, port=0, execute_projects=False)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/api/scenarios/%2e%2e%2fS01"
        try:
            urlopen(url, timeout=2)
            raise AssertionError("path traversal must be rejected")
        except HTTPError as error:
            assert 400 <= error.code < 500
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _get_json(url: str) -> dict[str, object]:
    with urlopen(url, timeout=2) as response:
        return json.loads(response.read().decode("utf-8"))


def _post_json(url: str, payload: dict[str, object]) -> dict[str, object]:
    body = json.dumps(payload).encode("utf-8")
    request = Request(
        url,
        method="POST",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    with urlopen(request, timeout=2) as response:
        return json.loads(response.read().decode("utf-8"))
