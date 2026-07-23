import os

from langchain_openai import OpenAIEmbeddings

EMBEDDING_MODEL = "text-embedding-3-small"

_embeddings: OpenAIEmbeddings | None = None


def _get_embeddings() -> OpenAIEmbeddings:
    global _embeddings
    if _embeddings is None:
        _embeddings = OpenAIEmbeddings(model=EMBEDDING_MODEL, api_key=os.environ["OPENAI_API_KEY"])
    return _embeddings


async def embed_text(text: str) -> list[float]:
    return await _get_embeddings().aembed_query(text)
