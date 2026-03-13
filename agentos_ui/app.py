import streamlit as st
import asyncio
import websockets
import json
import requests
import uuid
from datetime import datetime

# Configure the page
st.set_page_config(
    page_title="Agentic OS",
    page_icon="🌌",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Configuration constants
CORE_API_URL = "http://localhost:8000"
CORE_WS_URL = "ws://localhost:8000/chat"

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
                    # If this was streamed via tokens, the final might just be a completion signal.
                    # If not streamed via tokens, this contains the full text.
                    if content and not current_response:
                        current_response = content
                    response_placeholder.markdown(current_response)
                    st.session_state.chat_history.append({"role": "assistant", "content": current_response, "type": "message"})
                    break
                    
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

# Sidebar for session management
with st.sidebar:
    st.title("🌌 Agentic OS")
    st.markdown("---")
    
    st.subheader("Session Management")
    session_input = st.text_input("Session ID", value=st.session_state.session_id)
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Load History", use_container_width=True):
            if session_input:
                st.session_state.session_id = session_input
                if load_db_history(session_input):
                    st.success("History hydrated from pgvector!")
                else:
                    st.warning("No history found or DB unreachable.")
    with col2:
        if st.button("New Session", use_container_width=True):
            st.session_state.session_id = str(uuid.uuid4())
            st.session_state.chat_history = []
            st.rerun()

    st.markdown("---")
    st.caption("Ephemeral state stored in `st.session_state`. Permanent memory written to `pgvector`.")

# Main Chat Interface
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
    # Append to ephemeral state
    st.session_state.chat_history.append({"role": "user", "content": prompt, "type": "message"})
    
    # Render user message immediately
    with st.chat_message("user"):
        st.markdown(prompt)
        
    # Prepare the assistant's response container
    st.session_state.is_processing = True
    with st.chat_message("assistant"):
        message_container = st.container()
        
        # Run the async websocket loop
        asyncio.run(send_message_and_receive_stream(prompt, st.session_state.session_id, message_container))
        
    st.rerun()
