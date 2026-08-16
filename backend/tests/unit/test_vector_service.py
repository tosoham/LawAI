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


class TestAddDocuments:
    """
    Writing to a collection.

    These run against a real ChromaDB rather than a mock, because the bug they
    pin lives in chromadb's own semantics: ``collection.add`` with an id that
    already exists neither raises nor updates -- it silently keeps the previous
    text. A mocked collection asserts only that *we* called what we meant to
    call, which was exactly the thing that was wrong.
    """

    @pytest.fixture
    def service(self, tmp_path):
        service = VectorService(persist_directory=str(tmp_path / "store"))
        # Deterministic 3-dim vectors: this is about write semantics, not
        # similarity, and loading the real model here costs seconds per test.
        embeddings = Mock()
        embeddings.embed_texts.side_effect = lambda texts: [
            [float(len(t)), 0.0, 1.0] for t in texts
        ]
        service.embedding_service = embeddings
        return service

    def _stored(self, service, doc_id):
        found = service._get_or_create_collection("bns_sections").get(
            ids=[doc_id], include=["documents", "metadatas"]
        )
        return found["documents"][0], found["metadatas"][0]

    def test_a_rewritten_document_replaces_the_old_one(self, service):
        """
        Regression: re-seeding after a corpus fix must actually land.

        ``collection.add`` discards a write whose id already exists, silently
        and without error, so the stale text stays indexed and the seed reports
        success. BNSS 531 held 129,022 characters until the parser stopped it
        swallowing the First Schedule; under ``add`` that correction would have
        been dropped on every re-seed and the API would have kept serving the
        bad section.
        """
        service.add_documents(
            "bns_sections",
            documents=["the old, wrong text"],
            metadatas=[{"section_number": "103", "short_name": "BNS"}],
            ids=["bns_103"],
        )
        service.add_documents(
            "bns_sections",
            documents=["the corrected text"],
            metadatas=[{"section_number": "103", "short_name": "BNS", "fixed": True}],
            ids=["bns_103"],
        )

        document, metadata = self._stored(service, "bns_103")
        assert document == "the corrected text"
        assert metadata["fixed"] is True

    def test_reseeding_the_same_corpus_does_not_duplicate(self, service):
        """Idempotent in count as well as in content."""
        for _ in range(3):
            service.add_documents(
                "bns_sections",
                documents=["a", "b"],
                metadatas=[{"section_number": "1"}, {"section_number": "2"}],
                ids=["bns_1", "bns_2"],
            )

        assert service._get_or_create_collection("bns_sections").count() == 2

    @pytest.mark.parametrize(
        "documents,metadatas,ids",
        [
            (["a", "b", "c"], [{}, {}, {}], ["1", "2"]),          # ids short
            (["a", "b"], [{}, {}, {}], ["1", "2", "3"]),          # documents short
            (["a", "b", "c"], [{}, {}], ["1", "2", "3"]),         # metadatas short
        ],
    )
    def test_a_length_mismatch_is_refused(self, service, documents, metadatas, ids):
        """
        The guard was written as ``len(a) != len(b) != len(c)``, which Python
        reads as ``(a != b) and (b != c)`` -- False whenever two of the three
        happen to match, which is the likeliest mismatch of all. The first two
        cases here went straight through it.

        Worth being precise about the consequence, because the obvious guess is
        wrong: chromadb validates lengths itself and raises ``Unequal lengths
        for fields: ids: 2, metadatas: 3, ...``, so nothing was ever silently
        mis-paired. What the broken guard cost was the diagnosis -- a caller
        that passed 3 documents and 2 ids got an error naming *embeddings*, a
        list it never supplied, from inside a library two calls down.
        """
        with pytest.raises(ValueError, match="same length"):
            service.add_documents("bns_sections", documents, metadatas, ids)

    def test_empty_input_is_refused(self, service):
        with pytest.raises(ValueError, match="cannot be empty"):
            service.add_documents("bns_sections", [], [], [])
