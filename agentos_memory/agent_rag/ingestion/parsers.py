# src/ingestion/parsers.py
from typing import List, Dict, Any

def parse_document_structure(source_uri: str, mime_type: str = None) -> List[Dict[str, Any]]:
    """
    Mock parser representing unstructured.io or LlamaParse.
    In a real system, this identifies Headings, Paragraphs, Tables, and Code Blocks.
    """
    # Placeholder return simulating a parsed document structure.
    return [
        {"type": "Title", "text": "Acme Corp Parental Leave Policy"},
        {"type": "Heading", "text": "1. Overview"},
        {"type": "Paragraph", "text": "This document outlines the parental leave policy for Acme Corp employees in California."},
        {"type": "Heading", "text": "2. Eligibility"},
        {"type": "Paragraph", "text": "Full-time employees are eligible after 90 days. Contractors are not eligible."},
        {"type": "Table", "text": "| Region | Max Weeks | Paid | \n | CA | 12 | Yes |"}
    ]
