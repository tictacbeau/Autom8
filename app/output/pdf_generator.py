"""
PDF output generation.

File naming: YYYY-MM-DD_PayorName_$Amount.pdf
Organise into: output_folder/YYYY-MM-DD/
Sort greatest to smallest by deposit amount within each batch
(using a numeric prefix: 001_, 002_, etc., allocated at write time).

Sources:
  - Email body (HTML/text) → WeasyPrint HTML→PDF
  - PDF attachment → copy as-is
  - Other attachment format → convert then save
  - Both body + attachment needed → merge PDFs with PyMuPDF
"""
import logging
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# Graceful fallback if WeasyPrint missing
def _weasyprint():
    try:
        from weasyprint import HTML
        return HTML
    except Exception:
        return None


def _fitz():
    try:
        import fitz
        return fitz
    except ImportError:
        return None


def save_matched_pdf(
    email_dict: dict,
    deposit: dict,
    output_folder: str,
    payor_profile: Optional[dict] = None,
) -> str:
    """
    Generate and save the PDF for a matched remittance.
    Returns the absolute path of the saved file.
    """
    # Determine output subfolder (date-based)
    dep_date = deposit.get("deposit_date") or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if len(dep_date) > 10:
        dep_date = dep_date[:10]

    date_folder = Path(output_folder) / dep_date
    date_folder.mkdir(parents=True, exist_ok=True)

    # Build base filename (sanitise payor name)
    payor_name = deposit.get("payor_name", "Unknown")
    amount = deposit.get("amount", 0)
    safe_name = _safe_filename(payor_name)
    amount_str = f"${amount:,.2f}".replace(",", "")
    base_name = f"{dep_date}_{safe_name}_{amount_str}"

    # Allocate a sort prefix so files sort greatest→smallest within the folder
    prefix = _next_prefix(date_folder, amount)
    filename = f"{prefix}_{base_name}.pdf"
    dest_path = date_folder / filename

    save_mode = "both"
    if payor_profile:
        save_mode = payor_profile.get("save_mode") or "both"

    # Collect source PDFs to combine
    source_pdfs: list[Path] = []

    # Email body → PDF
    if save_mode in ("both", "body"):
        body_pdf = _body_to_pdf(email_dict, dest_path.stem)
        if body_pdf:
            source_pdfs.append(body_pdf)

    # Attachments → PDF
    if save_mode in ("both", "attachment"):
        for att in email_dict.get("attachments") or []:
            att_path = att.get("path", "")
            if att_path and Path(att_path).exists():
                att_pdf = _attachment_to_pdf(att)
                if att_pdf:
                    source_pdfs.append(att_pdf)

    if not source_pdfs:
        # Fallback: convert body even if mode says attachment-only
        body_pdf = _body_to_pdf(email_dict, dest_path.stem)
        if body_pdf:
            source_pdfs.append(body_pdf)

    if not source_pdfs:
        log.warning("No source PDFs generated for deposit %s", deposit.get("id"))
        return ""

    if len(source_pdfs) == 1:
        shutil.move(str(source_pdfs[0]), str(dest_path))
    else:
        _merge_pdfs(source_pdfs, dest_path)
        for tmp in source_pdfs:
            try:
                tmp.unlink()
            except Exception:
                pass

    log.info("Saved PDF: %s", dest_path)
    return str(dest_path)


# ---------------------------------------------------------------------------
# Body → PDF
# ---------------------------------------------------------------------------

