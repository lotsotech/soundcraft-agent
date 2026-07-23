"""
Semantic product search via Pinecone + Gemini embeddings.
Returns ranked product_ids. Gracefully returns [] if not configured.
"""
from __future__ import annotations

INDEX_NAME  = "soundcraft-gear"
EMBED_MODEL = "models/gemini-embedding-001"

_index  = None
_client = None
_ready  = None  # None = untried, True/False = result cached after first attempt


def _init() -> bool:
    global _index, _client, _ready
    if _ready is not None:
        return _ready
    try:
        from agent.config import get_secret
        try:
            pinecone_key = get_secret("PINECONE_API_KEY")
        except ValueError:
            _ready = False
            return False
        google_key = get_secret("GOOGLE_API_KEY")
        from pinecone import Pinecone
        from google import genai
        _client = genai.Client(api_key=google_key)
        _index  = Pinecone(api_key=pinecone_key).Index(INDEX_NAME)
        _ready  = True
    except Exception:
        _ready = False
    return _ready


def semantic_search(query: str, top_k: int = 20) -> list[str]:
    """Return product_ids ranked by semantic similarity. Returns [] if Pinecone is unavailable."""
    if not _init():
        return []
    try:
        result = _client.models.embed_content(
            model=EMBED_MODEL,
            contents=[query],
        )
        vec = result.embeddings[0].values
        response = _index.query(vector=vec, top_k=top_k, include_metadata=True)
        seen, ids = set(), []
        for match in response["matches"]:
            pid = match["metadata"].get("product_id")
            if pid and pid not in seen:
                seen.add(pid)
                ids.append(pid)
        return ids
    except Exception:
        return []
