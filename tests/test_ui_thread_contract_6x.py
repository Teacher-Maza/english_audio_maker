
from _rc_bootstrap import V2_ROOT

import sys
from pathlib import Path


root = Path(__file__).resolve().parents[1]
project_root = root.parent
sys.path.insert(0, str(project_root))

from v2_kokoro.app.ui import main_window  # noqa: E402


source = Path(main_window.__file__).read_text(encoding="utf-8")
assert "torch" not in sys.modules
assert "kokoro" not in sys.modules
assert "KokoroEngine" not in source
assert "threading.Thread" in source
assert "queue.Queue" in source
assert "self.root.after" in source
assert "from v2_kokoro.app.core.job_runner import run_generation" in source
assert "self.on_preview_stop(\"Geração iniciada. Prévia parada.\")" in source
assert "self.preview.close()" in source
assert 'self.root.iconbitmap(default=str(V2_ROOT / "app" / "ui" / "assets" / "app_icon.ico"))' in source
assert "bind_all" not in source and "unbind_all" not in source
assert "_bind_preview_mousewheel" in source
assert "V2.Hidden.TNotebook" in source
assert "from v2_kokoro.app.ui.style_tokens import" in source
assert (root / "ABRIR_INTERFACE_V2.bat").is_file()
print("6X UI thread contract: lazy backend, queue/after, local wheel and launcher OK")
