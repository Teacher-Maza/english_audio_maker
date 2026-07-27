from __future__ import annotations

import json
import os
from pathlib import Path


V2_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = V2_ROOT / "config"
DATA_ROOT_ENV = "VTS_V2_HUMANIZATION_A_DATA_ROOT"
OUTPUT_LOCATION_CONFIG = CONFIG_DIR / "output_location.json"
_PATH_SUFFIXES = ("_dir", "_exe", "_config", "_model", "_catalog")


def _confine_to_root(path: Path, root: Path, *, label: str, must_exist: bool, allow_root: bool) -> Path:
    root = root.resolve(strict=False)
    candidate = Path(path)
    lexical = candidate if candidate.is_absolute() else root / candidate
    lexical = lexical.absolute()
    try:
        relative = lexical.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"{label} must stay inside its authorized root") from exc
    if not allow_root and not relative.parts:
        raise ValueError(f"{label} cannot be the authorized root")
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"{label} cannot use symbolic links")
    resolved = lexical.resolve(strict=False)
    if resolved != root and root not in resolved.parents:
        raise ValueError(f"{label} escapes its authorized root")
    if must_exist and not resolved.exists():
        raise FileNotFoundError(f"{label} does not exist")
    return resolved


def confine_path(path: Path, *, label: str = "path", must_exist: bool = False, allow_root: bool = False) -> Path:
    return _confine_to_root(path, V2_ROOT, label=label, must_exist=must_exist, allow_root=allow_root)


def user_data_root() -> Path:
    configured = os.environ.get(DATA_ROOT_ENV)
    if not configured:
        return V2_ROOT
    local_appdata = os.environ.get("LOCALAPPDATA")
    if not local_appdata:
        raise RuntimeError("LOCALAPPDATA is required for installed user data")
    allowed_root = Path(local_appdata).resolve(strict=False)
    return _confine_to_root(Path(configured), allowed_root, label="user data root", must_exist=False, allow_root=False)


def confine_output_path(path: Path, *, label: str = "output", must_exist: bool = False, allow_root: bool = False) -> Path:
    try:
        return confine_path(path, label=label, must_exist=must_exist, allow_root=allow_root)
    except ValueError:
        data_root = user_data_root()
        if data_root != V2_ROOT:
            try:
                return _confine_to_root(path, data_root, label=label, must_exist=must_exist, allow_root=allow_root)
            except ValueError:
                pass
        selected_root = _authorized_external_output_root()
        if selected_root is None:
            raise
        return _confine_to_root(path, selected_root, label=label, must_exist=must_exist, allow_root=allow_root)


def _authorized_external_output_root() -> Path | None:
    config = confine_path(OUTPUT_LOCATION_CONFIG, label="output location config")
    if not config.exists() or config.is_symlink():
        return None
    try:
        data = json.loads(config.read_text(encoding="utf-8"))
        raw = data.get("selected_output_dir")
        if not isinstance(raw, str) or not raw.strip() or "\x00" in raw:
            return None
        root = Path(raw)
        if not root.is_absolute():
            return None
        lexical = root.absolute()
        if lexical.is_symlink() or lexical.resolve(strict=False) != lexical or not lexical.is_dir():
            return None
        return lexical
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def load_paths() -> dict[str, Path]:
    config_path = confine_path(CONFIG_DIR / "paths.json", label="paths config", must_exist=True)
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    resolved: dict[str, Path] = {}
    installed_data_root = user_data_root()
    for key, value in raw.items():
        if not key.endswith(_PATH_SUFFIXES):
            continue
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Invalid relative path for {key}")
        relative = Path(value)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"Path {key} must be relative and cannot contain traversal")
        if installed_data_root != V2_ROOT and key == "audio_dir":
            resolved[key] = confine_output_path(installed_data_root / "audios", label=key)
        elif installed_data_root != V2_ROOT and key == "generation_output_dir":
            resolved[key] = confine_output_path(installed_data_root / "audios" / "generated", label=key)
        else:
            resolved[key] = confine_path(V2_ROOT / relative, label=key)
    return resolved


def relative_to_v2(path: Path) -> str:
    try:
        return confine_path(path, label="relative path").relative_to(V2_ROOT).as_posix()
    except ValueError:
        return confine_output_path(path, label="user output").as_posix()
