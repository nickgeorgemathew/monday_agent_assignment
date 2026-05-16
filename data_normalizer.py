"""
data_normalizer.py
Handles all data quality issues in the Skylark Drones datasets.
Returns cleaned records + a list of caveats to surface to the user.
"""

import re
from typing import Any


# ─────────────────────────────────────────────
# Sector normalization map
# ─────────────────────────────────────────────

SECTOR_ALIASES = {
    "renewables": "Renewables",
    "renewable": "Renewables",
    "solar": "Renewables",
    "wind": "Renewables",
    "mining": "Mining",
    "mine": "Mining",
    "construction": "Construction",
    "infra": "Construction",
    "infrastructure": "Construction",
    "railways": "Railways",
    "railway": "Railways",
    "rail": "Railways",
    "aviation": "Aviation",
    "airports": "Aviation",
    "powerline": "Powerline",
    "power line": "Powerline",
    "power": "Powerline",
    "manufacturing": "Manufacturing",
    "security": "Security and Surveillance",
    "surveillance": "Security and Surveillance",
    "security and surveillance": "Security and Surveillance",
    "dsp": "DSP",
    "tender": "Tender",
    "others": "Others",
    "other": "Others",
    "": "Unknown",
}

DEAL_STAGE_ORDER = [
    "A. Lead Generated",
    "B. Sales Qualified Leads",
    "C. Demo Done",
    "D. Feasibility",
    "E. Proposal/Commercials Sent",
    "F. Negotiations",
    "G. Project Won",
    "H. Work Order Received",
    "I. POC",
    "J. Invoice sent",
    "K. Amount Accrued",
    "L. Project Lost",
    "M. Projects On Hold",
    "N. Not relevant at the moment",
    "O. Not Relevant at all",
    "Project Completed",
]

ACTIVE_DEAL_STAGES = {
    "A. Lead Generated",
    "B. Sales Qualified Leads",
    "C. Demo Done",
    "D. Feasibility",
    "E. Proposal/Commercials Sent",
    "F. Negotiations",
    "G. Project Won",
    "H. Work Order Received",
    "I. POC",
}

PROBABILITY_MAP = {
    "high": 0.75,
    "medium": 0.50,
    "low": 0.25,
    "very high": 0.90,
    "very low": 0.10,
    "confirmed": 1.0,
}


# ─────────────────────────────────────────────
# Normalization utilities
# ─────────────────────────────────────────────

def normalize_sector(raw: str) -> str:
    if not raw:
        return "Unknown"
    key = raw.strip().lower()
    return SECTOR_ALIASES.get(key, raw.strip())


def normalize_probability(raw: Any) -> float | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, (int, float)):
        return float(raw) if 0 <= float(raw) <= 1 else float(raw) / 100
    s = str(raw).strip().lower()
    if s in PROBABILITY_MAP:
        return PROBABILITY_MAP[s]
    # Try numeric
    try:
        v = float(s.replace("%", ""))
        return v / 100 if v > 1 else v
    except ValueError:
        return None


def normalize_amount(raw: Any) -> float | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    try:
        cleaned = re.sub(r"[^\d.]", "", str(raw))
        return float(cleaned) if cleaned else None
    except ValueError:
        return None


def normalize_date(raw: str) -> str:
    """Return ISO date string or empty."""
    if not raw:
        return ""
    raw = str(raw).strip()
    if re.match(r"\d{4}-\d{2}-\d{2}", raw):
        return raw[:10]
    return raw


def is_active_deal(stage: str) -> bool:
    return stage in ACTIVE_DEAL_STAGES


# ─────────────────────────────────────────────
# Record-level normalizers
# ─────────────────────────────────────────────

def normalize_deal_record(record: dict) -> tuple[dict, list[str]]:
    """
    Normalize a single deal record.
    Returns (clean_record, list_of_caveats)
    """
    caveats = []
    clean = dict(record)

    # Sector
    raw_sector = clean.get("Sector", "")
    clean["Sector"] = normalize_sector(raw_sector)
    if raw_sector and clean["Sector"] == "Unknown":
        caveats.append(f"Unrecognized sector '{raw_sector}' mapped to Unknown")

    # Probability
    raw_prob = clean.get("Closure Probability", "")
    clean["_prob_numeric"] = normalize_probability(raw_prob)
    if raw_prob and clean["_prob_numeric"] is None:
        caveats.append(f"Could not parse probability '{raw_prob}'")

    # Value
    raw_val = clean.get("Deal Value", "") or clean.get("Masked Deal value", "")
    clean["_value_numeric"] = normalize_amount(raw_val)
    if raw_val and clean["_value_numeric"] is None:
        caveats.append(f"Could not parse deal value '{raw_val}'")

    # Stage activity flag
    stage = clean.get("Deal Stage", "")
    clean["_is_active"] = is_active_deal(stage)

    # Close date
    clean["_close_date"] = normalize_date(
        clean.get("Close Date") or clean.get("Tentative Close Date", "")
    )
    if not clean["_close_date"]:
        caveats.append(f"Deal '{clean.get('_name', '')}' has no close date")

    return clean, caveats


def normalize_work_order_record(record: dict) -> tuple[dict, list[str]]:
    """
    Normalize a single work order record.
    Returns (clean_record, list_of_caveats)
    """
    caveats = []
    clean = dict(record)

    # Sector
    raw_sector = clean.get("Sector", "")
    clean["Sector"] = normalize_sector(raw_sector)

    # Amounts
    for field in ["Amount Excl GST", "Amount Incl GST", "Billed Excl GST",
                  "Collected Amount", "Amount Receivable"]:
        raw = clean.get(field, "")
        clean[f"_{field.lower().replace(' ', '_')}_numeric"] = normalize_amount(raw)

    # Dates
    for field in ["Data Delivery Date", "Date of PO/LOI", "Probable Start Date", "Probable End Date"]:
        clean[f"_{field.lower().replace('/', '_').replace(' ', '_')}"] = normalize_date(clean.get(field, ""))

    # Missing execution status
    if not clean.get("Execution Status"):
        clean["Execution Status"] = "Unknown"
        caveats.append(f"Work order '{clean.get('_name', '')}' has no execution status")

    return clean, caveats


# ─────────────────────────────────────────────
# Batch normalizer
# ─────────────────────────────────────────────

def normalize_records(records: list, record_type: str) -> dict:
    """
    Normalize a full list of records.
    record_type: 'deal' or 'work_order'
    Returns { records: [...], caveats: [...], stats: {...} }
    """
    cleaned = []
    all_caveats = []
    null_count = 0

    normalizer = normalize_deal_record if record_type == "deal" else normalize_work_order_record

    for rec in records:
        c, caveats = normalizer(rec)
        cleaned.append(c)
        all_caveats.extend(caveats)
        if any(v == "" or v is None for v in rec.values()):
            null_count += 1

    unique_caveats = list(dict.fromkeys(all_caveats))  # deduplicate, preserve order

    return {
        "records": cleaned,
        "caveats": unique_caveats[:10],  # cap at 10 to avoid overwhelming output
        "stats": {
            "total": len(cleaned),
            "records_with_nulls": null_count,
            "caveat_count": len(all_caveats),
        },
    }
