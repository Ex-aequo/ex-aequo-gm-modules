# ex-aequo-gm-modules

Ferramentas da Ex-Aequo Games para criar e gerir jogos de estratégia por turnos: mapas, mestre de jogo, narrativa.

Cada módulo vive em `modules/<nome>/` e tem o seu próprio README. Só há código partilhado quando dois módulos precisam
da mesma coisa (o primeiro caso: `map-renderer`).

## Módulos

| Módulo | Estado | O que faz |
|---|---|---|
| [world-map](modules/world-map/) | protótipo | Gerador de mundos: continentes, ilhas e mares à escolha, 25–150 reinos equilibrados, clima e nomes do Azgaar, base pintada determinística |
| [turn-engine](modules/turn-engine/) | protótipo | Motor de turnos determinístico (regras v0.6): nevoeiro de guerra, batedores, espiões, rumores, reinos-guardiões, ordens de GM e simulação |
| [map-renderer](modules/map-renderer/) | protótipo | Renderizador partilhado do mapa (WebGL2), usado pela demo do mapa e pelo painel do GM |
| [gm-panel](modules/gm-panel/) | protótipo | Painel do mestre de jogo em modo sandbox: FastAPI + React, controlo da Praga, rumores, pré-visualização, ver como jogador |

## Convenções

- **Dados gerados não entram no git.** Cada resultado tem de ser reproduzível a partir de código + configuração
  (por exemplo, `modules/world-map/worlds/*.toml`). Um mundo "oficial" congelado publica-se como release.
- **Sem IA generativa para assets.** O visual sai de código, dados e ferramentas determinísticas.
- Decisões de arquitetura registam-se em [docs/decisoes.md](docs/decisoes.md).
- Regras do jogo Praga (rascunho): [docs/regras-nucleo.md](docs/regras-nucleo.md). Resultados da simulação: [v0.2](docs/simulacao-v0.2.md), [v0.3](docs/simulacao-v0.3.md), [v0.4](docs/simulacao-v0.4.md), [v0.5 — nevoeiro](docs/simulacao-v0.5.md), [v0.6 — guardiões](docs/simulacao-v0.6.md).

## Licença

Proprietário — © Ex-Aequo Games. Ver [LICENSE](LICENSE) e [NOTICE](NOTICE) para componentes de terceiros.
