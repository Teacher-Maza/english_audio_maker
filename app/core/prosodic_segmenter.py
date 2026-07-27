from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass


SEGMENTER_ID = "humanization_b2_conservative_v1"
_MIN_OPTIONAL_SIDE_CHARS = 48

_SENTENCE_RE = re.compile(r"[.!?]+[\"'\u2019\u201d)\]}]*[ \t]*")
_PARAGRAPH_RE = re.compile(r"(?:\r?\n[ \t]*){2,}")
_SEMICOLON_COLON_RE = re.compile(r"[;:]+[ \t]*")
_DASH_RE = re.compile(r"(?:[ \t]+(?:\u2014|\u2013|--)[ \t]+)")
_COMMA_RE = re.compile(r",[ \t]+")
_WHITESPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class _Boundary:
    index: int
    reason: str


@dataclass(frozen=True)
class ProsodicSegment:
    text: str
    boundary: str


@dataclass(frozen=True)
class SegmentationResult:
    source_text: str
    segments: tuple[ProsodicSegment, ...]
    max_chars: int
    paragraph_count: int
    hard_boundary_count: int
    segment_budget: int
    sentence_boundaries_merged: int

    @property
    def texts(self) -> list[str]:
        return [segment.text for segment in self.segments]

    def diagnostics(self) -> dict:
        lengths = [len(segment.text) for segment in self.segments]
        reasons = [segment.boundary for segment in self.segments]
        return {
            "strategy": SEGMENTER_ID,
            "max_chars": self.max_chars,
            "source_char_count": len(self.source_text),
            "segment_count": len(self.segments),
            "segment_budget": self.segment_budget,
            "paragraph_count": self.paragraph_count,
            "hard_boundary_count": self.hard_boundary_count,
            "sentence_boundaries_merged": self.sentence_boundaries_merged,
            "segment_lengths": lengths,
            "max_generated_chars": max(lengths, default=0),
            "boundary_types": reasons,
            "boundary_counts": dict(sorted(Counter(reasons).items())),
            "oversized_segment_count": sum(length > self.max_chars for length in lengths),
            "text_preserved": "".join(self.texts) == self.source_text,
            "connectors_split_by_default": False,
            "full_text_saved": False,
        }


def _visible_length(value: str) -> int:
    return len(value.strip())


def _paragraph_ranges(text: str) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    start = 0
    for match in _PARAGRAPH_RE.finditer(text):
        if text[start:match.start()].strip():
            ranges.append((start, match.end()))
            start = match.end()
    if start < len(text):
        if text[start:].strip() or not ranges:
            ranges.append((start, len(text)))
        else:
            previous_start, _ = ranges.pop()
            ranges.append((previous_start, len(text)))
    return ranges


def _sentence_ends(text: str, start: int, end: int) -> list[int]:
    ends = [match.end() for match in _SENTENCE_RE.finditer(text, start, end) if match.end() < end]
    return ends + [end]


def _optional_boundaries(text: str, start: int, end: int) -> list[_Boundary]:
    priorities = {"semicolon_colon": 0, "dash": 1, "comma": 2}
    by_index: dict[int, str] = {}
    for pattern, reason in (
        (_SEMICOLON_COLON_RE, "semicolon_colon"),
        (_DASH_RE, "dash"),
        (_COMMA_RE, "comma"),
    ):
        for match in pattern.finditer(text, start, end):
            current = by_index.get(match.end())
            if current is None or priorities[reason] < priorities[current]:
                by_index[match.end()] = reason
    return [_Boundary(index, reason) for index, reason in sorted(by_index.items())]


def _balanced_optional_boundary(text: str, start: int, end: int, max_chars: int) -> _Boundary | None:
    remaining = end - start
    pieces_needed = max(2, math.ceil(remaining / max_chars))
    ideal = start + math.ceil(remaining / pieces_needed)
    limit = min(end, start + max_chars)
    candidates = []
    for item in _optional_boundaries(text, start, limit):
        left = _visible_length(text[start:item.index])
        right = _visible_length(text[item.index:end])
        if left >= _MIN_OPTIONAL_SIDE_CHARS and right >= _MIN_OPTIONAL_SIDE_CHARS:
            candidates.append(item)
    if not candidates:
        return None
    reason_priority = {"semicolon_colon": 0, "dash": 1, "comma": 2}
    return min(candidates, key=lambda item: (abs(item.index - ideal), reason_priority[item.reason], -item.index))


