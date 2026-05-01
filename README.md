# Ledger Engine

A production-grade, containerized backend designed for asynchronous data ingestion, multi-tenant transaction routing, and cryptographic user authentication. Built with a strict systems-based approach, this API prioritizes architectural depth, decoupled services, and isolated testing environments.

## Core Tech Stack

* **Framework:** FastAPI (Python 3.11)
* **Database:** PostgreSQL 15 
* **ORM & Driver:** SQLAlchemy (v2.0) with `asyncpg`
* **Authentication:** JWT & Bcrypt (via Passlib)
* **Testing:** Pytest, HTTPX (AsyncClient), Pytest-Asyncio
* **Infrastructure:** Docker & Docker Compose
* **CI/CD:** GitHub Actions

## Project Structure

The application is built on a modular architecture, separating network routing, database schemas, and core business logic.

```text
├── .github/workflows/ci.yml  # Automated CI pipeline
├── api_contract.md           # Master blueprint for frontend/backend alignment
├── app/
│   ├── core/                 # Cryptographic security & hashing (security.py)
│   ├── models/               # SQLAlchemy ORM models (user.py, transaction.py)
│   ├── routers/              # FastAPI endpoint routing (user.py, transaction.py)
│   ├── schemas/              # Pydantic V2 validation schemas
│   ├── services/             # Core logic (ledger_parser.py, ledger_queries.py)
│   ├── tests/                # Fully isolated asynchronous test suite
│   ├── database.py           # Engine creation and session management
│   └── main.py               # Application entry point
├── docker-compose.yml        # Multi-container orchestration
├── Dockerfile                # Backend environment configuration
└── requirements.txt          # Explicit dependency locking
