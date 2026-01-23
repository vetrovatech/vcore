<?php
/**
 * Plugin Name: Glassy VCore Sync
 * Plugin URI: https://vcore.glassy.in
 * Description: Syncs product catalog from VCore database to WooCommerce
 * Version: 1.0.0
 * Author: Glassy India
 * Author URI: https://glassy.in
 * Requires at least: 5.8
 * Requires PHP: 7.4
 * WC requires at least: 5.0
 * WC tested up to: 8.0
 */

if (!defined('ABSPATH')) {
    exit; // Exit if accessed directly
}

class Glassy_VCore_Sync {
    
    private $version = '1.0.0';
    private $category_mapping = array();
    
    public function __construct() {
        // Load category mapping from JSON file
        $json_file = plugin_dir_path(__FILE__) . 'category-structure.json';
        if (file_exists($json_file)) {
            $json_data = file_get_contents($json_file);
            $this->category_mapping = json_decode($json_data, true);
        }
        
        // Register REST API endpoints
        add_action('rest_api_init', array($this, 'register_rest_routes'));
        
        // Add admin menu
        add_action('admin_menu', array($this, 'add_admin_menu'));
    }
    
    /**
     * Register REST API routes
     */
    public function register_rest_routes() {
        register_rest_route('vcore/v1', '/sync-products', array(
            'methods' => 'POST',
            'callback' => array($this, 'sync_products'),
            'permission_callback' => array($this, 'check_permissions'),
        ));
        
        register_rest_route('vcore/v1', '/sync-single-product', array(
            'methods' => 'POST',
            'callback' => array($this, 'sync_single_product'),
            'permission_callback' => array($this, 'check_permissions'),
        ));
        
        register_rest_route('vcore/v1', '/create-categories', array(
            'methods' => 'POST',
            'callback' => array($this, 'create_category_structure'),
            'permission_callback' => array($this, 'check_permissions'),
        ));
    }
    
    /**
     * Check API permissions
     */
    public function check_permissions($request) {
        return current_user_can('manage_woocommerce');
    }
    
    /**
     * Sync multiple products from VCore
     */
    public function sync_products($request) {
        $products = $request->get_param('products');
        
        if (empty($products) || !is_array($products)) {
            return new WP_Error('invalid_data', 'Products data is required', array('status' => 400));
        }
        
        $results = array(
            'success' => 0,
            'failed' => 0,
            'errors' => array(),
            'product_ids' => array()
        );
        
        foreach ($products as $product_data) {
            $result = $this->process_single_product($product_data);
            
            if (is_wp_error($result)) {
                $results['failed']++;
                $results['errors'][] = array(
                    'product_name' => $product_data['product_name'],
                    'error' => $result->get_error_message()
                );
            } else {
                $results['success']++;
                $results['product_ids'][] = $result;
            }
        }
        
        return rest_ensure_response($results);
    }
    
    /**
     * Sync single product
     */
    public function sync_single_product($request) {
        $product_data = $request->get_json_params();
        
        if (empty($product_data)) {
            return new WP_Error('invalid_data', 'Product data is required', array('status' => 400));
        }
        
        $result = $this->process_single_product($product_data);
        
        if (is_wp_error($result)) {
            return $result;
        }
        
        return rest_ensure_response(array(
            'success' => true,
            'product_id' => $result,
            'message' => 'Product synced successfully'
        ));
    }
    
