"""
hana.media — Media handling and deduplication.

Manages media uploads with deduplication strategies.
"""

import hashlib
from pathlib import Path
from typing import Any

from hana.config import DedupStrategy, FeaturedPolicy, HanaConfig, OrphanPolicy
from hana.errors import MediaError
from hana.ledger import MediaLedger
from hana.logger import get_logger
from hana.models import GalleryItem, MediaInfo
from hana.wordpress import WordPressClient


def compute_checksum(file_path: Path, algorithm: str = "sha256") -> str:
    """Compute file checksum."""
    hasher = hashlib.new(algorithm)
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


class MediaHandler:
    """Handles media upload and deduplication."""

    def __init__(
        self,
        config: HanaConfig,
        wp_client: WordPressClient,
        media_ledger: MediaLedger,
        catalog_root: Path,
    ):
        self._config = config
        self._wp = wp_client
        self._ledger = media_ledger
        self._catalog_root = catalog_root
        self._logger = get_logger()

    def resolve_featured_image(
        self,
        sku: str,
        media_info: MediaInfo,
    ) -> str | None:
        """
        Resolve the featured image path.

        Returns:
            Path to featured image, or None if not applicable.

        Raises:
            MediaError: If featured_policy is error and no featured image.
        """
        if media_info.featured:
            return media_info.featured

        policy = self._config.media.featured_policy

        if policy == FeaturedPolicy.ERROR:
            raise MediaError(
                sku=sku,
                stage="featured_resolve",
                message="Featured image is required but not provided",
                payload={"policy": policy.value},
            )

        if policy == FeaturedPolicy.FIRST_GALLERY:
            if media_info.gallery:
                return media_info.gallery[0].file
            return None

        if policy == FeaturedPolicy.ALLOW_NULL:
            return None

        return None

    def get_file_path(self, sku: str, relative_path: str) -> Path:
        """Get absolute path for a media file."""
        sku_dir = self._catalog_root / sku
        return sku_dir / relative_path

    def find_existing_media(
        self, sku: str, file_path: Path, checksum: str | None
    ) -> int | None:
        """
        Find existing media using configured dedup strategy.

        Returns:
            Attachment ID if found, None otherwise.
        """
        strategy = self._config.media.dedup_strategy

        if strategy == DedupStrategy.CHECKSUM_META:
            if not checksum:
                checksum = compute_checksum(
                    file_path, self._config.media.checksum_algorithm
                )
            media = self._wp.find_media_by_checksum(sku, checksum)
            if media:
                return media["id"]

        elif strategy == DedupStrategy.FILENAME:
            media = self._wp.find_media_by_filename(sku, file_path.name)
            if media:
                return media["id"]

        elif strategy == DedupStrategy.LOCAL_LEDGER:
            if not checksum:
                checksum = compute_checksum(
                    file_path, self._config.media.checksum_algorithm
                )
            attachment_id = self._ledger.get_attachment_id(checksum)
            if attachment_id:
                return attachment_id

        return None

    def upload_media(
        self,
        sku: str,
        file_path: Path,
        checksum: str | None = None,
    ) -> int:
        """
        Upload media file with deduplication.

        Returns:
            Attachment ID.
        """
        if not checksum:
            checksum = compute_checksum(file_path, self._config.media.checksum_algorithm)

        existing_id = self.find_existing_media(sku, file_path, checksum)
        if existing_id:
            self._logger.debug(
                f"Media already exists: {file_path.name}",
                sku=sku,
                stage="media_upload",
                attachment_id=existing_id,
            )
            return existing_id

        media = self._wp.upload_media(sku, file_path, checksum)
        attachment_id = media["id"]

        if self._config.media.dedup_strategy == DedupStrategy.LOCAL_LEDGER:
            self._ledger.record(checksum, attachment_id, file_path.name)

        self._logger.info(
            f"Uploaded media: {file_path.name}",
            sku=sku,
            stage="media_upload",
            attachment_id=attachment_id,
        )

        return attachment_id

    def process_gallery(
        self,
        sku: str,
        gallery: tuple[GalleryItem, ...],
        existing_ids: list[int] | None = None,
    ) -> tuple[list[int], list[str]]:
        """
        Process gallery items and upload as needed.

        Returns:
            Tuple of (attachment_ids, warnings)
        """
        attachment_ids = []
        warnings = []
        existing_set = set(existing_ids or [])

        for item in gallery:
            file_path = self.get_file_path(sku, item.file)

            if not file_path.exists():
                warnings.append(f"Gallery file not found: {item.file}")
                continue

            try:
                attachment_id = self.upload_media(sku, file_path, item.checksum)
                attachment_ids.append(attachment_id)
            except MediaError as e:
                warnings.append(f"Failed to upload {item.file}: {e.message}")

        return attachment_ids, warnings

    def cleanup_orphans(
        self,
        sku: str,
        old_ids: list[int],
        new_ids: list[int],
    ) -> list[str]:
        """
        Clean up orphaned media based on orphan_policy.

        Returns:
            List of warnings.
        """
        warnings = []
        orphan_ids = set(old_ids) - set(new_ids)

        if not orphan_ids:
            return warnings

        policy = self._config.media.orphan_policy

        for media_id in orphan_ids:
            if policy == OrphanPolicy.DELETE:
                try:
                    self._wp.delete_media(sku, media_id)
                    self._logger.debug(
                        f"Deleted orphan media: {media_id}",
                        sku=sku,
                        stage="media_cleanup",
                    )
                except Exception as e:
                    warnings.append(f"Failed to delete media {media_id}: {e}")
            else:
                self._logger.debug(
                    f"Detached orphan media: {media_id}",
                    sku=sku,
                    stage="media_cleanup",
                )

        return warnings
