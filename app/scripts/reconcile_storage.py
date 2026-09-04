"""CLI tool for storage reconciliation between MongoDB and filesystem."""

import argparse
import asyncio
import sys
from typing import List

from app.core.config import get_settings
from app.core.logging import get_logger, setup_logging
from app.database.mongo import mongo_manager
from app.services.storage_reconciliation_service import (
    StorageReconciliationReport,
    StorageReconciliationService,
)

logger = get_logger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reconcile MongoDB backup records with physical filesystem storage.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--repair",
        action="store_true",
        help="Repair StorageUsage accounting records based on authoritative item sizes.",
    )
    parser.add_argument(
        "--delete-orphans",
        action="store_true",
        help="Extremely conservative flag to delete confirmed orphan files (requires --confirm).",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Confirm destructive deletion of orphan files.",
    )
    parser.add_argument(
        "--user-id",
        type=int,
        default=None,
        help="Target specific Telegram user ID (defaults to all users).",
    )
    return parser.parse_args()


async def run_reconciliation(args: argparse.Namespace) -> int:
    settings = get_settings()
    setup_logging("INFO")

    print("\n" + "=" * 60)
    print("📦 TELEGRAM BACKUP BOT — STORAGE RECONCILIATION")
    print("=" * 60)

    if not args.repair and not args.delete_orphans:
        print("Mode: 🔍 DRY RUN (Read-Only Analysis — Zero Changes Made)")
    else:
        print(f"Mode: 🛠 REPAIR MODE (Repair Usage: {args.repair}, Delete Orphans: {args.delete_orphans})")

    if args.delete_orphans and not args.confirm:
        print("\n⚠️  ERROR: --delete-orphans requires explicit --confirm flag to proceed.")
        return 1

    print(f"Storage Root: {settings.STORAGE_PATH}\n")

    db = await mongo_manager.connect()
    try:
        service = StorageReconciliationService(db=db, settings=settings)

        reports: List[StorageReconciliationReport] = []
        if args.user_id:
            report = await service.reconcile_user(
                user_id=args.user_id,
                repair=args.repair,
                delete_orphans=args.delete_orphans,
                confirm=args.confirm,
            )
            reports = [report]
        else:
            reports = await service.reconcile_all(
                repair=args.repair,
                delete_orphans=args.delete_orphans,
                confirm=args.confirm,
            )

        if not reports:
            print("No users or stored files found.")
            return 0

        total_db_items = sum(r.total_db_items for r in reports)
        total_physical_files = sum(r.total_physical_files for r in reports)
        total_missing = sum(len(r.missing_files) for r in reports)
        total_orphans = sum(len(r.orphan_files) for r in reports)
        total_mismatches = sum(1 for r in reports if r.usage_mismatch)
        total_orphans_deleted = sum(r.deleted_orphans_count for r in reports)

        print("-" * 60)
        print(f"{'User ID':<12} | {'DB Items':<8} | {'Disk Files':<10} | {'Missing':<8} | {'Orphans':<8} | {'Mismatch'}")
        print("-" * 60)
        for r in reports:
            mismatch_str = "YES" if r.usage_mismatch else "NO"
            if r.repaired_usage:
                mismatch_str += " (Repaired)"
            print(f"{r.user_id:<12} | {r.total_db_items:<8} | {r.total_physical_files:<10} | {len(r.missing_files):<8} | {len(r.orphan_files):<8} | {mismatch_str}")
        print("-" * 60)

        print("\n--- Summary ---")
        print(f"Known DB files:      {total_db_items}")
        print(f"Physical files:      {total_physical_files}")
        print(f"Missing files:       {total_missing}")
        print(f"Orphan files:        {total_orphans}")
        print(f"Usage mismatches:    {total_mismatches}")
        if total_orphans_deleted > 0:
            print(f"Orphans deleted:     {total_orphans_deleted}")

        if total_missing > 0:
            print("\n⚠️  Missing Physical Files Details:")
            for r in reports:
                for mf in r.missing_files:
                    print(f"  - User {r.user_id}: {mf}")

        if total_orphans > 0 and not args.delete_orphans:
            print("\n💡 Tip: To safely delete confirmed orphan files, re-run with:")
            print("   python -m app.scripts.reconcile_storage --repair --delete-orphans --confirm")

        print("\nReconciliation complete.\n")
        return 0

    finally:
        await mongo_manager.disconnect()


def main() -> None:
    args = parse_args()
    code = asyncio.run(run_reconciliation(args))
    sys.exit(code)


if __name__ == "__main__":
    main()
