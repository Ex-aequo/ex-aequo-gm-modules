import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ClientMap } from "@pf/map/clientMap";
import { ForgeMap, GameTiles, type Camera, type MapPath, type Marker } from "@forge-view/ForgeMap";
import { api, ApiError } from "./api";
import type { KnownRegion, Me, Order, PlayerState } from "./types";

const RES_PT: Record<string, string> = { gold: "ouro", food: "comida", wood: "madeira", iron: "ferro" };
const BUILDING_PT: Record<string, string> = {
  farm: "Quinta", sawmill: "Serração", iron_mine: "Mina de ferro", gold_mine: "Mina de ouro", fort: "Fortificação",
  upgrade: "Subir de nível",
};
const SIZE_PT = ["pequena", "média", "grande", "enorme"];
const PLAGUE_PT = ["limpa", "contaminada", "infestada", "perdida para a Praga"];
const LEVEL_PT = ["", "conhecida (fotografia antiga)", "visível", "espiada", "tua"];
const TERRAIN_PT: Record<string, string> = {
  plains: "planície", forest: "floresta", hills: "colinas", mountains: "montanhas", desert: "deserto",
  marsh: "pântano", jungle: "selva", tundra: "tundra",
};
const RESOURCE_PT: Record<string, string> = {
  grain: "cereal", wood: "madeira", stone: "pedra (fortificações a metade do preço)", iron: "ferro",
  horses: "cavalos (ainda sem efeito)", salt: "sal (ainda sem efeito)", gold: "ouro (permite mina de ouro)",
  spices: "especiarias (ainda sem efeito)",
};
const POSTURE_PT: Record<string, string> = { ally: "Aliado", neutral: "Neutro", hostile: "Hostil" };
const cost = (c: Record<string, number>) => Object.entries(c).map(([k, v]) => `${Math.round(v)} ${RES_PT[k] ?? k}`).join(" · ");

export function App() {
  const [me, setMe] = useState<Me | null>(null);
  const [checked, setChecked] = useState(false);
  useEffect(() => {
    api.me().then(setMe).catch(() => setMe(null)).finally(() => setChecked(true));
  }, []);
  if (!checked) return <div className="boot">A carregar…</div>;
  if (!me) return <Login onLogin={(m) => setMe(m)} />;
  if (me.role === "gm") {
    return (
      <div className="boot">
        <div>Estás ligado como mestre de jogo. <a href="/gm/">Abrir o painel do GM</a>
          <p><button type="button" className="link" onClick={() => api.logout().then(() => setMe(null))}>Sair</button></p>
        </div>
      </div>
    );
  }
  return <Game me={me} onLogout={() => api.logout().finally(() => setMe(null))} />;
}

