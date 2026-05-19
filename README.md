# PRGI Title Validator

**Press Registrar General of India — Title Uniqueness & Compliance Verification System**

A full-stack web application that verifies whether a proposed publication title can be registered under the Press Registration of Periodicals Act. It checks against a database of ~70,000 registered titles using a 5-priority semantic match system, compliance rules, and phonetic/fuzzy algorithms.

🔗 **Live Demo:** [prgi-model-xim.onrender.com](https://prgi-model-xim.onrender.com/)

---

## Features

- **Title Verification** — Real-time uniqueness check against 58,000+ registered PRGI titles
- **5-Priority Match System** — Exact match, high similarity, combination detection, cross-language semantic, and conceptual theme matching
- **Fuzzy & Phonetic Matching** — Catches typos, transliterations, and sound-alike titles using RapidFuzz and Jellyfish (Soundex + NYSIIS)
- **Cross-Language Detection** — Translates Hindi/regional language titles to English and checks against the registry
- **Compliance Rules Engine** — Blocks disallowed words, restricted prefixes/suffixes, and periodicity violations
- **Batch Upload** — Upload CSV/TXT/XLS/XLSX files (up to 200 titles) for bulk verification with 6 analytics charts
- **Admin Panel** — Review, approve/reject, and push verified titles into the main registry
- **Searchable Database** — Browse and filter all registered titles by state, language, periodicity, and more

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python, FastAPI, SQLite, Pydantic v2 |
| Frontend | Vanilla HTML/CSS/JS, Chart.js, Lucide Icons |
| Matching | RapidFuzz, Jellyfish, deep-translator (Google Translate) |
| Deployment | Render |

---

## Architecture

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

---

## Project Structure

```
PRGI-model-XIM/
├── backend/
│   ├── main.py                  # FastAPI app & all API endpoints
│   ├── database.py              # Main DB — CRUD + in-memory title cache
│   ├── temp_database.py         # Temp DB — batch/admin review queue
│   ├── load_titles.py           # One-time utility: imports Excel → DB
│   ├── requirements.txt
│   ├── models/
│   │   └── schemas.py           # Pydantic request/response models
│   ├── services/
│   │   ├── similarity_engine.py # Orchestrates all checks → final verdict
│   │   ├── rules_checker.py     # Compliance rules (disallowed words, prefix, combo)
│   │   ├── fuzzy_checker.py     # RapidFuzz string similarity
│   │   ├── phonetic_checker.py  # Soundex + NYSIIS phonetic matching
│   │   └── semantic_checker.py  # Cross-language translation + theme clusters
│   └── data/
│       ├── prgi_titles.db       # SQLite — main title registry (~70k titles)
│       ├── temp.db              # SQLite — pending batch submissions
│       └── disallowed_words.json
└── frontend/
    └── index.html               # Complete SPA (HTML + CSS + JS)
```

---

## Getting Started

### Prerequisites

- Python 3.9+
- pip

### Installation

```bash
# Clone the repository
git clone https://github.com/RemasteredGod/PRGI-model-XIM.git
cd PRGI-model-XIM

# Install backend dependencies
pip install -r backend/requirements.txt
```

### Running Locally

**Start the backend:**

```bash
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

**Serve the frontend** (in a separate terminal):

```bash
cd frontend
python -m http.server 5500
```

**Open in browser:**

| Page | URL |
|------|-----|
| Title Validator | `http://localhost:5500/index.html` |
| Batch Upload | `http://localhost:5500/batch.html` |
| Admin Panel | `http://localhost:5500/admin.html` |
| Admin Review | `http://localhost:5500/admin-review.html` |

**API Docs (auto-generated):**

| Format | URL |
|--------|-----|
| Swagger UI | `http://localhost:8000/docs` |
| ReDoc | `http://localhost:8000/redoc` |

### Startup Output

```
Loaded 70,936 titles from prgi_titles.db
After deduplication: 70,936 unique titles ready
Phonetic cache ready for 70,936 titles
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

---

## The 5-Priority Match System

All matches are ranked by severity:

| Priority | Label | What It Catches | Effect |
|----------|-------|-----------------|--------|
| **1** | Exact Match | Identical string in registry (O(1) set lookup) | Hard reject |
| **2** | High Similarity | Fuzzy or phonetic score ≥ 80% | Reject |
| **3** | Combination | Title = two or more existing titles combined | Reject |
| **4** | Semantic Cross-Language | Translated title matches ≥ 76% | Reject |
| **5** | Semantic Conceptual | Title word belongs to a theme cluster | Warning |

---

## API Reference

### Public Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/verify-title` | Verify a proposed title — returns verdict, score, and matches |
| `GET` | `/api/search` | Search registered titles (query params: `q`, `state`, `language`, `limit`) |
| `GET` | `/api/stats` | System statistics (total titles, languages, states) |
| `GET` | `/api/recent` | Last 10 verified titles |
| `GET` | `/api/disallowed-words` | List all disallowed words |
| `POST` | `/api/disallowed-words` | Add a disallowed word |
| `DELETE` | `/api/disallowed-words/{word}` | Remove a disallowed word |
| `POST` | `/api/batch-upload` | Upload CSV/TXT/XLS/XLSX for bulk verification |

### Admin Endpoints

All require header: `Authorization: Bearer prgi_admin_token_2024`

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/admin/login` | Authenticate admin |
| `GET` | `/api/admin/pending` | Get all pending batch titles |
| `POST` | `/api/admin/approve` | Approve selected titles |
| `POST` | `/api/admin/reject` | Reject selected titles |
| `POST` | `/api/admin/push-to-main` | Push approved titles into the main registry |
| `GET/POST` | `/api/admin/settings` | View/update acceptance threshold |

---

## Key Design Decisions

| Decision | Reason |
|----------|--------|
| In-memory title cache | Avoids DB queries per verification; O(1) exact match |
| Precomputed phonetic cache | No re-running Jellyfish on 70k titles per request |
| Parallel batch processing | `ThreadPoolExecutor` (12 workers) for concurrent I/O |
| Two-database architecture | Keeps official registry clean; batch titles go through admin review |
| RapidFuzz over difflib | 10–100× faster when scanning 70k candidates |
| Pydantic v2 models | Auto-validation, serialization, and OpenAPI schema generation |

---

## License

This project is open source. See the repository for details.

---

Built for the Press Registrar General of India's title registration workflow.
