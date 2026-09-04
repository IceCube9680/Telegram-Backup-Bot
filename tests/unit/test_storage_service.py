"""Unit tests for StorageService and LocalStorageService covering all 18 required scenarios."""

import asyncio
from io import BytesIO
from pathlib import Path
import pytest
import pytest_asyncio

from app.core.exceptions import StorageNotFoundError, StorageValidationError
from app.services.storage_service import LocalStorageService, StorageMetadata, StorageService


@pytest.fixture
def storage_service(tmp_path: Path) -> LocalStorageService:
    """Provide a LocalStorageService instance isolated to pytest's tmp_path."""
    return LocalStorageService(base_path=tmp_path)


# 1. Upload
@pytest.mark.asyncio
async def test_upload_bytes_and_file_obj(storage_service: LocalStorageService):
    """Test uploading raw bytes, synchronous BinaryIO, and async generator streams."""
    data = b"Hello, Telegram Backup Storage!"

    # Bytes upload
    key_bytes = await storage_service.upload(data, user_id=101, extension="txt")
    assert key_bytes.startswith("users/101/")
    assert key_bytes.endswith(".txt")
    assert await storage_service.exists(key_bytes) is True

    # BinaryIO upload
    bio = BytesIO(b"Streamed binary data")
    key_bio = await storage_service.upload(bio, user_id=101, extension="bin")
    assert await storage_service.exists(key_bio) is True
    assert await storage_service.download(key_bio) == b"Streamed binary data"

    # Async generator stream upload
    async def async_stream():
        yield b"chunk1-"
        yield b"chunk2-"
        yield b"chunk3"

    key_stream = await storage_service.upload(async_stream(), user_id=101, extension="dat")
    assert await storage_service.download(key_stream) == b"chunk1-chunk2-chunk3"


# 2. Download and Streaming Download
@pytest.mark.asyncio
async def test_download_and_download_stream(storage_service: LocalStorageService):
    """Test full download and chunked download_stream."""
    content = b"A" * (128 * 1024)  # 128 KB
    key = await storage_service.upload(content, user_id=102, extension="bin")

    # Full download
    downloaded = await storage_service.download(key)
    assert downloaded == content

    # Streamed download
    chunks = []
    async for chunk in storage_service.download_stream(key, chunk_size=32 * 1024):
        chunks.append(chunk)

    assert len(chunks) == 4
    assert b"".join(chunks) == content


# 3. Delete
@pytest.mark.asyncio
async def test_delete(storage_service: LocalStorageService):
    """Test delete returns True for existing file, False for missing file."""
    key = await storage_service.upload(b"to be deleted", user_id=103, extension="bin")
    assert await storage_service.exists(key) is True

    deleted = await storage_service.delete(key)
    assert deleted is True
    assert await storage_service.exists(key) is False

    # Second delete returns False
    assert await storage_service.delete(key) is False


# 4. Exists
@pytest.mark.asyncio
async def test_exists(storage_service: LocalStorageService):
    """Test exists behavior for valid existing, non-existent, and invalid keys."""
    key = await storage_service.upload(b"data", user_id=104, extension="bin")
    assert await storage_service.exists(key) is True
    assert await storage_service.exists("users/104/2026/01/01/non-existent.bin") is False
    assert await storage_service.exists("../../etc/passwd") is False


# 5. Get Size
@pytest.mark.asyncio
async def test_get_size(storage_service: LocalStorageService):
    """Test get_size returns exact byte count."""
    payload = b"Exact 25 bytes of payload"
    key = await storage_service.upload(payload, user_id=105, extension="bin")
    assert await storage_service.get_size(key) == 25


