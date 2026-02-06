#!/bin/sh
# WordPress setup script for Hana development environment
# Run with: docker compose --profile setup up wpcli

set -e

echo "=== Hana WordPress Setup ==="
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
        --title="Hana Development" \
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
echo "=== Installing Hana Plugin ==="

# Create must-use plugin directory
mkdir -p /var/www/html/wp-content/mu-plugins

# Copy the complete plugin from the project
if [ -f /app/wordpress/hana-cpt.php ]; then
    cp /app/wordpress/hana-cpt.php /var/www/html/wp-content/mu-plugins/hana-cpt.php
    echo "Installed hana-cpt.php from project"
else
    echo "WARNING: hana-cpt.php not found at /app/wordpress/"
    echo "You may need to install it manually"
fi

echo ""
echo "=== Installing ACF Plugin ==="

# Check if ACF is installed
if wp plugin is-installed advanced-custom-fields 2>/dev/null; then
    echo "ACF already installed"
    wp plugin activate advanced-custom-fields 2>/dev/null || true
else
    echo "Installing ACF..."
    wp plugin install advanced-custom-fields --activate 2>/dev/null || echo "ACF installation failed (install manually or use ACF PRO)"
fi

echo ""
echo "=== Setup Complete ==="
echo ""
echo "WordPress is ready at: http://localhost:8080"
echo "Admin login: admin / admin"
echo ""
echo "REST API endpoints:"
echo "  - http://localhost:8080/wp-json/wp/v2/catalog-items"
echo "  - http://localhost:8080/wp-json/wp/v2/media"
echo "  - http://localhost:8080/wp-json/wp/v2/item-category"
echo ""
