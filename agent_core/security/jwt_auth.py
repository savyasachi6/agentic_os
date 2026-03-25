import jwt
from typing import List, Optional
from pydantic import BaseModel
from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from datetime import datetime, timedelta, timezone
from agent_core.config import settings

def create_token(subject: str, scopes: List[str]) -> str:
    payload = {
        "sub": subject,
        "scopes": scopes,
        "exp": datetime.now(timezone.utc) + timedelta(hours=1)
    }
    return jwt.encode(payload, settings.admin_secret, algorithm=settings.jwt_algorithm)

class TokenPayload(BaseModel):
    sub: str
    scopes: List[str]
    exp: Optional[int] = None

class JWTMiddleware:
    def __init__(self, required_scopes: Optional[List[str]] = None):
        self.required_scopes = required_scopes or []
        self.security = HTTPBearer()

    async def __call__(self, request: Request) -> TokenPayload:
        auth: HTTPAuthorizationCredentials = await self.security(request)
        if not auth:
            raise HTTPException(status_code=401, detail="Missing authorization credentials")
        
        try:
            payload = jwt.decode(
                auth.credentials, 
                settings.admin_secret, 
                algorithms=[settings.jwt_algorithm]
            )
            token_data = TokenPayload(**payload)
            
            # Check scopes if required
            for scope in self.required_scopes:
                if scope not in token_data.scopes:
                    raise HTTPException(
                        status_code=403, 
                        detail=f"Token missing required scope: {scope}"
                    )
            
            return token_data
        except jwt.PyJWTError as e:
            raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")
