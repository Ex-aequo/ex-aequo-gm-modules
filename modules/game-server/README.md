# game-server — o servidor do jogo

Um servidor = um mundo. Serve:

| Caminho | O quê |
|---|---|
| `/` | cliente dos jogadores (`modules/player-client`, compilado) |
| `/gm/` | painel do mestre de jogo (`modules/gm-panel/frontend`, compilado), ligado ao jogo real |
| `/api/...` | API (FastAPI). `/api/map/...` é o mapa do Province-Forge (client map e tiles), **filtrado por jogador** |

Base de dados: PostgreSQL (SQLAlchemy Core; o estado do jogo fica em JSONB). Contas com palavra-passe (scrypt) e
sessão por cookie httpOnly. O motor de turnos é `modules/turn-engine`.

## Arrancar no Mac

Precisa de PostgreSQL 16, Python 3.12 (ou `uv`) e Node.js 20+. O gerador de mundos é o Province-Forge, submódulo em
`vendor/province-forge` (o `setup` vai buscá-lo e compila-o).

```bash
brew install postgresql@16 node          # se ainda não estiverem
brew services start postgresql@16
export PATH="$(brew --prefix postgresql@16)/bin:$PATH"

cd modules/game-server
scripts/praga.sh setup     # base de dados, dependências, Province-Forge, frontends, mundo de 25 reinos, 4 contas
scripts/praga.sh start     # http://localhost:8000
```

`setup` **apaga o jogo anterior** e cria contas novas. Parar o servidor antes de o correr. O mundo de teste demora uns
minutos (o relevo em tiles); `PRAGA_KINGDOMS=50 scripts/praga.sh setup` para outro tamanho.
Depois de um `git pull`: `git submodule update --init`, `scripts/praga.sh build` e voltar a arrancar.

## Mundos novos

No painel do GM, **Novo mundo**: controlos e pré-visualização no browser, depois "Criar" (o servidor corre o gerador
do Province-Forge em segundo plano e mostra o progresso) e "Começar um jogo neste mundo" (apaga o jogo atual; cada
conta de jogador recebe um reino do mundo novo). Os mundos ficam em `game-server/worlds/` (`PRAGA_WORLDS`).
Por script: `python scripts/new_game.py --generate --kingdoms 50 --players 4 --reset`.

Contas criadas: `gm` / `praga-gm` e `jogador1..4` / `praga`. Cada jogador recebe o reino-guardião mais intacto.
Para testar vários jogadores ao mesmo tempo, usar janelas privadas ou browsers diferentes (a sessão é um cookie).

## Como corre um turno

- Os jogadores enviam ordens até o turno fechar; podem mudá-las quantas vezes quiserem. O servidor valida-as e
  guarda só as aceites (o cliente mostra as recusadas e porquê).
- O GM fecha o turno com **Resolver turno**, ou liga o **relógio** (o turno fecha sozinho de N em N minutos).
- Quem não envia ordens fica com as permanentes (os exércitos guarnecem). Reinos sem jogador são guardiões (bots).

## Nevoeiro no servidor (§8)

O jogador nunca recebe o que não conhece:
- client map: só a geometria, o nome e o terreno das províncias que conhece (e do mar, lagos e gelo que lhes tocam);
  o resto não existe no browser (filtro do Province-Forge, `filter_client_map`).
- tiles: pintados de cinzento fora do que conhece, tile a tile (um tile sem nada conhecido é só cinzento); guardados
  em memória por jogador e turno. O URL leva o turno, para o browser não reutilizar tiles antigos.
- vista (`viewer` em `/api/player/state`): donos e Praga só das províncias que conhece, a partir das fotografias do
  motor; as que só conhece de uma vista antiga aparecem com um véu.

## Variáveis

| Variável | Por defeito |
|---|---|
| `PRAGA_DB` | `postgresql+psycopg://localhost/praga` |
| `PRAGA_WORLDS` | `game-server/worlds` |
| `PRAGA_KINGDOMS` (só `praga.sh`) | `25` |
| `PRAGA_PLAYERS` (só `praga.sh`) | `4` |
| `PRAGA_SESSION_DAYS` | `14` |
| `PRAGA_COOKIE_SECURE` | `0` (pôr `1` com HTTPS) |

## Testes

Apagam a base indicada — usar uma só para testes. Geram um mundo pequeno com o Province-Forge (precisa do CLI
compilado):

```bash
createdb praga_test
PRAGA_TEST_DB=postgresql+psycopg://localhost/praga_test .venv/bin/python -m unittest tests.test_server
```

## Limites desta versão

- Sem registo de contas nem recuperação de palavra-passe: as contas são criadas por `scripts/new_game.py`.
- Um processo só (o relógio é uma thread). Chega para testes e para um mundo pequeno; não para alta escala.
- Sem HTTPS próprio: em produção, pôr atrás de um proxy (Caddy/nginx) e `PRAGA_COOKIE_SECURE=1`.
