# Telegram Backup Bot 🤖📦

A robust, production-oriented Telegram backup system that allows users to back up documents, media, and messages, with metadata indexed in MongoDB, files stored in pluggable storage (local/S3), and managed via Telegram bot and FastAPI web dashboard.

---

## Architecture Overview

```text
                    USER
                     │
          ┌──────────┴──────────┐
          │                     │
       Telegram              Browser
          │                     │
          ▼                     ▼
    aiogram handlers       Web Dashboard (HTML5 / Vanilla JS)
          │                     │
          └──────────┬──────────┘
                     ▼
                Core Services
      (Management, Search, Folders, Tags, Storage)
                     │
          ┌──────────┴──────────┐
          ▼                     ▼
       MongoDB            StorageService
```

- **Database**: MongoDB 7.0 (Primary document store & task queue state — native async PyMongo `AsyncMongoClient`)
- **API Framework**: FastAPI (Async REST API & Web Dashboard)
- **Telegram Bot**: aiogram 3.x
- **Storage Engine**: Pluggable storage abstraction with path-traversal protection and streaming chunked I/O
- **Background Worker**: Asynchronous queue processor with lock heartbeat renewal and automatic stale recovery
- **Containerization**: Docker & Docker Compose

---

## Web Dashboard & Browser Access

The Web Dashboard allows authenticated users to browse, search, organize, inspect, safely delete, retry, and download their Telegram backups directly from a web browser.

### 🌐 Access URLs
- **Web Dashboard**: `http://localhost:8000/` or `http://localhost:8000/dashboard`
- **Login Page**: `http://localhost:8000/login`
- **Interactive OpenAPI Docs (Swagger)**: `http://localhost:8000/docs`

### 🔐 Authentication Options
1. **Telegram Bot One-Time Code**:
   - Send `/login` or `/web` to the Telegram Bot.
   - Enter the generated 6-digit one-time code on the login page.
   - Single-use, atomically consumed, and rate-limited against brute-force attempts.
2. **Telegram WebApp / Widget**:
   - Seamless auto-login when opening the dashboard from Telegram Mini Apps.
   - Authenticated via official HMAC-SHA-256 signature verification using the bot token.
3. **Session Security**:
   - Server-side sessions stored as SHA-256 hashes in MongoDB `web_sessions`.
   - Issued via `HttpOnly`, `SameSite=Lax`, and `Secure` (production) cookies.

---

## REST API Endpoints

### 🔑 Authentication (`/api/auth`)
| Method | Endpoint | Description | Auth Required |
|---|---|---|---|
| `POST` | `/api/auth/token` | Log in with single-use 6-digit bot code | No |
| `POST` | `/api/auth/telegram` | Log in with Telegram WebApp / Widget data | No |
| `POST` | `/api/auth/dev-login` | Quick development login (disabled in production) | No |
| `GET` | `/api/auth/me` | Get current authenticated user profile | Yes |
| `POST` | `/api/auth/logout` | Revoke session and clear cookies | Yes |

### 📁 Backup Files (`/api/files`)
| Method | Endpoint | Description | Auth Required |
|---|---|---|---|
| `GET` | `/api/files` | Paginated file browsing with status & folder filters | Yes |
| `GET` | `/api/files/{id}` | Detailed file metadata and tags | Yes |
| `DELETE` | `/api/files/{id}` | Safe file deletion (soft-delete + physical storage removal + usage decrement) | Yes |
| `POST` | `/api/files/{id}/retry` | Re-queue failed backup task | Yes |
| `POST` | `/api/files/{id}/move` | Move file to a destination folder or root | Yes |
| `GET` | `/api/files/{id}/tags` | List tags attached to file | Yes |
| `POST` | `/api/files/{id}/tags` | Attach tag to file | Yes |
| `DELETE` | `/api/files/{id}/tags/{tag_id}` | Detach tag from file | Yes |
| `GET` | `/api/files/{id}/download` | Safe streaming file download via `StorageService` | Yes |

### 🔍 Search (`/api/search`)
| Method | Endpoint | Description | Auth Required |
|---|---|---|---|
| `GET` | `/api/search?q={query}` | Regex-safe user-scoped search across filenames, captions, and MIME types | Yes |

### 📂 Folders (`/api/folders`)
| Method | Endpoint | Description | Auth Required |
|---|---|---|---|
| `GET` | `/api/folders` | List user folders | Yes |
| `POST` | `/api/folders` | Create a new folder | Yes |
| `GET` | `/api/folders/{id}` | Get folder details | Yes |
| `DELETE` | `/api/folders/{id}` | Delete folder (safely unassigns contained files to root) | Yes |

### 🏷 Tags (`/api/tags`)
| Method | Endpoint | Description | Auth Required |
|---|---|---|---|
| `GET` | `/api/tags` | List all user tags | Yes |
| `POST` | `/api/tags` | Create/ensure a normalized tag | Yes |
| `DELETE` | `/api/tags/{id}` | Delete tag and associations | Yes |
| `GET` | `/api/tags/{id}/files` | List active files associated with tag | Yes |

