# Telegram Backup Bot — Production Release Checklist

Use this exhaustive pre-flight and release checklist before deploying new releases or promoting to production.

---

## 1. Host & Server Infrastructure

- [ ] Operating System packages updated (`apt update && apt upgrade -y`).
- [ ] Non-root execution user configured (`appuser`).
- [ ] Docker engine installed and running (`docker --version` $\ge 24$).
- [ ] Docker Compose plugin available (`docker compose version` $\ge 2$).
- [ ] Firewall (UFW) active: only ports `80` (HTTP) and `443` (HTTPS) exposed.
- [ ] Port `27017` (MongoDB) is **NOT** exposed to public interface.
- [ ] Disk capacity verified ($\ge 20\%$ free, below 80% warning threshold).

---

## 2. Secrets & Configuration Hygiene

- [ ] `.env` file created from `.env.example` with strict file permissions (`chmod 600 .env`).
- [ ] `ENVIRONMENT=production` is set.
- [ ] `DEBUG=false` is enforced.
- [ ] Telegram `BOT_TOKEN` validated with correct format (`<digits>:<secret>`).
- [ ] `WEB_SESSION_SECRET` generated with $\ge 32$ high-entropy random characters (`openssl rand -hex 32`).
- [ ] `SECRET_KEY` and `JWT_SECRET` changed from insecure placeholders.
- [ ] `WEB_COOKIE_SECURE=true` enabled for HTTPS session cookies.
- [ ] No `.env` files, credentials, or private keys committed to Git repository (`git status`).

---

## 3. Database (MongoDB)

- [ ] Dedicated persistent volume `mongo_prod_data` configured.
- [ ] Unique and compound indexes verified on startup (`ensure_indexes`).
- [ ] TTL index active on `web_sessions.expires_at` (`expireAfterSeconds=0`).
- [ ] TTL index active on `login_tokens.expires_at` (`expireAfterSeconds=0`).
- [ ] Automated database backup script tested (`scripts/backup_mongodb.sh`).
- [ ] Isolated database restoration drill verified (`scripts/restore_mongodb.sh`).

---

## 4. Local File Storage

- [ ] Storage volume `app_prod_storage` mounted to `/app/storage`.
- [ ] Directory permissions verified for `appuser`.
- [ ] Path traversal protections active (`LocalStorageService.validate_storage_key`).
- [ ] Automated storage backup script tested (`scripts/backup_storage.sh`).
- [ ] Stale download temporary files cleanup tested (`cleanup_stale_temp_files`).
- [ ] Disk capacity monitoring operational (`/health`).

---

## 5. Reverse Proxy & HTTPS (Nginx)

- [ ] DNS A/AAAA records resolving to VPS public IP.
- [ ] Valid Let's Encrypt TLS certificate installed (`fullchain.pem`, `privkey.pem`).
- [ ] HTTP port `80` redirects with 301/308 to HTTPS port `443`.
- [ ] Modern TLS protocols enabled (`TLSv1.2`, `TLSv1.3`).
- [ ] Security headers attached (`nosniff`, `DENY`, strict CSP, `X-Request-ID`).
- [ ] `proxy_buffering off` enabled for streaming downloads.
- [ ] Certbot auto-renewal timer tested (`certbot renew --dry-run`).

---

## 6. Telegram Bot & Worker Daemon

- [ ] Single bot polling process running (`python -m app.bot.bot`).
- [ ] Background worker process active (`python -m app.workers.worker`).
- [ ] Worker does NOT run Telegram update polling.
- [ ] Worker concurrency configured (`WORKER_CONCURRENCY=4`).
- [ ] Worker heartbeat renewal loop verified (`renew_lock`).
- [ ] Stale crashed task recovery verified (`recover_stale_tasks`).

---

## 7. Web Dashboard & Security Isolation

- [ ] Web dashboard login operational (`/login`).
- [ ] One-time 6-digit Telegram login codes verified.
- [ ] Dev-login endpoint strictly disabled in production (`POST /api/auth/dev-login` $\to 403$).
- [ ] Rate limiting active on authentication and download routes.
- [ ] Cross-user tenant isolation verified: User A cannot access User B's files/folders/tags.

---

## 8. Rollback & Disaster Recovery

- [ ] Rollback procedure tested (`scripts/rollback.sh`).
- [ ] Last known-good image tag documented.
- [ ] MongoDB backup archive verified (`python -m app.scripts.verify_backup`).
- [ ] Runbooks reviewed (`docs/DEPLOYMENT_RUNBOOK.md`, `docs/ROLLBACK.md`).

---

## 9. Final Release Sign-Off

- [ ] Preflight check passed (`bash scripts/preflight.sh`).
- [ ] Smoke test passed (`bash scripts/smoke_test.sh`).
- [ ] Full pytest suite passed (`189/189 passed, 0 failures`).
- [ ] Release approved for production deployment.
