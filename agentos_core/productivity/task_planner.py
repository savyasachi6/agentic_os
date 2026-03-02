"""
Multi-step task planner and orchestrator.
"""
import uuid
import logging
from typing import List, Optional
from productivity.models import TaskPlan, PlanStep, PlanStepStatus
from agent_core.llm import generate_structured_output

logger = logging.getLogger(__name__)

class TaskPlanner:
    def __init__(self, tool_registry, tree_store=None):
        self.tool_registry = tool_registry
        self.tree_store = tree_store
        self.active_plans: List[TaskPlan] = []

    async def create_plan(self, goal: str, session_id: str = "default") -> TaskPlan:
        """
        Ask LLM to decompose goal into steps using structured output and persist to TreeStore.
        """
        prompt = f"Decompose the following user goal into a sequence of executable tool-based steps: '{goal}'"
        
        try:
            plan: TaskPlan = await generate_structured_output(
                prompt=prompt,
                response_model=TaskPlan,
                system_prompt="You are a high-level task orchestrator. Break down goals into atomic steps with specific tools."
            )
            
            plan.goal = goal
            if not plan.id:
                plan.id = str(uuid.uuid4())
            
            # Persist to TreeStore if available
            if self.tree_store:
                chain = self.tree_store.create_chain(session_id=session_id, description=goal)
                plan.context["chain_id"] = str(chain.id)
                
                for i, step in enumerate(plan.steps):
                    from agent_memory.models import Node, AgentRole, NodeType, NodeStatus
                    node = Node(
                        chain_id=chain.id,
                        agent_role=AgentRole.ORCHESTRATOR,
                        type=NodeType.PLAN,
                        status=NodeStatus.PENDING,
                        priority=5,
                        planned_order=i,
                        content=step.action
                    )
                    persisted_node = self.tree_store.add_node(node)
                    step.args["node_id"] = str(persisted_node.id)

            self.active_plans.append(plan)
            return plan
            
        except Exception as e:
            logger.error(f"Failed to generate task plan via LLM: {e}")
            fallback_plan = TaskPlan(
                id=str(uuid.uuid4()),
                goal=goal,
                steps=[
                    PlanStep(
                        action=f"System failed to decompose goal: {str(e)}",
                        status=PlanStepStatus.FAILED
                    )
                ]
            )
            self.active_plans.append(fallback_plan)
            return fallback_plan

    def execute_step(self, plan_id: str, step_idx: int) -> str:
        """
        Execute a single step in a plan and update its status in the TreeStore.
        """
        plan = next((p for p in self.active_plans if p.id == plan_id), None)
        if not plan or step_idx >= len(plan.steps):
            return "Plan or step not found."
            
        step = plan.steps[step_idx]
        step.status = PlanStepStatus.RUNNING
        
        # Update TreeStore if node_id exists
        node_id = step.args.get("node_id")
        if self.tree_store and node_id:
            from agent_memory.models import NodeStatus as DBNodeStatus
            self.tree_store.update_node_status(int(node_id), DBNodeStatus.RUNNING)
        
        result = ""
        if step.tool_name and step.tool_name in self.tool_registry:
            tool = self.tool_registry[step.tool_name]
            try:
                result = tool.execute(**{k: v for k, v in step.args.items() if k != "node_id"})
                step.result = result
                step.status = PlanStepStatus.DONE
                if self.tree_store and node_id:
                    self.tree_store.update_node_status(int(node_id), DBNodeStatus.DONE, content=result)
            except Exception as e:
                step.status = PlanStepStatus.FAILED
                result = f"Step failed: {e}"
                if self.tree_store and node_id:
                    self.tree_store.update_node_status(int(node_id), DBNodeStatus.FAILED, content=result)
        else:
            step.status = PlanStepStatus.DONE
            result = "Step marked as done (manual/analysis)."
            if self.tree_store and node_id:
                self.tree_store.update_node_status(int(node_id), DBNodeStatus.DONE, content=result)
                
        return result
