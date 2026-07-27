from __future__ import annotations

import sys
import multiprocessing
from importlib.machinery import ModuleSpec
from pathlib import Path
from types import ModuleType


V2_ROOT = Path(__file__).resolve().parents[1]


def _bind_runtime_package() -> None:
    existing = sys.modules.get("v2_kokoro")
    if existing is not None:
        return
    package = ModuleType("v2_kokoro")
    package.__file__ = str(V2_ROOT / "__init__.py")
    package.__package__ = "v2_kokoro"
    package.__path__ = [str(V2_ROOT)]
    package.__spec__ = ModuleSpec("v2_kokoro", loader=None, is_package=True)
    sys.modules["v2_kokoro"] = package


_bind_runtime_package()

from v2_kokoro.app.security.offline_guard import install_offline_guard


def main() -> int:
    multiprocessing.freeze_support()
    install_offline_guard()
    from v2_kokoro.app.ui.main_window import create_main_window

    root = create_main_window()
    root.mainloop()
    return 0


if __name__ == "__main__":
    main()
