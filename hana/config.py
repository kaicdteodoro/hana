"""
hana.config — Configuration loading and validation.

All configuration is external-only. No hardcoded defaults in engine logic.
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import yaml


class ExecutionMode(str, Enum):
    CREATE = "create"
    UPDATE = "update"
    UPSERT = "upsert"


class ImagePolicy(str, Enum):
    APPEND = "append"
    REPLACE = "replace"
    IGNORE = "ignore"


class SlugNullPolicy(str, Enum):
    FROM_TITLE = "from_title"
    FROM_SKU = "from_sku"
    ERROR = "error"


class SlugCollisionPolicy(str, Enum):
    FAIL = "fail"
    SUFFIX = "suffix"
    SKU = "sku"


class MissingTermPolicy(str, Enum):
    FALLBACK = "fallback"
    ERROR = "error"


class DedupStrategy(str, Enum):
    CHECKSUM_META = "checksum_meta"
    FILENAME = "filename"
    LOCAL_LEDGER = "local_ledger"


class OrphanPolicy(str, Enum):
    DETACH = "detach"
    DELETE = "delete"


class FeaturedPolicy(str, Enum):
    ERROR = "error"
    FIRST_GALLERY = "first_gallery"
    ALLOW_NULL = "allow_null"


class LockStrategy(str, Enum):
    FILESYSTEM = "filesystem"
    ADVISORY = "advisory"


class NullPolicy(str, Enum):
    IGNORE = "ignore"
    CLEAR = "clear"
    ERROR = "error"


class MissingPolicy(str, Enum):
    IGNORE = "ignore"
    ERROR = "error"


class CorruptionPolicy(str, Enum):
    FAIL = "fail"
    REBUILD = "rebuild"
    IGNORE_CORRUPT_LINES = "ignore_corrupt_lines"


class FailurePolicy(str, Enum):
    ROLLBACK = "rollback"
    MARK_INCOMPLETE = "mark_incomplete"
    ALLOW_PARTIAL = "allow_partial"


class OrderingStrategy(str, Enum):
    SKU_ASC = "sku_asc"
    FILESYSTEM = "filesystem"
    MANIFEST_ORDER = "manifest_order"


class BackpressureStrategy(str, Enum):
    PAUSE = "pause"
    SKIP = "skip"
    ABORT = "abort"


class BackpressureTrigger(str, Enum):
    CONSECUTIVE_ERRORS = "consecutive_errors"
    ERROR_RATE = "error_rate"
    RESPONSE_TIME = "response_time"


class MediaFailurePolicy(str, Enum):
    SKIP_MEDIA = "skip_media"
    FAIL_SKU = "fail_sku"
    RETRY_LATER = "retry_later"


class TaxonomyFailurePolicy(str, Enum):
    USE_FALLBACK = "use_fallback"
    FAIL_SKU = "fail_sku"


class LogLevel(str, Enum):
    DEBUG = "debug"
    INFO = "info"
    WARN = "warn"
    ERROR = "error"


class UnknownVersionPolicy(str, Enum):
    FAIL = "fail"
    WARN = "warn"


@dataclass
class ExecutionConfig:
    mode: ExecutionMode = ExecutionMode.UPSERT
    image_policy: ImagePolicy = ImagePolicy.REPLACE
    dry_run: bool = False
    parallel_skus: int = 1


@dataclass
class SchemaConfig:
    supported_versions: tuple[str, ...] = ("1.0",)
    unknown_version_policy: UnknownVersionPolicy = UnknownVersionPolicy.FAIL


@dataclass
class SlugConfig:
    null_policy: SlugNullPolicy = SlugNullPolicy.FROM_TITLE
    collision_policy: SlugCollisionPolicy = SlugCollisionPolicy.SUFFIX


@dataclass
class TaxonomyConfig:
    missing_term_policy: MissingTermPolicy = MissingTermPolicy.FALLBACK
    fallback: str = "pendente"


@dataclass
class MediaConfig:
    dedup_strategy: DedupStrategy = DedupStrategy.CHECKSUM_META
    checksum_algorithm: str = "sha256"
    featured_policy: FeaturedPolicy = FeaturedPolicy.FIRST_GALLERY
    orphan_policy: OrphanPolicy = OrphanPolicy.DETACH
    media_ledger_path: str = ".hana/media_ledger.json"


@dataclass
class LockConfig:
    strategy: LockStrategy = LockStrategy.FILESYSTEM
    timeout_seconds: int = 300
    cleanup_orphans: bool = True


@dataclass
class RateLimitConfig:
    requests_per_second: int = 5
    burst: int = 10


@dataclass
class RetryConfig:
    max_attempts: int = 3
    initial_delay_ms: int = 500
    max_delay_ms: int = 10000


@dataclass
class BackpressureConfig:
    strategy: BackpressureStrategy = BackpressureStrategy.PAUSE
    trigger: BackpressureTrigger = BackpressureTrigger.CONSECUTIVE_ERRORS
    threshold: int = 5
    cooldown_seconds: int = 30


@dataclass
class DegradationConfig:
    media_failure: MediaFailurePolicy = MediaFailurePolicy.SKIP_MEDIA
    taxonomy_failure: TaxonomyFailurePolicy = TaxonomyFailurePolicy.USE_FALLBACK


@dataclass
class UpdateConfig:
    null_policy: NullPolicy = NullPolicy.IGNORE
    missing_policy: MissingPolicy = MissingPolicy.IGNORE


@dataclass
class FailurePolicyConfig:
    post_then_media: FailurePolicy = FailurePolicy.MARK_INCOMPLETE


@dataclass
class OrderingConfig:
    strategy: OrderingStrategy = OrderingStrategy.SKU_ASC


@dataclass
class SignalsConfig:
    graceful_shutdown: bool = True
    checkpoint_on_sigterm: bool = True


@dataclass
class LoggingConfig:
    level: LogLevel = LogLevel.INFO


@dataclass
class LedgerConfig:
    path: str = ".hana/ledger.jsonl"
    corruption_policy: CorruptionPolicy = CorruptionPolicy.FAIL


@dataclass
class WordPressConfig:
    base_url: str = ""
    user: str = ""
    app_password: str = ""


@dataclass
class PathsConfig:
    catalog_root: str = ""


@dataclass
class HanaConfig:
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    schema: SchemaConfig = field(default_factory=SchemaConfig)
    slug: SlugConfig = field(default_factory=SlugConfig)
    taxonomy: TaxonomyConfig = field(default_factory=TaxonomyConfig)
    media: MediaConfig = field(default_factory=MediaConfig)
    lock: LockConfig = field(default_factory=LockConfig)
    rate_limit: RateLimitConfig = field(default_factory=RateLimitConfig)
    retry: RetryConfig = field(default_factory=RetryConfig)
    backpressure: BackpressureConfig = field(default_factory=BackpressureConfig)
    degradation: DegradationConfig = field(default_factory=DegradationConfig)
    update: UpdateConfig = field(default_factory=UpdateConfig)
    failure_policy: FailurePolicyConfig = field(default_factory=FailurePolicyConfig)
    ordering: OrderingConfig = field(default_factory=OrderingConfig)
    signals: SignalsConfig = field(default_factory=SignalsConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    ledger: LedgerConfig = field(default_factory=LedgerConfig)
    wp: WordPressConfig = field(default_factory=WordPressConfig)
    paths: PathsConfig = field(default_factory=PathsConfig)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HanaConfig":
        """Parse configuration from a dictionary."""

        def parse_execution(d: dict) -> ExecutionConfig:
            return ExecutionConfig(
                mode=ExecutionMode(d.get("mode", "upsert")),
                image_policy=ImagePolicy(d.get("image_policy", "replace")),
                dry_run=d.get("dry_run", False),
                parallel_skus=d.get("parallel_skus", 1),
            )

        def parse_schema(d: dict) -> SchemaConfig:
            versions = d.get("supported_versions", ["1.0"])
            return SchemaConfig(
                supported_versions=tuple(versions),
                unknown_version_policy=UnknownVersionPolicy(
                    d.get("unknown_version_policy", "fail")
                ),
            )

        def parse_slug(d: dict) -> SlugConfig:
            return SlugConfig(
                null_policy=SlugNullPolicy(d.get("null_policy", "from_title")),
                collision_policy=SlugCollisionPolicy(d.get("collision_policy", "suffix")),
            )

        def parse_taxonomy(d: dict) -> TaxonomyConfig:
            return TaxonomyConfig(
                missing_term_policy=MissingTermPolicy(
                    d.get("missing_term_policy", "fallback")
                ),
                fallback=d.get("fallback", "pendente"),
            )

        def parse_media(d: dict) -> MediaConfig:
            return MediaConfig(
                dedup_strategy=DedupStrategy(d.get("dedup_strategy", "checksum_meta")),
                checksum_algorithm=d.get("checksum_algorithm", "sha256"),
                featured_policy=FeaturedPolicy(d.get("featured_policy", "first_gallery")),
                orphan_policy=OrphanPolicy(d.get("orphan_policy", "detach")),
                media_ledger_path=d.get("media_ledger_path", ".hana/media_ledger.json"),
            )

        def parse_lock(d: dict) -> LockConfig:
            return LockConfig(
                strategy=LockStrategy(d.get("strategy", "filesystem")),
                timeout_seconds=d.get("timeout_seconds", 300),
                cleanup_orphans=d.get("cleanup_orphans", True),
            )

        def parse_rate_limit(d: dict) -> RateLimitConfig:
            return RateLimitConfig(
                requests_per_second=d.get("requests_per_second", 5),
                burst=d.get("burst", 10),
            )

        def parse_retry(d: dict) -> RetryConfig:
            return RetryConfig(
                max_attempts=d.get("max_attempts", 3),
                initial_delay_ms=d.get("initial_delay_ms", 500),
                max_delay_ms=d.get("max_delay_ms", 10000),
            )

        def parse_backpressure(d: dict) -> BackpressureConfig:
            return BackpressureConfig(
                strategy=BackpressureStrategy(d.get("strategy", "pause")),
                trigger=BackpressureTrigger(d.get("trigger", "consecutive_errors")),
                threshold=d.get("threshold", 5),
                cooldown_seconds=d.get("cooldown_seconds", 30),
            )

        def parse_degradation(d: dict) -> DegradationConfig:
            return DegradationConfig(
                media_failure=MediaFailurePolicy(d.get("media_failure", "skip_media")),
                taxonomy_failure=TaxonomyFailurePolicy(
                    d.get("taxonomy_failure", "use_fallback")
                ),
            )

        def parse_update(d: dict) -> UpdateConfig:
            return UpdateConfig(
                null_policy=NullPolicy(d.get("null_policy", "ignore")),
                missing_policy=MissingPolicy(d.get("missing_policy", "ignore")),
            )

        def parse_failure_policy(d: dict) -> FailurePolicyConfig:
            return FailurePolicyConfig(
                post_then_media=FailurePolicy(d.get("post_then_media", "mark_incomplete")),
            )

        def parse_ordering(d: dict) -> OrderingConfig:
            return OrderingConfig(
                strategy=OrderingStrategy(d.get("strategy", "sku_asc")),
            )

        def parse_signals(d: dict) -> SignalsConfig:
            return SignalsConfig(
                graceful_shutdown=d.get("graceful_shutdown", True),
                checkpoint_on_sigterm=d.get("checkpoint_on_sigterm", True),
            )

        def parse_logging(d: dict) -> LoggingConfig:
            return LoggingConfig(
                level=LogLevel(d.get("level", "info")),
            )

        def parse_ledger(d: dict) -> LedgerConfig:
            return LedgerConfig(
                path=d.get("path", ".hana/ledger.jsonl"),
                corruption_policy=CorruptionPolicy(d.get("corruption_policy", "fail")),
            )

        def parse_wp(d: dict) -> WordPressConfig:
            return WordPressConfig(
                base_url=d.get("base_url", ""),
                user=d.get("user", ""),
                app_password=d.get("app_password", ""),
            )

        def parse_paths(d: dict) -> PathsConfig:
            return PathsConfig(
                catalog_root=d.get("catalog_root", ""),
            )

        return cls(
            execution=parse_execution(data.get("execution", {})),
            schema=parse_schema(data.get("schema", {})),
            slug=parse_slug(data.get("slug", {})),
            taxonomy=parse_taxonomy(data.get("taxonomy", {})),
            media=parse_media(data.get("media", {})),
            lock=parse_lock(data.get("lock", {})),
            rate_limit=parse_rate_limit(data.get("rate_limit", {})),
            retry=parse_retry(data.get("retry", {})),
            backpressure=parse_backpressure(data.get("backpressure", {})),
            degradation=parse_degradation(data.get("degradation", {})),
            update=parse_update(data.get("update", {})),
            failure_policy=parse_failure_policy(data.get("failure_policy", {})),
            ordering=parse_ordering(data.get("ordering", {})),
            signals=parse_signals(data.get("signals", {})),
            logging=parse_logging(data.get("logging", {})),
            ledger=parse_ledger(data.get("ledger", {})),
            wp=parse_wp(data.get("wp", {})),
            paths=parse_paths(data.get("paths", {})),
        )

    @classmethod
    def from_yaml(cls, path: Path) -> "HanaConfig":
        """Load configuration from a YAML file."""
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return cls.from_dict(data)

    def validate(self) -> list[str]:
        """Validate configuration and return list of errors."""
        errors = []

        if not self.wp.base_url:
            errors.append("wp.base_url is required")
        if not self.wp.user:
            errors.append("wp.user is required")
        if not self.wp.app_password:
            errors.append("wp.app_password is required")
        if not self.paths.catalog_root:
            errors.append("paths.catalog_root is required")

        if self.execution.parallel_skus < 1:
            errors.append("execution.parallel_skus must be >= 1")

        if self.lock.timeout_seconds < 1:
            errors.append("lock.timeout_seconds must be >= 1")

        if self.rate_limit.requests_per_second < 1:
            errors.append("rate_limit.requests_per_second must be >= 1")

        if self.retry.max_attempts < 1:
            errors.append("retry.max_attempts must be >= 1")

        return errors
