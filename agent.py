"""
agent.py
The core BI agent — Claude with tool-calling loop.
Handles multi-turn conversations and returns structured responses with traces.
"""

import os
import json
from anthropic import Anthropic
from agent_tools import TOOL_DEFINITIONS, execute_tool

client = Anthropic()

SYSTEM_PROMPT = """You are a Business Intelligence agent for Skylark Drones — a drone services company.
You have access to two live data sources on Monday.com:
1. **Deals Board** — the sales funnel with 300+ deals across sectors like Mining, Renewables, Construction, Railways, Aviation, Powerline, Manufacturing, Security & Surveillance.
2. **Work Orders Board** — active/completed projects with financial data including billed amounts, collected amounts, and receivables.

Your job is to answer founder-level business questions accurately and conversationally.

**Behavior guidelines:**
- Always use the available tools to fetch LIVE data — never make up numbers.
- When data has quality issues (missing dates, null values, inconsistent formats), acknowledge them transparently using the caveats returned by your tools.
- Be specific with numbers — founders want concrete figures, not vague summaries.
- If a question spans both boards (e.g., revenue outlook), call tools for both.
- For ambiguous queries, make a reasonable assumption, state it, then answer.
- Keep responses concise but insightful. Lead with the key metric, then break it down.
- Format numbers as: ₹1.2Cr, ₹45L, etc. for Indian rupee values where appropriate.
- When you spot a business risk or opportunity in the data, flag it proactively.

**Data context:**
- Deal values are masked/anonymized but relative magnitudes are real.
- Closure probability is text-based (High/Medium/Low) — interpret accordingly.
- Work order amounts exclude GST unless specified.
- The company operates across multiple sectors; "energy" typically maps to Renewables + Powerline."""

MAX_TOOL_ROUNDS = 5  # prevent infinite loops


def chat(messages: list, on_trace=None) -> dict:
    """
    Run one turn of the agent.
    messages: full conversation history in Anthropic format
    on_trace: optional callback(trace_dict) called each time a tool executes
    Returns: { reply: str, traces: [...], caveats: [...] }
    """
    all_traces = []
    all_caveats = []
    current_messages = list(messages)

    for round_num in range(MAX_TOOL_ROUNDS):
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOL_DEFINITIONS,
            messages=current_messages,
        )

        # If no tool calls, we're done
        if response.stop_reason == "end_turn":
            reply_text = ""
            for block in response.content:
                if hasattr(block, "text"):
                    reply_text += block.text
            return {
                "reply": reply_text,
                "traces": all_traces,
                "caveats": all_caveats,
            }

        # Process tool calls
        if response.stop_reason == "tool_use":
            tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
            tool_results = []

            for block in tool_use_blocks:
                tool_name = block.name
                tool_input = block.input

                # Execute tool
                result = execute_tool(tool_name, tool_input)

                # Capture trace
                trace = result.get("trace", {})
                trace["round"] = round_num + 1
                all_traces.append(trace)
                if on_trace:
                    on_trace(trace)

                # Collect caveats
                if result.get("caveats"):
                    all_caveats.extend(result["caveats"])

                # Prepare result for Claude (without the trace metadata)
                clean_result = {
                    "result": result.get("result"),
                    "caveats": result.get("caveats", []),
                    "error": result.get("error"),
                }

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(clean_result, default=str),
                })

            # Add assistant response + tool results to conversation
            current_messages.append({"role": "assistant", "content": response.content})
            current_messages.append({"role": "user", "content": tool_results})

    # Fallback if max rounds hit
    return {
        "reply": "I reached the maximum number of tool calls. Please try a more specific question.",
        "traces": all_traces,
        "caveats": all_caveats,
    }
