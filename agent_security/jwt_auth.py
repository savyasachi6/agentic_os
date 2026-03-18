"""
JWT Authentication for the Agent OS components.
"""
import time
from typing import List, Optional
import jwt
from fastapi import Request, HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from agent_config import security_settings

class TokenPayload(BaseModel):
    sub: str
    scopes: List[str]
    exp: int

class JWTMiddleware(HTTPBearer):
    """FastAPI dependency to extract and validate JWT tokens."""
    def __init__(self):
        super().__init__(auto_error=True)

    async def __call__(self, request: Request) -> TokenPayload:
        cred: HTTPAuthorizationCredentials = await super().__call__(request)
        if not cred:
            raise HTTPException(status_code=403, detail="Missing authorization token")
        
        try:
            payload = verify_token(cred.credentials)
            return payload
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token expired")
        except jwt.InvalidTokenError as e:
            raise HTTPException(status_code=401, detail=f"Invalid token: {e}")

def create_token(subject: str, scopes: List[str]) -> str:
    """Create a new JWT token for a subject with specific scopes."""
    now = int(time.time())
    payload = {
        "sub": subject,
        "scopes": scopes,
        "iat": now,
        "exp": now + (security_settings.jwt_expiry_minutes * 60)
    }
    return jwt.encode(
        payload, 
        security_settings.jwt_secret, 
        algorithm=security_settings.jwt_algorithm
    )

def verify_token(token: str) -> TokenPayload:
    """Verify a JWT token and return its payload."""
    decoded = jwt.decode(
        token, 
        security_settings.jwt_secret, 
        algorithms=[security_settings.jwt_algorithm]
    )
    return TokenPayload(**decoded)
