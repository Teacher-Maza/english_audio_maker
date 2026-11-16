# Avisos de terceiros

Este repositório source-only não inclui runtimes, modelos de voz, FFmpeg nem
outros binários de execução de terceiros. O instalador distribuído
separadamente inclui esses componentes.

A interface inclui Manrope Semibold (600), distribuída sob SIL Open Font
License 1.1. A licença acompanha a fonte em `app/ui/assets/fonts/OFL.txt`;
a origem está em `app/ui/assets/fonts/SOURCE.md`.

As dependências Python conhecidas estão fixadas em `requirements.lock.txt`.
Entre os componentes esperados pelo fluxo local estão Kokoro, PyTorch,
phonemizer-fork, Python, o modelo Kokoro-82M e FFmpeg. Cada componente conserva
sua própria licença, seus avisos e suas condições de redistribuição.

As fontes do instalador registram, com base no ambiente local usado pelo projeto:

- Python 3.12: Python Software Foundation License;
- Kokoro 0.9.4: indicação de Apache-2.0;
- modelo e voicepacks Kokoro-82M: indicação de Apache-2.0;
- PyTorch: conjunto de licenças declarado pelo pacote; os 107 textos da
  distribuição correspondente estão em `installer/legal/TORCH_LICENSES.txt`;
- phonemizer-fork: GPL-3.0;
- FFmpeg portátil configurado no projeto: build com GPL.

Fontes das versões incluídas: [FFmpeg 8.1.2 da Gyan](https://github.com/GyanD/codexffmpeg/releases/tag/8.1.2)
indica o [commit de origem do FFmpeg](https://github.com/FFmpeg/FFmpeg/commit/38b88335f9);
o [phonemizer-fork 3.3.2](https://pypi.org/project/phonemizer-fork/3.3.2/)
oferece uma distribuição de código-fonte (`.tar.gz`).

Essas indicações não substituem os textos de licença e o SBOM incluídos no
instalador. As condições de redistribuição de cada componente continuam
aplicáveis, inclusive o acesso ao código-fonte correspondente quando exigido.

O código próprio do English Audio Maker está sob a licença MIT, em `LICENSE`.
