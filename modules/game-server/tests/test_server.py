"""Testes do servidor do jogo. APAGAM a base de dados indicada: usar uma base só para testes.

Correr a partir de modules/game-server:
    createdb praga_test
    PRAGA_TEST_DB=postgresql+psycopg://localhost/praga_test python -m unittest tests.test_server
Gera um mundo pequeno com o Province-Forge (precisa de Node e do CLI compilado em vendor/province-forge:
npm ci && npm run build:cli), ou usa PRAGA_TEST_WORLD (pasta de um mundo já gerado).
Sem PRAGA_TEST_DB ou sem mundo, os testes são saltados.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
CLI = HERE.parents[1] / "vendor/province-forge/build/cli/mapgen.js"
TEST_DB = os.environ.get("PRAGA_TEST_DB")
if TEST_DB:
    os.environ["PRAGA_DB"] = TEST_DB
sys.path.insert(0, str(HERE))


def _world() -> Path | None:
    if os.environ.get("PRAGA_TEST_WORLD"):
        return Path(os.environ["PRAGA_TEST_WORLD"])
    if not TEST_DB or not CLI.exists() or not shutil.which("node"):
        return None
    out = Path(tempfile.mkdtemp(prefix="praga-test-world-")) / "w"
    params = out.parent / "p.json"
    params.write_text(json.dumps({"autoScale": True, "playerSlots": 10, "reserveSlots": 0, "startProvinces": 5,
                                  "startShare": 0.3, "valueTolerance": 0.2}))
    subprocess.run(["node", str(CLI), "create", "--seed", "teste", "--out", str(out), "--params", str(params),
                    "--max-level", "1"], check=True, capture_output=True)
    sys.path.insert(0, str(HERE.parent / "world-forge"))
    from forge.convert import praga_world
    (out / "world.json").write_text(json.dumps(praga_world(json.loads((out / "static-map.json").read_text()), "Teste")))
    return out


WORLD = _world()
SKIP = None if TEST_DB and WORLD and (WORLD / "world.json").exists() else "falta PRAGA_TEST_DB, Node ou o mundo de teste"


@unittest.skipIf(SKIP, SKIP or "")
class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient

        from server import app as app_mod, auth, db
        from server.game import Game
        db.drop_all()
        db.create_all()
        g = Game.create(WORLD, "t")
        with db.engine.begin() as conn:
            auth.create_user(conn, "gm", "segredo-gm", "gm")
        cls.fids = []
        for i in (1, 2):
            fid = g.assign_kingdom()
            cls.fids.append(fid)
            with db.engine.begin() as conn:
                auth.create_user(conn, f"j{i}", "segredo", "player", fid)
        app_mod.GAME.reload()
        cls.app_mod = app_mod
        cls.TestClient = TestClient

    def client(self, user=None, pw=None):
        c = self.TestClient(self.app_mod.app)
        if user:
            r = c.post("/api/login", json={"username": user, "password": pw})
            self.assertEqual(r.status_code, 200, r.text)
        return c

    # ------------------------------------------------------------------ contas
    def test_login_and_roles(self):
        self.assertEqual(self.client().get("/api/player/state").status_code, 401)
        self.assertEqual(self.client().post("/api/login", json={"username": "j1", "password": "x"}).status_code, 401)
        p = self.client("j1", "segredo")
        me = p.get("/api/me").json()
        self.assertEqual((me["role"], me["faction"]), ("player", self.fids[0]))
        self.assertEqual(p.get("/api/gm/state").status_code, 403)
        g = self.client("gm", "segredo-gm")
        self.assertEqual(g.get("/api/player/state").status_code, 403)
        self.assertEqual(g.get("/api/gm/state").json()["mode"], "game")
        p.post("/api/logout")
        self.assertEqual(p.get("/api/me").status_code, 401)

    # ------------------------------------------------------------------ nevoeiro no servidor
    def test_player_map_is_filtered(self):
        p = self.client("j1", "segredo")
        st = p.get("/api/player/state").json()
        known = {int(k) for k in st["regions"]}
        cm = p.get("/api/map/client-map.json").json()
        self.assertTrue(cm["partial"])
        land = {r["id"] + 1 for r in cm["regions"] if r and r["kind"] == "land"}
        self.assertEqual(land, known)                       # só a geometria (e o nome) das províncias que conhece
        self.assertTrue({r - 1 for r in known} <= set(st["viewer"]["visible"]))     # vista em ids do Province-Forge
        gm = self.client("gm", "segredo-gm").get("/api/map/client-map.json").json()
        self.assertFalse(gm.get("partial"))
        self.assertGreater(sum(1 for r in gm["regions"] if r and r["kind"] == "land"), len(known))

    def test_tiles_are_masked(self):
        from server.forgemap import get_forgemap
        g = self.app_mod.GAME
        fm = get_forgemap(str(g.world_dir))
        vis = fm.visible_pf(g.known_regions(self.fids[0]))
        p = self.client("j1", "segredo")
        gm = self.client("gm", "segredo-gm")
        hidden = shown = None
        for tx in range(4):
            for ty in range(2):
                regs = fm.tile_regions(1, tx, ty)
                if regs and not regs & vis and hidden is None:
                    hidden = (tx, ty)
                if regs & vis and shown is None:
                    shown = (tx, ty)
        self.assertIsNotNone(hidden)
        grey = fm.grey_tile()
        self.assertEqual(p.get(f"/api/map/t1/tiles/1/{hidden[0]}/{hidden[1]}.webp").content, grey)
        self.assertNotEqual(gm.get(f"/api/map/gm/tiles/1/{hidden[0]}/{hidden[1]}.webp").content, grey)
        self.assertEqual(p.get(f"/api/map/t1/tiles/1/{shown[0]}/{shown[1]}.webp").status_code, 200)
        self.assertEqual(p.get("/api/map/t1/tiles/9/0/0.webp").status_code, 404)

    # ------------------------------------------------------------------ ordens e turno
    def test_orders_validated_stored_and_resolved(self):
        p = self.client("j2", "segredo")
        st = p.get("/api/player/state").json()
        army = st["armies"][0]
        home = army["region"]
        r = p.put("/api/player/orders", json={"orders": [
            {"type": "recruit", "region": home, "men": 100},
            {"type": "recruit", "region": 999999, "men": 100},
            {"type": "garrison", "army": army["id"]},
        ]}).json()
        self.assertEqual(len(r["accepted"]), 2)
        self.assertEqual(len(r["errors"]), 1)
        self.assertEqual(p.get("/api/player/state").json()["orders"], r["accepted"])
        g = self.client("gm", "segredo-gm")
        players = {x["username"]: x for x in g.get("/api/gm/state").json()["players"]}
        self.assertTrue(players["j2"]["submitted"])
        turn = st["clock"]["turn"]
        self.assertEqual(g.post("/api/gm/turn").status_code, 200)
        st2 = p.get("/api/player/state").json()
        self.assertEqual(st2["clock"]["turn"], turn + 1)
        self.assertEqual(st2["orders"], [])
        self.assertEqual(sum(a["men"] for a in st2["armies"]), sum(a["men"] for a in st["armies"]) + 100)

    def test_timer(self):
        g = self.client("gm", "segredo-gm")
        s = g.post("/api/gm/timer", json={"minutes": 30}).json()
        self.assertEqual(s["timer_minutes"], 30)
        self.assertIsNotNone(s["deadline"])
        p = self.client("j1", "segredo").get("/api/player/state").json()
        self.assertEqual(p["clock"]["deadline"], s["deadline"])
        s = g.post("/api/gm/timer", json={"minutes": 0}).json()
        self.assertIsNone(s["deadline"])


if __name__ == "__main__":
    unittest.main()
