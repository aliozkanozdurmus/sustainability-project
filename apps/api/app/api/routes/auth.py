from fastapi import APIRouter, Depends

from app.auth.dependencies import get_current_user, require_roles
from app.schemas.auth import AuthorizationDecision, CurrentUser

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=CurrentUser)
async def read_current_user(
    user: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    return user


@router.get("/authorizations/publish", response_model=AuthorizationDecision)
async def can_publish(
    user: CurrentUser = Depends(require_roles("admin", "compliance_manager", "board_member")),
) -> AuthorizationDecision:
    return AuthorizationDecision(
        allowed=True,
        required_roles=["admin", "compliance_manager", "board_member"],
    )


@router.get("/authorizations/approval-center", response_model=AuthorizationDecision)
async def can_access_approval_center(
    user: CurrentUser = Depends(
        require_roles("admin", "compliance_manager", "committee_secretary", "board_member")
    ),
) -> AuthorizationDecision:
    return AuthorizationDecision(
        allowed=True,
        required_roles=["admin", "compliance_manager", "committee_secretary", "board_member"],
    )

