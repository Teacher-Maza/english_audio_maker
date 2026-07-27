# Execução, testes e build

## Escopo

Esta cópia é deliberadamente source-only. Ela não baixa dependências e não
contém runtime, modelos, FFmpeg, previews de voz, `.venv` ou Inno Setup.

## Ativos locais esperados para execução

Quando licenciados e verificados separadamente, os ativos devem respeitar os
caminhos relativos definidos em `config/paths.json`:

- `runtime/`: Python local com Tcl/Tk e pacotes compatíveis;
- `models/Kokoro-82M/`: modelo, configuração e voicepacks;
- `tools/ffmpeg.exe`: executável FFmpeg local;
- `audios/blind_english_voices_6u/`: 28 previews WAV referenciados pelo catálogo.

Esses itens são locais e permanecem ignorados pelo Git.

## Execução

Com os ativos locais presentes, use `ABRIR_INTERFACE_V2.bat`. O launcher define
o modo offline e inicia `app/main.py` usando o runtime local.

## Testes

`RODAR_SUITE_RC.bat` executa os testes mantidos em `tests/` usando o runtime
local. Alguns testes de interface exigem sessão gráfica; testes de áudio,
preview e integração exigem os ativos locais correspondentes. Os resultados e
temporários ficam sob `temp/`, que é ignorado.

## Empacotamento

As fontes estão em `installer/`. O fluxo atual pressupõe:

- ambiente `.venv/Lib/site-packages` compatível com `requirements.lock.txt`;
- Python base compatível com o build;
- modelos e voicepacks locais;
- `tools/ffmpeg.exe`;
- os 28 previews WAV;
- Inno Setup 6.7.3 em `tools/inno_setup_6_7_3/compiler/ISCC.exe`.

`installer/build_installer.py` monta o payload em `temp/` e
`installer/BUILD_INNO_RC.cmd` chama o compilador Inno. Nenhum desses passos
deve buscar dependências automaticamente.

## Bloqueio de distribuição

Esta exportação não contém `.venv`, ativos locais nem Inno Setup e não oferece
um instalador compilado. As fontes de empacotamento permanecem disponíveis para
manutenção, mas instaladores públicos não estão liberados.

Qualquer distribuição futura exige verificação jurídica e técnica das licenças,
avisos, código-fonte correspondente quando aplicável e conteúdo final do
payload.
