// Praga — demonstração do mapa (dados Azgaar, render próprio).
// O desenho do mapa vive no módulo partilhado map-renderer; este ficheiro só tem a simulação de demonstração e a UI.
// Servir a partir de modules/:  python -m http.server  →  http://127.0.0.1:8000/world-map/web/

import { createMapRenderer, PRAGA } from "../../map-renderer/renderer.js";

const $ = (id) => document.getElementById(id);

let map;
try {
  map = await createMapRenderer({ canvas: $("gl"), overlay: $("overlay"), dataUrl: "data", animate: !window.__noAnim });
} catch (e) {
  $("err").style.display = "grid";
  $("err").textContent = e.message;
  throw e;
}
const world = map.world;
const regions = world.regions;            // id = índice + 1
const NREG = regions.length;
$("worldname").textContent = world.name;
let selected = 0;

// ---------------------------------------------------------------- estado do jogo
const state = {
  turn: 1,
  owner: new Int32Array(NREG + 1),
  plague: new Float32Array(NREG + 1),
};
for (const r of regions) state.owner[r.id] = r.owner;

// a Praga nasce nos ermos (terra sem dono) — ou, se não houver, na região mais remota
const seeds = regions.filter((r) => r.kind === "wild");
(seeds.length ? seeds : [regions.reduce((a, b) => (a.population < b.population ? a : b))]).forEach((r) => {
  state.plague[r.id] = 1;
  for (const n of r.neighbors) state.plague[n] = Math.max(state.plague[n], 0.45);
});

const factionById = new Map(world.factions.map((f) => [f.id, f]));
factionById.set(PRAGA, { id: PRAGA, name: "A Praga", color: "#3a1d40" });

