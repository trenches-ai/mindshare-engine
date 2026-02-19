"""
embedder.py - Sentence-transformer embedding (CPU-friendly, cached on init).
"""
from __future__ import annotations
import numpy as np
from loguru import logger
from mindshare_engine.config import EMBEDDING_MODEL


class Embedder:
    """Wraps sentence-transformers for batch and single embedding."""

    def __init__(self) -> None:
        from sentence_transformers import SentenceTransformer
        logger.info(f"Loading embedding model: {EMBEDDING_MODEL}")
        self._model = SentenceTransformer(EMBEDDING_MODEL)
        logger.info("Embedding model loaded")

    def embed_texts(self, texts: list[str]) -> np.ndarray:
        """Embed a list of texts, returns (N, D) float32 array."""
        if not texts:
            return np.array([])
        return self._model.encode(texts, convert_to_numpy=True, show_progress_bar=False)

    def embed_single(self, text: str) -> np.ndarray:
        """Embed a single text string."""
        return self._model.encode([text], convert_to_numpy=True, show_progress_bar=False)[0]

    @staticmethod
    def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        """Cosine similarity between two vectors."""
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))

    @staticmethod
    def cosine_similarities_batch(query: np.ndarray, matrix: np.ndarray) -> np.ndarray:
        """Cosine similarity between a query vector and a matrix of vectors."""
        if matrix.ndim == 1:
            matrix = matrix.reshape(1, -1)
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1e-10, norms)
        normed = matrix / norms
        query_norm = query / (np.linalg.norm(query) + 1e-10)
        return normed @ query_norm
