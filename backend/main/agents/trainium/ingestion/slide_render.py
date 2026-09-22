import asyncio
import tempfile
from pathlib import Path

import pypdfium2 as pdfium

from main.config import settings


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
