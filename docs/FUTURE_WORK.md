# Future Architecture & Enhancements Beyond Phase 9

This document records architectural proposals and advanced capabilities that were deliberately excluded from Phase 9 to maintain system simplicity, rock-solid stability, zero-external-dependency posture, and strict focus on release readiness.

---

## 1. Remote Object Storage (S3 / Cloud Storage Backend)

* **Current Architecture**: Local filesystem storage with atomic file streams, path traversal protection, and SHA-256 deduplication via `LocalStorageService`.
* **Proposed Enhancement**:
  * S3-compatible multi-region backend (AWS S3, Cloudflare R2, MinIO, Wasabi).
  * Direct pre-signed upload/download URLs with expiration to offload bandwidth from the FastAPI application.
  * Multi-tier lifecycle policies (e.g., Glacier archiving for old backups).

---

## 2. Distributed Caching & Multi-Instance Rate Limiting (Redis / KeyDB)

* **Current Architecture**: Process-local in-memory sliding-window rate limiter and MongoDB atomic state management (`$inc`, atomic find-and-modify).
* **Proposed Enhancement**:
  * Distributed token-bucket / sliding-log rate limiter backed by Redis across multiple horizontally scaled FastAPI replica instances.
  * Shared distributed locks using Redlock algorithm for multi-node deployments.

---

## 3. Large File Support (Phase 10 Implemented & Future Re-Upload Scope)

* **Phase 10 Ingestion Status (Completed)**:
  * Hybrid Bot API ($\le$ 20 MiB) + MTProto ($>$ 20 MiB up to 4 GiB) download pipeline implemented using Telethon client manager.
  * Constant $O(1)$ memory streaming, resumable `.part` transfers, incremental SHA-256 rebuild, and pre-flight disk headroom checks.
  * Authenticated web streaming download up to 4 GiB.
* **Proposed Future Enhancement — 4 GiB Telegram Re-Upload**:
  * Currently, the system supports uploading backups to storage and streaming stored 4 GiB files to the authenticated web dashboard.
  * Sending 4 GiB files back from storage into Telegram chats exceeds standard Bot API limits and will require an outgoing MTProto client sender pipeline with chunked upload parts (`upload.saveBigFilePart`).


---

## 4. Webhook Ingestion Mode

* **Current Architecture**: Long-polling via aiogram 3.x (`TELEGRAM_MODE=polling`).
* **Proposed Enhancement**:
  * Webhook mode with TLS endpoint registered directly with Telegram (`https://backup.example.com/api/telegram/webhook`).
  * Instant event notification without polling interval delays.

---

## 5. Multi-User Sharing & Public Access Links

* **Current Architecture**: Strict user ownership and tenant isolation. User A cannot access User B's files.
* **Proposed Enhancement**:
  * Secure, time-limited, password-protected public share links with download tracking.
  * Shared folder collaboration between registered Telegram users with read/write permission tiers.
