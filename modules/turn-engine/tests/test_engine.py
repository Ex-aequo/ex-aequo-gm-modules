"""Testes do motor. Correr a partir de modules/turn-engine:
    python -m unittest discover -s tests      (mundo de teste: tests/fixtures/world.json, Province-Forge, 25 reinos)
"""
import math
import os
import unittest
from pathlib import Path

from praga.state import land_distances
from praga import DEFAULT, FREE, PRAGA, WorldMap, add_faction, new_game, resolve_turn, validate
from praga.bots import STYLES, bot_orders

WORLD = Path(os.environ.get("PRAGA_WORLD", Path(__file__).resolve().parent / "fixtures/world.json"))


@unittest.skipUnless(WORLD.exists(), f"falta {WORLD}")
class EngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = WorldMap.load(WORLD, DEFAULT)

    def fresh(self):
        return new_game(self.world, DEFAULT, "small")

    def run_turns(self, n):
        s = self.fresh()
        fids = sorted(s.factions)
        for _ in range(n):
            orders = {f: bot_orders(s, self.world, DEFAULT, f, STYLES[i % 3]) for i, f in enumerate(fids)
                      if s.factions[f].active}
            s, _ = resolve_turn(s, self.world, DEFAULT, orders)
        return s

    def test_deterministic(self):
        self.assertEqual(self.run_turns(15).digest(), self.run_turns(15).digest())

    def test_state_roundtrip(self):
        from praga.state import GameState
        s, _, _ = self.with_focus()
        self.assertEqual(GameState.from_dict(s.to_dict()).digest(), s.digest())

    def test_resolve_does_not_mutate_input(self):
        s = self.fresh()
        before = s.digest()
        resolve_turn(s, self.world, DEFAULT, {})
        self.assertEqual(before, s.digest())

    def test_neighbors_symmetric(self):
        for rid, info in self.world.regions.items():
            for n in info.neighbors:
                self.assertIn(rid, self.world.regions[n].neighbors)

    def test_command_points_formula(self):
        s = self.fresh()
        fid = sorted(s.factions)[0]
        n = len(s.regions_of(fid))
        self.assertEqual(s.command_points(fid, DEFAULT), int(4 + 2 * math.sqrt(n)))

    def test_cannot_attack_without_hostile_posture(self):
        s = self.fresh()
        a = next(iter(s.armies.values()))
        # inventar um vizinho de outra fação
        tgt = self.world.regions[a.region].neighbors[0]
        other = next(f for f in s.factions if f != a.owner)
        s.regions[tgt].owner = other
        acc, errs = validate(s, self.world, DEFAULT, a.owner, [{"type": "attack", "army": a.id, "target": tgt}])
        self.assertFalse(acc)
        self.assertIn("Hostis", errs[0])
        acc, errs = validate(s, self.world, DEFAULT, a.owner, [
            {"type": "posture", "faction": other, "value": "hostile"},
            {"type": "attack", "army": a.id, "target": tgt}])
        self.assertEqual(len(acc), 2, errs)

    def test_command_points_limit(self):
        s = self.fresh()
        fid = sorted(s.factions)[0]
        rid = s.regions_of(fid)[0]
        s.factions[fid].stock = {k: 10_000 for k in s.factions[fid].stock}
        many = [{"type": "recruit", "region": r, "men": 10} for r in s.regions_of(fid)] * 10
        acc, errs = validate(s, self.world, DEFAULT, fid, many)
        self.assertLessEqual(len(acc), s.command_points(fid, DEFAULT))
        self.assertTrue(errs)

    def test_one_production_building_per_region(self):
        s = self.fresh()
        fid = sorted(s.factions)[0]
        rid = next(r for r in s.regions_of(fid) if self.world.regions[r].allowed_buildings)
        s.regions[rid].building, s.regions[rid].level = self.world.regions[rid].allowed_buildings[0], 1
        s.factions[fid].stock = {k: 1000 for k in s.factions[fid].stock}
        what = self.world.regions[rid].allowed_buildings[0]
        acc, errs = validate(s, self.world, DEFAULT, fid, [{"type": "build", "region": rid, "what": what}])
        self.assertFalse(acc)
        acc, _ = validate(s, self.world, DEFAULT, fid, [{"type": "build", "region": rid, "what": "upgrade"}])
        self.assertEqual(len(acc), 1)

    def test_inactivity_regency_then_guardian(self):
        s = self.fresh()
        fid = sorted(s.factions)[0]
        for _ in range(DEFAULT.dissolve_after + 1):
            s, ev = resolve_turn(s, self.world, DEFAULT, {})
        f = s.factions[fid]
        self.assertTrue(f.active, "um reino abandonado não desaparece")
        self.assertEqual(f.controller, "bot")
        self.assertTrue(s.regions_of(fid))

    def test_guardians_never_attack_kingdoms(self):
        from praga.bots import guardian_orders
        s = new_game(self.world, DEFAULT, "small", players=set())       # todos guardiões
        for _ in range(25):
            for fid in sorted(s.factions):
                for o in guardian_orders(s, self.world, DEFAULT, fid):
                    self.assertNotEqual(o["type"], "posture")
                    if o["type"] == "attack":
                        self.assertIn(s.regions[o["target"]].owner, (FREE, PRAGA))
            s, ev = resolve_turn(s, self.world, DEFAULT, {})
            self.assertFalse([e for e in ev if e[0] == "conquest" and e[3] not in (FREE, PRAGA)])
        self.assertGreater(sum(len(s.regions_of(f)) for f in s.factions), 3 * len(s.factions), "guardiões expandem")

    def test_submitted_orders_for_guardians_are_ignored(self):
        s = new_game(self.world, DEFAULT, "small", players=set())
        fid = sorted(s.factions)[0]
        a = s.armies_of(fid)[0]
        bogus = {fid: [{"type": "recruit", "region": s.regions_of(fid)[0], "men": 200}] * 1}
        t, _ = resolve_turn(s, self.world, DEFAULT, bogus)
        u, _ = resolve_turn(s, self.world, DEFAULT, {})
        self.assertEqual(t.digest(), u.digest())
        self.assertTrue(a)

    def test_newcomer_gets_most_intact_guardian(self):
        from praga import claim_kingdom
        players = set(sorted(self.world.factions)[1:5])
        s = new_game(self.world, DEFAULT, "small", players=players)
        bots = [f for f in s.factions if s.factions[f].controller == "bot"]
        fid = claim_kingdom(s, self.world, DEFAULT, "Recém-chegado")
        self.assertIn(fid, bots)
        f = s.factions[fid]
        self.assertEqual((f.controller, f.name), ("player", "Recém-chegado"))
        self.assertGreaterEqual(f.protected_until, s.turn)
        self.assertEqual(len(s.regions_of(fid)), max(len(s.regions_of(b)) for b in bots))
        s2 = new_game(self.world, DEFAULT, "small")
        self.assertIsNone(claim_kingdom(s2, self.world, DEFAULT), "sem guardiões não há reino para dar")

    def test_late_entry_is_protected_and_isolated(self):
        s = self.fresh()
        rid = add_faction(s, self.world, DEFAULT, 100, "Teste")
        self.assertIsNotNone(rid)
        self.assertEqual(s.regions[rid].plague, 0)
        f = s.factions[100]
        self.assertGreaterEqual(f.protected_until, s.turn)
        for n in self.world.regions[rid].neighbors:
            self.assertIn(s.regions[n].owner, (FREE, PRAGA, 100))

    def test_foci_within_band_from_capitals(self):
        s = self.fresh()
        self.assertEqual(len(s.foci), DEFAULT.plague_foci)
        caps = [self.world.regions[s.armies_of(f)[0].region].center for f in s.factions]
        reach = land_distances(self.world, [s.armies_of(f)[0].region for f in s.factions])
        dcap = {r: min(self.world.dist(self.world.regions[r].center, c) for c in caps) for r in reach}
        # num mundo com as capitais espalhadas por igual (Province-Forge) pode não haver terra a foci_min_dist de
        # todas: aí os focos ficam na terra mais afastada (sempre acima da mediana)
        floor = min(DEFAULT.foci_min_dist, sorted(dcap.values())[len(dcap) // 2])
        for rid in s.foci:
            self.assertGreaterEqual(dcap[rid], floor)

    def test_every_faction_starts_with_iron(self):
        s = self.fresh()
        for fid in s.factions:
            iron = sum(self.world.regions[r].base["iron"] + s.regions[r].iron_bonus for r in s.regions_of(fid))
            self.assertGreater(iron, 0, s.factions[fid].name)

    def test_well_governed_region_recedes(self):
        s = self.fresh()
        fid = sorted(s.factions)[0]
        rid = s.regions_of(fid)[0]
        s.regions[rid].plague, s.regions[rid].order = 20, 3
        s2, _ = resolve_turn(s, self.world, DEFAULT, {fid: []})
        self.assertLess(s2.regions[rid].plague, 20)

    # ------------------------------------------------------------- Praga como evento do GM (§6.1)
    def with_focus(self):
        s = self.fresh()
        focus = s.foci[0]
        s, ev = resolve_turn(s, self.world, DEFAULT, {}, [{"type": "plague_state", "value": "active"},
                                                          {"type": "plague_focus", "region": focus}])
        return s, focus, ev

    def test_plague_starts_dormant_without_foci(self):
        s = self.fresh()
        self.assertFalse(s.plague_active)
        self.assertFalse([r for r in s.regions.values() if r.owner == PRAGA or r.plague])

    def test_gm_focus_and_activation(self):
        s, focus, ev = self.with_focus()
        self.assertTrue(s.plague_active)
        self.assertEqual(s.regions[focus].owner, PRAGA)
        self.assertTrue(any(e[0] == "gm" and "desperta" in e[2] for e in ev))

    def test_gm_invalid_orders_are_rejected(self):
        from praga.engine import validate_gm
        s = self.fresh()
        acc, errs = validate_gm(s, self.world, DEFAULT, [{"type": "plague_state", "value": "on"},
                                                         {"type": "plague_intensity", "value": "extreme"},
                                                         {"type": "plague_focus", "region": 10 ** 6}])
        self.assertEqual(acc, [])
        self.assertEqual(len(errs), 3)

    def test_dormant_plague_does_not_grow_or_spread(self):
        s, focus, _ = self.with_focus()
        s, _ = resolve_turn(s, self.world, DEFAULT, {}, [{"type": "plague_state", "value": "dormant"}])
        before = {rid: r.plague for rid, r in s.regions.items()}
        for _ in range(5):
            s, _ = resolve_turn(s, self.world, DEFAULT, {})
        for rid, r in s.regions.items():
            if r.owner != PRAGA:
                self.assertLessEqual(r.plague, before[rid])

    def test_purge_works_while_dormant(self):
        s, focus, _ = self.with_focus()
        s, _ = resolve_turn(s, self.world, DEFAULT, {}, [{"type": "plague_state", "value": "dormant"}])
        nb = self.world.regions[focus].neighbors[0]
        fid = sorted(s.factions)[0]
        s.regions[nb].owner, s.regions[nb].plague, s.regions[nb].order = fid, 30, 1
        a = s.armies_of(fid)[0]
        a.region = nb
        s, _ = resolve_turn(s, self.world, DEFAULT, {fid: [{"type": "purge", "army": a.id}]})
        self.assertLess(s.regions[nb].plague, 30)

    def test_deterministic_with_gm(self):
        self.assertEqual(self.with_focus()[0].digest(), self.with_focus()[0].digest())

    def test_lost_region_must_be_purged_before_attack(self):
        s, lost, _ = self.with_focus()
        nb = self.world.regions[lost].neighbors[0]
        fid = sorted(s.factions)[0]
        s.regions[nb].owner = fid
        a = s.armies_of(fid)[0]
        a.region = nb
        _, errs = validate(s, self.world, DEFAULT, fid, [{"type": "attack", "army": a.id, "target": lost}])
        self.assertIn("purga", errs[0])


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(WORLD.exists(), f"falta {WORLD}")
class WorldStartTests(unittest.TestCase):
    """Início 'world': reinos com território e capital vindos do world.json (mundos com reinos próprios)."""

    def make_world(self):
        import json
        raw = json.loads(WORLD.read_text())
        regions = {r["id"]: r for r in raw["regions"]}
        for r in raw["regions"]:
            r["owner"] = FREE
        # dois reinos de 3 províncias contíguas, um sem ferro nenhum
        taken = set()
        kingdoms = []
        for start in sorted(regions):
            group = [start] + [n for n in regions[start]["neighbors"] if n not in taken][:2]
            if len(group) == 3 and not taken & set(group) and not any(
                    n in taken for g in group for n in regions[g]["neighbors"]):
                kingdoms.append(group)
                taken |= set(group)
            if len(kingdoms) == 2:
                break
        raw["factions"] = [{"id": 0, "name": "Terras Livres", "color": "#999999"}]
        for fid, group in enumerate(kingdoms, start=1):
            raw["factions"].append({"id": fid, "name": f"R{fid}", "color": "#123456", "capital": group[0]})
            for rid in group:
                regions[rid]["owner"] = fid
        return WorldMap(raw, DEFAULT), kingdoms

    def test_world_start_uses_kingdoms(self):
        world, kingdoms = self.make_world()
        self.assertTrue(world.has_kingdoms)
        s = new_game(world, DEFAULT)                     # sem 'start': escolhe 'world' sozinho
        for fid, group in enumerate(kingdoms, start=1):
            self.assertEqual(sorted(s.regions_of(fid)), sorted(group))
            self.assertEqual(s.armies_of(fid)[0].region, group[0])
            iron = any(world.regions[r].base["iron"] for r in group) or s.regions[group[0]].iron_bonus > 0
            self.assertTrue(iron, "ferro garantido no início")
        free = [r for r in s.regions.values() if r.owner == FREE]
        self.assertTrue(free and all(r.garrison > 0 for r in free))
