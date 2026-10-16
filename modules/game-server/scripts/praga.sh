#!/usr/bin/env bash
# Servidor do jogo, num só comando (pensado para o Mac; também corre em Linux).
#
#   scripts/praga.sh setup     instala tudo, compila, gera um mundo de 25 reinos e cria o jogo de teste
#                              (APAGA o jogo anterior e as contas)
#   scripts/praga.sh start     arranca o servidor em http://localhost:8000
#   scripts/praga.sh build     só recompila (depois de um git pull)
#
# Variáveis opcionais:
#   PRAGA_DB        por defeito postgresql+psycopg://localhost/praga
#   PRAGA_KINGDOMS  reinos do mundo de teste (por defeito 25)
#   PRAGA_PLAYERS   número de contas de teste (por defeito 4)
#   PORT            por defeito 8000
set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"
MODULES="$(dirname "$HERE")"
cd "$HERE"
export PRAGA_DB="${PRAGA_DB:-postgresql+psycopg://localhost/praga}"
KINGDOMS="${PRAGA_KINGDOMS:-25}"
PF="$(dirname "$MODULES")/vendor/province-forge"
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
  command -v npm >/dev/null || die "falta o Node.js 20 ou mais recente (brew install node)"
  if [ ! -f "$PF/package.json" ]; then
    echo "» a buscar o Province-Forge (submódulo)"
    git -C "$(dirname "$MODULES")" submodule update --init
  fi
  echo "» a compilar o Province-Forge (gerador de mundos)"
  (cd "$PF" && npm ci --no-audit --no-fund --loglevel=error && npm run -s build:cli)
  for d in "$MODULES/player-client" "$MODULES/gm-panel/frontend"; do
    echo "» a compilar $(basename "$(dirname "$d")")/$(basename "$d")"
    (cd "$d" && npm install --no-audit --no-fund --loglevel=error && npm run build >/dev/null)
  done
}

case "${1:-}" in
  setup)
    need_postgres
    if [[ "$PRAGA_DB" == *"localhost/praga" ]]; then
      psql -lqt | cut -d'|' -f1 | grep -qw praga || { echo "» a criar a base de dados praga"; createdb praga; }
    fi
    venv
    build
    echo "» a gerar um mundo de $KINGDOMS reinos e a criar o jogo (o relevo demora uns minutos)"
    "$PY" scripts/new_game.py --generate --kingdoms "$KINGDOMS" --name "Mundo de teste" --seed "praga-$RANDOM" \
      --players "$PLAYERS" --reset
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
