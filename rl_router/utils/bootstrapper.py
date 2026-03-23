"""
Heuristic Bootstrapper (Cold Start) for the RL Router.
Uses hardcoded rules to pre-train the bandit context.
"""
from typing import Tuple, List
import re

class Teacher:
    """Expert Bootstrapping Teacher for Heuristic Warm-Starting."""
    
    # Rule 2 Keywords
    TECHNICAL_KEYWORDS = {"refactor", "debug", "link"}
    
    @classmethod
    def evaluate_query(cls, query: str) -> Tuple[int, float]:
        """
        Evaluates a query based on heuristics and forces an action and reward.
        Returns: (forced_action_depth, high_reward)
        """
        words = query.split()
        word_count = len(words)
        query_lower = query.lower()
        
        has_keywords = any(kw in query_lower for kw in cls.TECHNICAL_KEYWORDS)
        
        # Rule 2: If keywords like "refactor," "debug," or "link" appear -> L3 Fractal Search (Depth 3).
        if has_keywords:
            return 3, 1.0  # Depth 3, High Reward
            
        # Rule 1: If query length < 5 words AND no technical keywords -> L1 Search (Depth 1).
        if word_count < 5 and not has_keywords:
            return 1, 1.0   # Depth 1, High Reward
            
        # Default fallback for bootstrapping: Depth 5
        return 5, 0.5
