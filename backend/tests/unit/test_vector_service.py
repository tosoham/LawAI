"""
Unit tests for Vector Service

Covers the two behaviours a deployment depends on: where the persistent store
lands, and that a reset works on a database that does not exist yet.
"""
from unittest.mock import Mock, patch

import pytest
from chromadb.errors import NotFoundError

from services.vector_service import DEFAULT_CHROMADB_PATH, VectorService


@pytest.fixture
def _stub_embeddings():
    """Avoid loading the sentence-transformers model for path/plumbing tests."""
    with patch("services.vector_service.get_embedding_service", return_value=Mock()):
        yield


@pytest.mark.usefixtures("_stub_embeddings")
class TestPersistDirectory:
    """Where ChromaDB stores its files."""

    def test_explicit_argument_wins(self, tmp_path):
        service = VectorService(persist_directory=str(tmp_path / "explicit"))
        assert service.persist_directory == str(tmp_path / "explicit")

    def test_reads_chromadb_path_from_environment(self, tmp_path, monkeypatch):
        """
        The container mounts a volume and points CHROMADB_PATH at it. This knob
        was documented in .env.example long before anything read it.
        """
        target = tmp_path / "from-env"
        monkeypatch.setenv("CHROMADB_PATH", str(target))

        service = VectorService()

        assert service.persist_directory == str(target)
        assert target.is_dir()

    def test_falls_back_to_default_when_unset(self, tmp_path, monkeypatch):
        monkeypatch.delenv("CHROMADB_PATH", raising=False)
        monkeypatch.chdir(tmp_path)

        service = VectorService()

        assert service.persist_directory == DEFAULT_CHROMADB_PATH


@pytest.mark.usefixtures("_stub_embeddings")
class TestDeleteCollection:
    """Deleting a collection has to be idempotent."""

    def test_deleting_absent_collection_is_a_no_op(self, tmp_path):
        """
        Regression: init_vector_db.py resets each collection before filling it,
        and chromadb raises NotFoundError rather than shrugging when the
        collection was never created. That aborted the seed on its first
        collection against an empty database -- the exact path a fresh
        deployment takes, so the corpus silently came up empty.
        """
        service = VectorService(persist_directory=str(tmp_path / "fresh"))
        service.client = Mock()
        service.client.delete_collection.side_effect = NotFoundError(
            "Collection [bns_sections] does not exist"
        )

        service.delete_collection("bns_sections")  # must not raise

        service.client.delete_collection.assert_called_once_with("bns_sections")

    def test_other_errors_still_propagate(self, tmp_path):
        """Only absence is benign; a real failure must not be swallowed."""
        service = VectorService(persist_directory=str(tmp_path / "fresh"))
        service.client = Mock()
        service.client.delete_collection.side_effect = RuntimeError("disk is on fire")

        with pytest.raises(RuntimeError, match="disk is on fire"):
            service.delete_collection("bns_sections")
