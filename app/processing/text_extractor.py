"""
Text extraction from various document formats.

Priority:
1. PDF — try text layer (PyMuPDF) first, OCR (pytesseract) only if page is blank
2. .docx — python-docx
3. .msg  — extract-msg
4. .eml  — email.parser
5. Images — pytesseract

Returns (text: str, method: str) where method is "text_layer", "ocr", or "parser".
All extraction is logged per document via app.database.
"""
import io
import logging
import os
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# ---- lazy imports so missing packages don't crash the app on startup ----

def _fitz():
    try:
        import fitz
        return fitz
    except ImportError:
        return None

def _pytesseract():
    try:
        import pytesseract
        return pytesseract
    except ImportError:
        return None

def _pil_image():
    try:
        from PIL import Image
        return Image
    except ImportError:
        return None


def extract_text_from_file(file_path: str) -> tuple[str, str]:
    """
    Main entry point. Dispatches to the appropriate extractor.
    Returns (text, method).
    """
    path = Path(file_path)
    ext = path.suffix.lower()

    if ext == ".pdf":
        return _extract_pdf(str(path))
    elif ext == ".docx":
        return _extract_docx(str(path))
    elif ext == ".msg":
        return _extract_msg(str(path))
    elif ext == ".eml":
        return _extract_eml(str(path))
    elif ext in (".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".gif", ".webp"):
        return _extract_image(str(path))
    else:
        log.warning("Unsupported file type: %s", ext)
        return "", "unsupported"


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------

def _extract_pdf(file_path: str) -> tuple[str, str]:
    """
    Try PyMuPDF text layer first.
    Fall back to OCR page-by-page if text layer is blank/sparse.
    """
    fitz = _fitz()
    if fitz is None:
        log.warning("PyMuPDF not available; trying OCR directly")
        return _ocr_pdf_fallback(file_path)

    try:
        doc = fitz.open(file_path)
    except Exception as e:
        log.error("Failed to open PDF %s: %s", file_path, e)
        return "", "error"

    all_text = []
    ocr_pages = []
    text_pages = []

    for page_num in range(len(doc)):
        page = doc[page_num]
        text = page.get_text("text").strip()
        if text:
            all_text.append(text)
            text_pages.append(page_num)
        else:
            # Try OCR for this page
            ocr_text = _ocr_page(page)
            if ocr_text:
                all_text.append(ocr_text)
            ocr_pages.append(page_num)

    doc.close()

    full_text = "\n\n".join(all_text)

    if ocr_pages and text_pages:
        method = "mixed"
    elif ocr_pages:
        method = "ocr"
    else:
        method = "text_layer"

    _log_extraction(file_path, method, len(all_text), len(ocr_pages))
    return full_text, method


def _ocr_page(page) -> str:
    """OCR a single PyMuPDF page. Returns empty string if pytesseract unavailable."""
    pytesseract = _pytesseract()
    Image = _pil_image()
    if not pytesseract or not Image:
        return ""
    try:
        pix = page.get_pixmap(dpi=300)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        return pytesseract.image_to_string(img).strip()
    except Exception as e:
        log.warning("OCR failed for page: %s", e)
        return ""


def _ocr_pdf_fallback(file_path: str) -> tuple[str, str]:
    """OCR an entire PDF when PyMuPDF is unavailable (uses PIL + pytesseract)."""
    pytesseract = _pytesseract()
    Image = _pil_image()
    if not pytesseract or not Image:
        return "", "ocr_unavailable"
    try:
        from PIL import Image as PILImage
        import fitz  # will raise if not installed
        doc = fitz.open(file_path)
        texts = []
        for page in doc:
            pix = page.get_pixmap(dpi=300)
            img = PILImage.frombytes("RGB", [pix.width, pix.height], pix.samples)
            texts.append(pytesseract.image_to_string(img))
        doc.close()
        return "\n\n".join(texts), "ocr"
    except Exception as e:
        return "", "error"


# ---------------------------------------------------------------------------
# DOCX
# ---------------------------------------------------------------------------

def _extract_docx(file_path: str) -> tuple[str, str]:
    try:
        from docx import Document
        doc = Document(file_path)
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        # Also extract tables
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    if cell.text.strip():
                        paragraphs.append(cell.text.strip())
        _log_extraction(file_path, "parser", len(paragraphs), 0)
        return "\n".join(paragraphs), "parser"
    except ImportError:
        log.warning("python-docx not installed; cannot parse .docx files")
        return "", "unavailable"
    except Exception as e:
        log.error("DOCX extraction error for %s: %s", file_path, e)
        return "", "error"


# ---------------------------------------------------------------------------
# MSG (Outlook message format)
# ---------------------------------------------------------------------------

def _extract_msg(file_path: str) -> tuple[str, str]:
    try:
        import extract_msg
        msg = extract_msg.Message(file_path)
        body = msg.body or ""
        html_body = msg.htmlBody or b""
        if isinstance(html_body, bytes):
            html_body = html_body.decode("utf-8", errors="replace")

        text = body
        if html_body and not body:
            import html2text
            h = html2text.HTML2Text()
            h.ignore_links = False
            text = h.handle(html_body)

        _log_extraction(file_path, "parser", 1, 0)
        return text.strip(), "parser"
    except ImportError:
        log.warning("extract-msg not installed; cannot parse .msg files")
        return "", "unavailable"
    except Exception as e:
        log.error("MSG extraction error for %s: %s", file_path, e)
        return "", "error"


# ---------------------------------------------------------------------------
# EML
# ---------------------------------------------------------------------------

def _extract_eml(file_path: str) -> tuple[str, str]:
    import email as email_lib
    try:
        with open(file_path, "rb") as f:
            msg = email_lib.message_from_bytes(f.read())

        text_parts = []
        html_parts = []

        if msg.is_multipart():
            for part in msg.walk():
                ct = part.get_content_type()
                cd = part.get_content_disposition() or ""
                if "attachment" in cd:
                    continue
                payload = part.get_payload(decode=True)
                if payload is None:
                    continue
                charset = part.get_content_charset() or "utf-8"
                decoded = payload.decode(charset, errors="replace")
                if ct == "text/plain":
                    text_parts.append(decoded)
                elif ct == "text/html":
                    html_parts.append(decoded)
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                decoded = payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
                if msg.get_content_type() == "text/html":
                    html_parts.append(decoded)
                else:
                    text_parts.append(decoded)

        if text_parts:
            return "\n".join(text_parts).strip(), "parser"

        if html_parts:
            import html2text
            h = html2text.HTML2Text()
            h.ignore_links = False
            text = h.handle("\n".join(html_parts))
            return text.strip(), "parser"

        return "", "parser"
    except Exception as e:
        log.error("EML extraction error for %s: %s", file_path, e)
        return "", "error"


# ---------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------

def _extract_image(file_path: str) -> tuple[str, str]:
    pytesseract = _pytesseract()
    Image = _pil_image()
    if not pytesseract or not Image:
        log.warning("pytesseract or Pillow not available; cannot OCR images")
        return "", "ocr_unavailable"
    try:
        img = Image.open(file_path)
        text = pytesseract.image_to_string(img).strip()
        _log_extraction(file_path, "ocr", 1, 1)
        return text, "ocr"
    except Exception as e:
        log.error("Image OCR error for %s: %s", file_path, e)
        return "", "error"


# ---------------------------------------------------------------------------
# Logging helper
# ---------------------------------------------------------------------------

def _log_extraction(file_path: str, method: str, page_count: int, ocr_pages: int):
    """Log extraction method to processing_log. Best-effort — never raises."""
    try:
        from app.database import get_db, now_iso
        get_db().execute("""
            INSERT INTO processing_log (source_file, extraction_method, page_count, ocr_pages, created_at)
            VALUES (?,?,?,?,?)
        """, (os.path.basename(file_path), method, page_count, ocr_pages, now_iso()))
        get_db().commit()
    except Exception as e:
        log.debug("Could not log extraction: %s", e)


# ---------------------------------------------------------------------------
# Body text extraction from cached email dict
# ---------------------------------------------------------------------------

def extract_text_from_email_dict(email_dict: dict) -> str:
    """
    Extract searchable text from an in-memory email dict (from email_cache).
    Combines body_text + text from all attachments.
    """
    parts = []

    body_text = email_dict.get("body_text", "")
    body_html = email_dict.get("body_html", "")

    if body_text:
        parts.append(body_text)
    elif body_html:
        try:
            import html2text
            h = html2text.HTML2Text()
            h.ignore_links = False
            parts.append(h.handle(body_html))
        except Exception:
            pass

    for att in (email_dict.get("attachments") or []):
        att_path = att.get("path", "")
        if att_path and Path(att_path).exists():
            try:
                text, _ = extract_text_from_file(att_path)
                if text:
                    parts.append(text)
            except Exception as e:
                log.warning("Could not extract text from attachment %s: %s", att_path, e)

    return "\n\n".join(parts)
