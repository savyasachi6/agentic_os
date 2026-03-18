import streamlit as st
import asyncio
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


from agent_memory.db import get_db_connection, init_db_pool

# Configure the page
st.set_page_config(
    page_title="Agentic OS",
    page_icon="🌌",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Configuration constants — override via env vars in Docker
CORE_API_URL = os.environ.get("CORE_API_URL", "http://localhost:8000")
CORE_WS_URL = os.environ.get("CORE_WS_URL", "ws://localhost:8000/ws")

@st.cache_resource
def init_db():
    init_db_pool()

init_db()

# ---------------------------------------------------------------------------
# Session State Initialization
# ---------------------------------------------------------------------------
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []  # List of {"role": "...", "content": "...", "type": "..."}
if "is_processing" not in st.session_state:
    st.session_state.is_processing = False

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

# ---------------------------------------------------------------------------
# WebSocket Communication
# ---------------------------------------------------------------------------
async def send_message_and_receive_stream(message: str, session_id: str, message_container):
    """Connect to the websocket, send the message, and stream the response to the UI."""
    try:
        # Disable ping_interval to prevent silent disconnects on long-running agent tasks
        async with websockets.connect(CORE_WS_URL, ping_interval=None) as ws:
            # Send the user message
            payload = json.dumps({"message": message, "session_id": session_id})
            await ws.send(payload)
            
            # Prepare UI placeholders for the streaming response
            current_thought = ""
            current_response = ""
            
            # Create a placeholder in the UI for the active response
            with message_container:
                thought_expander = st.empty()
                status_placeholder = st.empty()   # single updating status bar
                response_placeholder = st.empty()
            
            while True:
                response = await ws.recv()
                data = json.loads(response)
                msg_type = data.get("type")
                content = data.get("content", "")
                
                if msg_type == "session":
                    # The server assigned or confirmed the session ID
                    if data.get("session_id") != st.session_state.session_id:
                        st.session_state.session_id = data.get("session_id")
                        
                elif msg_type == "thought":
                    # Internal reasoning
                    current_thought += f"\n\n**Thought:**\n{content}"
                    thought_expander.expander("Agent Reasoning", expanded=True).markdown(current_thought)
                    st.session_state.chat_history.append({"role": "assistant", "content": content, "type": "thought"})
                    
                elif msg_type == "status":
                    # Transient keepalive — update a single status bar in-place,
                    # never add a new bubble and never save to history.
                    status_placeholder.info(f"⏳ {content}")

                elif msg_type == "observation":
                    # Tool output
                    current_thought += f"\n\n**Observation:**\n```\n{content}\n```"
                    thought_expander.expander("Agent Reasoning", expanded=True).markdown(current_thought)
                    st.session_state.chat_history.append({"role": "assistant", "content": content, "type": "observation"})
                    
                elif msg_type == "token":
                    # Streaming final output chunk
                    current_response += content
                    response_placeholder.markdown(current_response + "▌")
                    
                elif msg_type == "final":
                    # The final complete response
                    if content and not current_response:
                        current_response = content
                    status_placeholder.empty()   # clear the waiting indicator
                    response_placeholder.markdown(current_response)
                    st.session_state.chat_history.append({"role": "assistant", "content": current_response, "type": "message"})
                    break
                    
                elif msg_type == "ping":
                    # Keepalive from server
                    pass
                    
                elif msg_type == "error":
                    error_msg = f"Agent Error: {content}"
                    st.session_state.chat_history.append({"role": "assistant", "content": error_msg, "type": "message"})
                    break
                    
    except Exception as e:
        error_msg = f"WebSocket Connection Error: {e}\n\n(Is the Agentic OS backend `python main.py serve` running?)"
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
    
    page = st.selectbox("Navigation", ["💬 Terminal", "🧩 Skill Explorer", "🎯 RL Strategy"])
    
    st.markdown("---")
    
    if page == "💬 Terminal":
        st.subheader("Session Management")
        session_input = st.text_input("Session ID", value=st.session_state.session_id)
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Load History", use_container_width=True):
                if session_input:
                    st.session_state.session_id = session_input
                    if load_db_history(session_input):
                        st.success("History hydrated!")
                    else:
                        st.warning("No history found.")
        with col2:
            if st.button("New Session", use_container_width=True):
                st.session_state.session_id = str(uuid.uuid4())
                st.session_state.chat_history = []
                st.rerun()
    
    elif page == "🧩 Skill Explorer": # Skill Explorer Sidebar
        st.subheader("Knowledge Stats")
        s_count, c_count, r_count = get_stats()
        st.metric("Total Skills", s_count)
        st.metric("Total Chunks", c_count)
        st.metric("Hierarchical Links", r_count)
        
        if st.button("🔄 Sync Skills", use_container_width=True):
            with st.spinner("Indexing..."):
                import subprocess
                # Run the indexer from core
                result = subprocess.run([sys.executable, os.path.join(_ROOT, "main.py"), "index"], capture_output=True, text=True)
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
    for msg in st.session_state.chat_history:
        if msg["type"] == "message":
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
        elif msg["type"] == "thought":
            with st.chat_message("assistant", avatar="🧠"):
                with st.expander("Agent Thought", expanded=False):
                    st.markdown(msg["content"])
        elif msg["type"] == "observation":
            with st.chat_message("assistant", avatar="🛠️"):
                with st.expander("Tool Observation", expanded=False):
                    st.markdown(f"```\n{msg['content']}\n```")

    # Handle user input
    prompt = st.chat_input("Ask the Agentic OS...", disabled=st.session_state.is_processing)

    if prompt:
        st.session_state.chat_history.append({"role": "user", "content": prompt, "type": "message"})
        with st.chat_message("user"):
            st.markdown(prompt)
            
        st.session_state.is_processing = True
        with st.chat_message("assistant"):
            message_container = st.container()
            asyncio.run(send_message_and_receive_stream(prompt, st.session_state.session_id, message_container))
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

elif page == "🎯 RL Strategy":
    st.header("🎯 RL Strategy Optimizer")
    st.markdown("Monitor and analyze the **Dynamic Retrieval Depth** policy.")
    
    stats = get_router_stats()
    
    if stats and "arm_stats" in stats:
        # 1. Summary Metrics
        pull_counts = [a["pulls"] for a in stats["arm_stats"]]
        total_episodes = sum(pull_counts)
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Routing Episodes", total_episodes)
        
        # Mapping for better display names
        arm_names = {
            0: "Depth 0 (Spec Off)",
            1: "Depth 0 (Spec On)",
            2: "Depth 1 (Spec Off)",
            3: "Depth 1 (Spec On)",
            4: "Depth 2 (Spec Off)",
            5: "Depth 2 (Spec On)",
            6: "Depth 3 (Spec Off)",
            7: "Depth 3 (Spec On)",
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
