"""Index service — search API routes."""

from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from sunny.index.service import SearchResult, search

router = APIRouter(tags=["index"])


@router.get("/search")
def search_index(
    q: str = Query(..., min_length=1, alias="q"),
    project: Optional[str] = Query(None),
    kinds: Optional[str] = Query(None, description="Comma-separated: session,source,context,file"),
    tags: Optional[str] = Query(None, description="Comma-separated tags"),
    since: Optional[date] = Query(None),
    mode: str = Query("hybrid", regex="^(hybrid|keyword|semantic)$"),
    k: int = Query(8, ge=1, le=50),
) -> list[dict]:
    """Search the vault index.

    Returns SearchResult objects merged by hybrid RRF (when mode=hybrid),
    or from FTS5 alone (keyword) or vector alone (semantic).
    """
    kinds_list = [k.strip() for k in kinds.split(",")] if kinds else None
    tags_list = [t.strip() for t in tags.split(",")] if tags else None

    try:
        results = search(
            query=q,
            project=project,
            kinds=kinds_list,
            tags=tags_list,
            since=since,
            mode=mode,
            k=k,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return [r.model_dump() for r in results]
