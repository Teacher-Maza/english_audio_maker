from __future__ import annotations

import json
import secrets
from pathlib import Path
from typing import Callable

from .project_paths import CONFIG_DIR, V2_ROOT, load_paths


OUTPUT_LOCATION_CONFIG = CONFIG_DIR / "output_location.json"
WriteProbe = Callable[[Path], None]


def _is_inside_v2(path: Path) -> bool:
    resolved = path.resolve(strict=False)
    return resolved == V2_ROOT or V2_ROOT in resolved.parents


def _assert_plain_directory(path: Path, *, create: bool, verify_writable: bool, write_probe: WriteProbe | None = None) -> Path:
    if "\x00" in str(path):
        raise ValueError("A pasta de saída é inválida.")
    candidate = Path(path)
    if not candidate.is_absolute():
        raise ValueError("A pasta de saída precisa ser absoluta.")
    lexical = candidate.absolute()
    if lexical.is_symlink() or lexical.resolve(strict=False) != lexical:
        raise ValueError("A pasta de saída não pode usar links simbólicos.")
    if not lexical.exists():
        if not create or not _is_inside_v2(lexical):
            raise FileNotFoundError("A pasta de saída não existe.")
        lexical.mkdir(parents=True, exist_ok=True)
    if not lexical.is_dir():
        raise ValueError("A saída deve ser uma pasta comum.")
    if verify_writable:
        probe = write_probe or _write_probe
        probe(lexical)
    return lexical


def _write_probe(directory: Path) -> None:
    probe = directory / f".vts_output_probe_{secrets.token_hex(8)}.tmp"
    created = False
    try:
        with probe.open("xb") as handle:
            handle.write(b"ok")
        created = True
    except OSError as exc:
        raise PermissionError("Não há permissão para gravar nessa pasta.") from exc
    finally:
        if created:
            probe.unlink(missing_ok=True)


def validate_output_directory(path: Path, *, create: bool = False, verify_writable: bool = True, write_probe: WriteProbe | None = None) -> Path:
    return _assert_plain_directory(path, create=create, verify_writable=verify_writable, write_probe=write_probe)


def _settings_path(path: Path | None = None) -> Path:
    settings = (path or OUTPUT_LOCATION_CONFIG).resolve(strict=False)
    if settings.is_symlink() or V2_ROOT not in settings.parents:
        raise ValueError("Configuração de saída inválida.")
    return settings


def load_selected_output_directory(*, settings_path: Path | None = None) -> Path | None:
    settings = _settings_path(settings_path)
    if not settings.exists() or settings.is_symlink():
        return None
    try:
        data = json.loads(settings.read_text(encoding="utf-8"))
        value = data.get("selected_output_dir")
        if not isinstance(value, str) or not value.strip():
            return None
        return validate_output_directory(Path(value), verify_writable=False)
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def current_output_directory() -> Path:
    selected = load_selected_output_directory()
    if selected is not None:
        try:
            return validate_output_directory(selected)
        except (OSError, ValueError):
            pass
    return validate_output_directory(load_paths()["generation_output_dir"], create=True)


def save_selected_output_directory(path: Path, *, settings_path: Path | None = None) -> Path:
    directory = validate_output_directory(path)
    settings = _settings_path(settings_path)
    settings.parent.mkdir(parents=True, exist_ok=True)
    temporary = settings.with_suffix(".tmp")
    if temporary.exists() or temporary.is_symlink():
        raise ValueError("Não foi possível atualizar a configuração de saída.")
    temporary.write_text(
        json.dumps({"schema_version": 1, "selected_output_dir": str(directory)}, ensure_ascii=True, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(settings)
    return directory
