# Execução, testes e build

## Escopo

Esta cópia é deliberadamente source-only. Ela não baixa dependências e não
contém runtime, modelos, FFmpeg, previews de voz nem Inno Setup.

## Ativos locais esperados para execução

Quando licenciados e verificados separadamente, os ativos devem respeitar os
caminhos relativos definidos em `config/paths.json`:

- `runtime/`: Python local com Tcl/Tk e pacotes compatíveis;
- `models/Kokoro-82M/`: modelo, configuração e voicepacks;
- `tools/ffmpeg.exe`: executável FFmpeg local;
- `audios/blind_english_voices_6u/`: 9 previews WAV referenciados pelo catálogo.

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

- `runtime/` local compatível com `requirements.lock.txt`, incluindo os pacotes
  necessários em `runtime/Lib/site-packages`;
- modelos e voicepacks locais;
- `tools/ffmpeg.exe`;
- os 9 previews WAV;
- Inno Setup 6 instalado localmente; o script também aceita a cópia verificada
  em `tools/inno_setup_6_7_3/compiler/ISCC.exe`.

`installer/build_installer.py` monta o payload em `temp/` e
`installer/BUILD_INNO_RC.cmd` chama o compilador Inno. Nenhum desses passos
deve buscar dependências automaticamente.

## Distribuição

Esta exportação não contém ativos locais nem Inno Setup. As fontes de
empacotamento permanecem disponíveis para manutenção. O instalador compilado
é distribuído separadamente na página de Releases do GitHub.

O instalador 2.0.0 existente foi validado em instalação limpa, mas não em
atualização sobre uma instalação antiga. Quem já possui uma versão anterior
deve desinstalá-la e conferir arquivos remanescentes antes de instalar a 2.0.0.

Os testes em Windows 10 e em outro computador com 8 GB ainda estão pendentes.
Os componentes de terceiros mantêm suas próprias licenças; consulte
`THIRD_PARTY_NOTICES.md` e os avisos incluídos no instalador.
