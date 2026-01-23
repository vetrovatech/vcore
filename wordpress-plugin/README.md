# WordPress Sync Plugin Installation Guide

## Overview

This plugin enables one-click synchronization of products from your VCore database to WordPress/WooCommerce.

---

## Installation Steps

### 1. Upload Plugin to WordPress

1. **Zip the plugin folder**:
   ```bash
   cd /Users/montygupta/My/personal/bin/azure/vetrova/github/vcore/wordpress-plugin
   zip -r glassy-vcore-sync.zip glassy-vcore-sync.php category-structure.json
   ```

2. **Upload to WordPress**:
   - Log in to WordPress admin (https://glassy.in/wp-admin)
   - Go to **Plugins > Add New > Upload Plugin**
   - Choose `glassy-vcore-sync.zip`
   - Click **Install Now**
   - Click **Activate Plugin**

### 2. Create Application Password

1. Go to **Users > Profile** in WordPress admin
2. Scroll to **Application Passwords** section
3. Enter name: `VCore Sync`
4. Click **Add New Application Password**
5. **Copy the generated password** (format: `xxxx xxxx xxxx xxxx`)

### 3. Configure VCore

1. Add to `.env` file:
   ```bash
   WORDPRESS_URL=https://glassy.in
   WORDPRESS_API_USER=admin
   WORDPRESS_API_PASSWORD=xxxx xxxx xxxx xxxx  # Paste the Application Password here
   WORDPRESS_SYNC_ENABLED=true
   ```

2. Run database migration:
   ```bash
   python migrate_add_wordpress_sync.py
   ```

### 4. Create Category Structure

1. In VCore admin, go to **Admin > WordPress Sync**
2. Click **Test Connection** to verify setup
3. Click **Create Categories** to set up the new menu structure

### 5. Sync Products

1. Click **Sync to WordPress** button
2. Wait for sync to complete (may take 2-3 minutes for 74 products)
3. Check results and verify products in WordPress

---

## WordPress Menu Setup

### Hide Old Menu

1. Go to **Appearance > Menus** in WordPress
2. Rename current menu to "Legacy Catalog (Hidden)"
3. Go to **Appearance > Customize > Additional CSS**
4. Add this CSS:
   ```css
   /* Hide legacy catalog menu */
   .menu-item-legacy-catalog {
       display: none !important;
   }
   ```

### Create New Menu

1. Go to **Appearance > Menus**
2. Create new menu: "Main Navigation"
3. Add categories in this structure:
   - Architectural Glass
     - Commercial Buildings
     - Office Spaces
     - Public Spaces
   - Residential Glass
     - Living Spaces
     - Bedrooms
     - Windows & Doors
   - Commercial Glass
     - Retail & Hospitality
     - Corporate Offices
     - Specialized Applications
   - Luxury Glass
     - Premium Bathrooms
     - Designer Elements
     - Outdoor Luxury
     - Premium Kitchens

4. Assign to **Primary Menu** location
5. Save menu

---

## Verification Checklist

- [ ] Plugin installed and activated
- [ ] Application Password created
- [ ] VCore `.env` configured
- [ ] Database migration completed
- [ ] Connection test successful
- [ ] Categories created in WordPress
- [ ] Products synced successfully
- [ ] New menu structure created
- [ ] Old menu hidden
- [ ] Product images displaying correctly
- [ ] Product URLs working
- [ ] Old URLs still accessible (SEO preserved)

---

## Troubleshooting

### Connection Test Fails

**Error**: "Connection failed: 401"
- **Solution**: Check Application Password is correct in `.env`
- **Solution**: Verify WordPress user has admin/manager role

**Error**: "Connection failed: timeout"
- **Solution**: Check WordPress URL is correct
- **Solution**: Verify glassy.in is accessible

### Image Upload Fails

**Error**: "Failed to upload image"
- **Solution**: Check WordPress media upload permissions
- **Solution**: Verify S3 images are publicly accessible
- **Solution**: Increase PHP `upload_max_filesize` and `post_max_size`

### Categories Not Creating

**Error**: "Failed to create categories"
- **Solution**: Check WooCommerce is installed and activated
- **Solution**: Verify user has permission to manage product categories

### Products Not Syncing

**Error**: "Sync failed"
- **Solution**: Check WordPress error logs (`wp-content/debug.log`)
- **Solution**: Verify database connection in VCore
- **Solution**: Try syncing one product first to isolate issue

---

## Maintenance

### Re-sync Products

To update products after changes in VCore:
1. Go to **Admin > WordPress Sync**
2. Click **Sync to WordPress**
3. Existing products will be updated, new products will be created

### Sync Single Product

To sync a specific product:
- Use API endpoint: `POST /api/wordpress/sync-product/<product_id>`
- Or modify product in VCore and it will auto-sync (if enabled)

### Monitor Sync Status

Check sync statistics in the WordPress Sync admin page:
- Total products
- Synced products
- Pending sync
- Last sync timestamp

---

## Support

For issues or questions:
1. Check WordPress error logs
2. Check VCore application logs
3. Verify all configuration steps completed
4. Test with a single product first

---

## Next Steps

After successful setup:
1. Submit updated sitemap to Google Search Console
2. Monitor WordPress for 48 hours
3. Check product pages for SEO elements
4. Test navigation on mobile devices
5. Update any hardcoded links in content
