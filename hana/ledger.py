"""
hana.ledger — Execution and media ledger management.

Append-only ledgers for tracking execution state and media mappings.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from hana.config import CorruptionPolicy, HanaConfig
from hana.errors import LedgerError
from hana.logger import get_logger
from hana.models import LedgerEntry, MediaLedgerEntry


class ExecutionLedger:
    """Append-only execution ledger for tracking SKU processing state."""

    def __init__(self, path: Path, corruption_policy: CorruptionPolicy):
        self._path = path
        self._corruption_policy = corruption_policy
        self._entries: dict[str, LedgerEntry] = {}
        self._dirty = False

    def load(self) -> None:
        """Load ledger from disk."""
        if not self._path.exists():
            return

        logger = get_logger()
        line_num = 0
        corrupt_count = 0

        with open(self._path, "r", encoding="utf-8") as f:
            for line in f:
                line_num += 1
                line = line.strip()
                if not line:
                    continue

                try:
                    data = json.loads(line)
                    entry = LedgerEntry.from_dict(data)
                    self._entries[entry.sku] = entry
                except (json.JSONDecodeError, KeyError, TypeError) as e:
                    corrupt_count += 1

                    if self._corruption_policy == CorruptionPolicy.FAIL:
                        raise LedgerError(
                            sku="",
                            stage="ledger_load",
                            message=f"Corrupt ledger entry at line {line_num}: {e}",
                            payload={"line": line, "line_num": line_num},
                        )
                    elif self._corruption_policy == CorruptionPolicy.IGNORE_CORRUPT_LINES:
                        logger.warn(
                            f"Skipping corrupt ledger entry at line {line_num}",
                            stage="ledger_load",
                            line_num=line_num,
                            error=str(e),
                        )

        if corrupt_count > 0:
            logger.warn(
                f"Loaded ledger with {corrupt_count} corrupt entries skipped",
                stage="ledger_load",
                corrupt_count=corrupt_count,
            )

    def get(self, sku: str) -> LedgerEntry | None:
        """Get ledger entry for a SKU."""
        return self._entries.get(sku)

    def get_hash(self, sku: str) -> str | None:
        """Get the last recorded hash for a SKU."""
        entry = self._entries.get(sku)
        return entry.hash if entry else None

    def get_incomplete_skus(self) -> list[str]:
        """Get list of SKUs marked as incomplete."""
        return [sku for sku, entry in self._entries.items() if entry.incomplete]

    def record(
        self,
        sku: str,
        hash_value: str,
        action: str,
        status: str,
        post_id: int | None = None,
        incomplete: bool = False,
    ) -> None:
        """Record a new ledger entry."""
        entry = LedgerEntry(
            sku=sku,
            hash=hash_value,
            action=action,
            status=status,
            timestamp=datetime.now(timezone.utc).isoformat(),
            post_id=post_id,
            incomplete=incomplete,
        )
        self._entries[sku] = entry
        self._dirty = True

        self._append_to_file(entry)

    def _append_to_file(self, entry: LedgerEntry) -> None:
        """Append entry to ledger file."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")

    def flush(self) -> None:
        """Flush any pending writes. Currently writes are immediate."""
        pass

    def compact(self) -> None:
        """Compact the ledger by rewriting with only latest entries per SKU."""
        if not self._entries:
            return

        temp_path = self._path.with_suffix(".tmp")
        with open(temp_path, "w", encoding="utf-8") as f:
            for entry in sorted(self._entries.values(), key=lambda e: e.sku):
                f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")

        temp_path.replace(self._path)


class MediaLedger:
    """Ledger for tracking checksum to attachment ID mappings."""

    def __init__(self, path: Path):
        self._path = path
        self._entries: dict[str, MediaLedgerEntry] = {}
        self._dirty = False

    def load(self) -> None:
        """Load media ledger from disk."""
        if not self._path.exists():
            return

        with open(self._path, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
                for checksum, entry_data in data.items():
                    self._entries[checksum] = MediaLedgerEntry.from_dict(entry_data)
            except (json.JSONDecodeError, KeyError, TypeError):
                pass

    def get(self, checksum: str) -> MediaLedgerEntry | None:
        """Get attachment info for a checksum."""
        return self._entries.get(checksum)

    def get_attachment_id(self, checksum: str) -> int | None:
        """Get attachment ID for a checksum."""
        entry = self._entries.get(checksum)
        return entry.attachment_id if entry else None

    def record(
        self,
        checksum: str,
        attachment_id: int,
        filename: str,
    ) -> None:
        """Record a new media mapping."""
        entry = MediaLedgerEntry(
            checksum=checksum,
            attachment_id=attachment_id,
            filename=filename,
            uploaded_at=datetime.now(timezone.utc).isoformat(),
        )
        self._entries[checksum] = entry
        self._dirty = True

    def save(self) -> None:
        """Save media ledger to disk."""
        if not self._dirty:
            return

        self._path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            checksum: entry.to_dict() for checksum, entry in self._entries.items()
        }

        temp_path = self._path.with_suffix(".tmp")
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        temp_path.replace(self._path)
        self._dirty = False

    def flush(self) -> None:
        """Alias for save."""
        self.save()


def create_execution_ledger(config: HanaConfig) -> ExecutionLedger:
    """Create an execution ledger from configuration."""
    path = Path(config.ledger.path)
    ledger = ExecutionLedger(path, config.ledger.corruption_policy)
    ledger.load()
    return ledger


def create_media_ledger(config: HanaConfig) -> MediaLedger:
    """Create a media ledger from configuration."""
    path = Path(config.media.media_ledger_path)
    ledger = MediaLedger(path)
    ledger.load()
    return ledger
