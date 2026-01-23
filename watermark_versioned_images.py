#!/usr/bin/env python3
"""
Watermark images with ?v= version parameters and clean up URLs
"""

import pymysql
import requests
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import boto3
from botocore.exceptions import ClientError
import time

# Configuration
FONT_PATH = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
WATERMARK_TEXT = "Glassy India"
AWS_BUCKET = "glassyimages"
AWS_REGION = "ap-south-1"

# Initialize S3 client
s3_client = boto3.client('s3', region_name=AWS_REGION)

def add_watermark(image_data):
    """Add watermark to image"""
    img = Image.open(BytesIO(image_data))
    
    if img.mode != 'RGBA':
        img = img.convert('RGBA')
    
    watermark = Image.new('RGBA', img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(watermark)
    
    font_size = int(img.size[1] * 0.05)
    
    try:
        font = ImageFont.truetype(FONT_PATH, font_size)
    except:
        font = ImageFont.load_default()
    
    bbox = draw.textbbox((0, 0), WATERMARK_TEXT, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    
    padding = int(img.size[0] * 0.02)
    x = img.size[0] - text_width - padding
    y = img.size[1] - text_height - padding
    
    # Outline
    outline_width = 2
    for adj_x in range(-outline_width, outline_width + 1):
        for adj_y in range(-outline_width, outline_width + 1):
            draw.text((x + adj_x, y + adj_y), WATERMARK_TEXT, font=font, fill=(0, 0, 0, 180))
    
    # Main text
    draw.text((x, y), WATERMARK_TEXT, font=font, fill=(255, 255, 255, 200))
    
    watermarked = Image.alpha_composite(img, watermark)
    watermarked_rgb = watermarked.convert('RGB')
    
    output = BytesIO()
    watermarked_rgb.save(output, format='JPEG', quality=95)
    output.seek(0)
    
    return output.getvalue()

def upload_to_s3(image_data, s3_key):
    """Upload image to S3 with no-cache headers"""
    try:
        s3_client.put_object(
            Bucket=AWS_BUCKET,
            Key=s3_key,
            Body=image_data,
            ContentType='image/jpeg',
            CacheControl='no-cache, must-revalidate'
        )
        return True
    except ClientError as e:
        print(f"    ❌ S3 upload error: {e}")
        return False

# Connect to database
print("🔍 Finding images with version parameters...")
conn = pymysql.connect(
    host='ls-71c57fcd322c32a3616fd3e00e212391e383d4ba.c7cuq02uskcx.ap-south-1.rds.amazonaws.com',
    user='cdcuser',
    password='Divyam123',
    database='vcore',
    port=3306
)

cursor = conn.cursor()
cursor.execute('''
    SELECT id, product_name, 
           image_1_url, image_2_url, image_3_url, image_4_url
    FROM products 
    WHERE image_1_url LIKE '%?v=%' 
       OR image_2_url LIKE '%?v=%'
       OR image_3_url LIKE '%?v=%'
       OR image_4_url LIKE '%?v=%'
''')

products = cursor.fetchall()
print(f"Found {len(products)} products with versioned URLs\n")

# Statistics
total_images = 0
successful_images = 0
failed_images = 0
urls_updated = []

for product in products:
    product_id, product_name, img1, img2, img3, img4 = product
    print(f"📦 {product_name}")
    
    new_urls = [None, None, None, None]
    
    # Process each image
    for img_num, img_url in enumerate([img1, img2, img3, img4], 1):
        if not img_url or '?v=' not in img_url:
            new_urls[img_num - 1] = img_url  # Keep original
            continue
        
        total_images += 1
        
        try:
            # Download image (with version parameter)
            response = requests.get(img_url, timeout=15)
            if response.status_code != 200:
                print(f"    ❌ Image {img_num}: Download failed ({response.status_code})")
                failed_images += 1
                new_urls[img_num - 1] = img_url  # Keep original
                continue
            
            # Watermark
            watermarked_data = add_watermark(response.content)
            
            # Extract S3 key (remove ?v= parameter)
            clean_url = img_url.split('?')[0]
            s3_key = clean_url.split('.amazonaws.com/')[-1]
            
            # Upload
            if upload_to_s3(watermarked_data, s3_key):
                successful_images += 1
                new_urls[img_num - 1] = clean_url  # Store clean URL
                print(f"    ✅ Image {img_num}: Watermarked & URL cleaned")
            else:
                failed_images += 1
                new_urls[img_num - 1] = img_url  # Keep original
            
            time.sleep(0.3)
            
        except Exception as e:
            print(f"    ❌ Image {img_num}: {str(e)[:50]}")
            failed_images += 1
            new_urls[img_num - 1] = img_url  # Keep original
    
    # Update database with clean URLs
    try:
        cursor.execute('''
            UPDATE products 
            SET image_1_url = %s,
                image_2_url = %s,
                image_3_url = %s,
                image_4_url = %s
            WHERE id = %s
        ''', (new_urls[0], new_urls[1], new_urls[2], new_urls[3], product_id))
        conn.commit()
        urls_updated.append(product_name)
        print(f"    📝 Database updated with clean URLs")
    except Exception as e:
        print(f"    ⚠️  Database update failed: {e}")
    
    print()

conn.close()

# Summary
print("="*60)
print("📊 SUMMARY")
print("="*60)
print(f"Products processed: {len(products)}")
print(f"Total images: {total_images}")
print(f"✅ Successful: {successful_images}")
print(f"❌ Failed: {failed_images}")
print(f"📝 URLs cleaned: {len(urls_updated)} products")
print("="*60)
print("\n✅ Versioned images watermarked and URLs cleaned!")
print("All ?v= parameters removed from database.")
