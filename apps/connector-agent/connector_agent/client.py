from __future__ import annotations

import json
from typing import Any
from urllib import request

from .config import AgentSettings


class ConnectorAgentApiClient:
    def __init__(self, settings: AgentSettings) -> None:
        self.settings = settings

    def _headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "x-user-role": self.settings.user_role,
            "x-user-id": self.settings.user_id,
        }
        if self.settings.tenant_id:
            headers["x-tenant-id"] = self.settings.tenant_id
        return headers

    def _request_json(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        body = json.dumps(payload or {}).encode("utf-8")
        req = request.Request(
            url=f"{self.settings.api_base_url}{path}",
            data=body,
            headers=self._headers(),
            method=method,
        )
        with request.urlopen(req, timeout=30) as response:
            raw = response.read().decode("utf-8")
        return json.loads(raw) if raw else {}

    def register_agent(self) -> dict[str, Any]:
        return self._request_json(
            "POST",
            "/integrations/agents/register",
            {
                "tenant_id": self.settings.tenant_id,
                "project_id": self.settings.project_id,
                "agent_key": self.settings.agent_key,
                "display_name": self.settings.display_name,
                "agent_kind": self.settings.agent_kind,
                "supported_connectors": self.settings.supported_connectors,
                "capabilities": self.settings.capabilities,
            },
        )

    def heartbeat(self, agent_id: str, *, active_operation_id: str | None = None) -> dict[str, Any]:
        return self._request_json(
            "POST",
            f"/integrations/agents/{agent_id}/heartbeat",
            {
                "status": "online",
                "active_operation_id": active_operation_id,
                "metrics": {"poll_interval_seconds": self.settings.poll_interval_seconds},
            },
        )

    def claim_next(self, agent_id: str) -> dict[str, Any]:
        return self._request_json("POST", f"/integrations/agents/{agent_id}/claim-next", {})

    def execute_operation(
        self,
        *,
        integration_id: str,
        operation_id: str,
        preview_limit: int = 20,
        backfill_window_days: int | None = None,
    ) -> dict[str, Any]:
        query = f"?preview_limit={preview_limit}"
        if backfill_window_days is not None:
            query += f"&backfill_window_days={backfill_window_days}"
        return self._request_json(
            "POST",
            f"/integrations/connectors/{integration_id}/operations/{operation_id}/execute{query}",
            {},
        )

