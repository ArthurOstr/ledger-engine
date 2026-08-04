# Ledger Engine

An asynchronous, multi-tenant backend for parsing real-world Ukrainian bank exports (Monobank, PrivatBank) into a structured financial ledger.

Instead of blocking the HTTP thread on file parsing, or relying only on application-level `WHERE owner_id = ...` filters for tenant isolation, this project pushes both concerns down a layer: file parsing is offloaded to a background worker via a Redis task queue, and tenant isolation is enforced at the database layer using PostgreSQL Row-Level Security.

---

## Core Design Decisions

### 1. Database-Level Multi-Tenancy (Row-Level Security)

Tenant isolation isn't only handled in application code — it's also enforced by PostgreSQL itself using **Row-Level Security (RLS)** (`alembic/versions/c8985766e632_enable_row_level_security.py`).

- On each request, `get_current_user` (`app/core/dependencies.py`) resolves the authenticated user from the session cookie, then sets a transaction-scoped Postgres variable: `set_config('app.current_user_id', user_id, true)` — the `true` flag scopes it to the current transaction, equivalent to `SET LOCAL`.
- RLS policies reference this variable to automatically filter `SELECT`, `UPDATE`, and `DELETE` against tenant-owned tables.
- This adds a second, database-level layer of protection against cross-tenant data leaks — even if an application-layer query forgets to filter by tenant, the RLS policy still applies. (It's not an absolute guarantee — RLS depends on the app consistently setting the tenant variable per session, and on policies being applied to every relevant table/command — but it meaningfully reduces the blast radius of a routing or query bug.)

### 2. Non-Blocking Ingestion (ARQ + Redis)

Parsing `.xlsx` exports with thousands of transactions is I/O- and CPU-heavy enough that doing it inline would block the request.

- `POST /api/transactions/upload` returns `202 Accepted` immediately and hands the file off to an **ARQ background worker** (`app/worker.py`) via a Redis queue (Upstash).
- The FastAPI event loop stays free to serve other requests while parsing happens out-of-process.

### 3. Bulk Categorization via In-Database Updates

When a user defines a new categorization rule (e.g. `steam → Entertainment`), the backend doesn't pull historical transactions into Python to re-tag them.

- Instead, `app/routers/rules.py` issues a bulk `UPDATE` statement that runs entirely inside PostgreSQL.
- This avoids loading potentially large transaction histories into application memory through the ORM, and lets Postgres apply the update set-based rather than row-by-row in Python.

### 4. Hash-Based Deduplication

Users often re-upload bank statements with overlapping date ranges. To avoid duplicate entries, `app/services/ledger_parser.py` computes a **SHA-256 hash** per transaction from its timestamp, description, amount, and balance, then inserts with `INSERT ... ON CONFLICT DO NOTHING`.

- This makes re-uploads idempotent without needing a separate "check if this exists" query before every insert.

### 5. Cookie-Based Auth (No Tokens in Frontend JS)

Auth tokens are never stored in `localStorage` or exposed to frontend JavaScript.

- The API issues **HttpOnly, SameSite, Secure cookies**, negotiated through an edge proxy (`app/routers/google_auth.py`).
- This removes the most common way a stored token gets exfiltrated via XSS — the token is simply never reachable from JS in the first place.

---

## Ingestion Pipeline

```text
[ Client Upload ]
       │
       ▼  POST /api/transactions/upload
┌────────────────────────────────────────┐
│ FastAPI HTTP API (immediate 202)       │
└──────────────────┬─────────────────────┘
                   │ enqueues job
                   ▼
┌────────────────────────────────────────┐
│ Redis Queue (Upstash)                  │
└──────────────────┬─────────────────────┘
                   │ consumed asynchronously
                   ▼
┌────────────────────────────────────────┐
│ ARQ Background Worker (app/worker.py)  │
│  1. Parse Excel export (Pandas)        │
│  2. Compute SHA-256 hash per row       │
│  3. Map to Monobank/PrivatBank schema  │
└──────────────────┬─────────────────────┘
                   │ atomic upsert, RLS active
                   ▼
┌────────────────────────────────────────┐
│ PostgreSQL (Neon)                      │
└────────────────────────────────────────┘
```

---

## Repository Structure

```
ledger-engine-main/
├── alembic/
│   └── versions/
│       ├── 5cf7db0c7681_initial_schema.py
│       ├── b15f2c000860_add_category_rules_table.py
│       └── c8985766e632_enable_row_level_security.py   # RLS migration
├── app/
│   ├── core/
│   │   ├── config.py             # Pydantic environment settings
│   │   ├── dependencies.py       # Session injection & RLS tenant binding
│   │   └── security.py           # Crypto primitives & JWT validation
│   ├── models/                   # SQLAlchemy 2.0 declarative models
│   ├── routers/
│   │   ├── rules.py              # Bulk categorization endpoints
│   │   └── transaction.py        # 202 Accepted upload endpoint
│   ├── services/
│   │   ├── ledger_parser.py      # Pandas-based bank export ETL
│   │   └── ledger_queries.py     # Analytical queries
│   ├── tests/                    # Isolation, contract, and ETL tests
│   ├── main.py                   # FastAPI application entrypoint
│   └── worker.py                 # ARQ background task execution
├── docker-compose.yml            # API, worker, Redis, Postgres orchestration
└── Dockerfile
```

---

## Test Suite

The test suite (`app/tests/`) covers tenant isolation, async job behavior, and parser resilience, run against a live test database with RLS policies active.

```bash
# Full suite
docker compose exec api pytest -v

# RLS tenant isolation tests only
docker compose exec api pytest app/tests/test_transactions.py -k "test_rls_isolation" -v
```

**What's covered:**

- **Tenant isolation** — a session scoped to one tenant cannot read or modify another tenant's rows, including via queries without an explicit tenant filter.
- **Worker context propagation** — background jobs correctly inherit tenant context during batch ingestion (`with_db_session` decorator).
- **Parser resilience** — handles malformed real-world exports, including Cyrillic/Latin lookalike character mismatches and broken headers.
- **Hash determinism** — re-processing identical rows produces zero duplicate inserts.

---

## Running Locally

**1. Environment**

Create a `.env` file in the project root:

```
DATABASE_URL=postgresql+asyncpg://postgres:postgres@db:5432/ledger
REDIS_URL=redis://redis:6379
SECRET_KEY=your_secure_hex_secret
```

**2. Start the stack**

```bash
docker compose up --build -d
```

**3. Apply migrations (including RLS policies)**

```bash
docker compose exec api alembic upgrade head
```

**4. Explore the API**

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

---

## Stack

- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2.0 (async), Pydantic, Alembic
- **Infra:** Docker, Upstash Redis, ARQ, PostgreSQL (Neon)
