from pydantic import BaseModel, Field

from app.auth.roles import Role


class CurrentUser(BaseModel):
    user_id: str = Field(min_length=1)
    role: Role
    tenant_id: str = Field(min_length=1)


class AuthorizationDecision(BaseModel):
    allowed: bool
    required_roles: list[Role]

