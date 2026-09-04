"""CLI tool for checking and repairing database referential integrity."""

import argparse
import asyncio
import sys

from app.core.logging import get_logger, setup_logging
from app.database.mongo import mongo_manager
from app.services.integrity_service import DataIntegrityService, IntegrityReport

logger = get_logger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit database referential integrity across MongoDB collections.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--repair",
        action="store_true",
        help="Repair safe dangling references (unassign deleted folders, remove orphaned item-tags).",
    )
    return parser.parse_args()


async def run_integrity_check(args: argparse.Namespace) -> int:
    setup_logging("INFO")

    print("\n" + "=" * 60)
    print("🔍 TELEGRAM BACKUP BOT — DATA INTEGRITY CHECK")
    print("=" * 60)

    if not args.repair:
        print("Mode: 🔍 DRY RUN (Read-Only Audit — Zero Changes Made)\n")
    else:
        print("Mode: 🛠 REPAIR MODE (Applying safe referential repairs)\n")

    db = await mongo_manager.connect()
    try:
        service = DataIntegrityService(db=db)
        report: IntegrityReport = await service.check_integrity(repair=args.repair)

        print(f"Total Users Checked:        {report.total_users_checked}")
        print(f"Total BackupItems Checked:  {report.total_items_checked}")
        print(f"Total Folders Checked:      {report.total_folders_checked}")
        print(f"Total Tags Checked:         {report.total_tags_checked}\n")

        print("-" * 60)
        print("ANOMALY BREAKDOWN")
        print("-" * 60)
        print(f"Dangling Folder References:      {len(report.dangling_folder_refs)}")
        print(f"Orphaned Item-Tag Associations:  {len(report.orphaned_item_tags)}")
        print(f"Missing StorageUsage Records:    {len(report.missing_storage_usage_users)}")
        print(f"Ambiguous State Anomalies:       {len(report.ambiguous_anomalies)}")
        print("-" * 60)

        if report.dangling_folder_refs:
            print("\n⚠️  Dangling Folder References:")
            for d in report.dangling_folder_refs:
                print(f"  - {d}")

        if report.orphaned_item_tags:
            print("\n⚠️  Orphaned ItemTags:")
            for o in report.orphaned_item_tags:
                print(f"  - {o}")

        if report.missing_storage_usage_users:
            print("\n⚠️  Users Missing StorageUsage Records:")
            for u in report.missing_storage_usage_users:
                print(f"  - User {u}")

        if report.ambiguous_anomalies:
            print("\n🚨 Ambiguous State Anomalies (Report Only - Manual Review Recommended):")
            for a in report.ambiguous_anomalies:
                print(f"  - {a}")

        if args.repair:
            print(f"\n✅ Safe repairs applied: {report.repaired_count}")
        elif not report.is_clean:
            print("\n💡 Tip: To automatically fix safe dangling references, re-run with:")
            print("   python -m app.scripts.integrity_check --repair")

        print("\nIntegrity audit complete.\n")
        return 0 if report.is_clean or (args.repair and not report.ambiguous_anomalies) else 1

    finally:
        await mongo_manager.disconnect()


def main() -> None:
    args = parse_args()
    code = asyncio.run(run_integrity_check(args))
    sys.exit(code)


if __name__ == "__main__":
    main()
