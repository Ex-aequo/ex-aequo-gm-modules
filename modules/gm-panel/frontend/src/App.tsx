import { useCallback, useEffect, useMemo, useState } from "react";
import type { MapMarker } from "@map-renderer";
import { api } from "./api";
import { MapView } from "./MapView";
import type {
  ChronicleEntry, GameState, GMOrder, InboxEntry, Intensity, KnownRegion, MapData, Metrics, PlayerView, Preview, RegionDetail,
} from "./types";

const INTENSITY: { value: Intensity; label: string; hint: string }[] = [
  { value: "weak", label: "Fraca", hint: "×0,5" },
  { value: "normal", label: "Normal", hint: "×1" },
  { value: "strong", label: "Forte", hint: "×1,5" },
];
const BIOME_PT: Record<string, string> = {
  "Hot desert": "Deserto quente", "Cold desert": "Deserto frio", Savanna: "Savana", Grassland: "Pradaria",
  "Tropical seasonal forest": "Floresta tropical sazonal", "Temperate deciduous forest": "Floresta temperada",
  "Tropical rainforest": "Floresta tropical húmida", "Temperate rainforest": "Floresta temperada húmida",
  Taiga: "Taiga", Tundra: "Tundra", Glacier: "Glaciar", Wetland: "Pântano", Marine: "Marinho",
};
const BUILDING_PT: Record<string, string> = { farm: "Quinta", sawmill: "Serração", iron_mine: "Mina de ferro", gold_mine: "Mina de ouro" };
const pct = (x: number) => `${(x * 100).toFixed(1).replace(".", ",")}%`;
const SIZE_PT = ["pequena", "média", "grande", "enorme"];
const PLAGUE_PT = ["limpa", "contaminada", "infestada", "perdida"];
const LEVEL_PT = ["", "conhecida", "visível", "espiada", "tua"];

