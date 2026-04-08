from __future__ import annotations

from .config import AgentSettings
from .core import ConnectorAgentCore


def main() -> None:
    # Bu giris noktasi, Windows Service wrapper'lari tarafindan cagrilabilecek sade loop'u saglar.
    ConnectorAgentCore(AgentSettings.from_env()).run_forever()


if __name__ == "__main__":
    main()
