# Avisos de terceiros

Este repositório source-only não inclui runtimes, modelos de voz, FFmpeg nem
outros binários de terceiros.

As dependências Python conhecidas estão fixadas em `requirements.lock.txt`.
Entre os componentes esperados pelo fluxo local estão Kokoro, PyTorch,
phonemizer-fork, Python, o modelo Kokoro-82M e FFmpeg. Cada componente conserva
sua própria licença, seus avisos e suas condições de redistribuição.

As fontes do instalador registram, com base no ambiente local usado pelo projeto:

- Python 3.12: Python Software Foundation License;
- Kokoro 0.9.4: indicação de Apache-2.0;
- modelo e voicepacks Kokoro-82M: indicação de Apache-2.0;
- PyTorch: licença de estilo BSD;
- phonemizer-fork: GPL-3.0;
- FFmpeg portátil configurado no projeto: build com GPL.

Essas indicações não substituem a conferência dos arquivos de licença de cada
versão efetivamente usada. O instalador só deve ser distribuído após gerar e
auditar os avisos completos e o SBOM do payload, além de cumprir obrigações de
redistribuição e oferta de código-fonte que forem aplicáveis.

O código próprio do English Audio Maker está sob a licença MIT, em `LICENSE`.
