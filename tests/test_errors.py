"""Tests for hana.errors."""

import pytest

from hana.errors import (
    AuthError,
    ConcurrencyError,
    ConflictError,
    HanaError,
    LedgerError,
    MediaError,
    NotFoundError,
    TaxonomyError,
    TransportError,
    ValidationError,
)


class TestHanaError:
    def test_str_representation(self):
        error = HanaError(
            sku="TEST-001",
            stage="validation",
            message="Test error message",
        )
        assert str(error) == "[validation] SKU=TEST-001: Test error message"

    def test_to_dict(self):
        error = HanaError(
            sku="TEST-001",
            stage="validation",
            message="Test error",
            http_status=400,
            payload={"field": "value"},
            retryable=True,
        )
        d = error.to_dict()

        assert d["type"] == "HanaError"
        assert d["sku"] == "TEST-001"
        assert d["stage"] == "validation"
        assert d["message"] == "Test error"
        assert d["http_status"] == 400
        assert d["payload"] == {"field": "value"}
        assert d["retryable"] is True


class TestTypedErrors:
    def test_validation_error(self):
        error = ValidationError(
            sku="SKU-001",
            stage="manifest",
            message="Invalid manifest",
        )
        assert error.to_dict()["type"] == "ValidationError"
        assert error.retryable is False

    def test_conflict_error(self):
        error = ConflictError(
            sku="SKU-001",
            stage="create",
            message="SKU already exists",
        )
        assert error.to_dict()["type"] == "ConflictError"

    def test_not_found_error(self):
        error = NotFoundError(
            sku="SKU-001",
            stage="update",
            message="SKU not found",
        )
        assert error.to_dict()["type"] == "NotFoundError"

    def test_auth_error(self):
        error = AuthError(
            sku="SKU-001",
            stage="api",
            message="Authentication failed",
            http_status=401,
        )
        assert error.to_dict()["type"] == "AuthError"
        assert error.http_status == 401

    def test_taxonomy_error(self):
        error = TaxonomyError(
            sku="SKU-001",
            stage="taxonomy",
            message="Term not found",
        )
        assert error.to_dict()["type"] == "TaxonomyError"

    def test_media_error(self):
        error = MediaError(
            sku="SKU-001",
            stage="upload",
            message="Upload failed",
        )
        assert error.to_dict()["type"] == "MediaError"

    def test_concurrency_error(self):
        error = ConcurrencyError(
            sku="SKU-001",
            stage="lock",
            message="Lock timeout",
        )
        assert error.to_dict()["type"] == "ConcurrencyError"

    def test_ledger_error(self):
        error = LedgerError(
            sku="SKU-001",
            stage="ledger",
            message="Corrupt ledger",
        )
        assert error.to_dict()["type"] == "LedgerError"

    def test_transport_error_default_retryable(self):
        error = TransportError(
            sku="SKU-001",
            stage="api",
            message="Connection timeout",
        )
        assert error.to_dict()["type"] == "TransportError"
        assert error.retryable is True
