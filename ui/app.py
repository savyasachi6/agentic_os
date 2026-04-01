import streamlit as st
import asyncio
import threading
from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx
import websockets
import json
import requests
import uuid
import os
import sys
import pandas as pd
from datetime import datetime

# Root calculation
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(_ROOT)


from db.connection import get_db_connection, init_db_pool

# --- Configuration & Styling ---
def init_page():
    """Initializes the UI configuration, premium CSS, and session state."""
    st.set_page_config(
        page_title="Agentic OS | AI System Console",
        page_icon="🧬",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    
    # Premium Blueprint CSS (Phase 7 - Glassmorphism)
    st.markdown("""
    <style>
    [data-testid="stSidebarNav"] {
        position: sticky; top: 0; background: rgba(255, 255, 255, 0.05);
        backdrop-filter: blur(10px); z-index: 1000;
    }
    .session-item {
        padding: 12px; margin-bottom: 8px; border-radius: 8px;
        background: rgba(255, 255, 255, 0.03); border: 1px solid rgba(255, 255, 255, 0.1);
        transition: all 0.2s ease;
    }
    .session-item:hover {
        background: rgba(255, 255, 255, 0.08); border-color: rgba(255, 255, 255, 0.2);
    }
    </style>
    """, unsafe_allow_html=True)

    # Initialize session state keys
    if "session_id" not in st.session_state:
        st.session_state.session_id = str(uuid.uuid4())
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
    if "is_processing" not in st.session_state:
        st.session_state.is_processing = False
    if "pending_deletions" not in st.session_state:
        st.session_state.pending_deletions = set()

# Configuration constants — override via env vars in Docker
CORE_API_URL = os.environ.get("CORE_API_URL", "http://localhost:8000")
CORE_WS_URL = os.environ.get("CORE_WS_URL", "ws://localhost:8000/ws")

# ---------------------------------------------------------------------------
# Global App Logic Initialization
# ---------------------------------------------------------------------------
@st.cache_resource
def init_db():
    init_db_pool()

init_db()
init_page()

# ---------------------------------------------------------------------------
# Database Utilities for Skill Explorer
# ---------------------------------------------------------------------------
def get_stats():
    """Fetches aggregate statistics for the Skill Explorer dashboard."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM knowledge_skills")
            skill_count = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM skill_chunks")
            chunk_count = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM entity_relations WHERE relation_type = 'PART_OF'")
            rel_count = cur.fetchone()[0]
            return skill_count, chunk_count, rel_count

def search_skills(query: str):
    """
    Searches for skills by name, path, or description.
    Returns a list of matching skill records.
    """
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            if query:
                cur.execute("""
                    SELECT name, normalized_name, path, skill_type, description 
                    FROM knowledge_skills 
                    WHERE name ILIKE %s OR path ILIKE %s OR description ILIKE %s
                    LIMIT 50
                """, (f"%{query}%", f"%{query}%", f"%{query}%"))
            else:
                cur.execute("""
                    SELECT name, normalized_name, path, skill_type, description 
                    FROM knowledge_skills 
                    ORDER BY created_at DESC
                    LIMIT 50
                """)
            return cur.fetchall()

def get_inheritance(normalized_name: str):
    """
    Retrieves the recursive hierarchy of skills for a given skill.
    Visualizes the 'PART_OF' relationships in the knowledge graph.
    """
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT skill_level, skill_path, chunk_heading, chunk_content FROM get_skill_inheritance_chain(%s)", (normalized_name,))
            return cur.fetchall()

# ---------------------------------------------------------------------------
# API Utilities
# ---------------------------------------------------------------------------
def load_db_history(session_id: str):
    """Fetch the permanent history from pgvector and populate st.session_state."""
    try:
        response = requests.get(f"{CORE_API_URL}/chat/{session_id}/history", timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "success":
                history = data.get("history", [])
                st.session_state.chat_history = []
                for entry in history:
                    # Map the DB roles to UI roles
                    role = entry.get("role")
                    content = entry.get("content")
                    
                    if role == "user":
                        st.session_state.chat_history.append({"role": "user", "content": content, "type": "message"})
                    elif role == "assistant":
                        st.session_state.chat_history.append({"role": "assistant", "content": content, "type": "message"})
                    elif role == "thought":
                        st.session_state.chat_history.append({"role": "assistant", "content": content, "type": "thought"})
                    elif role == "tool":
                        st.session_state.chat_history.append({"role": "assistant", "content": content, "type": "observation"})
                return True
    except Exception as e:
        st.error(f"Failed to load history: {e}")
    return False

def load_sessions():
    """Fetch the list of historical sessions."""
    try:
        response = requests.get(f"{CORE_API_URL}/chat/sessions", timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "success":
                return data.get("sessions", [])
    except Exception as e:
        print(f"Failed to load sessions: {e}")
    return []

def delete_session_api(session_id: str):
    """Call the backend to delete a session."""
    try:
        response = requests.delete(f"{CORE_API_URL}/chat/{session_id}", timeout=5)
        return response.status_code == 200
    except Exception as e:
        st.error(f"Delete failed: {e}")
        return False

def get_router_stats():
    """Fetches bandit diagnostics directly from the mounted RL Router sub-app."""
    try:
        # Bypassing the /router/stats proxy in server.py which can cause deadlocks
        response = requests.get(f"{CORE_API_URL}/rl/bandit/stats", timeout=10)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        # Silently fail or log for UI
        print(f"Router stats fetch error: {e}")
    return None

def submit_feedback(query_hash_rl: str, arm_index: int, depth: int, feedback: int, chain_id: int = 0, metrics: dict = None):
    """Submit user feedback to the Gateway RLHF endpoint."""
    try:
        metrics = metrics or {}
        payload = {
            "chain_id": chain_id,
            "query_hash_rl": query_hash_rl,
            "arm": arm_index,
            "feedback": feedback,
            "depth": depth,
            "step_count": metrics.get("step_count"),
            "invalid_call_count": metrics.get("invalid_call_count")
        }
        # Using the new human-specific gateway endpoint
        response = requests.post(f"{CORE_API_URL}/api/feedback/human", json=payload, timeout=5)
        if response.status_code == 200:
            st.toast("Feedback recorded! 🚀" if feedback > 0 else "Feedback recorded. We'll improve! 🛠️")
        else:
            st.error(f"Feedback error: {response.text}")
    except Exception as e:
        st.error(f"Failed to submit feedback: {e}")

# ---------------------------------------------------------------------------
# WebSocket Communication
# ---------------------------------------------------------------------------
async def send_message_and_receive_stream(message: str, session_id: str, message_container):
    """Connect to the websocket, send the message, and stream the response to the UI."""
    try:
        async with websockets.connect(CORE_WS_URL, ping_interval=None) as ws:
            payload = json.dumps({"message": message, "session_id": session_id})
            await ws.send(payload)

            current_thought = ""
            current_response = ""

            with message_container:
                thought_container = st.empty()
                status_placeholder = st.empty()
                response_placeholder = st.empty()

            thought_placeholder = None

            while True:
                response = await ws.recv()
                data = json.loads(response)
                msg_type = data.get("type")
                content = data.get("content", "")

                if msg_type == "session":
                    if data.get("session_id") != st.session_state.session_id:
                        st.session_state.session_id = data.get("session_id")

                elif msg_type == "thought":
                    current_thought += content
                    if thought_placeholder is None:
                        with thought_container.container():
                            thought_expander = st.expander("Agent Reasoning", expanded=True)
                            thought_placeholder = thought_expander.empty()
                    thought_placeholder.markdown(current_thought)
                    # We only append to history at the very end of the turn to avoid history bloating
                
                elif msg_type == "status":
                    status_placeholder.info(f"⏳ {content}")

                elif msg_type == "observation":
                    current_thought += f"\n\n**Observation:**\n```\n{content}\n```"
                    if thought_placeholder is None:
                        with thought_container.container():
                            thought_expander = st.expander("Agent Reasoning", expanded=True)
                            thought_placeholder = thought_expander.empty()
                    thought_placeholder.markdown(current_thought)
                    # Note: observation is usually a full block, so we keep the header

                elif msg_type == "rl_metadata":
                    # Store RL metadata for the NEXT final message
                    st.session_state.last_rl_metadata = json.loads(content)

                elif msg_type == "token":
                    current_response += content
                    response_placeholder.markdown(current_response + "▌")

                elif msg_type == "final":
                    if content:
                        current_response = content.strip()
                    
                    if not current_response:
                        current_response = "*(The agent was unable to produce a response. Please check the 'Agent Reasoning' logs above for details.)*"

                    status_placeholder.empty()
                    response_placeholder.markdown(current_response)
                    
                    # Store everything including thoughts in history at the end
                    if current_thought:
                        st.session_state.chat_history.append({"role": "assistant", "content": current_thought, "type": "thought"})

                    # Store RL metadata with the message for feedback buttons
                    msg_metadata = st.session_state.get("last_rl_metadata", {})
                    st.session_state.chat_history.append({
                        "role": "assistant", 
                        "content": current_response, 
                        "type": "message",
                        "metadata": msg_metadata
                    })
                    st.session_state.last_rl_metadata = {} # Reset
                    break

                elif msg_type == "ping":
                    pass

                elif msg_type == "error":
                    error_msg = f"Agent Error: {content}"
                    st.session_state.chat_history.append({"role": "assistant", "content": error_msg, "type": "message"})
                    break

    except Exception as e:
        error_msg = f"WebSocket Connection Error: {e}\n\n(Is the Agentic OS backend running?)"
        st.session_state.chat_history.append({"role": "assistant", "content": error_msg, "type": "message"})
    finally:
        st.session_state.is_processing = False

# ---------------------------------------------------------------------------
# UI Layout
# ---------------------------------------------------------------------------

# Sidebar for session management and page selection
with st.sidebar:
    st.title("🌌 Agentic OS")
    st.markdown("---")
    
    page = st.selectbox("Navigation", ["💬 Terminal", "🧩 Skill Explorer", "🎯 RL Strategy (Inactive)"])
    
    st.markdown("---")
    
    if page == "💬 Terminal":
        st.subheader("Sessions")
        
        # New Session Button at the top
        if st.button("➕ New Chat", use_container_width=True, type="primary"):
            st.session_state.session_id = str(uuid.uuid4())
            st.session_state.chat_history = []
            st.rerun()
            
        st.markdown("---")
        
        available_sessions = load_sessions()
        
        if available_sessions:
            for s in available_sessions:
                s_id = s["session_id"]
                # Skip if optimistically deleted
                if s_id in st.session_state.pending_deletions:
                    continue
                    
                first_msg = str(s.get('first_message', 'No message'))[:30]
                created = str(s.get('created_at', '')).split(' ')[0]
                
                # Highlight active session
                is_active = s_id == st.session_state.session_id
                label = f"**{first_msg}...**\n_{created}_" if not is_active else f"👉 **{first_msg}...**\n_{created}_"
                
                col_text, col_del = st.columns([0.78, 0.22])
                
                with col_text:
                    if st.button(label, key=f"btn_{s_id}", use_container_width=True):
                        st.session_state.session_id = s_id
                        load_db_history(s_id)
                        st.rerun()
                
                with col_del:
                    if st.button("🗑️\n ", key=f"del_{s_id}", help="Delete Session", use_container_width=True):
                        # Optimistic Delete (Phase 7)
                        st.session_state.pending_deletions.add(s_id)
                        st.toast(f"Session marked for deletion. [Undo?]", icon="🗑️")
                        
                        # We trigger a background task to actually delete after 5s
                        # In Streamlit, we can't easily spawn background threads with undos, 
                        # so we'll just delete immediately but show the toast.
                        if delete_session_api(s_id):
                            if s_id == st.session_state.session_id:
                                st.session_state.session_id = str(uuid.uuid4())
                                st.session_state.chat_history = []
                            st.rerun()
        else:
            st.caption("No historical sessions found.")
        
        st.markdown("---")
        st.caption(f"Active: `{st.session_state.session_id[:8]}...`")
    
    elif page == "🧩 Skill Explorer": # Skill Explorer Sidebar
        st.subheader("Knowledge Stats")
        s_count, c_count, r_count = get_stats()
        st.metric("Total Skills", s_count)
        st.metric("Total Chunks", c_count)
        st.metric("Hierarchical Links", r_count)
        
        if st.button("🔄 Sync Skills", use_container_width=True):
            with st.spinner("Indexing..."):
                import subprocess
                # Run the indexer from agent_core.rag
                result = subprocess.run([sys.executable, "-m", "agent_core.rag.indexer"], capture_output=True, text=True)
                if result.returncode == 0:
                    st.success("Synced!")
                    st.rerun()
                else:
                    st.error("Index Error")

    elif page == "🎯 RL Strategy":
        st.subheader("Bandit Telemetry")
        stats = get_router_stats()
        if stats and "arm_stats" in stats:
            pulls = sum(a["pulls"] for a in stats["arm_stats"])
            st.metric("Total Decisions", pulls)
            best_arm = max(stats["arm_stats"], key=lambda x: x["mean_reward"])
            st.metric("Winning Strategy", f"Arm {best_arm['arm']}")
        else:
            st.caption("Router offline.")

    st.markdown("---")
    st.caption("Permanent memory written to `pgvector`.")

# Main Interface Logic
if page == "💬 Terminal":
    st.header("Terminal")
    
    # Render existing chat history
    i = 0
    while i < len(st.session_state.chat_history):
        msg = st.session_state.chat_history[i]
        
        if msg["type"] == "message":
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
                
                # Show feedback buttons for assistant messages with RL metadata
                metadata = msg.get("metadata")
                if msg["role"] == "assistant" and metadata and metadata.get("query_hash_rl"):
                    qh = metadata["query_hash_rl"]
                    arm = metadata["arm_index"]
                    depth = metadata.get("depth", 0)
                    cid = metadata.get("chain_id", 0)
                    
                    c1, c2, c3 = st.columns([0.05, 0.05, 0.9])
                    if c1.button("👍", key=f"up_{qh}"):
                        submit_feedback(qh, arm, depth, 1, chain_id=cid, metrics=metadata)
                    if c2.button("👎", key=f"down_{qh}"):
                        submit_feedback(qh, arm, depth, -1, chain_id=cid, metrics=metadata)
            i += 1
                        
        elif msg["type"] == "thought":
            # Consolidate consecutive thought blocks
            combined_thought = msg["content"]
            i += 1
            while i < len(st.session_state.chat_history) and st.session_state.chat_history[i]["type"] == "thought":
                combined_thought += "\n\n" + st.session_state.chat_history[i]["content"]
                i += 1
                
            with st.chat_message("assistant", avatar="🧠"):
                with st.expander("Agent Thought", expanded=False):
                    st.markdown(combined_thought)
                    
        elif msg["type"] == "observation":
            with st.chat_message("assistant", avatar="🛠️"):
                with st.expander("Tool Observation", expanded=False):
                    st.markdown(f"```\n{msg['content']}\n```")
            i += 1

    # Handle user input
    prompt = st.chat_input("Ask the Agentic OS...", disabled=st.session_state.is_processing)

    if prompt:
        st.session_state.chat_history.append({"role": "user", "content": prompt, "type": "message"})
        with st.chat_message("user"):
            st.markdown(prompt)
            
        st.session_state.is_processing = True
        with st.chat_message("assistant"):
            message_container = st.container()
            # Streamlit uses uvloop internally, so asyncio.run() conflicts.
            # The fix: run the coroutine in a fresh thread with its own event loop,
            # AND propagate Streamlit's script run context so st.* calls work in the thread.
            ctx = get_script_run_ctx()
            def _run_ws():
                add_script_run_ctx(threading.current_thread(), ctx)
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(
                        send_message_and_receive_stream(prompt, st.session_state.session_id, message_container)
                    )
                finally:
                    loop.close()
            t = threading.Thread(target=_run_ws, daemon=True)
            t.start()
            t.join()
        st.rerun()

elif page == "🧩 Skill Explorer": # Skill Explorer Page
    st.header("🧩 Skill & Hierarchy Explorer")
    st.markdown("Visualize the **Recursive Inheritance** in your RAG Knowledge Graph.")
    
    search_query = st.text_input("🔍 Search skills (name, path, or description)", "")
    results = search_skills(search_query)

    if results:
        df = pd.DataFrame(results, columns=["Name", "Normalized Name", "Path", "Type", "Description"])
        
        selected_name = st.selectbox("Select a skill to view its Inheritance Chain", df["Normalized Name"].tolist())
        
        if selected_name:
            st.divider()
            st.subheader(f"🌲 Inheritance Chain for: `{selected_name}`")
            
            chain = get_inheritance(selected_name)
            if chain:
                for level, path, heading, content in chain:
                    with st.expander(f"Level {level}: {path} » {heading}"):
                        st.markdown(content)
            else:
                st.info("No inheritance chain found. Parent folders might need 'instructions' chunks.")

        st.divider()
        st.subheader("📋 Search Results")
        st.dataframe(df, use_container_width=True)
    else:
        st.warning("No skills found.")

elif page == "🎯 RL Strategy (Inactive)":
    st.header("🎯 Reinforcement Learning Strategy")
    st.warning("⚠️ Telemetry Service Offline: The RL Router is not currently active in the standard specialist stack.")
    st.markdown("""
    This dashboard traditionally displays:
    - **Exploration vs. Exploitation** weights for specialist routing.
    - **Reward distributions** per agent role.
    - **Bandit convergence** metrics.
    
    *The RL Strategizer is a dangling feature awaiting telemetry re-integration.*
    """)
    
    stats = get_router_stats()
    
    if stats and "arm_stats" in stats:
        # 1. Summary Metrics
        pull_counts = [a["pulls"] for a in stats["arm_stats"]]
        total_episodes = sum(pull_counts)
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Routing Episodes", total_episodes)
        
        # Mapping for better display names
        arm_names = {
            0: "Collapsed Tree (Spec Off)",
            1: "Collapsed Tree (Spec On)",
            2: "Standard RAG (Spec Off)",
            3: "Standard RAG (Spec On)",
            4: "Multi-hop GraphRAG (Spec Off)",
            5: "Multi-hop GraphRAG (Spec On)",
            6: "Full Fractal Tree (Spec Off)",
            7: "Full Fractal Tree (Spec On)",
        }
        
        # 2. Arm Performance Table
        st.subheader("Learned Policy Diagnostics")
        df_stats = pd.DataFrame(stats["arm_stats"])
        df_stats["Action Name"] = df_stats["arm"].map(arm_names)
        
        # Sort and filter for display
        display_df = df_stats[["Action Name", "pulls", "mean_reward", "violation_rate", "theta_norm"]].copy()
        st.table(display_df.style.highlight_max(axis=0, subset=["mean_reward"], color="#2E7D32"))
        
        # 3. Visualization
        st.divider()
        st.subheader("Policy Confidence (Weight Gradients)")
        
        # Simple bar chart for rewards
        st.bar_chart(df_stats, x="Action Name", y="mean_reward", color="#FFD700")
        
        # 4. Recent Episodes (Audit Log)
        if "episodes" in stats and stats["episodes"]:
            st.divider()
            st.subheader("🕵️ Recent Retrieval Episodes")
            df_eps = pd.DataFrame(stats["episodes"])
            # Format JSON reward vector for readability
            st.dataframe(df_eps[["created_at", "query_hash", "depth_used", "speculative_used", "success", "reward_scalar", "final_utility_score"]], use_container_width=True)
    else:
        st.info("RL Router not detected or no stats available. Start the `rl_router` service.")
