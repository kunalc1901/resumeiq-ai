"""Split document text into overlapping chunks for retrieval."""


def chunk_page(
    page: dict,
    words_per_chunk: int = 400,
    overlap_words: int = 50,
) -> list[dict]:
    """Split a single page's text into overlapping word windows.

    Each chunk carries metadata so you can trace it back to the
    original page and word position.

    Args:
        page: Dict with keys ``text``, ``page_number``, ``source``.
        words_per_chunk: Target chunk size in words (default 200).
        overlap_words: Number of words that overlap between adjacent
            chunks (default 20).

    Returns:
        List of chunk dicts, each with ``content`` and ``meta``.
    """
    words = page["text"].split()
    step = words_per_chunk - overlap_words
    if step < 1:
        step = 1

    chunks = []
    for chunk_index, start in enumerate(range(0, len(words), step)):
        chunk_words = words[start : start + words_per_chunk]
        if len(chunk_words) < 10:
            continue

        chunks.append(
            {
                "content": " ".join(chunk_words),
                "meta": {
                    "page": page["page_number"],
                    "source": page["source"],
                    "chunk_index": chunk_index,
                    "word_start": start,
                    "word_end": start + len(chunk_words),
                },
            }
        )
    return chunks


def chunk_document(pages: list[dict]) -> list[dict]:
    """Chunk all pages of a document into a flat list of chunks."""
    all_chunks = []
    for page in pages:
        all_chunks.extend(chunk_page(page))
    return all_chunks
