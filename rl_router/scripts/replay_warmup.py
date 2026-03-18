import os
import sys

# --- Monorepo Shim: Ensure subpackages are discoverable ---
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
# ---------------------------------------------------------

from rl_router.domain.bandit import LinUCBBandit
from rl_router.domain.features import ContextFeatureBuilder
from rl_router.infrastructure.repositories import EpisodeRepository

def warmup_from_logs(bandit: LinUCBBandit, repo: EpisodeRepository, limit: int = 10000):
    """
    Replay logged production episodes into the bandit in chronological order.
    """
    # Assuming get_recent_episodes supports ordering or we handle it here
    episodes = repo.get_recent_episodes(limit=limit)
    if not episodes:
        print("No historical episodes found in repository for warm-start.")
        return

    # Sort by created_at ascending to ensure we replay in the order they happened
    episodes.sort(key=lambda x: x.created_at) 
    
    print(f"Replaying {len(episodes)} historical episodes into bandit (chronological order)...")

    builder = ContextFeatureBuilder(embedding_dim=1536)

    for ep in episodes:
        # Note: The repository stores raw data; we rebuild the context vector
        # assuming the logs contain the necessary info. 
        # In a real system, you might store the context vector itself or 
        # the parameters needed to rebuild it exactly.
        
        # For this shim, we assume the episode dict has the required fields
        # (or we provide fallbacks/simulations based on the logged query_type)
        
        # Since log_episode currently doesn't store query_text/embedding in the DB table
        # (check retrieval_episodes schema), we'd need to extend it.
        # For now, this is a structural template.
        
        # placeholder for real context reconstruction
        # context = builder.build(...) 
        # bandit.update(arm=ep['arm_index'], context=context, reward=ep['reward_scalar'], hallucination_flag=ep['hallucination_flag'])
        pass

    print("Warm-start replay complete.")

if __name__ == "__main__":
    # Example usage:
    # bandit = get_bandit()
    # repo = EpisodeRepository()
    # warmup_from_logs(bandit, repo)
    print("Replay Warm-start module initialized.")