    /**
     * Process a single product (create or update)
     */
    private function process_single_product($product_data) {
        // Check if product already exists by SKU or vcore_id
        $vcore_id = isset($product_data['id']) ? $product_data['id'] : null;
        $existing_product_id = null;
        
        if ($vcore_id) {
            // Check if product with this vcore_id exists
            $existing_products = get_posts(array(
                'post_type' => 'product',
                'meta_key' => '_vcore_product_id',
                'meta_value' => $vcore_id,
                'posts_per_page' => 1,
                'fields' => 'ids'
            ));
            
            if (!empty($existing_products)) {
                $existing_product_id = $existing_products[0];
            }
        }
        
        // Prepare product data
        $product_args = array(
            'post_title' => sanitize_text_field($product_data['product_name']),
            'post_content' => wp_kses_post($product_data['description'] ?? ''),
            'post_status' => 'publish',
            'post_type' => 'product',
        );
        
        // Create or update product
        if ($existing_product_id) {
            $product_args['ID'] = $existing_product_id;
            $product_id = wp_update_post($product_args);
        } else {
            $product_id = wp_insert_post($product_args);
        }
        
        if (is_wp_error($product_id)) {
            return $product_id;
        }
        
        // Update product meta
        update_post_meta($product_id, '_vcore_product_id', $vcore_id);
        update_post_meta($product_id, '_sku', 'GLASSY-' . $vcore_id);
        update_post_meta($product_id, '_regular_price', $this->parse_price($product_data['price'] ?? ''));
        update_post_meta($product_id, '_price', $this->parse_price($product_data['price'] ?? ''));
        update_post_meta($product_id, '_stock_status', 'instock');
        update_post_meta($product_id, '_manage_stock', 'no');
        
        // Store additional specifications
        if (!empty($product_data['specifications'])) {
            update_post_meta($product_id, '_vcore_specifications', $product_data['specifications']);
        }
        
        // Store common fields
        $meta_fields = array('material', 'brand', 'usage_application', 'thickness', 'shape', 'pattern');
        foreach ($meta_fields as $field) {
            if (!empty($product_data[$field])) {
                update_post_meta($product_id, '_vcore_' . $field, sanitize_text_field($product_data[$field]));
            }
        }
        
        // Handle images
        if (!empty($product_data['images'])) {
            $this->process_product_images($product_id, $product_data['images']);
        }
        
        // Assign categories
        if (!empty($product_data['category'])) {
            $this->assign_product_categories($product_id, $product_data['category']);
        }
        
        return $product_id;
    }
    
    /**
     * Process product images (download from S3 and upload to WordPress)
     */
    private function process_product_images($product_id, $image_urls) {
        require_once(ABSPATH . 'wp-admin/includes/file.php');
        require_once(ABSPATH . 'wp-admin/includes/media.php');
        require_once(ABSPATH . 'wp-admin/includes/image.php');
        
        $image_ids = array();
        
        foreach ($image_urls as $index => $image_url) {
            if (empty($image_url)) continue;
            
            // Download image from S3
            $tmp_file = download_url($image_url);
            
            if (is_wp_error($tmp_file)) {
                continue; // Skip this image
            }
            
            // Prepare file array
            $file_array = array(
                'name' => basename($image_url),
                'tmp_name' => $tmp_file
            );
            
            // Upload to WordPress
            $attachment_id = media_handle_sideload($file_array, $product_id);
            
            // Clean up temp file
            @unlink($tmp_file);
            
            if (is_wp_error($attachment_id)) {
                continue;
            }
            
            // Set alt text
            update_post_meta($attachment_id, '_wp_attachment_image_alt', get_the_title($product_id));
            
            $image_ids[] = $attachment_id;
        }
        
        // Set featured image (first image)
        if (!empty($image_ids)) {
            set_post_thumbnail($product_id, $image_ids[0]);
            
            // Set gallery images (remaining images)
            if (count($image_ids) > 1) {
                update_post_meta($product_id, '_product_image_gallery', implode(',', array_slice($image_ids, 1)));
            }
        }
    }
    
    /**
     * Assign product to categories based on mapping
     */
    private function assign_product_categories($product_id, $vcore_category) {
        $category_paths = $this->category_mapping['category_mapping'][$vcore_category] ?? array();
        
        if (empty($category_paths)) {
            // Fallback to uncategorized
            $category_paths = array('uncategorized');
        }
        
        $term_ids = array();
        
        foreach ($category_paths as $path) {
            $term_id = $this->get_or_create_category_from_path($path);
            if ($term_id) {
                $term_ids[] = $term_id;
            }
        }
        
        if (!empty($term_ids)) {
            wp_set_object_terms($product_id, $term_ids, 'product_cat');
        }
    }
    
    /**
     * Get or create category from path (e.g., "luxury_glass.premium_bathrooms")
     */
    private function get_or_create_category_from_path($path) {
        $parts = explode('.', $path);
        
        if (count($parts) < 2) {
            return null;
        }
        
        $parent_key = $parts[0];
        $child_key = $parts[1];
        
        $menu_structure = $this->category_mapping['menu_structure'] ?? array();
        
        if (!isset($menu_structure[$parent_key])) {
            return null;
        }
        
        $parent_data = $menu_structure[$parent_key];
        $child_data = $parent_data['subcategories'][$child_key] ?? null;
        
        if (!$child_data) {
            return null;
        }
        
        // Get or create parent category
        $parent_term = get_term_by('slug', $parent_data['slug'], 'product_cat');
        if (!$parent_term) {
            $parent_result = wp_insert_term($parent_data['name'], 'product_cat', array(
                'slug' => $parent_data['slug'],
                'description' => $parent_data['description'] ?? ''
            ));
            
            if (is_wp_error($parent_result)) {
                return null;
            }
            
            $parent_term_id = $parent_result['term_id'];
        } else {
            $parent_term_id = $parent_term->term_id;
        }
        
        // Get or create child category
        $child_term = get_term_by('slug', $child_data['slug'], 'product_cat');
        if (!$child_term) {
            $child_result = wp_insert_term($child_data['name'], 'product_cat', array(
                'slug' => $child_data['slug'],
                'parent' => $parent_term_id
            ));
            
            if (is_wp_error($child_result)) {
                return null;
            }
            
            return $child_result['term_id'];
        }
        
        return $child_term->term_id;
    }
    
