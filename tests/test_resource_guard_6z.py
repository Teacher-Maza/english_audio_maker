
from _rc_bootstrap import V2_ROOT

import os
import sys
from pathlib import Path


PROJECT_ROOT = V2_ROOT
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from v2_kokoro.app.core.resource_manager import (  # noqa: E402
    PROFILE_AUTOMATIC,
    PROFILE_BALANCED,
    PROFILE_ECONOMIC,
    ResourceSnapshot,
    apply_runtime_limits,
    evaluate_resources,
    load_resource_policy,
    resolve_profile,
)


policy = load_resource_policy()
automatic = resolve_profile(PROFILE_AUTOMATIC, policy, snapshot=ResourceSnapshot(8.0, 20.0, 80, False, 20.0, 250.0))
economic = resolve_profile(PROFILE_ECONOMIC, policy)
balanced = resolve_profile(PROFILE_BALANCED, policy)
assert automatic.adaptive and automatic.sequential and 1 <= automatic.threads <= 4
assert 1 <= economic.threads <= 2
assert 1 <= balanced.threads <= 4

runtime = apply_runtime_limits(economic)
assert runtime["threads"] == economic.threads
if os.name == "nt":
    assert runtime["priority_below_normal"] is True
assert os.environ["OMP_NUM_THREADS"] == str(economic.threads)
assert os.environ["MKL_NUM_THREADS"] == str(economic.threads)

healthy = ResourceSnapshot(8.0, 20.0, 80, False, 20.0, 250.0)
decision = evaluate_resources(PROFILE_BALANCED, snapshot=healthy, policy=policy)
assert decision.allowed and not decision.blocks

low_ram = ResourceSnapshot(1.5, 20.0, 80, False, 20.0, 250.0)
decision = evaluate_resources(PROFILE_BALANCED, snapshot=low_ram, policy=policy)
assert not decision.allowed and "Memoria" in decision.blocks[0]

eight_gb_busy = ResourceSnapshot(2.0, 20.0, 80, False, 40.0, 250.0, total_ram_gb=8.0)
decision = evaluate_resources(PROFILE_AUTOMATIC, snapshot=eight_gb_busy, policy=policy)
assert decision.allowed and decision.plan["safe_system_reserve_gb"] >= 1.25
conservative = resolve_profile(PROFILE_AUTOMATIC, policy, snapshot=eight_gb_busy, text_characters=5000)
assert conservative.threads == 1 and conservative.chunk_chars == 160 and conservative.throttle_seconds > 0

low_disk = ResourceSnapshot(8.0, 1.0, 80, False, 20.0, 250.0)
decision = evaluate_resources(PROFILE_BALANCED, snapshot=low_disk, policy=policy)
assert not decision.allowed and any("disco" in item for item in decision.blocks)

low_battery = ResourceSnapshot(8.0, 20.0, 10, False, 20.0, 250.0)
decision = evaluate_resources(PROFILE_BALANCED, snapshot=low_battery, policy=policy)
assert not decision.allowed and any("Bateria" in item for item in decision.blocks)

warning = ResourceSnapshot(1.9, 3.0, 25, False, 20.0, 250.0)
decision = evaluate_resources(PROFILE_BALANCED, snapshot=warning, policy=policy)
assert decision.allowed and len(decision.warnings) == 3

print("6Z/RC-19 resource guard: automatic margin, manual profiles, runtime limits and safety warnings OK")
