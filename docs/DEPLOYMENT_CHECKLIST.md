# Production Deployment Checklist

Use this checklist before and after deploying Telegram Backup Bot to a staging or production server.

---

## 1. Pre-Deployment Infrastructure & Security

- [ ] **Domain & DNS**: DNS A/AAAA records point to the reverse proxy public IP.
- [ ] **TLS / SSL**: Valid SSL certificates installed (e.g. Let's Encrypt / Certbot).
- [ ] **Docker & Compose**: Docker Engine 24+ and Docker Compose v2 installed on the host.
- [ ] **Non-Root Container User**: Containers execute as unprivileged user `appuser` (UID/GID 10001).
- [ ] **Host Storage Permissions**: Storage directory (`/app/storage` or host mount) is writable by `appuser` (`chmod 750` / `chown 10001:10001`).
- [ ] **Firewall & Ports**:
  - Open: `80/tcp` (HTTP redirect) and `443/tcp` (HTTPS).
  - Blocked: `27017/tcp` (MongoDB must NEVER be publicly exposed).

---

## 2. Environment Variables & Secret Configuration

Generate cryptographically secure secrets:
```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Verify in `.env`:
- [ ] `ENVIRONMENT=production`
- [ ] `DEBUG=false`
- [ ] `BOT_TOKEN`: Valid Telegram bot token from @BotFather (`<bot_id>:<token_secret>`).
- [ ] `WEB_SESSION_SECRET`: High-entropy string (>= 32 characters, no placeholders).
- [ ] `SECRET_KEY`: Custom secret (not default placeholder).
- [ ] `JWT_SECRET`: Custom secret (not default placeholder).
- [ ] `MONGODB_URI`: Points to internal MongoDB container (`mongodb://mongodb:27017`).
- [ ] `WEB_COOKIE_SECURE=true`.
- [ ] `WEB_BASE_URL`: Fully qualified HTTPS URL (`https://backup.example.com`).

---

## 3. Launch & Verification Sequence

1. **Validate Compose Configuration**:
   ```bash
   docker compose -f docker-compose.prod.yml config
   ```
2. **Build and Start Production Stack**:
   ```bash
   docker compose -f docker-compose.prod.yml up -d --build
   ```
3. **Verify Container Health**:
   ```bash
   docker compose -f docker-compose.prod.yml ps
   ```
   All services (`mongodb`, `api`, `bot`, `worker`) must report `healthy` or `running`.
4. **Run Smoke Test Script**:
   ```bash
   docker compose -f docker-compose.prod.yml exec api python -m app.scripts.healthcheck
   ```
   Must output: `Overall Status: ✅ HEALTHY`.

---

## 4. End-to-End Functional Smoke Test

- [ ] **API Liveness Probe**: `curl -f https://backup.example.com/health/live` returns HTTP 200 `{"status": "alive"}`.
- [ ] **API Readiness Probe**: `curl -f https://backup.example.com/health/ready` returns HTTP 200 `{"status": "ready"}`.
- [ ] **Dashboard Load**: Open `https://backup.example.com/` in a browser. Verifies clean dark glassmorphism UI loads.
- [ ] **Dev-Login Rejection**: Verify `POST /api/auth/dev-login` returns HTTP 403 Forbidden.
- [ ] **Telegram Bot Ingestion**: Send a photo or document to the bot. Confirm confirmation reply in Telegram.
- [ ] **Worker Processing**: Verify worker logs show task claimed, downloaded, and completed.
- [ ] **Dashboard File Inspection**: Refresh dashboard. Confirm uploaded file is listed.
- [ ] **Authenticated Download**: Click "Download" in web dashboard. Confirm file streams with correct Content-Disposition header.
- [ ] **Tagging & Folders**: Create a folder, move file to folder, assign tag. Confirm metadata updates.
- [ ] **Safe Deletion**: Delete file from dashboard. Confirm physical storage deletion and usage accounting decrement.
- [ ] **Automated Backups**: Run `scripts/backup_mongodb.sh` and `scripts/backup_storage.sh` to confirm initial backup archives are created.
