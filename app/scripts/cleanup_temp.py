"""CLI script to clean stale temporary download files."""

import argparse
import asyncio
from pathlib import Path
import sys
import time

from app.core.config import get_settings
from app.core.logging import setup_logging


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Clean stale temporary download files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--max-age-hours",
        type=float,
        default=1.0,
        help="Maximum age in hours before a temporary file is considered stale (default: 1.0).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scan and list stale files without deleting them.",
    )
    return parser.parse_args()


def clean_temp_downloads(max_age_hours: float, dry_run: bool) -> int:
    setup_logging("INFO")
    settings = get_settings()
    temp_dir = Path(settings.STORAGE_PATH).resolve() / ".tmp-downloads"

    print("\n" + "=" * 60)
    print("🧹 TELEGRAM BACKUP BOT — TEMP FILES CLEANUP")
    print("=" * 60)
    print(f"Target Directory: {temp_dir}")
    print(f"Max Age:          {max_age_hours} hour(s)")
    print(f"Mode:             {'🔍 DRY RUN' if dry_run else '🗑 DELETION'}\n")

    if not temp_dir.exists():
        print("Directory does not exist. Nothing to clean.")
        return 0

    max_age_seconds = max_age_hours * 3600.0
    now = time.time()
    stale_files = []

    for item in temp_dir.iterdir():
        if item.is_file():
            try:
                mtime = item.stat().st_mtime
                age_s = now - mtime
                if age_s > max_age_seconds:
                    size_kb = round(item.stat().st_size / 1024, 1)
                    stale_files.append((item, age_s, size_kb))
            except Exception as e:
                print(f"Error reading {item}: {e}")

    if not stale_files:
        print("No stale temporary files found.")
        return 0

    print(f"Found {len(stale_files)} stale temporary file(s):")
    freed_kb = 0.0
    cleaned_count = 0

    for path, age_s, size_kb in stale_files:
        age_m = round(age_s / 60, 1)
        if dry_run:
            print(f"  - [DRY RUN] {path.name} ({size_kb} KB, age: {age_m} min)")
        else:
            try:
                path.unlink(missing_ok=True)
                cleaned_count += 1
                freed_kb += size_kb
                print(f"  - [DELETED] {path.name} ({size_kb} KB, age: {age_m} min)")
            except Exception as de:
                print(f"  - [FAILED]  {path.name}: {de}")

    print("-" * 60)
    if dry_run:
        print(f"Scan complete. {len(stale_files)} stale files identified.")
    else:
        print(f"Cleanup complete. {cleaned_count} files removed ({round(freed_kb/1024, 2)} MB freed).")
    print()
    return 0


def main() -> None:
    args = parse_args()
    code = clean_temp_downloads(args.max_age_hours, args.dry_run)
    sys.exit(code)


if __name__ == "__main__":
    main()
