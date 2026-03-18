import os
import sys
import numpy as np
import random
import hashlib
from typing import List, Tuple
from collections import defaultdict

# --- Monorepo Shim: Ensure subpackages are discoverable ---
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
# ---------------------------------------------------------

from rl_router.domain.bandit import LinUCBBandit
from rl_router.domain.features import ContextFeatureBuilder
from rl_router.domain.models import RetrievalAction, RewardVector
from rl_router.infrastructure.repositories import EpisodeRepository

# --- Realistic query type distribution (Enhanced for multi-hop coverage) ---
QUERY_DISTRIBUTION = {
    "factual":    0.40,   # Reduced from 0.55 to allow more multi-hop samples
    "analytical": 0.30,
    "multi_hop":  0.30,   # Increased from 0.15 for better 1561-d stability
}

# --- Richer query templates per type ---
QUERY_TEMPLATES = {
    "factual": [
        "What is the capital of France?",
        "When was the Eiffel Tower built?",
        "Who wrote Hamlet?",
        "What is the boiling point of water?",
        "Define photosynthesis.",
    ],
    "analytical": [
        "Compare React and Vue for large-scale applications.",
        "What are the tradeoffs between SQL and NoSQL for analytics?",
        "Evaluate the pros and cons of microservices architecture.",
        "How does transformer attention scale with sequence length?",
    ],
    "multi_hop": [
        "How does embedding dimension relate to retrieval latency in pgvector with HNSW?",
        "If the CEO of company A acquired company B in 2019, who runs B's R&D now?",
        "What regulatory changes followed the 2008 crisis that affected Basel III adoption?",
    ],
}

def generate_synthetic_context(
    query_type: str,
    d: int = 1536,
    difficulty_noise: float = 0.15
) -> Tuple[np.ndarray, str]:
    """
    Enhanced context generation with:
    - Realistic query text sampling
    - Difficulty jitter to avoid oracle over-fitting
    """
    emb = np.random.randn(d)
    emb /= np.linalg.norm(emb)

    text = random.choice(QUERY_TEMPLATES[query_type])

    if query_type == "factual":
        intent = [0.9, 0.05, 0.02, 0.03]
        base_difficulty = 0.1
    elif query_type == "analytical":
        intent = [0.1, 0.8, 0.05, 0.05]
        base_difficulty = 0.4
    else:
        intent = [0.05, 0.1, 0.8, 0.05]
        base_difficulty = 0.9

    # Add jitter so the bandit doesn't memorize difficulty -> arm mapping
    difficulty = np.clip(base_difficulty + random.uniform(-difficulty_noise, difficulty_noise), 0.0, 1.0)

    builder = ContextFeatureBuilder(embedding_dim=d)
    # Zero out embeddings for pre-training (force learning from metadata signal)
    context = builder.build(
        query_text=text,
        query_embedding=[0.0] * d,
        intent_logits=intent,
        difficulty_estimate=float(difficulty)
    )
    return context, query_type


def get_reward(query_type: str, arm_idx: int, noise_scale: float = 0.20) -> Tuple[float, float]:
    """
    Returns (scalar_reward, overthinking_penalty).
    Separated so we can log them independently.
    """
    action = RetrievalAction(arm_idx)
    depth = action.depth
    spec = action.speculative

    if query_type == "factual":
        reward = 1.0 if depth == 0 else (0.5 if depth == 1 else 0.1)
        if spec:
            reward -= 0.2
        overthinking = max(0.0, depth * 0.15)   # penalize depth waste

    elif query_type == "analytical":
        reward = 1.0 if depth in [1, 2] else (0.4 if depth == 0 else 0.6)
        if not spec:
            reward -= 0.1
        overthinking = 0.0

    else:  # multi_hop
        reward = 1.0 if depth == 3 else (0.7 if depth == 2 else 0.2)
        if not spec:
            reward -= 0.3
        overthinking = 0.0

    reward += random.gauss(0, noise_scale)   # Gaussian noise, not uniform
    return max(0.0, min(1.0, reward)), overthinking


