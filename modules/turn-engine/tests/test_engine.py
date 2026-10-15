"""Testes do motor. Correr a partir de modules/turn-engine:
    PRAGA_WORLD=../world-map/web/data/world.json python -m unittest discover tests
"""
import math
import os
import unittest
from pathlib import Path

from praga import DEFAULT, FREE, PRAGA, WorldMap, add_faction, new_game, resolve_turn, validate
from praga.bots import STYLES, bot_orders

WORLD = Path(os.environ.get("PRAGA_WORLD", Path(__file__).resolve().parents[2] / "world-map/web/data/world.json"))


@unittest.skipUnless(WORLD.exists(), f"falta {WORLD} (gerar com o módulo world-map)")
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

    def test_inactivity_regency_then_dissolve(self):
        s = self.fresh()
        fid = sorted(s.factions)[0]
        for _ in range(DEFAULT.dissolve_after + 1):
            s, _ = resolve_turn(s, self.world, DEFAULT, {})
        self.assertFalse(s.factions[fid].active)
        self.assertFalse(s.regions_of(fid))

    def test_late_entry_is_protected_and_isolated(self):
        s = self.fresh()
        rid = add_faction(s, self.world, DEFAULT, 100, "Teste")
        self.assertIsNotNone(rid)
        self.assertEqual(s.regions[rid].plague, 0)
        f = s.factions[100]
        self.assertGreaterEqual(f.protected_until, s.turn)
        for n in self.world.regions[rid].neighbors:
            self.assertIn(s.regions[n].owner, (FREE, PRAGA, 100))

    def test_foci_far_from_capitals(self):
        from praga.state import land_distances
        s = self.fresh()
        self.assertEqual(len(s.foci), DEFAULT.plague_foci)
        dist = land_distances(self.world, s.foci)
        for fid in s.factions:
            cap = s.armies_of(fid)[0].region
            self.assertGreaterEqual(dist.get(cap, 99), DEFAULT.foci_min_distance)

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
