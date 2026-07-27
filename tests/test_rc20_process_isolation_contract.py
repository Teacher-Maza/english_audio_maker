from _rc_bootstrap import V2_ROOT

import json
import sys
from pathlib import Path


if str(V2_ROOT) not in sys.path:
    sys.path.insert(0, str(V2_ROOT))

from v2_kokoro.app.core.generation_contracts import GenerationRequest, MODE_NARRATION  # noqa: E402
from v2_kokoro.app.core.job_runner import _should_use_isolated_worker  # noqa: E402
from v2_kokoro.app.core.resource_manager import PROFILE_AUTOMATIC, ResourceSnapshot, resolve_profile  # noqa: E402


policy = json.loads((V2_ROOT / "config" / "resource_policy.json").read_text(encoding="utf-8"))
isolation = policy["process_isolation"]
assert isolation["enabled"] is True
assert isolation["start_method"] == "spawn"
assert isolation["scope"] == "one_kokoro_generation_per_child"
assert isolation["cancel_grace_seconds"] >= 2.0

request = GenerationRequest(
    mode=MODE_NARRATION,
    project_name="isolated_contract",
    text="A valid request uses the disposable Kokoro worker.",
    narration_voice_id="af_heart",
    output_base_dir=V2_ROOT / "temp" / "rc20_contract_output",
)
assert _should_use_isolated_worker(
    request,
    None,
    _resource_evaluator=None,
    _monitor_factory=None,
    _engine_factory=None,
    _mp3_validator=None,
    _use_child_process=None,
)
assert not _should_use_isolated_worker(
    request,
    None,
    _resource_evaluator=lambda *_args, **_kwargs: None,
    _monitor_factory=None,
    _engine_factory=None,
    _mp3_validator=None,
    _use_child_process=None,
)

eight_gb_conservative = resolve_profile(
    PROFILE_AUTOMATIC,
    snapshot=ResourceSnapshot(2.0, 20.0, None, None, 85.0, 150.0, total_ram_gb=8.0),
    text_characters=3000,
)
assert eight_gb_conservative.threads == 1
assert eight_gb_conservative.chunk_chars == 160
assert eight_gb_conservative.sequential is True

print("RC-20 contract: disposable spawn worker and 8 GB conservative plan OK")
