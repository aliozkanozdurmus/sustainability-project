from __future__ import annotations

import time
from typing import Any

from .client import ConnectorAgentApiClient
from .config import AgentSettings


class ConnectorAgentCore:
    def __init__(self, settings: AgentSettings) -> None:
        self.settings = settings
        self.client = ConnectorAgentApiClient(settings)
        self.agent_id: str | None = None

    def ensure_registered(self) -> str:
        payload = self.client.register_agent()
        self.agent_id = str(payload["agent_id"])
        return self.agent_id

    def run_once(self) -> dict[str, Any] | None:
        agent_id = self.agent_id or self.ensure_registered()
        self.client.heartbeat(agent_id)
        claimed = self.client.claim_next(agent_id)
        operation = claimed.get("operation")
        if not isinstance(operation, dict):
            return None
        integration_id = str(operation["integration_config_id"])
        operation_id = str(operation["operation_id"])
        self.client.heartbeat(agent_id, active_operation_id=operation_id)
        result = self.client.execute_operation(
            integration_id=integration_id,
            operation_id=operation_id,
            preview_limit=20,
        )
        self.client.heartbeat(agent_id)
        return result

    def run_forever(self) -> None:
        while True:
            try:
                result = self.run_once()
                if result:
                    print(
                        f"[connector-agent] executed operation={result.get('operation_id')} status={result.get('status')}",
                        flush=True,
                    )
            except Exception as exc:  # pragma: no cover - operational loop fallback
                print(f"[connector-agent] loop error: {exc}", flush=True)
            time.sleep(self.settings.poll_interval_seconds)

