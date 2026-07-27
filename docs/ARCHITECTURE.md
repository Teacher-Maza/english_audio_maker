# Arquitetura mínima

`app/main.py` registra o pacote local, instala a proteção offline e inicia a
interface Tk. `app/ui/` contém a interface e o preview; `app/core/` concentra
parsing, geração, processamento, exportação, limites de recursos e integração
com FFmpeg/Kokoro; `app/security/` bloqueia acesso de rede no processo.

`config/paths.json` define somente caminhos relativos. Os modelos e binários
necessários são ativos locais ignorados. `installer/build_installer.py` cria um
payload por allowlist de configurações e gera manifesto, SBOM e avisos antes do
empacotamento Inno.

Dados gerados, logs seguros, cache e temporários devem permanecer em diretórios
ignorados e nunca fazer parte do repositório.
