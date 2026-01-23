"""
Generate Bill of Materials (BOM) template for glass products
"""
import csv
import pymysql
import os
from dotenv import load_dotenv

load_dotenv()

def parse_database_url(url):
    """Parse MySQL database URL"""
    url = url.replace('mysql+pymysql://', '')
    auth, rest = url.split('@')
    user, password = auth.split(':')
    host_port, database = rest.split('/')
    host, port = host_port.split(':')
    return {
        'host': host,
        'user': user,
        'password': password,
        'database': database,
        'port': int(port)
    }

# BOM templates for different product types
BOM_TEMPLATES = {
    'DGU/Insulated Glass': [
        {'component': 'Toughened Glass (Outer)', 'unit': 'sqft', 'quantity': 1.0, 'cost_per_unit': 0, 'notes': 'Outer pane'},
        {'component': 'Toughened Glass (Inner)', 'unit': 'sqft', 'quantity': 1.0, 'cost_per_unit': 0, 'notes': 'Inner pane'},
        {'component': 'Aluminum Spacer', 'unit': 'ft', 'quantity': 0, 'cost_per_unit': 0, 'notes': 'Perimeter length'},
        {'component': 'Desiccant', 'unit': 'gm', 'quantity': 0, 'cost_per_unit': 0, 'notes': 'Moisture absorber'},
        {'component': 'Primary Sealant (Butyl)', 'unit': 'ft', 'quantity': 0, 'cost_per_unit': 0, 'notes': 'Inner seal'},
        {'component': 'Secondary Sealant (Silicone)', 'unit': 'ft', 'quantity': 0, 'cost_per_unit': 0, 'notes': 'Outer seal'},
        {'component': 'Inert Gas (Argon)', 'unit': 'sqft', 'quantity': 1.0, 'cost_per_unit': 0, 'notes': 'Gas filling'},
        {'component': 'Labor - Assembly', 'unit': 'hrs', 'quantity': 0, 'cost_per_unit': 0, 'notes': 'Assembly time'},
        {'component': 'Electricity', 'unit': 'unit', 'quantity': 1.0, 'cost_per_unit': 0, 'notes': 'Processing'},
    ],
    'Laminated Glass': [
        {'component': 'Toughened Glass (Top)', 'unit': 'sqft', 'quantity': 1.0, 'cost_per_unit': 0, 'notes': 'Top layer'},
        {'component': 'Toughened Glass (Bottom)', 'unit': 'sqft', 'quantity': 1.0, 'cost_per_unit': 0, 'notes': 'Bottom layer'},
        {'component': 'PVB Interlayer', 'unit': 'sqft', 'quantity': 1.0, 'cost_per_unit': 0, 'notes': 'Lamination film'},
        {'component': 'Labor - Lamination', 'unit': 'hrs', 'quantity': 0, 'cost_per_unit': 0, 'notes': 'Processing time'},
        {'component': 'Electricity - Autoclave', 'unit': 'unit', 'quantity': 1.0, 'cost_per_unit': 0, 'notes': 'Autoclave processing'},
    ],
    'Toughened Glass': [
        {'component': 'Float Glass', 'unit': 'sqft', 'quantity': 1.0, 'cost_per_unit': 0, 'notes': 'Raw glass'},
        {'component': 'Labor - Cutting', 'unit': 'hrs', 'quantity': 0, 'cost_per_unit': 0, 'notes': 'Cutting time'},
        {'component': 'Labor - Edging', 'unit': 'hrs', 'quantity': 0, 'cost_per_unit': 0, 'notes': 'Edge polishing'},
        {'component': 'Electricity - Tempering', 'unit': 'unit', 'quantity': 1.0, 'cost_per_unit': 0, 'notes': 'Furnace processing'},
    ],
    'Shower Enclosure': [
        {'component': 'Toughened Glass', 'unit': 'sqft', 'quantity': 0, 'cost_per_unit': 0, 'notes': 'Glass panels'},
        {'component': 'Aluminum Profile', 'unit': 'ft', 'quantity': 0, 'cost_per_unit': 0, 'notes': 'Frame'},
        {'component': 'Hinges (SS304)', 'unit': 'pcs', 'quantity': 0, 'cost_per_unit': 0, 'notes': 'Door hinges'},
        {'component': 'Handle', 'unit': 'pcs', 'quantity': 1, 'cost_per_unit': 0, 'notes': 'Door handle'},
        {'component': 'Rubber Gasket', 'unit': 'ft', 'quantity': 0, 'cost_per_unit': 0, 'notes': 'Sealing'},
        {'component': 'Silicone Sealant', 'unit': 'tube', 'quantity': 1, 'cost_per_unit': 0, 'notes': 'Installation'},
        {'component': 'Labor - Fabrication', 'unit': 'hrs', 'quantity': 0, 'cost_per_unit': 0, 'notes': 'Assembly'},
        {'component': 'Labor - Installation', 'unit': 'hrs', 'quantity': 0, 'cost_per_unit': 0, 'notes': 'On-site installation'},
    ],
    'Glass Partition': [
        {'component': 'Toughened Glass', 'unit': 'sqft', 'quantity': 0, 'cost_per_unit': 0, 'notes': 'Glass panels'},
        {'component': 'Aluminum U-Channel (Top)', 'unit': 'ft', 'quantity': 0, 'cost_per_unit': 0, 'notes': 'Top track'},
        {'component': 'Aluminum U-Channel (Bottom)', 'unit': 'ft', 'quantity': 0, 'cost_per_unit': 0, 'notes': 'Bottom track'},
        {'component': 'Rubber Gasket', 'unit': 'ft', 'quantity': 0, 'cost_per_unit': 0, 'notes': 'Glass support'},
        {'component': 'Patch Fittings', 'unit': 'set', 'quantity': 0, 'cost_per_unit': 0, 'notes': 'If frameless'},
        {'component': 'Silicone Sealant', 'unit': 'tube', 'quantity': 1, 'cost_per_unit': 0, 'notes': 'Installation'},
        {'component': 'Labor - Installation', 'unit': 'hrs', 'quantity': 0, 'cost_per_unit': 0, 'notes': 'On-site work'},
    ],
    'Etched/Frosted Glass': [
        {'component': 'Float Glass', 'unit': 'sqft', 'quantity': 1.0, 'cost_per_unit': 0, 'notes': 'Raw glass'},
        {'component': 'Acid/Sandblasting Material', 'unit': 'sqft', 'quantity': 1.0, 'cost_per_unit': 0, 'notes': 'Processing material'},
        {'component': 'Labor - Etching', 'unit': 'hrs', 'quantity': 0, 'cost_per_unit': 0, 'notes': 'Processing time'},
        {'component': 'Electricity - Tempering', 'unit': 'unit', 'quantity': 1.0, 'cost_per_unit': 0, 'notes': 'If toughened'},
    ],
    'Mirror Glass': [
        {'component': 'Float Glass', 'unit': 'sqft', 'quantity': 1.0, 'cost_per_unit': 0, 'notes': 'Raw glass'},
        {'component': 'Silver Coating', 'unit': 'sqft', 'quantity': 1.0, 'cost_per_unit': 0, 'notes': 'Reflective coating'},
        {'component': 'Protective Paint', 'unit': 'sqft', 'quantity': 1.0, 'cost_per_unit': 0, 'notes': 'Back coating'},
        {'component': 'Labor - Processing', 'unit': 'hrs', 'quantity': 0, 'cost_per_unit': 0, 'notes': 'Coating time'},
    ],
}