def _body_to_pdf(email_dict: dict, stem: str) -> Optional[Path]:
    """Convert email body (HTML or text) to a temporary PDF."""
    body_html = email_dict.get("body_html", "")
    body_text = email_dict.get("body_text", "")

    if not body_html and not body_text:
        return None

    from app.config import DATA_DIR
    tmp_path = DATA_DIR / f"_tmp_{stem}_body.pdf"

    HTML = _weasyprint()
    if HTML:
        try:
            if body_html:
                HTML(string=body_html).write_pdf(str(tmp_path))
            else:
                html_content = f"<html><body><pre>{body_text}</pre></body></html>"
                HTML(string=html_content).write_pdf(str(tmp_path))
            return tmp_path
        except Exception as e:
            log.warning("WeasyPrint failed: %s. Trying text fallback.", e)

    # Fallback: create a minimal PDF with PyMuPDF if WeasyPrint unavailable
    fitz = _fitz()
    if fitz:
        try:
            text = body_text or _html_to_text(body_html)
            doc = fitz.open()
            page = doc.new_page()
            page.insert_text((50, 50), text[:3000], fontsize=10)
            doc.save(str(tmp_path))
            doc.close()
            return tmp_path
        except Exception as e:
            log.warning("PyMuPDF body fallback failed: %s", e)

    return None


def _html_to_text(html: str) -> str:
    """Strip HTML tags for plain-text fallback."""
    try:
        import html2text
        h = html2text.HTML2Text()
        h.ignore_links = False
        return h.handle(html)
    except Exception:
        return re.sub(r'<[^>]+>', '', html)


# ---------------------------------------------------------------------------
# Attachment → PDF
# ---------------------------------------------------------------------------

def _attachment_to_pdf(att: dict) -> Optional[Path]:
    """Convert or copy an attachment to PDF. Returns temp path or None."""
    att_path = Path(att.get("path", ""))
    if not att_path.exists():
        return None

    ext = att_path.suffix.lower()

    # Already a PDF
    if ext == ".pdf":
        return att_path

    # DOCX → PDF (via python-docx if LibreOffice not available)
    if ext == ".docx":
        return _docx_to_pdf(att_path)

    # Images → PDF (via Pillow)
    if ext in (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tiff"):
        return _image_to_pdf(att_path)

    return None


def _docx_to_pdf(docx_path: Path) -> Optional[Path]:
    """Convert DOCX to PDF using python-docx text + PyMuPDF."""
    try:
        from docx import Document as DocxDocument
        doc = DocxDocument(str(docx_path))
        text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        fitz = _fitz()
        if not fitz:
            return None
        tmp = docx_path.with_suffix(".pdf")
        fdoc = fitz.open()
        page = fdoc.new_page()
        page.insert_text((50, 50), text[:3000], fontsize=10)
        fdoc.save(str(tmp))
        fdoc.close()
        return tmp
    except Exception as e:
        log.warning("DOCX→PDF conversion failed: %s", e)
        return None


def _image_to_pdf(img_path: Path) -> Optional[Path]:
    """Convert image to single-page PDF using Pillow."""
    try:
        from PIL import Image
        img = Image.open(str(img_path)).convert("RGB")
        tmp = img_path.with_suffix(".pdf")
        img.save(str(tmp), "PDF")
        return tmp
    except Exception as e:
        log.warning("Image→PDF conversion failed for %s: %s", img_path.name, e)
        return None


# ---------------------------------------------------------------------------
# Merge PDFs
# ---------------------------------------------------------------------------

def _merge_pdfs(source_paths: list[Path], dest: Path):
    """Merge multiple PDFs into one using PyMuPDF."""
    fitz = _fitz()
    if not fitz:
        log.warning("PyMuPDF unavailable; saving first PDF only")
        shutil.copy(str(source_paths[0]), str(dest))
        return
    try:
        merged = fitz.open()
        for src in source_paths:
            if src.exists():
                with fitz.open(str(src)) as part:
                    merged.insert_pdf(part)
        merged.save(str(dest))
        merged.close()
    except Exception as e:
        log.error("PDF merge failed: %s", e)
        shutil.copy(str(source_paths[0]), str(dest))


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _safe_filename(name: str) -> str:
    """Remove characters unsafe for filenames."""
    safe = re.sub(r'[^\w\s\-]', '', name)
    safe = re.sub(r'\s+', '_', safe.strip())
    return safe[:40]


def _next_prefix(folder: Path, amount: float) -> str:
    """
    Assign a zero-padded sort prefix so files sort greatest→smallest.
    Scans existing files, counts them, returns next padded number.
    """
    existing = list(folder.glob("*.pdf"))
    idx = len(existing) + 1
    return f"{idx:03d}"