export function App() {
  const [game, setGame] = useState<GameState | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [showPreview, setShowPreview] = useState(false);
  const [previewTurns, setPreviewTurns] = useState(10);
  const [names, setNames] = useState<Map<number, string>>(new Map());
  const [focusMode, setFocusMode] = useState(false);
  const [confirmFocus, setConfirmFocus] = useState<number | null>(null);
  const [selected, setSelected] = useState(0);
  const [detail, setDetail] = useState<RegionDetail | null>(null);
  const [hover, setHover] = useState(0);
  const [focusTarget, setFocusTarget] = useState(0);
  const [busy, setBusy] = useState<string | null>(null);
  const [viewAs, setViewAs] = useState(0);              // 0 = GM (tudo); senão, a vista de uma fação
  const [view, setView] = useState<PlayerView | null>(null);
  const [error, setError] = useState<string | null>(null);

  const run = useCallback(async <T,>(label: string, fn: () => Promise<T>): Promise<T | undefined> => {
    setBusy(label);
    setError(null);
    try {
      return await fn();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }, []);

  useEffect(() => { run("A carregar", async () => setGame(await api.state())); }, [run]);
  useEffect(() => {
    if (!viewAs) { setView(null); return; }
    run("A ler a vista do jogador", async () => setView(await api.view(viewAs)));
  }, [viewAs, game?.turn, run]);
  // ao mudar de fação, o mapa vai ter com ela
  const [centredOn, setCentredOn] = useState(0);
  useEffect(() => {
    if (!view || view.faction.id === centredOn) return;
    const home = view.armies[0]?.region ?? Number(Object.keys(view.regions).find((k) => view.regions[k].level === 4));
    if (home) setFocusTarget(home);
    setCentredOn(view.faction.id);
  }, [view, centredOn]);

  const regionName = (id: number) => names.get(id) ?? `região ${id}`;
  const knownTo = (id: number) => !view || (view.fog[id] ?? 0) > 0;
  const factionName = (id: number) =>
    id === -1 ? "A Praga" : id === 0 ? "Terras livres" : game?.factions.find((f) => f.id === id)?.name ?? `fação ${id}`;

  // qualquer mudança nas ordens ou no turno invalida a previsão
  const invalidatePreview = () => { setPreview(null); setShowPreview(false); };

  const addOrder = (o: GMOrder) =>
    run("A registar ordem", async () => {
      const { pending } = await api.addOrder(o);
      setGame((g) => (g ? { ...g, pending } : g));
      invalidatePreview();
    });
  const removeOrder = (i: number) =>
    run("A retirar ordem", async () => {
      const { pending } = await api.removeOrder(i);
      setGame((g) => (g ? { ...g, pending } : g));
      invalidatePreview();
    });
  const resolve = () =>
    run("A resolver o turno", async () => {
      setGame(await api.resolve());
      invalidatePreview();
      if (selected) setDetail(await api.region(selected));
    });
  const simulate = () =>
    run("A simular", async () => {
      setPreview(await api.preview(previewTurns));
      setShowPreview(true);
    });
  const reset = () =>
    run("A recomeçar", async () => {
      setGame(await api.reset(`s${Date.now() % 100000}`));
      invalidatePreview();
      setSelected(0);
      setDetail(null);
    });

  const onRegionClick = (id: number) => {
    if (!id) return;
    if (focusMode) { setConfirmFocus(id); return; }
    setSelected(id);
    if (!viewAs) run("A ler região", async () => setDetail(await api.region(id)));
  };

  const markers = useMemo<MapMarker[]>(() => {
    if (!game || viewAs) return [];
    const pendingFoci = game.pending.filter((o): o is Extract<GMOrder, { type: "plague_focus" }> => o.type === "plague_focus").map((o) => o.region);
    const list: MapMarker[] = game.suggested_foci.filter((r) => !pendingFoci.includes(r)).map((r) => ({ region: r, kind: "suggestion" }));
    for (const r of pendingFoci) list.push({ region: r, kind: "pending", label: "foco pendente" });
    if (confirmFocus) list.push({ region: confirmFocus, kind: "pending", label: "confirmar?" });
    return list;
  }, [game, confirmFocus, viewAs]);

  if (!game) {
    return <div className="boot">{error ? `Não foi possível ligar ao servidor: ${error}` : "A carregar o mundo…"}</div>;
  }
  const shown = showPreview && preview ? preview : game;
  const m = game.metrics;
  const pendingState = game.pending.find((o) => o.type === "plague_state") as Extract<GMOrder, { type: "plague_state" }> | undefined;
  const pendingIntensity = game.pending.find((o) => o.type === "plague_intensity") as Extract<GMOrder, { type: "plague_intensity" }> | undefined;
  const nextActive = pendingState ? pendingState.value === "active" : game.plague_active;
  const nextIntensity = pendingIntensity?.value ?? game.plague_intensity;
  const leader = game.factions.find((f) => f.id === m.leader);
  const mapData: MapData = view
    ? { owner: view.owner, plague: view.plague, fog: view.fog, factions: [...view.map_factions, game.praga] }
    : { owner: shown.owner, plague: shown.plague, fog: null, factions: [...shown.factions, game.praga] };

  return (
    <div className="app">
      <MapView
        data={mapData}
        markers={markers}
        selected={selected}
        focusTarget={focusTarget}
        onRegionClick={onRegionClick}
        onHover={setHover}
        onReady={setNames}
      />
      <div className="map-hud">
        {showPreview && preview && (
          <div className="banner preview">
            Previsão: turno {preview.from_turn + preview.turns}
            <button type="button" className="link" onClick={() => setShowPreview(false)}>voltar ao presente</button>
          </div>
        )}
        {focusMode && (
          <div className="banner focus">
            Clica na região onde a Praga vai abrir um foco
            <button type="button" className="link" onClick={() => { setFocusMode(false); setConfirmFocus(null); }}>cancelar</button>
          </div>
        )}
        {view && (
          <div className="banner view">
            A ver como <b>{view.faction.name}</b>: só o que esta fação sabe
            <button type="button" className="link" onClick={() => setViewAs(0)}>voltar à vista do GM</button>
          </div>
        )}
        {hover > 0 && <div className="hover-name">{knownTo(hover) ? regionName(hover) : "Terra desconhecida"}</div>}
      </div>

      <aside className="panel">
        <header className="panel-head">
          <div>
            <div className="eyebrow">Mestre de jogo · sandbox</div>
            <h1>Praga</h1>
          </div>
          <div className="turn-box">
            <div className="turn">Turno {game.turn}</div>
            <button type="button" className="primary" onClick={resolve} disabled={!!busy}>
              Resolver turno
            </button>
          </div>
        </header>
        {(busy || error) && <div className={`status ${error ? "err" : ""}`} role="status">{error ?? `${busy}…`}</div>}

        <section className="card">
          <h2>Ver como jogador</h2>
          <p className="muted small">O mapa e as mensagens mostram só o que essa fação sabe — o mesmo que o servidor lhe enviaria.</p>
          <select aria-label="Ver como" value={viewAs} onChange={(e) => { setViewAs(+e.target.value); setDetail(null); setSelected(0); }}>
            <option value={0}>Mestre de jogo (tudo)</option>
            {game.factions.filter((f) => f.active).map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
          </select>
          {view && <PlayerCard v={view} selected={selected} regionName={regionName} factionName={factionName} />}
        </section>

        <section className="card">
          <h2>Estado do mundo</h2>
          <div className="stats">
            <Stat label="Perdido para a Praga" value={pct(m.lost)} tone="plague" />
            <Stat label="Contaminado" value={pct(m.contaminated)} tone="warn" />
            <Stat label="Maior fação" value={leader ? `${leader.name}` : "—"} sub={leader ? `${m.leader_regions} regiões · ${pct(m.leader_regions / (game.owner.length - 1))}` : ""} />
          </div>
          <Sparkline history={game.history} />
        </section>

        <section className="card">
          <h2>A Praga</h2>
          <div className="row">
            <span className={`pill ${game.plague_active ? "on" : "off"}`}>{game.plague_active ? "Ativa" : "Adormecida"}</span>
            {game.plague_active && <span className="muted">intensidade {INTENSITY.find((i) => i.value === game.plague_intensity)?.label.toLowerCase()}</span>}
          </div>
          <div className="row gap">
            <button type="button" className={nextActive ? "" : "danger"} disabled={!!busy}
              onClick={() => addOrder({ type: "plague_state", value: nextActive ? "dormant" : "active" })}>
              {nextActive ? "Adormecer a Praga" : "Despertar a Praga"}
            </button>
            <button type="button" className={focusMode ? "active" : ""} disabled={!!busy}
              onClick={() => { setFocusMode(!focusMode); setConfirmFocus(null); }}>
              Abrir foco…
            </button>
          </div>
          <div className="segmented" role="radiogroup" aria-label="Intensidade">
            {INTENSITY.map((i) => (
              <button key={i.value} type="button" role="radio" aria-checked={nextIntensity === i.value}
                className={nextIntensity === i.value ? "on" : ""} disabled={!!busy}
                onClick={() => nextIntensity !== i.value && addOrder({ type: "plague_intensity", value: i.value })}>
                {i.label} <small>{i.hint}</small>
              </button>
            ))}
          </div>

          {confirmFocus !== null && (
            <div className="confirm">
              <p><b>Abrir um foco em {regionName(confirmFocus)}?</b></p>
              <p className="muted">
                A região fica perdida para a Praga e as vizinhas contaminadas. É irreversível e aparece na crónica pública.
                {game.owner[confirmFocus] > 0 && <> Pertence a <b>{factionName(game.owner[confirmFocus])}</b>.</>}
              </p>
              <div className="row gap">
                <button type="button" className="danger" disabled={!!busy} onClick={async () => {
                  const region = confirmFocus;
                  setConfirmFocus(null); setFocusMode(false);
                  await addOrder({ type: "plague_focus", region });
                  // um foco numa Praga adormecida não faz nada: desperta-a na mesma ordem de turno
                  if (!nextActive) await addOrder({ type: "plague_state", value: "active" });
                }}>Confirmar foco</button>
                <button type="button" onClick={() => setConfirmFocus(null)}>Cancelar</button>
              </div>
            </div>
          )}

          {game.suggested_foci.length > 0 && (
            <>
              <h3>Focos sugeridos</h3>
              <p className="muted small">Longe das capitais e uns dos outros. Marcados no mapa com círculo tracejado.</p>
              <ul className="chips">
                {game.suggested_foci.map((r) => (
                  <li key={r}>
                    <button type="button" className="chip" onClick={() => { setFocusTarget(r); setFocusMode(true); setConfirmFocus(r); }}>
                      {regionName(r)}
                    </button>
                  </li>
                ))}
              </ul>
            </>
          )}
        </section>

        <RumourCard factions={game.factions.filter((f) => f.active)} selected={viewAs ? 0 : selected}
          regionName={regionName} busy={!!busy} onSend={addOrder} />

        <section className="card">
          <h2>Ordens para o próximo turno</h2>
          {game.pending.length === 0 ? (
            <p className="muted">Sem ordens. O turno resolve-se só com as ações das fações.</p>
          ) : (
            <ol className="orders">
              {game.pending.map((o, i) => (
                <li key={i}>
                  <span>{describeOrder(o, regionName)}</span>
                  <button type="button" className="icon" aria-label="Retirar ordem" onClick={() => removeOrder(i)}>×</button>
                </li>
              ))}
            </ol>
          )}
        </section>

        <section className="card">
          <h2>Pré-visualização</h2>
          <p className="muted small">Simula os próximos turnos com as ordens acima, sem mudar o mundo. Com bots é exata; com jogadores reais será uma estimativa.</p>
          <div className="row gap">
            <select id="preview-turns" value={previewTurns} onChange={(e) => { setPreviewTurns(+e.target.value); invalidatePreview(); }}>
              {[5, 10, 20, 30].map((n) => <option key={n} value={n}>{n} turnos ({n * 2} dias)</option>)}
            </select>
            <button type="button" onClick={simulate} disabled={!!busy}>Simular</button>
          </div>
          {preview && <PreviewResult p={preview} now={m} show={showPreview} onToggle={() => setShowPreview(!showPreview)} />}
        </section>

        {detail && (
          <section className="card">
            <h2>Região</h2>
            <RegionCard d={detail} factionName={factionName} onClose={() => { setDetail(null); setSelected(0); }} />
          </section>
        )}

        <section className="card">
          <h2>Fações</h2>
          <table className="factions">
            <thead>
              <tr><th></th><th>Fação</th><th className="num">Regiões</th><th className="num">Δ10</th><th className="num">Homens</th></tr>
            </thead>
            <tbody>
              {game.factions.filter((f) => f.active).map((f) => (
                <tr key={f.id}>
                  <td><span className="sw" style={{ background: f.color }} /></td>
                  <td>{f.name}<div className="muted small">{f.style}{f.protected ? " · protegida" : ""}</div></td>
                  <td className="num">{f.regions}</td>
                  <td className={`num ${f.growth10 > 0 ? "up" : f.growth10 < 0 ? "down" : ""}`}>{f.growth10 > 0 ? `+${f.growth10}` : f.growth10}</td>
                  <td className="num">{f.men.toLocaleString("pt-PT")}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {game.factions.some((f) => !f.active) && (
            <p className="muted small">Fora do jogo: {game.factions.filter((f) => !f.active).map((f) => f.name).join(", ")}</p>
          )}
        </section>

        <section className="card">
          <h2>Crónica</h2>
          <Chronicle entries={game.chronicle} onRegion={(r) => setFocusTarget(r)} />
        </section>

        <footer className="panel-foot">
          <button type="button" className="link" onClick={reset} disabled={!!busy}>Recomeçar o mundo (nova seed)</button>
        </footer>
      </aside>
    </div>
  );
}

function describeOrder(o: GMOrder, name: (id: number) => string) {
  if (o.type === "plague_state") return o.value === "active" ? "Despertar a Praga" : "Adormecer a Praga";
  if (o.type === "plague_intensity") return `Intensidade ${INTENSITY.find((i) => i.value === o.value)?.label.toLowerCase()}`;
  if (o.type === "rumor") {
    const to = o.factions ? `${o.factions.length} fação(ões)` : `fações a ≤${o.radius} regiões de ${name(o.region!)}`;
    return `Rumor para ${to}: “${o.text.length > 60 ? o.text.slice(0, 60) + "…" : o.text}”`;
  }
  return `Abrir foco em ${name(o.region)}`;
}

function Stat({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone?: string }) {
  return (
    <div className={`stat ${tone ?? ""}`}>
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      {sub && <div className="stat-sub">{sub}</div>}
    </div>
  );
}

function Sparkline({ history }: { history: Metrics[] }) {
  const W = 320, H = 70, P = 4;
  if (history.length < 2) return <p className="muted small">O gráfico aparece a partir do segundo turno.</p>;
  // escala vertical ajustada: até 10% no início, para as primeiras perdas se verem
  const top = Math.min(1, Math.max(0.1, ...history.map((h) => Math.max(h.lost, h.contaminated))) * 1.2);
  const x = (i: number) => P + (i / (history.length - 1)) * (W - 2 * P);
  const y = (v: number) => H - P - (v / top) * (H - 2 * P);
  const line = (key: "lost" | "contaminated") => history.map((h, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(h[key]).toFixed(1)}`).join("");
  // faixas em que a Praga esteve ativa
  const bands: [number, number][] = [];
  history.forEach((h, i) => {
    if (!h.plague_active) return;
    const last = bands[bands.length - 1];
    if (last && last[1] === i - 1) last[1] = i; else bands.push([i, i]);
  });
  return (
    <figure className="spark">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Evolução da Praga por turno">
        {bands.map(([a, b]) => <rect key={a} x={x(a)} y={0} width={Math.max(2, x(b) - x(a))} height={H} className="band" />)}
        {[0.25, 0.5, 0.75].map((f) => <line key={f} x1={P} x2={W - P} y1={y(f * top)} y2={y(f * top)} className="grid" />)}
        <path d={line("contaminated")} className="l-cont" />
        <path d={line("lost")} className="l-lost" />
      </svg>
      <figcaption>
        <span className="key lost" /> perdido <span className="key cont" /> contaminado <span className="key band" /> Praga ativa
        <span className="muted"> · turnos 1–{history[history.length - 1].turn}, topo {pct(top)}</span>
      </figcaption>
    </figure>
  );
}

function PreviewResult({ p, now, show, onToggle }: { p: Preview; now: Metrics; show: boolean; onToggle: () => void }) {
  const end = p.series[p.series.length - 1];
  const delta = end.lost - now.lost;
  return (
    <div className="preview-result">
      <div className="stats">
        <Stat label={`Perdido no turno ${p.from_turn + p.turns}`} value={pct(end.lost)} sub={`${delta >= 0 ? "+" : ""}${pct(delta)} face a hoje`} tone="plague" />
        <Stat label="Regiões que caem" value={String(p.newly_lost.length)} />
      </div>
      {p.factions_hit.length > 0 ? (
        <p className="small">Fações mais atingidas: {p.factions_hit.map((f) => `${f.name} (−${f.lost})`).join(", ")}.</p>
      ) : (
        <p className="small muted">Nenhuma fação perde regiões para a Praga neste período.</p>
      )}
      <button type="button" onClick={onToggle}>{show ? "Ver o presente no mapa" : "Ver a previsão no mapa"}</button>
    </div>
  );
}

function RegionCard({ d, factionName, onClose }: { d: RegionDetail; factionName: (id: number) => string; onClose: () => void }) {
  return (
    <div className="region">
      <div className="region-head">
        <div>
          <div className="region-name">{d.name}</div>
          <div className="muted small">{BIOME_PT[d.biome] ?? d.biome}{d.coastal ? " · costeira" : ""}{d.suggested_focus ? " · foco sugerido" : ""}</div>
        </div>
        <button type="button" className="icon" aria-label="Fechar" onClick={onClose}>×</button>
      </div>
      <dl>
        <dt>Senhor</dt><dd>{factionName(d.owner)}</dd>
        <dt>Praga</dt><dd>{d.plague}%<div className="bar"><i style={{ width: `${d.plague}%` }} /></div></dd>
        <dt>População</dt><dd>{Math.round(d.pop)} mil</dd>
        <dt>Ordem pública</dt><dd>{d.order} / 3</dd>
        <dt>Fortificação</dt><dd>{d.fort} / 3</dd>
        <dt>Edifício</dt><dd>{d.building ? `${BUILDING_PT[d.building] ?? d.building} nível ${d.level}` : "—"}</dd>
        <dt>Exércitos</dt><dd>{d.armies.length ? d.armies.map((a) => `${a.men} (${factionName(a.owner)})`).join(", ") : d.garrison ? `guarnição neutra ${d.garrison}` : "—"}</dd>
      </dl>
    </div>
  );
}

function Chronicle({ entries, onRegion }: { entries: ChronicleEntry[]; onRegion: (r: number) => void }) {
  const list = [...entries].reverse().slice(0, 60);
  return (
    <ul className="chronicle">
      {list.map((e, i) => (
        <li key={i} className={`k-${e.kind}`}>
          <span className="t">T{e.turn}</span>
          <span>
            {e.text}
            {e.regions && e.regions.length > 0 && (
              <button type="button" className="link small" onClick={() => onRegion(e.regions![0])}> ver no mapa</button>
            )}
          </span>
        </li>
      ))}
    </ul>
  );
}

function RumourCard({ factions, selected, regionName, busy, onSend }: {
  factions: { id: number; name: string }[]; selected: number; regionName: (id: number) => string; busy: boolean;
  onSend: (o: GMOrder) => Promise<unknown>;
}) {
  const [text, setText] = useState("");
  const [mode, setMode] = useState<"faction" | "region">("faction");
  const [target, setTarget] = useState(factions[0]?.id ?? 0);
  const [radius, setRadius] = useState(6);
  const canSend = text.trim().length > 0 && (mode === "faction" ? target > 0 : selected > 0);
  const send = async () => {
    const o: GMOrder = mode === "faction"
      ? { type: "rumor", text: text.trim(), factions: [target] }
      : { type: "rumor", text: text.trim(), region: selected, radius };
    await onSend(o);
    setText("");
  };
  return (
    <section className="card">
      <h2>Rumores</h2>
      <p className="muted small">Chegam às fações no próximo turno, como mensagem. Podem ser verdadeiros ou falsos.</p>
      <textarea rows={3} maxLength={500} value={text} placeholder="Ex.: Mercadores falam de luzes estranhas nas montanhas a norte."
        aria-label="Texto do rumor" onChange={(e) => setText(e.target.value)} />
      <div className="segmented" role="radiogroup" aria-label="Destino">
        <button type="button" role="radio" aria-checked={mode === "faction"} className={mode === "faction" ? "on" : ""}
          onClick={() => setMode("faction")}>Uma fação</button>
        <button type="button" role="radio" aria-checked={mode === "region"} className={mode === "region" ? "on" : ""}
          onClick={() => setMode("region")}>À volta de uma região</button>
      </div>
      <div className="row gap">
        {mode === "faction" ? (
          <select aria-label="Fação" value={target} onChange={(e) => setTarget(+e.target.value)}>
            {factions.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
          </select>
        ) : (
          <>
            <span className="small">{selected ? regionName(selected) : "clica numa região no mapa"}</span>
            <select aria-label="Raio" value={radius} onChange={(e) => setRadius(+e.target.value)}>
              {[3, 6, 10, 15].map((r) => <option key={r} value={r}>até {r} regiões</option>)}
            </select>
          </>
        )}
        <button type="button" onClick={send} disabled={busy || !canSend}>Enviar</button>
      </div>
    </section>
  );
}

function PlayerCard({ v, selected, regionName, factionName }: {
  v: PlayerView; selected: number; regionName: (id: number) => string; factionName: (id: number) => string;
}) {
  const scouts = v.agents.filter((a) => a.kind === "scout").length;
  const spies = v.agents.length - scouts;
  const r = selected ? v.regions[String(selected)] : undefined;
  return (
    <div className="player">
      <div className="stats">
        <Stat label="Mapa conhecido" value={pct(v.known_share)} />
        <Stat label="Fações conhecidas" value={String(v.factions.length)} />
        <Stat label="Batedores · espiões" value={`${scouts} · ${spies}`} />
      </div>
      <p className="small muted">
        Ouro {Math.round(v.faction.stock.gold)} · comida {Math.round(v.faction.stock.food)} · madeira {Math.round(v.faction.stock.wood)}
        {" "}· ferro {Math.round(v.faction.stock.iron)} · {v.faction.command_points} pontos de comando
      </p>
      {selected > 0 && <KnownRegionCard id={selected} r={r} turn={v.turn} regionName={regionName} factionName={factionName} />}
      <h3>Mensagens</h3>
      <Inbox entries={v.inbox} />
    </div>
  );
}

function KnownRegionCard({ id, r, turn, regionName, factionName }: {
  id: number; r: KnownRegion | undefined; turn: number; regionName: (id: number) => string; factionName: (id: number) => string;
}) {
  if (!r) return <div className="region"><div className="region-name">Terra desconhecida</div><p className="muted small">Ninguém desta fação esteve lá.</p></div>;
  const armies = r.x ? r.x.armies.map(([o, men]) => `${men} (${factionName(o)})`)
    : (r.a ?? []).map(([o, b]) => `força ${SIZE_PT[b]} (${factionName(o)})`);
  return (
    <div className="region">
      <div className="region-name">{regionName(id)}</div>
      <div className="muted small">{LEVEL_PT[r.level]}{r.level === 1 ? ` · visto no turno ${r.t} (há ${turn - r.t} turnos)` : ""}</div>
      <dl>
        <dt>Senhor</dt><dd>{factionName(r.o)}</dd>
        <dt>Praga</dt><dd>{r.plague !== undefined ? `${r.plague}%` : PLAGUE_PT[r.p ?? 0]}</dd>
        <dt>Fortificação</dt><dd>{r.fort ?? r.f ?? 0} / 3</dd>
        <dt>Exércitos</dt><dd>{armies.length ? armies.join(", ") : r.g !== undefined ? `guarnição ${SIZE_PT[r.g]}` : "—"}</dd>
      </dl>
    </div>
  );
}

function Inbox({ entries }: { entries: InboxEntry[] }) {
  if (!entries.length) return <p className="muted small">Sem mensagens.</p>;
  const label = { rumour: "Rumor", gm: "Rumor", report: "Relatório" } as const;
  return (
    <ul className="chronicle">
      {[...entries].reverse().slice(0, 15).map((e, i) => (
        <li key={i} className={`k-${e.kind === "report" ? "faction" : "plague"}`}>
          <span className="t">T{e.turn}</span>
          <span><b>{label[e.kind]}.</b> {e.text}</span>
        </li>
      ))}
    </ul>
  );
}

