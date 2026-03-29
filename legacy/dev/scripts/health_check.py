# scripts/health_check.py
import asyncio
import sys
import os

# Put root in sys.path
sys.path.insert(0, os.getcwd())

from db.connection import get_pool, get_redis
from core.settings import settings

async def check_health():
    print("--- Agentic OS Health Check ---")
    
    # 1. DB Check
    try:
        from db.connection import get_db_connection
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                val = cur.fetchone()[0]
                if val == 1:
                    print("[OK] Postgres Connection")
                else:
                    print("[FAIL] Postgres Connection (Unexpected Result)")
    except Exception as e:
        print(f"[FAIL] Postgres Connection: {e}")

    # 2. Redis Check
    try:
        r = await get_redis()
        pong = await r.ping()
        if pong:
            print("[OK] Redis Connection")
        else:
            print("[FAIL] Redis Connection (No Pong)")
    except Exception as e:
        print(f"[FAIL] Redis Connection: {e}")

    # 3. LLM Check
    try:
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{settings.ollama_base_url}/api/tags")
            if resp.status_code == 200:
                print(f"[OK] LLM Provider ({settings.router_backend})")
            else:
                print(f"[FAIL] LLM Provider (Status {resp.status_code})")
    except Exception as e:
        print(f"[FAIL] LLM Provider: {e}")

if __name__ == "__main__":
    asyncio.run(check_health())
