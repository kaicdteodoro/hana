#!/bin/sh
# WordPress setup script for hana development environment
# Run with: docker compose --profile setup up wpcli

set -e

echo "=== hana WordPress Setup ==="
echo ""

# Wait for WordPress files
echo "Waiting for WordPress files..."
while [ ! -f /var/www/html/wp-config.php ]; do
    sleep 2
done

# Check if already installed
if wp core is-installed 2>/dev/null; then
    echo "WordPress already installed, skipping core setup..."
else
    echo "Installing WordPress..."
    wp core install \
        --url="http://localhost:8080" \
        --title="hana Development" \
        --admin_user="admin" \
        --admin_password="admin" \
        --admin_email="admin@example.com" \
        --skip-email
fi

echo ""
echo "=== Configuring REST API ==="

# Enable pretty permalinks (required for REST API)
wp rewrite structure '/%postname%/' --hard

# Create application password for hana
echo ""
echo "=== Creating Application Password ==="

# Check if application password exists
APP_PASS=$(wp user application-password list admin --format=json 2>/dev/null | grep -o '"name":"hana"' || true)

if [ -z "$APP_PASS" ]; then
    echo "Creating new application password..."
    NEW_PASS=$(wp user application-password create admin hana --porcelain 2>/dev/null)
    echo ""
    echo "============================================"
    echo "APPLICATION PASSWORD CREATED"
    echo "User: admin"
    echo "Password: $NEW_PASS"
    echo ""
    echo "Add to hana.yaml:"
    echo "  wp:"
    echo "    base_url: http://wordpress"
    echo "    user: admin"
    echo "    app_password: $NEW_PASS"
    echo "============================================"
else
    echo "Application password 'hana' already exists"
fi

echo ""
echo "=== Registering Custom Post Type ==="

# Create must-use plugin for custom post type
mkdir -p /var/www/html/wp-content/mu-plugins

cat > /var/www/html/wp-content/mu-plugins/hana-cpt.php << 'PLUGIN'
<?php
/**
 * Plugin Name: hana Custom Post Type
 * Description: Registers the 'produtos' post type for hana ingestion
 */

add_action('init', function() {
    register_post_type('produtos', [
        'label' => 'Produtos',
        'public' => true,
        'show_in_rest' => true,
        'rest_base' => 'produtos',
        'supports' => ['title', 'editor', 'thumbnail', 'custom-fields'],
        'has_archive' => true,
        'rewrite' => ['slug' => 'produtos'],
    ]);

    register_taxonomy('categoria-produto', 'produtos', [
        'label' => 'Categorias de Produto',
        'public' => true,
        'show_in_rest' => true,
        'rest_base' => 'categoria-produto',
        'hierarchical' => true,
        'rewrite' => ['slug' => 'categoria-produto'],
    ]);
});

// Expose ACF fields in REST API
add_filter('acf/rest_api/resource_settings', function($settings) {
    $settings['produtos'] = ['show' => true];
    return $settings;
}, 10, 1);
PLUGIN

echo "Custom post type 'produtos' registered"

echo ""
echo "=== Creating Default Taxonomy Terms ==="

# Create fallback term
wp term create categoria-produto "Pendente" --slug="pendente" 2>/dev/null || echo "Term 'pendente' already exists"
wp term create categoria-produto "Geral" --slug="geral" 2>/dev/null || echo "Term 'geral' already exists"

echo ""
echo "=== Setup Complete ==="
echo ""
echo "WordPress is ready at: http://localhost:8080"
echo "Admin login: admin / admin"
echo ""
echo "REST API endpoints:"
echo "  - http://localhost:8080/wp-json/wp/v2/produtos"
echo "  - http://localhost:8080/wp-json/wp/v2/media"
echo "  - http://localhost:8080/wp-json/wp/v2/categoria-produto"
echo ""
