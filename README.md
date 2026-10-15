# ex-aequo-gm-modules

Ferramentas da Ex-Aequo Games para criar e gerir jogos de estratégia por turnos: mapas, mestre de jogo, narrativa.

Cada módulo vive em `modules/<nome>/`, é independente e tem o seu próprio README. Não há código partilhado entre
módulos até dois deles precisarem da mesma coisa.

## Módulos

| Módulo | Estado | O que faz |
|---|---|---|
| [world-map](modules/world-map/) | protótipo | Mapa-mundo a partir de dados Azgaar: base pintada determinística, regiões jogáveis, fronteiras e Praga em WebGL2 |

## Convenções

- **Dados gerados não entram no git.** Cada resultado tem de ser reproduzível a partir de código + configuração
  (por exemplo, `modules/world-map/worlds/*.toml`). Um mundo "oficial" congelado publica-se como release.
- **Sem IA generativa para assets.** O visual sai de código, dados e ferramentas determinísticas.
- Decisões de arquitetura registam-se em [docs/decisoes.md](docs/decisoes.md).
- Regras do jogo Praga (rascunho): [docs/regras-nucleo.md](docs/regras-nucleo.md).

## Licença

Proprietário — © Ex-Aequo Games. Ver [LICENSE](LICENSE) e [NOTICE](NOTICE) para componentes de terceiros.