# 6. Get Metadata
@pytest.mark.asyncio
async def test_get_metadata(storage_service: LocalStorageService):
    """Test get_metadata provides size, timestamps, and MIME guess without absolute paths."""
    key = await storage_service.upload(b"%PDF-1.4 sample pdf content", user_id=106, extension="pdf")
    meta = await storage_service.get_metadata(key)

    assert isinstance(meta, StorageMetadata)
    assert meta.storage_key == key
    assert meta.size_bytes == 27
    assert meta.mime_type_guess == "application/pdf"
    assert meta.created_at is not None
    assert meta.modified_at is not None
    # Verify no absolute filesystem path leakage in model dict
    assert "base_path" not in meta.model_dump()


# 7. Path Traversal Rejection
@pytest.mark.asyncio
async def test_path_traversal_rejection(storage_service: LocalStorageService):
    """Test traversal attempts like ../, ..\\, and nested traversal raise StorageValidationError."""
    invalid_keys = [
        "../secret.txt",
        "..\\secret.txt",
        "users/../../etc/passwd",
        "users/101/../../../shadow",
        "users/./101/file.bin",
        "users//101/file.bin",
    ]
    for key in invalid_keys:
        with pytest.raises(StorageValidationError):
            storage_service.validate_storage_key(key)


# 8. Absolute Path Rejection
@pytest.mark.asyncio
async def test_absolute_path_rejection(storage_service: LocalStorageService):
    """Test absolute paths are rejected with StorageValidationError."""
    absolute_keys = [
        "/etc/passwd",
        "/var/log/syslog",
        "C:\\Windows\\System32\\cmd.exe",
        "C:/Windows/notepad.exe",
        "/app/storage/users/101/file.bin",
    ]
    for key in absolute_keys:
        with pytest.raises(StorageValidationError):
            storage_service.validate_storage_key(key)


# 9. Null Byte Rejection
@pytest.mark.asyncio
async def test_null_byte_rejection(storage_service: LocalStorageService):
    """Test null bytes in storage keys raise StorageValidationError."""
    null_keys = [
        "users/101/file\x00.bin",
        "users/101/\x00secret.txt",
        "\x00/etc/passwd",
    ]
    for key in null_keys:
        with pytest.raises(StorageValidationError):
            storage_service.validate_storage_key(key)


# 10. Failed Upload Cleanup
@pytest.mark.asyncio
async def test_failed_upload_cleanup(storage_service: LocalStorageService):
    """Test that when an upload stream errors out, temporary files are removed and target is not created."""
    async def failing_stream():
        yield b"initial-chunk-"
        raise RuntimeError("Simulated network/stream failure during upload")

    key = storage_service.generate_storage_key(user_id=110, extension="bin")
    target_path = storage_service.validate_storage_key(key)

    with pytest.raises(Exception):
        await storage_service.upload_to_key(failing_stream(), storage_key=key)

    # Verify target file does not exist
    assert target_path.exists() is False

    # Verify no dangling temporary files in target directory
    if target_path.parent.exists():
        temp_files = list(target_path.parent.glob("*.tmp.*"))
        assert len(temp_files) == 0


# 11. Missing File Behavior
@pytest.mark.asyncio
async def test_missing_file_behavior(storage_service: LocalStorageService):
    """Test download, get_size, and get_metadata raise StorageNotFoundError for non-existent files."""
    missing_key = "users/111/2026/09/04/missing-uuid-1234.bin"

    with pytest.raises(StorageNotFoundError):
        await storage_service.download(missing_key)

    with pytest.raises(StorageNotFoundError):
        await storage_service.get_size(missing_key)

    with pytest.raises(StorageNotFoundError):
        await storage_service.get_metadata(missing_key)


# 12. Concurrent Operations
@pytest.mark.asyncio
async def test_concurrent_operations(storage_service: LocalStorageService):
    """Test multiple concurrent uploads and downloads."""
    async def upload_and_verify(idx: int):
        payload = f"Concurrent payload #{idx}".encode()
        key = await storage_service.upload(payload, user_id=112, extension="txt")
        read_back = await storage_service.download(key)
        assert read_back == payload
        return key

    keys = await asyncio.gather(*[upload_and_verify(i) for i in range(25)])
    assert len(keys) == 25
    assert len(set(keys)) == 25  # All generated keys are unique


