from __future__ import annotations

from .config import AgentSettings
from .core import ConnectorAgentCore


def main() -> None:
    ConnectorAgentCore(AgentSettings.from_env()).run_forever()


if __name__ == "__main__":
    main()

