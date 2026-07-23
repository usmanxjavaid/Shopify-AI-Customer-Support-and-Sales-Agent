"""
knowledge_base/document_readers.py
-------------------------------------
Reads raw text out of PDF, DOCX, and TXT files. Knows nothing about
chunking or embeddings — just "file in, plain text out."
"""

from pathlib import Path
from pypdf import PdfReader
from docx import Document as DocxDocument

from logger import get_logger

logger = get_logger(__name__)


def read_txt(path: Path) -> str:
    """Reads a plain text file."""
    return path.read_text(encoding="utf-8")


def read_pdf(path: Path) -> str:
    """Extracts all text from a PDF file."""
    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def read_docx(path: Path) -> str:
    """Extracts all text from a DOCX file."""
    doc = DocxDocument(str(path))
    return "\n".join(para.text for para in doc.paragraphs)


# Maps file extensions to their reader function
READERS = {
    ".txt": read_txt,
    ".pdf": read_pdf,
    ".docx": read_docx,
}


def read_document(path: Path) -> str:
    """
    Reads any supported document type based on its extension.

    Args:
        path: Path to the document file.

    Returns:
        Extracted plain text.

    Raises:
        ValueError: If the file type isn't supported.
    """
    reader = READERS.get(path.suffix.lower())
    if reader is None:
        raise ValueError(f"Unsupported file type: {path.suffix}")
    return reader(path)


logger.debug("knowledge_base.document_readers loaded successfully")