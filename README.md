# ex-aequo-gm-modules

Ferramentas da Ex-Aequo Games para criar e gerir jogos de estratégia por turnos: mapas, mestre de jogo, narrativa.

Cada módulo vive em `modules/<nome>/` e tem o seu próprio README. O gerador de mapas é o
[Province-Forge](https://github.com/Ex-aequo/Province-Forge), incluído como submódulo em `vendor/province-forge`
(depois de clonar: `git submodule update --init`).

**Para jogar no Mac:** [modules/game-server](modules/game-server/) — `scripts/praga.sh setup` e `scripts/praga.sh start`.

## Módulos

| Módulo | Estado | O que faz |
|---|---|---|
| [game-server](modules/game-server/) | protótipo | Servidor do jogo: contas, ordens, turnos (à mão ou com relógio), mundos novos, nevoeiro aplicado no servidor (mapa e tiles) |
| [player-client](modules/player-client/) | protótipo | Frontend dos jogadores: mapa, todas as ordens, diplomacia, mensagens |
| [gm-panel](modules/gm-panel/) | protótipo | Painel do mestre de jogo (em `/gm/`): Praga, rumores, pré-visualização, ver como jogador, jogadores e relógio, novo mundo |
| [turn-engine](modules/turn-engine/) | protótipo | Motor de turnos determinístico (regras v0.6): nevoeiro, batedores, espiões, rumores, reinos-guardiões, ordens de GM, simulação |
| [world-forge](modules/world-forge/) | protótipo | Conversor do mapa do Province-Forge para o motor (reinos, terreno, recursos, ligações por mar) |
| [forge-view](modules/forge-view/) | protótipo | O mapa do Province-Forge com a camada do jogo (exércitos, agentes, setas), partilhado pelos dois frontends |

## Convenções

- **Dados gerados não entram no git.** Os mundos ficam em `modules/game-server/worlds/` (cada um guarda o mapa
  gerado, nunca só a semente: o gerador vai mudar). Um mundo "oficial" congelado publica-se como release.
- **Sem IA generativa para assets.** O visual sai de código, dados e ferramentas determinísticas.
- Decisões de arquitetura registam-se em [docs/decisoes.md](docs/decisoes.md).
- Regras do jogo Praga (rascunho): [docs/regras-nucleo.md](docs/regras-nucleo.md). Resultados da simulação: [v0.2](docs/simulacao-v0.2.md), [v0.3](docs/simulacao-v0.3.md), [v0.4](docs/simulacao-v0.4.md), [v0.5 — nevoeiro](docs/simulacao-v0.5.md), [v0.6 — guardiões](docs/simulacao-v0.6.md).

## Licença

Proprietário — © Ex-Aequo Games. Ver [LICENSE](LICENSE) e [NOTICE](NOTICE) para componentes de terceiros.
