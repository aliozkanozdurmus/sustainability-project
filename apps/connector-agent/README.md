# Connector Agent

Outbound-only customer-network connector agent for SAP OData, Logo Tiger SQL View, and Netsis REST onboarding flows.

Core capabilities:
- agent register and heartbeat
- queued operation claim
- backend-triggered execution for discover, preflight, preview sync, replay, and support bundle
- shared core for Docker and Windows runner entrypoints

Required environment variables:
- `CONNECTOR_AGENT_API_BASE_URL`
- `CONNECTOR_AGENT_KEY`
- `CONNECTOR_AGENT_DISPLAY_NAME`

Optional environment variables:
- `CONNECTOR_AGENT_TENANT_ID`
- `CONNECTOR_AGENT_PROJECT_ID`
- `CONNECTOR_AGENT_KIND`
- `CONNECTOR_AGENT_SUPPORTED_CONNECTORS`
- `CONNECTOR_AGENT_CAPABILITIES`
- `CONNECTOR_AGENT_POLL_INTERVAL_SECONDS`
- `CONNECTOR_AGENT_USER_ROLE`
- `CONNECTOR_AGENT_USER_ID`

