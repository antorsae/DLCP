import pymupdf4llm
import sys

def convert_pdf_to_md(pdf_path, md_path):
    print(f"Converting {pdf_path} to {md_path} using pymupdf4llm...")
    md_text = pymupdf4llm.to_markdown(pdf_path)
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(md_text)
    print("Conversion complete.")

if __name__ == "__main__":
    convert_pdf_to_md("39632e.pdf", "39632e.md")
