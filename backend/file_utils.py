"""
File upload utilities — text extraction from various file formats.
Used by chat file sharing to extract content for agent consumption.
"""

import io
import base64
import mimetypes
from pathlib import Path
from loguru import logger


# Maximum text content to extract (chars) — prevents context overflow
MAX_EXTRACT_CHARS = 15_000


def extract_text_from_bytes(data: bytes, filename: str) -> str:
    """Extract readable text from a file's bytes based on its extension/type."""
    ext = Path(filename).suffix.lower()
    
    try:
        if ext in (".txt", ".md", ".csv", ".log", ".json", ".yaml", ".yml",
                    ".xml", ".html", ".htm", ".py", ".js", ".ts", ".tsx",
                    ".jsx", ".css", ".sql", ".sh", ".bat", ".env", ".toml",
                    ".ini", ".cfg", ".rst", ".tex"):
            return _extract_plain_text(data)

        elif ext == ".pdf":
            return _extract_pdf(data)

        elif ext in (".docx",):
            return _extract_docx(data)

        elif ext in (".doc",):
            return "[.doc files not supported — please convert to .docx or .pdf]"

        elif ext in (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg"):
            # Images can't be "read" as text, but we return a placeholder
            return ""

        else:
            # Try as plain text
            return _extract_plain_text(data)

    except Exception as e:
        logger.warning(f"Text extraction failed for {filename}: {e}")
        return f"[Could not extract text from {filename}: {e}]"


def _extract_plain_text(data: bytes) -> str:
    """Decode bytes as text with charset detection fallback."""
    try:
        return data.decode("utf-8")[:MAX_EXTRACT_CHARS]
    except UnicodeDecodeError:
        pass
    
    try:
        import chardet
        detected = chardet.detect(data)
        enc = detected.get("encoding", "utf-8") or "utf-8"
        return data.decode(enc, errors="replace")[:MAX_EXTRACT_CHARS]
    except Exception:
        return data.decode("utf-8", errors="replace")[:MAX_EXTRACT_CHARS]


def _extract_pdf(data: bytes) -> str:
    """Extract text from PDF bytes."""
    try:
        from PyPDF2 import PdfReader
        reader = PdfReader(io.BytesIO(data))
        pages = []
        total = 0
        for page in reader.pages:
            text = page.extract_text() or ""
            pages.append(text)
            total += len(text)
            if total >= MAX_EXTRACT_CHARS:
                break
        return "\n\n".join(pages)[:MAX_EXTRACT_CHARS]
    except ImportError:
        return "[PDF support requires PyPDF2 — install with: pip install PyPDF2]"


def _extract_docx(data: bytes) -> str:
    """Extract text from DOCX bytes."""
    try:
        from docx import Document
        doc = Document(io.BytesIO(data))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        return "\n\n".join(paragraphs)[:MAX_EXTRACT_CHARS]
    except ImportError:
        return "[DOCX support requires python-docx — install with: pip install python-docx]"


def is_image_file(filename: str) -> bool:
    """Check if a filename corresponds to an image."""
    ext = Path(filename).suffix.lower()
    return ext in (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg", ".ico")


def get_mime_type(filename: str) -> str:
    """Get MIME type for a filename."""
    mime, _ = mimetypes.guess_type(filename)
    return mime or "application/octet-stream"
