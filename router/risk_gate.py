# router/risk_gate.py
from typing import Dict, Any, Tuple
from tools.base_tool import BaseTool
from config import config

class RiskGate:
    """
    Evaluates tool execution risk and handles human approval for high-risk actions.
    """
    def __init__(self):
        self.high_risk_keywords = config.HIGH_RISK_KEYWORDS

    async def check(self, tool: BaseTool, payload: Dict[str, Any], session_id: str) -> Tuple[bool, str]:
        """
        Check if the tool call is safe to proceed.
        Returns (is_approved, reason).
        """
        # 1. Base check on tool's risk level
        if tool.risk_level == "low":
            return True, "Low risk tool"
        
        # 2. Heuristic check for high-risk keywords in payload
        payload_str = str(payload).lower()
        for keyword in self.high_risk_keywords:
            if keyword in payload_str:
                if tool.risk_level == "high":
                    # For high-risk tools with high-risk keywords, we might require human approval
                    # In this simulation, we'll mark it as blocked if it's very dangerous
                    return False, f"High-risk keyword '{keyword}' detected in high-risk tool '{tool.name}'"
                
        # 3. Default to approved for normal risk
        return True, "Default approval"
