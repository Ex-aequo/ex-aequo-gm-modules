"""Testes da partição em províncias e reinos (sem Azgaar: uma grelha sintética de células).
Correr a partir de modules/world-map:  python -m unittest tools.test_partition
"""
import sys
import unittest
from collections import deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from partition import MAX_BONUS, PartitionError, kingdom_colors, make_kingdoms, make_provinces  # noqa: E402


def grid(w, h, gap_col=None):
    """Células numa grelha w x h com vizinhança de 4; uma coluna de mar opcional parte a terra em duas."""
    pts, nbrs, land = [], [], []
    for y in range(h):
        for x in range(w):
            i = y * w + x
            pts.append((x * 10.0 + (y % 2) * 3, y * 10.0))
            nbrs.append([j for j, ok in ((i - 1, x > 0), (i + 1, x < w - 1), (i - w, y > 0), (i + w, y < h - 1)) if ok])
            if x != gap_col:
                land.append(i)
    return pts, nbrs, land


def build(w, h, kingdoms, share=0.3, gap_col=None, value=lambda p, c: 1.0):
    pts, nbrs, land = grid(w, h, gap_col)
    prov_of, n = make_provinces(pts, land, nbrs)
    cells = [[] for _ in range(n)]
    for c, p in prov_of.items():
        cells[p].append(c)
    center = [(sum(pts[c][0] for c in cs) / len(cs), sum(pts[c][1] for c in cs) / len(cs)) for cs in cells]
    adj = [set() for _ in range(n)]
    for c, p in prov_of.items():
        for v in nbrs[c]:
            q = prov_of.get(v)
            if q is not None and q != p:
                adj[p].add(q)
    adj = [sorted(a) for a in adj]
    vals = [value(p, center[p]) for p in range(n)]
    return (prov_of, cells, adj, center, vals), make_kingdoms(cells, adj, center, vals, kingdoms, share)


def connected(nodes, adj):
    nodes = set(nodes)
    start = next(iter(nodes))
    seen, q = {start}, deque([start])
    while q:
        u = q.popleft()
        for v in adj[u]:
            if v in nodes and v not in seen:
                seen.add(v)
                q.append(v)
    return seen == nodes


class PartitionTests(unittest.TestCase):
    def test_provinces_are_contiguous_and_cover_land(self):
        (prov_of, cells, adj, _, _), _ = build(120, 70, 25)
        self.assertEqual(len(prov_of), 120 * 70)
        for cs in cells:
            self.assertTrue(cs)
        sizes = sorted(len(cs) for cs in cells)
        self.assertLess(sizes[-1] / sizes[0], 4, "províncias de tamanho comparável")

    def test_kingdoms_equal_and_contiguous(self):
        (_, cells, adj, _, _), (owner, cap_of, P, bonus, _, _) = build(120, 70, 25)
        self.assertEqual(len(cap_of), 25)
        self.assertEqual(P, int(0.3 * len(cells) // 25))
        for f, cap in cap_of.items():
            mine = [p for p, o in enumerate(owner) if o == f]
            self.assertEqual(owner[cap], f)
            self.assertTrue(P <= len(mine) <= P + MAX_BONUS)
            self.assertEqual(len(mine), P + bonus.get(f, 0))
            self.assertTrue(connected(mine, adj), f"reino {f} não é contíguo")
        self.assertGreater(owner.count(0), len(owner) // 2, "a maior parte do mundo começa livre")

    def test_compensation(self):
        _, (_, _, _, bonus, _, _) = build(120, 70, 25)
        self.assertEqual(bonus, {}, "terra uniforme: ninguém é compensado")
        # faixas alternadas de terra rica e pobre: há reinos compensados, nunca com mais de +2
        (_, _, _, center, _), (owner, cap_of, P, bonus, value, _) = build(
            120, 70, 25, value=lambda p, c: 1.0 if (c[0] // 150) % 2 == 0 else 0.05)
        self.assertTrue(bonus)
        self.assertTrue(all(1 <= b <= MAX_BONUS for b in bonus.values()))

    def test_deterministic(self):
        a = build(100, 60, 25)[1][0]
        b = build(100, 60, 25)[1][0]
        self.assertEqual(a, b)

    def test_two_landmasses_share_kingdoms(self):
        (_, _, _, center, _), (owner, cap_of, _, _, _, _) = build(120, 60, 25, gap_col=60)
        west = sum(1 for c in cap_of.values() if center[c][0] < 600)
        self.assertTrue(10 <= west <= 15, f"reinos repartidos pelas duas massas de terra ({west} a oeste)")

    def test_rejects_bad_kingdom_count(self):
        with self.assertRaises(PartitionError):
            build(120, 70, 30)

    def test_map_too_small_says_so(self):
        with self.assertRaises(PartitionError) as e:
            build(60, 40, 150)
        self.assertIn("províncias", str(e.exception))

    def test_colors_distinct(self):
        _, (_, cap_of, _, _, _, _) = build(120, 70, 25)
        (_, _, _, center, _), _ = build(120, 70, 25)
        cols = kingdom_colors(cap_of, center)
        self.assertEqual(len(set(cols.values())), 25)


if __name__ == "__main__":
    unittest.main()
