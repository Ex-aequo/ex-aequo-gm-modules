"""Cria (ou recria) o jogo: tabelas, mundo, conta do GM e contas de jogadores de teste.

Uso (a partir de modules/game-server):
    python scripts/new_game.py --generate --kingdoms 25 --players 4          gera um mundo novo e cria o jogo
    python scripts/new_game.py --world worlds/<pasta> --players 4            usa um mundo já gerado
Opções:
    --generate                        gera o mundo com o Province-Forge (precisa de Node e do CLI compilado)
      --kingdoms 25 --provinces 8 --share 0.3 --seed praga-1 --name Mundo --max-level 4
    --gm-user gm --gm-password …      conta do mestre de jogo (por defeito gm / praga-gm)
    --password …                      palavra-passe dos jogadores de teste (por defeito praga)
    --reset                           apaga tudo o que existe (contas incluídas) antes de criar
Cada jogador de teste (jogador1, jogador2, …) recebe o reino-guardião mais intacto, como um jogador real (§7).
O GM também pode criar mundos novos no painel (/gm/ → Novo mundo).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select  # noqa: E402

from server import auth, db  # noqa: E402
from server.game import Game  # noqa: E402
from server.worlds import JOBS  # noqa: E402


def generate(args) -> Path:
    params = {"playerSlots": args.kingdoms, "startProvinces": args.provinces, "startShare": args.share}
    job = JOBS.start(args.name, args.seed, params, args.max_level)
    print(f"a gerar o mundo «{args.name}» ({args.kingdoms} reinos) em {job['dir']}")
    last = None
    while True:
        st = JOBS.status()
        if (st["stage"], st["pct"] // 10) != last:
            last = (st["stage"], st["pct"] // 10)
            print(f"  {st['pct']:3d}% {st['stage']}", flush=True)
        if st["state"] != "running":
            break
        time.sleep(2)
    if st["state"] != "done":
        sys.exit(f"a geração falhou: {st['error']}")
    return Path(st["dir"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--world", help="pasta de um mundo gerado (bundle do Province-Forge com world.json)")
    ap.add_argument("--generate", action="store_true")
    ap.add_argument("--kingdoms", type=int, default=25)
    ap.add_argument("--provinces", type=int, default=8, help="províncias por reino")
    ap.add_argument("--share", type=float, default=0.3, help="território inicial (fração da terra)")
    ap.add_argument("--seed", default="praga-1")
    ap.add_argument("--name", default="Mundo de teste")
    ap.add_argument("--max-level", type=int, default=4)
    ap.add_argument("--players", type=int, default=4)
    ap.add_argument("--password", default="praga")
    ap.add_argument("--gm-user", default="gm")
    ap.add_argument("--gm-password", default="praga-gm")
    ap.add_argument("--reset", action="store_true")
    args = ap.parse_args()

    if args.reset:
        db.drop_all()
    db.create_all()
    with db.engine.begin() as conn:
        if conn.execute(select(db.users.c.id).limit(1)).first():
            sys.exit("já existem contas; usa --reset para apagar tudo e recomeçar")

    if args.generate:
        world = generate(args)
    elif args.world:
        world = Path(args.world)
    else:
        sys.exit("indica --world <pasta> ou --generate")
    if not (world / "world.json").exists():
        sys.exit(f"não encontro {world / 'world.json'}")

    g = Game.create(world, "s0")
    with db.engine.begin() as conn:
        auth.create_user(conn, args.gm_user, args.gm_password, "gm")
    w = json.loads((world / "world.json").read_text())
    print(f"mundo: {w['name']} · {len(g.state.factions)} reinos · {len(g.state.regions)} províncias")
    print(f"GM: {args.gm_user} / {args.gm_password}")
    for i in range(1, args.players + 1):
        fid = g.assign_kingdom()
        with db.engine.begin() as conn:
            auth.create_user(conn, f"jogador{i}", args.password, "player", fid)
        print(f"jogador{i} / {args.password} → {g.state.factions[fid].name} ({len(g.state.regions_of(fid))} províncias)")


if __name__ == "__main__":
    main()
