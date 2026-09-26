"""Extract text from PDFs loaded from bytes."""

import pymupdf as fitz


def read_pdf(pdf_bytes: bytes, source: str = "s3") -> list[dict]:
    """Open a PDF from bytes and return each page's text as a dict.

    Returns a list of dicts, one per page:
        {"text": str, "page_number": int, "source": str}
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages = []
    for page_num in range(len(doc)):
        page = doc[page_num]
        text = page.get_text().strip()
        if text:
            pages.append(
                {
                    "text": text,
                    "page_number": page_num + 1,
                    "source": source,
                }
            )
    doc.close()
    return pages