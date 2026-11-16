# English Audio Maker

Aplicativo offline para Windows que transforma textos em inglês em arquivos de
áudio.

## Modos disponíveis

- **Narração:** usa uma voz para ler um texto contínuo.
- **Conversação A/B:** alterna duas vozes em falas iniciadas por `A:` ou `B:`.

## Vozes e entonação

Biblioteca selecionada: Heart, Bella, Emma, Aoede, Fenrir, Puck, George, Lewis e Echo.
O Kokoro pode produzir perguntas com entonação neutra ou inadequada à intenção.
Interrogação e contexto não garantem expressividade. Para ensino de inglês,
revise o áudio antes de usá-lo como exemplo de entonação. Não há correção artificial de tom.

## Repositório source-only

Este repositório contém código-fonte, configurações públicas, testes, fontes do
instalador e documentação. Ele não inclui modelos, runtime Python, FFmpeg,
áudios de preview nem instalador compilado.

Um ambiente local completo é necessário para executar, testar ou empacotar o
aplicativo a partir do código-fonte. Os ativos precisam ser obtidos
separadamente. Consulte [BUILD.md](BUILD.md). O instalador para usuários fica
na página de [Releases](https://github.com/Teacher-Maza/english_audio_maker/releases).

## Colaboração

Projeto idealizado e coordenado pelo PROJETO VTS. Implementação realizada com assistência de ferramentas de inteligência artificial.

Contribuições técnicas, revisões e melhorias da comunidade são bem-vindas.

Antes de colaborar, leia [CONTRIBUTING.md](CONTRIBUTING.md) e
[SECURITY.md](SECURITY.md).

## Instalação da versão 2.0.0

O instalador é oferecido separadamente na página de Releases do GitHub; ele
não faz parte deste repositório. É destinado a Windows 10 ou 11 de 64 bits.

Se você já instalou uma versão anterior, desinstale-a pelo Windows antes de
executar o instalador 2.0.0. Não instale por cima de uma pasta antiga: arquivos
remanescentes podem fazer a validação falhar. Se a pasta de instalação ainda
contiver arquivos após a desinstalação, pare e confira o que há nela antes de
remover qualquer coisa. Preserve seus áudios e configurações.

O instalador não tem assinatura digital. Não desative o antivírus para instalá-lo.
Confira o nome e o SHA-256 informados na Release antes de executar o arquivo.

## Termos e licenças

Os termos públicos estão em [TERMS_OF_USE.md](TERMS_OF_USE.md). O código próprio
usa a licença MIT, disponível em [LICENSE](LICENSE). Componentes de terceiros
continuam sujeitos às próprias licenças; consulte
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
