"""
Role-based Access Control (RBAC) definitions.
"""
from enum import Enum
from typing import List
from fastapi import Depends, HTTPException
from .jwt_auth import JWTMiddleware, TokenPayload

class SecurityScope(str, Enum):
    """Available token scopes"""
    TOOL_INVOKE = "tool.invoke"
    TOOL_INVOKE_ELEVATED = "tool.invoke.elevated"
    SYSTEM_READ = "system.read"
    SYSTEM_WRITE = "system.write"

class Role(str, Enum):
    """User/Agent roles mapping to risk levels in tools map."""
    VIEWER = "viewer"
    TOOL_CALLER = "tool_caller" 
    HIGH_RISK_TOOL = "high_risk_tool"
    ADMIN = "admin"

def require_scope(required_scope: str):
    """FastAPI dependency generator for required token scopes"""
    async def _check_scope(token: TokenPayload = Depends(JWTMiddleware())):
        if required_scope not in token.scopes:
            raise HTTPException(
                status_code=403, 
                detail=f"Forbidden: insufficient scope. Requires '{required_scope}'"
            )
        return token
    return _check_scope

def get_required_scope_for_tool(risk_level: str) -> str:
    """Map tool risk level to the JWT scope required to invoke it."""
    if risk_level == "high":
        return SecurityScope.TOOL_INVOKE_ELEVATED.value
    return SecurityScope.TOOL_INVOKE.value
