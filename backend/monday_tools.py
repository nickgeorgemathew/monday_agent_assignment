"""
Monday.com API integration — all calls are LIVE at query time, no caching.
Uses Monday.com v2 GraphQL API.
"""
import os
import httpx
import json
from datetime import datetime
from typing import Any

MONDAY_API_URL = "https://api.monday.com/v2"

def get_headers() -> dict:
    token = os.environ.get("MONDAY_API_TOKEN", "")
    if not token:
        raise ValueError("MONDAY_API_TOKEN not set in environment")
    return {
        "Authorization": token,
        "Content-Type": "application/json",
        "API-Version": "2024-01",
    }

def run_query(query: str, variables: dict = None) -> dict:
    """Execute a raw GraphQL query against Monday.com and return the response."""
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    resp = httpx.post(MONDAY_API_URL, headers=get_headers(), json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if "errors" in data:
        raise RuntimeError(f"Monday API error: {data['errors']}")
    return data["data"]

def get_board_schema(board_id: str) -> dict:
    """Returns column definitions for a board."""
    query = """
    query ($boardId: [ID!]!) {
      boards(ids: $boardId) {
        id
        name
        columns { id title type }
      }
    }
    """
    data = run_query(query, {"boardId": [board_id]})
    board = data["boards"][0]
    return {"board_id": board["id"], "board_name": board["name"], "columns": board["columns"]}

def get_board_items(board_id: str, limit: int = 500) -> list:
    """Fetches all items from a board using cursor-based pagination. Live call — never cached."""
    query = """
    query ($boardId: ID!, $limit: Int!, $cursor: String) {
      boards(ids: [$boardId]) {
        items_page(limit: $limit, cursor: $cursor) {
          cursor
          items {
            id
            name
            column_values { id title text value }
          }
        }
      }
    }
    """
    all_items = []
    cursor = None
    while True:
        variables = {"boardId": board_id, "limit": limit}
        if cursor:
            variables["cursor"] = cursor
        data = run_query(query, variables)
        page = data["boards"][0]["items_page"]
        items = page["items"]
        for item in items:
            row = {"id": item["id"], "name": item["name"]}
            for cv in item["column_values"]:
                row[cv["title"]] = cv["text"] or ""
            all_items.append(row)
        cursor = page.get("cursor")
        if not cursor or len(items) < limit:
            break
    return all_items

def search_items_by_value(board_id: str, column_id: str, value: str) -> list:
    """Searches items where a specific column matches a given value."""
    query = """
    query ($boardId: ID!, $columnId: String!, $value: String!) {
      boards(ids: [$boardId]) {
        items_page(
          limit: 500,
          query_params: { rules: [{column_id: $columnId, compare_value: [$value]}] }
        ) {
          items {
            id
            name
            column_values { id title text }
          }
        }
      }
    }
    """
    data = run_query(query, {"boardId": board_id, "columnId": column_id, "value": value})
    items = data["boards"][0]["items_page"]["items"]
    result = []
    for item in items:
        row = {"id": item["id"], "name": item["name"]}
        for cv in item["column_values"]:
            row[cv["title"]] = cv["text"] or ""
        result.append(row)
    return result

# ── Data normalization helpers ────────────────────────────
PROBABILITY_MAP = {"high": 0.8, "medium": 0.5, "low": 0.2}
SECTOR_ALIASES = {
    "powerlines": "Powerline", "power line": "Powerline", "power lines": "Powerline",
    "mine": "Mining", "mines": "Mining",
    "solar": "Renewables", "wind": "Renewables",
    "railway": "Railways", "rail": "Railways",
}
STAGE_ORDER = {
    "A. Lead Generated": 1, "B. Sales Qualified Leads": 2, "C. Demo Done": 3,
    "D. Feasibility": 4, "E. Proposal/Commercials Sent": 5, "F. Negotiations": 6,
    "G. Project Won": 7, "H. Work Order Received": 8, "I. POC": 9,
    "J. Invoice sent": 10, "K. Amount Accrued": 11, "L. Project Lost": -1,
    "M. Projects On Hold": 0, "N. Not relevant at the moment": 0,
    "O. Not Relevant at all": 0, "Project Completed": 12,
}

def normalize_sector(raw: str) -> str:
    if not raw: return "Unknown"
    return SECTOR_ALIASES.get(raw.strip().lower(), raw.strip())

def normalize_probability(raw: str):
    if not raw: return None
    return PROBABILITY_MAP.get(raw.strip().lower())

def parse_amount(raw: str):
    if not raw: return None
    try:
        return float(str(raw).replace(",", "").replace("₹", "").strip())
    except (ValueError, TypeError):
        return None

def normalize_date(raw: str):
    if not raw: return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(raw.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return raw

def enrich_items(items: list, board_type: str) -> dict:
    """Normalizes and enriches a list of board items. Returns enriched items + quality notes."""
    enriched = []
    quality_notes = {"missing_sector": 0, "missing_amount": 0, "missing_date": 0,
                     "missing_probability": 0, "total_rows": len(items)}
    for item in items:
        row = dict(item)
        if board_type == "deals":
            sector_raw = row.get("Sector/service", "")
            row["_sector_normalized"] = normalize_sector(sector_raw)
            if not sector_raw: quality_notes["missing_sector"] += 1
            prob_raw = row.get("Closure Probability", "")
            row["_probability_score"] = normalize_probability(prob_raw)
            if not prob_raw: quality_notes["missing_probability"] += 1
            amt = parse_amount(row.get("Masked Deal value", ""))
            row["_amount_numeric"] = amt
            if amt is None: quality_notes["missing_amount"] += 1
            row["_stage_rank"] = STAGE_ORDER.get(row.get("Deal Stage", ""), None)
            close_date = normalize_date(row.get("Close Date (A)", ""))
            tentative = normalize_date(row.get("Tentative Close Date", ""))
            row["_close_date_resolved"] = close_date or tentative
            if not close_date and not tentative: quality_notes["missing_date"] += 1
        elif board_type == "work_orders":
            sector_raw = row.get("Sector", "")
            row["_sector_normalized"] = normalize_sector(sector_raw)
            if not sector_raw: quality_notes["missing_sector"] += 1
            for field in ["Amount in Rupees (Excl of GST) (Masked)",
                          "Billed Value in Rupees (Excl of GST.) (Masked)",
                          "Amount Receivable (Masked)"]:
                val = parse_amount(row.get(field, ""))
                row[f"_num_{field.split('(')[0].strip()}"] = val
                if val is None and "Excl of GST) (Masked)" in field:
                    quality_notes["missing_amount"] += 1
        enriched.append(row)
    return {"items": enriched, "quality_notes": quality_notes}
