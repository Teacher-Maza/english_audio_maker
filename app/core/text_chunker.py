from __future__ import annotations

import re


SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


def _split_long_piece(text: str, max_chars: int) -> list[str]:
    words = text.split()
    chunks: list[str] = []
    current: list[str] = []
    length = 0
    for word in words:
        added = len(word) + (1 if current else 0)
        if current and length + added > max_chars:
            chunks.append(" ".join(current))
            current = [word]
            length = len(word)
        else:
            current.append(word)
            length += added
    if current:
        chunks.append(" ".join(current))
    return chunks


def chunk_text(text: str, max_chars: int = 280) -> list[str]:
    cleaned = re.sub(r"(?m)^\s*###\s*Chunk\s+\d+\s*$", "", text).strip()
    if not cleaned:
        raise ValueError("Text cannot be empty")
    pieces = [piece.strip() for piece in SENTENCE_RE.split(cleaned) if piece.strip()]
    chunks: list[str] = []
    current = ""
    for piece in pieces:
        if len(piece) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_split_long_piece(piece, max_chars))
        elif not current:
            current = piece
        elif len(current) + 1 + len(piece) <= max_chars:
            current += " " + piece
        else:
            chunks.append(current)
            current = piece
    if current:
        chunks.append(current)
    return chunks

