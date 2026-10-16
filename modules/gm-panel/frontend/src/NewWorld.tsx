import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ViewerState } from "@pf/game/state";
import type { GeneratedMap } from "@pf/gen/types";
import { toClientMap } from "@pf/map/clientMap";
import { WorkerTileSource } from "@pf/view/tileSources";
import { ForgeMap } from "@forge-view/ForgeMap";
import { api, type WorldInfo, type WorldJob } from "./api";

/** Controlos do GM. Os outros parâmetros do Province-Forge ficam com os valores dele. */
interface Ctl { key: string; label: string; min: number; max: number; step: number; fmt?: (v: number) => string; help?: string }
const pct = (v: number) => `${Math.round(v * 100)}%`;
const x2 = (v: number) => `×${v.toFixed(2).replace(".", ",")}`;
const GROUPS: { title: string; ctl: Ctl[] }[] = [
  { title: "Reinos", ctl: [
    { key: "playerSlots", label: "Reinos", min: 25, max: 150, step: 5, help: "Cada reino é de um jogador ou, até alguém chegar, um reino-guardião." },
    { key: "startProvinces", label: "Províncias por reino", min: 3, max: 12, step: 1 },
    { key: "startShare", label: "Território inicial", min: 0.1, max: 0.6, step: 0.05, fmt: pct, help: "Parte da terra que começa com dono; o resto são Terras Livres. O tamanho do mundo vem daqui." },
  ] },
  { title: "Geografia", ctl: [
    { key: "landFraction", label: "Terra", min: 0.2, max: 0.6, step: 0.01, fmt: pct },
    { key: "continentSizes.0", label: "Continente A", min: 0.4, max: 1.6, step: 0.05, fmt: x2 },
    { key: "continentSizes.1", label: "Continente B", min: 0.4, max: 1.6, step: 0.05, fmt: x2 },
    { key: "continentSizes.2", label: "Continente C", min: 0.4, max: 1.6, step: 0.05, fmt: x2 },
    { key: "islandCount", label: "Ilhas", min: 0, max: 40, step: 1 },
    { key: "lakeCount", label: "Lagos", min: 0, max: 20, step: 1 },
    { key: "riverDensity", label: "Rios", min: 0.02, max: 0.12, step: 0.005, fmt: (v) => `${(v * 100).toFixed(1).replace(".", ",")}%` },
  ] },
  { title: "Clima e recursos", ctl: [
    { key: "temperatureBias", label: "Mais frio ↔ mais quente", min: -0.3, max: 0.3, step: 0.02, fmt: (v) => v.toFixed(2).replace(".", ",") },
    { key: "moistureBias", label: "Mais seco ↔ mais húmido", min: -0.3, max: 0.3, step: 0.02, fmt: (v) => v.toFixed(2).replace(".", ",") },
    { key: "rareShare", label: "Ouro e especiarias", min: 0.02, max: 0.15, step: 0.01, fmt: (v) => `${Math.round(v * 100)}% das províncias` },
  ] },
];
const START: Record<string, number> = {
  playerSlots: 25, startProvinces: 8, startShare: 0.3, landFraction: 0.5, "continentSizes.0": 1, "continentSizes.1": 1,
  "continentSizes.2": 1, islandCount: 14, lakeCount: 7, riverDensity: 0.06, temperatureBias: 0, moistureBias: 0, rareShare: 0.07,
};
const newSeed = () => Math.random().toString(36).slice(2, 8);

function toParams(v: Record<string, number>) {
  const p: Record<string, unknown> = {};
  for (const [k, val] of Object.entries(v)) if (!k.startsWith("continentSizes.")) p[k] = val;
  p.continentSizes = [v["continentSizes.0"], v["continentSizes.1"], v["continentSizes.2"]];
  return p;
}

