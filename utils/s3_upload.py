"""
S3 Upload Utility for Product Images
"""
import boto3
from botocore.exceptions import ClientError
from werkzeug.utils import secure_filename
import os
from datetime import datetime

class S3Uploader:
    """Handle S3 image uploads for product catalog"""
    
    def __init__(self):
        self.bucket_name = os.environ.get('AWS_BUCKET_NAME', 'glassyimages')
        self.region = os.environ.get('AWS_REGION', 'ap-south-1')
        
        # Initialize S3 client
        # In Lambda, boto3 automatically uses the execution role credentials
        # For local development, use explicit credentials from environment
        if os.environ.get('ENVIRONMENT') == 'production':
            # Production (Lambda) - use IAM role
            self.s3_client = boto3.client('s3', region_name=self.region)
        else:
            # Local development - use explicit credentials
            self.s3_client = boto3.client(
                's3',
                aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_ID'),
                aws_secret_access_key=os.environ.get('AWS_SECRET_ACCESS_KEY'),
                region_name=self.region
            )
    
    def upload_product_image(self, file, category, product_name, image_number=1):
        """
        Upload a product image to S3 with automatic watermarking
        
        Args:
            file: FileStorage object from Flask request.files
            category: Product category (for folder structure)
            product_name: Product name (for filename)
            image_number: Image number (1-4)
        
        Returns:
            str: Public S3 URL or None if upload fails
        """
        try:
            from PIL import Image, ImageDraw, ImageFont
            from io import BytesIO
            
            # Read image data
            image_data = file.read()
            file.seek(0)  # Reset file pointer
            
            # Add watermark
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
                font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", font_size)
            except:
                try:
                    # Fallback for Linux/production
                    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
                except:
                    font = ImageFont.load_default()
            
            # Watermark text
            watermark_text = "Glassy India"
            
            # Get text bounding box
            bbox = draw.textbbox((0, 0), watermark_text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            
            # Position: bottom-right corner with padding
            padding = int(img.size[0] * 0.02)
            x = img.size[0] - text_width - padding
            y = img.size[1] - text_height - padding
            
            # Draw text with outline for better visibility
            outline_width = 2
            for adj_x in range(-outline_width, outline_width + 1):
                for adj_y in range(-outline_width, outline_width + 1):
                    draw.text((x + adj_x, y + adj_y), watermark_text, font=font, fill=(0, 0, 0, 180))
            
            # Draw main text (white, semi-transparent)
            draw.text((x, y), watermark_text, font=font, fill=(255, 255, 255, 200))
            
            # Composite watermark onto image
            watermarked = Image.alpha_composite(img, watermark)
            
            # Convert back to RGB for saving as JPEG
            watermarked_rgb = watermarked.convert('RGB')
            
            # Save to bytes
            output = BytesIO()
            watermarked_rgb.save(output, format='JPEG', quality=95)
            output.seek(0)
            
            # Secure the filename
            original_filename = secure_filename(file.filename)
            file_ext = '.jpg'  # Always use .jpg for watermarked images
            
            # Create safe category and product name for S3 path
            category_safe = category.replace(' ', '_').replace('/', '_')
            product_safe = product_name.replace(' ', '_').replace('/', '_')
            
            # Generate unique filename with timestamp to avoid caching issues
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{product_safe}_{image_number}_{timestamp}{file_ext}"
            
            # S3 key (path in bucket)
            s3_key = f"product-images/{category_safe}/{filename}"
            
            # Upload watermarked image to S3
            self.s3_client.upload_fileobj(
                output,
                self.bucket_name,
                s3_key,
                ExtraArgs={
                    'ContentType': 'image/jpeg',
                    'CacheControl': 'no-cache, must-revalidate'  # Prevent caching issues
                }
            )
            
            # Generate public URL
            url = f"https://{self.bucket_name}.s3.{self.region}.amazonaws.com/{s3_key}"
            return url
            
        except ClientError as e:
            print(f"Error uploading to S3: {e}")
            return None
        except Exception as e:
            print(f"Unexpected error: {e}")
            return None
    
    def upload_bathqube_attachment(self, file, quote_id, stage):
        """Upload an ops attachment for a Bathqube work order.

        Unlike upload_product_image, this does NOT watermark — these are
        internal ops files (measurement photos, fabrication docs,
        installation photos, signed handover sheets) and preserving the
        original is important.

        Returns the public S3 URL or None on failure.
        """
        try:
            original_filename = secure_filename(file.filename or '') or 'file'
            ext = ''
            if '.' in original_filename:
                ext = '.' + original_filename.rsplit('.', 1)[1].lower()

            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            stage_safe = (stage or 'unknown').replace('/', '_')
            s3_key = f"bathqube-attachments/{quote_id}/{stage_safe}/{timestamp}{ext}"

            # Best-effort content-type guess. Default to octet-stream so the
            # browser at least doesn't try to render binary as text.
            content_type = 'application/octet-stream'
            ct_map = {
                '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
                '.png': 'image/png',  '.gif':  'image/gif',
                '.webp': 'image/webp','.pdf':  'application/pdf',
                '.heic': 'image/heic',
            }
            content_type = ct_map.get(ext, content_type)

            self.s3_client.upload_fileobj(
                file,
                self.bucket_name,
                s3_key,
                ExtraArgs={'ContentType': content_type},
            )
            return f"https://{self.bucket_name}.s3.{self.region}.amazonaws.com/{s3_key}"
        except ClientError as e:
            print(f"Error uploading bathqube attachment: {e}")
            return None
        except Exception as e:
            print(f"Unexpected error uploading bathqube attachment: {e}")
            return None

    def delete_image(self, s3_url):
        """
        Delete an image from S3
        
        Args:
            s3_url: Full S3 URL of the image
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Extract S3 key from URL
            # URL format: https://bucket.s3.region.amazonaws.com/key
            s3_key = s3_url.split(f"{self.bucket_name}.s3.{self.region}.amazonaws.com/")[1]
            
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=s3_key
            )
            return True
            
        except Exception as e:
            print(f"Error deleting from S3: {e}")
            return False
    
    def test_connection(self):
        """Test S3 connection"""
        try:
            self.s3_client.head_bucket(Bucket=self.bucket_name)
            return True
        except ClientError:
            return False
