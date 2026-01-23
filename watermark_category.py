#!/usr/bin/env python3
"""
Add watermarks to all product images in a specific category
"""

import pymysql
import requests
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import boto3
from botocore.exceptions import ClientError
import os
import time

# Configuration
CATEGORY = "Shower Enclosures"
FONT_PATH = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
WATERMARK_TEXT = "Glassy India"
AWS_BUCKET = "glassyimages"
AWS_REGION = "ap-south-1"

# Initialize S3 client
s3_client = boto3.client('s3', region_name=AWS_REGION)

def add_watermark(image_data):
    """Add watermark to image"""
    # Open image
    img = Image.open(BytesIO(image_data))
    
    # Convert to RGBA if needed
    if img.mode != 'RGBA':
        img = img.convert('RGBA')
    
    # Create watermark layer
    watermark = Image.new('RGBA', img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(watermark)
    
    # Calculate font size (5% of image height)
    font_size = int(img.size[1] * 0.05)
    
    # Load Arial Bold font
    try:
        font = ImageFont.truetype(FONT_PATH, font_size)
    except:
        print("  ⚠️  Could not load Arial Bold, using default")
        font = ImageFont.load_default()
    
    # Get text bounding box
    bbox = draw.textbbox((0, 0), WATERMARK_TEXT, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    
    # Position: bottom-right corner with padding
    padding = int(img.size[0] * 0.02)
    x = img.size[0] - text_width - padding
    y = img.size[1] - text_height - padding
    
    # Draw text with outline
    outline_width = 2
    for adj_x in range(-outline_width, outline_width + 1):
        for adj_y in range(-outline_width, outline_width + 1):
            draw.text((x + adj_x, y + adj_y), WATERMARK_TEXT, font=font, fill=(0, 0, 0, 180))
    
    # Draw main text (white, semi-transparent)
    draw.text((x, y), WATERMARK_TEXT, font=font, fill=(255, 255, 255, 200))
    
    # Composite watermark onto image
    watermarked = Image.alpha_composite(img, watermark)
    
    # Convert back to RGB for saving as JPEG
    watermarked_rgb = watermarked.convert('RGB')
    
    # Save to bytes
    output = BytesIO()
    watermarked_rgb.save(output, format='JPEG', quality=95)
    output.seek(0)
    
    return output.getvalue()

def upload_to_s3(image_data, s3_key):
    """Upload image to S3"""
    try:
        s3_client.put_object(
            Bucket=AWS_BUCKET,
            Key=s3_key,
            Body=image_data,
            ContentType='image/jpeg'
        )
        return True
    except ClientError as e:
        print(f"  ❌ S3 upload error: {e}")
        return False

# Connect to database
print(f"🔍 Fetching products from category: {CATEGORY}")
conn = pymysql.connect(
    host='ls-71c57fcd322c32a3616fd3e00e212391e383d4ba.c7cuq02uskcx.ap-south-1.rds.amazonaws.com',
    user='cdcuser',
    password='Divyam123',
    database='vcore',
    port=3306
)

cursor = conn.cursor()
cursor.execute('''
    SELECT id, product_name, image_1_url, image_2_url, image_3_url, image_4_url
    FROM products 
    WHERE category = %s
    AND (image_1_url IS NOT NULL OR image_2_url IS NOT NULL OR image_3_url IS NOT NULL OR image_4_url IS NOT NULL)
''', (CATEGORY,))

products = cursor.fetchall()
print(f"Found {len(products)} products with images\n")

# Process each product
total_images = 0
successful_images = 0
failed_images = 0

for product in products:
    product_id, product_name, img1, img2, img3, img4 = product
    print(f"📦 Processing: {product_name}")
    
    # Process each image
    for img_num, img_url in enumerate([img1, img2, img3, img4], 1):
        if not img_url or not img_url.startswith('http'):
            continue
        
        total_images += 1
        
        try:
            # Download image
            print(f"  📥 Downloading image {img_num}...")
            response = requests.get(img_url, timeout=15)
            if response.status_code != 200:
                print(f"  ❌ Failed to download (status {response.status_code})")
                failed_images += 1
                continue
            
            # Add watermark
            print(f"  🎨 Adding watermark...")
            watermarked_data = add_watermark(response.content)
            
            # Extract S3 key from URL
            # URL format: https://glassyimages.s3.ap-south-1.amazonaws.com/product-images/...
            if 'glassyimages' in img_url:
                s3_key = img_url.split('.amazonaws.com/')[-1]
            else:
                # If not S3, create new key
                s3_key = f"product-images/{CATEGORY.replace(' ', '_')}/{product_name.replace(' ', '_')}_watermarked_{img_num}.jpg"
            
            # Upload to S3
            print(f"  ⬆️  Uploading to S3: {s3_key}")
            if upload_to_s3(watermarked_data, s3_key):
                successful_images += 1
                print(f"  ✅ Image {img_num} watermarked successfully!")
            else:
                failed_images += 1
            
            # Small delay to avoid rate limiting
            time.sleep(0.5)
            
        except Exception as e:
            print(f"  ❌ Error processing image {img_num}: {e}")
            failed_images += 1
    
    print()

conn.close()

# Summary
print("=" * 60)
print("📊 SUMMARY")
print("=" * 60)
print(f"Category: {CATEGORY}")
print(f"Products processed: {len(products)}")
print(f"Total images: {total_images}")
print(f"✅ Successful: {successful_images}")
print(f"❌ Failed: {failed_images}")
print("=" * 60)
print("\n✅ Watermarking complete for this category!")
print("Images have been uploaded to S3 and will be visible immediately.")
