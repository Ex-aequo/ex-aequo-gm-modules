# game-server — o servidor do jogo

Um servidor = um mundo. Serve:

| Caminho | O quê |
|---|---|
| `/` | cliente dos jogadores (`modules/player-client`, compilado) |
| `/gm/` | painel do mestre de jogo (`modules/gm-panel/frontend`, compilado), ligado ao jogo real |
| `/api/...` | API (FastAPI). `/api/map/...` são os ficheiros do mapa **filtrados por jogador** |

Base de dados: PostgreSQL (SQLAlchemy Core; o estado do jogo fica em JSONB). Contas com palavra-passe (scrypt) e
sessão por cookie httpOnly. O motor de turnos é `modules/turn-engine`.

## Arrancar no Mac

Precisa de PostgreSQL 16, Python 3.12 (ou `uv`), Node.js e um mundo gerado em `world-map/build/exemplo/data`.

```bash
brew install postgresql@16 node          # se ainda não estiverem
brew services start postgresql@16
export PATH="$(brew --prefix postgresql@16)/bin:$PATH"

cd modules/game-server
scripts/praga.sh setup     # base de dados, dependências, os dois frontends, jogo com 4 contas de teste
scripts/praga.sh start     # http://localhost:8000
```

`setup` **apaga o jogo anterior** e cria contas novas. Parar o servidor antes de o correr.
Depois de um `git pull`: `scripts/praga.sh build` e voltar a arrancar.

Contas criadas: `gm` / `praga-gm` e `jogador1..4` / `praga`. Cada jogador recebe o reino-guardião mais intacto.
Para testar vários jogadores ao mesmo tempo, usar janelas privadas ou browsers diferentes (a sessão é um cookie).

## Como corre um turno

- Os jogadores enviam ordens até o turno fechar; podem mudá-las quantas vezes quiserem. O servidor valida-as e
  guarda só as aceites (o cliente mostra as recusadas e porquê).
- O GM fecha o turno com **Resolver turno**, ou liga o **relógio** (o turno fecha sozinho de N em N minutos).
- Quem não envia ordens fica com as permanentes (os exércitos guarnecem). Reinos sem jogador são guardiões (bots).

## Nevoeiro no servidor (§8)

O jogador nunca recebe o que não conhece:
- `world.json`: regiões desconhecidas sem nome, centro nem vizinhos; burgos, rios e estradas só nas conhecidas; só
  as fações que conhece.
- `regions.png`: regiões desconhecidas apagadas. `base.jpg`: pergaminho fora de uma margem à volta do que conhece.
- tiles: só os que tocam regiões conhecidas (um tile pode mostrar geografia vizinha — aceite).

## Variáveis

| Variável | Por defeito |
|---|---|
| `PRAGA_DB` | `postgresql+psycopg://localhost/praga` |
| `PRAGA_WORLD` (só `praga.sh`) | `../world-map/build/exemplo/data` |
| `PRAGA_PLAYERS` (só `praga.sh`) | `4` |
| `PRAGA_SESSION_DAYS` | `14` |
| `PRAGA_COOKIE_SECURE` | `0` (pôr `1` com HTTPS) |

## Testes

Apagam a base indicada — usar uma só para testes:

```bash
createdb praga_test
PRAGA_TEST_DB=postgresql+psycopg://localhost/praga_test .venv/bin/python -m unittest tests.test_server
```

## Limites desta versão

- Sem registo de contas nem recuperação de palavra-passe: as contas são criadas por `scripts/new_game.py`.
- Um processo só (o relógio é uma thread). Chega para testes e para um mundo pequeno; não para alta escala.
- Sem HTTPS próprio: em produção, pôr atrás de um proxy (Caddy/nginx) e `PRAGA_COOKIE_SECURE=1`.
