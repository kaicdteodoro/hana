# hana — Hands Are Not APIs

Deterministic WordPress Catalog Ingestion Engine.

## Overview

hana is a production-grade ingestion engine that imports product catalogs into WordPress via REST API. It is designed to be:

- **Deterministic** — Same input always produces same output
- **Idempotent** — Safe to re-run without side effects
- **Resumable** — Can resume after crash or interruption
- **Auditable** — Full execution ledger for tracking

## Quick Start

```bash
# Start WordPress environment
make up

# Run initial setup
make setup

# Copy and configure
cp hana.docker.yaml hana.yaml
# Edit hana.yaml with the app_password from setup

# Run health check
make health

# Run dry-run
make dry-run

# Run ingestion
make run
```

## Catalog Structure

```
data/catalog/
├── SKU-001/
│   ├── manifest.json
│   └── images/
│       ├── featured.jpg
│       └── gallery/
├── SKU-002/
│   ├── manifest.json
│   └── images/
```

## Manifest Format

```json
{
  "sku": "SKU-001",
  "meta": {
    "schema_version": "1.0",
    "source": "erp",
    "generated_at": "2024-01-01T00:00:00Z"
  },
  "product": {
    "title": "Product Name",
    "slug": "product-name",
    "status": "publish"
  },
  "taxonomy": {
    "categoria-produto": ["category-slug"]
  },
  "descriptions": {
    "short": "Short description",
    "technical": "<p>Technical specs</p>"
  },
  "attributes": {
    "available_colors": ["Red", "Blue"]
  },
  "media": {
    "featured": "images/featured.jpg",
    "gallery": [
      {"file": "images/gallery/1.jpg", "checksum": "sha256..."}
    ]
  }
}
```

## Configuration

See `hana.example.yaml` for all available options.

## License

MIT
