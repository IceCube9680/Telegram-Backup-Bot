"""Storage abstraction and Local filesystem storage engine with atomic writes and path traversal protection."""

from abc import ABC, abstractmethod
import asyncio
from datetime import datetime, timezone
from functools import lru_cache
import mimetypes
import os
from pathlib import Path
from typing import Any, AsyncIterable, AsyncIterator, BinaryIO, Optional, Union
import uuid
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.exceptions import (
    StorageError,
    StorageNotFoundError,
    StoragePermissionError,
    StorageValidationError,
)
from app.core.logging import get_logger

logger = get_logger(__name__)


class StorageMetadata(BaseModel):
    """Storage object metadata representation."""

    storage_key: str = Field(..., description="Unique relative storage key")
    size_bytes: int = Field(..., ge=0, description="Size in bytes")
    created_at: datetime = Field(..., description="Creation timestamp in UTC")
    modified_at: datetime = Field(..., description="Last modification timestamp in UTC")
    mime_type_guess: Optional[str] = Field(default=None, description="Guessed MIME type based on key suffix")


class StorageService(ABC):
    """Abstract interface for file storage engines."""

    @abstractmethod
    def generate_storage_key(self, user_id: int, extension: str = "bin") -> str:
        """Generate a safe, user-scoped storage key decoupling storage from user-supplied filenames."""
        pass

    @abstractmethod
    async def upload(
        self,
        file_data: Union[bytes, AsyncIterator[bytes], AsyncIterable[bytes], BinaryIO],
        user_id: int,
        extension: str = "bin",
    ) -> str:
        """Upload data and return the generated storage key."""
        pass

    @abstractmethod
    async def upload_to_key(
        self,
        file_data: Union[bytes, AsyncIterator[bytes], AsyncIterable[bytes], BinaryIO],
        storage_key: str,
    ) -> str:
        """Upload data to an explicitly specified storage key atomically."""
        pass

    @abstractmethod
    async def download(self, storage_key: str) -> bytes:
        """Download entire file content into memory."""
        pass

    @abstractmethod
    async def download_stream(
        self,
        storage_key: str,
        chunk_size: int = 64 * 1024,
    ) -> AsyncIterator[bytes]:
        """Stream file contents in chunks."""
        pass

    @abstractmethod
    async def delete(self, storage_key: str) -> bool:
        """Delete storage object safely. Returns True if file was deleted, False if it did not exist."""
        pass

    @abstractmethod
    async def store_from_file(
        self, source_path: Union[str, Path], storage_key: str, move: bool = True
    ) -> str:
        """Atomically commit a physical file into storage_key."""
        pass

    @abstractmethod
    async def exists(self, storage_key: str) -> bool:
        """Check if storage key exists."""
        pass

    @abstractmethod
    async def get_size(self, storage_key: str) -> int:
        """Get file size in bytes."""
        pass

    @abstractmethod
    async def get_metadata(self, storage_key: str) -> StorageMetadata:
        """Get file metadata without exposing absolute server filesystem paths."""
        pass