# 13. User Storage Isolation
@pytest.mark.asyncio
async def test_user_storage_isolation(storage_service: LocalStorageService):
    """Test that generated storage keys are separated into user subdirectories."""
    key_user_a = await storage_service.upload(b"User A Data", user_id=1001, extension="bin")
    key_user_b = await storage_service.upload(b"User B Data", user_id=2002, extension="bin")

    assert key_user_a.startswith("users/1001/")
    assert key_user_b.startswith("users/2002/")
    assert key_user_a != key_user_b


# 14. Generated Storage Keys Format
def test_generated_storage_keys_format(storage_service: LocalStorageService):
    """Test generate_storage_key adheres to users/{user_id}/{year}/{month}/{day}/{uuid}.{ext} format."""
    key = storage_service.generate_storage_key(user_id=789, extension=".PDF")
    parts = key.split("/")

    assert len(parts) == 6
    assert parts[0] == "users"
    assert parts[1] == "789"
    assert len(parts[2]) == 4  # Year (e.g. 2026)
    assert len(parts[3]) == 2  # Month (e.g. 09)
    assert len(parts[4]) == 2  # Day (e.g. 04)
    assert parts[5].endswith(".pdf")  # Normalized lowercase extension


# 15. Filenames Containing Spaces
@pytest.mark.asyncio
async def test_filenames_containing_spaces(storage_service: LocalStorageService):
    """Test that original filenames with spaces are decoupled from safe generated storage keys."""
    original_filename = "My Annual Financial Report (Final Version) 2026.pdf"
    file_bytes = b"Financial data content"

    # Extension extracted from original filename, key generated safely
    ext = Path(original_filename).suffix.lstrip(".")
    storage_key = await storage_service.upload(file_bytes, user_id=115, extension=ext)

    assert " " not in storage_key
    assert storage_key.endswith(".pdf")
    assert await storage_service.download(storage_key) == file_bytes


# 16. Unicode Filenames
@pytest.mark.asyncio
async def test_unicode_filenames(storage_service: LocalStorageService):
    """Test that original filenames with Japanese, Hindi, emojis, or accents do not affect storage keys."""
    unicode_filenames = [
        "テストファイル.jpg",
        "दस्तावेज़.docx",
        "مستند_مهم.pdf",
        "🎉 party_photo 🥳.png",
        "résumé_français.pdf",
    ]
    for original in unicode_filenames:
        ext = Path(original).suffix.lstrip(".") or "bin"
        storage_key = await storage_service.upload(b"unicode content", user_id=116, extension=ext)
        assert storage_key.isascii()  # Storage key remains strictly safe ASCII
        assert await storage_service.exists(storage_key) is True


# 17. Very Long Filenames
@pytest.mark.asyncio
async def test_very_long_filenames(storage_service: LocalStorageService):
    """Test that excessively long filenames (>255 characters) are handled cleanly without OS filesystem error."""
    long_filename = "A" * 300 + ".zip"
    ext = Path(long_filename).suffix.lstrip(".")

    storage_key = await storage_service.upload(b"compressed archive", user_id=117, extension=ext)
    assert len(storage_key) < 100  # Generated key is compact and safe
    assert await storage_service.exists(storage_key) is True


# 18. Unusual Filename Characters
@pytest.mark.asyncio
async def test_unusual_filename_characters(storage_service: LocalStorageService):
    """Test that original filenames with special characters ($#%&*<>:|?) do not break storage keys."""
    special_filenames = [
        "report$#%&*!.dat",
        "dangerous<script>:file?.pdf",
        'quote"and|pipe.bin',
    ]
    for original in special_filenames:
        ext = Path(original).suffix.lstrip(".") or "bin"
        storage_key = await storage_service.upload(b"safe payload", user_id=118, extension=ext)
        assert all(c not in storage_key for c in "<>:\"|?*$#%&'!")
        assert await storage_service.download(storage_key) == b"safe payload"