    /**
     * Create entire category structure
     */
    public function create_category_structure($request) {
        $menu_structure = $this->category_mapping['menu_structure'] ?? array();
        
        $created = array();
        
        foreach ($menu_structure as $parent_key => $parent_data) {
            // Create parent category
            $parent_term = get_term_by('slug', $parent_data['slug'], 'product_cat');
            
            if (!$parent_term) {
                $parent_result = wp_insert_term($parent_data['name'], 'product_cat', array(
                    'slug' => $parent_data['slug'],
                    'description' => $parent_data['description'] ?? ''
                ));
                
                if (!is_wp_error($parent_result)) {
                    $created[] = $parent_data['name'];
                    $parent_term_id = $parent_result['term_id'];
                } else {
                    continue;
                }
            } else {
                $parent_term_id = $parent_term->term_id;
            }
            
            // Create child categories
            foreach ($parent_data['subcategories'] as $child_key => $child_data) {
                $child_term = get_term_by('slug', $child_data['slug'], 'product_cat');
                
                if (!$child_term) {
                    $child_result = wp_insert_term($child_data['name'], 'product_cat', array(
                        'slug' => $child_data['slug'],
                        'parent' => $parent_term_id
                    ));
                    
                    if (!is_wp_error($child_result)) {
                        $created[] = $child_data['name'];
                    }
                }
            }
        }
        
        return rest_ensure_response(array(
            'success' => true,
            'created_categories' => $created,
            'message' => count($created) . ' categories created'
        ));
    }
    
    /**
     * Parse price from various formats
     */
    private function parse_price($price_string) {
        if (empty($price_string)) {
            return '';
        }
        
        // Extract numeric value from strings like "160/sqft", "24,999/Unit"
        preg_match('/[\d,]+/', $price_string, $matches);
        
        if (!empty($matches)) {
            return str_replace(',', '', $matches[0]);
        }
        
        return '';
    }
    
    /**
     * Add admin menu
     */
    public function add_admin_menu() {
        add_submenu_page(
            'woocommerce',
            'VCore Sync',
            'VCore Sync',
            'manage_woocommerce',
            'vcore-sync',
            array($this, 'admin_page')
        );
    }
    
    /**
     * Admin page content
     */
    public function admin_page() {
        ?>
        <div class="wrap">
            <h1>VCore Product Sync</h1>
            <p>This plugin receives product data from VCore and syncs it to WooCommerce.</p>
            
            <div class="card">
                <h2>API Endpoints</h2>
                <ul>
                    <li><strong>Sync Products:</strong> <code><?php echo rest_url('vcore/v1/sync-products'); ?></code></li>
                    <li><strong>Sync Single Product:</strong> <code><?php echo rest_url('vcore/v1/sync-single-product'); ?></code></li>
                    <li><strong>Create Categories:</strong> <code><?php echo rest_url('vcore/v1/create-categories'); ?></code></li>
                </ul>
                
                <h3>Authentication</h3>
                <p>Use WordPress Application Password for authentication.</p>
                <p><a href="<?php echo admin_url('profile.php'); ?>" class="button">Generate Application Password</a></p>
            </div>
            
            <div class="card">
                <h2>Category Structure</h2>
                <p>Categories will be automatically created when products are synced.</p>
                <form method="post" action="<?php echo admin_url('admin-post.php'); ?>">
                    <input type="hidden" name="action" value="vcore_create_categories">
                    <?php wp_nonce_field('vcore_create_categories'); ?>
                    <button type="submit" class="button button-primary">Create All Categories Now</button>
                </form>
            </div>
        </div>
        <?php
    }
}

// Initialize plugin
new Glassy_VCore_Sync();
