# Operations & Maintenance Runbook

This runbook describes routine administration commands, troubleshooting workflows, secret rotation, and operational procedures for Telegram Backup Bot.

---

## 1. Routine Operational Commands

All maintenance CLI tools default to **DRY RUN (read-only)** mode.

### Storage Reconciliation
Scan and compare MongoDB records with physical disk storage:
```bash
# Dry run analysis (safe, zero modifications)
python -m app.scripts.reconcile_storage

# Repair storage accounting drift to match active items
python -m app.scripts.reconcile_storage --repair

# Conservative orphan deletion (requires explicit confirm)
python -m app.scripts.reconcile_storage --repair --delete-orphans --confirm
```

### Referential Integrity Audit
Audit cross-collection references (`BackupItem ↔ Folder`, `ItemTag ↔ Tag`, `User ↔ StorageUsage`):
```bash
# Dry run audit
python -m app.scripts.integrity_check

# Safe repair (unassign missing folders, clean orphaned item-tags)
python -m app.scripts.integrity_check --repair
```

### Temporary Download Files Cleanup
Clean stale download chunks older than 1 hour:
```bash
python -m app.scripts.cleanup_temp --max-age-hours 1.0
```

### Healthcheck Smoke Test
Run full application dependency check:
```bash
python -m app.scripts.healthcheck
```

---

## 2. Troubleshooting & Recovery Procedures

### Scenario A: Worker is Stuck or Container Crashed
If a worker crashes while processing a task:
1. The task remains in `processing` status with a `locked_at` timestamp.
2. The active worker heartbeat loop keeps leases refreshed during normal operation.
3. If the worker stops renewing, the stale task recovery mechanism automatically unlocks tasks whose lease exceeded `WORKER_LOCK_TIMEOUT` (default: 300s) and resets them to `pending` with exponential retry backoff.
4. To manually inspect or restart worker:
   ```bash
   docker compose logs --tail=100 worker
   docker compose restart worker
   ```

### Scenario B: Disk Space Nearly Full (>= 80% Warning, >= 90% Critical)
1. Check disk status via healthcheck:
   ```bash
   python -m app.scripts.healthcheck
   ```
2. Clean stale temporary downloads:
   ```bash
   python -m app.scripts.cleanup_temp --max-age-hours 0.5
   ```
3. Run storage reconciliation to clean confirmed orphan files:
   ```bash
   python -m app.scripts.reconcile_storage --repair --delete-orphans --confirm
   ```
4. Archive or prune old database backups in `backups/`.

### Scenario C: MongoDB Outage or Restart
1. The FastAPI app and Worker automatically attempt to reconnect upon transient database unavailability.
2. Check MongoDB logs:
   ```bash
   docker compose logs --tail=100 mongodb
   ```
3. Restart MongoDB service if unresponsive:
   ```bash
   docker compose restart mongodb
   ```

### Scenario D: Telegram API Rate Limiting (HTTP 429 / FloodWait)
1. aiogram and `TaskProcessor` categorize rate limits as retryable errors.
2. The worker automatically calculates exponential backoff with jitter and re-queues the task with increased delay up to `WORKER_RETRY_MAX_DELAY`.

---

## 3. Secret Rotation Procedures

### Rotating `WEB_SESSION_SECRET`
1. Generate new session secret:
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(48))"
   ```
2. Update `WEB_SESSION_SECRET` in `.env`.
3. Restart API service:
   ```bash
   docker compose -f docker-compose.prod.yml restart api
   ```
4. **Impact**: Existing active sessions remain valid in MongoDB (since sessions are stored as raw SHA-256 hashes of the random token issued to the client). Invalidate all existing sessions if required by deleting documents in `web_sessions` collection.

### Rotating Telegram `BOT_TOKEN`
1. Request new token from @BotFather.
2. Update `BOT_TOKEN` in `.env`.
3. Restart Bot and Worker services:
   ```bash
   docker compose -f docker-compose.prod.yml restart bot worker api
   ```
