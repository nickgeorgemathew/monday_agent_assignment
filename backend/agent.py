"""
Skylark Drones BI Agent — Claude-powered tool-calling agent.
All Monday.com API calls are live at query time with full trace visibility.
"""
import os
import json
import time
from anthropic import Anthropic
from backend.monday_tools import (
    get_board_schema, get_board_items, search_items_by_value, enrich_items,
)

client = Anthropic()

TOOLS = [
    {
        "name": "get_board_schema",
        "description": "Fetches the column structure of a Monday.com board. Call this first when you need to understand what columns exist before querying items.",
        "input_schema": {
            "type": "object",
            "properties": {
                "board_id": {"type": "string", "description": "Monday.com board ID. Use env var DEALS_BOARD_ID for deals, WO_BOARD_ID for work orders."}
            },
            "required": ["board_id"],
        },
    },
    {
        "name": "get_board_items",
        "description": "Fetches ALL items from a Monday.com board with a live API call. Use for aggregate queries, trend analysis, or when you need the full dataset. board_type must be 'deals' or 'work_orders'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "board_id": {"type": "string"},
                "board_type": {"type": "string", "enum": ["deals", "work_orders"]},
            },
            "required": ["board_id", "board_type"],
        },
    },
    {
        "name": "search_items_by_value",
        "description": "Searches a Monday.com board for items matching a specific column value. More efficient than fetching all items when filtering by a single known value.",
        "input_schema": {
            "type": "object",
            "properties": {
                "board_id": {"type": "string"},
                "board_type": {"type": "string", "enum": ["deals", "work_orders"]},
                "column_id": {"type": "string", "description": "Monday column ID"},
                "value": {"type": "string"},
            },
            "required": ["board_id", "board_type", "column_id", "value"],
        },
    },
]

def execute_tool(tool_name: str, tool_input: dict) -> tuple:
    """Execute a tool call and return (result, latency_ms)."""
    start = time.time()
    if tool_name == "get_board_schema":
        result = get_board_schema(tool_input["board_id"])
    elif tool_name == "get_board_items":
        raw = get_board_items(tool_input["board_id"])
        result = enrich_items(raw, tool_input["board_type"])
    elif tool_name == "search_items_by_value":
        raw = search_items_by_value(tool_input["board_id"], tool_input["column_id"], tool_input["value"])
        result = enrich_items(raw, tool_input["board_type"])
    else:
        result = {"error": f"Unknown tool: {tool_name}"}
    return result, round((time.time() - start) * 1000)

def run_agent(user_message: str, conversation_history: list, deals_board_id: str, wo_board_id: str) -> dict:
    """Runs the agent loop for a single user message. Returns answer, traces, updated history."""
    traces = []
    system_prompt = f"""You are a Business Intelligence assistant for Skylark Drones — a drone services company.
You have access to two live Monday.com boards:
- Deals Board (ID: {deals_board_id}): Pipeline — deal names, stages, sectors, values, close dates, probability.
- Work Orders Board (ID: {wo_board_id}): Operations — WO status, revenue, billing, collection.

Board IDs for tool calls: Deals={deals_board_id}, Work Orders={wo_board_id}

Data context:
- Deal stages: A=Lead Generated through O=Not Relevant, G=Project Won, L=Lost, Project Completed=done
- Sectors: Mining, Powerline, Renewables, Railways, Construction, Others, DSP, Aviation, Manufacturing
- Deal values and WO amounts are masked (relative figures, not absolute revenue)
- Closure probability: High=0.8, Medium=0.5, Low=0.2
- Some rows have missing dates/probabilities — always mention data quality caveats

Rules:
1. ALWAYS make live API calls — never assume or hallucinate data values
2. Use _sector_normalized, _amount_numeric, _probability_score, _stage_rank fields for analysis
3. Always report quality_notes (missing counts) at the end of your answer
4. Cross-reference both boards when asked about revenue + pipeline together
5. Format large numbers as lakhs (1,00,000) or crores where appropriate
6. Be concise but insightful — founders want key numbers and actionable signals"""

    messages = conversation_history + [{"role": "user", "content": user_message}]

    while True:
        response = client.messages.create(
            model="claude-sonnet-4-6", max_tokens=4096,
            system=system_prompt, tools=TOOLS, messages=messages,
        )
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            answer = "".join(b.text for b in response.content if hasattr(b, "text"))
            return {"answer": answer, "traces": traces, "updated_history": messages}

        elif response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result, latency_ms = execute_tool(block.name, block.input)
                    traces.append({
                        "tool": block.name, "input": block.input,
                        "latency_ms": latency_ms,
                        "result_summary": _summarize(result),
                        "timestamp": time.strftime("%H:%M:%S"),
                    })
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result, default=str),
                    })
            messages.append({"role": "user", "content": tool_results})
        else:
            break

    return {"answer": "Agent stopped unexpectedly.", "traces": traces, "updated_history": messages}

def _summarize(result) -> str:
    if isinstance(result, dict):
        if "items" in result:
            n = len(result["items"])
            qn = result.get("quality_notes", {})
            return (f"{n} items — missing: {qn.get('missing_sector',0)} sectors, "
                    f"{qn.get('missing_amount',0)} amounts, {qn.get('missing_date',0)} dates")
        elif "columns" in result:
            return f"Schema: {len(result['columns'])} cols from '{result.get('board_name','')}'"
        elif "error" in result:
            return f"Error: {result['error']}"
    return str(result)[:120]
