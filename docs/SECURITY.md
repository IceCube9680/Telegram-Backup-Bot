# Security Architecture & Policies

This document details the security posture, authentication protocols, defense-in-depth measures, and operational constraints for Telegram Backup Bot.

---

## 1. Authentication & Session Security

1. **Hashed Server-Side Sessions**:
   - Random 48-byte URL-safe session tokens are generated during login.
   - The plain token is sent ONLY to the browser in an `HttpOnly`, `SameSite=Lax`, `Secure` cookie.
   - The database stores only the one-way `SHA-256(token)` hash. If the database is compromised, active session tokens cannot be reverse-engineered.
   - Sessions expire automatically via MongoDB TTL index on `expires_at`.

2. **One-Time 6-Digit Login Codes**:
   - Users generate temporary 6-digit numeric login codes via `/login` or `/web` Telegram commands.
   - Tokens are single-use and consumed atomically via MongoDB `find_one_and_update`.
   - Concurrency protection ensures simultaneous redemption requests with the same code authenticate exactly once.
   - Brute-force protection locks codes after 5 failed attempts.

3. **Telegram WebApp / Widget HMAC Verification**:
   - Validates initData and widget signatures using HMAC-SHA-256 with `SHA256(bot_token)`.
   - Validates `auth_date` freshness to reject replay attacks.

4. **Dev Login Prohibition**:
   - `POST /api/auth/dev-login` is strictly restricted to development/testing environments and returns `403 Forbidden` whenever `ENVIRONMENT=production`.

---

## 2. Authorization & Multi-User Isolation

- **Query-Level Enforcement**: Every database query for files, folders, tags, statistics, and tasks enforces `{"user_id": current_user_id}`.
- **Cross-User Download Protection**: `GET /api/files/{id}/download` resolves the item through `item_repo.get_by_id(user_id=current_user_id, item_id=id)` before touching physical storage.
- **Storage Directory Scoping**: Backups are partitioned under `storage/users/{user_id}/`.

---

## 3. Storage & Filesystem Defense

- **Path Traversal Protection**: `LocalStorageService` resolves all paths and strictly asserts `storage_path in resolved_path.parents`. Traversal payloads (`../`, `..\`, absolute paths, null bytes) raise immediate `StoragePathTraversalError`.
- **Stream Memory Safety**: File downloads and uploads stream in 64 KiB chunks, keeping memory consumption constant regardless of file size.
- **Conservative Maintenance**: Storage reconciliation defaults to read-only reporting and only deletes orphan files inside user-managed directories when `--delete-orphans` AND `--confirm` are both passed.

---

## 4. HTTP Security Headers & Content Security Policy (CSP)

The following headers are attached to every API response via `SecurityHeadersMiddleware`:

| Header | Value | Purpose |
| :--- | :--- | :--- |
| `X-Content-Type-Options` | `nosniff` | Prevents MIME-type sniffing attacks |
| `X-Frame-Options` | `DENY` | Prevents Clickjacking |
| `Referrer-Policy` | `strict-origin-when-cross-origin` | Protects referrer leakage |
| `Permissions-Policy` | `geolocation=(), camera=(), microphone=()` | Restricts browser hardware features |
| `Content-Security-Policy` | `default-src 'self'; script-src 'self' 'unsafe-inline' https://telegram.org; ...` | Prevents XSS and unauthorized resource loading |
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains` | Enforces HTTPS on modern browsers |

---

## 5. Rate Limiting & Denial-of-Service Defense

- In-memory sliding window rate limiter protects sensitive endpoints (`/api/auth/*`, `/api/search`, `/api/files/{id}/download`, `/api/files/{id}` DELETE).
- *Limitation*: Designed for single-instance baselines. Horizontal scaling requires reverse-proxy rate limiting (Nginx) or Redis in future phases.

---

## 6. Secret Management & Logging Privacy

- Production startup enforces non-empty, strong secrets (`BOT_TOKEN`, `WEB_SESSION_SECRET`, `SECRET_KEY`, `JWT_SECRET`).
- Logs are strictly sanitized: secrets, bot tokens, session tokens, passwords, and authorization headers are never logged.
