#  Monday.com BI Agent

A conversational Business Intelligence agent that answers founder-level queries by making **live API calls** to Monday.com boards containing Deals and Work Orders data.

## Live Demo
[](https://monday-agent.onrender.com)

## Monday.com Boards


---

## Architecture

```
User Query
    │
    ▼
Streamlit UI (app.py)
    │
    ▼
Claude Sonnet Agent (agent.py)
    │  Tool definitions (agent_tools.py)
    │  System prompt with business context
    │
    ▼  Live API calls, no cache
Monday.com GraphQL API (monday_client.py)
    │
    ▼
Data Normalizer (data_normalizer.py)
    │  Sector normalization, null handling, type coercion
    │
    ▼
Structured result + caveats → Claude → Natural language response
```

Key design decisions:
- Every query triggers fresh Monday.com API calls — zero caching
- Tool traces are displayed inline in the UI with latency metrics
- Data quality caveats are surfaced transparently
- Claude manages multi-turn context and calls multiple tools when needed

---

## Setup

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Prepare CSVs for Monday.com import
```bash
mkdir data
cp /path/to/Deal_funnel_Data.xlsx data/
cp /path/to/Work_Order_Tracker_Data.xlsx data/
python scripts/prepare_csv.py
# Produces: data/deals_clean.csv and data/work_orders_clean.csv
```

### 3. Import to Monday.com
1. Create two new boards in Monday.com
2. Import deals_clean.csv → name it "Skylark Deals"
3. Import work_orders_clean.csv → name it "Skylark Work Orders"
4. Note both board IDs from the URL (monday.com/boards/BOARD_ID)

### 4. Get API credentials
- Monday.com token: Account Settings > Developer > API Token v2
- Anthropic key: https://console.anthropic.com

### 5. Configure environment
```bash
cp .env.example .env
# Edit .env with your actual values
```

### 6. Run
```bash
streamlit run app.py
```

---

## Deploying to Render (free tier)

1. Push to GitHub
2. New Web Service on render.com
3. Build command: `pip install -r requirements.txt`
4. Start command: `streamlit run app.py --server.port=$PORT --server.address=0.0.0.0`
5. Add environment variables in Render dashboard

---

## Example Queries

- "How's our overall pipeline looking?"
- "Which sector is performing best this quarter?"
- "What deals are closing in the next 30 days?"
- "Show revenue, billing, and collection status"
- "Any overdue work orders in Mining?"
- "Who is the top performing BD owner?"
- "Renewables pipeline for Q1 2026"

---

## Data Handling

| Issue | Handling |
|---|---|
| Work Order headers on row 2 | prepare_csv.py skips row 1 |
| Text probabilities (High/Medium/Low) | Mapped to 0.75 / 0.50 / 0.25 |
| Sector name variants | Normalized via SECTOR_ALIASES dict |
| Missing close dates | Flagged as caveat, excluded from filters |
| Header rows polluting data | Filtered during normalization |
| Mixed amount formats | Regex-based numeric extraction |
| Empty execution status | Defaulted to "Unknown" with caveat |

---

## File Structure

```
skylark-bi-agent/
├── app.py              Streamlit frontend
├── agent.py            Claude agent + tool-calling loop  
├── agent_tools.py      Tool definitions + executors
├── monday_client.py    Monday.com GraphQL API client
├── data_normalizer.py  Data cleaning + normalization
├── requirements.txt
├── Procfile
├── .env.example
├── scripts/
│   └── prepare_csv.py  One-time CSV prep from Excel
└── README.md
```
