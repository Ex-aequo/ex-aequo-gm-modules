"""Testes da visão, batedores, espiões e rumores (§8). Correr a partir de modules/turn-engine:
    python -m unittest discover tests
"""
import copy
import json
import os
import unittest
from pathlib import Path

from praga import DEFAULT, FREE, WorldMap, new_game, resolve_turn
from praga.bots import STYLES, bot_orders
from praga.state import Agent, Army, GameState
from praga.vision import KNOWN, OWN, SPIED, VISIBLE, player_view

WORLD = Path(os.environ.get("PRAGA_WORLD", Path(__file__).resolve().parent / "fixtures/world.json"))


@unittest.skipUnless(WORLD.exists(), f"falta {WORLD}")
class VisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = WorldMap.load(WORLD, DEFAULT)

    def fresh(self):
        return new_game(self.world, DEFAULT, "small")

    def played(self, n=12):
        s = self.fresh()
        for i in range(n):
            orders = {f: bot_orders(s, self.world, DEFAULT, f, STYLES[k % 3])
                      for k, f in enumerate(sorted(s.factions)) if s.factions[f].active}
            s, _ = resolve_turn(s, self.world, DEFAULT, orders)
        return s

    def fid_and_free_neighbor_far(self, s):
        fid = sorted(s.factions)[0]
        cap = s.armies_of(fid)[0].region
        return fid, cap

    # ------------------------------------------------------------------ visão base
    def test_start_vision_is_own_plus_land_neighbours(self):
        s = self.fresh()
        for fid in sorted(s.factions)[:5]:
            own = set(s.regions_of(fid))
            expect = own | {n for r in own for n in self.world.regions[r].neighbors}
            self.assertEqual(set(s.vision[fid]), expect)
            self.assertEqual(set(s.known[fid]), expect)
            self.assertTrue(all(s.vision[fid][r] == OWN for r in own))

    def test_sea_links_do_not_give_vision(self):
        s = self.fresh()
        for fid in sorted(s.factions):
            own = set(s.regions_of(fid))
            land = {n for r in own for n in self.world.regions[r].neighbors}
            sea_only = {n for r in own for n in self.world.regions[r].sea_links} - land - own
            self.assertFalse(sea_only & set(s.vision[fid]))

    # ------------------------------------------------------------------ fugas
    def test_player_view_does_not_depend_on_hidden_state(self):
        """Mudar tudo o que a fação não vê não pode mudar nada na vista dela."""
        s = self.played(10)
        fid = next(f for f in sorted(s.factions) if s.factions[f].active)
        before = json.dumps(player_view(s, self.world, DEFAULT, fid), sort_keys=True)
        t = copy.deepcopy(s)
        hidden = [rid for rid in t.regions if rid not in t.vision[fid]]
        self.assertTrue(hidden)
        other = next(f for f in sorted(t.factions) if f != fid)
        for rid in hidden:
            r = t.regions[rid]
            r.owner, r.pop, r.plague, r.fort, r.garrison = other, 99.0, 55, 3, 999
        for a in t.armies.values():
            if a.region in hidden:
                a.men += 5000
        t.armies[99999] = Army(id=99999, owner=other, region=hidden[0], men=4000)
        t.agents[99999] = Agent(id=99999, owner=other, kind="spy", region=hidden[0])
        t.factions[other].stock["gold"] = 1e6
        after = json.dumps(player_view(t, self.world, DEFAULT, fid), sort_keys=True)
        self.assertEqual(before, after)

    def test_view_only_contains_known_regions_and_seen_factions(self):
        s = self.played(10)
        for fid in sorted(s.factions)[:6]:
            if not s.factions[fid].active:
                continue
            v = player_view(s, self.world, DEFAULT, fid)
            self.assertEqual(set(v["regions"]), set(s.known[fid]))
            seen = {e["o"] for e in v["regions"].values()} | {o for e in v["regions"].values() for o, _ in e.get("a", [])}
            self.assertTrue({f["id"] for f in v["factions"]} <= seen)
            for rid, e in v["regions"].items():
                if e["level"] < SPIED:
                    self.assertNotIn("x", e, "detalhe de espião numa região não espiada")
                if e["level"] == KNOWN:
                    self.assertLess(e["t"], s.turn, "uma região só conhecida tem uma fotografia antiga")

    # ------------------------------------------------------------------ batedores e espiões
    def agent(self, s, fid, kind, region):
        aid = max(s.agents, default=0) + 1
        s.agents[aid] = Agent(id=aid, owner=fid, kind=kind, region=region)
        s.next_agent = aid + 1
        return aid

    def far_path(self, s, fid):
        """Um caminho de 2 passos por terra (sem terreno difícil) que sai da visão da fação."""
        vis = s.vision[fid]
        for rid in sorted(vis):
            for a in self.world.regions[rid].neighbors:
                for b in self.world.regions[a].neighbors:
                    if (b not in vis and not self.world.regions[a].rough and not self.world.regions[b].rough
                            and not s.armies_in(a) and not s.armies_in(b)):
                        return rid, [a, b]
        self.skipTest("sem caminho adequado")

    def test_recruit_scout_and_explore(self):
        s = self.fresh()
        fid = sorted(s.factions)[0]
        cap = s.regions_of(fid)[0]
        s, _ = resolve_turn(s, self.world, DEFAULT, {fid: [{"type": "recruit_agent", "region": cap, "kind": "scout"}]})
        mine = s.agents_of(fid)
        self.assertEqual(len(mine), 1)
        start, path = self.far_path(s, fid)
        mine[0].region = start
        s, _ = resolve_turn(s, self.world, DEFAULT, {fid: [{"type": "agent_move", "agent": mine[0].id, "path": path}]})
        self.assertEqual(s.vision[fid].get(path[-1]), VISIBLE)
        # o batedor volta para trás: a região fica só conhecida, com a fotografia do turno em que foi vista
        seen_turn = s.known[fid][path[-1]]["t"]
        s, _ = resolve_turn(s, self.world, DEFAULT, {fid: [{"type": "agent_move", "agent": mine[0].id,
                                                          "path": [path[0], start]}]})
        if path[-1] not in s.vision[fid]:
            v = player_view(s, self.world, DEFAULT, fid)
            self.assertEqual(v["regions"][path[-1]]["level"], KNOWN)
            self.assertEqual(v["regions"][path[-1]]["t"], seen_turn)

    def test_scout_caught_by_foreign_army(self):
        s = self.fresh()
        a, b = sorted(s.factions)[:2]
        target = s.armies_of(b)[0].region
        self.agent(s, a, "scout", target)
        s, ev = resolve_turn(s, self.world, DEFAULT, {})
        self.assertFalse(s.agents_of(a))
        self.assertIn("scout_lost", [e[0] for e in ev])
        self.assertTrue(any(m["kind"] == "report" for m in s.inbox[a]))

    def test_spy_sees_exact_numbers(self):
        s = self.fresh()
        a, b = sorted(s.factions)[:2]
        target = s.armies_of(b)[0].region
        self.agent(s, a, "spy", target)
        from praga.vision import update_vision
        update_vision(s, self.world, DEFAULT)
        v = player_view(s, self.world, DEFAULT, a)
        self.assertEqual(v["regions"][target]["level"], SPIED)
        men = {m for o, m, _ in v["regions"][target]["x"]["armies"] if o == b}
        self.assertIn(s.armies_of(b)[0].men, men)

    def test_spies_get_caught_eventually(self):
        s = self.fresh()
        a, b = sorted(s.factions)[:2]
        self.agent(s, a, "spy", s.regions_of(b)[0])
        for _ in range(60):
            s, ev = resolve_turn(s, self.world, DEFAULT, {a: [], b: []})   # ambos ativos (sem regência)
            if not s.agents_of(a):
                break
        self.assertFalse(s.agents_of(a), "com 10 % por turno, 60 turnos chegam")
        self.assertTrue(any("espião" in m["text"] for m in s.inbox.get(b, [])), "o dono da região sabe quem espiava")

    def test_agent_orders_validation(self):
        from praga import validate
        s = self.fresh()
        fid = sorted(s.factions)[0]
        other = s.regions_of(sorted(s.factions)[1])[0]
        acc, errs = validate(s, self.world, DEFAULT, fid, [{"type": "recruit_agent", "region": other, "kind": "scout"},
                                                            {"type": "recruit_agent", "region": s.regions_of(fid)[0],
                                                             "kind": "dragon"}])
        self.assertEqual(acc, [])
        self.assertEqual(len(errs), 2)

    def test_agent_upkeep(self):
        s = self.fresh()
        fid = sorted(s.factions)[0]
        base, _ = resolve_turn(s, self.world, DEFAULT, {})
        self.agent(s, fid, "spy", s.regions_of(fid)[0])
        with_spy, _ = resolve_turn(s, self.world, DEFAULT, {})
        self.assertAlmostEqual(base.factions[fid].stock["gold"] - with_spy.factions[fid].stock["gold"],
                               DEFAULT.spy_upkeep, places=2)

    # ------------------------------------------------------------------ rumores
    def test_rumours_about_unseen_plague(self):
        s = self.fresh()
        from praga.state import land_distances
        fid = sorted(s.factions)[0]
        dist = land_distances(self.world, s.regions_of(fid))
        focus = next(r for r in sorted(dist) if dist[r] == 5 and s.regions[r].owner == FREE)
        s, _ = resolve_turn(s, self.world, DEFAULT, {}, [{"type": "plague_state", "value": "active"},
                                                         {"type": "plague_focus", "region": focus}])
        name = self.world.regions[focus].name
        got = [f for f in s.factions if any(m["kind"] == "rumour" for m in s.inbox.get(f, []))]
        self.assertIn(fid, got, "quem está a 5 regiões do foco ouve rumores")
        for f in got:
            self.assertNotIn(focus, s.vision[f], "quem vê o foco não precisa de rumores")
            for m in s.inbox[f]:
                self.assertNotIn(name, m["text"], "um rumor nunca diz o nome da região")

    def test_gm_rumour_by_region(self):
        s = self.fresh()
        fid = sorted(s.factions)[0]
        cap = s.regions_of(fid)[0]
        s, ev = resolve_turn(s, self.world, DEFAULT, {}, [{"type": "rumor", "text": "Um cometa cruzou o céu.",
                                                           "region": cap, "radius": 0}])
        self.assertEqual([m["text"] for m in s.inbox[fid] if m["kind"] == "gm"], ["Um cometa cruzou o céu."])
        self.assertIn("Rumor enviado a 1 fação(ões).", [e[2] for e in ev if e[0] == "gm"])

    def test_state_roundtrip_with_vision(self):
        s = self.played(6)
        self.assertEqual(GameState.from_dict(json.loads(json.dumps(s.to_dict()))).digest(), s.digest())

    def test_bots_explore(self):
        s = self.played(15)
        self.assertTrue(s.agents, "os bots recrutam batedores")
        start = self.fresh()
        grew = [f for f in s.factions if s.factions[f].active and len(s.known[f]) > len(start.known[f])]
        self.assertTrue(grew)

    def test_view_marks_guardian_kingdoms(self):
        players = set(sorted(self.world.factions)[1::2])
        s = new_game(self.world, DEFAULT, "small", players=players)
        for _ in range(4):
            s, _ = resolve_turn(s, self.world, DEFAULT, {f: [] for f in players})
        for fid in sorted(players):
            for f in player_view(s, self.world, DEFAULT, fid)["factions"]:
                self.assertEqual(f["bot"], f["id"] not in players)

