from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class AgentSettings:
    api_base_url: str
    agent_key: str
    display_name: str
    tenant_id: str | None
    project_id: str | None
    agent_kind: str
    supported_connectors: list[str]
    capabilities: list[str]
    poll_interval_seconds: int
    user_role: str
    user_id: str

    @classmethod
    def from_env(cls) -> "AgentSettings":
        def _split(name: str, default: str) -> list[str]:
            raw = os.getenv(name, default)
            return [item.strip() for item in raw.split(",") if item.strip()]

        return cls(
            api_base_url=os.environ["CONNECTOR_AGENT_API_BASE_URL"].rstrip("/"),
            agent_key=os.environ["CONNECTOR_AGENT_KEY"],
            display_name=os.environ["CONNECTOR_AGENT_DISPLAY_NAME"],
            tenant_id=os.getenv("CONNECTOR_AGENT_TENANT_ID"),
            project_id=os.getenv("CONNECTOR_AGENT_PROJECT_ID"),
            agent_kind=os.getenv("CONNECTOR_AGENT_KIND", "docker"),
            supported_connectors=_split(
                "CONNECTOR_AGENT_SUPPORTED_CONNECTORS",
                "sap_odata,logo_tiger_sql_view,netsis_rest",
            ),
            capabilities=_split(
                "CONNECTOR_AGENT_CAPABILITIES",
                "discover,preflight,preview_sync,replay,support_bundle",
            ),
            poll_interval_seconds=int(os.getenv("CONNECTOR_AGENT_POLL_INTERVAL_SECONDS", "15")),
            user_role=os.getenv("CONNECTOR_AGENT_USER_ROLE", "admin"),
            user_id=os.getenv("CONNECTOR_AGENT_USER_ID", "connector-agent"),
        )

