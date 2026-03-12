"""Legacy compatibility wrapper.

The repo no longer keeps the OCR-derived ``39632e.txt`` intermediate.  The
authoritative source is ``39632e.pdf``; regenerate the Markdown companion
directly from that PDF.
"""

from convert_pdf_to_md_pymupdf import convert_pdf_to_md


if __name__ == "__main__":
    convert_pdf_to_md("39632e.pdf", "39632e.md")
    print("Conversion complete from PDF.")