function Login({ onLogin }: { onLogin: (m: Me) => void }) {
  const [user, setUser] = useState("");
  const [pw, setPw] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      await api.login(user, pw);
      onLogin(await api.me());
    } catch (x) {
      setErr((x as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="login">
      <form className="login-card" onSubmit={submit}>
        <h1>Praga</h1>
        <p className="muted">Entra no teu reino.</p>
        <label>Nome<input value={user} onChange={(e) => setUser(e.target.value)} autoComplete="username" autoFocus /></label>
        <label>Palavra-passe<input type="password" value={pw} onChange={(e) => setPw(e.target.value)} autoComplete="current-password" /></label>
        {err && <p className="err" role="alert">{err}</p>}
        <button type="submit" className="primary" disabled={busy || !user || !pw}>Entrar</button>
      </form>
    </div>
  );
}

type Mode = null | { type: "move" | "agent_move"; unit: number; path: number[] } | { type: "attack"; army: number };
type Sel = { kind: "region" | "army" | "agent"; id: number } | null;

function Game({ me, onLogout }: { me: Me; onLogout: () => void }) {
  const [st, setSt] = useState<PlayerState | null>(null);
  const [orders, setOrders] = useState<Order[]>([]);
  const [cmap, setCmap] = useState<ClientMap | null>(null);
  const [sel, setSel] = useState<Sel>(null);
  const [mode, setMode] = useState<Mode>(null);
  const [hover, setHover] = useState(0);
  const [msg, setMsg] = useState<{ text: string; bad?: boolean } | null>(null);
  const [now, setNow] = useState(Date.now());
  const camera = useRef<Camera | null>(null);
  const turnRef = useRef(0);

  const load = useCallback(async () => {
    try {
      const s = await api.state();
      if (s.clock.turn !== turnRef.current) {
        if (turnRef.current) setMsg({ text: `Começou o turno ${s.clock.turn}. O mapa e as mensagens foram atualizados.` });
        turnRef.current = s.clock.turn;
        setSel(null);
        setMode(null);
        // o mapa (só o que o reino conhece) muda com o turno
        const r = await fetch("/api/map/client-map.json", { credentials: "same-origin" });
        if (!r.ok) throw new ApiError(r.status, "o mapa não carregou");
        setCmap(await r.json());
      }
      setSt(s);
      setOrders(s.orders);
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) onLogout();
      else setMsg({ text: (e as Error).message, bad: true });
    }
  }, [onLogout]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    const t = setInterval(load, 20000);
    const c = setInterval(() => setNow(Date.now()), 15000);
    return () => { clearInterval(t); clearInterval(c); };
  }, [load]);

  const me_id = st?.faction.id ?? 0;
  const factionName = useCallback((id: number) => {
    if (id === -1) return "a Praga";
    if (id === 0) return "Terras Livres";
    if (id === me_id) return st?.faction.name ?? "tu";
    const f = st?.factions.find((x) => x.id === id) ?? st?.map_factions.find((x) => x.id === id);
    return f ? f.name : `reino ${id}`;
  }, [st, me_id]);
  /** Nome de uma província do Praga (rid); no Province-Forge é a região rid - 1. */
  const regionName = useCallback((id: number) => cmap?.regions[id - 1]?.name?.pt ?? "Terra desconhecida", [cmap]);
  const tiles = useMemo(() => (cmap?.tiles ? new GameTiles(`/api/map/t${st?.clock.turn ?? 0}/tiles`, cmap.tiles) : null),
    [cmap]); // eslint-disable-line react-hooks/exhaustive-deps

  const submit = useCallback(async (next: Order[], added?: Order) => {
    try {
      const r = await api.orders(next);
      setOrders(r.accepted);
      const lastErr = added ? r.errors.find((e) => new RegExp(`^ordem ${next.length - 1}\\b`).test(e)) : undefined;
      if (lastErr) {
        setMsg({ text: `Ordem recusada: ${lastErr.replace(/^ordem \d+\s*(\([^)]*\))?:\s*/, "")}`, bad: true });
      } else if (r.errors.length) {
        setMsg({ text: `Algumas ordens deixaram de ser válidas e foram retiradas: ${r.errors.join("; ")}`, bad: true });
      } else {
        setMsg(null);
      }
    } catch (e) {
      setMsg({ text: (e as Error).message, bad: true });
    }
  }, []);

  /** Junta uma ordem, substituindo a que já existir para o mesmo exército, agente, região ou fação. */
  const addOrder = (o: Order) => {
    const same = (x: Order) =>
      ("army" in x && "army" in o && x.army === o.army) ||
      ("agent" in x && "agent" in o && x.agent === o.agent) ||
      (x.type === o.type && "region" in x && "region" in o && x.region === o.region) ||
      (x.type === "posture" && o.type === "posture" && x.faction === o.faction);
    const next = [...orders.filter((x) => !same(x)), o];
    submit(next, o);
    setMode(null);
  };
  const removeOrder = (i: number) => submit(orders.filter((_, j) => j !== i));

  const onSelect = (pf: number | null) => {
    onClick(pf !== null && cmap?.regions[pf]?.kind === "land" ? pf + 1 : 0);
  };
  const onClick = (id: number) => {
    if (!st) return;
    if (mode?.type === "attack") {
      if (id) addOrder({ type: "attack", army: mode.army, target: id });
      return;
    }
    if (mode && (mode.type === "move" || mode.type === "agent_move")) {
      if (!id) return;
      const path = [...mode.path, id];
      const maxSteps = mode.type === "move" ? 2 : (st.agents.find((a) => a.id === mode.unit)?.kind === "scout" ? 2 : 1);
      if (path.length >= maxSteps) {
        addOrder(mode.type === "move" ? { type: "move", army: mode.unit, path } : { type: "agent_move", agent: mode.unit, path });
      } else {
        setMode({ ...mode, path });
      }
      return;
    }
    if (!id) { setSel(null); return; }
    const army = st.armies.find((a) => a.region === id);
    setSel(army && !(sel?.kind === "army" && sel.id === army.id) ? { kind: "army", id: army.id } : { kind: "region", id });
  };

  const markers = useMemo<Marker[]>(() => {
    if (!st) return [];
    const list: Marker[] = [];
    for (const a of st.armies) list.push({ region: a.region, kind: "army", label: String(a.men), selected: sel?.kind === "army" && sel.id === a.id });
    for (const [rid, r] of Object.entries(st.regions)) {
      if (r.level < 2) continue;
      const foes = (r.a ?? []).filter(([o]) => o !== me_id);
      if (foes.length) list.push({ region: +rid, kind: "foe", label: SIZE_PT[Math.max(...foes.map(([, b]) => b))] });
    }
    for (const g of st.agents) list.push({ region: g.region, kind: "agent", selected: sel?.kind === "agent" && sel.id === g.id });
    if (mode?.type === "attack") {
      const a = st.armies.find((x) => x.id === mode.army);
      if (a) list.push({ region: a.region, kind: "target", label: "atacar onde?" });
    }
    return list;
  }, [st, sel, mode, me_id]);

  const paths = useMemo<MapPath[]>(() => {
    if (!st) return [];
    const armyAt = (id: number) => st.armies.find((a) => a.id === id)?.region;
    const agentAt = (id: number) => st.agents.find((a) => a.id === id)?.region;
    const out: MapPath[] = [];
    for (const o of orders) {
      if (o.type === "move") { const s = armyAt(o.army); if (s) out.push({ kind: "move", regions: [s, ...o.path] }); }
      if (o.type === "attack") { const s = armyAt(o.army); if (s) out.push({ kind: "attack", regions: [s, o.target] }); }
      if (o.type === "agent_move") { const s = agentAt(o.agent); if (s) out.push({ kind: "agent", regions: [s, ...o.path] }); }
    }
    if (mode && mode.type !== "attack" && mode.path.length) {
      const s = mode.type === "move" ? armyAt(mode.unit) : agentAt(mode.unit);
      if (s) out.push({ kind: mode.type === "move" ? "move" : "agent", regions: [s, ...mode.path] });
    }
    return out;
  }, [st, orders, mode]);

  // o mapa trabalha com ids do Province-Forge (pf = rid - 1)
  const markersPf = useMemo(() => markers.map((m) => ({ ...m, region: m.region - 1 })), [markers]);
  const pathsPf = useMemo(() => paths.map((p) => ({ ...p, regions: p.regions.map((r) => r - 1) })), [paths]);

  if (!st || !cmap) return <div className="boot">{msg?.text ?? "A carregar o reino…"}</div>;

  const used = orders.reduce((s, o) => s + (st.order_cost[o.type] ?? 0), 0);
  const total = st.faction.command_points;
  const home = st.armies[0]?.region ?? Number(Object.keys(st.regions).find((k) => st.regions[k].level === 4) ?? 0);
  const deadline = st.clock.deadline ? new Date(st.clock.deadline).getTime() : null;
  const left = deadline ? Math.max(0, Math.round((deadline - now) / 60000)) : null;

  return (
    <div className="app">
      <div className="map">
        <ForgeMap map={cmap} tiles={tiles} view={st.viewer} markers={markersPf} paths={pathsPf}
          selected={sel?.kind === "region" ? sel.id - 1 : null} home={home - 1} camera={camera}
          onSelect={onSelect} onHover={(pf) => setHover(pf !== null && cmap.regions[pf]?.kind === "land" ? pf + 1 : 0)} />
      </div>
      <div className="map-hud">
        {mode && (
          <div className="banner">
            {mode.type === "attack" ? "Clica na região a atacar" :
              mode.path.length === 0 ? "Clica na região para onde vai" : "Clica na segunda região, ou confirma"}
            {mode.type !== "attack" && mode.path.length > 0 && (
              <button type="button" className="link" onClick={() => addOrder(mode.type === "move"
                ? { type: "move", army: mode.unit, path: mode.path } : { type: "agent_move", agent: mode.unit, path: mode.path })}>
                confirmar
              </button>
            )}
            <button type="button" className="link" onClick={() => setMode(null)}>cancelar</button>
          </div>
        )}
        {msg && (
          <div className={`banner ${msg.bad ? "bad" : ""}`} role="status">
            {msg.text}<button type="button" className="link" onClick={() => setMsg(null)}>fechar</button>
          </div>
        )}
        {hover > 0 && <div className="hover-name">{regionName(hover)}</div>}
      </div>

      <aside className="panel">
        <header className="panel-head">
          <div>
            <div className="eyebrow">{me.world} · {me.username}</div>
            <h1>{st.faction.name}</h1>
          </div>
          <div className="turn-box">
            <div className="turn">Turno {st.clock.turn}</div>
            <div className="muted small">
              {left !== null ? `fecha daqui a ${left} min` : "o mestre de jogo fecha o turno"}
            </div>
            <button type="button" className="link small" onClick={onLogout}>sair</button>
          </div>
        </header>

        <section className="card">
          <div className="stock">
            {Object.entries(st.faction.stock).map(([k, v]) => (
              <div key={k}><span className="muted small">{RES_PT[k]}</span><b>{Math.round(v)}</b></div>
            ))}
            <div><span className="muted small">comando</span><b className={used > total ? "over" : ""}>{used}/{total}</b></div>
          </div>
          {st.faction.famine && <p className="err small">Fome! Os exércitos perdem homens enquanto faltar comida.</p>}
          {st.faction.protected_until >= st.clock.turn && (
            <p className="muted small">Protegido até ao turno {st.faction.protected_until}: não podes atacar nem ser atacado.</p>
          )}
        </section>

        <section className="card">
          <h2>Ordens deste turno</h2>
          {orders.length === 0 ? (
            <p className="muted small">Sem ordens. Seleciona um exército ou uma região tua no mapa. Os exércitos sem ordem guarnecem.</p>
          ) : (
            <ol className="orders">
              {orders.map((o, i) => (
                <li key={i}><span>{describe(o, st, regionName, factionName)}</span>
                  <button type="button" className="icon" aria-label="Retirar ordem" onClick={() => removeOrder(i)}>×</button></li>
              ))}
            </ol>
          )}
          <p className="muted small">As ordens ficam guardadas no servidor e podes mudá-las até o turno fechar.</p>
        </section>

        <Selection st={st} sel={sel} regionName={regionName} factionName={factionName} orders={orders}
          onMode={setMode} onOrder={addOrder} onSelect={setSel} />

        <section className="card">
          <h2>Exércitos e agentes</h2>
          <ul className="units">
            {st.armies.map((a) => (
              <li key={`a${a.id}`}><button type="button" className="chip" onClick={() => setSel({ kind: "army", id: a.id })}>
                ⛨ {a.men} homens{a.vet ? ` · vet. ${a.vet}` : ""} — {regionName(a.region)}</button></li>
            ))}
            {st.agents.map((g) => (
              <li key={`g${g.id}`}><button type="button" className="chip" onClick={() => setSel({ kind: "agent", id: g.id })}>
                ◆ {g.kind === "scout" ? "Batedor" : "Espião"} — {regionName(g.region)}</button></li>
            ))}
            {!st.armies.length && !st.agents.length && <li className="muted small">Nenhum.</li>}
          </ul>
        </section>

        <Diplomacy st={st} orders={orders} onOrder={addOrder} />

        <section className="card">
          <h2>Mensagens</h2>
          {st.inbox.length === 0 ? <p className="muted small">Sem mensagens.</p> : (
            <ul className="inbox">
              {[...st.inbox].reverse().slice(0, 25).map((m, i) => (
                <li key={i} className={`k-${m.kind}`}><span className="t">T{m.turn}</span>
                  <span><b>{m.kind === "report" ? "Relatório." : "Rumor."}</b> {m.text}</span></li>
              ))}
            </ul>
          )}
        </section>
      </aside>
    </div>
  );
}

