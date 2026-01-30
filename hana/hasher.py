"""
hana.hasher — Deterministic payload hashing for no-op detection.

Computes stable hashes of manifests for change detection.
"""

import hashlib
import json
from typing import Any

from hana.models import ProductManifest


def _normalize_value(value: Any) -> Any:
    """Normalize a value for stable hashing."""
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_normalize_value(v) for v in value]
    if isinstance(value, dict):
        return {k: _normalize_value(v) for k, v in sorted(value.items())}
    if hasattr(value, "__dict__"):
        return _normalize_value(vars(value))
    return str(value)


def compute_manifest_hash(manifest: ProductManifest) -> str:
    """
    Compute a deterministic hash of a product manifest.

    The hash is stable across runs if the content is the same.
    """
    normalized = {
        "sku": manifest.sku,
        "product": {
            "title": manifest.product.title,
            "slug": manifest.product.slug,
            "status": manifest.product.status.value,
        },
        "taxonomy": {k: list(v) for k, v in sorted(manifest.taxonomy.items())},
        "descriptions": {
            "short": manifest.descriptions.short,
            "technical": manifest.descriptions.technical,
        },
        "attributes": {k: list(v) for k, v in sorted(manifest.attributes.items())},
        "media": {
            "featured": manifest.media.featured,
            "gallery": [
                {"file": g.file, "checksum": g.checksum}
                for g in manifest.media.gallery
            ],
        },
    }

    canonical = json.dumps(normalized, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


def compute_payload_hash(payload: dict[str, Any]) -> str:
    """
    Compute a deterministic hash of an API payload.
    """
    normalized = _normalize_value(payload)
    canonical = json.dumps(normalized, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(canonical.encode()).hexdigest()
