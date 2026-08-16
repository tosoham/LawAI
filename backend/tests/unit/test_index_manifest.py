"""
The manifest, and the failure it exists to catch.

Querying an index with a different embedding model than built it is silent and
total: the vectors are well-formed, the distances are numbers, and every answer
is subtly wrong. Nothing downstream can detect it, so it has to be caught at the
only point where both facts are known -- the seed.
"""
import json

import pytest

from services.index_manifest import (
    MANIFEST_FILENAME,
    IndexManifest,
    chunk_hash,
    content_hash,
)


def manifest(**overrides) -> IndexManifest:
    defaults = {
        "embedding_model": "all-MiniLM-L6-v2",
        "embedding_dimension": 384,
        "chunk_max_chars": 1200,
        "chunk_overlap_chars": 150,
    }
    return IndexManifest(**{**defaults, **overrides})


def chunk(chunk_id: str, text: str, **metadata) -> dict:
    return {"id": chunk_id, "text": text, "metadata": metadata or {"section": "1"}}


class TestContentHash:
    def test_the_same_chunks_hash_the_same(self):
        chunks = [chunk("a", "one"), chunk("b", "two")]
        assert content_hash(chunks) == content_hash(list(chunks))

    def test_order_does_not_matter(self):
        """Chunks arrive in whatever order the loader produced them."""
        a, b = chunk("a", "one"), chunk("b", "two")
        assert content_hash([a, b]) == content_hash([b, a])

    def test_changed_text_changes_the_hash(self):
        assert content_hash([chunk("a", "one")]) != content_hash([chunk("a", "ONE")])

    def test_changed_metadata_changes_the_hash(self):
        """
        A chunk whose text is unchanged but whose section number was corrected
        is a different chunk for every purpose that matters here -- the citation
        is what the reader follows.
        """
        assert content_hash([chunk("a", "one", section="1")]) != content_hash(
            [chunk("a", "one", section="2")]
        )

    def test_metadata_key_order_does_not_matter(self):
        one = {"id": "a", "text": "t", "metadata": {"x": 1, "y": 2}}
        two = {"id": "a", "text": "t", "metadata": {"y": 2, "x": 1}}
        assert content_hash([one]) == content_hash([two])

    def test_a_removed_chunk_changes_the_hash(self):
        both = [chunk("a", "one"), chunk("b", "two")]
        assert content_hash(both) != content_hash(both[:1])

    def test_chunk_hash_is_per_chunk(self):
        assert chunk_hash(chunk("a", "one")) != chunk_hash(chunk("a", "two"))

    def test_stamping_a_chunk_with_its_own_hash_does_not_change_its_hash(self):
        """
        Regression, and a silent one.

        Each chunk's hash is stored in its own metadata so the next run can tell
        what changed without re-reading the corpus. If the hash covered that
        key, its value would depend on whether it had been written yet -- the
        first pass hashes metadata without it, the second hashes metadata with
        it, the two never agree, and every chunk looks changed forever.

        Nothing breaks: the index stays correct and the seed still succeeds. The
        reuse optimisation just never fires, and the only evidence is a
        surprising number in a log line. Measured before the fix: a corpus where
        exactly one chunk had moved re-embedded all 525 and reported
        "525 embedded, 0 reused". After: "1 embedded, 524 reused".
        """
        pristine = chunk("a", "one", section="103")
        digest = chunk_hash(pristine)

        stamped = {**pristine, "metadata": {**pristine["metadata"], "content_hash": digest}}

        assert chunk_hash(stamped) == digest

    def test_a_stamped_chunk_still_detects_a_real_change(self):
        """The exclusion must not blind the hash to anything that matters."""
        stamped = chunk("a", "one", section="103", content_hash="whatever")
        changed = chunk("a", "one", section="104", content_hash="whatever")
        assert chunk_hash(stamped) != chunk_hash(changed)


