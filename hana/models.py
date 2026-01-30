"""
hana.models — Domain models for the ingestion engine.

ProductManifest is the canonical representation of a product to be ingested.
All fields follow explicit absence/null/empty semantics.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class Action(str, Enum):
    CREATED = "created"
    UPDATED = "updated"
    SKIPPED = "skipped"
    FAILED = "failed"
    WOULD_CREATE = "would_create"
    WOULD_UPDATE = "would_update"
    WOULD_SKIP = "would_skip"


class Reason(str, Enum):
    NOOP = "noop"
    CONFLICT = "conflict"
    ERROR = "error"
    PARTIAL = "partial"
    BACKPRESSURE = "backpressure"


class Status(str, Enum):
    PUBLISH = "publish"
    DRAFT = "draft"


@dataclass(frozen=True)
class ManifestMeta:
    schema_version: str
    source: str | None = None
    generated_at: str | None = None


@dataclass(frozen=True)
class ProductInfo:
    title: str
    slug: str | None = None
    status: Status = Status.DRAFT


@dataclass(frozen=True)
class Descriptions:
    short: str | None = None
    technical: str | None = None


@dataclass(frozen=True)
class GalleryItem:
    file: str
    checksum: str | None = None


@dataclass(frozen=True)
class MediaInfo:
    featured: str | None = None
    gallery: tuple[GalleryItem, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ProductManifest:
    sku: str
    meta: ManifestMeta
    product: ProductInfo
    taxonomy: dict[str, tuple[str, ...]] = field(default_factory=dict)
    descriptions: Descriptions = field(default_factory=Descriptions)
    attributes: dict[str, tuple[str, ...]] = field(default_factory=dict)
    media: MediaInfo = field(default_factory=MediaInfo)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProductManifest":
        """Parse a manifest from a dictionary."""
        meta_data = data.get("meta", {})
        meta = ManifestMeta(
            schema_version=meta_data.get("schema_version", "1.0"),
            source=meta_data.get("source"),
            generated_at=meta_data.get("generated_at"),
        )

        product_data = data.get("product", {})
        product = ProductInfo(
            title=product_data.get("title", ""),
            slug=product_data.get("slug"),
            status=Status(product_data.get("status", "draft")),
        )

        desc_data = data.get("descriptions", {})
        descriptions = Descriptions(
            short=desc_data.get("short"),
            technical=desc_data.get("technical"),
        )

        media_data = data.get("media", {})
        gallery_items = tuple(
            GalleryItem(
                file=item.get("file", ""),
                checksum=item.get("checksum"),
            )
            for item in media_data.get("gallery", [])
        )
        media = MediaInfo(
            featured=media_data.get("featured"),
            gallery=gallery_items,
        )

        taxonomy = {
            k: tuple(v) if isinstance(v, list) else (v,)
            for k, v in data.get("taxonomy", {}).items()
        }

        attributes = {
            k: tuple(v) if isinstance(v, list) else (v,)
            for k, v in data.get("attributes", {}).items()
        }

        return cls(
            sku=data["sku"],
            meta=meta,
            product=product,
            taxonomy=taxonomy,
            descriptions=descriptions,
            attributes=attributes,
            media=media,
        )


@dataclass
class Timings:
    total_ms: int = 0
    lookup_ms: int = 0
    post_ms: int = 0
    media_ms: int = 0
    taxonomy_ms: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "total_ms": self.total_ms,
            "lookup_ms": self.lookup_ms,
            "post_ms": self.post_ms,
            "media_ms": self.media_ms,
            "taxonomy_ms": self.taxonomy_ms,
        }


@dataclass
class SKUResult:
    sku: str
    action: Action
    post_id: int | None = None
    reason: Reason | None = None
    warnings: list[str] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    timings: Timings = field(default_factory=Timings)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sku": self.sku,
            "action": self.action.value,
            "post_id": self.post_id,
            "reason": self.reason.value if self.reason else None,
            "warnings": self.warnings,
            "errors": self.errors,
            "timings": self.timings.to_dict(),
        }


@dataclass
class LedgerEntry:
    sku: str
    hash: str
    action: str
    status: str
    timestamp: str
    post_id: int | None = None
    incomplete: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "sku": self.sku,
            "hash": self.hash,
            "action": self.action,
            "status": self.status,
            "timestamp": self.timestamp,
            "post_id": self.post_id,
            "incomplete": self.incomplete,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LedgerEntry":
        return cls(
            sku=data["sku"],
            hash=data["hash"],
            action=data["action"],
            status=data["status"],
            timestamp=data["timestamp"],
            post_id=data.get("post_id"),
            incomplete=data.get("incomplete", False),
        )


@dataclass
class MediaLedgerEntry:
    checksum: str
    attachment_id: int
    filename: str
    uploaded_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "checksum": self.checksum,
            "attachment_id": self.attachment_id,
            "filename": self.filename,
            "uploaded_at": self.uploaded_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MediaLedgerEntry":
        return cls(
            checksum=data["checksum"],
            attachment_id=data["attachment_id"],
            filename=data["filename"],
            uploaded_at=data["uploaded_at"],
        )
