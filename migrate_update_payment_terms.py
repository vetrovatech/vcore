#!/usr/bin/env python3
"""
Migration script to update payment terms for all existing quotes
"""
import sys
import os

# Add parent directory to path to import models
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from models import db, Quote
from app import app

# New default payment terms
NEW_PAYMENT_TERMS = """Payment & Commercial Terms

•  Payment by crossed cheque only in favour of Vetrova Tech Services Private Limited.
•  50% advance on order confirmation; balance 50% at delivery.
•  Delivery: Minimum 8 working days from confirmation and advance receipt.
•  Transport: Material dispatched at customer's risk; insurance, if any, on customer's behalf—claims subject to insurer settlement only.
•  Quality Claims: Must be reported in writing within 3 working days of delivery.
•  Cancellation: No cancellation or alteration of confirmed toughened glass orders.
•  Disputes: Arbitration applicable."""

def update_payment_terms():
    """Update payment terms for all existing quotes"""
    with app.app_context():
        try:
            # Get all quotes
            quotes = Quote.query.all()
            total_quotes = len(quotes)
            updated_count = 0
            
            print(f"Found {total_quotes} quotes to update...")
            
            for quote in quotes:
                # Update payment terms
                quote.payment_terms = NEW_PAYMENT_TERMS
                updated_count += 1
                
                if updated_count % 10 == 0:
                    print(f"Updated {updated_count}/{total_quotes} quotes...")
            
            # Commit all changes
            db.session.commit()
            print(f"\n✅ Successfully updated payment terms for {updated_count} quotes!")
            
        except Exception as e:
            db.session.rollback()
            print(f"\n❌ Error updating payment terms: {str(e)}")
            raise

if __name__ == "__main__":
    print("=" * 60)
    print("Payment Terms Update Migration")
    print("=" * 60)
    print("\nThis will update payment terms for ALL existing quotes.")
    print("New payment terms:")
    print(NEW_PAYMENT_TERMS)
    print("\n" + "=" * 60)
    
    response = input("\nDo you want to proceed? (yes/no): ")
    if response.lower() in ['yes', 'y']:
        update_payment_terms()
    else:
        print("Migration cancelled.")
