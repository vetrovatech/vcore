#!/usr/bin/env python3
"""
Create a sample watermarked image for review
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
img = Image.open(BytesIO(response.content))
print(f"Image size: {img.size}")

# Convert to RGBA if needed
if img.mode != 'RGBA':
    img = img.convert('RGBA')

# Create watermark layer
watermark = Image.new('RGBA', img.size, (0, 0, 0, 0))
draw = ImageDraw.Draw(watermark)

# Calculate font size (5% of image height)
font_size = int(img.size[1] * 0.05)
try:
    # Try to use a nice font
    font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", font_size)
except:
    # Fallback to default font
    font = ImageFont.load_default()

# Watermark text
text = "Glassy India"

# Get text bounding box
bbox = draw.textbbox((0, 0), text, font=font)
text_width = bbox[2] - bbox[0]
text_height = bbox[3] - bbox[1]

# Position: bottom-right corner with padding
padding = int(img.size[0] * 0.02)  # 2% padding
x = img.size[0] - text_width - padding
y = img.size[1] - text_height - padding

# Draw text with outline for better visibility
# Draw outline (black)
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
output_path = 'sample_watermarked_image.jpg'
watermarked_rgb.save(output_path, 'JPEG', quality=95)

print(f"\n✅ Sample watermarked image saved: {output_path}")
print(f"Original product: {product_name}")
print(f"\nWatermark details:")
print(f"  - Position: Bottom-right corner")
print(f"  - Text: 'Glassy India'")
print(f"  - Style: White text with black outline")
print(f"  - Opacity: Semi-transparent (78%)")
print(f"  - Size: {font_size}px ({int(font_size/img.size[1]*100)}% of image height)")
