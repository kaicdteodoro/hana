"""
hana.cli — Command-line interface.

Usage:
    hana run [--config CONFIG] [--dry-run]
    hana health [--config CONFIG]
    hana validate [--config CONFIG]
"""

import argparse
import json
import sys
from pathlib import Path

from hana.config import HanaConfig
from hana.engine import IngestionEngine
from hana.logger import configure_logger, get_logger
from hana.wordpress import WordPressClient


def cmd_run(args: argparse.Namespace) -> int:
    """Run the ingestion engine."""
    config = load_config(args.config)

    if args.dry_run:
        config.execution.dry_run = True

    configure_logger(config.logging.level)
    logger = get_logger()

    errors = config.validate()
    if errors:
        for error in errors:
            logger.error(error, stage="config_validation")
        return 1

    logger.info(
        "Starting ingestion",
        stage="startup",
        mode=config.execution.mode.value,
        dry_run=config.execution.dry_run,
    )

    engine = IngestionEngine(config)
    results = engine.run()

    summary = engine.get_summary()

    for result in results:
        print(json.dumps(result.to_dict(), ensure_ascii=False))

    logger.info(
        "Ingestion complete",
        stage="complete",
        **summary,
    )

    failed_count = summary.get("failed", 0)
    return 1 if failed_count > 0 else 0


def cmd_health(args: argparse.Namespace) -> int:
    """Run health check."""
    config = load_config(args.config)
    configure_logger(config.logging.level)
    logger = get_logger()

    errors = config.validate()
    if errors:
        for error in errors:
            logger.error(error, stage="config_validation")
        return 1

    logger.info("Running health check", stage="health_check")

    client = WordPressClient(config)
    results = client.health_check()
    client.close()

    print(json.dumps(results, indent=2))

    all_ok = (
        results["authentication"]
        and results["rest_available"]
        and all(results["endpoints"].values())
    )

    if all_ok:
        logger.info("Health check passed", stage="health_check")
        return 0
    else:
        logger.error("Health check failed", stage="health_check", results=results)
        return 1


def cmd_validate(args: argparse.Namespace) -> int:
    """Validate configuration and manifests."""
    config = load_config(args.config)
    configure_logger(config.logging.level)
    logger = get_logger()

    errors = config.validate()

    if errors:
        print("Configuration errors:")
        for error in errors:
            print(f"  - {error}")
        return 1

    print("Configuration is valid")

    engine = IngestionEngine(config)
    engine._setup()

    manifest_count = 0
    error_count = 0

    try:
        for sku, manifest in engine.discover_manifests():
            manifest_count += 1
            validation_errors = engine.validate_manifest(manifest)

            if validation_errors:
                error_count += 1
                print(f"Manifest errors for {sku}:")
                for error in validation_errors:
                    print(f"  - {error}")

    finally:
        engine._teardown()

    print(f"\nValidated {manifest_count} manifests, {error_count} with errors")

    return 1 if error_count > 0 else 0


def load_config(config_path: str | None) -> HanaConfig:
    """Load configuration from file."""
    if config_path:
        path = Path(config_path)
    else:
        for candidate in ["hana.yaml", "hana.yml", ".hana.yaml", ".hana.yml"]:
            path = Path(candidate)
            if path.exists():
                break
        else:
            print("No configuration file found", file=sys.stderr)
            sys.exit(1)

    if not path.exists():
        print(f"Configuration file not found: {path}", file=sys.stderr)
        sys.exit(1)

    return HanaConfig.from_yaml(path)


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        prog="hana",
        description="Hands Are Not APIs — Deterministic WordPress Catalog Ingestion Engine",
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    run_parser = subparsers.add_parser("run", help="Run the ingestion engine")
    run_parser.add_argument(
        "-c", "--config",
        help="Path to configuration file",
    )
    run_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Perform dry run without making changes",
    )

    health_parser = subparsers.add_parser("health", help="Run health check")
    health_parser.add_argument(
        "-c", "--config",
        help="Path to configuration file",
    )

    validate_parser = subparsers.add_parser("validate", help="Validate configuration and manifests")
    validate_parser.add_argument(
        "-c", "--config",
        help="Path to configuration file",
    )

    args = parser.parse_args()

    if args.command == "run":
        return cmd_run(args)
    elif args.command == "health":
        return cmd_health(args)
    elif args.command == "validate":
        return cmd_validate(args)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
