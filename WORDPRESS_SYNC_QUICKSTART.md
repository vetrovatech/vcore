# WordPress Sync - Quick Start Guide

## 🎯 What's Been Built

A complete one-click sync system that pushes products from your vcore database to WordPress/WooCommerce with:

✅ **WordPress Plugin** - Receives and processes product data  
✅ **Sync Utility** - Downloads S3 images and uploads to WordPress  
✅ **Admin Interface** - One-click sync button in vcore  
✅ **Category Mapping** - New use-case driven menu structure  
✅ **SEO Preservation** - Old URLs remain active  

---

## 🚀 Quick Start (5 Steps)

### Step 1: Install WordPress Plugin (2 minutes)

```bash
# Create plugin zip
cd wordpress-plugin
zip -r glassy-vcore-sync.zip glassy-vcore-sync.php category-structure.json
```

Then:
1. Go to https://glassy.in/wp-admin
2. **Plugins > Add New > Upload Plugin**
3. Upload `glassy-vcore-sync.zip`
4. Click **Activate**

### Step 2: Create Application Password (1 minute)

1. Go to **Users > Profile** in WordPress
2. Scroll to **Application Passwords**
3. Name: `VCore Sync`
4. Click **Add New**
5. **Copy the password** (format: `xxxx xxxx xxxx xxxx`)

### Step 3: Configure VCore (1 minute)

Add to `.env`:
```bash
WORDPRESS_URL=https://glassy.in
WORDPRESS_API_USER=admin
WORDPRESS_API_PASSWORD=xxxx xxxx xxxx xxxx  # Paste password here
WORDPRESS_SYNC_ENABLED=true
```

### Step 4: Run Migration (30 seconds)

```bash
python3 migrate_add_wordpress_sync.py
```

### Step 5: Sync Products (3 minutes)

1. Start vcore: `python3 app.py`
2. Go to: http://localhost:8080/admin/wordpress-sync
3. Click **Test Connection** ✓
4. Click **Create Categories** ✓
5. Click **Sync to WordPress** ✓

**Done!** All 74 products are now on WordPress.

---

## 📁 Files Created

### WordPress Plugin
- `wordpress-plugin/glassy-vcore-sync.php` - Main plugin file
- `wordpress-plugin/category-structure.json` - Category mapping
- `wordpress-plugin/README.md` - Installation guide

### VCore Files
- `utils/wordpress_sync.py` - Sync utility class
- `templates/admin/wordpress_sync.html` - Admin interface
- `migrate_add_wordpress_sync.py` - Database migration
- `config/wordpress.env.example` - Config template
- `setup-wordpress-sync.sh` - Quick setup script

### Updated Files
- `app.py` - Added WordPress sync routes

---

## 🎨 New Menu Structure

The plugin creates this category hierarchy in WordPress:

```
📁 Architectural Glass
   ├─ Commercial Buildings
   ├─ Office Spaces
   └─ Public Spaces

📁 Residential Glass
   ├─ Living Spaces
   ├─ Bedrooms
   └─ Windows & Doors

📁 Commercial Glass
   ├─ Retail & Hospitality
   ├─ Corporate Offices
   └─ Specialized Applications

📁 Luxury Glass
   ├─ Premium Bathrooms
   ├─ Designer Elements
   ├─ Outdoor Luxury
   └─ Premium Kitchens
```

Products are automatically assigned to correct categories based on their vcore category.

---

## 🔄 How It Works

1. **Click "Sync to WordPress"** in vcore admin
2. VCore reads all active products from database
3. For each product:
   - Downloads images from S3
   - Uploads images to WordPress Media Library
   - Maps category to new structure
   - Creates/updates WooCommerce product
4. Returns sync status (success/failed counts)

---

## 🎯 Next Steps (After Sync)

### In WordPress Admin:

1. **Create New Menu**:
   - Go to **Appearance > Menus**
   - Create "Main Navigation"
   - Add the new categories
   - Assign to Primary location

2. **Hide Old Menu**:
   - Rename old menu to "Legacy Catalog (Hidden)"
   - Add CSS to hide it (see README.md)

3. **Verify Products**:
   - Check **Products** page
   - Verify images loaded
   - Check categories assigned correctly

4. **Submit Sitemap**:
   - Go to Google Search Console
   - Submit updated sitemap

---

## 📊 Monitoring

Access sync dashboard at: `/admin/wordpress-sync`

Shows:
- Total products
- Synced products
- Pending sync
- Last sync time

---

## 🆘 Troubleshooting

### Connection Test Fails
- Check Application Password in `.env`
- Verify WordPress URL is correct

### Images Not Uploading
- Check S3 images are publicly accessible
- Verify WordPress upload permissions

### Categories Not Creating
- Ensure WooCommerce is installed
- Check user has admin permissions

**Full troubleshooting guide**: See `wordpress-plugin/README.md`

---

## ⏱️ Timeline

- **Setup**: 5 minutes
- **First Sync**: 3 minutes (74 products)
- **Menu Setup**: 10 minutes
- **Testing**: 15 minutes

**Total**: ~30 minutes to full launch! 🚀

---

## 📞 Support

All documentation is in:
- `wordpress-plugin/README.md` - Full installation guide
- `implementation_plan.md` - Technical details
- `task.md` - Progress tracking

---

## ✅ Checklist

Before launch:
- [ ] WordPress plugin installed
- [ ] Application Password created
- [ ] `.env` configured
- [ ] Migration completed
- [ ] Connection tested
- [ ] Categories created
- [ ] Products synced
- [ ] New menu created
- [ ] Old menu hidden
- [ ] Products verified

**Ready to launch!** 🎉