/** Os reinos do turno 1, para a pré-visualização: as posições iniciais com o nome e a cor do gerador. */
function previewViewer(m: GeneratedMap): ViewerState {
  const provinces: ViewerState["provinces"] = {};
  for (const s of m.starts) for (const p of s.provinces) provinces[p] = { owner: `k${s.slot}`, controller: `k${s.slot}`, praga: 0 };
  return {
    turn: 1, viewer: null, known: {}, details: {}, reserved: [], provinces,
    countries: m.starts.map((s) => ({ id: `k${s.slot}`, name: s.country!.name, fullName: s.country!.fullName, color: s.country!.color })),
    visible: m.regions.map((r) => r.id),
  };
}

export function NewWorld({ onClose }: { onClose?: () => void }) {
  const [vals, setVals] = useState<Record<string, number>>(START);
  const [seed, setSeed] = useState(newSeed);
  const [name, setName] = useState("");
  const [gen, setGen] = useState<{ map: GeneratedMap; ms: number } | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [worlds, setWorlds] = useState<WorldInfo[]>([]);
  const [job, setJob] = useState<WorldJob | null>(null);
  const [current, setCurrent] = useState<string | null>(null);
  const [confirmDir, setConfirmDir] = useState<string | null>(null);
  const [started, setStarted] = useState<string | null>(null);
  const worker = useRef<Worker | null>(null);
  const reqId = useRef(0);

  const refresh = useCallback(() => api.worlds().then((r) => { setWorlds(r.worlds); setJob(r.job); setCurrent(r.current); })
    .catch((e: Error) => setErr(e.message)), []);
  useEffect(() => { refresh(); }, [refresh]);
  useEffect(() => {                                           // acompanhar a geração no servidor
    if (job?.state !== "running") return;
    const t = setInterval(refresh, 3000);
    return () => clearInterval(t);
  }, [job?.state, refresh]);

  useEffect(() => {
    const w = new Worker(new URL("./gen.worker.ts", import.meta.url), { type: "module" });
    w.onmessage = (e) => {
      if (e.data.id !== reqId.current) return;
      setBusy(false);
      if (e.data.error) setErr(`a geração falhou: ${e.data.error}`);
      else { setErr(null); setGen({ map: e.data.map, ms: e.data.ms }); }
    };
    worker.current = w;
    return () => w.terminate();
  }, []);

  const preview = () => {
    setBusy(true);
    setErr(null);
    worker.current?.postMessage({ id: ++reqId.current, params: { ...toParams(vals), seed, autoScale: true, reserveSlots: 0 } });
  };
  useEffect(() => { preview(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const cmap = useMemo(() => (gen ? toClientMap(gen.map) : null), [gen]);
  const tiles = useMemo(() => (gen ? new WorkerTileSource(gen.map) : null), [gen]);
  const viewer = useMemo(() => (gen ? previewViewer(gen.map) : null), [gen]);

  const build = async () => {
    try {
      const r = await api.newWorld(name.trim() || `Mundo ${seed}`, seed, toParams(vals));
      setJob(r.job);
    } catch (e) {
      setErr((e as Error).message);
    }
  };
  const startGame = async (dir: string) => {
    try {
      const r = await api.newGame(dir);
      setStarted(`Jogo novo começado. Contas: ${r.players.map((p) => p.username).join(", ") || "nenhuma"} (cada uma recebeu um reino).`);
      setConfirmDir(null);
      refresh();
    } catch (e) {
      setErr((e as Error).message);
    }
  };

  const m = gen?.map;
  const land = m ? m.stats.landProvinces : 0;
  const sameAsPreview = m && m.params.seed === seed && JSON.stringify(toParams(vals)) ===
    JSON.stringify(toParams(Object.fromEntries(Object.keys(START).map((k) => [k, k.startsWith("continentSizes.")
      ? m.params.continentSizes[+k.slice(-1)] : (m.params as unknown as Record<string, number>)[k]]))));

  return (
    <div className="app">
      <div className="map">
        {cmap && <ForgeMap key={gen!.ms + seed} map={cmap} tiles={tiles} view={viewer} />}
        <div className="map-hud">
          {busy && <div className="banner">A gerar a pré-visualização… (5–20 s, mais com muitos reinos)</div>}
          {err && <div className="banner bad" role="alert">{err}</div>}
        </div>
      </div>
      <aside className="panel">
        <header className="panel-head">
          <div>
            <div className="eyebrow">Mestre de jogo</div>
            <h1>Novo mundo</h1>
          </div>
          {onClose && <button type="button" className="link" onClick={onClose}>voltar ao jogo</button>}
        </header>

        <section className="card">
          <h2>Pré-visualização</h2>
          <div className="row gap">
            <label className="small">Semente <input value={seed} onChange={(e) => setSeed(e.target.value)} style={{ width: 110 }} /></label>
            <button type="button" onClick={() => setSeed(newSeed())}>Outra</button>
            <button type="button" className="primary" onClick={preview} disabled={busy}>Gerar</button>
          </div>
          {m && (
            <p className="small">
              {land} províncias · {m.starts.length} reinos de {m.params.startProvinces} · equilíbrio {m.fairness?.score ?? "—"}/100
              {m.fairness ? ` (diferença de valor ${(m.fairness.valueSpread * 100).toFixed(1).replace(".", ",")}%)` : ""} · {(gen!.ms / 1000).toFixed(1)} s
            </p>
          )}
          {m && m.issues.length > 0 && <p className="muted small">Avisos: {m.issues.map((i) => i.message).join("; ")}</p>}
        </section>

        {GROUPS.map((g) => (
          <section className="card" key={g.title}>
            <h2>{g.title}</h2>
            {g.ctl.map((c) => (
              <div className="param" key={c.key}>
                <label htmlFor={`nw-${c.key}`}>{c.label}</label>
                <output>{(c.fmt ?? String)(vals[c.key])}</output>
                <input id={`nw-${c.key}`} type="range" min={c.min} max={c.max} step={c.step} value={vals[c.key]}
                  onChange={(e) => setVals({ ...vals, [c.key]: +e.target.value })} />
                {c.help && <span className="muted small">{c.help}</span>}
              </div>
            ))}
          </section>
        ))}

        <section className="card">
          <h2>Criar este mundo</h2>
          <p className="muted small">O servidor gera o mundo final (com o relevo em todos os níveis de zoom). Demora alguns minutos; podes continuar a jogar entretanto.</p>
          <div className="row gap">
            <input aria-label="Nome do mundo" placeholder="Nome do mundo" value={name} onChange={(e) => setName(e.target.value)} />
            <button type="button" className="primary" onClick={build} disabled={job?.state === "running" || !sameAsPreview}>Criar</button>
          </div>
          {!sameAsPreview && m && <p className="muted small">Mudaste os controlos: gera a pré-visualização antes de criar.</p>}
          {job && (
            <p className={`small ${job.state === "failed" ? "err" : ""}`}>
              «{job.name}»: {job.state === "running" ? `${job.pct}% — ${job.stage}` : job.state === "done" ? "pronto" : `falhou: ${job.error}`}
            </p>
          )}
        </section>

        <section className="card">
          <h2>Mundos criados</h2>
          {started && <p className="small">{started} <a href="./">Abrir o jogo</a></p>}
          {worlds.length === 0 ? <p className="muted small">Ainda nenhum.</p> : (
            <ul className="worlds">
              {worlds.map((w) => (
                <li key={w.dir}>
                  <div><b>{w.name}</b> {w.dir === current && <span className="pill on">em jogo</span>}</div>
                  <div className="muted small">{w.kingdoms} reinos · {w.provinces} províncias · {new Date(w.created).toLocaleString("pt-PT")}</div>
                  {w.dir !== current && (confirmDir === w.dir ? (
                    <div className="row gap">
                      <span className="err small">Isto apaga o jogo atual. As contas ficam e recebem reinos novos.</span>
                      <button type="button" className="danger" onClick={() => startGame(w.dir)}>Confirmar</button>
                      <button type="button" className="link" onClick={() => setConfirmDir(null)}>cancelar</button>
                    </div>
                  ) : <button type="button" onClick={() => setConfirmDir(w.dir)}>Começar um jogo neste mundo</button>)}
                </li>
              ))}
            </ul>
          )}
        </section>
      </aside>
    </div>
  );
}
