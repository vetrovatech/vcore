"""
Generate SEO-friendly product descriptions for glassy.in products
Creates a CSV file with product_id, current_description, and new_description
"""
import csv
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine

load_dotenv()

def generate_seo_description(product_name, category):
    """
    Generate SEO-friendly description (max 50 chars)
    Focus on: material, use case, key feature
    """
    name_lower = product_name.lower()
    
    # Extract key features from product name
    features = []
    
    # Glass types
    if 'toughened' in name_lower or 'tempered' in name_lower:
        features.append('Toughened')
    if 'laminated' in name_lower:
        features.append('Laminated')
    if 'frosted' in name_lower or 'etched' in name_lower:
        features.append('Frosted')
    if 'clear' in name_lower:
        features.append('Clear')
    if 'fluted' in name_lower:
        features.append('Fluted')
    if 'acid' in name_lower:
        features.append('Acid Etched')
    if 'sandblasted' in name_lower:
        features.append('Sandblasted')
    
    # Applications
    if 'shower' in name_lower or 'bathroom' in name_lower:
        application = 'Shower'
    elif 'door' in name_lower:
        application = 'Door'
    elif 'window' in name_lower:
        application = 'Window'
    elif 'partition' in name_lower or 'divider' in name_lower:
        application = 'Partition'
    elif 'railing' in name_lower or 'balcony' in name_lower:
        application = 'Railing'
    elif 'table' in name_lower:
        application = 'Table'
    elif 'cabinet' in name_lower:
        application = 'Cabinet'
    else:
        application = category.split()[0] if category else 'Glass'
    
    # Thickness
    thickness = None
    for word in product_name.split():
        if 'mm' in word.lower():
            thickness = word
            break
    
    # Build description (max 50 chars)
    parts = []
    
    if features:
        parts.append(features[0])
    
    parts.append('Glass')
    
    if application and application not in parts:
        parts.append(application)
    
    if thickness:
        parts.append(thickness)
    
    description = ' '.join(parts)
    
    # Ensure it's under 50 characters
    if len(description) > 50:
        # Try shorter version
        if thickness:
            description = f"{features[0] if features else ''} Glass {thickness}".strip()
        else:
            description = f"{features[0] if features else ''} {application} Glass".strip()
    
    # Final fallback
    if len(description) > 50:
        description = description[:47] + '...'
    
    return description

def main():
    # Get database connection details
    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        print("❌ DATABASE_URL not found in .env file")
        return
    
    print("🔗 Connecting to database...")
    connection = create_engine(db_url).raw_connection()
    
    try:
        with connection.cursor() as cursor:
            # Fetch all products
            query = """
                SELECT id, product_name, category, description
                FROM products
                WHERE is_active = 1
                ORDER BY category, product_name
            """
            cursor.execute(query)
            products = cursor.fetchall()
            
            print(f"📦 Found {len(products)} active products")
            
            # Generate CSV
            csv_filename = 'product_descriptions_update.csv'
            
            with open(csv_filename, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                
                # Header
                writer.writerow(['product_id', 'product_name', 'category', 'current_description', 'new_description', 'description_length'])
                
                # Data
                for product in products:
                    product_id, product_name, category, current_desc = product
                    
                    # Generate new SEO-friendly description
                    new_desc = generate_seo_description(product_name, category)
                    
                    writer.writerow([
                        product_id,
                        product_name,
                        category,
                        current_desc or '',
                        new_desc,
                        len(new_desc)
                    ])
                    
                    print(f"   ✅ {product_id}: {product_name[:40]}... -> {new_desc}")
            
            print(f"\n✅ CSV file created: {csv_filename}")
            print(f"\n📋 To import, use:")
            print(f"   python3 import_product_descriptions.py")
            
    finally:
        connection.close()

if __name__ == "__main__":
    main()
