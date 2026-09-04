# Telegram Backup Bot — Production Operations & Deployment Runbook

This runbook provides standardized operational procedures and commands for managing the Telegram Backup Bot in production environments.

---

## 🟢 SAFE OPERATIONS

Safe operations do not disrupt running user traffic, corrupt database state, or modify persistent storage.

### 1. Production Preflight Check
Verify system prerequisites, disk capacity, secrets format, and compose definitions:
```bash
bash scripts/preflight.sh
```

### 2. View Service Status
Check all running container processes, uptime, and healthcheck status:
```bash
docker compose -f docker-compose.prod.yml ps
```

### 3. Real-Time Log Inspection
Monitor service logs with request correlation IDs and structured logs:
```bash
# Follow API backend logs
docker compose -f docker-compose.prod.yml logs -f --tail=100 api

# Follow Telegram Bot polling logs
docker compose -f docker-compose.prod.yml logs -f --tail=100 bot

# Follow Download Worker daemon logs
docker compose -f docker-compose.prod.yml logs -f --tail=100 worker

# Follow MongoDB database logs
docker compose -f docker-compose.prod.yml logs -f --tail=50 mongodb
```

### 4. Health Probes
```bash
# Check process liveness
curl -fsS http://127.0.0.1:8000/health/live

# Check database readiness
curl -fsS http://127.0.0.1:8000/health/ready

# Check combined application and disk health
curl -fsS http://127.0.0.1:8000/health | jq .
```

### 5. Automated Production Smoke Tests
```bash
bash scripts/smoke_test.sh
```

### 6. Automated Scheduled Backups
```bash
# Backup MongoDB database (with automatic archive verification)
bash scripts/backup_mongodb.sh

# Backup Storage directory
bash scripts/backup_storage.sh
```

### 7. Storage Health & Referential Integrity Audits (Dry Run)
```bash
# Audit MongoDB references vs physical storage files (DRY RUN)
docker compose -f docker-compose.prod.yml exec api python -m app.scripts.reconcile_storage

# Audit collection referential integrity (DRY RUN)
docker compose -f docker-compose.prod.yml exec api python -m app.scripts.integrity_check
```

---

## 🟡 ELEVATED OPERATIONS

Elevated operations may temporarily restart services or modify non-critical state.

### 1. Standard Production Deployment
Idempotent build, migration check, service restart, and smoke test:
```bash
bash scripts/deploy.sh
```

### 2. Graceful Service Restarts
```bash
# Restart API without restarting database or storage
docker compose -f docker-compose.prod.yml restart api

# Restart Worker
docker compose -f docker-compose.prod.yml restart worker

# Restart Telegram Bot
docker compose -f docker-compose.prod.yml restart bot
```

### 3. Application Rollback
Roll back container images to a previous known-good tag:
```bash
# Usage: bash scripts/rollback.sh <IMAGE_TAG_OR_VERSION> [--confirm]
bash scripts/rollback.sh v0.1.0 --confirm
```

### 4. Provision MTProto Session for Large Files (Phase 10)
Authenticate dedicated Telegram account for MTProto large file transfers:
```bash
python3 scripts/create_mtproto_session.py
chmod 0600 secrets/mtproto_worker.session
docker compose -f docker-compose.prod.yml restart worker
```

---

## 🔴 DESTRUCTIVE OPERATIONS (REQUIRE CONFIRMATION)

> [!CAUTION]
> Destructive operations can cause downtime, overwrite live database collections, or delete orphaned files. **Never execute without an explicit backup and operator approval.**

### 1. Database Restoration from Backup
Restores MongoDB from a compressed mongodump archive (drops existing collections):
```bash
# Interactive confirmation required
bash scripts/restore_mongodb.sh backups/mongodb/mongo_backup_20260904_120000.archive.gz

# Automated / non-interactive (only in disaster recovery scripts)
bash scripts/restore_mongodb.sh backups/mongodb/mongo_backup_20260904_120000.archive.gz --confirm
```

### 2. Storage Orphan Cleanup
Permanently deletes unreferenced files on disk:
```bash
# Requires both flags for physical deletion
docker compose -f docker-compose.prod.yml exec api python -m app.scripts.reconcile_storage --delete-orphans --confirm
```

### 3. Full Service Teardown (NEVER use `-v` in normal operations)
```bash
# Stop containers (preserves all data volumes)
docker compose -f docker-compose.prod.yml down

# WARNING: NEVER run 'docker compose down -v' as it permanently deletes MongoDB data
```
