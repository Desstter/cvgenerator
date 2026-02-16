import fitz
import pymupdf4llm
from pathlib import Path


def extract_as_markdown(pdf_path: str | Path) -> str:
    """Extract PDF content as structured markdown using pymupdf4llm."""
    md_text = pymupdf4llm.to_markdown(str(pdf_path))
    return md_text


def extract_detailed(pdf_path: str | Path) -> list[dict]:
    """Extract text with positional and font metadata for in-place editing."""
    doc = fitz.open(str(pdf_path))
    pages = []
    for page_num, page in enumerate(doc):
        blocks = []
        text_dict = page.get_text("dict")
        for block in text_dict.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    blocks.append({
                        "text": span["text"],
                        "bbox": span["bbox"],
                        "font": span["font"],
                        "size": span["size"],
                        "color": span["color"],
                        "page": page_num,
                    })
        pages.append({
            "page_num": page_num,
            "width": page.rect.width,
            "height": page.rect.height,
            "blocks": blocks,
        })
    doc.close()
    return pages
