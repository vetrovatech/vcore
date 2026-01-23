#!/usr/bin/env python3
"""
Create watermark samples with different fonts
"""

import pymysql
import requests
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import os

# Database connection
conn = pymysql.connect(
    host='ls-71c57fcd322c32a3616fd3e00e212391e383d4ba.c7cuq02uskcx.ap-south-1.rds.amazonaws.com',
    user='cdcuser',
    password='Divyam123',
    database='vcore',
    port=3306
)

cursor = conn.cursor()
cursor.execute('''
    SELECT id, product_name, image_1_url 
    FROM products 
    WHERE image_1_url IS NOT NULL 
    AND image_1_url != "" 
    AND image_1_url LIKE "http%"
    LIMIT 1
''')
result = cursor.fetchone()
conn.close()

if not result:
    print("No product images found in database")
    exit(1)

product_id, product_name, image_url = result
print(f"Processing: {product_name}")
print(f"Image URL: {image_url}")

# Download image
print("Downloading image...")
response = requests.get(image_url, timeout=10)
if response.status_code != 200:
    print(f"Failed to download image: {response.status_code}")
    exit(1)

# Open image
original_img = Image.open(BytesIO(response.content))
print(f"Image size: {original_img.size}")

# Font options to try
font_options = [
    {
        'name': 'Helvetica Bold',
        'path': '/System/Library/Fonts/Helvetica.ttc',
        'index': 1,  # Bold variant
        'filename': 'sample_watermark_helvetica_bold.jpg'
    },
    {
        'name': 'Arial Bold',
        'path': '/System/Library/Fonts/Supplemental/Arial Bold.ttf',
        'index': 0,
        'filename': 'sample_watermark_arial_bold.jpg'
    },
    {
        'name': 'Futura Medium',
        'path': '/System/Library/Fonts/Supplemental/Futura.ttc',
        'index': 1,
        'filename': 'sample_watermark_futura.jpg'
    },
    {
        'name': 'Avenir Heavy',
        'path': '/System/Library/Fonts/Avenir.ttc',
        'index': 5,  # Heavy variant
        'filename': 'sample_watermark_avenir.jpg'
    },
    {
        'name': 'Impact',
        'path': '/Library/Fonts/Impact.ttf',
        'index': 0,
        'filename': 'sample_watermark_impact.jpg'
    }
]

text = "Glassy India"

for font_option in font_options:
    try:
        # Convert to RGBA if needed
        img = original_img.copy()
        if img.mode != 'RGBA':
            img = img.convert('RGBA')
        
        # Create watermark layer
        watermark = Image.new('RGBA', img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(watermark)
        
        # Calculate font size (5% of image height)
        font_size = int(img.size[1] * 0.05)
        
        # Load font
        try:
            if 'index' in font_option and font_option['path'].endswith('.ttc'):
                font = ImageFont.truetype(font_option['path'], font_size, index=font_option['index'])
            else:
                font = ImageFont.truetype(font_option['path'], font_size)
        except:
            print(f"  ⚠️  Could not load {font_option['name']}, skipping...")
            continue
        
        # Get text bounding box
        bbox = draw.textbbox((0, 0), text, font=font)
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
                draw.text((x + adj_x, y + adj_y), text, font=font, fill=(0, 0, 0, 180))
        
        # Draw main text (white, semi-transparent)
        draw.text((x, y), text, font=font, fill=(255, 255, 255, 200))
        
        # Composite watermark onto image
        watermarked = Image.alpha_composite(img, watermark)
        
        # Convert back to RGB for saving as JPEG
        watermarked_rgb = watermarked.convert('RGB')
        
        # Save sample
        watermarked_rgb.save(font_option['filename'], 'JPEG', quality=95)
        
        print(f"  ✅ Created: {font_option['filename']} ({font_option['name']})")
        
    except Exception as e:
        print(f"  ❌ Error with {font_option['name']}: {e}")

print(f"\n✅ All samples created!")
print(f"Original product: {product_name}")
