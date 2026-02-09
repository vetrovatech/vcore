#!/usr/bin/env python3
"""
Import suppliers and glass catalog data from PDFs
This script extracts data from Bhoomi and P-Tuff PDFs and populates the database
"""
from app import app, db
from models import Supplier, GlassType, SupplierPricing
from datetime import date, datetime
import pdfplumber
import re

def import_suppliers():
    """Import supplier information"""
    with app.app_context():
        print("\n" + "="*60)
        print("Importing Suppliers")
        print("="*60 + "\n")
        
        # Bhoomi Tough Glass
        bhoomi = Supplier.query.filter_by(name="Bhoomi Tough Glass LLP").first()
        if not bhoomi:
            bhoomi = Supplier(
                name="Bhoomi Tough Glass LLP",
                contact_person="Rebecca",
                phone="",
                email="bhoomitough150117@gmail.com",
                address="No. 42/1, Kumbaranahalli Village, Kasaba Hobli, Haragadde Post, Anekal Taluk",
                city="Bangalore",
                state="Karnataka",
                pincode="562106",
                gstin="29AARFB6370R1ZE",
                pan="AARFB6370R",
                bank_name="AXIS BANK",
                account_number="924030002482035",
                ifsc_code="UTIB0002629",
                branch="ANEKAL",
                payment_terms="For Confirmation the order need to give 100% of Quotation Value",
                lead_time_days=5,
                is_active=True
            )
            db.session.add(bhoomi)
            print(f"✅ Added supplier: {bhoomi.name}")
        else:
            print(f"ℹ️  Supplier already exists: {bhoomi.name}")
        
        # P-Tuff Safety Glass
        ptuff = Supplier.query.filter_by(name="P-Tuff Safety Glass Pvt Ltd").first()
        if not ptuff:
            ptuff = Supplier(
                name="P-Tuff Safety Glass Pvt Ltd",
                contact_person="Muthuragavan M / Manish G",
                phone="9448217116, 9384817496, 9384817495",
                email="ptuffsafetyglass@gmail.com",
                address="S.No. 86/2, 87/2, Komaranapalli Village, Near Duroflex Puff Factory, Hosur To Anekal Road Cross",
                city="Hosur",
                state="Tamil Nadu",
                pincode="635114",
                gstin="33AAOCP0201B1Z7",
                is_active=True
            )
            db.session.add(ptuff)
            print(f"✅ Added supplier: {ptuff.name}")
        else:
            print(f"ℹ️  Supplier already exists: {ptuff.name}")
        
        db.session.commit()
        print(f"\n✅ Suppliers imported successfully!")
        return bhoomi, ptuff

