# Bu yetkilendirme modulu, roles kararlarini merkezi hale getirir.

from typing import Literal

Role = Literal[
    "admin",
    "compliance_manager",
    "analyst",
    "board_member",
    "committee_secretary",
    "auditor_readonly",
]

ALL_ROLES: tuple[Role, ...] = (
    "admin",
    "compliance_manager",
    "analyst",
    "board_member",
    "committee_secretary",
    "auditor_readonly",
)

