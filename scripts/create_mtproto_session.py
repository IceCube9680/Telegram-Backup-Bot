#!/usr/bin/env python3
"""Interactive utility to create and authenticate a Telethon MTProto session file.

Security Guidelines:
- Run this script interactively in a secure terminal.
- Never hardcode phone numbers, passwords, or SMS codes.
- The generated session file will be written with permissions 0600.
"""

import asyncio
import os
import stat
import sys
from pathlib import Path

try:
    from telethon import TelegramClient
except ImportError:
    print("Error: telethon is not installed. Install with: pip install telethon>=1.38.0")
    sys.exit(1)


async def main() -> None:
    print("=" * 65)
    print(" Telegram Backup Bot — MTProto Session Generator (Phase 10)")
    print("=" * 65)
    print("This utility authenticates a dedicated Telegram account for MTProto")
    print("large-file downloads (up to 4 GiB).\n")

    api_id_env = os.getenv("MT_PROTO_API_ID")
    api_hash_env = os.getenv("MT_PROTO_API_HASH")
    session_path_env = os.getenv("MT_PROTO_SESSION_PATH", "./secrets/mtproto_worker.session")

    api_id_str = input(f"Enter Telegram API_ID [{api_id_env or ''}]: ").strip() or api_id_env
    if not api_id_str:
        print("Error: API_ID is required. Obtain it from https://my.telegram.org")
        sys.exit(1)

    try:
        api_id = int(api_id_str)
    except ValueError:
        print("Error: API_ID must be an integer.")
        sys.exit(1)

    api_hash = input(f"Enter Telegram API_HASH [{api_hash_env or ''}]: ").strip() or api_hash_env
    if not api_hash:
        print("Error: API_HASH is required. Obtain it from https://my.telegram.org")
        sys.exit(1)

    session_target = input(f"Enter Session Filepath [{session_path_env}]: ").strip() or session_path_env
    session_path = Path(session_target).resolve()

    # Ensure parent directory exists with secure permissions (0700)
    session_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(session_path.parent, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
    except Exception:
        pass

    # Telethon automatically appends .session if not already present
    session_name = str(session_path)
    if session_name.endswith(".session"):
        session_name = session_name[:-8]

    print(f"\nInitializing Telethon client for session: {session_path}...")
    client = TelegramClient(session_name, api_id, api_hash)
    await client.start()

    me = await client.get_me()
    print("\nAuthentication successful!")
    print(f"Logged in as: {me.first_name} (@{me.username or 'no_username'}) [ID: {me.id}]")

    await client.disconnect()

    # Secure file permissions (chmod 0600)
    actual_file = Path(f"{session_name}.session")
    if actual_file.exists():
        os.chmod(actual_file, stat.S_IRUSR | stat.S_IWUSR)
        print(f"Session file successfully secured with 0600 permissions at: {actual_file}")

    print("\nNext steps:")
    print("1. Set MT_PROTO_ENABLED=true in your .env configuration.")
    print("2. Set MT_PROTO_API_ID and MT_PROTO_API_HASH in .env.")
    print(f"3. Set MT_PROTO_SESSION_PATH={actual_file} in .env.")
    print("4. Restart the worker service: docker compose restart worker\n")


if __name__ == "__main__":
    asyncio.run(main())
