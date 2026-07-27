
from _rc_bootstrap import V2_ROOT

import ast
import sys
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = V2_ROOT
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from v2_kokoro.app.core.export_manager import create_export_layout  # noqa: E402
from v2_kokoro.app.core.generation_contracts import GenerationRequest, MODE_NARRATION  # noqa: E402
from v2_kokoro.app.core.project_paths import confine_path, load_paths  # noqa: E402
from v2_kokoro.app.core.validators import (  # noqa: E402
    MAX_LINE_CHARS,
    MAX_TEXT_CHARS,
    MAX_TEXT_LINES,
    validate_request,
    validate_text_content,
)
from v2_kokoro.app.core.voice_registry import VoiceRegistry  # noqa: E402


for value in load_paths().values():
    assert value == V2_ROOT or V2_ROOT in value.parents

outside = V2_ROOT.parent / "outside_security_probe"
for candidate in (outside, V2_ROOT / ".." / "outside_security_probe"):
    try:
        confine_path(candidate, label="malicious")
        raise AssertionError("Traversal was accepted")
    except ValueError:
        pass

fake_link = V2_ROOT / "temp" / "phase_7a_fake_link"
original_is_symlink = Path.is_symlink
with patch.object(Path, "is_symlink", autospec=True, side_effect=lambda path: path == fake_link or original_is_symlink(path)):
    try:
        confine_path(fake_link / "payload.txt", label="symlink probe")
        raise AssertionError("Symlink component was accepted")
    except ValueError:
        pass

for bad_name in ("../escape", "C:escape", "bad/name", "x" * 65):
    try:
        create_export_layout(bad_name, V2_ROOT / "temp" / "phase_7a_exports")
        raise AssertionError("Unsafe project name was accepted")
    except ValueError:
        pass

for bad_text in (
    "x" * (MAX_TEXT_CHARS + 1),
    "\n".join("x" for _ in range(MAX_TEXT_LINES + 1)),
    "x" * (MAX_LINE_CHARS + 1),
    "safe\x00unsafe",
):
    try:
        validate_text_content(bad_text)
        raise AssertionError("Unsafe text was accepted")
    except ValueError:
        pass

registry = VoiceRegistry()
request = GenerationRequest(
    mode=MODE_NARRATION,
    project_name="safe_project",
    text="A safe short text.",
    narration_voice_id="af_heart",
)
validate_request(request, registry)

for folder in (V2_ROOT / "app", V2_ROOT / "scripts"):
    for path in folder.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                modules = [alias.name for alias in node.names] if isinstance(node, ast.Import) else [node.module or ""]
                assert not any(module == "pickle" or module.startswith("pickle.") for module in modules)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in {"eval", "exec"}
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if isinstance(node.func.value, ast.Name) and node.func.value.id == "subprocess":
                    shell_keywords = [item for item in node.keywords if item.arg == "shell"]
                    assert shell_keywords and isinstance(shell_keywords[0].value, ast.Constant) and shell_keywords[0].value.value is False

print("7A boundaries: confined paths, traversal/symlink/input rejection and static code audit OK")