def train(
    use_db: bool = False,
    episodes: int = 10000,           # 10k episodes for better dimensionality coverage
    checkpoint_every: int = 2000,
    alpha: float = 0.25,              # Lower alpha for more stable exploitation
):
    print(f"Starting synthetic training: {episodes} episodes...")

    repo = EpisodeRepository() if use_db else None

    # Derive context_dim from the builder - no magic numbers
    _builder = ContextFeatureBuilder(embedding_dim=1536)
    context_dim = _builder.output_dim
    n_arms = 8
    print(f"Derived context_dim={context_dim} from ContextFeatureBuilder")

    bandit = LinUCBBandit(n_arms=n_arms, d=context_dim, alpha=alpha)

    # Track per-type arm selection for coverage diagnostics
    arm_counts = defaultdict(lambda: defaultdict(int))

    query_types = list(QUERY_DISTRIBUTION.keys())
    weights = list(QUERY_DISTRIBUTION.values())

    os.makedirs("checkpoints", exist_ok=True)

    for i in range(episodes):
        # Sample from realistic distribution
        q_type = random.choices(query_types, weights=weights, k=1)[0]
        context, _ = generate_synthetic_context(q_type)

        # Implementation of 0.5% epsilon-greedy floor for safety
        if random.random() < 0.005:
            arm = random.randint(0, n_arms - 1)
        else:
            arm, _, _ = bandit.select_arm(context, epsilon=0.005)
            
        reward, overthinking = get_reward(q_type, arm)

        hallucinated = False
        if q_type == "multi_hop" and arm < 4:
            if random.random() < 0.4:
                hallucinated = True

        bandit.update(arm, context, reward, hallucination_flag=hallucinated)
        arm_counts[q_type][arm] += 1

        if repo:
            action = RetrievalAction(arm)
            repo.log_episode(
                query_hash=hashlib.md5(q_type.encode()).hexdigest()[:16],
                query_type=q_type,
                depth_used=action.depth,
                speculative_used=action.speculative,
                latency_ms=random.randint(100, 1500),
                success=True,
                hallucination_flag=hallucinated,
                hallucination_score=0.9 if hallucinated else 0.05,
                auditor_score=reward,
                faithfulness_score=reward,
                coverage_score=reward,
                cost_tokens=1000,
                reward=RewardVector(
                    quality=reward,
                    hallucination_penalty=-0.5 if hallucinated else 0.0,
                    latency_cost=-0.1,
                    overthinking_penalty=-overthinking,
                    scalar=reward
                ),
                arm_index=arm,
                final_utility_score=reward
            )

        # Periodic checkpoint
        if (i + 1) % checkpoint_every == 0:
            path = f"checkpoints/bandit_ep{i+1}.npz"
            with open(path, "wb") as f:
                f.write(bandit.save_to_bytes())
            print(f"  [{i+1}/{episodes}] Checkpoint saved -> {path}")

    # Final weights
    final_path = "bandit_weights.npz"
    with open(final_path, "wb") as f:
        f.write(bandit.save_to_bytes())
    print(f"Training complete. Final weights -> {final_path}")

    # Coverage report
    print("\n--- Arm Coverage by Query Type ---")
    for qt in query_types:
        total = sum(arm_counts[qt].values())
        print(f"\n{qt} (n={total}):")
        for arm in range(n_arms):
            pct = arm_counts[qt][arm] / total * 100 if total else 0
            print(f"  Arm {arm}: {arm_counts[qt][arm]:4d} pulls ({pct:.1f}%)")

    print("\n--- Final Arm Stats ---")
    for s in bandit.get_all_arm_stats():
        print(
            f"Arm {s['arm']}: pulls={s['pulls']:4d}, "
            f"mean_reward={s['mean_reward']:.3f}, "
            f"viol_rate={s['violation_rate']:.3f}"
        )


if __name__ == "__main__":
    train(use_db=True, episodes=10000)
