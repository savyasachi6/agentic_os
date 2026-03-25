import json
import os
import sys
import argparse
import asyncio
import traceback
from typing import List, Dict, Tuple, Optional

# Setup path to include project root for agent_core imports
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", ".."))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from llm.client import LLMClient
from db.queries.commands import TreeStore
from agent_core.types import NodeStatus

class RICECalculator:
    """Calculate RICE scores and prioritize using LLM reasoning"""
    
    def __init__(self, model_name: Optional[str] = None):
        self.llm = LLMClient(model_name=model_name)
        self.tree_store = TreeStore()
    
    async def prioritize_backlog(self, backlog_data: str) -> Dict:
        """Use LLM to calculate RICE and prioritize"""
        system_prompt = (
            "You are a Product Manager using the RICE framework (Reach, Impact, Confidence, Effort).\n"
            "Analyze the provided backlog and return a prioritized list in JSON format.\n"
            "Each item must have: name, reach (users/qtr), impact (0.1-3.0), confidence (0.1-1.0), "
            "effort (weeks), rice_score, and a short justification.\n"
            "Return ONLY a JSON object with 'prioritized_features' and 'portfolio_analysis'."
        )
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Backlog Content:\n{backlog_data}"}
        ]
        
        response = await self.llm.generate_async(messages)
        try:
            clean_json = response.strip()
            if "```json" in clean_json:
                clean_json = clean_json.split("```json")[1].split("```")[0].strip()
            elif "```" in clean_json:
                clean_json = clean_json.split("```")[1].split("```")[0].strip()
            
            return json.loads(clean_json)
        except Exception as e:
            print(f"Error parsing LLM response: {e}")
            return {"error": "Failed to parse prioritization", "raw": response}

    async def report_status(self, node_id: int, status: NodeStatus, result: Dict[str, Any]):
        """Update node status in the execution tree"""
        try:
            await self.tree_store.update_node_status_async(node_id, status, result=result)
        except Exception as e:
            print(f"Failed to update DB status for node {node_id}: {e}")

async def main():
    parser = argparse.ArgumentParser(description='RICE Prioritization Framework')
    parser.add_argument('input', nargs='?', help='CSV content or description of features')
    parser.add_argument('--node-id', type=int, help='TreeStore Node ID for status reporting')
    parser.add_argument('--model', help='LLM model to use')
    parser.add_argument('--capacity', type=int, default=10, help='Team capacity (optional)')
    
    args = parser.parse_args()
    
    # Check environment variable for node ID as fallback
    node_id_val = args.node_id or os.environ.get("AGENTOS_TASK_ID")
    if node_id_val:
        node_id = int(node_id_val)
    else:
        node_id = None

    calculator = RICECalculator(model_name=args.model)
    
    input_data = args.input or "Sample backlog: Search, Mobile dashboard, Dark mode, PDF export"
    
    try:
        print(f"Prioritizing backlog: {input_data[:50]}...")
        result = await calculator.prioritize_backlog(input_data)
        
        # Output to stdout
        print(json.dumps(result, indent=2))
        
        if node_id:
            await calculator.report_status(node_id, NodeStatus.DONE, result=result)
            print(f"✓ Updated node {node_id} to DONE")
            
    except Exception as e:
        error_trace = traceback.format_exc()
        print(f"Error during prioritization: {e}")
        
        if node_id:
            await calculator.report_status(node_id, NodeStatus.FAILED, result={"error": str(e), "trace": error_trace})
            print(f"✗ Updated node {node_id} to FAILED")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
