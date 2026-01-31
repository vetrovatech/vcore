"""
PDF Generator for Quotes
Uses WeasyPrint to convert HTML templates to PDF
"""

from weasyprint import HTML, CSS
from flask import render_template
import os


def generate_quote_pdf(quote):
    """
    Generate PDF for a quote
    
    Args:
        quote: Quote model instance
        
    Returns:
        bytes: PDF file content
    """
    # Render HTML template
    html_content = render_template('quotes/pdf_template.html', quote=quote)
    
    # Convert HTML to PDF
    pdf = HTML(string=html_content).write_pdf()
    
    return pdf
