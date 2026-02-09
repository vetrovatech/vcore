#!/usr/bin/env python3
"""
Analyze supplier PDFs to extract structure and data
"""
import pdfplumber
import json

def analyze_pdf(pdf_path):
    """Analyze a PDF and extract text and table structure"""
    print(f"\n{'='*60}")
    print(f"Analyzing: {pdf_path}")
    print(f"{'='*60}\n")
    
    with pdfplumber.open(pdf_path) as pdf:
        print(f"Total pages: {len(pdf.pages)}\n")
        
        for page_num, page in enumerate(pdf.pages, 1):
            print(f"\n--- Page {page_num} ---")
            
            # Extract text
            text = page.extract_text()
            if text:
                print("Text content (first 500 chars):")
                print(text[:500])
                print("...")
            
            # Extract tables
            tables = page.extract_tables()
            if tables:
                print(f"\nFound {len(tables)} table(s)")
                for i, table in enumerate(tables, 1):
                    print(f"\nTable {i}:")
                    print(f"  Rows: {len(table)}")
                    print(f"  Columns: {len(table[0]) if table else 0}")
                    if table:
                        print(f"  Header: {table[0]}")
                        if len(table) > 1:
                            print(f"  Sample row: {table[1]}")
            
            # Only analyze first 2 pages for now
            if page_num >= 2:
                print(f"\n... (showing first 2 pages only)")
                break

if __name__ == "__main__":
    # Analyze both supplier PDFs
    analyze_pdf("suppliers/bhoomi.pdf")
    analyze_pdf("suppliers/ptuff.pdf")
