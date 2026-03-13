import os
import sys
import numpy as np
import random
from typing import List, Tuple

# Enable relative imports for the script
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agentic_rl_router.domain.bandit import LinUCBBandit
from agentic_rl_router.domain.features import ContextFeatureBuilder
from agentic_rl_router.domain.models import RetrievalAction

def generate_synthetic_context(query_type: str, d: int = 1536) -> Tuple[np.ndarray, str]:
    """Generates a synthetic context vector based on query complexity."""
    # 1. Random embedding
    emb = np.random.randn(d)
    emb /= np.linalg.norm(emb)
    
    # 2. Intent logits (factual, analytical, multi-hop, unknown)
    if query_type == "factual":
        intent = [0.9, 0.05, 0.02, 0.03]
        text = "What is the capital of France?"
    elif query_type == "analytical":
        intent = [0.1, 0.8, 0.05, 0.05]
        text = "Compare the performance of React and Vue for large scale applications."
    else: # multi-hop
        intent = [0.05, 0.1, 0.8, 0.05]
        text = "How does the embedding dimension relate to the retrieval latency in pgvector using HNSW indexes?"

    # 3. Use the real FeatureBuilder to ensure dim consistency
    builder = ContextFeatureBuilder(embedding_dim=d)
    context = builder.build(
        query_text=text,
        query_embedding=list(emb),
        intent_logits=intent,
        difficulty_estimate=0.1 if query_type == "factual" else (0.4 if query_type == "analytical" else 0.9)
    )
    return context, query_type

def get_reward(query_type: str, arm_idx: int) -> float:
    """Perfect world reward function for training."""
    action = RetrievalAction(arm_idx)
    depth = action.depth
    spec = action.speculative
    
    if query_type == "factual":
        # Factual: best is depth 0. Penalize depth > 0.
        reward = 1.0 if depth == 0 else (0.5 if depth == 1 else 0.1)
        if spec: reward -= 0.2 # Speculative is overkill for factual
    elif query_type == "analytical":
        # Analytical: best is depth 1 or 2.
        reward = 1.0 if depth in [1, 2] else (0.4 if depth == 0 else 0.6)
        if not spec: reward -= 0.1 # Speculative helps for analytical
    else: # multi-hop
        # Multi-hop: best is depth 3.
        reward = 1.0 if depth == 3 else (0.7 if depth == 2 else 0.2)
        if not spec: reward -= 0.3 # Speculative is critical for multi-hop
        
    # Add noise
    reward += random.uniform(-0.1, 0.1)
    return max(0.0, min(1.0, reward))

def train():
    print("Starting synthetic training for RL Router...")
    
    # Matching config defaults
    n_arms = 8
    context_dim = 1561 
    
    print("Initializing bandit...")
    bandit = LinUCBBandit(n_arms=n_arms, d=context_dim, alpha=0.1) # Low alpha for training convergence
    
    episodes = 500
    types = ["factual", "analytical", "multi_hop"]
    
    print(f"Starting {episodes} episodes loop...")
    for i in range(episodes):
        q_type = random.choice(types)
        context, _ = generate_synthetic_context(q_type)
        
        # In actual training, we'd pick the arm the bandit suggests, 
        # but here we can simulate all arms to fill the matrices or 
        # just let the bandit explore.
        arm, _, _ = bandit.select_arm(context)
        reward = get_reward(q_type, arm)
        
        # Check for "hallucination" simulation
        hallucinated = False
        if q_type == "multi_hop" and arm < 4: # Deep query with shallow search
            if random.random() < 0.4: hallucinated = True
            
        bandit.update(arm, context, reward, hallucination_flag=hallucinated)
        
        if (i + 1) % 500 == 0:
            print(f"Completed {i+1}/{episodes} episodes...")

    # Save weights
    weights = bandit.save_to_bytes()
    with open("bandit_weights.npz", "wb") as f:
        f.write(weights)
    
    print("Training complete. Weights saved to bandit_weights.npz")
    
    # Print final stats
    stats = bandit.get_all_arm_stats()
    print("\nFinal Arm Stats:")
    for s in stats:
        print(f"Arm {s['arm']}: pulls={s['pulls']}, mean_reward={s['mean_reward']:.3f}, viol_rate={s['violation_rate']:.3f}")

if __name__ == "__main__":
    train()
