"""
What produced the index, recorded alongside it.

A vector index is derived data, and the derivation is invisible once it is
written: 3,184 rows of 384 floats look exactly the same whichever model
produced them. That is the failure this file exists to prevent.

**Swapping the embedding model against an existing store is silent.** Nothing
errors, every query returns results, and every result is subtly wrong -- the
query is embedded by one model and compared against vectors written by another,
so the distances are meaningless while remaining perfectly well-formed numbers.
There is no assertion anywhere downstream that could catch it, because at that
point the only evidence is that the answers got slightly worse.

The same holds, less dramatically, for the chunk parameters: an index built at
1,200 characters and queried by a system that now assumes 800 is not corrupt,
just stale in a way nothing reports.

So the manifest records the inputs to the derivation -- model, dimension, chunk
size and overlap -- and the seeding path refuses to append to a store whose
manifest disagrees. It also records a content hash per collection, which is what
makes a re-seed of an unchanged corpus a no-op rather than a five-minute
re-embedding pass.

The manifest lives *inside* the Chroma directory, so it travels with the volume
it describes. A store with no manifest is treated as unknown provenance and
rebuilt.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

MANIFEST_FILENAME = "index_manifest.json"

# Bumped when the manifest's own shape changes in a way older readers cannot
# interpret. An unrecognised version is treated as incompatible rather than
# guessed at.
SCHEMA_VERSION = 1


# The chunk's own hash is stored in its metadata so the next run can tell what
# changed without re-reading the corpus. It must be excluded from the hash it is
# stored under, or the value depends on whether it has been written yet: the
# first pass hashes metadata without it, the second hashes metadata with it, the
# two never agree, and every chunk looks changed forever. That is a silent
# failure -- the index stays correct, the reuse optimisation just quietly never
# fires. Measured: 525 embedded / 0 reused on a corpus where one chunk moved.
HASH_EXCLUDED_METADATA_KEYS = frozenset({"content_hash"})


def _hashable_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in metadata.items() if k not in HASH_EXCLUDED_METADATA_KEYS}


def content_hash(chunks: list[dict[str, Any]]) -> str:
    """
    A stable fingerprint of what a collection should contain.

    Hashes id, text and metadata for every chunk, sorted by id so the digest
    does not depend on iteration order. Metadata is included because a chunk
    whose text is unchanged but whose section number was corrected is a
    different chunk for every purpose that matters -- the citation is what the
    reader follows.

    Hashing the same chunk twice gives the same answer whether or not it has
    already been stamped with its own hash; see the note above.
    """
    digest = hashlib.sha256()
    for chunk in sorted(chunks, key=lambda c: c["id"]):
        digest.update(chunk["id"].encode())
        digest.update(b"\x00")
        digest.update(chunk["text"].encode())
        digest.update(b"\x00")
        # sort_keys so a dict rebuilt in a different order hashes the same.
        digest.update(
            json.dumps(
                _hashable_metadata(chunk["metadata"]), sort_keys=True, default=str
            ).encode()
        )
        digest.update(b"\x1e")
    return digest.hexdigest()


def chunk_hash(chunk: dict[str, Any]) -> str:
    """Fingerprint one chunk, for deciding whether it must be re-embedded."""
    return content_hash([chunk])


@dataclass
class CollectionState:
    """What a single collection held when it was last written."""

    documents: int = 0
    chunks: int = 0
    content_hash: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> CollectionState:
        return cls(
            documents=int(payload.get("documents", 0)),
            chunks=int(payload.get("chunks", 0)),
            content_hash=str(payload.get("content_hash", "")),
        )


@dataclass
class IndexManifest:
    """The provenance of an index, written beside it."""

    embedding_model: str
    embedding_dimension: int
    chunk_max_chars: int
    chunk_overlap_chars: int
    schema_version: int = SCHEMA_VERSION
    collections: dict[str, CollectionState] = field(default_factory=dict)
    updated_at: str = ""

    # -- provenance --------------------------------------------------------

    def build_fingerprint(self) -> str:
        """
        Everything that determines how vectors were produced.

        Deliberately excludes the corpus: a manifest whose fingerprint matches
        describes an index this code *could* have written, whatever is in it.
        Whether the contents are current is the per-collection content hash's
        question, and the two failures want different remedies -- a fingerprint
        mismatch means rebuild from scratch, a content mismatch means re-seed
        the collections that moved.
        """
        parts = (
            f"schema={self.schema_version}",
            f"model={self.embedding_model}",
            f"dim={self.embedding_dimension}",
            f"chunk={self.chunk_max_chars}",
            f"overlap={self.chunk_overlap_chars}",
        )
        return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]

    def incompatible_with(self, other: IndexManifest) -> str | None:
        """
        Why ``other`` cannot be appended to this index, or None if it can.

        Returns a human-readable reason rather than a bool, because this is
        printed to whoever is running the seed and "manifest mismatch" is not
        an actionable message.
        """
        if self.schema_version != other.schema_version:
            return (
                f"manifest schema {other.schema_version} was written by a different "
                f"version of this code (this one writes {self.schema_version})"
            )
        if self.embedding_model != other.embedding_model:
            return (
                f"index was built with embedding model {other.embedding_model!r}, "
                f"this run uses {self.embedding_model!r} -- their vectors are not "
                "comparable"
            )
        if self.embedding_dimension != other.embedding_dimension:
            return (
                f"index holds {other.embedding_dimension}-dimensional vectors, "
                f"this run produces {self.embedding_dimension}"
            )
        if (self.chunk_max_chars, self.chunk_overlap_chars) != (
            other.chunk_max_chars,
            other.chunk_overlap_chars,
        ):
            return (
                f"index was chunked at {other.chunk_max_chars}/"
                f"{other.chunk_overlap_chars} chars, this run uses "
                f"{self.chunk_max_chars}/{self.chunk_overlap_chars}"
            )
        return None

    def collection_is_current(self, name: str, digest: str) -> bool:
        state = self.collections.get(name)
        return state is not None and state.content_hash == digest and bool(digest)

    def record(self, name: str, documents: int, chunks: int, digest: str) -> None:
        self.collections[name] = CollectionState(
            documents=documents, chunks=chunks, content_hash=digest
        )

    # -- persistence -------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["build_fingerprint"] = self.build_fingerprint()
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> IndexManifest:
        return cls(
            embedding_model=str(payload.get("embedding_model", "")),
            embedding_dimension=int(payload.get("embedding_dimension", 0)),
            chunk_max_chars=int(payload.get("chunk_max_chars", 0)),
            chunk_overlap_chars=int(payload.get("chunk_overlap_chars", 0)),
            schema_version=int(payload.get("schema_version", 0)),
            collections={
                name: CollectionState.from_dict(state)
                for name, state in (payload.get("collections") or {}).items()
            },
            updated_at=str(payload.get("updated_at", "")),
        )

    def write(self, directory: str | Path) -> Path:
        """
        Write the manifest, atomically.

        Written to a temporary file and renamed, because a manifest truncated
        by a crash is worse than none: it would claim provenance the index does
        not have, and `os.replace` is atomic on POSIX.
        """
        self.updated_at = datetime.now(UTC).isoformat()
        path = Path(directory) / MANIFEST_FILENAME
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(self.to_dict(), indent=2) + "\n")
        temporary.replace(path)
        return path

    @classmethod
    def read(cls, directory: str | Path) -> IndexManifest | None:
        """Read the manifest, or None if absent or unreadable."""
        path = Path(directory) / MANIFEST_FILENAME
        if not path.is_file():
            return None
        try:
            return cls.from_dict(json.loads(path.read_text()))
        except (json.JSONDecodeError, ValueError, TypeError) as error:
            # Unreadable is treated as absent: the index gets rebuilt, which is
            # slow but correct. Trusting a half-parsed manifest is neither.
            logger.warning(f"ignoring unreadable manifest at {path}: {error}")
            return None
