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
        self.s3_client = boto3.client(
            's3',
            aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.environ.get('AWS_SECRET_ACCESS_KEY'),
            region_name=self.region
        )
    
    def upload_product_image(self, file, category, product_name, image_number=1):
        """
        Upload a product image to S3
        
        Args:
            file: FileStorage object from Flask request.files
            category: Product category (for folder structure)
            product_name: Product name (for filename)
            image_number: Image number (1-4)
        
        Returns:
            str: Public S3 URL or None if upload fails
        """
        try:
            # Secure the filename
            original_filename = secure_filename(file.filename)
            file_ext = os.path.splitext(original_filename)[1] or '.png'
            
            # Create safe category and product name for S3 path
            category_safe = category.replace(' ', '_').replace('/', '_')
            product_safe = product_name.replace(' ', '_').replace('/', '_')
            
            # Generate unique filename
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{product_safe}_{image_number}{file_ext}"
            
            # S3 key (path in bucket)
            s3_key = f"product-images/{category_safe}/{filename}"
            
            # Upload to S3
            self.s3_client.upload_fileobj(
                file,
                self.bucket_name,
                s3_key,
                ExtraArgs={
                    'ContentType': file.content_type or 'image/png',
                    'ACL': 'public-read'
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
