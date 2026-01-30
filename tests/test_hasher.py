"""Tests for hana.hasher."""

import pytest

from hana.hasher import compute_manifest_hash, compute_payload_hash
from hana.models import ProductManifest


class TestComputeManifestHash:
    def test_deterministic(self):
        data = {
            "sku": "TEST-001",
            "meta": {"schema_version": "1.0"},
            "product": {"title": "Test Product"},
        }
        manifest = ProductManifest.from_dict(data)

        hash1 = compute_manifest_hash(manifest)
        hash2 = compute_manifest_hash(manifest)

        assert hash1 == hash2
        assert len(hash1) == 64  # SHA256 hex

    def test_different_content_different_hash(self):
        data1 = {
            "sku": "TEST-001",
            "meta": {"schema_version": "1.0"},
            "product": {"title": "Product A"},
        }
        data2 = {
            "sku": "TEST-001",
            "meta": {"schema_version": "1.0"},
            "product": {"title": "Product B"},
        }

        manifest1 = ProductManifest.from_dict(data1)
        manifest2 = ProductManifest.from_dict(data2)

        hash1 = compute_manifest_hash(manifest1)
        hash2 = compute_manifest_hash(manifest2)

        assert hash1 != hash2

    def test_same_content_same_hash(self):
        data = {
            "sku": "TEST-001",
            "meta": {"schema_version": "1.0"},
            "product": {"title": "Test Product"},
            "taxonomy": {"cat": ["a", "b"]},
        }

        manifest1 = ProductManifest.from_dict(data)
        manifest2 = ProductManifest.from_dict(data.copy())

        hash1 = compute_manifest_hash(manifest1)
        hash2 = compute_manifest_hash(manifest2)

        assert hash1 == hash2


class TestComputePayloadHash:
    def test_deterministic(self):
        payload = {"title": "Test", "status": "publish"}

        hash1 = compute_payload_hash(payload)
        hash2 = compute_payload_hash(payload)

        assert hash1 == hash2

    def test_order_independent(self):
        payload1 = {"a": 1, "b": 2, "c": 3}
        payload2 = {"c": 3, "a": 1, "b": 2}

        hash1 = compute_payload_hash(payload1)
        hash2 = compute_payload_hash(payload2)

        assert hash1 == hash2

    def test_nested_order_independent(self):
        payload1 = {"outer": {"a": 1, "b": 2}}
        payload2 = {"outer": {"b": 2, "a": 1}}

        hash1 = compute_payload_hash(payload1)
        hash2 = compute_payload_hash(payload2)

        assert hash1 == hash2
