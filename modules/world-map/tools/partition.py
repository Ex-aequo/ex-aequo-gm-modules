"""Províncias e reinos próprios (substituem as províncias e os estados do Azgaar).

Entrada: as células do Azgaar (posição, terra, vizinhas, área, população) e a secção [politica] do ficheiro de mundo.
Saída: região de cada célula, lista de regiões, lista de fações (com capital) e um relatório.

Regras (decisões de 2026-10-15):
  - Províncias: tamanho alvo fixo em células (CELLS_PER_PROVINCE). O número de províncias sai do tamanho do mapa.
  - Reinos: 25, 50, ..., 150. Todos começam com o mesmo número P de províncias contíguas; P é calculado:
        P = floor(territorio_inicial × províncias / reinos)
    Um reino com terra pobre pode receber até +2 províncias de compensação. O resto do mundo são Terras Livres.
  - Capitais espalhadas por toda a terra (amostragem do ponto mais distante + relaxamento), proporcionais ao tamanho
    de cada massa de terra. Ilhas pequenas ficam livres.
Tudo é determinístico: mesmas células + mesma configuração = mesma partição.
"""
from __future__ import annotations

import colorsys
import heapq
import math
from collections import defaultdict, deque

import numpy as np
from scipy.spatial import cKDTree

CELLS_PER_PROVINCE = 16     # ~16 células do Azgaar por província
KINGDOM_CHOICES = (25, 50, 75, 100, 125, 150)
MAX_BONUS = 2               # províncias extra de compensação por reino pobre
POOR = 0.75                 # reino "pobre": valor abaixo de 75 % da mediana
FREE = 0


class PartitionError(ValueError):
    pass


def _components(nodes, adj):
    seen, comps = set(), []
    for s in nodes:
        if s in seen:
            continue
        comp, q = [], deque([s])
        seen.add(s)
        while q:
            u = q.popleft()
            comp.append(u)
            for v in adj[u]:
                if v not in seen:
                    seen.add(v)
                    q.append(v)
        comps.append(sorted(comp))
    return comps


def _farthest_points(items, k, dist_from, first):
    """Escolhe k itens bem espalhados: começa em `first` e junta sempre o mais distante dos já escolhidos."""
    chosen = [first]
    best = dist_from(first)
    while len(chosen) < k:
        nxt = max(items, key=lambda i: (best.get(i, -1), -i))
        chosen.append(nxt)
        for i, d in dist_from(nxt).items():
            if d < best.get(i, 1e18):
                best[i] = d
    return chosen


def _bfs(adj, sources, allowed=None):
    dist = {s: 0 for s in sources}
    q = deque(sources)
    while q:
        u = q.popleft()
        for v in adj[u]:
            if v not in dist and (allowed is None or v in allowed):
                dist[v] = dist[u] + 1
                q.append(v)
    return dist


def _largest_remainder(total, weights):
    s = sum(weights)
    raw = [total * w / s for w in weights]
    out = [int(x) for x in raw]
    for i in sorted(range(len(raw)), key=lambda i: (-(raw[i] - out[i]), i))[: total - sum(out)]:
        out[i] += 1
    return out


