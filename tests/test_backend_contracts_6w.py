
from _rc_bootstrap import V2_ROOT

import sys
from pathlib import Path

sys.path.insert(0, str(V2_ROOT))

from v2_kokoro.app.core.dialogue_parser import parse_dialogue_ab
from v2_kokoro.app.core.generation_contracts import GenerationRequest, MODE_DIALOGUE_AB, MODE_NARRATION
from v2_kokoro.app.core.job_runner import _plan_items, run_generation
from v2_kokoro.app.core.progress_events import ProgressEvent
from v2_kokoro.app.core.text_chunker import chunk_text
from v2_kokoro.app.core.validators import validate_request
from v2_kokoro.app.core.voice_registry import VoiceRegistry


registry = VoiceRegistry()
voice_ids = registry.validate_all()
assert len(voice_ids) == 9
voices = registry.list_voices()
assert all(set(item["review_metadata"]) == {"display_name", "gender", "accent", "favorite", "source"} for item in voices)
assert all(item["review_metadata"]["gender"] in {"Masculino", "Feminino", "Não classificada"} for item in voices)
assert all(item["review_metadata"]["accent"] in {"Americano", "Britânico", "Não classificada"} for item in voices)

valid_narration = GenerationRequest(
    mode=MODE_NARRATION,
    project_name="contract_narration",
    text="A valid narration.",
    narration_voice_id=voice_ids[0],
)
validate_request(valid_narration, registry)

valid_dialogue = GenerationRequest(
    mode=MODE_DIALOGUE_AB,
    project_name="contract_dialogue",
    text="A: Hello.\nB: Hello.",
    voice_a_id=voice_ids[0],
    voice_b_id=voice_ids[0],
)
validate_request(valid_dialogue, registry)
assert len(parse_dialogue_ab(valid_dialogue.text)) == 2
assert len(chunk_text("First sentence. Second sentence.", max_chars=20)) == 2

continued_lf = (
    "  A: First sentence: the internal colon is content.\n"
    "This manually wrapped line stays with A.\n\n"
    "A new paragraph also stays with A.\n"
    "\tB: The second turn starts after optional spaces.\n"
    "This line stays with B."
)
continued_turns = parse_dialogue_ab(continued_lf)
assert [(turn.speaker, turn.text) for turn in continued_turns] == [
    (
        "A",
        "First sentence: the internal colon is content.\n"
        "This manually wrapped line stays with A.\n\n"
        "A new paragraph also stays with A.",
    ),
    ("B", "The second turn starts after optional spaces.\nThis line stays with B."),
]
assert parse_dialogue_ab(continued_lf.replace("\n", "\r\n")) == continued_turns

marker_then_text = parse_dialogue_ab("\nA:\nText on the next line.\n\nB: Reply.\n")
assert [(turn.speaker, turn.text) for turn in marker_then_text] == [
    ("A", "Text on the next line."),
    ("B", "Reply."),
]

continued_request = GenerationRequest(
    mode=MODE_DIALOGUE_AB,
    project_name="continued_dialogue",
    text=continued_lf,
    voice_a_id=voice_ids[0],
    voice_b_id=voice_ids[1],
)
validate_request(continued_request, registry)
continued_items, _, continued_diagnostics = _plan_items(continued_request, max_chunk_chars=90)
assert continued_diagnostics["turn_count"] == 2
assert continued_diagnostics["text_preserved"] is True
assert {voice for voice, _ in continued_items} == {voice_ids[0], voice_ids[1]}

for invalid_dialogue in (
    "Introduction before a marker.\nA: Valid later turn.",
    "A:\n\nB: Non-empty second turn.",
    "   \n\t",
):
    try:
        parse_dialogue_ab(invalid_dialogue)
    except ValueError:
        pass
    else:
        raise AssertionError(f"Invalid dialogue was accepted: {invalid_dialogue!r}")

invalid_requests = [
    GenerationRequest(mode=MODE_NARRATION, project_name="missing_voice", text="Text."),
    GenerationRequest(mode=MODE_DIALOGUE_AB, project_name="missing_b", text="A: Hi.", voice_a_id=voice_ids[0]),
    GenerationRequest(mode="other", project_name="bad_mode", text="Text.", narration_voice_id=voice_ids[0]),
    GenerationRequest(mode=MODE_NARRATION, project_name="empty", text=" ", narration_voice_id=voice_ids[0]),
    GenerationRequest(mode=MODE_NARRATION, project_name="bad/name", text="Text.", narration_voice_id=voice_ids[0]),
    GenerationRequest(mode=MODE_NARRATION, project_name="bad_voice", text="Text.", narration_voice_id="missing_voice"),
    GenerationRequest(
        mode=MODE_DIALOGUE_AB,
        project_name="bad_dialogue",
        text="Teacher: Hello.",
        voice_a_id=voice_ids[0],
        voice_b_id=voice_ids[1],
    ),
]
for request in invalid_requests:
    result = run_generation(request)
    assert result.success is False
    assert result.created_files == []
    assert result.metadata["full_text_saved"] is False

event = ProgressEvent(stage="synthesizing", percent=50, current=1, total=2)
assert not hasattr(event, "text")
print("6W contracts: 9 voices, explicit selections, parser/chunks and errors OK")
