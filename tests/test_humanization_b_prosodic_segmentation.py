from _rc_bootstrap import V2_ROOT

import hashlib
import json
import math
import re

from v2_kokoro.app.core.generation_contracts import GenerationRequest, MODE_DIALOGUE_AB, MODE_NARRATION
from v2_kokoro.app.core.job_runner import _plan_items
from v2_kokoro.app.core.prosodic_segmenter import SEGMENTER_ID, segment_text_with_diagnostics


CORPUS_ROOT = V2_ROOT / "tests" / "corpus" / "humanization_b_listening_v1_0"
MANIFEST = json.loads((CORPUS_ROOT / "corpus_manifest.json").read_text(encoding="utf-8"))
EXPECTED_COUNTS_280 = [1, 2, 1, 1, 2, 1, 3, 4, 6, 1]


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


assert SEGMENTER_ID == "humanization_b2_conservative_v1"
assert MANIFEST["corpus_id"] == "humanization_b_listening_v1_0"
assert len(MANIFEST["cases"]) == 10

planned_counts = []
for number, case in enumerate(MANIFEST["cases"], start=1):
    path = CORPUS_ROOT / case["file"]
    raw = path.read_bytes()
    assert digest(raw) == case["sha256"]
    text = raw.decode("utf-8")
    assert text.encode("utf-8") == raw

    if case["mode"] == "narration":
        request = GenerationRequest(
            mode=MODE_NARRATION,
            project_name=f"b2_case_{number:02d}",
            text=text,
            narration_voice_id="af_heart",
        )
    else:
        request = GenerationRequest(
            mode=MODE_DIALOGUE_AB,
            project_name=f"b2_case_{number:02d}",
            text=text,
            voice_a_id="am_michael",
            voice_b_id="bf_emma",
        )
    items, _, diagnostics = _plan_items(request, max_chunk_chars=280)
    planned_counts.append(len(items))
    assert diagnostics["strategy"] == SEGMENTER_ID
    assert diagnostics["text_preserved"] is True
    assert diagnostics["full_text_saved"] is False
    assert diagnostics["segment_count"] == len(items)
    assert all(text_piece.strip() for _, text_piece in items)
    assert all(len(text_piece) <= 280 for _, text_piece in items)
    assert text not in json.dumps(diagnostics)
    if case["mode"] == "narration":
        rebuilt = "".join(text_piece for _, text_piece in items)
        assert rebuilt == text
        assert re.findall(r"\S+", rebuilt) == re.findall(r"\S+", text)
        assert diagnostics["segment_count"] <= diagnostics["segment_budget"]
    else:
        assert {voice for voice, _ in items} <= {"am_michael", "bf_emma"}

assert planned_counts == EXPECTED_COUNTS_280, planned_counts

# Conservative behavior learned from the B listening test.
case_02 = (CORPUS_ROOT / MANIFEST["cases"][1]["file"]).read_text(encoding="utf-8")
long_sentence = segment_text_with_diagnostics(case_02, max_chars=280)
assert [len(piece) for piece in long_sentence.texts] == [152, 133]
assert long_sentence.diagnostics()["boundary_counts"] == {"comma": 1, "end": 1}

for case_index in (0, 2, 3, 5, 9):
    text = (CORPUS_ROOT / MANIFEST["cases"][case_index]["file"]).read_text(encoding="utf-8")
    result = segment_text_with_diagnostics(text, max_chars=280)
    assert len(result.texts) == 1

case_05 = (CORPUS_ROOT / MANIFEST["cases"][4]["file"]).read_text(encoding="utf-8")
connectors = segment_text_with_diagnostics(case_05, max_chars=280).diagnostics()
assert connectors["connectors_split_by_default"] is False
assert "connector" not in connectors["boundary_counts"]
assert connectors["boundary_counts"] == {"end": 1, "sentence": 1}

case_07 = (CORPUS_ROOT / MANIFEST["cases"][6]["file"]).read_text(encoding="utf-8")
paragraphs = segment_text_with_diagnostics(case_07, max_chars=280)
assert len(paragraphs.texts) == 3
assert paragraphs.diagnostics()["boundary_counts"] == {"end": 1, "paragraph": 2}
assert paragraphs.diagnostics()["sentence_boundaries_merged"] >= 1

# Every resource profile remains word-safe and within its character ceiling.
for max_chars in (160, 220, 280):
    for case in MANIFEST["cases"]:
        if case["mode"] != "narration":
            continue
        text = (CORPUS_ROOT / case["file"]).read_text(encoding="utf-8")
        result = segment_text_with_diagnostics(text, max_chars=max_chars)
        assert "".join(result.texts) == text
        assert all(len(piece) <= max_chars for piece in result.texts)
        expected_budget = math.ceil(len(text) / max_chars) + result.hard_boundary_count
        assert result.segment_budget == expected_budget
        assert len(result.texts) <= expected_budget

single_token = "x" * 200
oversized = segment_text_with_diagnostics(single_token, max_chars=64)
assert oversized.texts == [single_token]
assert oversized.diagnostics()["oversized_segment_count"] == 1

print("Humanization B2 conservative segmentation: exact corpus, reduced boundaries, dialogue turns, limits and text integrity OK")
