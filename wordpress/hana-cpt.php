<?php
/**
 * Plugin Name: Hana Catalog Integration
 * Description: Registers 'catalog-items' CPT with native meta fields (no ACF required)
 * Version: 3.0.0
 * Author: Hana
 *
 * INSTALLATION:
 * 1. Copy this file to: wp-content/mu-plugins/hana-cpt.php
 * 2. Done - no other plugins required
 */

if (!defined('ABSPATH')) exit;

// =============================================================================
// CUSTOM POST TYPE: catalog-items
// =============================================================================

add_action('init', function() {
    register_post_type('catalog-items', [
        'labels' => [
            'name'               => 'Catalog Items',
            'singular_name'      => 'Catalog Item',
            'add_new'            => 'Add New',
            'add_new_item'       => 'Add New Item',
            'edit_item'          => 'Edit Item',
            'new_item'           => 'New Item',
            'view_item'          => 'View Item',
            'search_items'       => 'Search Items',
            'not_found'          => 'No items found',
            'not_found_in_trash' => 'No items found in trash',
            'menu_name'          => 'Catalog',
        ],
        'public'              => true,
        'show_in_rest'        => true,
        'rest_base'           => 'catalog-items',
        'supports'            => ['title', 'editor', 'thumbnail', 'custom-fields'],
        'has_archive'         => true,
        'rewrite'             => ['slug' => 'catalog'],
        'menu_icon'           => 'dashicons-archive',
        'show_in_menu'        => true,
        'publicly_queryable'  => true,
        'exclude_from_search' => false,
    ]);
});

// =============================================================================
// TAXONOMY: item-category
// =============================================================================

add_action('init', function() {
    register_taxonomy('item-category', 'catalog-items', [
        'labels' => [
            'name'              => 'Item Categories',
            'singular_name'     => 'Item Category',
            'search_items'      => 'Search Categories',
            'all_items'         => 'All Categories',
            'parent_item'       => 'Parent Category',
            'parent_item_colon' => 'Parent Category:',
            'edit_item'         => 'Edit Category',
            'update_item'       => 'Update Category',
            'add_new_item'      => 'Add New Category',
            'new_item_name'     => 'New Category Name',
            'menu_name'         => 'Categories',
        ],
        'public'            => true,
        'show_in_rest'      => true,
        'rest_base'         => 'item-category',
        'hierarchical'      => true,
        'rewrite'           => ['slug' => 'item-category'],
        'show_admin_column' => true,
    ]);
}, 0);

// =============================================================================
// DEFAULT TERMS
// =============================================================================

add_action('init', function() {
    if (get_option('hana_default_terms_v4')) return;
    if (!taxonomy_exists('item-category')) return;

    $default_terms = [
        'uncategorized' => 'Uncategorized',
        'pending'       => 'Pending Review',
        'pens'          => 'Pens',
        'bbq-kits'      => 'BBQ Kits',
        'cheese-kits'   => 'Cheese Kits',
    ];

    foreach ($default_terms as $slug => $name) {
        if (!term_exists($slug, 'item-category')) {
            wp_insert_term($name, 'item-category', ['slug' => $slug]);
        }
    }

    update_option('hana_default_terms_v4', true);
}, 20);

// =============================================================================
// REGISTER META FIELDS FOR REST API
// =============================================================================

add_action('init', function() {
    $meta_fields = [
        'sku' => [
            'type'         => 'string',
            'description'  => 'Product SKU',
            'single'       => true,
            'show_in_rest' => true,
        ],
        'short_description' => [
            'type'         => 'string',
            'description'  => 'Short product description',
            'single'       => true,
            'show_in_rest' => true,
        ],
        'technical_description' => [
            'type'         => 'string',
            'description'  => 'Technical description (HTML)',
            'single'       => true,
            'show_in_rest' => true,
        ],
        'available_colors' => [
            'type'         => 'string',
            'description'  => 'Available colors (JSON array)',
            'single'       => true,
            'show_in_rest' => true,
        ],
        'gallery' => [
            'type'         => 'string',
            'description'  => 'Gallery image IDs (JSON array)',
            'single'       => true,
            'show_in_rest' => true,
        ],
        'hana_checksum' => [
            'type'         => 'string',
            'description'  => 'Manifest checksum for dedup',
            'single'       => true,
            'show_in_rest' => true,
        ],
    ];

    foreach ($meta_fields as $key => $args) {
        register_post_meta('catalog-items', $key, $args);
    }

    // Media checksum for deduplication
    register_post_meta('attachment', 'hana_checksum', [
        'type'         => 'string',
        'single'       => true,
        'show_in_rest' => true,
    ]);
});

// =============================================================================
// REST API: Enable meta queries for SKU lookup
// =============================================================================

// Register query params
add_filter('rest_catalog-items_collection_params', function($params) {
    $params['meta_key'] = [
        'description' => 'Meta key to filter by',
        'type'        => 'string',
    ];
    $params['meta_value'] = [
        'description' => 'Meta value to filter by',
        'type'        => 'string',
    ];
    return $params;
});

// Apply meta query
add_filter('rest_catalog-items_query', function($args, $request) {
    $meta_key   = $request->get_param('meta_key');
    $meta_value = $request->get_param('meta_value');

    if ($meta_key && $meta_value) {
        $args['meta_query'] = [
            [
                'key'     => $meta_key,
                'value'   => $meta_value,
                'compare' => '=',
            ],
        ];
    }

    return $args;
}, 10, 2);

// =============================================================================
// REST API: Enable media checksum lookup
// =============================================================================

