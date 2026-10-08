"""Vault chunker — split text into overlapping segments for indexing."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Chunk:
    """A single indexed chunk of text."""
    text: str
    path: str
    project: str | None = None
    kind: str = "session"  # session, source, context, file, idea, report, recipe, fact
    session_id: str | None = None
    source_id: str | None = None
    turn_range: tuple[int, int] | None = None  # (start_turn, end_turn)
    tags: list[str] = field(default_factory=list)
    mode: str = "text"  # text, voice


def _split_by_heading(text: str) -> list[str]:
    """Split text on markdown headings into sections."""
    sections: list[str] = []
    current: list[str] = []
    for line in text.splitlines():
        if line.startswith("# "):
            if current:
                sections.append("\n".join(current))
                current = []
        current.append(line)
    if current:
        sections.append("\n".join(current))
    return sections


def chunk_text(
    text: str,
    path: str,
    *,
    chunk_size: int = 400,
    overlap: int = 60,
    min_section: int = 100,
) -> list[Chunk]:
    """Split *text* into overlapping chunks of approximately *chunk_size* tokens.

    First tries to split on markdown headings. If sections are smaller than
    *min_section* tokens, they are kept as-is. Overlapping windows fill the
    remaining space.

    Returns a list of :class:`Chunk` instances.
    """
    chunks: list[Chunk] = []
    sections = _split_by_heading(text)

    for section in sections:
        section_tokens = len(section) // 4  # rough char->token
        if section_tokens < min_section and len(sections) > 1:
            # Too small for a section — add as one chunk
            chunks.append(Chunk(
                text=section,
                path=path,
                kind="file",
            ))
            continue
        # If section is large enough, chunk it with overlap
        if section_tokens <= chunk_size:
            chunks.append(Chunk(text=section, path=path))
        else:
            chunks.extend(_chunk_window(section, path, chunk_size, overlap))
    return chunks


def _chunk_window(text: str, path: str, chunk_size: int, overlap: int) -> list[Chunk]:
    """Split text into fixed-size overlapping windows."""
    chunks: list[Chunk] = []
    start = 0
    text_len = len(text)
    chunk_size_chars = chunk_size * 4  # rough chars per token

    while start < text_len:
        end = min(start + chunk_size_chars, text_len)
        # Don't break in the middle of a paragraph if possible
        if end < text_len and end > start + 50:
            newline = text.rfind("\n\n", start, end)
            if newline > start + 50:
                end = newline + 1

        chunk_text = text[start:end].strip()
        if chunk_text:
            chunks.append(Chunk(text=chunk_text, path=path))
        if end >= text_len:
            break
        start = end - overlap

    return chunks


def chunk_session_file(content: str, session_slug: str, project: str | None) -> list[Chunk]:
    """Parse a session file and produce chunks, one per turn group."""
    chunks: list[Chunk] = []
    current_turns: list[str] = []
    in_turn = False
    turn_start = 0
    turn_count = 0
    last_mode = "text"

    for i, line in enumerate(content.splitlines()):
        # Detect turn headings: ### Role · HH:MM · mode
        if line.startswith("### ") and " · " in line:
            # Flush previous turn
            if current_turns:
                body = "\n".join(current_turns)
                if body.strip():
                    chunks.append(Chunk(
                        text=body,
                        path=session_slug,
                        project=project,
                        kind="session",
                        session_id=session_slug,
                        turn_range=(turn_start, turn_start + turn_count),
                        mode=last_mode,
                    ))
                current_turns = []
                turn_count = 0
            in_turn = True
            turn_start = turn_count
            # Extract mode from heading
            parts = line.split(" · ")
            if len(parts) >= 3:
                last_mode = parts[-1].strip().lower()
        elif in_turn:
            current_turns.append(line)
            turn_count += 1

    # Flush last turn
    if current_turns:
        body = "\n".join(current_turns)
        if body.strip():
            chunks.append(Chunk(
                text=body,
                path=session_slug,
                project=project,
                kind="session",
                session_id=session_slug,
                turn_range=(turn_start, turn_start + turn_count),
                mode=last_mode,
            ))

    return chunks


def chunk_source_file(content: str, source_id: str, kind: str = "pdf") -> list[Chunk]:
    """Chunk an extracted source file."""
    chunks = chunk_text(
        content,
        path=f"sources/{source_id}",
    )
    for c in chunks:
        c.kind = "source"
        c.source_id = source_id
        c.tags = [kind]
    return chunks