class LocalStorageService(StorageService):
    """Local filesystem implementation of StorageService."""

    def __init__(self, base_path: Optional[Union[str, Path]] = None) -> None:
        settings = get_settings()
        raw_path = base_path or settings.STORAGE_PATH
        self.base_path: Path = Path(raw_path).resolve()

        # Ensure base storage directory exists
        try:
            self.base_path.mkdir(parents=True, exist_ok=True)
            logger.info(f"LocalStorageService initialized at {self.base_path}")
        except PermissionError as e:
            logger.error(f"Permission denied creating storage directory {self.base_path}: {e}")
            raise StoragePermissionError(
                message=f"Cannot initialize storage directory: Permission denied",
                details={"path": str(self.base_path)},
            ) from e
        except Exception as e:
            logger.error(f"Failed to initialize storage directory {self.base_path}: {e}")
            raise StorageError(
                message=f"Storage initialization error: {str(e)}",
                details={"path": str(self.base_path)},
            ) from e

    def generate_storage_key(self, user_id: int, extension: str = "bin") -> str:
        """Generate safe storage key: users/{user_id}/{year}/{month:02d}/{day:02d}/{uuid4}.{ext}"""
        now = datetime.now(timezone.utc)
        clean_ext = "".join(c for c in extension if c.isalnum()).lower() or "bin"
        random_id = str(uuid.uuid4())
        return f"users/{user_id}/{now.year}/{now.month:02d}/{now.day:02d}/{random_id}.{clean_ext}"

    def validate_storage_key(self, storage_key: str) -> Path:
        """Validate storage key against path traversal, null bytes, and absolute paths.

        Returns safe absolute Path residing strictly within self.base_path.
        """
        if not storage_key or not isinstance(storage_key, str):
            raise StorageValidationError(
                message="Storage key must be a non-empty string",
                details={"storage_key": str(storage_key)},
            )

        # 1. Null byte detection
        if "\x00" in storage_key:
            raise StorageValidationError(
                message="Storage key contains forbidden null bytes",
                details={"storage_key": repr(storage_key)},
            )

        # 2. Absolute path rejection
        if (
            storage_key.startswith("/")
            or storage_key.startswith("\\")
            or (len(storage_key) > 1 and storage_key[1] == ":")  # Windows drive letter
            or os.path.isabs(storage_key)
        ):
            raise StorageValidationError(
                message="Absolute storage paths are forbidden",
                details={"storage_key": storage_key},
            )

        # 3. Path traversal segment checking
        normalized = storage_key.replace("\\", "/")
        parts = normalized.split("/")
        if any(part in ("..", ".", "") for part in parts):
            raise StorageValidationError(
                message="Storage key contains invalid or traversal segments ('..', '.', empty)",
                details={"storage_key": storage_key},
            )

        # 4. Canonical resolution & boundary verification
        try:
            target_path = (self.base_path / normalized).resolve()
        except Exception as e:
            raise StorageValidationError(
                message=f"Could not resolve storage path: {str(e)}",
                details={"storage_key": storage_key},
            ) from e

        # Ensure target_path is strictly a child of self.base_path
        try:
            target_path.relative_to(self.base_path)
        except ValueError as e:
            raise StorageValidationError(
                message="Storage key escapes the root storage directory",
                details={"storage_key": storage_key},
            ) from e

        return target_path

    async def upload(
        self,
        file_data: Union[bytes, AsyncIterator[bytes], AsyncIterable[bytes], BinaryIO],
        user_id: int,
        extension: str = "bin",
    ) -> str:
        """Generate safe storage key and upload data."""
        storage_key = self.generate_storage_key(user_id=user_id, extension=extension)
        return await self.upload_to_key(file_data=file_data, storage_key=storage_key)

    async def upload_to_key(
        self,
        file_data: Union[bytes, AsyncIterator[bytes], AsyncIterable[bytes], BinaryIO],
        storage_key: str,
    ) -> str:
        """Atomically write data to target storage key using temporary file and atomic replace."""
        target_path = self.validate_storage_key(storage_key)

        try:
            # Ensure parent directories exist
            target_path.parent.mkdir(parents=True, exist_ok=True)
        except PermissionError as e:
            raise StoragePermissionError(
                message="Permission denied creating storage subdirectories",
                details={"storage_key": storage_key},
            ) from e

        # Temporary file path alongside destination file
        temp_path = target_path.with_name(f".{target_path.name}.tmp.{uuid.uuid4().hex}")

        try:
            # Write data to temporary file
            if isinstance(file_data, bytes):
                await asyncio.to_thread(self._write_bytes_sync, temp_path, file_data)
            elif hasattr(file_data, "__aiter__"):
                # Async iterator / stream
                await self._write_async_stream(temp_path, file_data)
            elif hasattr(file_data, "read"):
                # Synchronous BinaryIO stream
                await asyncio.to_thread(self._write_file_obj_sync, temp_path, file_data)
            else:
                raise StorageValidationError(
                    message="Unsupported file_data type for upload",
                    details={"type": type(file_data).__name__},
                )

            # Atomic replace
            await asyncio.to_thread(os.replace, temp_path, target_path)
            logger.debug(f"Successfully uploaded file to {storage_key}")
            return storage_key

        except StorageValidationError:
            # Re-raise validation errors without wrapping
            if temp_path.exists():
                try:
                    temp_path.unlink(missing_ok=True)
                except Exception:
                    pass
            raise
        except PermissionError as e:
            if temp_path.exists():
                try:
                    temp_path.unlink(missing_ok=True)
                except Exception:
                    pass
            raise StoragePermissionError(
                message=f"Permission denied during file write: {str(e)}",
                details={"storage_key": storage_key},
            ) from e
        except Exception as e:
            # Clean up temporary file on failure
            if temp_path.exists():
                try:
                    temp_path.unlink(missing_ok=True)
                except Exception:
                    pass
            logger.error(f"Failed to upload file to {storage_key}: {e}")
            raise StorageError(
                message=f"Failed to write file to storage: {str(e)}",
                details={"storage_key": storage_key},
            ) from e

    async def store_from_file(
        self,
        source_path: Union[str, Path],
        storage_key: str,
        move: bool = True,
    ) -> str:
        """Atomically commit a physical file into target storage key (via os.replace or copy)."""
        target_path = self.validate_storage_key(storage_key)
        src = Path(source_path).resolve()

        if not src.exists() or not src.is_file():
            raise StorageNotFoundError(
                message=f"Source file not found for storage: '{src}'",
                details={"source_path": str(src), "storage_key": storage_key},
            )

        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            if move:
                # Atomic zero-copy move on same filesystem
                await asyncio.to_thread(os.replace, src, target_path)
            else:
                await asyncio.to_thread(shutil.copy2, src, target_path)
            logger.debug(f"Successfully stored file from {src} to {storage_key} (move={move})")
            return storage_key
        except PermissionError as e:
            raise StoragePermissionError(
                message=f"Permission denied storing file into {storage_key}: {e}",
                details={"storage_key": storage_key},
            ) from e
        except Exception as e:
            raise StorageError(
                message=f"Failed to commit file to storage: {e}",
                details={"storage_key": storage_key},
            ) from e

    @staticmethod
    def _write_bytes_sync(path: Path, data: bytes) -> None:
        """Synchronously write bytes, flush and fsync."""
        with open(path, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())

    @staticmethod
    def _write_file_obj_sync(path: Path, src_file: BinaryIO, chunk_size: int = 64 * 1024) -> None:
        """Synchronously write binary stream in chunks."""
        with open(path, "wb") as dest:
            while chunk := src_file.read(chunk_size):
                dest.write(chunk)
            dest.flush()
            os.fsync(dest.fileno())

    @staticmethod
    async def _write_async_stream(path: Path, stream: AsyncIterable[bytes]) -> None:
        """Write async byte stream to file."""
        def _open_file():
            return open(path, "wb")

        f = await asyncio.to_thread(_open_file)
        try:
            async for chunk in stream:
                if chunk:
                    await asyncio.to_thread(f.write, chunk)
            await asyncio.to_thread(f.flush)
            await asyncio.to_thread(os.fsync, f.fileno())
        finally:
            await asyncio.to_thread(f.close)

    async def download(self, storage_key: str) -> bytes:
        """Read and return entire file contents."""
        target_path = self.validate_storage_key(storage_key)

        if not target_path.exists() or not target_path.is_file():
            raise StorageNotFoundError(
                message=f"File not found for storage key '{storage_key}'",
                details={"storage_key": storage_key},
            )

        try:
            return await asyncio.to_thread(target_path.read_bytes)
        except PermissionError as e:
            raise StoragePermissionError(
                message="Permission denied reading storage object",
                details={"storage_key": storage_key},
            ) from e
        except Exception as e:
            raise StorageError(
                message=f"Failed to read file from storage: {str(e)}",
                details={"storage_key": storage_key},
            ) from e

    async def download_stream(
        self,
        storage_key: str,
        chunk_size: int = 64 * 1024,
    ) -> AsyncIterator[bytes]:
        """Stream file in chunks."""
        target_path = self.validate_storage_key(storage_key)

        if not target_path.exists() or not target_path.is_file():
            raise StorageNotFoundError(
                message=f"File not found for storage key '{storage_key}'",
                details={"storage_key": storage_key},
            )

        def _open_file():
            return open(target_path, "rb")

        f = await asyncio.to_thread(_open_file)
        try:
            while True:
                chunk = await asyncio.to_thread(f.read, chunk_size)
                if not chunk:
                    break
                yield chunk
        finally:
            await asyncio.to_thread(f.close)

    async def delete(self, storage_key: str) -> bool:
        """Safely delete file from storage. Returns True if deleted, False if non-existent."""
        target_path = self.validate_storage_key(storage_key)

        if not target_path.exists():
            return False

        try:
            await asyncio.to_thread(target_path.unlink)
            logger.debug(f"Deleted storage object at {storage_key}")
            return True
        except FileNotFoundError:
            return False
        except PermissionError as e:
            raise StoragePermissionError(
                message="Permission denied deleting storage object",
                details={"storage_key": storage_key},
            ) from e
        except Exception as e:
            raise StorageError(
                message=f"Failed to delete file from storage: {str(e)}",
                details={"storage_key": storage_key},
            ) from e

    async def exists(self, storage_key: str) -> bool:
        """Check if file exists at given storage key."""
        try:
            target_path = self.validate_storage_key(storage_key)
            return await asyncio.to_thread(target_path.is_file)
        except StorageValidationError:
            return False

    async def get_size(self, storage_key: str) -> int:
        """Return size in bytes of storage object."""
        target_path = self.validate_storage_key(storage_key)

        if not target_path.exists() or not target_path.is_file():
            raise StorageNotFoundError(
                message=f"File not found for storage key '{storage_key}'",
                details={"storage_key": storage_key},
            )

        try:
            stat = await asyncio.to_thread(target_path.stat)
            return stat.st_size
        except Exception as e:
            raise StorageError(
                message=f"Failed to get file size: {str(e)}",
                details={"storage_key": storage_key},
            ) from e

    async def get_metadata(self, storage_key: str) -> StorageMetadata:
        """Return safe metadata object without exposing server filesystem absolute paths."""
        target_path = self.validate_storage_key(storage_key)

        if not target_path.exists() or not target_path.is_file():
            raise StorageNotFoundError(
                message=f"File not found for storage key '{storage_key}'",
                details={"storage_key": storage_key},
            )

        try:
            stat = await asyncio.to_thread(target_path.stat)
            created_at = datetime.fromtimestamp(stat.st_ctime, timezone.utc)
            modified_at = datetime.fromtimestamp(stat.st_mtime, timezone.utc)
            mime_guess, _ = mimetypes.guess_type(storage_key)

            return StorageMetadata(
                storage_key=storage_key,
                size_bytes=stat.st_size,
                created_at=created_at,
                modified_at=modified_at,
                mime_type_guess=mime_guess,
            )
        except Exception as e:
            raise StorageError(
                message=f"Failed to get file metadata: {str(e)}",
                details={"storage_key": storage_key},
            ) from e


@lru_cache()
def get_storage_service() -> StorageService:
    """Singleton factory providing the configured StorageService instance."""
    settings = get_settings()
    if settings.STORAGE_TYPE.lower() == "local":
        return LocalStorageService(base_path=settings.STORAGE_PATH)
    else:
        # Fallback or future S3
        logger.warning(
            f"Storage type '{settings.STORAGE_TYPE}' not yet implemented. Defaulting to LocalStorageService."
        )
        return LocalStorageService(base_path=settings.STORAGE_PATH)
