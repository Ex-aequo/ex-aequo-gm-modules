"""Testes do conversor Province-Forge → Praga. Correr a partir de modules/world-forge:
    python -m unittest tests.test_convert
"""
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "turn-engine"))
sys.path.insert(0, str(HERE.parent))

from forge.convert import praga_world  # noqa: E402
from praga import DEFAULT, FREE, WorldMap, new_game, resolve_turn  # noqa: E402
from praga.orders import build_cost  # noqa: E402

STATIC = json.loads((HERE / "fixture-static.json").read_text())


class ConvertTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.w = praga_world(STATIC, "Teste")
        cls.world = WorldMap(cls.w, DEFAULT)

    def test_ids_and_neighbours(self):
        land = [r for r in STATIC["regions"] if r["kind"] == "land"]
        self.assertEqual([r["id"] for r in self.w["regions"]], list(range(1, len(land) + 1)))
        ids = {r["id"] for r in self.w["regions"]}
        for r in self.w["regions"]:
            self.assertTrue(set(r["neighbors"]) <= ids, r["id"])
            self.assertNotIn(r["id"], r["neighbors"])
            for n in r["neighbors"]:                              # simétrico
                self.assertIn(r["id"], self.w["regions"][n - 1]["neighbors"])

    def test_kingdoms_from_starts(self):
        players = [s for s in STATIC["starts"] if not s["reserved"]]
        self.assertEqual(len(self.w["factions"]) - 1, len(players))   # as reservas não viram reinos
        for s in players:
            fid = s["slot"] + 1
            f = next(f for f in self.w["factions"] if f["id"] == fid)
            self.assertEqual(f["capital"], s["capital"] + 1)
            self.assertTrue(f["name"] and f["color"].startswith("#"))
            owned = [r["id"] for r in self.w["regions"] if r["owner"] == fid]
            self.assertEqual(sorted(owned), sorted(p + 1 for p in s["provinces"]))

    def test_sea_links_only_between_coastal(self):
        any_link = False
        for r in self.w["regions"]:
            for n in r["sea_links"]:
                any_link = True
                self.assertTrue(r["coastal"] and self.w["regions"][n - 1]["coastal"])
                self.assertNotIn(n, r["neighbors"])
        self.assertTrue(any_link)

    def test_engine_reads_terrain_and_resources(self):
        for rid, info in self.world.regions.items():
            raw = self.w["regions"][rid - 1]
            self.assertEqual(info.terrain, raw["terrain"])
            if raw["resource"] == "gold":
                self.assertIn("gold_mine", info.allowed_buildings)
            else:
                self.assertNotIn("gold_mine", info.allowed_buildings)
            if raw["resource"] == "grain":
                self.assertGreaterEqual(info.base["food"], 1 + raw["amount"])

    def test_stone_halves_fort_cost(self):
        state = new_game(self.world, DEFAULT, None, "t")
        stone = next((rid for rid, i in self.world.regions.items() if i.resource == "stone"), None)
        other = next(rid for rid, i in self.world.regions.items() if i.resource != "stone")
        if stone is None:
            self.skipTest("o mundo de teste não tem pedra")
        full, _ = build_cost(state, other, "fort", DEFAULT, self.world)
        half, _ = build_cost(state, stone, "fort", DEFAULT, self.world)
        self.assertEqual(half, {k: round(v / 2) for k, v in full.items()})

    def test_wrap_distance(self):
        W = self.world.wrap_width
        self.assertGreater(W, 0)
        a, b = (5.0, 100.0), (W - 5.0, 100.0)
        self.assertAlmostEqual(self.world.dist(a, b) * self.world.scale, 10.0)
        self.assertEqual(self.world.delta(a, b), (-10.0, 0.0))

    def test_game_runs(self):
        state = new_game(self.world, DEFAULT, None, "t")
        self.assertEqual(len(state.factions), len(self.w["factions"]) - 1)
        self.assertTrue(any(r.owner == FREE for r in state.regions.values()))
        for _ in range(5):
            state, _ev = resolve_turn(state, self.world, DEFAULT, {}, [])
        self.assertEqual(state.turn, 6)


if __name__ == "__main__":
    unittest.main()
