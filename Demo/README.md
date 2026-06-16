# CDGC DQRO Score Upload Demo

End-to-end demo for Informatica Cloud Data Governance & Catalog (CDGC) that creates a **Data Quality Rule Occurrence (DQRO)** asset and uploads data quality scores via the April 2026 API.

---

## What the demo does

| Step | Action |
|------|--------|
| 1 | Authenticates to Informatica Cloud (session ID + JWT token) |
| 2 | Searches the catalog for a `firstname` Column asset |
| 3 | Creates a DQRO asset with measuring method = **Technical Script** |
| 4 | Links the `firstname` column as the DQRO's **Primary Data Element** |
| 5 | Uploads DQ scores from `dq_scores_sample.csv` using the CSV import endpoint |
| 6 | Polls the import job until it reaches a terminal state |
| 7 | Retrieves and prints the uploaded score runs |

---

## Files

| File | Purpose |
|------|---------|
| `demo.py` | Main end-to-end demo script |
| `dq_scores_sample.csv` | Dummy DQ score data (3 weekly runs) |
| `README.md` | This file |

Parent directory:

| File | Purpose |
|------|---------|
| `CDGCAPIClient.py` | Base API client (auth, search, export, asset CRUD) |
| `CDGCAPIClientV2.py` | Extended client — inherits base; adds DQRO, import, relationships, DQ scores |

---

## Prerequisites

```bash
pip install requests
```

> `CDGCAPIClient.py` imports `dotenv`, `pandas`, `pyodbc`, and `zipfile` for other methods not used by this demo. Only `requests` is needed to run `demo.py`.

---

## Running the demo

```bash
cd Demo
python demo.py
```

Credentials are set directly in `demo.py` (lines 30-33). To use environment variables instead, load them from the `env` file in the project root:

```python
from dotenv import load_dotenv
load_dotenv('../env')
BASE_URL  = os.getenv('BASE_URL')
# ...
```

---

## Sample CSV format (`dq_scores_sample.csv`)

The CSV must match the column names exactly:

```
Reference ID,Score,Total Rows,Failed Rows,Scanned Time,Exception File Path
DQRO-FIRSTNAME-001,92,10000,800,2026-06-01T08:00:00.000Z,/exceptions/firstname_check_2026-06-01.csv
```

| Column | Description |
|--------|-------------|
| `Reference ID` | `core.externalId` of the target DQRO |
| `Score` | Numeric 0–100 (no `%` sign) |
| `Total Rows` | Total rows processed |
| `Failed Rows` | Rows that failed the rule |
| `Scanned Time` | ISO 8601 timestamp `YYYY-MM-ddTHH:mm:ss.SSSZ` |
| `Exception File Path` | Full path to the exception records file |

`demo.py` automatically overwrites the `Reference ID` column at runtime with the reference ID of the DQRO it just created.

---

## Key API endpoints used

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/identity-service/api/v1/Login` | POST | Obtain session ID |
| `/identity-service/api/v1/jwt/Token` | POST | Exchange session for JWT |
| `/data360/search/v1/assets` | POST | Search for Column asset |
| `/data360/content/v1/assets` | POST | Create DQRO asset |
| `/data360/content/v1/assets/{id}` | PATCH | Add Primary Data Element relationship |
| `/ccgf-data-profiling-and-quality/v1/rule-occurrences/runs` | POST | Upload DQ scores (CSV) |
| `/data360/observable/v1/jobs/{jobId}` | GET | Monitor import job |
| `/data360/data-quality/v1/rule-occurrences/{id}/runs` | GET | Retrieve score history |

---

## DQRO asset model

- **Class type**: `com.infa.ccgf.models.governance.RuleInstance`
- **Measuring method attribute**: `com.infa.ccgf.models.governance.measuringMethod`
- **Primary Data Element relationship**: `com.infa.ccgf.models.governance.primaryDataElement`
- **Column class type** (for search): `com.infa.odin.models.relational.Column`

---

## Notes

- DQ score updates can take **up to 1 hour** to reflect in the CDGC UI after a successful import.
- The CSV import endpoint replaces the deprecated PATCH endpoint (`/ccgf-ruleautomation/api/v1/dataQuality/publishScore`) which is supported until July 2026. `CDGCAPIClientV2` keeps both methods; use `import_dq_scores_from_csv()` for new work.
- Maximum 5 concurrent import jobs may be active at a time.
