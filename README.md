# Telegram Backup Bot 🤖📦

A robust, production-oriented Telegram backup system that allows users to back up documents, media, and messages, with metadata indexed in MongoDB, files stored in pluggable storage (local/S3), and managed via Telegram bot and FastAPI web dashboard.

---

## Architecture Overview

```
Telegram User ──────> aiogram 3.x Bot ───> Backup Service ───> MongoDB (Tasks & Metadata)
                                                                     │
Web Dashboard <────── FastAPI REST API <── Storage Service <── Worker Polling Loop
```

- **Database**: MongoDB (Primary store & resilient task queue state — No Redis required)
- **Async Driver**: Modern PyMongo Asynchronous API (`pymongo.AsyncMongoClient`)
- **API Framework**: FastAPI (Async REST API & Web Dashboard)
- **Telegram Bot**: aiogram 3.x
- **Containerization**: Docker & Docker Compose

---

## Directory Structure

```
telegram-backup-bot/
├── app/
│   ├── main.py                  # Top-level application runner
│   ├── bot/                     # aiogram Telegram bot components
│   │   ├── bot.py
│   │   ├── handlers/
│   │   ├── keyboards/
│   │   ├── filters/
│   │   └── middlewares/
│   ├── api/                     # FastAPI backend & endpoints
│   │   ├── main.py
│   │   ├── dependencies.py
│   │   ├── routes/
│   │   └── schemas/
│   ├── core/                    # Core configuration, logging, exceptions
│   │   ├── config.py
│   │   ├── security.py
│   │   ├── logging.py
│   │   └── exceptions.py
│   ├── database/                # MongoDB connection, models & repositories
│   │   ├── mongo.py
│   │   ├── models/
│   │   └── repositories/
│   ├── services/                # Business logic services
│   │   ├── backup_service.py
│   │   ├── file_service.py
│   │   ├── hash_service.py
│   │   ├── search_service.py
│   │   ├── storage_service.py
│   │   └── user_service.py
│   ├── workers/                 # MongoDB task worker
│   │   ├── worker.py
│   │   └── tasks.py
│   └── templates/               # Jinja2 HTML templates
├── frontend/                    # Static frontend assets (CSS, JS)
├── tests/                       # Unit, integration, and API tests
│   ├── unit/
│   ├── integration/
│   └── api/
├── storage/                     # Local storage destination
├── scripts/                     # Operational & verification scripts
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── requirements.txt
└── README.md
```

---

## Health Check & Probe Endpoints

| Endpoint | Probe Type | Purpose | Healthy Status | Disconnected / Degraded |
|---|---|---|---|---|
| `GET /health/live` | Liveness | Verifies application process is running | HTTP 200 (`{"status": "alive"}`) | — |
| `GET /health/ready` | Readiness | Verifies MongoDB connectivity | HTTP 200 (`{"status": "ready"}`) | HTTP 503 (`{"status": "not_ready"}`) |
| `GET /health` | Combined | Overall application + database status | HTTP 200 (`{"status": "healthy"}`) | HTTP 503 (`{"status": "degraded"}`) |
| `GET /api/health` | Alias | API prefixed status check | HTTP 200 (`{"status": "healthy"}`) | HTTP 503 (`{"status": "degraded"}`) |

---

## Getting Started

### 1. Prerequisites
- Python 3.12+ (or 3.13)
- MongoDB 7.0+ (or Docker)
- Docker & Docker Compose (optional, for containerized run)

### 2. Local Setup

```bash
# Clone and navigate into directory
cd Telegram-backup-bot

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
```

### 3. Running with Docker Compose

```bash
# Build and start MongoDB and FastAPI
docker compose up -d

# Check service logs
docker compose logs -f api

# Verify health probes
curl http://localhost:8000/health/live
curl http://localhost:8000/health/ready
curl http://localhost:8000/health
```

### 4. Running Locally

```bash
# Start FastAPI application
python3 -m app.main
# or
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## Running Tests

```bash
# Run full test suite
pytest -v
```

---

## Development Phases Roadmap

- [x] **Phase 1: Foundation** (Project structure, Async PyMongo connection manager, Config, Logging, Liveness/Readiness Health Checks, Docker, Tests)
- [ ] **Phase 2: MongoDB Models & Repositories**
- [ ] **Phase 3: Storage Layer** (StorageService & LocalStorageService)
- [ ] **Phase 4: Telegram Bot** (aiogram 3.x commands & media handlers)
- [ ] **Phase 5: MongoDB Task Worker**
- [ ] **Phase 6: Search & Filtering**
- [ ] **Phase 7: FastAPI REST API**
- [ ] **Phase 8: Web Dashboard**
- [ ] **Phase 9: Security Audit & Hardening**
- [ ] **Phase 10: Production Readiness & Deployment**
- [ ] **Phase 11: Advanced Features** (S3/R2, Encryption, AI categorization)
