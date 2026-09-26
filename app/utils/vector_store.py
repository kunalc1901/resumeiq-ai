"""ChromaDB-backed vector store for storing and retrieving chunks.

ChromaDB is an open-source, local vector database.  It uses
`all-MiniLM-L6-v2` (384-dimensional embeddings) by default for
both indexing and querying, so you don't need a separate embedding
model or API key for storage/retrieval.

Multi-user, multi-resume: every chunk is tagged with ``user_id`` and
``resume_id`` in its metadata, and all reads filter by both so each user
only sees their own data for a specific resume.
"""

import hashlib

import chromadb
from chromadb.config import Settings


class VectorStore:
    """Persistent vector store backed by ChromaDB.

    Usage:
        store = VectorStore("path/to/db_dir")
        store.add_chunks(chunks, user_id, resume_id)  # index chunks
    """

    def __init__(self, persist_dir: str = "./chroma_db"):
        self._client = chromadb.PersistentClient(
            path=persist_dir,
            settings=Settings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(
            name="rag_docs",
            metadata={"hnsw:space": "cosine"},
        )

    def add_chunks(self, chunks: list[dict], user_id: str, resume_id: str) -> None:
        """Add a list of chunk dicts to the collection, scoped to a user + resume.

        Each chunk should have:
            content (str)  - the chunk text (gets embedded automatically)
            meta   (dict)  - metadata stored alongside for filtering / display

        Every chunk is tagged with ``user_id`` and ``resume_id`` so it can
        be retrieved later with ``search(..., user_id=user_id,
        resume_id=resume_id)``.
        """
        ids = []
        documents = []
        metadatas = []

        for i, chunk in enumerate(chunks):
            digest = hashlib.md5(chunk["content"].encode()).hexdigest()[:16]
            ids.append(f"{user_id}_{resume_id}_{digest}")
            documents.append(chunk["content"])
            meta = dict(chunk["meta"])
            meta["user_id"] = user_id
            meta["resume_id"] = resume_id
            metadatas.append(meta)

        print(metadatas)

        self._collection.add(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
        )

    def search(
        self,
        query: str,
        user_id: str,
        resume_id: str,
        top_k: int = 5,
    ) -> list[dict]:
        """Embed the *query* and return the *top_k* most similar chunks.

        Only chunks belonging to ``user_id`` for ``resume_id`` are searched.

        Returns a list of dicts with keys:
            content (str)  - chunk text
            meta    (dict) - original metadata
            score   (float) - cosine distance (lower = more similar)
        """
        results = self._collection.query(
            query_texts=[query],
            n_results=top_k,
            where={
                "$and": [
                    {"user_id": user_id},
                    {"resume_id": resume_id},
                ]
            },
        )

        out = []
        for i in range(len(results["ids"][0])):
            out.append(
                {
                    "content": results["documents"][0][i],
                    "meta": results["metadatas"][0][i],
                    "score": results["distances"][0][i],
                }
            )
        return out
