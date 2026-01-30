"""
hana.errors — Typed error model for the ingestion engine.

All errors are explicitly typed and include:
- sku: affected SKU
- stage: pipeline stage where error occurred
- http_status: HTTP status code (if applicable)
- payload: snapshot of relevant data
- retryable: whether the operation can be retried
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class HanaError(Exception):
    """Base error for all hana errors."""
    sku: str
    stage: str
    message: str
    http_status: int | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    retryable: bool = False

    def __str__(self) -> str:
        return f"[{self.stage}] SKU={self.sku}: {self.message}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.__class__.__name__,
            "sku": self.sku,
            "stage": self.stage,
            "message": self.message,
            "http_status": self.http_status,
            "payload": self.payload,
            "retryable": self.retryable,
        }


@dataclass(frozen=True)
class ValidationError(HanaError):
    """Manifest or payload validation failed."""
    pass


@dataclass(frozen=True)
class ConflictError(HanaError):
    """SKU or slug conflict detected."""
    pass


@dataclass(frozen=True)
class NotFoundError(HanaError):
    """Required resource not found."""
    pass


@dataclass(frozen=True)
class AuthError(HanaError):
    """Authentication or authorization failed."""
    pass


@dataclass(frozen=True)
class TaxonomyError(HanaError):
    """Taxonomy term resolution failed."""
    pass


@dataclass(frozen=True)
class MediaError(HanaError):
    """Media upload or processing failed."""
    pass


@dataclass(frozen=True)
class ConcurrencyError(HanaError):
    """Lock acquisition or concurrency conflict."""
    pass


@dataclass(frozen=True)
class LedgerError(HanaError):
    """Ledger read/write or corruption error."""
    pass


@dataclass(frozen=True)
class TransportError(HanaError):
    """Network or HTTP transport error."""
    retryable: bool = True


ERROR_TYPES = {
    "ValidationError": ValidationError,
    "ConflictError": ConflictError,
    "NotFoundError": NotFoundError,
    "AuthError": AuthError,
    "TaxonomyError": TaxonomyError,
    "MediaError": MediaError,
    "ConcurrencyError": ConcurrencyError,
    "LedgerError": LedgerError,
    "TransportError": TransportError,
}
