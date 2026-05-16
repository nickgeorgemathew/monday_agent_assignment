"""
app.py
Streamlit frontend for the Skylark Drones BI Agent.
Run: streamlit run app.py
"""

import streamlit as st
import json
import time
from agent import chat

# ─────────────────────────────────────────────
# Page config
# ─────────────────────────────────────────────

st.set_page_config(
    page_title="Skylark Drones — BI Agent",
    page_icon="🚁",
    layout="wide",
)

# ─────────────────────────────────────────────
# Styling
# ─────────────────────────────────────────────

st.markdown("""
<style>
.stApp { background-color: #0f1117; }
.main-header {
    background: linear-gradient(135deg, #1a1f2e 0%, #232b3e 100%);
    padding: 1.5rem 2rem;
    border-radius: 12px;
    border: 1px solid #2d3748;
    margin-bottom: 1rem;
}
.caveat-box {
    background: #1a1a2e;
    border-left: 3px solid #f59e0b;
    padding: 0.75rem 1rem;
    border-radius: 0 8px 8px 0;
    font-size: 0.85rem;
    color: #fbbf24;
    margin-top: 0.5rem;
}
.trace-box {
    background: #0d1117;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 0.75rem;
    font-family: monospace;
    font-size: 0.8rem;
    color: #58a6ff;
}
.metric-card {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 1rem;
    text-align: center;
}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# Header
# ─────────────────────────────────────────────

st.markdown("""
<div class="main-header">
    <h2 style="margin:0; color:#e2e8f0;">🚁 Skylark Drones — BI Agent</h2>
    <p style="margin:0; color:#94a3b8; font-size:0.9rem;">
        Live Monday.com data · Ask founder-level business questions
    </p>
</div>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# Sidebar — suggested queries
# ─────────────────────────────────────────────

with st.sidebar:
    st.markdown("### 💡 Suggested Queries")
    suggestions = [
        "How's our overall pipeline looking?",
        "Which sector is performing best?",
        "What deals are closing this quarter?",
        "Show me revenue and collection status",
        "Any overdue work orders?",
        "Mining sector pipeline breakdown",
        "Who is the top performing owner?",
        "What's our Renewables pipeline for Q1 2026?",
    ]
    for s in suggestions:
        if st.button(s, key=f"sug_{s}", use_container_width=True):
            st.session_state["prefill"] = s

    st.markdown("---")
    st.markdown("### ⚙️ Settings")
    show_raw = st.checkbox("Show raw JSON in traces", value=False)
    st.markdown("---")
    if st.button("🗑️ Clear conversation", use_container_width=True):
        st.session_state["messages"] = []
        st.session_state["traces"] = []
        st.rerun()

# ─────────────────────────────────────────────
# Session state
# ─────────────────────────────────────────────

if "messages" not in st.session_state:
    st.session_state["messages"] = []
if "traces" not in st.session_state:
    st.session_state["traces"] = []
if "prefill" not in st.session_state:
    st.session_state["prefill"] = ""

# ─────────────────────────────────────────────
# Display chat history
# ─────────────────────────────────────────────

chat_container = st.container()

with chat_container:
    for i, msg in enumerate(st.session_state["messages"]):
        role = msg["role"]
        content = msg["content"] if isinstance(msg["content"], str) else ""

        if role == "user":
            with st.chat_message("user"):
                st.markdown(content)
        elif role == "assistant":
            with st.chat_message("assistant", avatar="🚁"):
                st.markdown(content)

                # Show traces if available
                trace_key = f"trace_{i}"
                if trace_key in st.session_state:
                    trace_data = st.session_state[trace_key]
                    traces = trace_data.get("traces", [])
                    caveats = trace_data.get("caveats", [])

                    # Caveats
                    if caveats:
                        unique_caveats = list(dict.fromkeys(caveats))
                        caveat_html = "<br>".join(f"⚠️ {c}" for c in unique_caveats[:5])
                        st.markdown(
                            f'<div class="caveat-box"><strong>Data Quality Notes:</strong><br>{caveat_html}</div>',
                            unsafe_allow_html=True
                        )

                    # Tool call traces
                    if traces:
                        total_calls = sum(len(t.get("api_calls", [])) for t in traces)
                        total_latency = sum(
                            ac.get("latency_ms", 0)
                            for t in traces
                            for ac in t.get("api_calls", [])
                        )

                        with st.expander(
                            f"🔍 {total_calls} API call(s) made — {total_latency}ms total",
                            expanded=False
                        ):
                            for t in traces:
                                st.markdown(f"**Tool:** `{t.get('tool')}`")
                                st.markdown(f"**Input:** `{json.dumps(t.get('input', {}))}`")
                                for ac in t.get("api_calls", []):
                                    cols = st.columns(4)
                                    cols[0].metric("Board", ac.get("board", "—"))
                                    cols[1].metric("Items Fetched", ac.get("items_fetched", "—"))
                                    cols[2].metric("Latency", f"{ac.get('latency_ms', 0)}ms")
                                    cols[3].metric("Board ID", ac.get("board_id", "—")[:8] + "…" if ac.get("board_id") else "—")
                                if show_raw:
                                    st.code(json.dumps(t, indent=2, default=str), language="json")
                                st.divider()

# ─────────────────────────────────────────────
# Input
# ─────────────────────────────────────────────

prefill = st.session_state.pop("prefill", "")
user_input = st.chat_input("Ask a business question...", key="chat_input")

# Handle prefill from sidebar button
if prefill and not user_input:
    user_input = prefill

if user_input:
    # Add user message
    st.session_state["messages"].append({"role": "user", "content": user_input})

    with st.chat_message("user"):
        st.markdown(user_input)

    # Build conversation history for agent (filter to only string content)
    history = []
    for msg in st.session_state["messages"]:
        content = msg["content"]
        if isinstance(content, str) and content.strip():
            history.append({"role": msg["role"], "content": content})

    # Stream response
    with st.chat_message("assistant", avatar="🚁"):
        with st.spinner("Fetching live data from Monday.com..."):
            start_time = time.time()
            result = chat(history)
            elapsed = round((time.time() - start_time) * 1000)

        reply = result["reply"]
        traces = result["traces"]
        caveats = result["caveats"]

        st.markdown(reply)

        # Data quality caveats
        if caveats:
            unique_caveats = list(dict.fromkeys(caveats))
            caveat_html = "<br>".join(f"⚠️ {c}" for c in unique_caveats[:5])
            st.markdown(
                f'<div class="caveat-box"><strong>Data Quality Notes:</strong><br>{caveat_html}</div>',
                unsafe_allow_html=True
            )

        # Tool call traces
        if traces:
            total_calls = sum(len(t.get("api_calls", [])) for t in traces)
            total_latency = sum(
                ac.get("latency_ms", 0)
                for t in traces
                for ac in t.get("api_calls", [])
            )

            with st.expander(
                f"🔍 {total_calls} API call(s) made — {total_latency}ms total",
                expanded=True  # expanded on fresh response
            ):
                for t in traces:
                    st.markdown(f"**Tool:** `{t.get('tool')}`")
                    st.markdown(f"**Input:** `{json.dumps(t.get('input', {}))}`")
                    for ac in t.get("api_calls", []):
                        cols = st.columns(4)
                        cols[0].metric("Board", ac.get("board", "—"))
                        cols[1].metric("Items Fetched", ac.get("items_fetched", "—"))
                        cols[2].metric("Latency", f"{ac.get('latency_ms', 0)}ms")
                        cols[3].metric("Board ID", ac.get("board_id", "—"))
                    if show_raw:
                        st.code(json.dumps(t, indent=2, default=str), language="json")
                    st.divider()

    # Persist to session state
    msg_idx = len(st.session_state["messages"])
    st.session_state["messages"].append({"role": "assistant", "content": reply})
    st.session_state[f"trace_{msg_idx}"] = {"traces": traces, "caveats": caveats}

    st.rerun()