function describe(o: Order, st: PlayerState, rn: (id: number) => string, fn: (id: number) => string): string {
  const army = (id: number) => { const a = st.armies.find((x) => x.id === id); return a ? `${a.men} homens em ${rn(a.region)}` : `exército ${id}`; };
  switch (o.type) {
    case "move": return `Mover ${army(o.army)} → ${o.path.map(rn).join(" → ")}`;
    case "attack": return `Atacar ${rn(o.target)} com ${army(o.army)}`;
    case "garrison": return `Guarnecer com ${army(o.army)}`;
    case "purge": return `Purgar a Praga com ${army(o.army)}`;
    case "build": return `Construir ${BUILDING_PT[o.what] ?? o.what} em ${rn(o.region)}`;
    case "recruit": return `Recrutar ${o.men} homens em ${rn(o.region)}`;
    case "posture": return `${fn(o.faction)} passa a ${POSTURE_PT[o.value].toLowerCase()}`;
    case "recruit_agent": return `Recrutar ${o.kind === "scout" ? "batedor" : "espião"} em ${rn(o.region)}`;
    case "agent_move": {
      const g = st.agents.find((x) => x.id === o.agent);
      return `${g?.kind === "spy" ? "Espião" : "Batedor"} → ${o.path.map(rn).join(" → ")}`;
    }
  }
}

