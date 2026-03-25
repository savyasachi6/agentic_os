import os
import sys
import asyncio
import hashlib
import httpx

# --- Monorepo Shim ---
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
# --------------------

from rag.retrieval.rl_client import RLRoutingClient
from rl_router.schemas.api_models import ToolCallLogInput
from rl_router.domain.models import HallucinationCategory

async def verify_integration():
    client = RLRoutingClient()
    query = "Test query for trajectory metrics"
    q_hash = hashlib.md5(query.encode()).hexdigest()
    
    print(f"Submitting feedback for query: {query}")
    
    # 1. Mock a successful but inefficient trajectory (High step count)
    tool_calls = [
        ToolCallLogInput(tool_name="t1", cost_tokens=500, execution_latency_ms=100.0, hallucination_type=HallucinationCategory.NONE),
        ToolCallLogInput(tool_name="t2", cost_tokens=500, execution_latency_ms=100.0, hallucination_type=HallucinationCategory.NONE)
    ]
    
    result = await client.submit_feedback(
        query_hash=q_hash,
        arm_index=2,
        success=True,
        latency_ms=500.0,
        depth_used=1,
        step_count=5, # High step count should penalize
        invalid_call_count=1, # One invalid call penalty
        tool_calls=tool_calls,
        user_feedback=1.0
    )
    
    print(f"Result: {result}")
    
    if result.get("status") == "error":
        print("Integration test failed!")
    else:
        print("Integration test passed! Metrics were accepted by the RL Router.")

if __name__ == "__main__":
    asyncio.run(verify_integration())
