# Production Architecture Specification

This document details the production architecture, components, networking, failure modes, and recovery paths for the Telegram Backup Bot system.

---

## 1. High-Level Architecture

```text
                                INTERNET
                                   │
                                   ▼
                         [ Reverse Proxy / TLS ]
                         (Nginx / HTTPS:443 / HSTS)
                                   │
                    ┌──────────────┴──────────────┐
                    │ (HTTP / X-Request-ID)       │ (Webhook or Polling)
                    ▼                             ▼
             [ FastAPI REST / Web ]        [ Telegram Bot ]
             - Glassmorphic Dashboard      - aiogram 3.x
             - Hashed Session Auth         - Ingestion Middleware
             - Rate Limiting Middleware    - Media Categorization
             - User Isolation Guard        - Task Queue Producer
                    │                             │
                    └──────────────┬──────────────┘
                                   │
                                   ▼
                       [ Core Service Layer ]
          ┌────────────────────────┼────────────────────────┐
          ▼                        ▼                        ▼
  [ BackupManagement ]     [ Folder & Tag ]         [ SearchService ]
          │                        │                        │
          └────────────────────────┼────────────────────────┘
                                   ▼
                       [ Asynchronous Worker ]
                       - Atomic Task Claiming
                       - Chunked Streaming & SHA-256
                       - Stale Lease Recovery
                       - Heartbeat Lock Renewal
                                   │
                    ┌──────────────┴──────────────┐
                    ▼                             ▼
          [ MongoDB Cluster / 7.0 ]     [ LocalStorageService ]
          - Repositories & Indexes      - User-Scoped Directories
          - TTL Automated Cleanups      - Non-Root Isolation
          - Internal Docker Network     - Path Traversal Defense
                    │                             │
                    ▼                             ▼
          [ Database Backups ]          [ Storage Backups ]
          - mongodump (.archive.gz)     - tar / rsync (.tar.gz)
          - Verified Restores           - Daily Retention Policy
```

---

## 2. Ingestion & Asynchronous Processing Pipeline

```text
Telegram User
    │
    ▼ (sends photo / video / document / audio / voice)
Telegram Servers
    │
    ▼ (getUpdates / Polling)
aiogram Bot Dispatcher
    │
    ▼ (UserMiddleware: upserts user, verifies active status)
Media Extraction & Validation (file size, MIME type, caption)
    │
    ▼ (Atomic MongoDB Transaction)
Create BackupItem (status: 'pending') + Create BackupTask (status: 'pending')
    │
    ▼
Task Queue (MongoDB collection 'backup_tasks')
    │
    ▼ (Atomic find_one_and_update lock: status='processing', worker_id=...)
Backup Worker (TaskProcessor)
    │
    ├─► Heartbeat Loop (renews lock lease every 30s)
    │
    ├─► Capacity Check (verifies available disk space >= required buffer)
    │
    ├─► TelegramDownloader (streams chunked binary from Telegram API to .tmp-downloads)
    │   └─► Incremental SHA-256 computation
    │
    ├─► LocalStorageService.upload (writes to users/{user_id}/{sha256}.{ext})
    │
    ├─► BackupItemRepository (updates storage_key, sha256, status='completed')
    │
    ├─► StorageUsageRepository (atomic $inc total_files & total_size)
    │
    └─► BackupTaskRepository (marks task 'completed', releases worker lock)
```

---

## 3. Web Dashboard & REST API Flow

```text
Web Browser / Telegram WebApp
    │
    ▼ (HTTPS Request with X-Request-ID)
Reverse Proxy (Nginx)
    │
    ▼
FastAPI Application
    │
    ├─► SecurityHeadersMiddleware (CSP, X-Frame-Options, X-Content-Type-Options)
    ├─► RequestIDMiddleware (Extracts or generates UUID4, attaches to log context & response)
    ├─► RateLimiter (In-memory sliding window per IP)
    │
    ├─► Auth Routes:
    │   ├─► POST /api/auth/token (Atomic single-use 6-digit code consumption with brute-force lock)
    │   ├─► POST /api/auth/telegram (HMAC-SHA256 signature verification)
    │   └─► POST /api/auth/dev-login (Strictly 403 Forbidden in production)
    │
    ├─► File Management Routes:
    │   ├─► GET /api/files (User-scoped pagination & filtering)
    │   ├─► GET /api/files/{id}/download (Ownership verification & chunked stream via StorageService)
    │   ├─► DELETE /api/files/{id} (Soft-delete DB record + delete physical file + decrement usage)
    │   └─► POST /api/files/{id}/retry (Re-queues failed tasks for worker)
    │
    └─► Health Probes:
        ├─► /health/live (Process liveness)
        ├─► /health/ready (MongoDB connection readiness)
        └─► /health (Combined health + disk space capacity metrics)
```

---

## 4. Disaster Recovery & Maintenance Subsystem

```text
                    Maintenance / CLI Layer
                               │
            ┌──────────────────┼──────────────────┐
            ▼                  ▼                  ▼
  [ reconcile_storage ] [ integrity_check ] [ cleanup_temp ]
            │                  │                  │
    (Dry-run by default) (Dry-run by default) (Age-based > 1h)
            │                  │                  │
   - Missing DB files   - Dangling folders  - Stale chunks
   - Orphan disk files  - Orphan item-tags  - Temp downloads
   - Storage usage sync - Ambiguous state
```

---

## 5. Architectural Boundaries & Constraints

1. **Storage Isolation**: The web API and Telegram bot never access the raw filesystem directly; all I/O must pass through `StorageService`.
2. **User Ownership**: Every database query on files, folders, tags, tasks, and storage usage enforces `{"user_id": current_user_id}`.
3. **Task Atomicity**: Tasks are claimed using MongoDB atomic `find_one_and_update`, preventing multiple workers from executing the same task.
4. **Single-Instance In-Memory Rate Limiting**: The built-in rate limiter is designed for single-instance baselines. Horizontal multi-instance setups should configure reverse-proxy rate limiting or distributed Redis in future phases.
