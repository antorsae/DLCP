from docling.document_converter import DocumentConverter

def convert_pdf_to_md(pdf_path, md_path):
    print(f"Converting {pdf_path} to {md_path} using Docling...")
    converter = DocumentConverter()
    result = converter.convert(pdf_path)
    md_text = result.document.export_to_markdown()
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(md_text)
    print("Conversion complete.")

if __name__ == "__main__":
    convert_pdf_to_md("40001303h.pdf", "40001303h_docling.md")