// PRNG determinístico (o mesmo turno dá sempre o mesmo resultado)
function mulberry32(a) {
  return () => {
    a |= 0; a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

map.setFactions([...factionById.values()]);
map.setState(state);

// ---------------------------------------------------------------- painéis
const BIOME_PT = {
  "Marine": "Marinho", "Hot desert": "Deserto quente", "Cold desert": "Deserto frio", "Savanna": "Savana",
  "Grassland": "Pradaria", "Tropical seasonal forest": "Floresta tropical sazonal",
  "Temperate deciduous forest": "Floresta temperada", "Tropical rainforest": "Floresta tropical húmida",
  "Temperate rainforest": "Floresta temperada húmida", "Taiga": "Taiga", "Tundra": "Tundra",
  "Glacier": "Glaciar", "Wetland": "Pântano",
};
const fmtPop = (k) => (k >= 1000 ? `${(k / 1000).toFixed(1)} M` : `${Math.round(k)} mil`);
function select(id) {
  selected = id;
  map.setSelected(id);
  const box = $("info");
  if (!id) { box.classList.remove("show"); return; }
  const r = regions[id - 1];
  const f = factionById.get(state.owner[id]);
  const p = Math.round(state.plague[id] * 100);
  box.innerHTML = `
    <h2>Região</h2>
    <div class="name">${r.fullName}</div>
    <div class="kind">${r.kind === "wild" ? "Ermos sem senhor" : "Província"}${r.coastal ? " · costeira" : ""}</div>
    <dl>
      <dt>Senhor</dt><dd>${state.owner[id] ? f.name : "Terras livres"}</dd>
      <dt>Bioma</dt><dd>${BIOME_PT[r.biome] || r.biome}</dd>
      <dt>Altitude</dt><dd>${r.elevation}</dd>
      <dt>População</dt><dd>${fmtPop(r.population)}</dd>
      <dt>Vizinhos</dt><dd>${r.neighbors.length}</dd>
      <dt>Praga</dt><dd>${p}%<div class="bar"><i style="width:${p}%"></i></div></dd>
    </dl>`;
  box.classList.add("show");
}

function renderLegend() {
  const counts = new Map();
  for (let id = 1; id <= NREG; id++) counts.set(state.owner[id], (counts.get(state.owner[id]) || 0) + 1);
  const list = world.factions.filter((f) => f.id !== 0).map((f) => ({ ...f, n: counts.get(f.id) || 0 }));
  list.sort((a, b) => b.n - a.n);
  const praga = counts.get(PRAGA) || 0;
  $("factions").innerHTML =
    (praga ? `<div class="fac praga"><span class="sw"></span><span>A Praga</span><span class="n">${praga}</span></div>` : "") +
    list.map((f) => `<div class="fac${f.n ? "" : " dead"}"><span class="sw" style="background:${f.color}"></span><span>${f.name}</span><span class="n">${f.n}</span></div>`).join("");
}
const log = (html) => { const p = document.createElement("p"); p.innerHTML = html; $("logbody").prepend(p); };


// ---------------------------------------------------------------- simulação de demonstração
function nextTurn() {
  const rnd = mulberry32(state.turn * 9973 + 17);
  const prevPlague = state.plague.slice();
  let infected = 0, lost = [];
  // 1) a Praga cresce e alastra
  for (const r of regions) {
    const p = prevPlague[r.id];
    if (p <= 0) continue;
    state.plague[r.id] = Math.min(1, p + 0.10 * (1 - p) + 0.04);
    if (p > 0.3) for (const n of r.neighbors) {
      if (rnd() < 0.55) {
        const before = state.plague[n];
        state.plague[n] = Math.min(1, before + p * (0.12 + rnd() * 0.18));
        if (before === 0 && state.plague[n] > 0) infected++;
      }
    }
  }
  // 2) regiões totalmente consumidas caem para a Praga
  for (const r of regions) {
    if (state.plague[r.id] >= 0.98 && state.owner[r.id] !== PRAGA) {
      if (state.owner[r.id] && state.owner[r.id] !== PRAGA) lost.push(r);
      state.owner[r.id] = PRAGA;
    }
  }
  // 3) guerra: algumas fações tomam uma região vizinha a um rival
  const conquests = [];
  const byFaction = new Map();
  for (const r of regions) {
    const o = state.owner[r.id];
    if (o && o !== PRAGA) (byFaction.get(o) || byFaction.set(o, []).get(o)).push(r);
  }
  for (const [fid, owned] of byFaction) {
    if (rnd() > 0.35) continue;
    const targets = [];
    for (const r of owned) for (const n of r.neighbors) {
      const o = state.owner[n];
      if (o !== fid && o !== PRAGA && state.plague[n] < 0.5) targets.push(n);
    }
    if (!targets.length) continue;
    const t = targets[Math.floor(rnd() * targets.length)];
    const from = state.owner[t];
    state.owner[t] = fid;
    conquests.push([fid, from, t]);
  }
  // 4) a Praga também recua um pouco onde há resistência organizada (fações grandes)
  for (const [fid, owned] of byFaction) {
    if (owned.length < 30) continue;
    for (const r of owned) if (state.plague[r.id] > 0 && state.plague[r.id] < 0.4 && rnd() < 0.3) state.plague[r.id] = Math.max(0, state.plague[r.id] - 0.15);
  }

  state.turn++;
  $("turn").textContent = `Turno ${state.turn}`;
  const name = (id) => (id === 0 ? "Terras Livres" : factionById.get(id).name);
  if (infected) log(`<b>Turno ${state.turn}.</b> A Praga alastra a ${infected > 1 ? `${infected} novas regiões` : "uma nova região"}.`);
  for (const r of lost.slice(0, 3)) log(`<b>Turno ${state.turn}.</b> ${r.name} é engolida pela Praga.`);
  for (const [a, b, t] of conquests.slice(0, 3)) log(`<b>Turno ${state.turn}.</b> ${name(a)} toma ${regions[t - 1].name} a ${name(b)}.`);
  map.setState(state);
  renderLegend();
  if (selected) select(selected);
}
$("next").addEventListener("click", nextTurn);

map.on("click", (id) => select(id));
for (const [id, key] of [["tBorders", "borders"], ["tPlague", "plague"], ["tRivers", "rivers"], ["tLabels", "labels"]]) {
  $(id).addEventListener("change", (e) => map.setOptions({ [key]: e.target.checked }));
}
renderLegend();
log(`<b>Turno 1.</b> A Praga desperta nos ermos.`);

// gancho para testes automáticos
window.__praga = { cam: map.camera, state, nextTurn, select, requestRedraw: map.requestRedraw, zoomAt: map.zoomAt, regions };
