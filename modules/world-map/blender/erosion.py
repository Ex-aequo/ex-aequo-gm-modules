"""Erosão do relevo para a base renderizada no Blender.

Método: erosão fluvial "stream power" com solver implícito (Braun & Willett 2013). A água escoa pela rede de
drenagem até ao mar (a rede vem de um priority-flood, por isso as depressões escoam sem serem aplanadas) e o
relevo é cortado em proporção ao caudal e ao declive; uma difusão leve arredonda as cristas. Dá vales ramificados
que descem até à costa. Depois, ruído "erodido" acrescenta o detalhe fino.

Experimentado e posto de parte: erosão por gotas de água — enchia as depressões e criava "lagos" planos.
Determinístico. Precisa de numba (pip install numba).
"""
from __future__ import annotations

import heapq

import numpy as np
from numba import njit


@njit(cache=True)
def _stream_power(h, land, uplift, K, m, dt, iters, kd):
    """Erosão fluvial implícita (Braun & Willett 2013), com a rede de drenagem tirada de um priority-flood:
    cada célula drena para a vizinha por onde a "inundação" a alcançou, por isso as depressões escoam sem serem
    aplanadas. h em píxeis de altura; o mar (land == 0) é o nível de base."""
    H, W = h.shape
    n = H * W
    rec = np.empty(n, np.int64)
    order = np.empty(n, np.int64)
    area = np.empty(n, np.float64)
    done = np.zeros(n, np.uint8)
    for _ in range(iters):
        done[:] = 0
        heap = [(0.0, 0)]
        heap.pop()
        cnt = 0
        for i in range(n):
            y, x = i // W, i % W
            if land[y, x] == 0 or y == 0 or x == 0 or y == H - 1 or x == W - 1:
                done[i] = 1
                rec[i] = i
                heapq.heappush(heap, (h[y, x], i))
        while heap:
            z, i = heapq.heappop(heap)
            y, x = i // W, i % W
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    yy, xx = y + dy, x + dx
                    if 0 <= yy < H and 0 <= xx < W:
                        j = yy * W + xx
                        if done[j] == 0:
                            done[j] = 1
                            rec[j] = i
                            order[cnt] = j
                            cnt += 1
                            heapq.heappush(heap, (max(h[yy, xx], z), j))
        for k in range(n):
            area[k] = 1.0
        for t in range(cnt - 1, -1, -1):
            j = order[t]
            r = rec[j]
            if r != j:
                area[r] += area[j]
        for t in range(cnt):
            j = order[t]
            r = rec[j]
            y, x = j // W, j % W
            ry, rx = r // W, r % W
            dist = 1.4142 if (y != ry and x != rx) else 1.0
            f = K * dt * area[j] ** m / dist
            hj = h[y, x] + dt * uplift[y, x]
            h[y, x] = (hj + f * h[ry, rx]) / (1 + f)
        # difusão de encosta: arredonda cristas demasiado afiadas
        if kd > 0:
            lap = np.zeros((H, W))
            for y in range(1, H - 1):
                for x in range(1, W - 1):
                    if land[y, x]:
                        lap[y, x] = h[y - 1, x] + h[y + 1, x] + h[y, x - 1] + h[y, x + 1] - 4 * h[y, x]
            for y in range(H):
                for x in range(W):
                    h[y, x] += kd * dt * lap[y, x]
    return h


def perlin(shape, freq, seed):
    """Ruído de gradiente 2D clássico, vetorizado. freq = células por lado. Valores ~[-0.7, 0.7]."""
    rng = np.random.default_rng(seed)
    H, W = shape
    ang = rng.uniform(0, 2 * np.pi, (freq + 2, freq + 2))
    gx, gy = np.cos(ang), np.sin(ang)
    y, x = np.mgrid[0:H, 0:W].astype(np.float64)
    x = x / W * freq
    y = y / H * freq
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    fx, fy = x - x0, y - y0

    def dot(ix, iy, dx, dy):
        return gx[iy, ix] * dx + gy[iy, ix] * dy

    n00 = dot(x0, y0, fx, fy)
    n10 = dot(x0 + 1, y0, fx - 1, fy)
    n01 = dot(x0, y0 + 1, fx, fy - 1)
    n11 = dot(x0 + 1, y0 + 1, fx - 1, fy - 1)
    u = fx * fx * fx * (fx * (fx * 6 - 15) + 10)
    v = fy * fy * fy * (fy * (fy * 6 - 15) + 10)
    return ((n00 * (1 - u) + n10 * u) * (1 - v) + (n01 * (1 - u) + n11 * u) * v).astype(np.float32)


def eroded_fbm(shape, freq, octaves, seed):
    """fBm em que cada oitava perde força onde a encosta já é íngreme: imita vales e cristas de erosão
    (a ideia do "erosion fbm" com derivadas), sem simulação. Valores ~[-0.5, 0.5]."""
    out = np.zeros(shape, np.float32)
    amp = 0.5
    for o in range(octaves):
        n = perlin(shape, freq * 2 ** o, seed + o)
        gy, gx = np.gradient(out)
        slope = (gx * gx + gy * gy) * (shape[0] / freq) ** 2
        out += amp * n / (1 + 6 * slope)
        amp *= 0.5
    return out


def mountains(base: np.ndarray, land: np.ndarray, vertical_px: float, seed: int = 101) -> np.ndarray:
    """Relevo final: base suave (0..1, do Azgaar) erodida a 1/4 da resolução + detalhe fino à resolução final.
    vertical_px: quantos píxeis (da resolução final) vale a altura 1. O lado tem de ser múltiplo de 4.
    Não usar diretamente numa janela sem margem: a borda funciona como nível de base (ver export_tile)."""
    from scipy import ndimage
    N = base.shape[0]
    n = N // 4
    b = ndimage.zoom(base, n / N, order=1)
    lnd = ndimage.zoom(land.astype(np.float32), n / N, order=1) > 0.5
    mount = np.clip((b - 0.12) / 0.45, 0, 1)                    # 0 nas planícies, 1 na alta montanha
    v = vertical_px / 4                                         # cada píxel daqui vale 4 da resolução final
    noise = perlin((n, n), 8, seed) * 0.6 + perlin((n, n), 16, seed + 1) * 0.3 + perlin((n, n), 32, seed + 2) * 0.15
    h0 = np.where(lnd, np.clip(b * 0.7 + noise * 0.12 * (0.3 + mount), 0.002, None), 0) * v
    uplift = 0.35 * (0.1 + mount ** 1.5) * lnd
    hh = _stream_power(h0.astype(np.float64), lnd.astype(np.uint8), uplift.astype(np.float64),
                       0.02, 0.5, 1.0, 80, 0.15)
    h = ndimage.gaussian_filter(hh / v, 0.8)                     # tira os traços retos da drenagem em 8 direções
    up = ndimage.zoom(h, N / n, order=3)[:N, :N]
    mount_f = ndimage.zoom(mount, N / n, order=1)[:N, :N]
    detail = eroded_fbm((N, N), 24, 4, seed + 10)
    up = up + detail * (0.008 + 0.05 * mount_f)
    return np.where(land, np.clip(up, 0.004, None), 0).astype(np.float32)
