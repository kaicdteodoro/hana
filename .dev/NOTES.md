# Hana — Development Notes

## Current Structure (v2.0)

### WordPress
- **CPT:** `catalog-items` (REST: `/wp-json/wp/v2/catalog-items`)
- **Taxonomy:** `item-category` (REST: `/wp-json/wp/v2/item-category`)
- **Default terms:** `uncategorized`, `pending`

### ACF Fields
| Field | Key | Type |
|-------|-----|------|
| SKU | `sku` | text |
| Short Description | `short_description` | textarea |
| Technical Description | `technical_description` | wysiwyg |
| Available Colors | `available_colors` | repeater → `color` |
| Gallery | `gallery` | gallery |

### Required WordPress Plugins
1. **ACF PRO** — Custom fields
2. **hana-cpt.php** — CPT, taxonomy, REST config (mu-plugin)

---

## Setup: External WordPress (cPanel)

### 1. Install Plugin
Upload `wordpress/hana-cpt.php` to `wp-content/mu-plugins/`

### 2. Ensure ACF PRO is Active
Plugins → ACF PRO → Activate

### 3. Create Application Password
Users → Profile → Application Passwords → Name: `hana` → Create

### 4. Configure Hana
```bash
cp hana.cpanel.yaml hana.yaml
# Edit wp.base_url, wp.user, wp.app_password
```

### 5. Test
```bash
python -m hana health
python -m hana run --dry-run
python -m hana run
```

---

## Setup: Local Docker

```bash
# Start environment
docker compose up -d wordpress mariadb

# Wait for WordPress to be ready, then run setup
docker compose --profile setup up wpcli

# Copy the app password from output, update hana.docker.yaml

# Test
docker compose run --rm hana hana health -c /app/hana.docker.yaml
docker compose run --rm hana hana run -c /app/hana.docker.yaml --dry-run
```

---

## Manifest Format

```json
{
  "sku": "ITEM-001",
  "meta": {
    "schema_version": "1.0",
    "source": "optional",
    "generated_at": "2024-01-01T00:00:00Z"
  },
  "product": {
    "title": "Product Name",
    "slug": "product-name",
    "status": "draft"
  },
  "taxonomy": {
    "item-category": ["category-slug"]
  },
  "descriptions": {
    "short": "Brief description",
    "technical": "<p>HTML content</p>"
  },
  "attributes": {
    "available_colors": ["Red", "Blue"]
  },
  "media": {
    "featured": "path/to/image.jpg",
    "gallery": [
      {"file": "path/to/img.jpg", "checksum": "sha256..."}
    ]
  }
}
```

---

## Key Files

```
hana/
├── engine.py        # Main ingestion logic
├── wordpress.py     # REST API client
├── retry.py         # Retry with exponential backoff
├── config.py        # All configuration options
└── models.py        # Data models

wordpress/
└── hana-cpt.php     # WordPress plugin (copy to mu-plugins)

data/catalog/
└── {SKU}/
    └── manifest.json
```

---

## Implemented Features

- [x] Full ingestion pipeline
- [x] Retry with exponential backoff
- [x] Rate limiting
- [x] Idempotent execution (hash-based skip)
- [x] Media deduplication
- [x] Graceful shutdown
- [x] Structured JSON logging
- [x] Dry-run mode

## TODO

- [ ] Integration tests with real WordPress
- [ ] Ledger rebuild from WordPress
- [ ] CLI commands: status, retry-incomplete
