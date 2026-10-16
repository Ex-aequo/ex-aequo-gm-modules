"""Mundos novos: o GM escolhe os parâmetros (pré-visualização no browser) e o servidor gera o mundo final com o
Province-Forge (mapgen CLI, Node) em segundo plano, seguido do conversor para o motor (modules/world-forge).

Um mundo por pasta em WORLDS_DIR/<nome>-<mapId>. Uma geração de cada vez; o progresso vem das linhas JSON que o
mapgen escreve.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

from .config import MODULES, WORLDS_DIR

PF = MODULES.parent / "vendor/province-forge"
CLI = PF / "build/cli/mapgen.js"
sys.path.insert(0, str(MODULES / "world-forge"))
from forge.convert import praga_world  # noqa: E402

# parâmetros que o GM pode mudar (o resto fica como no Province-Forge)
ALLOWED = {
    "landFraction", "continentSizes", "coastRoughness", "islandCount", "lakeCount", "riverDensity",
    "temperatureBias", "moistureBias", "playerSlots", "startProvinces", "startShare", "rareShare",
    "valueTolerance", "polarIce", "minStraitCells", "ridgeBorderWeight", "riverBorderWeight",
}


class WorldJobs:
    def __init__(self):
        self.lock = threading.Lock()
        self.job: dict | None = None

    def status(self) -> dict | None:
        with self.lock:
            return dict(self.job) if self.job else None

    def start(self, name: str, seed: str, params: dict, max_level: int = 4) -> dict:
        if not CLI.exists():
            raise RuntimeError(f"falta compilar o Province-Forge: cd {PF} && npm ci && npm run build:cli")
        with self.lock:
            if self.job and self.job["state"] == "running":
                raise RuntimeError("já há um mundo a ser gerado")
            slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "mundo"
            out = WORLDS_DIR / f"{slug}-{int(time.time())}"
            p = {k: v for k, v in params.items() if k in ALLOWED}
            p.update({"autoScale": True, "reserveSlots": 0})
            self.job = {"state": "running", "name": name, "seed": seed, "dir": str(out), "stage": "a começar",
                        "pct": 0, "started": time.time(), "error": None, "params": p}
        threading.Thread(target=self._run, args=(name, seed, p, out, max_level), daemon=True).start()
        return self.status()

    def _set(self, **kw):
        with self.lock:
            self.job.update(kw)

    def _run(self, name: str, seed: str, params: dict, out: Path, max_level: int):
        try:
            WORLDS_DIR.mkdir(parents=True, exist_ok=True)
            pfile = WORLDS_DIR / f".{out.name}.params.json"
            pfile.write_text(json.dumps(params))
            proc = subprocess.Popen(["node", str(CLI), "create", "--seed", seed, "--out", str(out),
                                     "--params", str(pfile), "--max-level", str(max_level)],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            for line in proc.stdout:
                try:
                    m = json.loads(line)
                except ValueError:
                    continue
                st = m.get("stage")
                if st == "generate":
                    self._set(stage="a gerar a geografia e as províncias", pct=1)
                elif st == "maps":
                    self._set(stage="a desenhar o relevo (tiles)", pct=3)
                elif st == "tiles" and "pct" in m:
                    self._set(stage="a desenhar o relevo (tiles)", pct=3 + int(m["pct"] * 0.95))
                elif st == "failed":
                    self._set(error=f"o gerador recusou este mundo: {m.get('reason')}")
            err = proc.stderr.read()
            if proc.wait() != 0:
                raise RuntimeError(self.job.get("error") or err.strip().splitlines()[-1:] or "o gerador falhou")
            pfile.unlink(missing_ok=True)
            self._set(stage="a preparar o mundo para o jogo", pct=99)
            static = json.loads((out / "static-map.json").read_text())
            (out / "world.json").write_text(json.dumps(praga_world(static, name), ensure_ascii=False,
                                                       separators=(",", ":")))
            self._set(state="done", stage="pronto", pct=100)
        except Exception as e:                                  # noqa: BLE001 — o erro vai para o painel do GM
            self._set(state="failed", stage="falhou", error=str(e))


JOBS = WorldJobs()


def list_worlds() -> list[dict]:
    out = []
    if not WORLDS_DIR.exists():
        return out
    for d in sorted(WORLDS_DIR.iterdir(), reverse=True):
        mf, wj = d / "manifest.json", d / "world.json"
        if not (d.is_dir() and mf.exists() and wj.exists()):
            continue
        m = json.loads(mf.read_text())
        w = json.loads(wj.read_text())
        out.append({"dir": str(d), "name": w["name"], "kingdoms": len(w["factions"]) - 1,
                    "provinces": len(w["regions"]), "created": m.get("createdAt"), "fairness": (m.get("fairness") or {}).get("score"),
                    "issues": [i["message"] for i in m.get("issues", [])]})
    return out
