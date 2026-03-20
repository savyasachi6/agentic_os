import requests
from jose import jwt
from fastapi import Request, HTTPException
import os

# These would ideally come from environment variables
KEYCLOAK_URL = os.getenv("KEYCLOAK_URL", "http://localhost:8080/realms/myrealm")
CLIENT_ID = os.getenv("KEYCLOAK_CLIENT_ID", "agentic-os-kernel")
CLIENT_SECRET = os.getenv("KEYCLOAK_CLIENT_SECRET", "your-client-secret")
KEYCLOAK_PUBLIC_KEY = os.getenv("KEYCLOAK_PUBLIC_KEY", "PUBLIC_KEY_OR_SECRET")

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
            print(f"Error fetching service account token: {e}")
            return None

    @staticmethod
    async def verify_token(request: Request):
        """FastAPI Middleware to validate User JWT"""
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            raise HTTPException(status_code=401, detail="Missing Token")
        
        try:
            token = auth_header.split(" ")[1]
            # In production, fetch public key from KEYCLOAK_URL/protocol/openid-connect/certs
            payload = jwt.decode(token, KEYCLOAK_PUBLIC_KEY, audience="account", algorithms=["RS256"])
            roles = payload.get("realm_access", {}).get("roles", [])
            return {"user_id": payload.get("sub"), "roles": roles}
        except Exception as e:
            print(f"JWT Verification failed: {e}")
            raise HTTPException(status_code=401, detail="Invalid Token")
