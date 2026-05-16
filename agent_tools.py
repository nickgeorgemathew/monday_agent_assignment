"""
agent_tools.py
Defines the tools available to the Claude agent + their executor functions.
Every tool makes a LIVE API call — nothing is cached.
"""

import os
from monday_client import get_board_as_records, get_all_boards
from data_normalizer import normalize_records, ACTIVE_DEAL_STAGES
from datetime import datetime, date
from collections import defaultdict

# Board IDs — set via environment variables after Monday.com setup
DEALS_BOARD_ID = os.getenv("MONDAY_DEALS_BOARD_ID", "")
WORK_ORDERS_BOARD_ID = os.getenv("MONDAY_WORK_ORDERS_BOARD_ID", "")


# ─────────────────────────────────────────────
# Tool definitions (for Claude API tool_choice)
# ─────────────────────────────────────────────

TOOL_DEFINITIONS = [
    {
        "name": "get_pipeline_summary",
        "description": (
            "Get a summary of the deal pipeline. Returns total deals, value breakdown by stage "
            "and sector, active vs closed deals, and deals closing this quarter/month. "
            "Use this for questions like: 'How's our pipeline?', 'What's the deal flow?', "
            "'Show me pipeline health', 'What are our open deals?'"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "sector_filter": {
                    "type": "string",
                    "description": "Optional sector to filter by (e.g., 'Mining', 'Renewables'). Leave empty for all sectors.",
                },
                "status_filter": {
                    "type": "string",
                    "description": "Optional deal status filter: 'Open', 'Won', 'Dead', 'On Hold'.",
                },
                "quarter_filter": {
                    "type": "string",
                    "description": "Optional quarter filter like 'Q1 2026', 'Q4 2025'. Filters by tentative close date.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_sector_analysis",
        "description": (
            "Deep-dive analysis for a specific sector or all sectors. Returns deal count, "
            "total value, average deal size, win rate, and stage distribution per sector. "
            "Use for: 'How is energy sector doing?', 'Which sector is performing best?', "
            "'Give me mining sector breakdown'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "sector": {
                    "type": "string",
                    "description": "Specific sector name, or leave empty for all sectors.",
                }
            },
            "required": [],
        },
    },
    {
        "name": "get_work_order_status",
        "description": (
            "Fetch work order data — execution status, billing, collection, overdue items. "
            "Use for: 'What work orders are pending?', 'Show billing status', "
            "'Which work orders are overdue?', 'What's our collection status?'"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "sector_filter": {
                    "type": "string",
                    "description": "Filter by sector, e.g. 'Mining'.",
                },
                "status_filter": {
                    "type": "string",
                    "description": "Filter by WO status: 'Open', 'Closed', 'Completed', 'Not Started', etc.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_revenue_insights",
        "description": (
            "Cross-board revenue analysis combining deals and work orders. Returns total pipeline "
            "value, billed amounts, collected amounts, outstanding receivables, and month-wise trends. "
            "Use for: 'What's our revenue outlook?', 'How much have we billed?', "
            "'Show me outstanding receivables', 'Revenue by sector'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "breakdown_by": {
                    "type": "string",
                    "description": "Group results by: 'sector', 'month', 'owner', or 'status'.",
                    "enum": ["sector", "month", "owner", "status"],
                }
            },
            "required": [],
        },
    },
    {
        "name": "get_deals_closing_soon",
        "description": (
            "Find deals with tentative close dates approaching. Returns list of deals sorted "
            "by close date with stage and value. Use for: 'What's closing this month?', "
            "'Show deals due this quarter', 'What should we prioritize?'"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "days_ahead": {
                    "type": "integer",
                    "description": "Number of days to look ahead (default 90).",
                },
                "sector_filter": {
                    "type": "string",
                    "description": "Optional sector filter.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "search_deal_by_name",
        "description": (
            "Look up a specific deal or company by name. Returns all deal details. "
            "Use when the user mentions a specific deal name or client."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Deal name or partial name to search for.",
                }
            },
            "required": ["name"],
        },
    },
    {
        "name": "get_team_performance",
        "description": (
            "Analyze deal performance by owner/BD personnel. Returns deals per owner, "
            "win rates, and pipeline value. Use for: 'Who is performing best?', "
            "'Show me owner-wise pipeline', 'Team performance breakdown'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
]


# ─────────────────────────────────────────────
# Tool executor
# ─────────────────────────────────────────────

def execute_tool(tool_name: str, tool_input: dict) -> dict:
    """
    Routes tool calls to the correct function.
    Returns { result: <data>, trace: <api_call_info>, caveats: [...] }
    """
    trace = {"tool": tool_name, "input": tool_input, "api_calls": []}

    try:
        if tool_name == "get_pipeline_summary":
            return _get_pipeline_summary(tool_input, trace)
        elif tool_name == "get_sector_analysis":
            return _get_sector_analysis(tool_input, trace)
        elif tool_name == "get_work_order_status":
            return _get_work_order_status(tool_input, trace)
        elif tool_name == "get_revenue_insights":
            return _get_revenue_insights(tool_input, trace)
        elif tool_name == "get_deals_closing_soon":
            return _get_deals_closing_soon(tool_input, trace)
        elif tool_name == "search_deal_by_name":
            return _search_deal_by_name(tool_input, trace)
        elif tool_name == "get_team_performance":
            return _get_team_performance(tool_input, trace)
        else:
            return {"error": f"Unknown tool: {tool_name}", "trace": trace}
    except Exception as e:
        return {"error": str(e), "trace": trace}


# ─────────────────────────────────────────────
# Tool implementations
# ─────────────────────────────────────────────

def _fetch_deals(trace: dict) -> tuple[list, list]:
    """Fetch and normalize deals. Updates trace in place."""
    result = get_board_as_records(DEALS_BOARD_ID)
    trace["api_calls"].append({
        "board": "Deals",
        "board_id": DEALS_BOARD_ID,
        "items_fetched": result["total"],
        "latency_ms": result["latency_ms"],
    })
    normalized = normalize_records(result["records"], "deal")
    return normalized["records"], normalized["caveats"]


def _fetch_work_orders(trace: dict) -> tuple[list, list]:
    """Fetch and normalize work orders. Updates trace in place."""
    result = get_board_as_records(WORK_ORDERS_BOARD_ID)
    trace["api_calls"].append({
        "board": "Work Orders",
        "board_id": WORK_ORDERS_BOARD_ID,
        "items_fetched": result["total"],
        "latency_ms": result["latency_ms"],
    })
    normalized = normalize_records(result["records"], "work_order")
    return normalized["records"], normalized["caveats"]


def _get_pipeline_summary(params: dict, trace: dict) -> dict:
    records, caveats = _fetch_deals(trace)

    sector_filter = (params.get("sector_filter") or "").strip().lower()
    status_filter = (params.get("status_filter") or "").strip().lower()
    quarter_filter = params.get("quarter_filter", "").strip()

    if sector_filter:
        records = [r for r in records if r.get("Sector", "").lower() == sector_filter]
    if status_filter:
        records = [r for r in records if r.get("Deal Status", "").lower() == status_filter]

    # Quarter filter
    if quarter_filter:
        try:
            q, yr = quarter_filter.upper().split()
            q_num = int(q[1])
            yr_num = int(yr)
            q_months = {1: (1, 3), 2: (4, 6), 3: (7, 9), 4: (10, 12)}
            m_start, m_end = q_months[q_num]
            filtered = []
            for r in records:
                d = r.get("_close_date", "")
                if d:
                    try:
                        dt = datetime.fromisoformat(d)
                        if dt.year == yr_num and m_start <= dt.month <= m_end:
                            filtered.append(r)
                    except Exception:
                        pass
            records = filtered
        except Exception:
            caveats.append(f"Could not parse quarter filter '{quarter_filter}' — showing all")

    by_stage = defaultdict(lambda: {"count": 0, "value": 0})
    by_status = defaultdict(lambda: {"count": 0, "value": 0})
    by_sector = defaultdict(lambda: {"count": 0, "value": 0})
    total_value = 0
    active_count = 0

    for r in records:
        stage = r.get("Deal Stage", "Unknown")
        status = r.get("Deal Status", "Unknown")
        sector = r.get("Sector", "Unknown")
        val = r.get("_value_numeric") or 0

        by_stage[stage]["count"] += 1
        by_stage[stage]["value"] += val
        by_status[status]["count"] += 1
        by_status[status]["value"] += val
        by_sector[sector]["count"] += 1
        by_sector[sector]["value"] += val
        total_value += val
        if r.get("_is_active"):
            active_count += 1

    return {
        "result": {
            "total_deals": len(records),
            "active_deals": active_count,
            "total_pipeline_value": round(total_value),
            "by_stage": {k: dict(v) for k, v in sorted(by_stage.items())},
            "by_status": {k: dict(v) for k, v in sorted(by_status.items())},
            "by_sector": {k: dict(v) for k, v in sorted(by_sector.items())},
            "filters_applied": {
                "sector": sector_filter or None,
                "status": status_filter or None,
                "quarter": quarter_filter or None,
            },
        },
        "caveats": caveats,
        "trace": trace,
    }


def _get_sector_analysis(params: dict, trace: dict) -> dict:
    records, caveats = _fetch_deals(trace)

    target_sector = (params.get("sector") or "").strip().lower()

    if target_sector:
        records = [r for r in records if r.get("Sector", "").lower() == target_sector]

    sectors = defaultdict(lambda: {
        "count": 0, "total_value": 0, "won": 0, "lost": 0, "open": 0,
        "avg_value": 0, "stages": defaultdict(int)
    })

    for r in records:
        s = r.get("Sector", "Unknown")
        val = r.get("_value_numeric") or 0
        status = r.get("Deal Status", "").lower()
        stage = r.get("Deal Stage", "Unknown")

        sectors[s]["count"] += 1
        sectors[s]["total_value"] += val
        sectors[s]["stages"][stage] += 1
        if status == "won":
            sectors[s]["won"] += 1
        elif status == "dead":
            sectors[s]["lost"] += 1
        elif status == "open":
            sectors[s]["open"] += 1

    result = {}
    for s, data in sorted(sectors.items(), key=lambda x: -x[1]["total_value"]):
        win_rate = round(data["won"] / data["count"] * 100, 1) if data["count"] > 0 else 0
        avg_val = round(data["total_value"] / data["count"]) if data["count"] > 0 else 0
        result[s] = {
            "deal_count": data["count"],
            "total_value": round(data["total_value"]),
            "avg_deal_value": avg_val,
            "win_rate_pct": win_rate,
            "open": data["open"],
            "won": data["won"],
            "lost": data["lost"],
            "top_stages": dict(sorted(data["stages"].items(), key=lambda x: -x[1])[:5]),
        }

    return {"result": result, "caveats": caveats, "trace": trace}


def _get_work_order_status(params: dict, trace: dict) -> dict:
    records, caveats = _fetch_work_orders(trace)

    sector_filter = (params.get("sector_filter") or "").strip().lower()
    status_filter = (params.get("status_filter") or "").strip().lower()

    if sector_filter:
        records = [r for r in records if r.get("Sector", "").lower() == sector_filter]
    if status_filter:
        records = [r for r in records if status_filter in r.get("Execution Status", "").lower()]

    by_status = defaultdict(int)
    by_billing = defaultdict(int)
    by_sector = defaultdict(int)
    overdue = []
    today = date.today()

    for r in records:
        by_status[r.get("Execution Status", "Unknown")] += 1
        by_billing[r.get("Billing Status", "Unknown")] += 1
        by_sector[r.get("Sector", "Unknown")] += 1

        end = r.get("_probable_end_date", "")
        if end:
            try:
                end_date = datetime.fromisoformat(end).date()
                exec_status = r.get("Execution Status", "")
                if end_date < today and exec_status not in ("Completed", "Executed until current month"):
                    overdue.append({
                        "name": r.get("_name", ""),
                        "sector": r.get("Sector", ""),
                        "end_date": end,
                        "status": exec_status,
                    })
            except Exception:
                pass

    return {
        "result": {
            "total_work_orders": len(records),
            "by_execution_status": dict(by_status),
            "by_billing_status": dict(by_billing),
            "by_sector": dict(by_sector),
            "overdue_items": overdue[:20],
            "overdue_count": len(overdue),
        },
        "caveats": caveats,
        "trace": trace,
    }


def _get_revenue_insights(params: dict, trace: dict) -> dict:
    deals, deal_caveats = _fetch_deals(trace)
    work_orders, wo_caveats = _fetch_work_orders(trace)

    breakdown = params.get("breakdown_by", "sector")

    # Pipeline value from deals
    total_pipeline = sum(r.get("_value_numeric") or 0 for r in deals if r.get("_is_active"))
    won_value = sum(r.get("_value_numeric") or 0 for r in deals if r.get("Deal Status") == "Won")

    # Work order financials
    total_billed = sum(r.get("_billed_excl_gst_numeric") or 0 for r in work_orders)
    total_collected = sum(r.get("_collected_amount_numeric") or 0 for r in work_orders)
    total_receivable = sum(r.get("_amount_receivable_numeric") or 0 for r in work_orders)
    total_contracted = sum(r.get("_amount_excl_gst_numeric") or 0 for r in work_orders)

    # Sector breakdown
    sector_data = defaultdict(lambda: {"pipeline": 0, "billed": 0, "collected": 0, "deals": 0, "work_orders": 0})

    for r in deals:
        s = r.get("Sector", "Unknown")
        if r.get("_is_active"):
            sector_data[s]["pipeline"] += r.get("_value_numeric") or 0
        sector_data[s]["deals"] += 1

    for r in work_orders:
        s = r.get("Sector", "Unknown")
        sector_data[s]["billed"] += r.get("_billed_excl_gst_numeric") or 0
        sector_data[s]["collected"] += r.get("_collected_amount_numeric") or 0
        sector_data[s]["work_orders"] += 1

    return {
        "result": {
            "summary": {
                "total_active_pipeline": round(total_pipeline),
                "won_deal_value": round(won_value),
                "total_contracted_wo": round(total_contracted),
                "total_billed": round(total_billed),
                "total_collected": round(total_collected),
                "total_receivable": round(total_receivable),
                "collection_rate_pct": round(total_collected / total_billed * 100, 1) if total_billed > 0 else 0,
            },
            "by_sector": {
                s: {k: round(v) if isinstance(v, float) else v for k, v in data.items()}
                for s, data in sorted(sector_data.items(), key=lambda x: -x[1]["pipeline"])
            },
        },
        "caveats": deal_caveats + wo_caveats,
        "trace": trace,
    }


def _get_deals_closing_soon(params: dict, trace: dict) -> dict:
    records, caveats = _fetch_deals(trace)

    days_ahead = params.get("days_ahead", 90)
    sector_filter = (params.get("sector_filter") or "").strip().lower()
    today = date.today()

    closing = []
    for r in records:
        d = r.get("_close_date", "")
        if not d:
            continue
        try:
            dt = datetime.fromisoformat(d).date()
            delta = (dt - today).days
            if 0 <= delta <= days_ahead:
                if sector_filter and r.get("Sector", "").lower() != sector_filter:
                    continue
                closing.append({
                    "name": r.get("_name", ""),
                    "sector": r.get("Sector", ""),
                    "stage": r.get("Deal Stage", ""),
                    "status": r.get("Deal Status", ""),
                    "close_date": d,
                    "days_away": delta,
                    "value": r.get("_value_numeric"),
                    "probability": r.get("Closure Probability", ""),
                })
        except Exception:
            continue

    closing.sort(key=lambda x: x["days_away"])

    return {
        "result": {
            "deals_closing_in_next_days": days_ahead,
            "count": len(closing),
            "total_value": round(sum(d.get("value") or 0 for d in closing)),
            "deals": closing[:30],
        },
        "caveats": caveats,
        "trace": trace,
    }


def _search_deal_by_name(params: dict, trace: dict) -> dict:
    records, caveats = _fetch_deals(trace)

    name = params.get("name", "").strip().lower()
    matches = [
        r for r in records
        if name in (r.get("_name") or "").lower()
        or name in (r.get("Client Code") or "").lower()
    ]

    return {
        "result": {
            "query": name,
            "matches_found": len(matches),
            "deals": [
                {
                    "name": r.get("_name"),
                    "client": r.get("Client Code"),
                    "sector": r.get("Sector"),
                    "stage": r.get("Deal Stage"),
                    "status": r.get("Deal Status"),
                    "value": r.get("_value_numeric"),
                    "close_date": r.get("_close_date"),
                    "probability": r.get("Closure Probability"),
                    "owner": r.get("Owner Code"),
                }
                for r in matches[:20]
            ],
        },
        "caveats": caveats,
        "trace": trace,
    }


def _get_team_performance(params: dict, trace: dict) -> dict:
    records, caveats = _fetch_deals(trace)

    owners = defaultdict(lambda: {"deals": 0, "value": 0, "won": 0, "open": 0, "dead": 0})

    for r in records:
        owner = r.get("Owner Code", "Unknown")
        owners[owner]["deals"] += 1
        owners[owner]["value"] += r.get("_value_numeric") or 0
        status = r.get("Deal Status", "").lower()
        if status == "won":
            owners[owner]["won"] += 1
        elif status == "open":
            owners[owner]["open"] += 1
        elif status == "dead":
            owners[owner]["dead"] += 1

    result = {}
    for owner, data in sorted(owners.items(), key=lambda x: -x[1]["value"]):
        win_rate = round(data["won"] / data["deals"] * 100, 1) if data["deals"] > 0 else 0
        result[owner] = {
            "total_deals": data["deals"],
            "total_pipeline_value": round(data["value"]),
            "won": data["won"],
            "open": data["open"],
            "dead": data["dead"],
            "win_rate_pct": win_rate,
        }

    return {"result": result, "caveats": caveats, "trace": trace}
