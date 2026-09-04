"""Base asynchronous MongoDB repository with validation, bounded pagination, and sort whitelisting."""

from typing import Any, Dict, List, Optional, Set, Tuple
from bson import ObjectId
from bson.errors import InvalidId
from pymongo import ASCENDING, DESCENDING
from pymongo.asynchronous.collection import AsyncCollection
from pymongo.asynchronous.database import AsyncDatabase

from app.core.exceptions import ResourceNotFoundError, ValidationError


class BaseRepository:
    """Base repository providing validated BSON operations, bounded pagination, and safe sorting."""

    DEFAULT_LIMIT: int = 20
    MAX_LIMIT: int = 100

    def __init__(self, db: AsyncDatabase, collection_name: str) -> None:
        self.db = db
        self.collection_name = collection_name
        self.collection: AsyncCollection = db[collection_name]

    @staticmethod
    def validate_object_id(id_val: Any, field_name: str = "id") -> ObjectId:
        """Validate and convert an input string or ObjectId to a valid BSON ObjectId.

        Raises ValidationError on invalid format instead of unhandled BSON InvalidId.
        """
        if isinstance(id_val, ObjectId):
            return id_val
        if not id_val or not isinstance(id_val, str):
            raise ValidationError(
                message=f"Invalid {field_name}: Must be a non-empty 24-character hexadecimal string.",
                details={"field": field_name, "value": str(id_val)},
            )
        try:
            return ObjectId(id_val)
        except (InvalidId, TypeError) as e:
            raise ValidationError(
                message=f"Invalid {field_name} format: '{id_val}' is not a valid ObjectId.",
                details={"field": field_name, "value": str(id_val)},
            ) from e

    @classmethod
    def sanitize_pagination(
        cls,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> Tuple[int, int]:
        """Enforce strict lower and upper bounds on limit and offset."""
        sanitized_limit = cls.DEFAULT_LIMIT if limit is None else limit
        sanitized_offset = 0 if offset is None else offset

        if sanitized_limit < 1:
            sanitized_limit = cls.DEFAULT_LIMIT
        elif sanitized_limit > cls.MAX_LIMIT:
            sanitized_limit = cls.MAX_LIMIT

        if sanitized_offset < 0:
            sanitized_offset = 0

        return sanitized_limit, sanitized_offset

    @staticmethod
    def sanitize_sort(
        sort_by: Optional[str],
        sort_desc: bool,
        allowed_sort_fields: Set[str],
        default_field: str = "created_at",
    ) -> List[Tuple[str, int]]:
        """Validate sort field against a controlled whitelist to prevent arbitrary field injection."""
        field = default_field
        if sort_by and sort_by in allowed_sort_fields:
            field = sort_by
        elif sort_by and sort_by not in allowed_sort_fields:
            raise ValidationError(
                message=f"Invalid sort field '{sort_by}'. Allowed fields: {sorted(allowed_sort_fields)}",
                details={"sort_by": sort_by, "allowed_fields": list(allowed_sort_fields)},
            )

        direction = DESCENDING if sort_desc else ASCENDING
        return [(field, direction)]

    @staticmethod
    def format_doc(doc: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Normalize BSON document by converting _id to id string."""
        if doc is None:
            return None
        doc_copy = dict(doc)
        if "_id" in doc_copy:
            doc_copy["id"] = str(doc_copy.pop("_id"))
        return doc_copy

    @classmethod
    def format_docs(cls, docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Normalize a list of BSON documents."""
        return [cls.format_doc(d) for d in docs if d is not None]  # type: ignore
