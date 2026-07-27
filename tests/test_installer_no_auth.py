from _rc_bootstrap import V2_ROOT

import ast


installer = V2_ROOT / "installer"
active_sources = [
    installer / "installer_bootstrap.py",
    installer / "build_installer.py",
    installer / "integration_test_installer.py",
    installer / "run_installed_backend_tests.py",
    installer / "EnglishAudioMakerV2_RC.iss",
    installer / "BUILD_INNO_RC.cmd",
    installer / "install.cmd",
]
combined = "\n".join(path.read_text(encoding="utf-8") for path in active_sources)

for forbidden in (
    "KeyValidator",
    "request_install_key",
    "needs_key",
    "key_saved",
    "_EXPECTED_DIGEST",
    "MAX_ATTEMPTS",
    "MAX_KEY_LENGTH",
    "simpledialog",
    "hmac.compare_digest",
    "Digite a chave",
    "Chave invalida",
    "Tentativas restantes",
    "Instalacao bloqueada",
):
    assert forbidden not in combined

bootstrap_tree = ast.parse(
    (installer / "installer_bootstrap.py").read_text(encoding="utf-8"),
    filename="installer_bootstrap.py",
)
assert not any(
    isinstance(node, ast.Call)
    and isinstance(node.func, ast.Attribute)
    and node.func.attr in {"askstring", "askopenfilename", "askyesno"}
    for node in ast.walk(bootstrap_tree)
)
assert "verify_payload(install_root)" in combined
assert "validate_locations(install_root, data_root" in combined
assert "install_payload(" in combined and "remove_installation(" in combined

print("Installer no-auth: no prompt, validator, secret storage or authentication messages; integrity preserved")
