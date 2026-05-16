"""
Skylark BI Agent — Streamlit Frontend
Conversational chat UI with visible API/tool-call traces.
"""

import streamlit as st
import requests
import json
import os

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")

st.set_page_config(
    page_title="Skylark BI Agent",
    page_icon="🚁",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
.main-header {
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
    padding: 1.5rem 2rem; border-radius: 12px; margin-bottom: 1.5rem; color: white;
}
.main-header h1 { margin: 0; font-size: 1.8rem; }
.main-header p  { margin: 0.3rem 0 0; color: #a0b4cc; font-size: 0.9rem; }
.trace-box {
    background: #0d1117; border: 1px solid #30363d; border-radius: 8px;
    padding: 0.8rem 1rem; font-family: monospace; font-size: 0.78rem;
    color: #8b949e; margin-top: 0.5rem;
}
.trace-tool { color: #58a6ff; font-weight: bold; }
.trace-ok   { color: #3fb950; }
.trace-err  { color: #f85149; }
</style>
""", unsafe_allow_html=True)

if "messages" not in st.session_state:
    st.session_state.messages = []
if "traces" not in st.session_state:
    st.session_state.traces = {}

with st.sidebar:
    st.markdown("### 🚁 Skylark BI Agent")
    st.caption("Monday.com — Live Business Intelligence")
    st.divider()
    st.markdown("**📋 Sample Queries**")

    SAMPLES = [
        "How's our pipeline looking for the energy sector this quarter?",
        "Give me a sector-wise breakdown of deal pipeline value.",
        "Which deals are in the proposal stage right now?",
        "How many work orders are currently ongoing vs completed?",
        "What's our receivables situation — how much is uncollected?",
        "Show me all high-probability open deals.",
        "Which sector generates the most work orders?",
        "What deals are on hold or at risk?",
        "Summarize overall pipeline health.",
        "Which owner has the most open deals?",
    ]

    for q in SAMPLES:
        if st.button(q, key=f"sq_{q[:25]}", use_container_width=True):
            st.session_state.pending_query = q

    st.divider()
    if st.button("🗑️ Clear Conversation", use_container_width=True):
        st.session_state.messages = []
        st.session_state.traces = {}
        st.rerun()
    st.divider()
    st.caption("All responses use **live** Monday.com API calls. Zero caching.")

st.markdown("""
<div class="main-header">
    <h1>🚁 Skylark Drones — BI Agent</h1>
    <p>Ask founder-level business questions. Live data from Monday.com boards.</p>
</div>
""", unsafe_allow_html=True)

# Render chat history
for i, msg in enumerate(st.session_state.messages):
    role = msg["role"]
    content = msg["content"]
    with st.chat_message(role, avatar="🧑‍💼" if role == "user" else "🚁"):
        st.markdown(content)
        if role == "assistant" and i in st.session_state.traces:
            trace = st.session_state.traces[i]
            if trace:
                with st.expander(f"🔍 API Calls Made ({len(trace)})", expanded=False):
                    for j, e in enumerate(trace):
                        di = {k: (f"[{len(v)} items]" if isinstance(v, list) and len(v) > 3 else v)
                              for k, v in e["inputs"].items()}
                        cls = "trace-err" if e.get("error") else "trace-ok"
                        st.markdown(f"""<div class="trace-box">
<span class="trace-tool">#{j+1} {e['tool']}</span><br/>
<b>Inputs:</b> {json.dumps(di, default=str)}<br/>
<span class="{cls}">{e['result_summary']}</span>
</div>""", unsafe_allow_html=True)

# Input
pending = st.session_state.pop("pending_query", None)
user_input = st.chat_input("Ask a business question about deals or work orders...") or pending

if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input})

    with st.chat_message("user", avatar="🧑‍💼"):
        st.markdown(user_input)

    api_messages = [{"role": m["role"], "content": m["content"]}
                    for m in st.session_state.messages if isinstance(m["content"], str)]

    with st.chat_message("assistant", avatar="🚁"):
        with st.spinner("Querying Monday.com boards live..."):
            try:
                resp = requests.post(f"{BACKEND_URL}/chat",
                                     json={"messages": api_messages}, timeout=120)
                resp.raise_for_status()
                data = resp.json()
                reply = data["reply"]
                trace = data.get("trace", [])

                st.markdown(reply)

                msg_idx = len(st.session_state.messages)
                st.session_state.traces[msg_idx] = trace

                if trace:
                    with st.expander(f"🔍 API Calls Made ({len(trace)})", expanded=True):
                        for j, e in enumerate(trace):
                            di = {k: (f"[{len(v)} items]" if isinstance(v, list) and len(v) > 3 else v)
                                  for k, v in e["inputs"].items()}
                            cls = "trace-err" if e.get("error") else "trace-ok"
                            st.markdown(f"""<div class="trace-box">
<span class="trace-tool">#{j+1} {e['tool']}</span><br/>
<b>Inputs:</b> {json.dumps(di, default=str)}<br/>
<span class="{cls}">{e['result_summary']}</span>
</div>""", unsafe_allow_html=True)

                st.session_state.messages.append({"role": "assistant", "content": reply})

            except requests.exceptions.ConnectionError:
                err = "⚠️ Cannot connect to backend. Is the FastAPI server running on port 8000?"
                st.error(err)
                st.session_state.messages.append({"role": "assistant", "content": err})
            except Exception as ex:
                err = f"⚠️ Error: {ex}"
                st.error(err)
                st.session_state.messages.append({"role": "assistant", "content": err})

    st.rerun()
