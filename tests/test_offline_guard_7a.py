
from _rc_bootstrap import V2_ROOT

import os
import socket
import sys
from pathlib import Path


PROJECT_ROOT = V2_ROOT
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from v2_kokoro.app.security.offline_guard import (  # noqa: E402
    OfflineNetworkError,
    install_offline_guard,
    is_offline_guard_installed,
)


install_offline_guard()
install_offline_guard()
assert is_offline_guard_installed()
assert os.environ["HF_HUB_OFFLINE"] == "1"
assert os.environ["TRANSFORMERS_OFFLINE"] == "1"
assert os.environ["HF_HUB_DISABLE_TELEMETRY"] == "1"

for operation in (
    lambda: socket.create_connection(("127.0.0.1", 9), timeout=0.01),
    lambda: socket.getaddrinfo("example.invalid", 443),
    lambda: socket.socket().connect(("127.0.0.1", 9)),
):
    try:
        operation()
        raise AssertionError("Network operation was not blocked")
    except OfflineNetworkError:
        pass

source = (V2_ROOT / "app" / "core" / "job_runner.py").read_text(encoding="utf-8")
assert source.index("install_offline_guard()") < source.index("from .kokoro_engine import KokoroEngine")

print("7A offline guard: environment, DNS and outbound socket operations blocked in process")
