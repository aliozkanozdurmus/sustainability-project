from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Literal, Protocol, TypedDict
from uuid import uuid4

from app.core.settings import settings
from app.orchestration.state import NodeName, WorkflowState


CheckpointStatus = Literal["completed", "failed"]


class CheckpointRecord(TypedDict):
    checkpoint_id: str
    run_id: str
    node: NodeName
    status: CheckpointStatus
    created_at_utc: str
    state: WorkflowState
    metadata: dict[str, Any]


class CheckpointStore(Protocol):
    def save_checkpoint(
        self,
        *,
        run_id: str,
        node: NodeName,
        status: CheckpointStatus,
        state: WorkflowState,
        metadata: dict[str, Any] | None = None,
    ) -> CheckpointRecord: ...

    def load_latest_checkpoint(self, *, run_id: str) -> CheckpointRecord | None: ...

    def list_checkpoints(self, *, run_id: str) -> list[CheckpointRecord]: ...


def _state_copy(state: WorkflowState) -> WorkflowState:
    return json.loads(json.dumps(state, ensure_ascii=True))


@dataclass
class LocalJsonlCheckpointStore:
    root_path: Path

    def _target_path(self, run_id: str) -> Path:
        safe_run_id = run_id.replace("/", "_")
        return self.root_path / f"{safe_run_id}.jsonl"

    def save_checkpoint(
        self,
        *,
        run_id: str,
        node: NodeName,
        status: CheckpointStatus,
        state: WorkflowState,
        metadata: dict[str, Any] | None = None,
    ) -> CheckpointRecord:
        self.root_path.mkdir(parents=True, exist_ok=True)
        record: CheckpointRecord = {
            "checkpoint_id": str(uuid4()),
            "run_id": run_id,
            "node": node,
            "status": status,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "state": _state_copy(state),
            "metadata": metadata or {},
        }
        target = self._target_path(run_id)
        with target.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=True))
            fh.write("\n")
        return record

    def load_latest_checkpoint(self, *, run_id: str) -> CheckpointRecord | None:
        records = self.list_checkpoints(run_id=run_id)
        if not records:
            return None
        return records[-1]

    def list_checkpoints(self, *, run_id: str) -> list[CheckpointRecord]:
        target = self._target_path(run_id)
        if not target.exists():
            return []
        records: list[CheckpointRecord] = []
        for line in target.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            parsed = json.loads(line)
            if isinstance(parsed, dict):
                records.append(parsed)  # type: ignore[arg-type]
        return records


def get_checkpoint_store() -> CheckpointStore:
    return LocalJsonlCheckpointStore(root_path=settings.local_checkpoint_root_path)
