"""CLI utility to verify MongoDB and Storage backup archive integrity and consistency."""

import argparse
import gzip
import hashlib
from pathlib import Path
import sys
import tarfile
from typing import Dict, Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify backup archive file integrity (supports .gz, .tar.gz, mongodump archives).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "archive_path",
        type=str,
        help="Path to the backup archive (.gz, .tar.gz, .archive.gz).",
    )
    parser.add_argument(
        "--calculate-checksum",
        action="store_true",
        default=True,
        help="Calculate and display SHA-256 checksum of the archive.",
    )
    return parser.parse_args()


def calculate_sha256(path: Path) -> str:
    """Compute SHA-256 checksum of a file in streaming 64KiB chunks."""
    sha = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            sha.update(chunk)
    return sha.hexdigest()


def verify_archive(archive_path: str, compute_hash: bool = True) -> int:
    path = Path(archive_path).resolve()

    print("\n" + "=" * 65)
    print("📦 TELEGRAM BACKUP BOT — BACKUP ARCHIVE VERIFIER")
    print("=" * 65)
    print(f"Target Archive:   {path.name}")
    print(f"Absolute Path:    {path}")

    if not path.exists():
        print(f"❌ Error: Archive file '{path}' does not exist.")
        return 1

    if not path.is_file():
        print(f"❌ Error: Path '{path}' is not a regular file.")
        return 1

    file_size_bytes = path.stat().st_size
    file_size_kb = round(file_size_bytes / 1024, 2)
    print(f"Archive Size:     {file_size_kb} KB ({file_size_bytes} bytes)")

    if file_size_bytes == 0:
        print("❌ Error: Archive file is completely empty (0 bytes).")
        return 1

    # Checksum calculation
    if compute_hash:
        try:
            sha256_hash = calculate_sha256(path)
            print(f"SHA-256 Checksum: {sha256_hash}")
        except Exception as e:
            print(f"❌ Error computing checksum: {e}")
            return 1

    # Determine archive type and verify
    is_tar_archive = False
    name_lower = path.name.lower()

    if name_lower.endswith((".tar.gz", ".tgz")):
        is_tar_archive = True
    elif name_lower.endswith(".gz") and not name_lower.endswith(".archive.gz"):
        # Could be tar.gz or simple gz, test tar first
        try:
            if tarfile.is_tarfile(path):
                is_tar_archive = True
        except Exception:
            is_tar_archive = False

    if is_tar_archive:
        print("Archive Format:   TAR GZIP (.tar.gz)")
        try:
            with tarfile.open(path, "r:gz") as tar:
                members = tar.getmembers()
                print(f"✅ Tar Structure:     Valid ({len(members)} member entries detected)")
                # Test reading headers and sample files
                for m in members[:5]:
                    print(f"   • {m.name} ({m.size} bytes)")
                if len(members) > 5:
                    print(f"   ... and {len(members) - 5} more entries")
        except Exception as e:
            print(f"❌ Error: Failed to inspect tar.gz archive: {e}")
            return 1
    else:
        print("Archive Format:   GZIP Stream / Mongodump Archive (.gz)")
        try:
            total_decompressed_bytes = 0
            with gzip.open(path, "rb") as gz:
                while chunk := gz.read(65536):
                    total_decompressed_bytes += len(chunk)
            
            if total_decompressed_bytes == 0:
                print("❌ Error: Decompressed gzip stream is empty.")
                return 1
            decompressed_kb = round(total_decompressed_bytes / 1024, 2)
            print(f"✅ Gzip Decompress:   Valid & readable ({decompressed_kb} KB uncompressed)")
        except Exception as e:
            print(f"❌ Error: Failed to decompress gzip archive: {e}")
            return 1

    print("-" * 65)
    print("Verification Status:  ✅ ARCHIVE VALID (Format & Data Stream Intact)")
    print("Note: 'ARCHIVE VALID' confirms archive integrity. Full restore")
    print("verification requires execution of database/storage restore drills.")
    print("=" * 65 + "\n")
    return 0


def main() -> None:
    args = parse_args()
    code = verify_archive(args.archive_path, compute_hash=args.calculate_checksum)
    sys.exit(code)


if __name__ == "__main__":
    main()
