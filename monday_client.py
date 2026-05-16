"""
monday_client.py
All Monday.com API interactions. Every call is LIVE — no caching.
"""

import os
import requests
from typing import Optional
import time

MONDAY_API_URL = "https://api.monday.com/v2"


def get_headers():
    token = os.getenv("MONDAY_API_TOKEN")
    if not token:
        raise ValueError("MONDAY_API_TOKEN environment variable not set.")
    return {
        "Authorization": token,
        "Content-Type": "application/json",
        "API-Version": "2024-01",
    }


def run_query(query: str, variables: dict = None) -> dict:
    """Execute a raw GraphQL query against Monday.com API."""
    payload = {"query": query}
    if variables:
        payload["variables"] = variables

    start = time.time()
    resp = requests.post(
        MONDAY_API_URL,
        json=payload,
        headers=get_headers(),
        timeout=30,
    )
    elapsed = round((time.time() - start) * 1000)

    resp.raise_for_status()
    data = resp.json()

    if "errors" in data:
        raise RuntimeError(f"Monday.com API error: {data['errors']}")

    return {"data": data.get("data", {}), "latency_ms": elapsed}


# ─────────────────────────────────────────────
# Board-level helpers
# ─────────────────────────────────────────────

def get_all_boards() -> dict:
    """List all boards in the workspace."""
    query = """
    query {
      boards(limit: 50) {
        id
        name
        items_count
      }
    }
    """
    return run_query(query)


def get_board_columns(board_id: str) -> dict:
    """Get column definitions for a board."""
    query = """
    query ($boardId: ID!) {
      boards(ids: [$boardId]) {
        name
        columns {
          id
          title
          type
        }
      }
    }
    """
    return run_query(query, {"boardId": board_id})


# ─────────────────────────────────────────────
# Item fetching
# ─────────────────────────────────────────────

def get_board_items(board_id: str, limit: int = 500) -> dict:
    """
    Fetch all items from a board with their column values.
    Uses cursor-based pagination to get everything.
    """
    query = """
    query ($boardId: ID!, $limit: Int!, $cursor: String) {
      boards(ids: [$boardId]) {
        name
        items_page(limit: $limit, cursor: $cursor) {
          cursor
          items {
            id
            name
            column_values {
              id
              text
              value
            }
          }
        }
      }
    }
    """
    all_items = []
    cursor = None
    board_name = None
    total_latency = 0

    while True:
        vars_ = {"boardId": board_id, "limit": min(limit, 500)}
        if cursor:
            vars_["cursor"] = cursor

        result = run_query(query, vars_)
        total_latency += result["latency_ms"]

        board_data = result["data"]["boards"][0]
        board_name = board_data["name"]
        page = board_data["items_page"]
        all_items.extend(page["items"])

        cursor = page.get("cursor")
        if not cursor or len(page["items"]) == 0:
            break

    return {
        "data": {"board_name": board_name, "items": all_items, "total": len(all_items)},
        "latency_ms": total_latency,
    }


def search_items_by_column(board_id: str, column_id: str, value: str) -> dict:
    """Search items in a board by a specific column value."""
    query = """
    query ($boardId: ID!, $columnId: String!, $value: String!) {
      items_page_by_column_values(
        board_id: $boardId,
        limit: 200,
        columns: [{ column_id: $columnId, column_values: [$value] }]
      ) {
        items {
          id
          name
          column_values {
            id
            text
            value
          }
        }
      }
    }
    """
    return run_query(query, {
        "boardId": board_id,
        "columnId": column_id,
        "value": value,
    })


# ─────────────────────────────────────────────
# Parsed / normalized helpers
# ─────────────────────────────────────────────

def items_to_dicts(items: list, columns_map: dict) -> list:
    """
    Convert raw Monday items into clean Python dicts.
    columns_map: { column_id -> column_title }
    """
    result = []
    for item in items:
        row = {"_name": item["name"], "_id": item["id"]}
        for cv in item.get("column_values", []):
            col_title = columns_map.get(cv["id"], cv["id"])
            row[col_title] = cv.get("text") or ""
        result.append(row)
    return result


def get_board_as_records(board_id: str) -> dict:
    """
    High-level: fetch a board and return clean list of record dicts.
    This is what the agent tools call.
    """
    # First get column schema
    cols_result = get_board_columns(board_id)
    cols = cols_result["data"]["boards"][0]["columns"]
    columns_map = {c["id"]: c["title"] for c in cols}

    # Then get items
    items_result = get_board_items(board_id)
    items = items_result["data"]["items"]
    records = items_to_dicts(items, columns_map)

    return {
        "records": records,
        "board_name": items_result["data"]["board_name"],
        "total": items_result["data"]["total"],
        "latency_ms": cols_result["latency_ms"] + items_result["latency_ms"],
    }
