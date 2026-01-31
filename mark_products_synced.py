#!/usr/bin/env python3
"""
Mark all products as synced to WordPress
This script updates the last_wordpress_sync timestamp for all active products
"""

from app import app, db
from models import Product
from datetime import datetime

def mark_all_synced():
    """Mark all active products as synced"""
    with app.app_context():
        # Check current status
        total = Product.query.filter_by(is_active=True).count()
        synced = Product.query.filter(
            Product.is_active == True, 
            Product.last_wordpress_sync.isnot(None)
        ).count()
        never_synced = Product.query.filter(
            Product.is_active == True, 
            Product.last_wordpress_sync == None
        ).count()
        
        print(f'📊 Current Status:')
        print(f'   Total active products: {total}')
        print(f'   Already marked as synced: {synced}')
        print(f'   Never synced (NULL): {never_synced}')
        print()
        
        if never_synced == 0:
            print('✅ All products are already marked as synced!')
            return
        
        # Show sample products
        print('📋 Sample products to be updated:')
        samples = Product.query.filter(
            Product.is_active == True,
            Product.last_wordpress_sync == None
        ).limit(5).all()
        
        for p in samples:
            print(f'   {p.id}: {p.product_name[:50]}...')
        
        if never_synced > 5:
            print(f'   ... and {never_synced - 5} more')
        print()
        
        # Confirm
        response = input(f'Mark {never_synced} products as synced? (yes/no): ')
        if response.lower() != 'yes':
            print('❌ Cancelled')
            return
        
        # Update all products
        now = datetime.utcnow()
        products_to_update = Product.query.filter(
            Product.is_active == True,
            Product.last_wordpress_sync == None
        ).all()
        
        for product in products_to_update:
            product.last_wordpress_sync = now
        
        db.session.commit()
        
        print(f'✅ Successfully marked {len(products_to_update)} products as synced!')
        print(f'   Timestamp: {now}')
        print()
        print('🎯 Next steps:')
        print('   - Quick Sync will now only sync products you edit')
        print('   - Edit any product to trigger a re-sync')
        print('   - Use Full Sync to re-sync everything if needed')

if __name__ == '__main__':
    mark_all_synced()
