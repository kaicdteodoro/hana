"""
hana.engine — Core ingestion engine.

Orchestrates the deterministic, idempotent ingestion pipeline.
"""

import json
import signal
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from hana.config import (
    ExecutionMode,
    FailurePolicy,
    HanaConfig,
    ImagePolicy,
    MediaFailurePolicy,
    MissingTermPolicy,
    NullPolicy,
    OrderingStrategy,
    SlugCollisionPolicy,
    SlugNullPolicy,
    TaxonomyFailurePolicy,
    UnknownVersionPolicy,
)
from hana.errors import (
    ConflictError,
    HanaError,
    MediaError,
    NotFoundError,
    TaxonomyError,
    TransportError,
    ValidationError,
)
from hana.hasher import compute_manifest_hash
from hana.ledger import ExecutionLedger, MediaLedger, create_execution_ledger, create_media_ledger
from hana.lock import LockManager
from hana.logger import get_logger
from hana.media import MediaHandler
from hana.models import Action, ProductManifest, Reason, SKUResult, Timings
from hana.rate_limiter import RateLimitedExecutor
from hana.wordpress import WordPressClient


class IngestionEngine:
    """Deterministic, idempotent WordPress catalog ingestion engine."""

    def __init__(self, config: HanaConfig):
        self._config = config
        self._logger = get_logger()
        self._wp: WordPressClient | None = None
        self._ledger: ExecutionLedger | None = None
        self._media_ledger: MediaLedger | None = None
        self._lock_manager: LockManager | None = None
        self._rate_limiter: RateLimitedExecutor | None = None
        self._media_handler: MediaHandler | None = None
        self._shutdown_requested = False
        self._results: list[SKUResult] = []

    def _setup(self) -> None:
        """Initialize all components."""
        self._wp = WordPressClient(self._config)
        self._ledger = create_execution_ledger(self._config)
        self._media_ledger = create_media_ledger(self._config)
        self._lock_manager = LockManager(self._config)
        self._rate_limiter = RateLimitedExecutor(self._config)
        self._media_handler = MediaHandler(
            self._config,
            self._wp,
            self._media_ledger,
            Path(self._config.paths.catalog_root),
        )

        if self._config.signals.graceful_shutdown:
            signal.signal(signal.SIGINT, self._handle_shutdown)
            signal.signal(signal.SIGTERM, self._handle_shutdown)

    def _teardown(self) -> None:
        """Clean up resources."""
        if self._lock_manager:
            self._lock_manager.release_all()
        if self._ledger:
            self._ledger.flush()
        if self._media_ledger:
            self._media_ledger.flush()
        if self._wp:
            self._wp.close()

    def _handle_shutdown(self, signum: int, frame: Any) -> None:
        """Handle shutdown signal."""
        self._logger.info(
            f"Shutdown signal received ({signum}), finishing current SKU...",
            stage="shutdown",
        )
        self._shutdown_requested = True

    def discover_manifests(self) -> Iterator[tuple[str, ProductManifest]]:
        """Discover and load manifests from catalog root."""
        catalog_root = Path(self._config.paths.catalog_root)

        if not catalog_root.exists():
            raise ValidationError(
                sku="",
                stage="discovery",
                message=f"Catalog root does not exist: {catalog_root}",
                payload={"catalog_root": str(catalog_root)},
            )

        sku_dirs = []
        for item in catalog_root.iterdir():
            if item.is_dir():
                manifest_path = item / "manifest.json"
                if manifest_path.exists():
                    sku_dirs.append((item.name, manifest_path))

        if self._config.ordering.strategy == OrderingStrategy.SKU_ASC:
            sku_dirs.sort(key=lambda x: x[0])
        elif self._config.ordering.strategy == OrderingStrategy.FILESYSTEM:
            sku_dirs.sort(key=lambda x: x[1].stat().st_mtime)

        for sku, manifest_path in sku_dirs:
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                manifest = ProductManifest.from_dict(data)

                if manifest.sku != sku:
                    self._logger.warn(
                        f"SKU mismatch: directory={sku}, manifest={manifest.sku}",
                        sku=sku,
                        stage="discovery",
                    )

                yield sku, manifest

            except (json.JSONDecodeError, KeyError, TypeError) as e:
                self._logger.error(
                    f"Failed to load manifest: {e}",
                    sku=sku,
                    stage="discovery",
                )

    def validate_manifest(self, manifest: ProductManifest) -> list[str]:
        """Validate a manifest and return list of errors."""
        errors = []

        if not manifest.sku:
            errors.append("SKU is required")

        if not manifest.product.title:
            errors.append("Product title is required")

        schema_version = manifest.meta.schema_version
        if schema_version not in self._config.schema.supported_versions:
            if self._config.schema.unknown_version_policy == UnknownVersionPolicy.FAIL:
                errors.append(f"Unsupported schema version: {schema_version}")

        return errors

    def _resolve_slug(self, manifest: ProductManifest, existing_post: dict | None) -> str | None:
        """Resolve the slug based on configuration."""
        slug = manifest.product.slug

        if slug is None:
            policy = self._config.slug.null_policy
            if policy == SlugNullPolicy.FROM_TITLE:
                slug = self._slugify(manifest.product.title)
            elif policy == SlugNullPolicy.FROM_SKU:
                slug = manifest.sku.lower()
            elif policy == SlugNullPolicy.ERROR:
                raise ValidationError(
                    sku=manifest.sku,
                    stage="slug_resolve",
                    message="Slug is required but not provided",
                    payload={"null_policy": policy.value},
                )

        return slug

    @staticmethod
    def _slugify(text: str) -> str:
        """Convert text to URL-safe slug."""
        import re
        import unicodedata

        text = unicodedata.normalize("NFKD", text)
        text = text.encode("ascii", "ignore").decode("ascii")
        text = re.sub(r"[^\w\s-]", "", text.lower())
        text = re.sub(r"[-\s]+", "-", text).strip("-")
        return text

    def _build_acf_payload(self, manifest: ProductManifest) -> dict[str, Any]:
        """Build ACF fields payload."""
        acf = {
            "codigo_sku": manifest.sku,
        }

        if manifest.attributes.get("available_colors"):
            acf["cores_disponiveis"] = [
                {"cor": color} for color in manifest.attributes["available_colors"]
            ]

        if manifest.descriptions.short is not None:
            acf["descricao_curta"] = manifest.descriptions.short

        if manifest.descriptions.technical is not None:
            acf["descricao_tecnica"] = manifest.descriptions.technical

        return acf

    def _process_sku(self, manifest: ProductManifest) -> SKUResult:
        """Process a single SKU."""
        sku = manifest.sku
        timings = Timings()
        warnings: list[str] = []
        start_time = time.monotonic()

        try:
            validation_errors = self.validate_manifest(manifest)
            if validation_errors:
                raise ValidationError(
                    sku=sku,
                    stage="validation",
                    message="; ".join(validation_errors),
                    payload={"errors": validation_errors},
                )

            lookup_start = time.monotonic()
            existing_post = self._wp.find_post_by_sku(sku)
            timings.lookup_ms = int((time.monotonic() - lookup_start) * 1000)

            mode = self._config.execution.mode

            if mode == ExecutionMode.CREATE and existing_post:
                raise ConflictError(
                    sku=sku,
                    stage="mode_check",
                    message="SKU already exists in create mode",
                    payload={"post_id": existing_post["id"]},
                )

            if mode == ExecutionMode.UPDATE and not existing_post:
                raise NotFoundError(
                    sku=sku,
                    stage="mode_check",
                    message="SKU not found in update mode",
                )

            manifest_hash = compute_manifest_hash(manifest)
            ledger_hash = self._ledger.get_hash(sku)

            if existing_post and manifest_hash == ledger_hash:
                timings.total_ms = int((time.monotonic() - start_time) * 1000)

                if self._config.execution.dry_run:
                    return SKUResult(
                        sku=sku,
                        action=Action.WOULD_SKIP,
                        post_id=existing_post["id"],
                        reason=Reason.NOOP,
                        timings=timings,
                    )

                return SKUResult(
                    sku=sku,
                    action=Action.SKIPPED,
                    post_id=existing_post["id"],
                    reason=Reason.NOOP,
                    timings=timings,
                )

            taxonomy_start = time.monotonic()
            taxonomy_terms: dict[str, list[int]] = {}

            for taxonomy, term_slugs in manifest.taxonomy.items():
                fallback = None
                if self._config.taxonomy.missing_term_policy == MissingTermPolicy.FALLBACK:
                    fallback = self._config.taxonomy.fallback

                term_ids, term_warnings = self._wp.resolve_taxonomy_terms(
                    sku, taxonomy, list(term_slugs), fallback
                )
                warnings.extend(term_warnings)

                if not term_ids and self._config.taxonomy.missing_term_policy == MissingTermPolicy.ERROR:
                    raise TaxonomyError(
                        sku=sku,
                        stage="taxonomy_resolve",
                        message=f"No valid terms found for {taxonomy}",
                        payload={"terms": list(term_slugs)},
                    )

                if term_ids:
                    taxonomy_terms[taxonomy] = term_ids

            timings.taxonomy_ms = int((time.monotonic() - taxonomy_start) * 1000)

            slug = self._resolve_slug(manifest, existing_post)
            acf_fields = self._build_acf_payload(manifest)

            media_start = time.monotonic()
            featured_id: int | None = None
            gallery_ids: list[int] = []

            if self._config.execution.image_policy != ImagePolicy.IGNORE:
                try:
                    featured_path = self._media_handler.resolve_featured_image(
                        sku, manifest.media
                    )

                    if featured_path:
                        file_path = self._media_handler.get_file_path(sku, featured_path)
                        if file_path.exists():
                            checksum = None
                            for item in manifest.media.gallery:
                                if item.file == featured_path:
                                    checksum = item.checksum
                                    break
                            featured_id = self._media_handler.upload_media(
                                sku, file_path, checksum
                            )

                    if manifest.media.gallery:
                        gallery_ids, media_warnings = self._media_handler.process_gallery(
                            sku, manifest.media.gallery
                        )
                        warnings.extend(media_warnings)

                except MediaError as e:
                    if self._config.degradation.media_failure == MediaFailurePolicy.FAIL_SKU:
                        raise
                    elif self._config.degradation.media_failure == MediaFailurePolicy.SKIP_MEDIA:
                        warnings.append(f"Media skipped: {e.message}")
                    elif self._config.degradation.media_failure == MediaFailurePolicy.RETRY_LATER:
                        warnings.append(f"Media will retry later: {e.message}")

            timings.media_ms = int((time.monotonic() - media_start) * 1000)

            if gallery_ids:
                acf_fields["imagens"] = gallery_ids

            post_start = time.monotonic()

            if self._config.execution.dry_run:
                timings.total_ms = int((time.monotonic() - start_time) * 1000)

                if existing_post:
                    return SKUResult(
                        sku=sku,
                        action=Action.WOULD_UPDATE,
                        post_id=existing_post["id"],
                        warnings=warnings,
                        timings=timings,
                    )
                else:
                    return SKUResult(
                        sku=sku,
                        action=Action.WOULD_CREATE,
                        warnings=warnings,
                        timings=timings,
                    )

            if existing_post:
                post = self._wp.update_post(
                    sku=sku,
                    post_id=existing_post["id"],
                    title=manifest.product.title,
                    slug=slug,
                    status=manifest.product.status.value,
                    acf_fields=acf_fields,
                    taxonomy_terms=taxonomy_terms,
                    featured_media=featured_id,
                )
                action = Action.UPDATED
            else:
                post = self._wp.create_post(
                    sku=sku,
                    title=manifest.product.title,
                    slug=slug,
                    status=manifest.product.status.value,
                    acf_fields=acf_fields,
                    taxonomy_terms=taxonomy_terms,
                )

                if featured_id:
                    self._wp.update_post(
                        sku=sku,
                        post_id=post["id"],
                        featured_media=featured_id,
                    )

                action = Action.CREATED

            timings.post_ms = int((time.monotonic() - post_start) * 1000)
            timings.total_ms = int((time.monotonic() - start_time) * 1000)

            self._ledger.record(
                sku=sku,
                hash_value=manifest_hash,
                action=action.value,
                status="success",
                post_id=post["id"],
            )

            return SKUResult(
                sku=sku,
                action=action,
                post_id=post["id"],
                warnings=warnings,
                timings=timings,
            )

        except HanaError as e:
            timings.total_ms = int((time.monotonic() - start_time) * 1000)

            self._ledger.record(
                sku=sku,
                hash_value="",
                action="failed",
                status="error",
                incomplete=True,
            )

            return SKUResult(
                sku=sku,
                action=Action.FAILED,
                reason=Reason.ERROR,
                warnings=warnings,
                errors=[e.to_dict()],
                timings=timings,
            )

        except Exception as e:
            timings.total_ms = int((time.monotonic() - start_time) * 1000)

            self._ledger.record(
                sku=sku,
                hash_value="",
                action="failed",
                status="error",
                incomplete=True,
            )

            return SKUResult(
                sku=sku,
                action=Action.FAILED,
                reason=Reason.ERROR,
                warnings=warnings,
                errors=[{
                    "type": type(e).__name__,
                    "message": str(e),
                    "sku": sku,
                    "stage": "unknown",
                }],
                timings=timings,
            )

    def run(self) -> list[SKUResult]:
        """Run the ingestion engine."""
        self._setup()

        try:
            manifests = list(self.discover_manifests())

            self._logger.info(
                f"Discovered {len(manifests)} manifests",
                stage="discovery",
            )

            if self._config.execution.parallel_skus > 1:
                results = self._run_parallel(manifests)
            else:
                results = self._run_sequential(manifests)

            self._results = results
            return results

        finally:
            self._teardown()

    def _run_sequential(
        self, manifests: list[tuple[str, ProductManifest]]
    ) -> list[SKUResult]:
        """Run ingestion sequentially."""
        results = []

        for sku, manifest in manifests:
            if self._shutdown_requested:
                self._logger.info("Shutdown requested, stopping", stage="shutdown")
                break

            self._logger.info(f"Processing SKU: {sku}", sku=sku, stage="process")

            with self._lock_manager.lock_sku(sku):
                result = self._process_sku(manifest)

            results.append(result)
            self._logger.info(
                f"Completed: {result.action.value}",
                sku=sku,
                stage="complete",
                action=result.action.value,
                post_id=result.post_id,
            )

        return results

    def _run_parallel(
        self, manifests: list[tuple[str, ProductManifest]]
    ) -> list[SKUResult]:
        """Run ingestion in parallel."""
        results: list[SKUResult] = []
        max_workers = self._config.execution.parallel_skus

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {}

            for sku, manifest in manifests:
                if self._shutdown_requested:
                    break

                future = executor.submit(self._process_sku_with_lock, sku, manifest)
                futures[future] = sku

            for future in as_completed(futures):
                sku = futures[future]
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    results.append(SKUResult(
                        sku=sku,
                        action=Action.FAILED,
                        reason=Reason.ERROR,
                        errors=[{"type": type(e).__name__, "message": str(e)}],
                    ))

        results.sort(key=lambda r: r.sku)
        return results

    def _process_sku_with_lock(
        self, sku: str, manifest: ProductManifest
    ) -> SKUResult:
        """Process SKU with lock acquisition."""
        with self._lock_manager.lock_sku(sku):
            return self._process_sku(manifest)

    def get_summary(self) -> dict[str, Any]:
        """Get execution summary."""
        if not self._results:
            return {}

        created = sum(1 for r in self._results if r.action == Action.CREATED)
        updated = sum(1 for r in self._results if r.action == Action.UPDATED)
        skipped = sum(1 for r in self._results if r.action == Action.SKIPPED)
        failed = sum(1 for r in self._results if r.action == Action.FAILED)

        would_create = sum(1 for r in self._results if r.action == Action.WOULD_CREATE)
        would_update = sum(1 for r in self._results if r.action == Action.WOULD_UPDATE)
        would_skip = sum(1 for r in self._results if r.action == Action.WOULD_SKIP)

        total_time = sum(r.timings.total_ms for r in self._results)

        return {
            "total": len(self._results),
            "created": created,
            "updated": updated,
            "skipped": skipped,
            "failed": failed,
            "would_create": would_create,
            "would_update": would_update,
            "would_skip": would_skip,
            "total_time_ms": total_time,
            "dry_run": self._config.execution.dry_run,
        }