def _balanced_word_boundary(text: str, start: int, end: int, max_chars: int) -> _Boundary:
    remaining = end - start
    pieces_needed = max(2, math.ceil(remaining / max_chars))
    ideal = start + math.ceil(remaining / pieces_needed)
    limit = min(end, start + max_chars)
    matches = [
        match
        for match in _WHITESPACE_RE.finditer(text, start, limit + 1)
        if match.end() > start and text[start:match.end()].strip()
    ]
    if matches:
        chosen = min(matches, key=lambda match: (abs(match.end() - ideal), -match.end()))
        return _Boundary(chosen.end(), "length_word_boundary")
    next_space = _WHITESPACE_RE.search(text, limit, end)
    if next_space is not None:
        return _Boundary(next_space.end(), "oversized_token")
    return _Boundary(end, "oversized_token" if remaining > max_chars else "end")


def _split_long_span(text: str, start: int, end: int, max_chars: int) -> list[_Boundary]:
    boundaries: list[_Boundary] = []
    cursor = start
    while end - cursor > max_chars:
        boundary = _balanced_optional_boundary(text, cursor, end, max_chars)
        if boundary is None:
            boundary = _balanced_word_boundary(text, cursor, end, max_chars)
        if boundary.index <= cursor:
            raise RuntimeError("Conservative segmenter did not advance")
        boundaries.append(boundary)
        cursor = boundary.index
    boundaries.append(_Boundary(end, "end"))
    return boundaries


def _paragraph_boundaries(text: str, start: int, end: int, max_chars: int, is_final: bool) -> tuple[list[_Boundary], int]:
    sentence_ends = _sentence_ends(text, start, end)
    boundaries: list[_Boundary] = []
    group_start = start
    previous_end = start
    merged_sentences = 0

    for sentence_end in sentence_ends:
        if sentence_end - group_start <= max_chars:
            if previous_end > group_start and previous_end < sentence_end:
                merged_sentences += 1
            previous_end = sentence_end
            continue

        if previous_end > group_start:
            boundaries.append(_Boundary(previous_end, "sentence"))
            group_start = previous_end

        if sentence_end - group_start > max_chars:
            long_boundaries = _split_long_span(text, group_start, sentence_end, max_chars)
            boundaries.extend(long_boundaries[:-1])
            group_start = long_boundaries[-2].index if len(long_boundaries) > 1 else group_start
            if sentence_end - group_start > max_chars:
                raise RuntimeError("Long sentence remains above the configured limit")
        previous_end = sentence_end

    if not boundaries or boundaries[-1].index < end:
        boundaries.append(_Boundary(end, "end" if is_final else "paragraph"))
    else:
        final = boundaries.pop()
        boundaries.append(_Boundary(final.index, "end" if is_final else "paragraph"))
    return boundaries, merged_sentences


def segment_text_with_diagnostics(text: str, max_chars: int = 280) -> SegmentationResult:
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Text cannot be empty")
    if max_chars < 32:
        raise ValueError("max_chars must be at least 32")

    paragraphs = _paragraph_ranges(text)
    raw_boundaries: list[_Boundary] = []
    merged_sentences = 0
    for index, (start, end) in enumerate(paragraphs):
        boundaries, merged = _paragraph_boundaries(
            text,
            start,
            end,
            max_chars,
            is_final=index == len(paragraphs) - 1,
        )
        raw_boundaries.extend(boundaries)
        merged_sentences += merged

    segments: list[ProsodicSegment] = []
    start = 0
    for boundary in raw_boundaries:
        if boundary.index <= start:
            continue
        piece = text[start:boundary.index]
        if not piece.strip():
            if not segments:
                raise RuntimeError("Conservative segmenter produced an empty leading segment")
            previous = segments.pop()
            segments.append(ProsodicSegment(previous.text + piece, boundary.reason))
        else:
            segments.append(ProsodicSegment(piece, boundary.reason))
        start = boundary.index

    paragraph_count = len(paragraphs)
    sentence_boundary_count = sum(max(0, len(_sentence_ends(text, start, end)) - 1) for start, end in paragraphs)
    hard_boundary_count = sentence_boundary_count + max(0, paragraph_count - 1)
    capacity_minimum = max(1, math.ceil(len(text) / max_chars))
    segment_budget = capacity_minimum + hard_boundary_count
    if len(segments) > segment_budget:
        raise RuntimeError("Conservative segmenter exceeded its segment budget")

    result = SegmentationResult(
        source_text=text,
        segments=tuple(segments),
        max_chars=max_chars,
        paragraph_count=paragraph_count,
        hard_boundary_count=hard_boundary_count,
        segment_budget=segment_budget,
        sentence_boundaries_merged=merged_sentences,
    )
    if "".join(result.texts) != text:
        raise RuntimeError("Conservative segmentation changed the source text")
    return result


def segment_text(text: str, max_chars: int = 280) -> list[str]:
    return segment_text_with_diagnostics(text, max_chars=max_chars).texts
