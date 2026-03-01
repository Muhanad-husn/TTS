"""Document parsers for PDF, DOCX, Markdown/TXT, and EPUB."""

import re
import sys
from pathlib import Path

from read_aloud import MAX_PARAGRAPH_CHARS, console


def parse_pdf(path: Path, pages: set[int] | None = None) -> list[str]:
    """Extract paragraphs from a PDF file."""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        console.print("[red]Error: PyMuPDF not installed. Run: pip install PyMuPDF[/red]")
        sys.exit(1)

    doc = fitz.open(path)
    paragraphs = []
    for page_num, page in enumerate(doc):
        if pages is not None and page_num not in pages:
            continue
        text = page.get_text()
        for para in re.split(r"\n{2,}", text):
            cleaned = " ".join(para.split())
            if cleaned:
                paragraphs.append(cleaned)
    doc.close()
    return paragraphs


def parse_docx(path: Path, pages: set[int] | None = None) -> list[str]:
    """Extract paragraphs from a DOCX file."""
    try:
        from docx import Document
    except ImportError:
        console.print("[red]Error: python-docx not installed. Run: pip install python-docx[/red]")
        sys.exit(1)

    doc = Document(str(path))
    return [p.text.strip() for p in doc.paragraphs if p.text.strip()]


def parse_markdown(path: Path, pages: set[int] | None = None) -> list[str]:
    """Extract paragraphs from a Markdown or plain text file."""
    text = path.read_text(encoding="utf-8")

    # Strip code blocks entirely
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"`[^`]+`", "", text)

    # Strip images
    text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", text)
    # Convert links to just their text
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    # Strip headings markers
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    # Strip bold/italic markers
    text = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", text)
    text = re.sub(r"_{1,3}([^_]+)_{1,3}", r"\1", text)
    # Strip list markers
    text = re.sub(r"^[\s]*[-*+]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^[\s]*\d+\.\s+", "", text, flags=re.MULTILINE)
    # Strip horizontal rules
    text = re.sub(r"^[-*_]{3,}\s*$", "", text, flags=re.MULTILINE)
    # Strip blockquote markers
    text = re.sub(r"^>\s?", "", text, flags=re.MULTILINE)

    paragraphs = []
    for para in re.split(r"\n{2,}", text):
        cleaned = " ".join(para.split())
        if cleaned:
            paragraphs.append(cleaned)
    return paragraphs


def parse_epub(path: Path, pages: set[int] | None = None) -> list[str]:
    """Extract paragraphs from an EPUB file."""
    try:
        import ebooklib
        from ebooklib import epub
    except ImportError:
        console.print("[red]Error: ebooklib not installed. Run: pip install ebooklib[/red]")
        sys.exit(1)
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        console.print("[red]Error: beautifulsoup4 not installed. Run: pip install beautifulsoup4[/red]")
        sys.exit(1)

    book = epub.read_epub(str(path), options={"ignore_ncx": True})
    paragraphs = []
    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        soup = BeautifulSoup(item.get_content(), "html.parser")
        for tag in soup.find_all(["p", "h1", "h2", "h3", "h4", "h5", "h6"]):
            text = tag.get_text(separator=" ").strip()
            if text:
                paragraphs.append(text)
    return paragraphs


PARSERS = {
    ".pdf": parse_pdf,
    ".docx": parse_docx,
    ".md": parse_markdown,
    ".markdown": parse_markdown,
    ".txt": parse_markdown,
    ".epub": parse_epub,
}


def parse_page_ranges(spec: str) -> set[int]:
    """Parse a page range spec like '1-5,8,10-12' into 0-indexed page numbers."""
    result: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            start_str, end_str = part.split("-", 1)
            start = int(start_str)
            end = int(end_str)
            if start < 1 or end < start:
                console.print(f"[red]Error: Invalid page range: {part}[/red]")
                sys.exit(1)
            result.update(range(start - 1, end))  # 1-indexed to 0-indexed
        else:
            page = int(part)
            if page < 1:
                console.print(f"[red]Error: Invalid page number: {part}[/red]")
                sys.exit(1)
            result.add(page - 1)
    return result


def split_long_paragraphs(paragraphs: list[str], max_chars: int = MAX_PARAGRAPH_CHARS) -> list[str]:
    """Split paragraphs longer than max_chars at sentence boundaries."""
    result = []
    for para in paragraphs:
        if len(para) <= max_chars:
            result.append(para)
            continue
        # Split at sentence-ending punctuation followed by a space
        sentences = re.split(r"(?<=[.!?])\s+", para)
        chunk = ""
        for sentence in sentences:
            if chunk and len(chunk) + len(sentence) + 1 > max_chars:
                result.append(chunk.strip())
                chunk = sentence
            else:
                chunk = f"{chunk} {sentence}" if chunk else sentence
        if chunk.strip():
            result.append(chunk.strip())
    return result
