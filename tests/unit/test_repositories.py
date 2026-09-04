"""Unit tests for BaseRepository validation, pagination, and sorting."""

from bson import ObjectId
import pytest

from app.core.exceptions import ValidationError
from app.database.repositories.base import BaseRepository


def test_validate_object_id_valid():
    """Test validate_object_id with valid 24-character hexadecimal strings and ObjectIds."""
    valid_hex = "65f1a2b3c4d5e6f7a8b9c0d1"
    res = BaseRepository.validate_object_id(valid_hex)
    assert isinstance(res, ObjectId)
    assert str(res) == valid_hex

    # Existing ObjectId input
    obj_id = ObjectId()
    assert BaseRepository.validate_object_id(obj_id) is obj_id


def test_validate_object_id_invalid():
    """Test validate_object_id with invalid formats raises ValidationError."""
    with pytest.raises(ValidationError) as exc:
        BaseRepository.validate_object_id("not-an-id")
    assert "Invalid id format" in exc.value.message

    with pytest.raises(ValidationError):
        BaseRepository.validate_object_id("")

    with pytest.raises(ValidationError):
        BaseRepository.validate_object_id(12345)


def test_sanitize_pagination_bounds():
    """Test sanitize_pagination clamps within [1, MAX_LIMIT] and non-negative offsets."""
    # Defaults
    limit, offset = BaseRepository.sanitize_pagination(None, None)
    assert limit == BaseRepository.DEFAULT_LIMIT
    assert offset == 0

    # Negative / zero limit clamps to default
    limit, offset = BaseRepository.sanitize_pagination(-10, -5)
    assert limit == BaseRepository.DEFAULT_LIMIT
    assert offset == 0

    # Upper limit bound clamping
    limit, offset = BaseRepository.sanitize_pagination(500, 10)
    assert limit == BaseRepository.MAX_LIMIT
    assert offset == 10


def test_sanitize_sort_whitelisting():
    """Test sort field validation against controlled whitelist."""
    allowed = {"created_at", "updated_at", "file_size"}

    # Valid sort field
    sort_spec = BaseRepository.sanitize_sort("file_size", True, allowed)
    assert sort_spec == [("file_size", -1)]

    # Default field
    sort_spec = BaseRepository.sanitize_sort(None, False, allowed)
    assert sort_spec == [("created_at", 1)]

    # Invalid injected field
    with pytest.raises(ValidationError) as exc:
        BaseRepository.sanitize_sort("injected_admin_field", True, allowed)
    assert "Invalid sort field" in exc.value.message


def test_format_doc_conversion():
    """Test _id to id string normalization."""
    obj_id = ObjectId()
    raw_doc = {"_id": obj_id, "name": "sample", "count": 10}
    formatted = BaseRepository.format_doc(raw_doc)

    assert formatted is not None
    assert "id" in formatted
    assert formatted["id"] == str(obj_id)
    assert "_id" not in formatted
    assert formatted["name"] == "sample"

    # None document
    assert BaseRepository.format_doc(None) is None
