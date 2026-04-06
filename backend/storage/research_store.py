from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class NoteRecord:
    key: str
    note: str
    tags: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=_utc_now)


class ResearchStore:
    """
    Lightweight in-memory storage for notes, cached payloads, and paper catalogs.

    The current app already uses in-memory session state, so this store follows
    the same lifecycle and keeps the implementation simple for the MVP.
    """

    def __init__(self) -> None:
        self._notes: dict[str, list[NoteRecord]] = {}
        self._catalogs: dict[str, dict[str, dict[str, Any]]] = {}
        self._cache: dict[str, Any] = {}

    def save_note(
        self,
        namespace: str,
        note: str,
        key: str | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        clean_namespace = namespace or "default"
        clean_key = key or f"note_{len(self._notes.get(clean_namespace, [])) + 1}"
        record = NoteRecord(key=clean_key, note=note, tags=tags or [])
        self._notes.setdefault(clean_namespace, []).append(record)
        return {
            "namespace": clean_namespace,
            "key": clean_key,
            "note": note,
            "tags": record.tags,
            "created_at": record.created_at,
        }

    def get_notes(self, namespace: str) -> list[dict[str, Any]]:
        return [
            {
                "key": note.key,
                "note": note.note,
                "tags": list(note.tags),
                "created_at": note.created_at,
            }
            for note in self._notes.get(namespace or "default", [])
        ]

    def upsert_papers(
        self,
        namespace: str,
        papers: list[dict[str, Any]],
    ) -> dict[str, Any]:
        clean_namespace = namespace or "default"
        catalog = self._catalogs.setdefault(clean_namespace, {})
        inserted = 0
        updated = 0

        for paper in papers:
            paper_id = (
                str(paper.get("id") or "")
                or str(paper.get("doi") or "")
                or str(paper.get("arxiv_id") or "")
                or str(paper.get("title") or "").strip().lower()
            )
            if not paper_id:
                continue
            if paper_id in catalog:
                catalog[paper_id].update(paper)
                updated += 1
            else:
                catalog[paper_id] = dict(paper)
                inserted += 1

        return {
            "namespace": clean_namespace,
            "inserted": inserted,
            "updated": updated,
            "total": len(catalog),
        }

    def list_papers(self, namespace: str) -> list[dict[str, Any]]:
        catalog = self._catalogs.get(namespace or "default", {})
        return list(catalog.values())

    def cache_store(self, key: str, value: Any) -> dict[str, Any]:
        self._cache[key] = value
        return {"key": key, "stored": True}

    def cache_lookup(self, key: str) -> dict[str, Any]:
        hit = key in self._cache
        return {"key": key, "hit": hit, "value": self._cache.get(key)}


research_store = ResearchStore()
