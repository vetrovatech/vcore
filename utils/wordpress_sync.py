"""
WordPress Sync Utility
Syncs products from vcore database to WordPress/WooCommerce
"""

import os
import requests
import json
from typing import Dict, List, Optional
from datetime import datetime
import base64


class WordPressSync:
    """Handle synchronization of products to WordPress"""
    
    def __init__(self):
        self.wp_url = os.getenv('WORDPRESS_URL', 'https://glassy.in')
        self.wp_user = os.getenv('WORDPRESS_API_USER', 'admin')
        self.wp_password = os.getenv('WORDPRESS_API_PASSWORD', '')
        self.api_base = f"{self.wp_url}/wp-json/vcore/v1"
        
        # Create auth header
        credentials = f"{self.wp_user}:{self.wp_password}"
        token = base64.b64encode(credentials.encode()).decode()
        self.headers = {
            'Authorization': f'Basic {token}',
            'Content-Type': 'application/json'
        }
    
    def test_connection(self) -> Dict:
        """Test WordPress API connection"""
        try:
            response = requests.get(
                f"{self.wp_url}/wp-json/wc/v3/system_status",
                headers=self.headers,
                timeout=10
            )
            
            if response.status_code == 200:
                return {'success': True, 'message': 'Connection successful'}
            else:
                return {
                    'success': False,
                    'message': f'Connection failed: {response.status_code}'
                }
        except Exception as e:
            return {'success': False, 'message': f'Error: {str(e)}'}
    
    def create_categories(self) -> Dict:
        """Create category structure in WordPress"""
        try:
            response = requests.post(
                f"{self.api_base}/create-categories",
                headers=self.headers,
                timeout=30
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                return {
                    'success': False,
                    'message': f'Failed to create categories: {response.text}'
                }
        except Exception as e:
            return {'success': False, 'message': f'Error: {str(e)}'}
    
    def sync_all_products(self, db_connection) -> Dict:
        """Sync all active products to WordPress"""
        from models import Product
        
        try:
            # Get all active products
            products = Product.query.filter_by(is_active=True).all()
            
            if not products:
                return {
                    'success': False,
                    'message': 'No active products found'
                }
            
            # Prepare product data
            products_data = []
            for product in products:
                product_dict = self._prepare_product_data(product)
                products_data.append(product_dict)
            
            # Send to WordPress in batches (smaller batches to avoid timeout)
            batch_size = 3  # Reduced from 10 to handle image uploads
            total_success = 0
            total_failed = 0
            errors = []
            
            for i in range(0, len(products_data), batch_size):
                batch = products_data[i:i + batch_size]
                
                response = requests.post(
                    f"{self.api_base}/sync-products",
                    headers=self.headers,
                    json={'products': batch},
                    timeout=120  # Increased from 60 to handle image downloads
                )
                
                if response.status_code == 200:
                    result = response.json()
                    total_success += result.get('success', 0)
                    total_failed += result.get('failed', 0)
                    errors.extend(result.get('errors', []))
                else:
                    total_failed += len(batch)
                    errors.append({
                        'batch': f'{i}-{i+len(batch)}',
                        'error': response.text
                    })
            
            return {
                'success': True,
                'total_products': len(products_data),
                'synced': total_success,
                'failed': total_failed,
                'errors': errors
            }
            
        except Exception as e:
            return {
                'success': False,
                'message': f'Sync failed: {str(e)}'
            }
    
    def sync_single_product(self, product) -> Dict:
        """Sync a single product to WordPress"""
        try:
            product_data = self._prepare_product_data(product)
            
            response = requests.post(
                f"{self.api_base}/sync-single-product",
                headers=self.headers,
                json=product_data,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                
                # Update product with WordPress ID
                if result.get('success') and result.get('product_id'):
                    product.wordpress_id = result['product_id']
                    product.last_wordpress_sync = datetime.utcnow()
                
                return result
            else:
                return {
                    'success': False,
                    'message': f'Sync failed: {response.text}'
                }
                
        except Exception as e:
            return {
                'success': False,
                'message': f'Error: {str(e)}'
            }
    
    def _prepare_product_data(self, product) -> Dict:
        """Prepare product data for WordPress"""
        # Get all image URLs
        images = []
        for i in range(1, 5):
            img_url = getattr(product, f'image_{i}_url', None)
            if img_url:
                images.append(img_url)
        
        # Parse specifications
        specs = product.get_specifications() if hasattr(product, 'get_specifications') else {}
        
        return {
            'id': product.id,
            'product_name': product.product_name,
            'category': product.category,
            'description': product.description or '',
            'price': product.price or '',
            'images': images,
            'material': product.material,
            'brand': product.brand,
            'usage_application': product.usage_application,
            'thickness': product.thickness,
            'shape': product.shape,
            'pattern': product.pattern,
            'specifications': json.dumps(specs) if specs else '',
            'availability': product.availability or 'In Stock',
            'product_url': product.product_url or ''
        }
    
    def get_sync_status(self, db_connection) -> Dict:
        """Get sync status statistics"""
        from models import Product
        
        try:
            total_products = Product.query.filter_by(is_active=True).count()
            synced_products = Product.query.filter(
                Product.is_active == True,
                Product.wordpress_id.isnot(None)
            ).count()
            
            return {
                'success': True,
                'total_products': total_products,
                'synced_products': synced_products,
                'pending_sync': total_products - synced_products
            }
        except Exception as e:
            return {
                'success': False,
                'message': f'Error: {str(e)}'
            }