# ------------------------------------------------------------------------------------------------ províncias
def make_provinces(pts, land_cells, cell_nbrs, cells_per_province=CELLS_PER_PROVINCE, iterations=3):
    """Divide a terra em províncias compactas e contíguas (k-médias sobre o grafo de células).
    Devolve (province_of_cell: dict célula->índice 0.., número de províncias)."""
    land = set(land_cells)
    adj = {c: [v for v in cell_nbrs[c] if v in land] for c in land_cells}
    comps = _components(land_cells, adj)
    tiny_limit = max(3, cells_per_province // 4)
    prov_of = {}
    n_prov = 0
    tiny = []
    for comp in sorted(comps, key=lambda c: (-len(c), c[0])):
        if len(comp) < tiny_limit:
            tiny.extend(comp)
            continue
        k = max(1, round(len(comp) / cells_per_province))
        cx = sum(pts[c][0] for c in comp) / len(comp)
        cy = sum(pts[c][1] for c in comp) / len(comp)
        first = min(comp, key=lambda c: ((pts[c][0] - cx) ** 2 + (pts[c][1] - cy) ** 2, c))
        seeds = _kmeans_seeds(pts, comp, k, first) if k > 1 else [first]
        for _ in range(iterations):         # acerto no grafo: em terra côncava o centro geométrico pode cair fora
            owner = _dijkstra(pts, adj, seeds)
            groups = defaultdict(list)
            for c in comp:
                groups[owner[c]].append(c)
            new = []
            for s in seeds:
                g = groups[s]
                gx = sum(pts[c][0] for c in g) / len(g)
                gy = sum(pts[c][1] for c in g) / len(g)
                new.append(min(g, key=lambda c: ((pts[c][0] - gx) ** 2 + (pts[c][1] - gy) ** 2, c)))
            if new == seeds:
                break
            seeds = new
        owner = _dijkstra(pts, adj, seeds)
        index = {s: n_prov + i for i, s in enumerate(seeds)}
        for c in comp:
            prov_of[c] = index[owner[c]]
        n_prov += len(seeds)
    # ilhotas: juntam-se à província da célula de terra mais próxima (não contíguas, mas a 1 passo por mar)
    if tiny and prov_of:
        placed = list(prov_of)
        for c in tiny:
            near = min(placed, key=lambda o: ((pts[o][0] - pts[c][0]) ** 2 + (pts[o][1] - pts[c][1]) ** 2, o))
            prov_of[c] = prov_of[near]
    return prov_of, n_prov


def _kmeans_seeds(pts, comp, k, first, iterations=40):
    """Sementes bem distribuídas: ponto mais distante (euclidiano) + k-médias (Lloyd) nas coordenadas das células."""
    xy = np.array([pts[c] for c in comp], dtype=np.float64)
    i0 = comp.index(first)
    chosen = [i0]
    d = ((xy - xy[i0]) ** 2).sum(1)
    for _ in range(k - 1):
        j = int(np.argmax(d))
        chosen.append(j)
        d = np.minimum(d, ((xy - xy[j]) ** 2).sum(1))
    centers = xy[chosen].copy()
    for _ in range(iterations):
        _, lab = cKDTree(centers).query(xy)
        cnt = np.bincount(lab, minlength=k)
        sx = np.bincount(lab, weights=xy[:, 0], minlength=k)
        sy = np.bincount(lab, weights=xy[:, 1], minlength=k)
        ok = cnt > 0
        new = centers.copy()
        new[ok, 0] = sx[ok] / cnt[ok]
        new[ok, 1] = sy[ok] / cnt[ok]
        if np.allclose(new, centers):
            break
        centers = new
    # cada centro passa para a célula de terra mais próxima ainda livre
    tree = cKDTree(xy)
    seeds, used = [], set()
    for cx, cy in centers:
        _, near = tree.query((cx, cy), k=min(len(comp), 8))
        for j in np.atleast_1d(near):
            if int(j) not in used:
                used.add(int(j))
                seeds.append(comp[int(j)])
                break
    return seeds


def _dijkstra(pts, adj, seeds):
    owner, dist = {}, {}
    heap = [(0.0, i, s, s) for i, s in enumerate(seeds)]
    while heap:
        d, _, s, u = heapq.heappop(heap)
        if u in owner:
            continue
        owner[u] = s
        for v in adj[u]:
            if v not in owner:
                nd = d + math.dist(pts[u], pts[v])
                if nd < dist.get(v, 1e18):
                    dist[v] = nd
                    heapq.heappush(heap, (nd, len(dist), s, v))
    return owner


# ------------------------------------------------------------------------------------------------ reinos
def make_kingdoms(prov_cells, prov_adj, prov_center, prov_value, kingdoms, share):
    """Atribui `kingdoms` reinos com o mesmo número P de províncias contíguas (+0..2 de compensação).
    Devolve (owner por província, capital por reino, P, notas)."""
    if kingdoms not in KINGDOM_CHOICES:
        raise PartitionError(f"reinos tem de ser um de {KINGDOM_CHOICES} (pedido: {kingdoms})")
    if not 0.05 <= share <= 0.8:
        raise PartitionError("territorio_inicial tem de estar entre 0.05 e 0.8")
    n = len(prov_cells)
    P = int(share * n // kingdoms)
    if P < 2:
        need = math.ceil(2 * kingdoms / share)
        raise PartitionError(f"o mapa tem {n} províncias: dá {share * n / kingdoms:.1f} por reino com {kingdoms} reinos. "
                             f"São precisas pelo menos 2, o que pede ~{need} províncias (um mapa maior, "
                             f"mais terra, ou menos reinos)")
    provs = list(range(n))
    comps = sorted(_components(provs, prov_adj), key=lambda c: (-len(c), c[0]))
    eligible = [c for c in comps if len(c) >= 2 * P]            # cabe um reino e ainda sobra terra livre
    if not eligible:
        raise PartitionError("nenhuma massa de terra tem tamanho para um reino")
    # capitais só em terra habitável (valor acima da mediana das províncias); desertos e gelo ficam para crescer,
    # e a quota de reinos de cada massa de terra conta só a terra habitável (um continente meio gelado não se enche)
    vmed = sorted(prov_value)[n // 2]
    good = {p for p in range(n) if prov_value[p] >= vmed}
    eligible = [c for c in eligible if any(p in good for p in c)]
    if not eligible:
        raise PartitionError("nenhuma massa de terra habitável tem tamanho para um reino")
    weights = [sum(p in good for p in c) for c in eligible]
    per = _largest_remainder(kingdoms, weights)
    # uma massa de terra não pode receber mais reinos do que cabem lá (com 2P províncias por reino)
    for _ in range(len(eligible)):
        over = [i for i, k in enumerate(per) if k * 2 * P > len(eligible[i])]
        if not over:
            break
        spare = 0
        for i in over:
            cap = len(eligible[i]) // (2 * P)
            spare += per[i] - cap
            per[i] = cap
        room = [i for i in range(len(eligible)) if (per[i] + 1) * 2 * P <= len(eligible[i])]
        if not room:
            raise PartitionError(f"não há terra contígua para {kingdoms} reinos de {P} províncias")
        for i, extra in zip(room, _largest_remainder(spare, [weights[i] for i in room])):
            per[i] += extra

    def d2(a, b):
        return (prov_center[a][0] - prov_center[b][0]) ** 2 + (prov_center[a][1] - prov_center[b][1]) ** 2

    capitals = []
    for comp, k in zip(eligible, per):
        if k == 0:
            continue
        compset = set(comp)
        cx = sum(prov_center[p][0] for p in comp) / len(comp)
        cy = sum(prov_center[p][1] for p in comp) / len(comp)
        hops = lambda s: _bfs(prov_adj, [s], compset)
        far = max(comp, key=lambda p: ((prov_center[p][0] - cx) ** 2 + (prov_center[p][1] - cy) ** 2, -p))
        pool = [p for p in comp if p in good]
        if len(pool) < k:
            pool = comp
        far = max(pool, key=lambda p: ((prov_center[p][0] - cx) ** 2 + (prov_center[p][1] - cy) ** 2, -p))
        caps = _farthest_points(pool, k, hops, far)
        for _ in range(4):            # relaxamento: cada capital vai para o centro da sua zona
            near = defaultdict(list)
            dist_all = [hops(c) for c in caps]
            for p in comp:
                j = min(range(len(caps)), key=lambda j: (dist_all[j].get(p, 10 ** 6), j))
                near[j].append(p)
            new = []
            for j, c in enumerate(caps):
                zone = near[j]
                gx = sum(prov_center[p][0] for p in zone) / len(zone)
                gy = sum(prov_center[p][1] for p in zone) / len(zone)
                inner = [p for p in zone if len(prov_adj[p]) >= 3 and p in good] or [p for p in zone if p in good] or zone
                new.append(min(inner, key=lambda p: ((prov_center[p][0] - gx) ** 2 + (prov_center[p][1] - gy) ** 2, p)))
            if new == caps or len(set(new)) < len(new):
                break
            caps = new
        capitals.extend(caps)

    owner = [FREE] * n
    for f, c in enumerate(capitals, start=1):
        owner[c] = f
    size = {f: 1 for f in range(1, len(capitals) + 1)}
    cap_of = {f: c for f, c in enumerate(capitals, start=1)}
    stuck = set()

    def grow(f, target):
        """Junta ao reino f a província livre vizinha mais perto da capital, evitando tocar noutros reinos."""
        cands = {q for p in range(n) if owner[p] == f for q in prov_adj[p] if owner[q] == FREE}
        if not cands:
            return False
        touch = lambda q: any(owner[r] not in (FREE, f) for r in prov_adj[q])
        poor = lambda q: 2.0 if prov_value[q] < 0.25 * vmed else 1.0
        best = min(cands, key=lambda q: (touch(q), d2(q, cap_of[f]) * poor(q), q))
        owner[best] = f
        size[f] += 1
        return True

    for rnd in range(1, P):
        order = list(range(1, len(capitals) + 1))
        shift = rnd % len(order)
        for f in order[shift:] + order[:shift]:                # ordem rodada a cada volta: ninguém escolhe sempre 1.º
            if f not in stuck and size[f] < P and not grow(f, P):
                stuck.add(f)
    notes = []
    for f in sorted(stuck):                                    # reino encurralado: recomeça noutro sítio
        for p in range(n):
            if owner[p] == f:
                owner[p] = FREE
        free = [p for p in range(n) if owner[p] == FREE]
        taken = [p for p in range(n) if owner[p] != FREE]
        dist = _bfs(prov_adj, taken) if taken else {}
        room = lambda p: len(_bfs(prov_adj, [p], set(free)))
        options = sorted((p for p in free if room(p) >= 2 * P), key=lambda p: (p not in good, -min(dist.get(p, 10 ** 6), 6), p))
        if not options:
            raise PartitionError(f"o reino {f} não tem espaço para {P} províncias")
        cap_of[f] = options[0]
        owner[options[0]], size[f] = f, 1
        while size[f] < P:
            if not grow(f, P):
                raise PartitionError(f"o reino {f} não tem espaço para {P} províncias")
        notes.append(f"reino {f} encurralado na primeira volta; recolocado")

    # compensação: reinos com terra pobre recebem até +2 províncias
    value = {f: sum(prov_value[p] for p in range(n) if owner[p] == f) for f in cap_of}
    med = sorted(value.values())[len(value) // 2]
    bonus = {}
    for f in sorted(cap_of):
        b = 0
        while value[f] < POOR * med and b < MAX_BONUS:
            before = {p for p in range(n) if owner[p] == f}
            if not grow(f, P + b + 1):
                break
            got = next(p for p in range(n) if owner[p] == f and p not in before)
            value[f] += prov_value[got]
            b += 1
        if b:
            bonus[f] = b
    return owner, cap_of, P, bonus, value, notes


# ------------------------------------------------------------------------------------------------ cores
def kingdom_colors(cap_of, prov_center):
    """Uma cor por reino; reinos próximos recebem cores afastadas (atribuição gulosa)."""
    k = len(cap_of)
    palette = []
    for i in range(max(k, 12)):
        h = (i * 0.618034) % 1.0
        tier = i % 3
        l = (0.50, 0.40, 0.60)[tier]
        s = (0.48, 0.42, 0.36)[tier]
        r, g, b = colorsys.hls_to_rgb(h, l, s)
        palette.append((r, g, b))

    def cdist(a, b):
        return sum((x - y) ** 2 for x, y in zip(a, b))

    used, out = set(), {}
    for f in sorted(cap_of):
        c0 = prov_center[cap_of[f]]
        near = sorted((math.dist(c0, prov_center[cap_of[g]]), g) for g in out)[:8]
        free = [i for i in range(len(palette)) if i not in used]
        best = max(free, key=lambda i: (min((cdist(palette[i], palette[out[g]]) for _, g in near), default=1), -i))
        used.add(best)
        out[f] = best
    return {f: "#%02x%02x%02x" % tuple(int(255 * x) for x in palette[i]) for f, i in out.items()}


# ------------------------------------------------------------------------------------------------ nomes
ROMAN = ["", " II", " III", " IV", " V", " VI", " VII", " VIII"]


def province_names(prov_cells, prov_center, pts, cell_burg, burg_pop, burg_name, cell_azprov, azprov):
    """Nome = maior burgo da província; sem burgo, a província do Azgaar onde cai o centro, com um qualificativo
    geográfico ("do Norte", "Oriental"...) se o nome já existir."""
    names, used = [], defaultdict(int)
    for p, cells in enumerate(prov_cells):
        burgs = [cell_burg[c] for c in cells if cell_burg[c]]
        if burgs:
            name = burg_name[max(burgs, key=lambda b: (burg_pop[b], -b))]
        else:
            cx, cy = prov_center[p]
            c = min(cells, key=lambda c: ((pts[c][0] - cx) ** 2 + (pts[c][1] - cy) ** 2, c))
            ap = azprov.get(cell_azprov[c])
            if ap:
                name = ap["name"]
                if used[name]:
                    ax, ay = pts[ap["center"]] if ap.get("center") is not None else (cx, cy)
                    dx, dy = cx - ax, cy - ay
                    q = (" do Norte" if dy < 0 else " do Sul") if abs(dy) > abs(dx) else (
                        " Oriental" if dx > 0 else " Ocidental")
                    if not used[name + q]:
                        name += q
            else:
                name = f"Terra {p + 1}"
        used[name] += 1
        n = used[name]
        names.append(name + (ROMAN[n - 1] if n <= len(ROMAN) else f" {n}"))
    return names
