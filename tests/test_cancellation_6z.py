
from _rc_bootstrap import V2_ROOT

import sys
import threading
from pathlib import Path


PROJECT_ROOT = V2_ROOT
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from v2_kokoro.app.core.generation_contracts import GenerationRequest, MODE_NARRATION  # noqa: E402
from v2_kokoro.app.core.job_runner import GenerationCancelled, _GENERATION_LOCK, _check_cancelled, run_generation  # noqa: E402


cancel = threading.Event()
cancel.set()
try:
    _check_cancelled(cancel)
    raise AssertionError("Cancellation was not detected")
except GenerationCancelled:
    pass

request = GenerationRequest(
    mode=MODE_NARRATION,
    project_name="lock_contract",
    text="Safe contract text.",
    narration_voice_id="af_heart",
)
assert _GENERATION_LOCK.acquire(blocking=False)
try:
    result = run_generation(request)
finally:
    _GENERATION_LOCK.release()
assert not result.success and result.errors == ["generation_already_running"]
assert result.created_files == [] and result.metadata["full_text_saved"] is False

print("6Z cancellation: cooperative cancellation signal and backend single-job lock OK")