add_filter('rest_attachment_query', function($args, $request) {
    $meta_key   = $request->get_param('meta_key');
    $meta_value = $request->get_param('meta_value');

    if ($meta_key === 'hana_checksum' && $meta_value) {
        $args['meta_query'] = [
            [
                'key'     => 'hana_checksum',
                'value'   => $meta_value,
                'compare' => '=',
            ],
        ];
    }

    return $args;
}, 10, 2);

// =============================================================================
// ADMIN: Meta Box for Catalog Fields
// =============================================================================

add_action('add_meta_boxes', function() {
    add_meta_box(
        'hana_catalog_fields',
        'Catalog Item Data',
        'hana_render_meta_box',
        'catalog-items',
        'normal',
        'high'
    );
});

function hana_render_meta_box($post) {
    wp_nonce_field('hana_save_meta', 'hana_meta_nonce');

    $sku = get_post_meta($post->ID, 'sku', true);
    $short_desc = get_post_meta($post->ID, 'short_description', true);
    $tech_desc = get_post_meta($post->ID, 'technical_description', true);
    $colors = get_post_meta($post->ID, 'available_colors', true);
    $gallery = get_post_meta($post->ID, 'gallery', true);
    ?>
    <style>
        .hana-field { margin-bottom: 15px; }
        .hana-field label { display: block; font-weight: 600; margin-bottom: 5px; }
        .hana-field input[type="text"], .hana-field textarea { width: 100%; }
        .hana-field textarea { min-height: 100px; }
    </style>

    <div class="hana-field">
        <label for="hana_sku">SKU</label>
        <input type="text" id="hana_sku" name="hana_sku" value="<?php echo esc_attr($sku); ?>" />
    </div>

    <div class="hana-field">
        <label for="hana_short_description">Short Description</label>
        <textarea id="hana_short_description" name="hana_short_description"><?php echo esc_textarea($short_desc); ?></textarea>
    </div>

    <div class="hana-field">
        <label for="hana_technical_description">Technical Description (HTML)</label>
        <textarea id="hana_technical_description" name="hana_technical_description" style="min-height: 150px;"><?php echo esc_textarea($tech_desc); ?></textarea>
    </div>

    <div class="hana-field">
        <label for="hana_available_colors">Available Colors (JSON array, e.g. ["Red", "Blue"])</label>
        <input type="text" id="hana_available_colors" name="hana_available_colors" value="<?php echo esc_attr($colors); ?>" />
    </div>

    <div class="hana-field">
        <label for="hana_gallery">Gallery (Image IDs, JSON array, e.g. [123, 456])</label>
        <input type="text" id="hana_gallery" name="hana_gallery" value="<?php echo esc_attr($gallery); ?>" />
    </div>

    <?php if ($gallery): ?>
        <?php $ids = json_decode($gallery, true); ?>
        <?php if (is_array($ids) && count($ids) > 0): ?>
            <div class="hana-field">
                <label>Gallery Preview</label>
                <div style="display: flex; gap: 10px; flex-wrap: wrap;">
                    <?php foreach ($ids as $img_id): ?>
                        <?php echo wp_get_attachment_image($img_id, 'thumbnail'); ?>
                    <?php endforeach; ?>
                </div>
            </div>
        <?php endif; ?>
    <?php endif; ?>
    <?php
}

add_action('save_post_catalog-items', function($post_id) {
    if (!isset($_POST['hana_meta_nonce']) || !wp_verify_nonce($_POST['hana_meta_nonce'], 'hana_save_meta')) {
        return;
    }

    if (defined('DOING_AUTOSAVE') && DOING_AUTOSAVE) return;
    if (!current_user_can('edit_post', $post_id)) return;

    $fields = ['sku', 'short_description', 'technical_description', 'available_colors', 'gallery'];

    foreach ($fields as $field) {
        $key = 'hana_' . $field;
        if (isset($_POST[$key])) {
            update_post_meta($post_id, $field, sanitize_textarea_field($_POST[$key]));
        }
    }
});

// =============================================================================
// ADMIN: Add SKU column to catalog list
// =============================================================================

add_filter('manage_catalog-items_posts_columns', function($columns) {
    $new_columns = [];
    foreach ($columns as $key => $value) {
        $new_columns[$key] = $value;
        if ($key === 'title') {
            $new_columns['sku'] = 'SKU';
        }
    }
    return $new_columns;
});

add_action('manage_catalog-items_posts_custom_column', function($column, $post_id) {
    if ($column === 'sku') {
        $sku = get_post_meta($post_id, 'sku', true);
        echo esc_html($sku ?: '—');
    }
}, 10, 2);

add_filter('manage_edit-catalog-items_sortable_columns', function($columns) {
    $columns['sku'] = 'sku';
    return $columns;
});

// =============================================================================
// HELPER: Get gallery images for templates
// =============================================================================

function hana_get_gallery_images($post_id = null) {
    if (!$post_id) $post_id = get_the_ID();
    $gallery = get_post_meta($post_id, 'gallery', true);
    if (!$gallery) return [];

    $ids = json_decode($gallery, true);
    if (!is_array($ids)) return [];

    $images = [];
    foreach ($ids as $id) {
        $images[] = [
            'id'        => $id,
            'url'       => wp_get_attachment_url($id),
            'thumbnail' => wp_get_attachment_image_url($id, 'thumbnail'),
            'medium'    => wp_get_attachment_image_url($id, 'medium'),
            'large'     => wp_get_attachment_image_url($id, 'large'),
            'full'      => wp_get_attachment_image_url($id, 'full'),
        ];
    }
    return $images;
}

function hana_get_available_colors($post_id = null) {
    if (!$post_id) $post_id = get_the_ID();
    $colors = get_post_meta($post_id, 'available_colors', true);
    if (!$colors) return [];

    $arr = json_decode($colors, true);
    return is_array($arr) ? $arr : [];
}