class TestCompatibility:
    """What may be appended to an existing index, and what may not."""

    def test_an_identical_build_is_compatible(self):
        assert manifest().incompatible_with(manifest()) is None

    def test_a_different_embedding_model_is_refused(self):
        reason = manifest().incompatible_with(manifest(embedding_model="bge-small-en"))
        assert reason is not None
        assert "bge-small-en" in reason
        assert "not comparable" in reason

    def test_a_different_dimension_is_refused(self):
        reason = manifest().incompatible_with(manifest(embedding_dimension=768))
        assert reason is not None and "768" in reason

    def test_different_chunk_parameters_are_refused(self):
        reason = manifest().incompatible_with(manifest(chunk_max_chars=800))
        assert reason is not None and "800" in reason

    def test_a_different_schema_version_is_refused(self):
        reason = manifest().incompatible_with(manifest(schema_version=99))
        assert reason is not None and "99" in reason

    def test_the_reason_is_readable(self):
        """
        Printed to whoever is running the seed. "manifest mismatch" is not an
        actionable message; naming both models is.
        """
        reason = manifest().incompatible_with(manifest(embedding_model="other-model"))
        assert "all-MiniLM-L6-v2" in reason and "other-model" in reason

    def test_the_fingerprint_ignores_corpus_contents(self):
        """
        A fingerprint match says the index *could* have been written by this
        code. Whether its contents are current is a separate question with a
        separate remedy.
        """
        empty = manifest()
        filled = manifest()
        filled.record("bns_sections", documents=358, chunks=525, digest="deadbeef")
        assert empty.build_fingerprint() == filled.build_fingerprint()


class TestCurrency:
    def test_a_matching_digest_is_current(self):
        m = manifest()
        m.record("bns_sections", 358, 525, "abc123")
        assert m.collection_is_current("bns_sections", "abc123")

    def test_a_different_digest_is_not(self):
        m = manifest()
        m.record("bns_sections", 358, 525, "abc123")
        assert not m.collection_is_current("bns_sections", "changed")

    def test_an_unknown_collection_is_not_current(self):
        assert not manifest().collection_is_current("bns_sections", "abc123")

    def test_an_empty_digest_is_never_current(self):
        """Otherwise two collections that both failed to hash look identical."""
        m = manifest()
        m.record("bns_sections", 0, 0, "")
        assert not m.collection_is_current("bns_sections", "")


class TestPersistence:
    def test_a_round_trip_preserves_everything(self, tmp_path):
        original = manifest()
        original.record("bns_sections", 358, 525, "abc123")
        original.write(tmp_path)

        restored = IndexManifest.read(tmp_path)

        assert restored.embedding_model == original.embedding_model
        assert restored.embedding_dimension == 384
        assert restored.chunk_max_chars == 1200
        assert restored.collections["bns_sections"].chunks == 525
        assert restored.collections["bns_sections"].content_hash == "abc123"
        assert restored.build_fingerprint() == original.build_fingerprint()

    def test_writing_records_a_timestamp(self, tmp_path):
        manifest().write(tmp_path)
        payload = json.loads((tmp_path / MANIFEST_FILENAME).read_text())
        assert payload["updated_at"]

    def test_an_absent_manifest_reads_as_none(self, tmp_path):
        assert IndexManifest.read(tmp_path) is None

    def test_a_corrupt_manifest_reads_as_none(self, tmp_path):
        """
        Rebuilding is slow but correct; trusting a half-parsed manifest is
        neither. A truncated file must not be read as "no collections are
        current", which would be indistinguishable from a valid empty one --
        both rebuild, so the safe answer is the same either way.
        """
        (tmp_path / MANIFEST_FILENAME).write_text('{"embedding_model": "trunc')
        assert IndexManifest.read(tmp_path) is None

    def test_the_write_is_atomic(self, tmp_path):
        """
        Written to a temporary file and renamed. A manifest truncated by a crash
        would claim provenance the index does not have.
        """
        manifest().write(tmp_path)
        assert not list(tmp_path.glob("*.tmp"))
        assert (tmp_path / MANIFEST_FILENAME).is_file()

    def test_rewriting_replaces_rather_than_appends(self, tmp_path):
        first = manifest()
        first.record("bns_sections", 358, 525, "aaa")
        first.write(tmp_path)

        second = manifest()
        second.record("bns_sections", 358, 600, "bbb")
        second.write(tmp_path)

        restored = IndexManifest.read(tmp_path)
        assert restored.collections["bns_sections"].chunks == 600
        assert restored.collections["bns_sections"].content_hash == "bbb"


@pytest.mark.parametrize("missing", ["embedding_model", "collections", "schema_version"])
def test_a_partial_manifest_does_not_explode(tmp_path, missing):
    """
    Forward compatibility: a manifest written by another version may lack keys
    this one expects. It should read as something safe and be judged
    incompatible, not raise.
    """
    payload = manifest().to_dict()
    payload.pop(missing, None)
    (tmp_path / MANIFEST_FILENAME).write_text(json.dumps(payload))

    restored = IndexManifest.read(tmp_path)

    assert restored is not None
    if missing != "collections":
        assert manifest().incompatible_with(restored) is not None
