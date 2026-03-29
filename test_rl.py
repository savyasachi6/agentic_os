import httpx
import asyncio
import os
import sys

# Add current dir to path
sys.path.insert(0, os.getcwd())

from core.settings import settings

async def main():
    print(f"DEBUG: settings.rl_router_url = {settings.rl_router_url}")
    print(f"DEBUG: Checking {settings.rl_router_url}/bandit/stats...")
    
    async with httpx.AsyncClient(timeout=2.0) as client:
        try:
            r = await client.get(f"{settings.rl_router_url}/bandit/stats")
            print(f"STATUS: {r.status_code}")
            print(f"BODY: {r.text[:500]}")
        except Exception as e:
            print(f"ERROR: {e}")

if __name__ == "__main__":
    asyncio.run(main())