### 📊 Statistics (`/api/stats`)
| Method | Endpoint | Description | Auth Required |
|---|---|---|---|
| `GET` | `/api/stats` | Storage accounting and status breakdown (`completed`, `processing`, `pending`, `failed`) | Yes |

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
# Build and start all 4 services (mongodb, api, bot, worker)
docker compose up -d --build

# Check running containers
docker compose ps

# View logs
docker compose logs -f api
```

### 4. Running Tests

```bash
# Run full automated test suite (138 tests)
pytest -v
```

---

## Production Hardening & Operational Runbooks (Phase 8)

Phase 8 elevates Telegram Backup Bot to a fully production-hardened, observable, reliable, and recoverable architecture.

### 📚 Operational & Security Documentation
- [Production Architecture](file:///home/icecube/ASUS/Telegram-backup-bot/docs/PRODUCTION_ARCHITECTURE.md)
- [Production Deployment Checklist](file:///home/icecube/ASUS/Telegram-backup-bot/docs/DEPLOYMENT_CHECKLIST.md)
- [Disaster Recovery & Backup Guide](file:///home/icecube/ASUS/Telegram-backup-bot/docs/DISASTER_RECOVERY.md)
- [Operations & Troubleshooting Runbook](file:///home/icecube/ASUS/Telegram-backup-bot/docs/OPERATIONS.md)
- [Security Architecture & Policies](file:///home/icecube/ASUS/Telegram-backup-bot/docs/SECURITY.md)

---

## 🛠 Administrative & Maintenance CLI Commands

All administrative tools default to safe **DRY RUN** (read-only) mode.

### 1. Storage Reconciliation
Compares MongoDB active backup records with physical files on disk:
```bash
# Dry run analysis
python -m app.scripts.reconcile_storage

# Repair storage accounting drift to match active items
python -m app.scripts.reconcile_storage --repair

# Conservative orphan deletion (requires explicit --confirm)
python -m app.scripts.reconcile_storage --repair --delete-orphans --confirm
```

### 2. Referential Integrity Audit
Audits database integrity across users, items, tasks, folders, and tags:
```bash
# Dry run audit
python -m app.scripts.integrity_check

# Apply safe repairs (unassign missing folders, clean orphaned item-tags)
python -m app.scripts.integrity_check --repair
```

### 3. Stale Temporary Downloads Cleanup
Purges stale in-flight download chunks older than the specified age:
```bash
python -m app.scripts.cleanup_temp --max-age-hours 1.0
```

### 4. Health Smoke Test
Verifies database connectivity, disk space capacity, and API service status:
```bash
python -m app.scripts.healthcheck
```

### 5. Automated Backups & Restore
```bash
# Backup MongoDB database (compressed archive with retention cleanup)
./scripts/backup_mongodb.sh

# Restore MongoDB from archive (requires explicit confirmation)
./scripts/restore_mongodb.sh backups/mongodb/mongo_backup_YYYYMMDD_HHMMSS.archive.gz --confirm

# Backup physical file storage
./scripts/backup_storage.sh

# Verify backup archive integrity
python -m app.scripts.verify_backup backups/mongodb/mongo_backup_YYYYMMDD_HHMMSS.archive.gz
```

---

## Development Phases Roadmap

- [x] **Phase 1: Foundation** (Async PyMongo manager, Config, Logging, Liveness/Readiness Probes, Docker, Tests)
- [x] **Phase 2: MongoDB Models & Repositories** (Task queue claiming, Compound indexes, Ownership isolation, Soft deletion)
- [x] **Phase 3: Storage Engine** (StorageService, LocalStorageService, Path traversal defense, Streaming I/O)
- [x] **Phase 4: Telegram Bot Ingestion** (aiogram 3.x media extractors, User middleware, Deduplication)
- [x] **Phase 5: Background Download Worker** (Streaming download, Incremental SHA-256, Lock renewal, Stale recovery)
- [x] **Phase 6: Backup Management & User Experience** (Bot file pagination, Safe deletion, Search, Folders, Tags, Stats)
- [x] **Phase 7: Web Dashboard & REST API** (Browser interface, Hashed session security, Streaming downloads, REST APIs)
- [x] **Phase 8: Production Hardening & Disaster Recovery** (TTL cleanups, Security headers, CSP, Rate limits, Storage reconciliation, Integrity checks, DR & Backups)
- [x] **Phase 9: Production Deployment & Release Validation** (Nginx TLS reverse proxy, Preflight validation, Automated smoke tests, Container healthchecks)
- [x] **Phase 10: 4 GiB Large File Support** (Hybrid Bot API $\le$ 20 MiB + MTProto $>$ 20 MiB up to 4 GiB, Telethon chunked streaming, Resumable downloads, $O(1)$ memory, SHA-256 rebuild)

