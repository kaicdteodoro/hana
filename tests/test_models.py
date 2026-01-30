"""Tests for hana.models."""

import pytest

from hana.models import (
    Action,
    Descriptions,
    GalleryItem,
    LedgerEntry,
    ManifestMeta,
    MediaInfo,
    MediaLedgerEntry,
    ProductInfo,
    ProductManifest,
    Reason,
    SKUResult,
    Status,
    Timings,
)


class TestProductManifest:
    def test_from_dict_minimal(self):
        data = {
            "sku": "TEST-001",
            "meta": {"schema_version": "1.0"},
            "product": {"title": "Test Product"},
        }
        manifest = ProductManifest.from_dict(data)

        assert manifest.sku == "TEST-001"
        assert manifest.meta.schema_version == "1.0"
        assert manifest.product.title == "Test Product"
        assert manifest.product.status == Status.DRAFT

    def test_from_dict_full(self):
        data = {
            "sku": "TEST-002",
            "meta": {
                "schema_version": "1.0",
                "source": "test",
                "generated_at": "2024-01-01T00:00:00Z",
            },
            "product": {
                "title": "Full Product",
                "slug": "full-product",
                "status": "publish",
            },
            "taxonomy": {
                "categoria-produto": ["cat1", "cat2"],
            },
            "descriptions": {
                "short": "Short desc",
                "technical": "Tech desc",
            },
            "attributes": {
                "available_colors": ["red", "blue"],
            },
            "media": {
                "featured": "images/featured.jpg",
                "gallery": [
                    {"file": "images/1.jpg", "checksum": "abc123"},
                    {"file": "images/2.jpg"},
                ],
            },
        }
        manifest = ProductManifest.from_dict(data)

        assert manifest.sku == "TEST-002"
        assert manifest.product.status == Status.PUBLISH
        assert manifest.product.slug == "full-product"
        assert manifest.taxonomy["categoria-produto"] == ("cat1", "cat2")
        assert manifest.descriptions.short == "Short desc"
        assert manifest.attributes["available_colors"] == ("red", "blue")
        assert manifest.media.featured == "images/featured.jpg"
        assert len(manifest.media.gallery) == 2
        assert manifest.media.gallery[0].checksum == "abc123"


class TestSKUResult:
    def test_to_dict(self):
        result = SKUResult(
            sku="TEST-001",
            action=Action.CREATED,
            post_id=123,
            warnings=["warn1"],
            timings=Timings(total_ms=100),
        )
        d = result.to_dict()

        assert d["sku"] == "TEST-001"
        assert d["action"] == "created"
        assert d["post_id"] == 123
        assert d["warnings"] == ["warn1"]
        assert d["timings"]["total_ms"] == 100


class TestLedgerEntry:
    def test_round_trip(self):
        entry = LedgerEntry(
            sku="TEST-001",
            hash="abc123",
            action="created",
            status="success",
            timestamp="2024-01-01T00:00:00Z",
            post_id=123,
        )
        d = entry.to_dict()
        restored = LedgerEntry.from_dict(d)

        assert restored.sku == entry.sku
        assert restored.hash == entry.hash
        assert restored.action == entry.action
        assert restored.post_id == entry.post_id


class TestMediaLedgerEntry:
    def test_round_trip(self):
        entry = MediaLedgerEntry(
            checksum="abc123",
            attachment_id=456,
            filename="test.jpg",
            uploaded_at="2024-01-01T00:00:00Z",
        )
        d = entry.to_dict()
        restored = MediaLedgerEntry.from_dict(d)

        assert restored.checksum == entry.checksum
        assert restored.attachment_id == entry.attachment_id
        assert restored.filename == entry.filename
