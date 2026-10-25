"""Load the markdown knowledge base and split it into clause-level chunks.

Each document starts with a YAML front matter block (doc_id, title, category, version,
effective_date, ...). Every clause starts with a heading of the form ``### 1.2 Clause title``
and becomes one chunk. The chunk id is ``<doc_id>#<clause_id>``, for example ``OPS-CUT-001#1.2``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

_FRONT_MATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)
_CLAUSE_HEADING = re.compile(r"^###\s+(\d+\.\d+)\s+(.+?)\s*$", re.M)
_REQUIRED = ("doc_id", "title", "category", "version", "effective_date")


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    doc_id: str
    clause_id: str
    clause_title: str
    doc_title: str
    category: str
    version: str
    effective_date: str
    content: str

    @property
    def embedding_text(self) -> str:
        """Text that is embedded and keyword-indexed: a header that names the clause plus the clause body."""
        return f"{self.doc_id} v{self.version} clause {self.clause_id} - {self.clause_title}\n{self.content}"

    def to_row(self, embedding: list[float] | None = None) -> dict[str, Any]:
        row: dict[str, Any] = {
            "chunk_id": self.chunk_id,
            "doc_id": self.doc_id,
            "clause_id": self.clause_id,
            "clause_title": self.clause_title,
            "doc_title": self.doc_title,
            "category": self.category,
            "version": self.version,
            "effective_date": self.effective_date,
            "content": self.content,
        }
        if embedding is not None:
            row["embedding"] = embedding
        return row

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "Chunk":
        return cls(
            chunk_id=row["chunk_id"],
            doc_id=row["doc_id"],
            clause_id=row["clause_id"],
            clause_title=row["clause_title"],
            doc_title=row["doc_title"],
            category=row["category"],
            version=str(row["version"]),
            effective_date=str(row["effective_date"]),
            content=row["content"],
        )


def parse_document(path: Path) -> list[Chunk]:
    text = Path(path).read_text(encoding="utf-8")
    m = _FRONT_MATTER.match(text)
    if not m:
        raise ValueError(f"{path.name}: missing YAML front matter")
    meta = yaml.safe_load(m.group(1)) or {}
    missing = [k for k in _REQUIRED if k not in meta]
    if missing:
        raise ValueError(f"{path.name}: front matter is missing {missing}")

    body = text[m.end():]
    headings = list(_CLAUSE_HEADING.finditer(body))
    if not headings:
        raise ValueError(f"{path.name}: no '### N.N Title' clause headings found")

    chunks: list[Chunk] = []
    for i, h in enumerate(headings):
        start = h.end()
        end = headings[i + 1].start() if i + 1 < len(headings) else len(body)
        content = body[start:end].strip()
        if not content:
            raise ValueError(f"{path.name}: clause {h.group(1)} is empty")
        chunks.append(
            Chunk(
                chunk_id=f"{meta['doc_id']}#{h.group(1)}",
                doc_id=str(meta["doc_id"]),
                clause_id=h.group(1),
                clause_title=h.group(2),
                doc_title=str(meta["title"]),
                category=str(meta["category"]),
                version=str(meta["version"]),
                effective_date=str(meta["effective_date"]),
                content=content,
            )
        )
    return chunks


def load_chunks(kb_dir: Path) -> list[Chunk]:
    kb_dir = Path(kb_dir)
    files = sorted(kb_dir.glob("*.md"))
    if not files:
        raise FileNotFoundError(f"No .md documents found in {kb_dir}")
    chunks: list[Chunk] = []
    for f in files:
        chunks.extend(parse_document(f))
    ids = [c.chunk_id for c in chunks]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        raise ValueError(f"Duplicate chunk ids: {dupes}")
    return chunks
