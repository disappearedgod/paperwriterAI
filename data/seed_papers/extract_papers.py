#!/usr/bin/env python3
"""Extract text from seed papers for analysis"""

import pdfplumber
import os
import json

PAPERS_DIR = os.path.dirname(os.path.abspath(__file__))
papers = [
    ("2311.10723_LLM_in_Finance_Survey.pdf", "2311.10723_summary.json"),
    ("2408.06361_LLM_Agent_Financial_Trading_Survey.pdf", "2408.06361_summary.json"),
    ("2412.20138_TradingAgents.pdf", "2412.20138_summary.json"),
    ("2509.09995_QuantAgent.pdf", "2509.09995_summary.json"),
    ("2510.05533_New_Quant_Survey.pdf", "2510.05533_summary.json"),
]

def extract_pdf_text(pdf_path, max_pages=15):
    """Extract text from first N pages of PDF"""
    texts = []
    with pdfplumber.open(pdf_path) as pdf:
        total_pages = len(pdf.pages)
        print(f"  Total pages: {total_pages}")
        # Extract first N pages (abstract, intro, and main sections)
        pages_to_read = min(max_pages, total_pages)
        for i, page in enumerate(pdf.pages[:pages_to_read]):
            text = page.extract_text()
            if text:
                texts.append(f"--- Page {i+1} ---\n{text}")
    return "\n\n".join(texts), total_pages

def extract_paper_info(pdf_path):
    """Extract key info from paper"""
    with pdfplumber.open(pdf_path) as pdf:
        # Get first page for title/abstract
        first_page_text = pdf.pages[0].extract_text() if pdf.pages else ""
        # Get second page too for better abstract
        second_page_text = pdf.pages[1].extract_text() if len(pdf.pages) > 1 else ""

        return {
            "first_page": first_page_text[:2000],
            "second_page": second_page_text[:1500],
            "total_pages": len(pdf.pages)
        }

results = []
for pdf_file, summary_file in papers:
    pdf_path = os.path.join(PAPERS_DIR, pdf_file)
    summary_path = os.path.join(PAPERS_DIR, summary_file)

    if os.path.exists(pdf_path):
        print(f"\nProcessing: {pdf_file}")
        try:
            info = extract_paper_info(pdf_path)
            result = {
                "paper": pdf_file,
                "total_pages": info["total_pages"],
                "first_page_preview": info["first_page"],
                "second_page_preview": info["second_page"]
            }
            results.append(result)

            # Save individual summary
            with open(summary_path, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            print(f"  Saved to {summary_file}")
        except Exception as e:
            print(f"  Error: {e}")
    else:
        print(f"  Not found: {pdf_path}")

# Save combined results
combined_path = os.path.join(PAPERS_DIR, "combined_summaries.json")
with open(combined_path, 'w', encoding='utf-8') as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print(f"\n\nAll summaries saved to: {combined_path}")
