from collections.abc import Callable

from fastapi import Depends, Header, HTTPException, status

from app.auth.roles import ALL_ROLES, Role
from app.schemas.auth import CurrentUser


def _validate_role(raw_role: str) -> Role:
    if raw_role not in ALL_ROLES:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or unsupported role.",
        )
    return raw_role


def get_current_user(
    x_user_id: str | None = Header(default=None),
    x_user_role: str | None = Header(default=None),
    x_tenant_id: str | None = Header(default=None),
) -> CurrentUser:
    # Dev baseline until Entra/JWT wiring is added in later tasks.
    user_id = x_user_id or "dev-user"
    tenant_id = x_tenant_id or "dev-tenant"
    role = _validate_role(x_user_role or "analyst")
    return CurrentUser(user_id=user_id, role=role, tenant_id=tenant_id)


def require_roles(*roles: Role) -> Callable[[CurrentUser], CurrentUser]:
    required = set(roles)

    def dependency(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.role not in required:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient role permissions for this operation.",
            )
        return user

    return dependency

