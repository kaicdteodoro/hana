"""Tests for hana.config."""

import pytest
from pathlib import Path
import tempfile

from hana.config import (
    BackpressureStrategy,
    DedupStrategy,
    ExecutionMode,
    FeaturedPolicy,
    HanaConfig,
    ImagePolicy,
    LogLevel,
    MissingTermPolicy,
    OrderingStrategy,
    SlugNullPolicy,
)


class TestHanaConfig:
    def test_defaults(self):
        config = HanaConfig()

        assert config.execution.mode == ExecutionMode.UPSERT
        assert config.execution.image_policy == ImagePolicy.REPLACE
        assert config.execution.dry_run is False
        assert config.execution.parallel_skus == 1
        assert config.schema.supported_versions == ("1.0",)
        assert config.taxonomy.fallback == "pendente"
        assert config.media.dedup_strategy == DedupStrategy.CHECKSUM_META
        assert config.logging.level == LogLevel.INFO

    def test_from_dict(self):
        data = {
            "execution": {
                "mode": "create",
                "image_policy": "append",
                "dry_run": True,
            },
            "taxonomy": {
                "missing_term_policy": "error",
            },
            "wp": {
                "base_url": "https://example.com",
                "user": "test",
                "app_password": "secret",
            },
            "paths": {
                "catalog_root": "/data/catalog",
            },
        }
        config = HanaConfig.from_dict(data)

        assert config.execution.mode == ExecutionMode.CREATE
        assert config.execution.image_policy == ImagePolicy.APPEND
        assert config.execution.dry_run is True
        assert config.taxonomy.missing_term_policy == MissingTermPolicy.ERROR
        assert config.wp.base_url == "https://example.com"

    def test_from_yaml(self):
        yaml_content = """
execution:
  mode: update
  parallel_skus: 4

wp:
  base_url: https://test.com
  user: admin
  app_password: pass123

paths:
  catalog_root: /tmp/catalog
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()

            config = HanaConfig.from_yaml(Path(f.name))

        assert config.execution.mode == ExecutionMode.UPDATE
        assert config.execution.parallel_skus == 4
        assert config.wp.base_url == "https://test.com"

    def test_validate_missing_required(self):
        config = HanaConfig()
        errors = config.validate()

        assert "wp.base_url is required" in errors
        assert "wp.user is required" in errors
        assert "wp.app_password is required" in errors
        assert "paths.catalog_root is required" in errors

    def test_validate_valid(self):
        config = HanaConfig.from_dict({
            "wp": {
                "base_url": "https://example.com",
                "user": "test",
                "app_password": "secret",
            },
            "paths": {
                "catalog_root": "/data",
            },
        })
        errors = config.validate()

        assert len(errors) == 0

    def test_validate_invalid_values(self):
        config = HanaConfig.from_dict({
            "execution": {
                "parallel_skus": 0,
            },
            "lock": {
                "timeout_seconds": 0,
            },
            "wp": {
                "base_url": "https://example.com",
                "user": "test",
                "app_password": "secret",
            },
            "paths": {
                "catalog_root": "/data",
            },
        })
        errors = config.validate()

        assert "execution.parallel_skus must be >= 1" in errors
        assert "lock.timeout_seconds must be >= 1" in errors
