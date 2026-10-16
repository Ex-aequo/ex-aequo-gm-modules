#!/usr/bin/env bash
# Servidor do jogo, num só comando (pensado para o Mac; também corre em Linux).
#
#   scripts/praga.sh setup     instala tudo, compila os dois frontends e cria o jogo de teste (APAGA o jogo anterior)
#   scripts/praga.sh start     arranca o servidor em http://localhost:8000
#   scripts/praga.sh build     só recompila os frontends (depois de um git pull)
#
# Variáveis opcionais:
#   PRAGA_DB       por defeito postgresql+psycopg://localhost/praga
#   PRAGA_WORLD    por defeito ../world-map/build/exemplo/data
#   PRAGA_PLAYERS  número de contas de teste (por defeito 4)
#   PORT           por defeito 8000
set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"
MODULES="$(dirname "$HERE")"
cd "$HERE"
export PRAGA_DB="${PRAGA_DB:-postgresql+psycopg://localhost/praga}"
WORLD="${PRAGA_WORLD:-$MODULES/world-map/build/exemplo/data}"
PLAYERS="${PRAGA_PLAYERS:-4}"
PORT="${PORT:-8000}"
PY="$HERE/.venv/bin/python"

die() { echo "erro: $*" >&2; exit 1; }

need_postgres() {
  command -v psql >/dev/null || die "não encontro o PostgreSQL. No Mac: brew install postgresql@16 && brew services start postgresql@16
       (e acrescentar ao PATH: export PATH=\"\$(brew --prefix postgresql@16)/bin:\$PATH\"), ou instalar a Postgres.app."
  pg_isready -q || die "o PostgreSQL não está a correr. No Mac: brew services start postgresql@16"
}

venv() {
  if [ ! -x "$PY" ]; then
    echo "» a criar o ambiente Python em game-server/.venv"
    if command -v uv >/dev/null; then uv venv --python 3.12 .venv; else python3 -m venv .venv; fi
  fi
  if command -v uv >/dev/null; then uv pip install --python "$PY" -q -r requirements.txt
  else "$PY" -m pip install -q -r requirements.txt; fi
}

build() {
  command -v npm >/dev/null || die "falta o Node.js (brew install node)"
  for d in "$MODULES/player-client" "$MODULES/gm-panel/frontend"; do
    echo "» a compilar $(basename "$(dirname "$d")")/$(basename "$d")"
    (cd "$d" && npm install --no-audit --no-fund --loglevel=error && npm run build >/dev/null)
  done
}

case "${1:-}" in
  setup)
    need_postgres
    [ -f "$WORLD/world.json" ] || die "não encontro o mundo em $WORLD (gera-o com world-map/tools/build_world.py ou define PRAGA_WORLD)"
    if [[ "$PRAGA_DB" == *"localhost/praga" ]]; then
      psql -lqt | cut -d'|' -f1 | grep -qw praga || { echo "» a criar a base de dados praga"; createdb praga; }
    fi
    venv
    build
    echo "» a criar o jogo"
    "$PY" scripts/new_game.py --world "$WORLD" --players "$PLAYERS" --reset
    echo
    echo "Pronto. Arranca com: scripts/praga.sh start"
    ;;
  build)
    build
    ;;
  start)
    need_postgres
    [ -x "$PY" ] || die "corre primeiro: scripts/praga.sh setup"
    echo "Jogadores: http://localhost:$PORT    GM: http://localhost:$PORT/gm/   (Ctrl+C para parar)"
    exec "$PY" -m uvicorn server.app:app --port "$PORT"
    ;;
  *)
    sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//'
    exit 1
    ;;
esac
