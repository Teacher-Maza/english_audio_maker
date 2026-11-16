from _rc_bootstrap import V2_ROOT

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from v2_kokoro.app.core.voice_registry import VoiceRegistry
from v2_kokoro.installer import build_installer as build

expected = {'af_heart', 'af_bella', 'bf_emma', 'af_aoede', 'am_fenrir', 'am_puck', 'bm_george', 'bm_lewis', 'am_echo'}
registry = VoiceRegistry()
assert set(registry.validate_all()) == expected
voices = registry.list_voices()
assert sum(v['review_metadata']['gender'] == 'Feminino' for v in voices) == 4
assert sum(v['review_metadata']['gender'] == 'Masculino' for v in voices) == 5
for name, field in [('voice_preview_catalog.json', 'voice_id'), ('english_voices.json', 'id')]:
    data = json.loads((V2_ROOT / 'config' / name).read_text(encoding='utf-8'))
    assert {v[field] for v in data['voices']} == expected
for rejected in ('af_nicole', 'am_michael'):
    try:
        registry.get(rejected)
    except ValueError:
        pass
    else:
        raise AssertionError('Rejected voice accepted')

# Build a tiny synthetic payload, including an unapproved local voicepack.
base = V2_ROOT / 'temp'
base.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(dir=base) as temporary:
    root = Path(temporary)
    source, payload = root / 'source', root / 'payload'
    source.mkdir()
    for relative in ('app/main.py', 'tools/ffmpeg.exe', 'installer/Launch.cmd',
                     'requirements.lock.txt', 'models/Kokoro-82M/config.json',
                     'models/Kokoro-82M/kokoro-v1_0.pth',
                     'models/Kokoro-82M/voices/af_nicole.pt'):
        path = source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'test')
    for voice in voices:
        for field in ('voicepack_path', 'preview_wav_path'):
            path = source / voice[field]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'test')
    (source / 'config').mkdir()
    for name in build.CONFIG_ALLOWLIST:
        (source / 'config' / name).write_bytes((V2_ROOT / 'config' / name).read_bytes())
    with patch.object(build, 'V2_ROOT', source), patch.object(build, 'PAYLOAD_DIR', payload), patch.object(build, 'INSTALLER_DIR', source / 'installer'):
        build.copy_application()
    packed = payload / 'v2_kokoro'
    assert {p.stem for p in (packed / 'models/Kokoro-82M/voices').glob('*.pt')} == expected
    assert len(list((packed / 'assets/voice_previews').glob('*.wav'))) == 9
print('Final library: 9 approved voices, rejected voices blocked, payload contains only selected voices OK')
