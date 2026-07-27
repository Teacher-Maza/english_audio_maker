
from _rc_bootstrap import V2_ROOT

import importlib
import sys
from pathlib import Path


PROJECT_ROOT = V2_ROOT
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main() -> None:
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    try:
        sys.stdout = None
        sys.stderr = None
        module = importlib.import_module("v2_kokoro.app.core.kokoro_engine")
        assert module.sys.stdout is not None
        assert module.sys.stderr is not None
    finally:
        sys.stdout = original_stdout
        sys.stderr = original_stderr

    print("test_pythonw_kokoro_runtime_6y: OK")


if __name__ == "__main__":
    main()