def get_product_category_mapping(category):
    """Map product category to BOM template"""
    category_lower = category.lower()
    
    if 'insulated' in category_lower or 'dgu' in category_lower or 'sound proof' in category_lower:
        return 'DGU/Insulated Glass'
    elif 'laminated' in category_lower or 'laminate' in category_lower:
        return 'Laminated Glass'
    elif 'shower' in category_lower or 'enclosure' in category_lower:
        return 'Shower Enclosure'
    elif 'partition' in category_lower:
        return 'Glass Partition'
    elif 'etched' in category_lower or 'frosted' in category_lower or 'sandblast' in category_lower:
        return 'Etched/Frosted Glass'
    elif 'mirror' in category_lower:
        return 'Mirror Glass'
    elif 'toughened' in category_lower or 'tempered' in category_lower or 'transparent' in category_lower:
        return 'Toughened Glass'
    else:
        return 'Toughened Glass'  # Default

def main():
    # Get database connection
    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        print("❌ DATABASE_URL not found in .env file")
        return
    
    db_config = parse_database_url(db_url)
    connection = pymysql.connect(**db_config)
    
    try:
        with connection.cursor() as cursor:
            # Get all active products
            cursor.execute("""
                SELECT id, product_name, category 
                FROM products 
                WHERE is_active = 1 
                ORDER BY category, product_name
            """)
            products = cursor.fetchall()
            
            # Create BOM CSV
            csv_filename = 'product_bom_template.csv'
            
            with open(csv_filename, 'w', newline='', encoding='utf-8') as csvfile:
                fieldnames = [
                    'product_id', 'product_name', 'category', 'bom_type',
                    'component_name', 'unit', 'quantity_per_unit', 
                    'cost_per_unit', 'notes'
                ]
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                
                for product_id, product_name, category in products:
                    # Get BOM template for this category
                    bom_type = get_product_category_mapping(category)
                    bom_items = BOM_TEMPLATES.get(bom_type, BOM_TEMPLATES['Toughened Glass'])
                    
                    # Write BOM items for this product
                    for item in bom_items:
                        writer.writerow({
                            'product_id': product_id,
                            'product_name': product_name,
                            'category': category,
                            'bom_type': bom_type,
                            'component_name': item['component'],
                            'unit': item['unit'],
                            'quantity_per_unit': item['quantity'],
                            'cost_per_unit': item['cost_per_unit'],
                            'notes': item['notes']
                        })
                
                print(f"✅ Created BOM template: {csv_filename}")
                print(f"   Total products: {len(products)}")
                print(f"\n📝 Next steps:")
                print(f"   1. Open {csv_filename}")
                print(f"   2. Fill in the quantity_per_unit and cost_per_unit columns")
                print(f"   3. Adjust components as needed for each product")
                print(f"   4. Use this for cost estimation and production planning")
                
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        connection.close()

if __name__ == "__main__":
    main()
