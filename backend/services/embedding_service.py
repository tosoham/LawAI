"""
Embedding Service for LawAI
Uses sentence-transformers for fast, local embeddings
"""
import logging
from typing import Optional

from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

# Named here rather than inline in __init__ so the seeding path can record it in
# the index manifest. Which model produced a set of vectors is not recoverable
# from the vectors themselves, and querying an index with a different model than
# built it fails silently -- see services/index_manifest.py.
MODEL_NAME = "all-MiniLM-L6-v2"


class EmbeddingService:
    """Singleton service for generating embeddings"""

    _instance: Optional['EmbeddingService'] = None
    _model: SentenceTransformer | None = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize embedding model (singleton pattern)"""
        if self._model is None:
            try:
                # Use lightweight model for speed
                logger.info(f"Loading embedding model: {MODEL_NAME}")
                self._model = SentenceTransformer(MODEL_NAME)
                logger.info("Embedding model loaded successfully")
            except Exception as e:
                logger.error(f"Failed to load embedding model: {e}")
                raise

    @property
    def model_name(self) -> str:
        """The model that produced this service's vectors."""
        return MODEL_NAME

    def embed_text(self, text: str) -> list[float]:
        """
        Generate embedding for a single text

        Args:
            text: Input text to embed

        Returns:
            List of floats representing the embedding
        """
        try:
            if not text or not text.strip():
                raise ValueError("Text cannot be empty")

            embedding = self._model.encode(text, convert_to_numpy=True)
            return embedding.tolist()
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            raise

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embeddings for multiple texts (batch processing)

        Args:
            texts: List of texts to embed

        Returns:
            List of embeddings
        """
        try:
            if not texts:
                raise ValueError("Texts list cannot be empty")

            # Filter out empty texts
            valid_texts = [t for t in texts if t and t.strip()]
            if not valid_texts:
                raise ValueError("No valid texts to embed")

            embeddings = self._model.encode(valid_texts, convert_to_numpy=True)
            return embeddings.tolist()
        except Exception as e:
            logger.error(f"Error generating batch embeddings: {e}")
            raise

    def get_embedding_dimension(self) -> int:
        """
        Get the dimension of embeddings produced by this model.

        sentence-transformers renamed ``get_sentence_embedding_dimension`` to
        ``get_embedding_dimension``; both spellings are in the wild depending on
        the installed version, so prefer the new one and fall back rather than
        pinning a version for a single accessor.
        """
        model = self._model
        getter = getattr(model, "get_embedding_dimension", None) or (
            model.get_sentence_embedding_dimension
        )
        return getter()


# Global instance
_embedding_service: EmbeddingService | None = None


def get_embedding_service() -> EmbeddingService:
    """Get or create the global embedding service instance"""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service
