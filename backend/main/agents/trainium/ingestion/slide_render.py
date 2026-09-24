import asyncio
import io
import tempfile
from pathlib import Path

import pypdfium2 as pdfium

from main.config import settings


def render_pdf_to_png(pdf_bytes: bytes) -> list[bytes]:
    """Rasterize each PDF page to a PNG at 1280px wide, one per page.

    A PDF deck is one page per slide, which is the same shape the PPTX path
    produces after LibreOffice has converted it. This is that path's second
    half, called directly when the upload is already a PDF.
    """
    pdf = pdfium.PdfDocument(pdf_bytes)
    try:
        images: list[bytes] = []
        for page in pdf:
            bitmap = page.render(scale=1280 / page.get_size()[0])
            buffer = io.BytesIO()
            bitmap.to_pil().save(buffer, format="PNG")
            images.append(buffer.getvalue())
        return images
    finally:
        pdf.close()


def _looks_like_chrome(line: str, page_number: int) -> bool:
    """True for page furniture rather than content.

    PDF text comes out in the order the file stores it, which is not reading
    order: slide numbers and footer branding routinely land first. Taking the
    literal first line as the title gave every slide of a real deck the title
    "1 - NIIT", so the obvious furniture is skipped before choosing one.
    """
    stripped = line.strip(" -–—|·•\t")
    if not stripped:
        return True
    # A bare page number, or one glued to a footer, e.g. "12 – Acme".
    if stripped.isdigit():
        return True
    if stripped.split()[0].rstrip(".").isdigit() and len(stripped) < 24:
        return True
    return stripped == str(page_number)


def extract_pdf_text(pdf_bytes: bytes) -> list[dict]:
    """Text per page, shaped like the PPTX extractor's output.

    A PDF has no title placeholder and no speaker notes, so the title is
    inferred: the first line that is not page furniture. The body keeps
    everything, since the Director reads that regardless and dropping content
    would cost more than a slightly wrong title.
    """
    pdf = pdfium.PdfDocument(pdf_bytes)
    try:
        pages: list[dict] = []
        for index, page in enumerate(pdf, start=1):
            textpage = page.get_textpage()
            raw = textpage.get_text_bounded() or ""
            textpage.close()

            lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
            content = [ln for ln in lines if not _looks_like_chrome(ln, index)]
            pages.append(
                {
                    "slide_number": index,
                    "title": content[0] if content else "",
                    "body": "\n".join(content[1:]),
                    "notes": "",
                }
            )
        return pages
    finally:
        pdf.close()


async def render_slides_to_png(pptx_bytes: bytes) -> list[bytes]:
    """Convert a PPTX to PDF via LibreOffice headless, then rasterize each
    page to a PNG at 1280px wide. Returns one PNG per slide, in order.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        pptx_path = tmp_path / "deck.pptx"
        pptx_path.write_bytes(pptx_bytes)

        process = await asyncio.create_subprocess_exec(
            settings.soffice_path,
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            str(tmp_path),
            str(pptx_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()
        if process.returncode != 0:
            raise RuntimeError(f"LibreOffice conversion failed: {stderr.decode()}")

        pdf_path = tmp_path / "deck.pdf"
        if not pdf_path.exists():
            raise RuntimeError("LibreOffice did not produce a PDF output")

        pdf = pdfium.PdfDocument(str(pdf_path))
        images: list[bytes] = []
        for page in pdf:
            bitmap = page.render(scale=1280 / page.get_size()[0])
            pil_image = bitmap.to_pil()
            import io

            buffer = io.BytesIO()
            pil_image.save(buffer, format="PNG")
            images.append(buffer.getvalue())
        pdf.close()

        return images
