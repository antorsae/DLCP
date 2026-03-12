"""Legacy entry point kept for compatibility.

The old OCR-derived ``39632e.txt`` companion has been retired.  Use the PDF as
ground truth and regenerate ``39632e.md`` directly from ``39632e.pdf``.
"""

from convert_pdf_to_md_pymupdf import convert_pdf_to_md


if __name__ == "__main__":
    convert_pdf_to_md("39632e.pdf", "39632e.md")
