# Production Rollback & Recovery Procedures

This guide specifies the exact protocol for rolling back application versions and recovering from failed releases.

---

## 1. Core Rollback Policy

> [!IMPORTANT]
> 1. **Application Rollback $\ne$ Database Restore**:
>    Application rollbacks revert container application code (FastAPI, Bot, Worker). They do **NOT** and must **NOT** automatically wipe or restore database state unless explicit data corruption occurred.
> 2. **Never delete volumes**:
>    Rollback commands must never execute `docker compose down -v` or delete `mongo_prod_data` / `app_prod_storage`.
> 3. **Avoid destructive git operations**:
>    Do not use `git reset --hard` or `git checkout` on production servers to avoid discarding uncommitted environment configs or local patches.

---

## 2. Standard Application Rollback Workflow

```text
    1. Incident Triggered (Failed release / Critical bug)
                         │
                         ▼
    2. Execute Rollback Script (scripts/rollback.sh <TAG> --confirm)
                         │
                         ▼
    3. Stop Current Application Containers (api, bot, worker)
                         │
                         ▼
    4. Deploy Previous Known-Good Immutable Container Image
                         │
                         ▼
    5. Health Check & Database Readiness Probe Validation
                         │
                         ▼
    6. Execute Smoke Test Suite (scripts/smoke_test.sh)
                         │
                         ▼
    7. Incident Post-Mortem & Log Analysis
```

### Execution Command:
```bash
# Rollback to specific known-good release tag
bash scripts/rollback.sh v0.1.0 --confirm
```

---

## 3. Database Disaster Recovery (When Data Corruption Occurs)

If a failed deployment executed incompatible database schema migrations or corrupted MongoDB documents, follow the isolated database restoration procedure:

1. **Create emergency snapshot of current state before restore**:
   ```bash
   bash scripts/backup_mongodb.sh
   ```

2. **Verify target restore archive integrity**:
   ```bash
   python -m app.scripts.verify_backup backups/mongodb/mongo_backup_PRE_RELEASE.archive.gz
   ```

3. **Execute database restore**:
   ```bash
   bash scripts/restore_mongodb.sh backups/mongodb/mongo_backup_PRE_RELEASE.archive.gz --confirm
   ```

4. **Verify MongoDB collections & indexes**:
   ```bash
   docker compose -f docker-compose.prod.yml exec api python -m app.scripts.integrity_check
   ```

5. **Restart application services**:
   ```bash
   docker compose -f docker-compose.prod.yml restart api bot worker
   bash scripts/smoke_test.sh
   ```
