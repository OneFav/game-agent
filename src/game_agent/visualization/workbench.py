from __future__ import annotations

import json
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from game_agent.utils.fs import read_json, write_json


_PROJECT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_INTERVENTIONS = {
    "adjust_budget",
    "change_method",
    "message",
    "pause",
    "resume",
    "rerun",
    "stop",
}


class WorkbenchStore:
    """Local product state kept separate from immutable experiment facts."""

    def __init__(self, project_root: Path, run_root: Path) -> None:
        self.project_root = Path(project_root).resolve()
        run_name = re.sub(r"[^A-Za-z0-9_.-]+", "-", Path(run_root).name).strip("-")
        self.root = self.project_root / ".autogame" / "workbench" / (run_name or "default")
        self.projects_path = self.root / "projects.json"
        self.events_root = self.root / "events"
        self._lock = threading.Lock()

    def list_local_projects(self) -> list[dict[str, Any]]:
        projects = self._load_projects().get("projects", [])
        if not isinstance(projects, list):
            return []
        return [dict(item) for item in projects if isinstance(item, dict)]

    def load_local_project(self, project_id: str) -> dict[str, Any] | None:
        self._validate_project_id(project_id)
        for project in self.list_local_projects():
            if project.get("project_id") == project_id:
                return project
        return None

    def create_project(self, title: str, goal: str) -> dict[str, Any]:
        title = _clean_text(title, "项目标题", maximum=120)
        goal = _clean_text(goal, "项目目标", maximum=4_000)
        now = _utc_now()
        project = {
            "project_id": f"local-{uuid.uuid4().hex[:12]}",
            "title": title,
            "goal": goal,
            "source_kind": "local",
            "status": "active",
            "execution_mode": "autonomous",
            "created_at": now,
            "updated_at": now,
        }
        with self._lock:
            payload = self._load_projects()
            projects = payload.setdefault("projects", [])
            if not isinstance(projects, list):
                projects = []
                payload["projects"] = projects
            projects.insert(0, project)
            write_json(self.projects_path, payload)
            self._append_event_unlocked(
                project["project_id"],
                "project.created",
                {"title": title, "goal": goal},
            )
            self._append_event_unlocked(
                project["project_id"],
                "workflow.declared",
                {"execution_mode": "autonomous"},
            )
        return project

    def update_project(self, project_id: str, **changes: Any) -> dict[str, Any]:
        self._validate_project_id(project_id)
        allowed = {
            "active_turn_id",
            "agent_summary",
            "agent_thread_id",
            "artifacts",
            "error",
            "outcome",
            "status",
            "updated_at",
        }
        unexpected = set(changes) - allowed
        if unexpected:
            raise ValueError(f"unsupported project fields: {sorted(unexpected)}")
        with self._lock:
            payload = self._load_projects()
            projects = payload.get("projects", [])
            if not isinstance(projects, list):
                raise ValueError("local project store is invalid")
            for project in projects:
                if isinstance(project, dict) and project.get("project_id") == project_id:
                    project.update(changes)
                    project["updated_at"] = _utc_now()
                    write_json(self.projects_path, payload)
                    return dict(project)
        raise ValueError(f"unknown local project: {project_id}")

    def append_system_event(
        self, project_id: str, event_type: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        self._validate_project_id(project_id)
        if not isinstance(event_type, str) or not event_type.startswith(
            ("artifact.", "execution.", "node.")
        ):
            raise ValueError("invalid system event type")
        with self._lock:
            return self._append_event_unlocked(project_id, event_type, payload)

    def control_state(self, project_id: str) -> str:
        for event in reversed(self.list_events(project_id)):
            event_type = event.get("event_type")
            if event_type == "human.stop":
                return "stop"
            if event_type == "human.pause":
                return "pause"
            if event_type == "human.resume":
                return "run"
        return "run"

    def list_events(self, project_id: str) -> list[dict[str, Any]]:
        path = self._event_path(project_id)
        if not path.is_file():
            return []
        events: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(value, dict):
                    events.append(value)
        return events

    def append_intervention(
        self, project_id: str, action: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        self._validate_project_id(project_id)
        if action not in _INTERVENTIONS:
            raise ValueError(f"unsupported intervention: {action}")
        if not isinstance(payload, dict):
            raise ValueError("intervention payload must be an object")
        if len(json.dumps(payload, ensure_ascii=False)) > 8_000:
            raise ValueError("intervention payload is too large")
        with self._lock:
            return self._append_event_unlocked(
                project_id,
                f"human.{action}",
                payload,
            )

    def _append_event_unlocked(
        self, project_id: str, event_type: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        event = {
            "event_id": uuid.uuid4().hex,
            "project_id": project_id,
            "event_type": event_type,
            "created_at": _utc_now(),
            "payload": payload,
        }
        path = self._event_path(project_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")))
            handle.write("\n")
        return event

    def _load_projects(self) -> dict[str, Any]:
        if not self.projects_path.is_file():
            return {"schema_version": "autogame_projects/v1", "projects": []}
        return read_json(self.projects_path)

    def _event_path(self, project_id: str) -> Path:
        self._validate_project_id(project_id)
        return self.events_root / f"{project_id}.jsonl"

    @staticmethod
    def _validate_project_id(project_id: str) -> None:
        if not isinstance(project_id, str) or not _PROJECT_ID.fullmatch(project_id):
            raise ValueError("invalid project id")


def _clean_text(value: str, label: str, *, maximum: int) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label}必须是文本")
    cleaned = " ".join(value.split()).strip()
    if not cleaned:
        raise ValueError(f"{label}不能为空")
    if len(cleaned) > maximum:
        raise ValueError(f"{label}不能超过 {maximum} 个字符")
    return cleaned


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
