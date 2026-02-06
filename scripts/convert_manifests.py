#!/usr/bin/env python3
"""
Convert manifests from old Portuguese format to new English format.

Changes:
- taxonomy: categoria-produto → item-category
- product.type: produtos → catalog-items
- Term slugs: Portuguese → English
- Removes acf block (now using native meta via descriptions/attributes)
"""

import json
from pathlib import Path
from datetime import datetime, timezone

CATALOG_ROOT = Path(__file__).parent.parent / "data" / "catalog"

# Taxonomy term mapping: Portuguese name → English slug
TERM_MAP = {
    "Canetas": "pens",
    "Kits Churrasco": "bbq-kits",
    "Kits Queijo": "cheese-kits",
}


def convert_manifest(data: list) -> list:
    """Convert manifest data from old format to new format."""
    converted = []

    for item in data:
        new_item = {
            "sku": item["sku"],
            "product": {
                "title": item["product"]["title"],
                "slug": item["product"]["slug"],
                "status": item["product"]["status"],
                "type": "catalog-items",  # Changed from "produtos"
            },
            "taxonomy": {},
            "descriptions": item.get("descriptions", {}),
            "attributes": item.get("attributes", {}),
            "media": item.get("media", {}),
            "meta": item.get("meta", {}),
        }

        # Convert taxonomy
        old_taxonomy = item.get("taxonomy", {})
        if "categoria-produto" in old_taxonomy:
            old_terms = old_taxonomy["categoria-produto"]
            new_terms = [TERM_MAP.get(term, term) for term in old_terms]
            new_item["taxonomy"]["item-category"] = new_terms

        # acf block is intentionally not copied (using native meta now)

        converted.append(new_item)

    return converted


def create_placeholder_manifest(sku: str, media_data: dict) -> list:
    """Create a placeholder manifest from manifest.media.json data."""
    images = media_data.get("media", {}).get("images", [])
    colors = media_data.get("attributes", {}).get("available_colors", [])

    # Build gallery from images
    gallery = [{"file": img["file"], "color_hex": img.get("color_hex")} for img in images]
    featured = images[0]["file"] if images else None

    return [{
        "sku": sku,
        "product": {
            "title": f"Product {sku}",  # Placeholder title
            "slug": sku.lower(),
            "status": "draft",  # Draft until reviewed
            "type": "catalog-items",
        },
        "taxonomy": {
            "item-category": ["uncategorized"],
        },
        "descriptions": {
            "short": None,
            "technical": None,
        },
        "attributes": {
            "available_colors": colors,
            "materials": media_data.get("attributes", {}).get("materials", []),
        },
        "media": {
            "featured": featured,
            "gallery": gallery,
        },
        "meta": {
            "source": "media-only",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
    }]


def process_catalog():
    """Process all catalog folders."""
    stats = {"converted": 0, "created": 0, "errors": 0, "skipped": 0}

    for folder in sorted(CATALOG_ROOT.iterdir()):
        if not folder.is_dir():
            continue

        manifest_path = folder / "manifest.json"
        media_manifest_path = folder / "manifest.media.json"

        try:
            if manifest_path.exists():
                # Check if already converted
                with open(manifest_path, "r", encoding="utf-8-sig") as f:
                    data = json.load(f)

                if not data:
                    print(f"SKIP (empty): {folder.name}")
                    stats["skipped"] += 1
                    continue

                # Check if needs conversion
                first_item = data[0]
                old_taxonomy = first_item.get("taxonomy", {})
                product_type = first_item.get("product", {}).get("type", "")

                if "categoria-produto" not in old_taxonomy and product_type == "catalog-items":
                    print(f"SKIP (already converted): {folder.name}")
                    stats["skipped"] += 1
                    continue

                # Convert
                converted = convert_manifest(data)
                with open(manifest_path, "w", encoding="utf-8") as f:
                    json.dump(converted, f, indent=2, ensure_ascii=False)
                print(f"CONVERTED: {folder.name}")
                stats["converted"] += 1

            elif media_manifest_path.exists():
                # Create placeholder from media manifest
                with open(media_manifest_path, "r", encoding="utf-8-sig") as f:
                    media_data = json.load(f)

                sku = folder.name
                placeholder = create_placeholder_manifest(sku, media_data)

                with open(manifest_path, "w", encoding="utf-8") as f:
                    json.dump(placeholder, f, indent=2, ensure_ascii=False)
                print(f"CREATED: {folder.name} (from media manifest)")
                stats["created"] += 1

            else:
                print(f"SKIP (no manifest): {folder.name}")
                stats["skipped"] += 1

        except Exception as e:
            print(f"ERROR: {folder.name} - {e}")
            stats["errors"] += 1

    print("\n=== Summary ===")
    print(f"Converted: {stats['converted']}")
    print(f"Created: {stats['created']}")
    print(f"Skipped: {stats['skipped']}")
    print(f"Errors: {stats['errors']}")


if __name__ == "__main__":
    process_catalog()
