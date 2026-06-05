from fastapi import Header, HTTPException, status


ROLE_PERMISSIONS = {
    "admin": {"*"},
    "operator": {
        "topics:approve",
        "reviews:final",
        "reports:read",
        "calendar:write",
        "wechat:create_draft",
    },
    "editor": {
        "articles:import",
        "articles:search",
        "topics:generate",
        "workspace:write",
        "reviews:submit",
    },
    "reviewer": {"reviews:submit", "risk:read", "articles:search"},
}


def get_actor(x_user: str = Header(default="系统用户"), x_role: str = Header(default="admin")) -> dict[str, str]:
    return {"user": x_user, "role": x_role}


def require_permission(permission: str):
    def dependency(actor: dict[str, str] = Header(default=None)):  # type: ignore[assignment]
        return actor

    async def checker(x_user: str = Header(default="系统用户"), x_role: str = Header(default="admin")) -> dict[str, str]:
        permissions = ROLE_PERMISSIONS.get(x_role, set())
        if "*" not in permissions and permission not in permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role {x_role} lacks permission {permission}",
            )
        return {"user": x_user, "role": x_role}

    return checker

