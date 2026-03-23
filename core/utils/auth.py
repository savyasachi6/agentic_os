import requests
from fastapi import Request, HTTPException
import os
import logging
from agent_config import security_settings

logger = logging.getLogger("agentos.auth")

# Strictly load configurations from Pydantic matching the .env
KEYCLOAK_URL = security_settings.keycloak_url
CLIENT_ID = security_settings.keycloak_client_id
CLIENT_SECRET = security_settings.keycloak_client_secret

import jwt as pyjwt # Using pyjwt instead of jose if not colliding
from jwt import PyJWKClient

# Cache the JWKS client for performance across requests
jwks_url = f"{KEYCLOAK_URL}/protocol/openid-connect/certs"
jwks_client = PyJWKClient(jwks_url)

class KeycloakManager:
    @staticmethod
    def get_service_account_token():
        """Supervisor Agent authenticates as a Service Account"""
        data = {
            "grant_type": "client_credentials",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
        }
        try:
            response = requests.post(f"{KEYCLOAK_URL}/protocol/openid-connect/token", data=data)
            response.raise_for_status()
            return response.json().get("access_token")
        except Exception as e:
            logger.error(f"Error fetching service account token: {e}")
            return None

    @staticmethod
    async def verify_token(request: Request):
        """FastAPI Middleware to validate User JWT"""
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            raise HTTPException(status_code=401, detail="Missing Token")
        
        try:
            token = auth_header.split(" ")[1]
            
            # Fetch signing key dynamically
            signing_key = jwks_client.get_signing_key_from_jwt(token)
            
            # Validate token with pyjwt
            payload = pyjwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience="account",
                options={"verify_aud": False} # Adjust audience validation depending on Keycloak setup
            )
            
            roles = payload.get("realm_access", {}).get("roles", [])
            return {"user_id": payload.get("sub"), "roles": roles}
        except Exception as e:
            logger.error(f"JWT Verification failed: {e}")
            raise HTTPException(status_code=401, detail="Invalid Token")
