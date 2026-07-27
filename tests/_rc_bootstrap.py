from __future__ import annotations

import sys
from importlib.machinery import ModuleSpec
from pathlib import Path
from types import ModuleType


V2_ROOT = Path(__file__).resolve().parents[1]


def bind_rc_package() -> Path:
    package = ModuleType("v2_kokoro")
    package.__file__ = str(V2_ROOT / "__init__.py")
    package.__package__ = "v2_kokoro"
    package.__path__ = [str(V2_ROOT)]
    package.__spec__ = ModuleSpec("v2_kokoro", loader=None, is_package=True)
    sys.modules["v2_kokoro"] = package
    return V2_ROOT


bind_rc_package()
