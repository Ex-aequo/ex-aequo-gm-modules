"""Cria (ou recria) o jogo: tabelas, mundo, conta do GM e contas de jogadores de teste.

Uso (a partir de modules/game-server):
    python scripts/new_game.py --world ../world-map/build/exemplo/data --players 4
Opções:
    --gm-user gm --gm-password …      conta do mestre de jogo (por defeito gm / praga-gm)
    --password …                      palavra-passe dos jogadores de teste (por defeito praga)
    --seed s0                         semente do acaso do motor
    --reset                           apaga tudo o que existe (contas incluídas) antes de criar
Cada jogador de teste (jogador1, jogador2, …) recebe o reino-guardião mais intacto, como um jogador real (§7).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select  # noqa: E402

from server import auth, db  # noqa: E402
from server.game import Game  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--world", required=True, help="pasta com world.json, regions.png, base.jpg (e tiles/)")
    ap.add_argument("--players", type=int, default=4)
    ap.add_argument("--password", default="praga")
    ap.add_argument("--gm-user", default="gm")
    ap.add_argument("--gm-password", default="praga-gm")
    ap.add_argument("--seed", default="s0")
    ap.add_argument("--reset", action="store_true")
    args = ap.parse_args()
    world = Path(args.world)
    if not (world / "world.json").exists():
        sys.exit(f"não encontro {world / 'world.json'}")

    if args.reset:
        db.drop_all()
    db.create_all()
    with db.engine.begin() as conn:
        if conn.execute(select(db.users.c.id).limit(1)).first():
            sys.exit("já existem contas; usa --reset para apagar tudo e recomeçar")
    g = Game.create(world, args.seed)
    with db.engine.begin() as conn:
        auth.create_user(conn, args.gm_user, args.gm_password, "gm")
    print(f"mundo: {g.raw_world.get('name')} · {len(g.state.factions)} reinos · {len(g.state.regions)} regiões")
    print(f"GM: {args.gm_user} / {args.gm_password}")
    for i in range(1, args.players + 1):
        fid = g.assign_kingdom()
        with db.engine.begin() as conn:
            auth.create_user(conn, f"jogador{i}", args.password, "player", fid)
        print(f"jogador{i} / {args.password} → {g.state.factions[fid].name} ({len(g.state.regions_of(fid))} regiões)")


if __name__ == "__main__":
    main()