function Selection({ st, sel, regionName, factionName, orders, onMode, onOrder, onSelect }: {
  st: PlayerState; sel: Sel; regionName: (id: number) => string; factionName: (id: number) => string; orders: Order[];
  onMode: (m: Mode) => void; onOrder: (o: Order) => void; onSelect: (s: Sel) => void;
}) {
  if (!sel) {
    return <section className="card"><h2>Seleção</h2><p className="muted small">Clica numa região ou num exército no mapa.</p></section>;
  }
  if (sel.kind === "army") {
    const a = st.armies.find((x) => x.id === sel.id);
    if (!a) return null;
    const r = st.regions[String(a.region)];
    return (
      <section className="card">
        <h2>Exército</h2>
        <p><b>{a.men}</b> homens{a.vet ? `, veterania ${a.vet}` : ""} em <b>{regionName(a.region)}</b>.</p>
        <div className="actions">
          <button type="button" onClick={() => onMode({ type: "move", unit: a.id, path: [] })}>Mover</button>
          <button type="button" onClick={() => onMode({ type: "attack", army: a.id })}>Atacar</button>
          <button type="button" onClick={() => onOrder({ type: "garrison", army: a.id })}>Guarnecer</button>
          {(r?.plague ?? 0) > 0 && <button type="button" onClick={() => onOrder({ type: "purge", army: a.id })}>Purgar a Praga</button>}
          <button type="button" className="link" onClick={() => onSelect({ kind: "region", id: a.region })}>ver a região</button>
        </div>
        <p className="muted small">Mover: até 2 regiões tuas ou de aliados (floresta, pântano e montanha contam o dobro). Atacar: uma vizinha; contra um reino, só com postura Hostil.</p>
      </section>
    );
  }
  if (sel.kind === "agent") {
    const g = st.agents.find((x) => x.id === sel.id);
    if (!g) return null;
    return (
      <section className="card">
        <h2>{g.kind === "scout" ? "Batedor" : "Espião"}</h2>
        <p>Em <b>{regionName(g.region)}</b>.</p>
        <div className="actions"><button type="button" onClick={() => onMode({ type: "agent_move", unit: g.id, path: [] })}>Mover</button></div>
        <p className="muted small">{g.kind === "scout"
          ? "Anda até 2 regiões por terra e vê o caminho. É apanhado se acabar o turno junto a um exército não aliado."
          : "Anda 1 região. Onde estiver, vês tudo ao detalhe; pode ser descoberto em cada turno."}</p>
      </section>
    );
  }
  const id = sel.id;
  const r: KnownRegion | undefined = st.regions[String(id)];
  if (!r) return <section className="card"><h2>Terra desconhecida</h2><p className="muted small">Ninguém do teu reino esteve lá. Envia um batedor.</p></section>;
  const mine = r.level === 4;
  const armies = r.x ? r.x.armies.map(([o, m]) => `${m} (${factionName(o)})`) : (r.a ?? []).filter(([o]) => o !== st.faction.id)
    .map(([o, b]) => `força ${SIZE_PT[b]} (${factionName(o)})`);
  const has = (t: string) => orders.some((o) => o.type === t && "region" in o && o.region === id);
  const info = st.region_info[String(id)];
  return (
    <section className="card">
      <h2>{regionName(id)}</h2>
      <p className="muted small">{LEVEL_PT[r.level]}{r.level === 1 ? `, vista no turno ${r.t}` : ""}</p>
      <dl>
        <dt>Senhor</dt><dd>{factionName(r.o)}</dd>
        {info && <><dt>Terreno</dt><dd>{TERRAIN_PT[info.terrain] ?? info.terrain}{info.rough ? " (custa 2 passos)" : ""}</dd></>}
        {info?.resource && <><dt>Recurso</dt><dd>{RESOURCE_PT[info.resource] ?? info.resource}{info.amount > 1 ? ` ×${info.amount}` : ""}</dd></>}
        <dt>Praga</dt><dd>{r.plague !== undefined ? `${r.plague}%` : PLAGUE_PT[r.p ?? 0]}</dd>
        {mine && <><dt>População</dt><dd>{Math.round(r.pop ?? 0)} mil · ordem {r.order}/3</dd></>}
        <dt>Fortificação</dt><dd>{r.fort ?? r.f ?? 0}/3</dd>
        <dt>Edifício</dt><dd>{(r.building ?? r.b) ? `${BUILDING_PT[(r.building ?? r.b)!]} nível ${r.lvl ?? r.l}` : "—"}</dd>
        {armies.length > 0 && <><dt>Exércitos</dt><dd>{armies.join(", ")}</dd></>}
        {r.g !== undefined && r.o === 0 && <><dt>Guarnição</dt><dd>{SIZE_PT[r.g]}</dd></>}
      </dl>
      {mine && <OwnRegionActions st={st} id={id} r={r} has={has} onOrder={onOrder} />}
    </section>
  );
}

