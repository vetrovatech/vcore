#!/usr/bin/env python3
"""
Extract detailed item and pricing data from supplier PDFs
"""
import pdfplumber
import json
import re

def extract_bhoomi_data(pdf_path):
    """Extract items and pricing from Bhoomi PDF"""
    print(f"\n{'='*60}")
    print(f"Extracting Bhoomi data from: {pdf_path}")
    print(f"{'='*60}\n")
    
    items = []
    
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            
            for table in tables:
                for row in table:
                    # Skip header rows and empty rows
                    if not row or len(row) < 5:
                        continue
                    
                    # Print row for analysis
                    print(f"Row: {row}")
    
    return items

def extract_ptuff_data(pdf_path):
    """Extract items and pricing from P-Tuff PDF"""
    print(f"\n{'='*60}")
    print(f"Extracting P-Tuff data from: {pdf_path}")
    print(f"{'='*60}\n")
    
    items = []
    
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, 1):
            print(f"\n--- Page {page_num} ---")
            tables = page.extract_tables()
            
            for table_num, table in enumerate(tables, 1):
                print(f"\nTable {table_num} (rows: {len(table)}):")
                for i, row in enumerate(table[:10]):  # First 10 rows
                    print(f"  Row {i}: {row}")
    
    return items

if __name__ == "__main__":
    bhoomi_items = extract_bhoomi_data("suppliers/bhoomi.pdf")
    ptuff_items = extract_ptuff_data("suppliers/ptuff.pdf")
    
    print(f"\n\nSummary:")
    print(f"Bhoomi items: {len(bhoomi_items)}")
    print(f"P-Tuff items: {len(ptuff_items)}")
