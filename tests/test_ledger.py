"""Tests for hana.ledger."""

import json
import pytest
import tempfile
from pathlib import Path

from hana.config import CorruptionPolicy
from hana.errors import LedgerError
from hana.ledger import ExecutionLedger, MediaLedger


class TestExecutionLedger:
    def test_record_and_get(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "ledger.jsonl"
            ledger = ExecutionLedger(path, CorruptionPolicy.FAIL)

            ledger.record(
                sku="TEST-001",
                hash_value="abc123",
                action="created",
                status="success",
                post_id=123,
            )

            entry = ledger.get("TEST-001")

            assert entry is not None
            assert entry.sku == "TEST-001"
            assert entry.hash == "abc123"
            assert entry.post_id == 123

    def test_get_hash(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "ledger.jsonl"
            ledger = ExecutionLedger(path, CorruptionPolicy.FAIL)

            ledger.record(
                sku="TEST-001",
                hash_value="abc123",
                action="created",
                status="success",
            )

            assert ledger.get_hash("TEST-001") == "abc123"
            assert ledger.get_hash("NONEXISTENT") is None

    def test_persistence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "ledger.jsonl"

            ledger1 = ExecutionLedger(path, CorruptionPolicy.FAIL)
            ledger1.record(
                sku="TEST-001",
                hash_value="abc123",
                action="created",
                status="success",
            )

            ledger2 = ExecutionLedger(path, CorruptionPolicy.FAIL)
            ledger2.load()

            entry = ledger2.get("TEST-001")
            assert entry is not None
            assert entry.hash == "abc123"

    def test_corrupt_line_fail(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "ledger.jsonl"
            path.write_text("invalid json\n")

            ledger = ExecutionLedger(path, CorruptionPolicy.FAIL)

            with pytest.raises(LedgerError):
                ledger.load()

    def test_corrupt_line_ignore(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "ledger.jsonl"

            valid_entry = {
                "sku": "TEST-001",
                "hash": "abc",
                "action": "created",
                "status": "success",
                "timestamp": "2024-01-01T00:00:00Z",
            }
            path.write_text(f"invalid json\n{json.dumps(valid_entry)}\n")

            ledger = ExecutionLedger(path, CorruptionPolicy.IGNORE_CORRUPT_LINES)
            ledger.load()

            assert ledger.get("TEST-001") is not None

    def test_get_incomplete_skus(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "ledger.jsonl"
            ledger = ExecutionLedger(path, CorruptionPolicy.FAIL)

            ledger.record("SKU-1", "hash1", "created", "success", incomplete=False)
            ledger.record("SKU-2", "hash2", "failed", "error", incomplete=True)
            ledger.record("SKU-3", "hash3", "failed", "error", incomplete=True)

            incomplete = ledger.get_incomplete_skus()

            assert "SKU-1" not in incomplete
            assert "SKU-2" in incomplete
            assert "SKU-3" in incomplete


class TestMediaLedger:
    def test_record_and_get(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "media.json"
            ledger = MediaLedger(path)

            ledger.record("abc123", 456, "test.jpg")

            entry = ledger.get("abc123")

            assert entry is not None
            assert entry.attachment_id == 456
            assert entry.filename == "test.jpg"

    def test_get_attachment_id(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "media.json"
            ledger = MediaLedger(path)

            ledger.record("abc123", 456, "test.jpg")

            assert ledger.get_attachment_id("abc123") == 456
            assert ledger.get_attachment_id("nonexistent") is None

    def test_persistence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "media.json"

            ledger1 = MediaLedger(path)
            ledger1.record("abc123", 456, "test.jpg")
            ledger1.save()

            ledger2 = MediaLedger(path)
            ledger2.load()

            assert ledger2.get_attachment_id("abc123") == 456
