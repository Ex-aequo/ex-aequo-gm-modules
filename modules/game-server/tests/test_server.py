"""Testes do servidor do jogo. APAGAM a base de dados indicada: usar uma base só para testes.

Correr a partir de modules/game-server:
    createdb praga_test
    PRAGA_TEST_DB=postgresql+psycopg://localhost/praga_test python -m unittest tests.test_server
Precisa de um mundo gerado (por defeito ../world-map/build/exemplo/data; ou PRAGA_TEST_WORLD).
Sem PRAGA_TEST_DB ou sem mundo, os testes são saltados.
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
WORLD = Path(os.environ.get("PRAGA_TEST_WORLD", HERE.parent / "world-map/build/exemplo/data"))
TEST_DB = os.environ.get("PRAGA_TEST_DB")
if TEST_DB:
    os.environ["PRAGA_DB"] = TEST_DB
sys.path.insert(0, str(HERE))

SKIP = None if TEST_DB and (WORLD / "world.json").exists() else "falta PRAGA_TEST_DB ou o mundo de teste"


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
        w = p.get("/api/map/world.json").json()
        named = {r["id"] for r in w["regions"] if r["name"]}
        self.assertEqual(named, known)                               # nem o nome das desconhecidas
        self.assertTrue(all(b["region"] in known for b in w["burgs"]))
        ids = {f["id"] for f in w["factions"]}
        self.assertNotIn(self.fids[1], ids - {f["id"] for f in st["map_factions"]})
        gm = self.client("gm", "segredo-gm").get("/api/map/world.json").json()
        self.assertGreater(len(gm["regions"]), len(known))
        self.assertTrue(all(r["name"] for r in gm["regions"]))

    def test_hidden_tiles_are_refused(self):
        from server.mapdata import get_mapdata
        g = self.app_mod.GAME
        md = get_mapdata(str(g.world_dir))
        if not md.tiles:
            self.skipTest("mundo sem tiles")
        known = g.known_regions(self.fids[0])
        hidden = next((z, k) for (z, k), regs in md.tile_regions.items() if regs and not regs & known)
        shown = next((z, k) for (z, k), regs in md.tile_regions.items() if regs & known)
        p = self.client("j1", "segredo")
        self.assertEqual(p.get(f"/api/map/tiles/{hidden[0]}/{hidden[1]}.webp").status_code, 404)
        self.assertEqual(p.get(f"/api/map/tiles/{shown[0]}/{shown[1]}.webp").status_code, 200)
        self.assertEqual(self.client("gm", "segredo-gm").get(f"/api/map/tiles/{hidden[0]}/{hidden[1]}.webp").status_code, 200)
        self.assertEqual(p.get("/api/map/tiles/0/..%2Fworld.json").status_code, 404)

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