def import_glass_types_and_pricing():
    """Import glass types and pricing from PDFs"""
    with app.app_context():
        print("\n" + "="*60)
        print("Importing Glass Types and Pricing")
        print("="*60 + "\n")
        
        # Get suppliers
        bhoomi = Supplier.query.filter_by(name="Bhoomi Tough Glass LLP").first()
        ptuff = Supplier.query.filter_by(name="P-Tuff Safety Glass Pvt Ltd").first()
        
        if not bhoomi or not ptuff:
            print("❌ Error: Suppliers not found. Please run import_suppliers() first.")
            return
        
        # Define glass types based on PDF analysis
        glass_types_data = [
            {
                "name": "6mm Toughened Glass",
                "category": "Toughened",
                "thickness_mm": 6.0,
                "description": "6mm clear toughened safety glass",
                "bhoomi_rate": 762.00,
                "ptuff_rate": 800.00,
                "bhoomi_hole": 300.00,
                "ptuff_hole": 0.00,
                "bhoomi_cutout": 100.00,
                "ptuff_cutout": 0.00
            },
            {
                "name": "8mm Toughened Glass",
                "category": "Toughened",
                "thickness_mm": 8.0,
                "description": "8mm clear toughened safety glass",
                "bhoomi_rate": 1016.00,
                "ptuff_rate": 0.00,  # Not in P-Tuff PDF
                "bhoomi_hole": 300.00,
                "bhoomi_cutout": 100.00
            },
            {
                "name": "6mm + 1.52 PVB + 6mm Laminated Glass",
                "category": "Laminated",
                "thickness_mm": 13.52,
                "description": "6mm toughened glass + 1.52mm PVB interlayer + 6mm toughened glass",
                "bhoomi_rate": 2900.00,
                "ptuff_rate": 2800.00,
                "bhoomi_hole": 300.00,
                "ptuff_hole": 0.00,
                "bhoomi_cutout": 100.00,
                "ptuff_cutout": 0.00
            },
            {
                "name": "6mm Toughened Glass with Full Frosting",
                "category": "Toughened",
                "thickness_mm": 6.0,
                "description": "6mm clear toughened glass with full frosting",
                "is_frosted": True,
                "ptuff_rate": 800.00,
                "ptuff_hole": 0.00,
                "ptuff_cutout": 0.00
            }
        ]
        
        for gt_data in glass_types_data:
            # Check if glass type exists
            glass_type = GlassType.query.filter_by(name=gt_data["name"]).first()
            
            if not glass_type:
                glass_type = GlassType(
                    name=gt_data["name"],
                    category=gt_data["category"],
                    thickness_mm=gt_data["thickness_mm"],
                    description=gt_data.get("description"),
                    is_frosted=gt_data.get("is_frosted", False),
                    is_active=True
                )
                db.session.add(glass_type)
                db.session.flush()  # Get the ID
                print(f"✅ Added glass type: {glass_type.name}")
            else:
                print(f"ℹ️  Glass type already exists: {glass_type.name}")
            
            # Add Bhoomi pricing if available
            if gt_data.get("bhoomi_rate"):
                bhoomi_pricing = SupplierPricing.query.filter_by(
                    supplier_id=bhoomi.id,
                    glass_type_id=glass_type.id
                ).first()
                
                if not bhoomi_pricing:
                    bhoomi_pricing = SupplierPricing(
                        supplier_id=bhoomi.id,
                        glass_type_id=glass_type.id,
                        rate_per_sqm=gt_data["bhoomi_rate"],
                        hole_price=gt_data.get("bhoomi_hole", 0),
                        cutout_price=gt_data.get("bhoomi_cutout", 0),
                        effective_from=date.today(),
                        is_active=True
                    )
                    db.session.add(bhoomi_pricing)
                    print(f"  ✅ Added Bhoomi pricing: ₹{gt_data['bhoomi_rate']}/sqm")
            
            # Add P-Tuff pricing if available
            if gt_data.get("ptuff_rate"):
                ptuff_pricing = SupplierPricing.query.filter_by(
                    supplier_id=ptuff.id,
                    glass_type_id=glass_type.id
                ).first()
                
                if not ptuff_pricing:
                    ptuff_pricing = SupplierPricing(
                        supplier_id=ptuff.id,
                        glass_type_id=glass_type.id,
                        rate_per_sqm=gt_data["ptuff_rate"],
                        hole_price=gt_data.get("ptuff_hole", 0),
                        cutout_price=gt_data.get("ptuff_cutout", 0),
                        big_hole_price=gt_data.get("ptuff_big_hole", 0),
                        big_cutout_price=gt_data.get("ptuff_big_cutout", 0),
                        effective_from=date.today(),
                        is_active=True
                    )
                    db.session.add(ptuff_pricing)
                    print(f"  ✅ Added P-Tuff pricing: ₹{gt_data['ptuff_rate']}/sqm")
        
        db.session.commit()
        print(f"\n✅ Glass types and pricing imported successfully!")

def main():
    """Main import function"""
    print("\n" + "="*60)
    print("SUPPLIER AND GLASS CATALOG DATA IMPORT")
    print("="*60)
    
    # Import suppliers
    bhoomi, ptuff = import_suppliers()
    
    # Import glass types and pricing
    import_glass_types_and_pricing()
    
    # Summary
    with app.app_context():
        supplier_count = Supplier.query.count()
        glass_type_count = GlassType.query.count()
        pricing_count = SupplierPricing.query.count()
        
        print("\n" + "="*60)
        print("IMPORT SUMMARY")
        print("="*60)
        print(f"Suppliers: {supplier_count}")
        print(f"Glass Types: {glass_type_count}")
        print(f"Pricing Records: {pricing_count}")
        print("="*60 + "\n")

if __name__ == '__main__':
    main()
