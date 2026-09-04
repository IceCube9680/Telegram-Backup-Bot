# Large File Support Architecture (Phase 10 — Up to 4 GiB)

## 1. Overview & Architecture

Telegram imposes distinct file size limits across its APIs:
- **Telegram Bot API**: Strict maximum payload download limit of **20 MiB** (20,971,520 bytes).
- **Telegram MTProto Protocol**: Supports media uploads and downloads up to **4 GiB** (4,294,967,296 bytes) for Telegram Premium document references and up to 2 GiB for standard users.

This project implements a **Hybrid Telegram Bot API + MTProto Architecture**:

```
Telegram Client
      │
      ▼
Telegram Bot (aiogram 3.x)
      │
      ├── Extracts chat_id, message_id, file_id, file_unique_id, file_size
      ├── Validates user quota (default 50 MB, configurable up to 4 GiB)
      └── Enforces platform hard boundary: exactly 4 GiB allowed, > 4 GiB rejected
      │
      ▼
MongoDB BackupTask Queue
      │
      ▼
BackupWorker (Single Async Daemon Loop)
      │
      ├── Provider Selection:
      │     ├── file_size ≤ 20 MiB  ──> BotApiDownloader (Bot.get_file streaming)
      │     └── file_size > 20 MiB  ──> MtProtoDownloader (Telethon MTProto streaming)
      │
      ├── Pre-flight Disk Headroom Check:
      │     Requires: free_disk_bytes >= file_size + safety_margin (default 1 GiB)
      │
      ├── Resumable Chunked Download:
      │     Streams into: .tmp_mtproto_<task_id>.part in 1 MiB bounded chunks
      │     O(1) memory footprint (never loads full file into RAM)
      │     Sequential SHA-256 rebuild on worker restart
      │
      ├── Validation & Storage:
      │     Exact byte count validation
      │     Incremental SHA-256 verification
      │     Atomic zero-copy move into user-scoped storage key:
      │     users/{user_id}/{year}/{month}/{day}/{uuid}.{ext}
      │
      └── MongoDB State Synchronization:
            Atomically update BackupItem (storage_key, sha256, transfer_method, completed)
            Atomically increment StorageUsage ($inc total_files, total_size)
            Mark BackupTask completed
            Unlink temporary .part file
```

---

## 2. Telegram Source Identity & Resolution

Bot API `file_id` strings are transient base64 identifiers generated per-bot and **cannot** be used directly as MTProto document references.

To bridge this gap cleanly:
1. `TelegramMediaService` extracts and preserves:
   - `chat_id`: Telegram chat where the message was sent (user DM or group).
   - `telegram_message_id`: Original message ID.
   - `telegram_file_id`: Bot API file identifier.
   - `telegram_file_unique_id`: Unique identifier across Telegram.
   - `file_size`: Expected file size in bytes.
2. `TelegramSourceRef` is passed to the downloader.
3. `MtProtoDownloader` uses the server-side Telethon client to resolve the message by `chat_id` and `message_id`, obtaining the authentic `MessageMediaDocument` TL reference.

---

## 3. Configuration & Security

### Environment Variables (`.env`)

| Variable | Default | Description |
| :--- | :--- | :--- |
| `MT_PROTO_ENABLED` | `false` | Master toggle for MTProto large-file support |
| `MT_PROTO_API_ID` | `None` | Telegram API ID from https://my.telegram.org |
| `MT_PROTO_API_HASH` | `None` | Telegram API Hash from https://my.telegram.org |
| `MT_PROTO_SESSION_PATH` | `./secrets/mtproto_worker.session` | Filepath to Telethon session (chmod 0600) |
| `MT_PROTO_CHUNK_SIZE` | `1048576` (1 MiB) | Streaming chunk size |
| `MT_PROTO_CONCURRENCY` | `1` | Max concurrent MTProto large downloads |
| `MT_PROTO_MAX_ATTEMPTS` | `5` | Maximum retry attempts for transient errors |
| `MT_PROTO_RETRY_BASE_DELAY`| `2.0` | Initial exponential backoff delay in seconds |
| `MT_PROTO_RETRY_MAX_DELAY` | `60.0` | Maximum backoff delay in seconds |
| `LARGE_FILE_THRESHOLD` | `20971520` (20 MiB) | Routing threshold between Bot API and MTProto |
| `LARGE_FILE_RESUME_ENABLED`| `true` | Enable resumable transfer from `.part` file |
| `LARGE_FILE_DISK_SAFETY_MARGIN` | `1073741824` (1 GiB) | Minimum required free disk headroom |

### Session Security Rules
1. **Never commit `.session` files to Git**: Explicitly listed in `.gitignore` and `.dockerignore`.
2. **Filesystem Permissions**: Automatically restricted to `0700` for directory and `0600` for session file.
3. **No Web Exposure**: Session files are mounted strictly in the worker container and are never accessible via FastAPI or static web routes.

---

## 4. Resumable Transfers & SHA-256 Integrity

If a worker is killed or crashes mid-transfer:
1. The temporary file `.tmp_mtproto_<task_id>.part` is preserved on disk.
2. When the task is re-claimed (via stale lock recovery after `WORKER_LOCK_TIMEOUT` seconds), `MtProtoDownloader` inspects the existing `.part` file.
3. **Validation & SHA-256 Rebuild**:
   - Checks that `0 < existing_bytes <= expected_size`. If oversized/corrupt, the partial file is reset to 0.
   - Sequentially re-reads existing bytes in 1 MiB chunks to rebuild `hashlib.sha256` state in **O(1) memory**.
   - Resumes network streaming from `offset = existing_bytes`.
4. Upon completion:
   - Verifies `total_downloaded == expected_size`.
   - Produces final authoritative SHA-256 checksum.

---

## 5. Error Classification & Handling

| Error | Category | Action |
| :--- | :--- | :--- |
| `FloodWaitError` | Rate Limit | Extracts `wait_seconds` from Telegram; worker records status and does not thrash |
| `FileReferenceExpiredError` | Transient | Re-resolves source message to obtain fresh file reference and resumes |
| `FileMigrateError` | DC Migration | Automatically switches DC connection and resumes download |
| `ConnectionError` / `TimeoutError` | Network | Exponential backoff retry with jitter |
| `Size Exceeded (> 4 GiB)` | Permanent | Rejected at ingestion with `ValidationError` |
| `Insufficient Disk Space` | System | Task released for retry; download not started |

---

## 6. Authenticated Web Streaming

Stored large files (up to 4 GiB) can be streamed directly to authenticated users via the web dashboard:
- **Endpoint**: `GET /api/files/{file_id}/download`
- **Security**: Strictly enforces user ownership (`user_id`). Rejects path traversal and arbitrary path injection.
- **Memory Safety**: Streams directly from `LocalStorageService.download_stream()` in 64 KiB chunks with `Content-Length` and `Content-Disposition` headers.

---

## 7. MTProto Session Generation & Phase 10A Spike

### Generating Session File
```bash
python scripts/create_mtproto_session.py
```
Follow interactive prompts to login with SMS/OTP code.

### Running Phase 10A Access Spike
```bash
python scripts/mtproto_access_spike.py <chat_id> <message_id> [expected_size]
```
Outputs validation diagnostics, byte count, and SHA-256 checksum.
