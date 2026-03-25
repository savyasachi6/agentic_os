import json
import os
import sys
import argparse
import asyncio
import traceback
from typing import Dict, List, Tuple, Optional

# Setup path to include project root for agent_core imports
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", ".."))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from llm.client import LLMClient
from db.queries.commands import TreeStore
from agent_core.types import NodeStatus

class UserStoryGenerator:
    """Generate INVEST-compliant user stories using LLM"""
    
    def __init__(self, model_name: Optional[str] = None):
        self.llm = LLMClient(model_name=model_name)
        self.tree_store = TreeStore()
        self.personas = {
            'end_user': 'End User (daily usage, efficiency, simplicity)',
            'admin': 'Administrator (system management, security, control)',
            'power_user': 'Power User (automation, customization, shortcuts)',
            'new_user': 'New User (onboarding, guidance, clarity)'
        }
    
    async def generate_stories_from_prompt(self, prompt: str) -> List[Dict]:
        """Use LLM to generate stories from a description or epic"""
        system_prompt = (
            "You are an Agile Product Owner. Break down the user's request into 3-5 INVEST-compliant user stories.\n"
            "Format each story as a JSON object with: id, title, narrative (As a... I want... So that...), "
            "acceptance_criteria (list of Given/When/Then), estimation (Fibonacci), priority (low/medium/high), "
            "and invest_check (object with boolean values for each letter).\n"
            "Return ONLY a JSON list of stories."
        )
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Epic/Feature: {prompt}"}
        ]
        
        response = await self.llm.generate_async(messages)
        try:
            # Clean up potential markdown formatting
            clean_json = response.strip()
            if "```json" in clean_json:
                clean_json = clean_json.split("```json")[1].split("```")[0].strip()
            elif "```" in clean_json:
                clean_json = clean_json.split("```")[1].split("```")[0].strip()
            
            return json.loads(clean_json)
        except Exception as e:
            print(f"Error parsing LLM response: {e}")
            print(f"Raw response: {response}")
            return [{"error": "Failed to parse stories", "raw": response}]

    async def report_status(self, node_id: int, status: NodeStatus, result: Dict[str, Any]):
        """Update node status in the execution tree"""
        try:
            await self.tree_store.update_node_status_async(node_id, status, result=result)
        except Exception as e:
            print(f"Failed to update DB status for node {node_id}: {e}")

async def main():
    parser = argparse.ArgumentParser(description='User Story Generator with INVEST Criteria')
    parser.add_argument('prompt', nargs='?', help='Epic or feature description')
    parser.add_argument('--node-id', type=int, help='TreeStore Node ID for status reporting')
    parser.add_argument('--model', help='LLM model to use')
    parser.add_argument('sprint_cmd', nargs='?', help='Sprint command (optional)')
    parser.add_argument('capacity', nargs='?', type=int, help='Sprint capacity (optional)')
    
    args = parser.parse_args()
    
    # Check environment variable for node ID as fallback
    node_id_val = args.node_id or os.environ.get("AGENTOS_TASK_ID")
    if node_id_val:
        node_id = int(node_id_val)
    else:
        node_id = None

    generator = UserStoryGenerator(model_name=args.model)
    
    prompt = args.prompt or "Generic User Dashboard features"
    
    try:
        print(f"Generating stories for: {prompt[:50]}...")
        stories = await generator.generate_stories_from_prompt(prompt)
        
        # Output to stdout for worker observation
        print(json.dumps(stories, indent=2))
        
        if node_id:
            await generator.report_status(node_id, NodeStatus.DONE, result={"stories": stories})
            print(f"✓ Updated node {node_id} to DONE")
            
    except Exception as e:
        error_trace = traceback.format_exc()
        print(f"Error during generation: {e}")
        print(error_trace)
        
        if node_id:
            await generator.report_status(node_id, NodeStatus.FAILED, result={"error": str(e), "trace": error_trace})
            print(f"✗ Updated node {node_id} to FAILED")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
