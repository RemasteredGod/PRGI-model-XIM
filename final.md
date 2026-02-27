# PRGI Title Validator — Complete Reference Guide

> Everything you need to know about the system: how it works, what powers it, and how the score is calculated.

---

## Table of Contents

1. [What is this system?](#1-what-is-this-system)
2. [Tech Stack at a Glance](#2-tech-stack-at-a-glance)
3. [How FastAPI is Used](#3-how-fastapi-is-used)
4. [All API Endpoints](#4-all-api-endpoints)
5. [External Libraries & Why Each is Used](#5-external-libraries--why-each-is-used)
6. [The Scoring Formula — Layman's Explanation](#6-the-scoring-formula--laymans-explanation)
7. [The 5-Priority Match System](#7-the-5-priority-match-system)
8. [Database Structure](#8-database-structure)
9. [How a Title Flows Through the System](#9-how-a-title-flows-through-the-system)
10. [Admin Workflow](#10-admin-workflow)
11. [Batch Processing](#11-batch-processing)
12. [Performance Design — Why It's Fast](#12-performance-design--why-its-fast)
13. [Frequently Asked Questions](#13-frequently-asked-questions)

---

## 1. What is this system?

The **Press Registrar General of India (PRGI) Title Validator** is a web-based tool that helps applicants check whether a proposed newspaper or magazine title is unique and eligible for registration.

**The problem it solves:** India has 77,564+ registered publication titles. Manually checking if a new title clashes with an existing one — including phonetically similar names, translated versions, or combinations of existing titles — is impossible at scale. This system automates that check in under a second.

**What it checks:**
- Is the exact title already registered?
- Does it *sound like* an existing title?
- Is it a *combination* of two existing titles?
- Does it mean the same thing in another language?
- Does it contain restricted/disallowed words?
- Does it violate periodicity or prefix/suffix rules?

---

## 2. Tech Stack at a Glance

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Frontend | HTML + CSS + Vanilla JS | Single-page UI, no framework |
| Backend | Python + FastAPI | REST API server |
| Database | SQLite (WAL mode) | Stores 77,564 registered titles |
| Fuzzy Matching | RapidFuzz | Fast character-level similarity |
| Phonetic Matching | Jellyfish | Sound-alike detection (Soundex, NYSIIS) |
| Cross-Language | deep-translator (Google Translate) | Detect same meaning in Hindi/regional languages |
| Data Import | pandas + openpyxl + xlrd | Read CSV/Excel files for bulk imports |
| Validation | Pydantic v2 | Request/response schema validation |
| Server | Uvicorn (ASGI) | Runs the FastAPI app |

---

## 3. How FastAPI is Used

FastAPI is the backbone of the entire backend. Here's exactly how it's set up:

### Application Setup

```
app = FastAPI(title="PRGI Title Validator API")
```

The app is mounted with **CORS middleware** so the frontend (served separately on a different port) can call the API without browser security errors.

### Startup Lifecycle (`lifespan`)

When the server starts, FastAPI's `lifespan` context manager runs:

```
init_db()
  → Creates all 9 database tables if they don't exist
  → Loads all 77,564 titles into RAM (in-memory cache)
  → Pre-computes phonetic codes (Soundex + NYSIIS) for every title
  → Builds 3 reverse indexes (phonetic, word, combination)
  → Loads disallowed words cache
```

This means the server does heavy work **once at startup**, so every subsequent request is served from RAM — not from disk.

### Route Organization

Routes are grouped by function:
- `/api/verify-title` — Core validation
- `/api/stats`, `/api/search`, `/api/recent` — Public data
- `/api/disallowed-words` — Word list management
- `/api/approval-request`, `/api/admin/*` — Admin workflow
- `/api/batch/*` — Bulk file processing

### Async vs Sync

- **Async routes** (`async def`): Used for I/O operations like file uploads and database writes
- **Sync routes** (`def`): Used for CPU-heavy operations like fuzzy matching (FastAPI runs these in a thread pool automatically)
- **`asyncio.to_thread()`**: The `init_db()` startup function is offloaded to a thread so it doesn't block the event loop

### Request/Response Validation

Every endpoint uses **Pydantic models** for automatic validation:

```python
class TitleRequest(BaseModel):
    title: str           # Required string

class TitleResponse(BaseModel):
    title: str
    verdict: str         # "APPROVED" | "REJECTED" | "PENDING_ADMIN"
    approval_probability: float
    rejection_reasons: list[str]
    priority_matches: dict
```

If a request sends wrong data types, FastAPI returns a `422 Unprocessable Entity` automatically — no manual validation code needed.

---

## 4. All API Endpoints

### Core Validation

| Method | Path | What it does |
|--------|------|-------------|
| `POST` | `/api/verify-title` | Check a single title — returns score, verdict, matches |
| `GET` | `/api/suggest-titles?title=...` | Get up to 5 alternative title suggestions |
| `GET` | `/api/stats` | Total titles, languages, states, disallowed word count |
| `GET` | `/api/search` | Search the database (by title, owner, state, language, etc.) |
| `GET` | `/api/recent` | Last 10 verified titles |

### Disallowed Words

| Method | Path | What it does |
|--------|------|-------------|
| `GET` | `/api/disallowed-words` | List all restricted words |
| `POST` | `/api/disallowed-words` | Add a new restricted word |
| `DELETE` | `/api/disallowed-words/{word}` | Remove a restricted word |

### Approval Workflow

| Method | Path | What it does |
|--------|------|-------------|
| `POST` | `/api/approval-request` | Submit a borderline title for admin review |
| `GET` | `/api/admin/pending-requests` | Get all titles awaiting admin decision |
| `GET` | `/api/admin/requests` | Get all requests (all statuses) |
| `POST` | `/api/admin/approve` | Approve a specific request |
| `POST` | `/api/admin/reject` | Reject a specific request |
| `POST` | `/api/admin/batch-approve` | Approve multiple requests at once |
| `POST` | `/api/admin/batch-reject` | Reject multiple requests at once |
| `POST` | `/api/admin/batch-approve-all-requests` | Approve all pending requests |
| `POST` | `/api/admin/batch-reject-all-requests` | Reject all pending requests |

### Temp2 & Rejected Titles

| Method | Path | What it does |
|--------|------|-------------|
| `GET` | `/api/admin/temp2` | Titles that are approved but not yet finalized |
| `POST` | `/api/admin/batch-approve-all` | Move all temp2 titles to the main database |
| `POST` | `/api/admin/batch-reject-all` | Discard all temp2 titles |
| `POST` | `/api/admin/batch-approve-by-score` | Approve temp2 titles above a score threshold |
| `GET` | `/api/admin/rejected-titles` | All auto/admin-rejected titles |
| `GET` | `/api/admin/rejected-titles/search` | Search rejected titles |
| `POST` | `/api/admin/rejected-titles/{id}/allow-retry` | Allow a rejected title to be resubmitted |

### Batch File Processing

| Method | Path | What it does |
|--------|------|-------------|
| `POST` | `/api/batch/upload` | Upload CSV/XLSX/XLS/TXT file, verify all titles |
| `POST` | `/api/batch/upload-text` | Submit a list of titles as text |
| `GET` | `/api/batch/{id}/results` | Get all results for a batch |
| `GET` | `/api/batch/{id}/analytics` | Breakdown of violations, conflicts, confidence levels |
| `POST` | `/api/batch/{id}/approve` | Approve selected titles from a batch |
| `POST` | `/api/batch/{id}/request-approval` | Send batch results to admin review queue |

### Admin Auth & Config

| Method | Path | What it does |
|--------|------|-------------|
| `POST` | `/api/admin/login` | Authenticate admin (SHA256 password check) |
| `GET` | `/api/admin/config/acceptance-ratio` | Get current acceptance threshold (default: 60%) |
| `POST` | `/api/admin/config/acceptance-ratio` | Update the acceptance threshold |
| `POST` | `/api/title/update` | Edit a field on an existing title record |

---

## 5. External Libraries & Why Each is Used

### `FastAPI`
The web framework. Chosen because it's fast (built on Starlette + ASGI), generates automatic API docs (`/docs`), and has native Pydantic integration for request validation with zero boilerplate.

### `Uvicorn`
The ASGI server that actually runs FastAPI. Think of FastAPI as the engine and Uvicorn as the car — you need Uvicorn to start the server.

### `RapidFuzz`
Used for **fuzzy string matching** — checking if two titles are *similar* even with typos, reordering, or minor differences.

- **Why RapidFuzz over fuzzywuzzy?** It's written in C++ and is 10–100× faster. Important when comparing against 77,564 titles.
- **Algorithm used:** `fuzz.token_sort_ratio` — breaks both strings into words, sorts them alphabetically, then compares. This means "Daily Times" and "Times Daily" score very high (essentially the same words, different order).
- **Threshold:** Only matches above 60% are reported. Matches above 80% are flagged as high-risk.

### `Jellyfish`
Used for **phonetic matching** — catching titles that *sound alike* even if spelled differently.

Two algorithms are used:
- **Soundex**: Groups words by how consonants sound. "SMITH" and "SMYTH" get the same code `S530`.
- **NYSIIS** (New York State Identification and Intelligence System): More sophisticated than Soundex, better for names and non-English words.

Both codes are pre-computed at startup for all 77,564 titles and stored in reverse indexes for O(1) candidate lookup.

### `deep-translator` (Google Translate API)
Used for **cross-language semantic detection**. When a title contains non-ASCII characters (Hindi, Bengali, Marathi, etc.), it's translated to English first, then fuzzy-matched against the English titles database.

- **Why needed?** "Rashtra Samachar" and "National News" would never match via fuzzy or phonetic checks. But translated, they become very similar.
- **API used:** `deep_translator.GoogleTranslator(source='auto', target='en')`
- **Skip condition:** If the title is pure ASCII (already English), translation is skipped entirely to save API call time.

### `pandas`
Used only for **batch file uploads** — reading CSV and Excel files into a structured table, then extracting the title column.

- Handles CSV, XLSX, XLS, TXT
- Auto-detects which column contains titles by scanning column names for keywords like "title", "name", "publication"

### `openpyxl`
Excel `.xlsx` file reader, used as the pandas engine for modern Excel files.

### `xlrd`
Excel `.xls` (legacy format) file reader. Pinned to `xlrd<2.0` because newer versions dropped `.xls` support.

### `Pydantic v2`
Data validation library. Every API request and response is defined as a Pydantic model. FastAPI uses these models to:
- Validate incoming request fields (type, presence, constraints)
- Serialize outgoing responses to JSON
- Auto-generate the `/docs` Swagger UI

### `python-multipart`
Enables FastAPI to accept `multipart/form-data` requests (file uploads). Without this, the batch upload endpoint would fail silently.

### `sqlite3` (built-in Python)
No external dependency — Python includes SQLite. Used in WAL (Write-Ahead Logging) mode, which allows multiple simultaneous readers while a write is happening. Critical for batch processing where many results are being written while the UI is polling for updates.

---

## 6. The Scoring Formula — Layman's Explanation

### The Simple Version

Imagine you're applying for a title. The system gives you a score out of 100%. This score answers the question:

> *"What is the chance this title will be approved?"*

The score is built from **4 ingredients**, each contributing a different amount:

| Ingredient | Weight | What it measures |
|-----------|--------|-----------------|
| How unique the title sounds | 45% | Is it too similar to something already registered? |
| How clean it is by the rules | 30% | Does it use banned words or break name rules? |
| Whether it has restricted words at start/end | 15% | Does it start with "The" or end with "Daily"? |
| Whether it combines existing titles | 10% | Is it stitched together from two existing titles? |

---

### The Cricket Analogy

Think of the score like a **cricket batting scorecard**:

- You start with a **potential of 100 runs**.
- Every problem with your title *deducts* runs.
- Your final score is what's left after all deductions.

**Ingredient 1 — Uniqueness (45 runs available):**
The system checks how similar your title is to any existing title (using phonetic + fuzzy + translation checks). If your title is 80% similar to "Times Daily", you only earn `(1 - 0.80) × 45 = 9 runs` out of 45. If completely unique, you earn all 45.

**Ingredient 2 — Rule Compliance (30 runs available):**
The system counts how many rule violations your title has (banned words, periodicity abuse, etc.). Each violation costs you 3 runs. Zero violations = full 30. Ten or more violations = 0 runs.

**Ingredient 3 — Clean Start/End (15 runs available):**
If your title starts or ends with restricted words like "The", "India", "Samachar", "Daily", "Weekly":
- 0 such words → 15 runs
- 1–2 such words → 7.5 runs
- 3 or more → 0 runs

**Ingredient 4 — Not a Combination (10 runs available):**
If your title looks like it was made by merging two existing titles (e.g., "Times" + "Samachar" → "Times Samachar Daily"):
- Not a combination → 10 runs
- Is a combination → 0 runs

**Final Score = Sum of all four ingredients**

---

### The Exact Formula (for technical readers)

```
Score = (Uniqueness Component  × 0.45)
      + (Rule Compliance       × 0.30)
      + (Prefix/Suffix Score   × 0.15)
      + (Combination Score     × 0.10)

Where each component is a value between 0.0 and 1.0:

Uniqueness      = 1.0 − max(fuzzy_similarity, phonetic_similarity, cross_language_similarity)
Rule Compliance = max(0.0, 1.0 − violation_count / 10.0)
Prefix/Suffix   = 1.0 if 0 warnings, 0.5 if 1–2 warnings, 0.0 if 3+ warnings
Combination     = 1.0 if no combination found, 0.0 if combination found

Final Score × 100 = Approval Probability %
```

---

### What Happens Based on the Score

| Score | Decision | Meaning |
|-------|---------|---------|
| **> 60%** | ✅ AUTO APPROVED | Title goes to Temp2 staging database |
| **30% – 60%** | ⏳ PENDING ADMIN | Sent to admin review queue |
| **< 30%** | ❌ AUTO REJECTED | Logged in rejected titles |

The 60% threshold is **configurable by admin** via the Settings panel.

---

### Hard Overrides (Score Becomes 0% Instantly)

Some situations bypass the formula entirely:

- **Exact match found** → 0% (the title exists verbatim in the database)
- **Disallowed word detected** → 0%
- **Prefix/suffix rule violated strictly** → 5%

No matter how good the rest of the title is, these hard overrides make it an instant rejection.

---

### Real Example

**Title submitted:** "Bharat Samachar Weekly"

| Check | Finding | Score Impact |
|-------|---------|-------------|
| Exact match? | No exact match | No override |
| Fuzzy similar? | "Bharat Samachar" = 72% similar to "Bharat News" | Uniqueness = `(1 − 0.72) × 0.45 = 0.126` |
| Rule violations? | 1 violation (periodicity: "Bharat Samachar" already exists + "Weekly" added) | Rule = `(1 − 1/10) × 0.30 = 0.27` |
| Prefix/suffix? | "Weekly" at end — 1 warning | P/S = `0.5 × 0.15 = 0.075` |
| Combination? | No combination | Combo = `1.0 × 0.10 = 0.10` |
| **Final Score** | `0.126 + 0.27 + 0.075 + 0.10 = 0.571` → **57.1%** | PENDING ADMIN |

---

## 7. The 5-Priority Match System

The system doesn't just do one check — it runs **five different types of comparisons**, from simplest to most complex. They are run in order, and the results of each feed into the final score.

### Priority 1 — Exact Match
**What it does:** Checks if the title already exists word-for-word.
**How:** O(1) Python set lookup against all 77,564 titles in RAM.
**Example:** "Times Daily" → exact match found → instant 0%.
**Speed:** Microseconds.

### Priority 2 — Similar Titles (Fuzzy + Phonetic)
**What it does:** Finds titles that look or sound similar.

**Fuzzy Matching:** Uses character-level comparison.
- "Times Daly" vs "Times Daily" → 95% similar (one character different)
- "Dainik Bhaskar" vs "Dainick Bhasker" → 88% similar (multiple typos)

**Phonetic Matching:** Uses sound codes.
- "Prabhat" and "Prabhaat" → both encode to the same Soundex codes → flagged as phonetically identical
- Catches transliteration variations where the same Hindi word is spelled differently in Roman script

**Threshold for risk:** > 80% = flagged as high-risk similar title.

### Priority 3 — Combination Detection
**What it does:** Detects if a new title is made by merging parts of two or more existing titles.

**Example:**
- "Hindustan Times" is registered.
- "Daily News" is registered.
- Someone submits "Hindustan Times Daily News" — this combines both.
- The system detects both original titles embedded inside and rejects it.

**How it works:** Uses a word → titles reverse index. For each word in the submitted title, it finds every existing title containing that word, then checks if two or more such titles are fully embedded.

### Priority 4 — Cross-Language Semantic Matching
**What it does:** Translates the submitted title to English (if it contains non-ASCII text) and then fuzzy-matches the translation against the database.

**Example:**
- "Rashtra Samachar" (Hindi) → Google Translate → "National News"
- "National News" fuzzy-matched against database → 82% match with "National Daily"
- Flagged as cross-language semantic conflict.

**Why important:** India has 22 official languages. A title in Gujarati could mean the same thing as an already-registered title in English.

### Priority 5 — Conceptual Theme Matching
**What it does:** Checks if the title belongs to an overused conceptual theme using pre-defined keyword clusters.

**Themes defined:**
- "morning": prabhat, bhor, pratah, ushakal, subah
- "evening": sayam, sham
- "nation": rashtra, desh

**Example:** "Prabhat Times" → "prabhat" matches "morning" theme → flagged as conceptual theme overlap.

**Note:** This doesn't auto-reject but it's reported to the reviewer.

---

## 8. Database Structure

All data is stored in a single SQLite file: `backend/data/prgi_titles.db`

### Tables Overview

```
prgi_titles.db
├── titles              ← 77,564 registered publication titles
├── disallowed_words    ← Restricted/banned words
├── approval_requests   ← Titles pending admin decision
├── temp2               ← Approved but not yet finalized titles
├── batch_uploads       ← Batch job metadata
├── batch_results       ← Individual results from batch jobs
├── admin_users         ← Admin credentials (SHA256 hashed)
├── admin_config        ← Configurable settings (e.g., acceptance ratio)
└── rejected_titles     ← History of all rejected titles
```

### Key Table: `titles`

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Auto-incrementing primary key |
| title | TEXT | The publication name |
| registration_number | TEXT | Official RNI number |
| registration_date | TEXT | Date of original registration |
| language | TEXT | Publication language |
| periodicity | TEXT | Daily / Weekly / Monthly / etc. |
| publisher | TEXT | Publisher name |
| owner | TEXT | Owner name |
| pub_state | TEXT | State of publication |
| pub_district | TEXT | District of publication |

### In-Memory Caches (Loaded at Startup)

These are Python data structures built from the database and kept in RAM for fast access:

| Cache | Type | Purpose |
|-------|------|---------|
| `TITLES_CACHE_SET` | `set` | O(1) exact match lookup |
| `TITLES_CACHE_LIST` | `list` | Iteration for fuzzy search |
| `PHONETIC_CACHE` | `dict` | title → (soundex_codes, nysiis_codes) |
| `SOUNDEX_INDEX` | `dict` | soundex_code → set of titles |
| `NYSIIS_INDEX` | `dict` | nysiis_code → set of titles |
| `WORD_INDEX` | `dict` | word → set of titles containing it |
| `DISALLOWED_WORDS_CACHE` | `list` | All banned words |

Without these caches, every request would require scanning all 77,564 rows in SQL — which would be slow. With them, most lookups happen in microseconds.

---

## 9. How a Title Flows Through the System

Here is the complete journey of a title from submission to verdict:

```
User types "Hindustan Morning Times"
           ↓
[POST /api/verify-title]
           ↓
TitleEvaluationService.evaluate(title)
           ↓
┌─────────────────────────────────────────┐
│  STEP 1: Normalize                      │
│  "Hindustan Morning Times"              │
│  → Strip extra spaces, uppercase        │
│  → "HINDUSTAN MORNING TIMES"            │
└────────────────┬────────────────────────┘
                 ↓
┌─────────────────────────────────────────┐
│  STEP 2: Check Cache                    │
│  MD5("hindustan morning times") → key   │
│  If result < 5 min old → return cached  │
└────────────────┬────────────────────────┘
                 ↓
┌─────────────────────────────────────────┐
│  STEP 3: Priority 1 — Exact Match       │
│  "HINDUSTAN MORNING TIMES" in SET?      │
│  No → continue                          │
└────────────────┬────────────────────────┘
                 ↓
┌─────────────────────────────────────────┐
│  STEP 4: Priority 2 — Fuzzy Check       │
│  RapidFuzz against TITLES_CACHE_LIST    │
│  "Hindustan Morning" → 76% match        │
│  → Reported as similar title            │
└────────────────┬────────────────────────┘
                 ↓
┌─────────────────────────────────────────┐
│  STEP 5: Priority 2 — Phonetic Check    │
│  Soundex("HINDUSTAN")="H532"            │
│  Lookup SOUNDEX_INDEX["H532"]           │
│  → Set of titles containing H532        │
│  Score overlap → reported               │
└────────────────┬────────────────────────┘
                 ↓
┌─────────────────────────────────────────┐
│  STEP 6: Priority 3 — Rules Check       │
│  check_rules_detailed()                 │
│  → No disallowed words                  │
│  → "MORNING" → suffix/prefix flag       │
│  → Combination: "HINDUSTAN" + "TIMES"   │
│     both found in WORD_INDEX            │
│  → VIOLATION: combination detected      │
└────────────────┬────────────────────────┘
                 ↓
┌─────────────────────────────────────────┐
│  STEP 7: Priority 4 — Cross-Language    │
│  Title is ASCII? Yes → SKIP             │
└────────────────┬────────────────────────┘
                 ↓
┌─────────────────────────────────────────┐
│  STEP 8: Priority 5 — Conceptual Theme  │
│  "MORNING" → matches "morning" theme    │
│  → Theme flag reported                  │
└────────────────┬────────────────────────┘
                 ↓
┌─────────────────────────────────────────┐
│  STEP 9: Weighted Formula               │
│  Uniqueness: 1 - 0.76 = 0.24 × 0.45    │
│  Rules: (1 - 1/10) × 0.30 = 0.27       │
│  Prefix/Suffix: 0.5 × 0.15 = 0.075     │
│  Combination: 0 × 0.10 = 0.0           │
│  SCORE = 10.8 + 27 + 7.5 + 0 = 45.3%   │
└────────────────┬────────────────────────┘
                 ↓
           PENDING ADMIN
    (30% < 45.3% < 60% threshold)
           ↓
[Auto-insert into approval_requests table]
           ↓
[Return response to UI with all details]
```

---

## 10. Admin Workflow

The system has a two-stage approval process for borderline titles:

```
Title Score 30–60%
       ↓
Inserted into approval_requests (status: pending)
       ↓
Admin logs in → /api/admin/login
       ↓
Admin sees pending requests → /api/admin/pending-requests
       ↓
Admin reviews each title and its match report
       ↓
         ┌───────────────────┬───────────────────┐
         ▼                   ▼                   ▼
  APPROVE single       REJECT single      BULK APPROVE/REJECT
 /admin/approve       /admin/reject       /admin/batch-approve
         ↓                   ↓
  Goes to temp2       Goes to rejected_titles
         ↓
  Admin can then push
  all temp2 → titles
 /admin/batch-approve-all
```

**Why temp2?** It acts as a staging area. Even after admin approval, a title isn't immediately public. An admin must do a final "publish all" action to move temp2 → main database. This gives a chance to catch any mistakes before they become permanent.

---

## 11. Batch Processing

For government/publisher use cases where hundreds of titles need to be checked at once:

1. **Upload a file** (CSV, Excel, or TXT) via `/api/batch/upload`
2. The system:
   - Auto-detects the title column
   - Runs all 77,564-title checks for each row in **parallel** (up to 16 workers via `ThreadPoolExecutor`)
   - Inserts titles above the score threshold into temp2
   - Logs all results in `batch_results` table
3. **View results** via `/api/batch/{id}/results`
4. **View analytics** via `/api/batch/{id}/analytics`:
   - Breakdown by violation type
   - Distribution by confidence level
   - Language conflict counts
   - State-wise rejection patterns
5. Admin can then **approve or reject** from the batch UI

---

## 12. Performance Design — Why It's Fast

Checking 77,564 titles naively would mean 77,564 comparisons per request. For fuzzy matching, that's ~77,000 string operations. The system uses several optimizations to avoid this:

### Reverse Indexes (Most Important Optimization)

Instead of "scan all titles for each query", the system builds lookup tables at startup:

**SOUNDEX_INDEX:**
```
"H532" → {"HINDUSTAN TIMES", "HINDUSTAN DAILY", "HINDUSTAN SAMACHAR", ...}
```
For a new title, compute its Soundex codes → look up only the titles that share those codes → compare only ~50–200 candidates instead of 77,564.

**WORD_INDEX:**
```
"TIMES" → {"Times Daily", "New York Times", "Times of India", ...}
```
For combination detection, look up only titles that share words with the input.

### In-Memory Cache (TITLES_CACHE_SET)
Exact match = one Python `in` operation. No SQL query, no disk I/O.

### 5-Minute Result Cache
MD5 hash of the normalized title → cached result. Same title verified within 5 minutes returns instantly.

### Parallel Batch Processing
`ThreadPoolExecutor(max_workers=16)` means 16 titles are verified simultaneously during batch uploads.

### WAL Mode on SQLite
Allows reads and writes to happen concurrently — batch writes don't block the UI from reading results.

---

## 13. Frequently Asked Questions

**Q: How is the score different from "similarity"?**
A: Similarity is just one component (45% weight). The score also considers rule compliance, restricted words, and combination patterns. A title can be completely unique but still score low because it uses banned words.

**Q: What does PENDING_ADMIN mean? Is the title rejected?**
A: No. It means the system isn't confident enough to auto-approve or auto-reject. A human admin reviews it. The final decision is theirs.

**Q: Can a title score 100%?**
A: Yes — if it has zero similarity to anything in the database, zero rule violations, no restricted prefix/suffix words, and no combination patterns. In practice, most titles with common words like "India", "Daily", "News" will lose points on the prefix/suffix component.

**Q: What happens if I submit the same title twice?**
A: The result is served from a 5-minute cache. Identical result, zero processing cost.

**Q: What does "Cross-language" match mean in the results?**
A: Your title (in a regional language) was translated to English, and that English translation closely matches an already-registered title. Example: "Desh Samachar" → "Country News" → 82% match with "National News".

**Q: Why does the system use Soundex AND NYSIIS? Why both?**
A: Soundex is simple but misses some patterns. NYSIIS is more accurate for Indian names and transliterations. Running both and taking the max gives better coverage with minimal extra cost (both are pre-computed at startup).

**Q: What is temp2?**
A: A staging database. Admin-approved titles land here first instead of directly in the main database. This lets admins review the full set before making them public. Think of it as a "confirmed but unpublished" queue.

**Q: Can the 60% acceptance threshold be changed?**
A: Yes. Admin can change it from 0–100 via the Admin panel → Settings. Lowering it means more titles auto-approve. Raising it means more go to admin review.

**Q: How does the combination detection avoid false positives?**
A: It requires at least 3-word titles and skips common stop words (THE, AND, OF, FOR, IN, A). Single-word or two-word overlaps with common words like "The Times" don't trigger combination violations. Only full embedded titles from the database count.

**Q: What languages does the cross-language check support?**
A: All languages supported by Google Translate (100+). The system uses `auto-detect` as the source language, so it handles any non-ASCII title automatically.

**Q: Why is the database SQLite and not PostgreSQL/MySQL?**
A: The system is designed as a deployable government desktop/intranet tool, not a cloud service. SQLite requires zero configuration, no separate server process, and the WAL mode handles the concurrency needs of this workload. For a multi-user cloud deployment, swapping to PostgreSQL would require changing only the connection string.

---
