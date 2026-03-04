# PRGI Title Validator

**Press Registrar General of India — Title Uniqueness & Compliance Verification System**

A full-stack web application that verifies whether a proposed publication title can be registered under the Press Registration of Periodicals Act. It checks against a database of ~70,000 registered titles using a 5-priority semantic match system, compliance rules, and phonetic/fuzzy algorithms.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Project Structure](#project-structure)
3. [How FastAPI is Used](#how-fastapi-is-used)
4. [Pydantic Models & Schemas](#pydantic-models--schemas)
5. [Database Design](#database-design)
6. [Services & Matching Engine](#services--matching-engine)
7. [The 5-Priority Match System](#the-5-priority-match-system)
8. [Batch Upload & Admin Workflow](#batch-upload--admin-workflow)
9. [API Reference](#api-reference)
10. [Setup & Running](#setup--running)

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────┐
│                   Browser (index.html)                   │
│           Vanilla JS · Chart.js · Lucide Icons           │
└────────────────────────┬─────────────────────────────────┘
                         │ HTTP (fetch)
                         ▼
┌─────────────────────────────────────────────────────────┐
│               FastAPI  (backend/main.py)                │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │  Verify API  │  │  Batch API   │  │   Admin API   │  │
│  └──────┬───────┘  └──────┬───────┘  └──────┬────────┘  │
│         │                 │                 │           │
│         ▼                 ▼                 ▼           │
│  ┌─────────────────────────────────────────────────┐    │
│  │          similarity_engine.py  (core)           │    │
│  │  ┌───────────┐ ┌──────────┐ ┌───────────────┐   │    │
│  │  │  fuzzy_   │ │phonetic_ │ │  semantic_    │   │    │
│  │  │ checker   │ │ checker  │ │   checker     │   │    │
│  │  └───────────┘ └──────────┘ └───────────────┘   │    │
│  │           rules_checker.py                      │    │
│  └─────────────────────────────────────────────────┘    │
│         │                                               │
│         ▼                                               │
│  ┌───────────────────┐   ┌───────────────────────────┐  │
│  │  prgi_titles.db   │   │        temp.db            │  │
│  │  (~70k titles)    │   │  (batch review queue)     │  │
│  └───────────────────┘   └───────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

The backend is a **stateless FastAPI service**. On startup, all registered titles are loaded into two in-memory data structures (`list` + `set`) for fast lookup. The frontend is a single HTML file — no build step required.

---

## Project Structure

```
prgi-title-validator/
│
├── backend/
│   ├── main.py                  # FastAPI app, all API endpoints
│   ├── database.py              # Main DB (prgi_titles.db) — CRUD + in-memory cache
│   ├── temp_database.py         # Temp DB (temp.db) — batch/admin review queue
│   ├── load_titles.py           # One-time utility: imports Excel files into the DB
│   ├── requirements.txt
│   │
│   ├── models/
│   │   └── schemas.py           # Pydantic request/response models
│   │
│   ├── services/
│   │   ├── similarity_engine.py # Orchestrates all checks → produces final verdict
│   │   ├── rules_checker.py     # Compliance rules (disallowed words, prefix, combo)
│   │   ├── fuzzy_checker.py     # RapidFuzz string similarity
│   │   ├── phonetic_checker.py  # Soundex + NYSIIS phonetic matching
│   │   └── semantic_checker.py  # Cross-language translation + theme cluster checks
│   │
│   └── data/
│       ├── prgi_titles.db       # SQLite — main title registry (~70,000 titles)
│       ├── temp.db              # SQLite — pending/approved batch submissions
│       ├── disallowed_words.json
│       └── test_titles.txt / test_batch.csv / TestExcel*.xls
│
└── frontend/
    └── index.html               # Complete SPA (HTML + CSS + JS in one file)
```

---

## How FastAPI is Used

### App Initialization

```python
# backend/main.py

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()       # Creates schema + loads all titles into memory
    init_temp_db()  # Creates temp tables + default admin settings
    yield

app = FastAPI(
    title="PRGI Title Validator",
    description="Unified Editorial Title Verification System",
    lifespan=lifespan
)
```

FastAPI's **lifespan context manager** runs startup logic before the first request. This is where ~70,000 titles are read from SQLite and stored in global in-memory caches (`TITLES_CACHE_LIST` and `TITLES_CACHE_SET`), making every subsequent verification fast without hitting the database.

### CORS

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

Allows the frontend (served from any origin, including `file://`) to call the API. Restrict to a specific domain for production.

### Endpoint Patterns

FastAPI is used for four distinct input patterns:

| Pattern | Example Endpoint |
|---------|-----------------|
| JSON request body | `POST /verify-title` — `TitleRequest` Pydantic model |
| Query parameters | `GET /search?q=&state=&limit=` |
| Path parameters | `DELETE /disallowed-words/{word}` |
| File upload (multipart) | `POST /batch-upload` — `UploadFile` |

### Admin Authentication

A `_require_admin(request)` guard function checks the `Authorization` header on every admin endpoint:

```python
def _require_admin(request: Request):
    auth = request.headers.get('Authorization', '')
    if auth != f"Bearer {ADMIN_TOKEN}":
        raise HTTPException(401, "Unauthorized")

@app.get("/api/admin/pending")
async def admin_pending(request: Request):
    _require_admin(request)
    return get_all_temp()
```

The token (`prgi_admin_token_2024`) is a fixed constant in `temp_database.py`, verified against `Authorization: Bearer <token>`.

---

## Pydantic Models & Schemas

All request/response shapes are defined in `backend/models/schemas.py` using **Pydantic v2**.

```python
class TitleRequest(BaseModel):
    title: str                          # Proposed publication title

class SimilarityResult(BaseModel):
    existing_title: str                 # Matching title found in the registry
    match_percentage: float             # 0–100 similarity score
    match_type: str                     # "exact" | "fuzzy" | "phonetic" |
                                        # "semantic_cross_language" | "semantic_conceptual"

class PriorityGroup(BaseModel):
    priority: int                       # 1 (most critical) → 5 (informational)
    label: str                          # Human-readable group label
    matches: List[SimilarityResult]

class TitleResponse(BaseModel):
    title: str
    approval_probability: float         # 0–100 numeric score
    verdict: str                        # "APPROVED" or "REJECTED"
    rejection_reasons: List[str]        # Plain-text reasons for rejection
    priority_matches: List[PriorityGroup]
    checks: Dict[str, Any]             # Raw scores per check type

class WordRequest(BaseModel):
    word: str                           # Word to add to the disallowed list
```

`TitleResponse` is used as the `response_model` on the verify endpoint — FastAPI auto-validates the output, strips undeclared fields, and generates the OpenAPI schema from it.

---

## Database Design

### Main Database — `prgi_titles.db`

Managed by `backend/database.py`. Stores the official PRGI title registry.

```sql
CREATE TABLE titles (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    title               TEXT NOT NULL,
    registration_number TEXT,
    registration_date   TEXT,
    language            TEXT,
    periodicity         TEXT,       -- Daily / Weekly / Monthly / etc.
    publisher           TEXT,
    owner               TEXT,
    pub_state           TEXT,
    pub_district        TEXT
);

CREATE INDEX idx_title ON titles(title);

CREATE TABLE disallowed_words (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    word TEXT UNIQUE NOT NULL
);
```

**In-Memory Cache (loaded at startup):**

```python
TITLES_CACHE_LIST = []     # Ordered list — used by fuzzy/phonetic checkers
TITLES_CACHE_SET  = set()  # Hash set   — O(1) exact-match and periodicity lookups
```

All ~70,000 titles are loaded once. Every verification runs entirely in memory. The database is only queried for search, stats, and admin push operations.

### Temp Database — `temp.db`

Managed by `backend/temp_database.py`. Acts as a **review queue** for batch submissions.

```sql
CREATE TABLE temp_titles (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    title                TEXT NOT NULL,
    verdict              TEXT,                -- APPROVED / REJECTED
    approval_probability REAL,
    rejection_reasons    TEXT,               -- JSON-encoded list
    batch_id             TEXT,               -- Groups titles from the same upload
    submitted_at         TEXT,               -- ISO datetime
    language             TEXT DEFAULT '',
    state                TEXT DEFAULT '',
    status               TEXT DEFAULT 'pending',  -- pending | approved | rejected | pushed
    top_match            TEXT DEFAULT '',
    top_match_score      REAL DEFAULT 0
);

CREATE TABLE admin_settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);
-- Defaults: acceptance_threshold = '50'
--           admin_password       = 'prgi@2024'
```

A title moves through four statuses:

```
batch upload → pending → approved / rejected → pushed (into prgi_titles.db)
```

---

## Services & Matching Engine

### `similarity_engine.py` — Orchestrator

`verify_title()` is the single entry point. It calls every checker, aggregates results, and computes the final verdict.

```
verify_title(title)
    │
    ├── check_rules_detailed()        → hard violations + prefix warnings
    ├── check_fuzzy()                 → typographical similarity (RapidFuzz)
    ├── check_phonetic()              → sound-alike detection (Soundex/NYSIIS)
    ├── check_cross_language_similarity() → translated title matching
    └── check_conceptual_theme()      → Indian-language theme clusters
```

**Probability Calculation:**

```
approval_probability = 100 − highest_match_score_across_all_checks
                     − 10  (penalty if any prefix/suffix warning triggered)

verdict = "REJECTED"  if  hard_violations > 0
                      OR  approval_probability < 50
        = "APPROVED"  otherwise
```

---

### `rules_checker.py` — Compliance Rules

Hard constraints that cause rejection regardless of similarity scores.

**1. Disallowed Words** (from `disallowed_words.json`)
```
Police, Crime, Corruption, CBI, CID, Army, Military, Government, India Gate
```
Any exact word match → hard rejection.

**2. Restricted Prefixes / Suffixes**
```
THE, INDIA, SAMACHAR, NEWS, DAILY, WEEKLY, MONTHLY, TIMES, PRESS,
JAN, NAV, AMAR, DAINIK, RASHTRIYA, PRABHAT, UDAYA, JANATA, LOKMAT, DIVYA
```
Title starts/ends with these → warning, raises rejection probability.

**3. Periodicity Violation**
If the title contains a periodicity word (`DAILY`, `WEEKLY`, `MONTHLY`, `DAINIK`, `SAPTAHIK`, `MASIK`, etc.) and the **core title** (title minus that word) already exists in the registry via O(1) set lookup → hard rejection.

Example: `"DAILY DAWN"` is rejected if `"DAWN"` is already registered.

**4. Combination Detection**
For titles with 3+ words: checks if the title is a concatenation of 2 or more already-registered titles, after filtering stop words (`THE`, `AND`, `OF`, `FOR`, `IN`, `TO`, `A`, `AN`).

---

### `fuzzy_checker.py` — Typographical Similarity

Uses **RapidFuzz** `fuzz.ratio` for character-level string similarity.

```python
results = process.extract(
    query=title,
    choices=existing_titles,
    scorer=fuzz.ratio,
    score_cutoff=60.0,
    limit=5
)
# Returns top-5 matches above 60% — type="fuzzy"
```

---

### `phonetic_checker.py` — Sound-alike Detection

Uses **Jellyfish** to compute Soundex and NYSIIS codes, then measures set overlap.

```python
soundex_codes = {jellyfish.soundex(w) for w in words}
nysiis_codes  = {jellyfish.nysiis(w)  for w in words}

# Score = (intersection / max_union) × 100
# Takes the best of Soundex vs NYSIIS
# Threshold: > 30.0 → type="phonetic"
```

Catches transliteration variants like `"PRABHAT"` vs `"PRABHATH"`.

---

### `semantic_checker.py` — Cross-Language & Theme Matching

**Cross-Language Translation:**

```python
from deep_translator import GoogleTranslator

translated = GoogleTranslator(source='auto', target='en').translate(title)
matches = process.extract(translated, existing_titles,
                          scorer=fuzz.token_sort_ratio,
                          score_cutoff=76.0, limit=5)
# type="cross-language"
```

Catches Hindi/regional titles whose English meaning matches an already-registered English title.

**Conceptual Theme Clusters:**

```python
THEME_CLUSTERS = {
    "morning": ["PRATAH", "PRABHAT", "BHOR", "USHAKAL", "SUBAH"],
    "evening": ["SAYAM", "SHAM"],
    "nation":  ["RASHTRA", "DESH"],
}
# If any cluster word is found in title → type="semantic_conceptual"
```

---

## The 5-Priority Match System

Matches are ranked into five groups, most critical first:

| Priority | Label | Trigger | Effect |
|----------|-------|---------|--------|
| **1** | Exact Match | Identical string in registry (O(1) set lookup) | Hard reject |
| **2** | High Similarity | Fuzzy or phonetic score ≥ 80% | Reject |
| **3** | Combination | Title = two or more existing titles joined | Reject |
| **4** | Semantic Cross-Language | Translated title matches ≥ 76% | Reject |
| **5** | Semantic Conceptual | Title word belongs to a theme cluster | Warning |

The frontend renders each group separately with colour-coded type tags and a percentage bar per match.

---

## Batch Upload & Admin Workflow

### Upload Flow

```
User uploads CSV / TXT / XLS / XLSX (up to 200 rows)
        │
        ▼
POST /api/batch-upload
  ├── Parse file with pandas
  ├── Extract: title, state, language columns (auto-detected)
  ├── For each title → verify_title()
  ├── Store all results in temp.db (status = 'pending')
  ├── Compute aggregate stats:
  │     violation_types, prefix_distribution,
  │     state_rejections, word_ratio,
  │     confidence_distribution (10 buckets × 10%),
  │     language_conflicts
  └── Return stats + batch_id to frontend → renders 6 charts
```

### 6 Analytics Charts

| Chart | Type | Data |
|-------|------|------|
| Rule Violation Distribution | Horizontal bar | `violation_types` |
| Prefix Usage Distribution | Leaderboard | `prefix_distribution` |
| Statewise Rejection Rate | Doughnut | `state_rejections` |
| Unique vs Duplicate Word Ratio | Pie | `word_ratio` |
| Rejection Confidence Levels | Gradient bar | `confidence_distribution` (10 buckets) |
| Language-based Similarity Conflicts | Bar | `language_conflicts` |

### Admin Review Flow

```
Click Admin → Login modal (admin / prgi@2024)
        │
        ▼
GET /api/admin/pending  →  Excel-style review table
        │
        ├── Select rows → POST /api/admin/approve
        │                 POST /api/admin/reject
        │
        └── Select approved → POST /api/admin/push-to-main
                              (INSERTs into prgi_titles.db,
                               marks temp rows as 'pushed')
```

Admin can also adjust the **Acceptance Threshold** slider (0–100%) and change the admin password, both saved to `admin_settings` in `temp.db`.

---

## API Reference

### Public Endpoints

```
POST   /api/verify-title
       Body:    { "title": "string" }
       Returns: TitleResponse

GET    /api/search
       Params:  q, registration_number, owner, state, district, language, limit
       Returns: Array of title records

GET    /api/stats
       Returns: { total_titles, total_languages, total_states, total_disallowed_words }

GET    /api/recent
       Returns: Last 10 verified titles with verdict + probability

GET    /api/disallowed-words
       Returns: Array of strings

POST   /api/disallowed-words
       Body:    { "word": "string" }

DELETE /api/disallowed-words/{word}

POST   /api/batch-upload
       Body:    multipart/form-data, field name "file"
       Returns: Batch stats dict + batch_id
```

### Admin Endpoints

All require header: `Authorization: Bearer prgi_admin_token_2024`

```
POST   /api/admin/login
       Body:    { "username": "admin", "password": "prgi@2024" }
       Returns: { "token": "prgi_admin_token_2024" }

GET    /api/admin/pending
       Returns: All rows from temp_titles table

POST   /api/admin/approve
       Body:    { "ids": [1, 2, 3] }

POST   /api/admin/reject
       Body:    { "ids": [1, 2, 3] }

POST   /api/admin/push-to-main
       Body:    { "ids": [1, 2, 3] }
       Action:  INSERT approved temp titles → prgi_titles.db

GET    /api/admin/settings
       Returns: { acceptance_threshold, admin_password }

POST   /api/admin/settings
       Body:    { "acceptance_threshold": "70" }
```

---

## Setup & Running

### Install

### Install

```bash
cd prgi-title-validator
pip install -r backend/requirements.txt
```

### Run

```bash
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

Serve the frontend with a static server on port 5500:

```bash
cd frontend
python -m http.server 5500
```

Open in browser:
- Main page: `http://localhost:5500/index.html`
- Batch upload: `http://localhost:5500/batch.html`
- Admin panel: `http://localhost:5500/admin.html`
- Admin review: `http://localhost:5500/admin-review.html`

### Startup Output

```
Loaded 70,936 titles from prgi_titles.db
After deduplication: 70,936 unique titles ready
Phonetic cache ready for 70,936 titles
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### Auto-generated API Docs

- Swagger UI: `http://localhost:8000/docs`
- ReDoc:      `http://localhost:8000/redoc`

---

## Key Design Decisions

| Decision | Reason |
|----------|--------|
| In-memory title cache | Avoids a DB query for every verification; O(1) exact match |
| Precomputed phonetic cache | Eliminates re-running jellyfish on all 70k titles per request; built once at startup |
| Parallel batch processing | `ThreadPoolExecutor` with 12 workers; I/O-bound translate calls and C-extension work run concurrently |
| Skip translate for ASCII | English-only titles bypass the Google Translate HTTP call entirely |
| Two-database architecture | Keeps the official registry clean; batch submissions go through admin review before being promoted |
| Multiple frontend pages | Separate HTML files for verify, batch, admin, and review workflows |
| Pandas for file parsing | Handles CSV, XLS, XLSX uniformly in a few lines |
| RapidFuzz over difflib | 10–100× faster when scanning 70,000 candidate strings per request |
| Pydantic v2 models | Auto-validation, serialisation, and OpenAPI schema generation with no extra code |