function OwnRegionActions({ st, id, r, has, onOrder }: {
  st: PlayerState; id: number; r: KnownRegion; has: (t: string) => boolean; onOrder: (o: Order) => void;
}) {
  const allowed = st.allowed_buildings[String(id)] ?? [];
  const builds: { what: string; c: Record<string, number> }[] = [];
  if (!r.project) {
    if ((r.fort ?? 0) < 3) builds.push({ what: "fort", c: st.costs.fort_by_region[String(id)] ?? st.costs.fort });
    if (r.building) { if ((r.lvl ?? 0) < 3) builds.push({ what: "upgrade", c: st.costs.building[String((r.lvl ?? 0) + 1)] }); }
    else for (const b of allowed) builds.push({ what: b, c: st.costs.building["1"] });
  }
  const rc = (men: number) => Object.fromEntries(Object.entries(st.costs.recruit_per_100).map(([k, v]) => [k, v * men / 100]));
  return (
    <>
      <h3>Construir {has("build") && <span className="muted small">(já há uma ordem)</span>}</h3>
      {r.project ? <p className="muted small">Obra em curso: {BUILDING_PT[r.project.what ?? r.project.kind] ?? r.project.kind}, faltam {r.project.left} turno(s).</p> : (
        <div className="actions">
          {builds.map((b) => (
            <button type="button" key={b.what} onClick={() => onOrder({ type: "build", region: id, what: b.what })}>
              {BUILDING_PT[b.what]} <small>{cost(b.c)}</small></button>
          ))}
        </div>
      )}
      <h3>Recrutar</h3>
      <div className="actions">
        {[100, 200].map((m) => (
          <button type="button" key={m} onClick={() => onOrder({ type: "recruit", region: id, men: m })}>{m} homens <small>{cost(rc(m))}</small></button>
        ))}
        <button type="button" onClick={() => onOrder({ type: "recruit_agent", region: id, kind: "scout" })}>Batedor <small>{cost(st.costs.scout)}</small></button>
        <button type="button" onClick={() => onOrder({ type: "recruit_agent", region: id, kind: "spy" })}>Espião <small>{cost(st.costs.spy)}</small></button>
      </div>
    </>
  );
}

function Diplomacy({ st, orders, onOrder }: { st: PlayerState; orders: Order[]; onOrder: (o: Order) => void }) {
  if (!st.factions.length) {
    return <section className="card"><h2>Diplomacia</h2><p className="muted small">Ainda não conheces nenhum outro reino.</p></section>;
  }
  return (
    <section className="card">
      <h2>Diplomacia</h2>
      <table className="diplo">
        <tbody>
          {st.factions.map((f) => {
            const pending = orders.find((o) => o.type === "posture" && o.faction === f.id) as Extract<Order, { type: "posture" }> | undefined;
            const cur = pending?.value ?? st.faction.postures[String(f.id)] ?? "neutral";
            return (
              <tr key={f.id}>
                <td>{f.name}{f.bot && <div className="muted small">reino-guardião (sem jogador)</div>}</td>
                <td>
                  <select aria-label={`Postura para ${f.name}`} value={cur}
                    onChange={(e) => onOrder({ type: "posture", faction: f.id, value: e.target.value as "ally" | "neutral" | "hostile" })}>
                    {Object.entries(POSTURE_PT).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                  </select>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </section>
  );
}
