// Praga — protótipo de mapa.
// Camada 1: base.jpg (pintada uma vez, offline, a partir dos dados do Azgaar)
// Camada 2: shader WebGL2 que desenha fronteiras, cores de fação e a Praga a partir de
//           regions.png (raster de IDs) + duas tabelas (LUTs) atualizadas a cada turno.
// Camada 3: canvas 2D para vetores e texto (rios, estradas, burgos, nomes).

const $ = (id) => document.getElementById(id);
const glCanvas = $("gl");
const ovCanvas = $("overlay");

// ---------------------------------------------------------------- carregamento
async function loadImage(url) {
  const blob = await (await fetch(url)).blob();
  // sem conversão de cor nem pré-multiplicação: os IDs têm de chegar intactos ao GPU
  return createImageBitmap(blob, { colorSpaceConversion: "none", premultiplyAlpha: "none" });
}

const [world, baseImg, regionImg] = await Promise.all([
  fetch("data/world.json").then((r) => r.json()),
  loadImage("data/base.jpg"),
  loadImage("data/regions.png"),
]);

const W = world.width, H = world.height, SCALE = world.rasterScale;
const regions = world.regions;            // id = índice + 1
const NREG = regions.length;
$("worldname").textContent = world.name;

// raster de IDs também no CPU, para saber em que região se clicou
const regionIds = (() => {
  const c = new OffscreenCanvas(regionImg.width, regionImg.height);
  const ctx = c.getContext("2d", { willReadFrequently: true });
  ctx.drawImage(regionImg, 0, 0);
  const px = ctx.getImageData(0, 0, c.width, c.height).data;
  const ids = new Uint16Array(c.width * c.height);
  for (let i = 0; i < ids.length; i++) ids[i] = px[i * 4] + px[i * 4 + 1] * 256;
  return ids;
})();
const regionAt = (wx, wy) => {
  const x = Math.floor(wx * SCALE), y = Math.floor(wy * SCALE);
  if (x < 0 || y < 0 || x >= regionImg.width || y >= regionImg.height) return 0;
  return regionIds[y * regionImg.width + x];
};

// ---------------------------------------------------------------- estado do jogo
const PRAGA = 255; // "fação" da Praga: regiões perdidas para a infestação
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

// ---------------------------------------------------------------- WebGL
const gl = glCanvas.getContext("webgl2", { antialias: false, premultipliedAlpha: false });
if (!gl) {
  $("err").style.display = "grid";
  $("err").textContent = "Este browser não suporta WebGL2.";
  throw new Error("no webgl2");
}

const VERT = `#version 300 es
in vec2 aPos;
void main() { gl_Position = vec4(aPos, 0.0, 1.0); }`;

const FRAG = `#version 300 es
precision highp float;
precision highp int;
uniform sampler2D uBase;
uniform sampler2D uRegion;   // IDs de região (nearest)
uniform sampler2D uRegLut;   // por região: rg = dono, b = praga
uniform sampler2D uFacLut;   // por fação: cor
uniform vec2 uCam, uRes, uWorld;
uniform float uZoom, uDpr, uScale, uTime;
uniform int uHover, uSelected;
uniform bool uBorders, uPlague;
out vec4 outColor;

int regionAt(vec2 w) {
  ivec2 c = ivec2(clamp(w * uScale, vec2(0.0), uWorld * uScale - 1.0));
  vec4 v = texelFetch(uRegion, c, 0);
  return int(v.r * 255.0 + 0.5) + int(v.g * 255.0 + 0.5) * 256;
}
vec4 regInfo(int id) { return texelFetch(uRegLut, ivec2(id, 0), 0); }
int ownerOf(int id) { vec4 r = regInfo(id); return int(r.r * 255.0 + 0.5) + int(r.g * 255.0 + 0.5) * 256; }
vec3 facColor(int o) { return texelFetch(uFacLut, ivec2(o, 0), 0).rgb; }

float hash(vec2 p) { p = fract(p * vec2(123.34, 456.21)); p += dot(p, p + 45.32); return fract(p.x * p.y); }
float vnoise(vec2 p) {
  vec2 i = floor(p), f = fract(p);
  vec2 u = f * f * (3.0 - 2.0 * f);
  return mix(mix(hash(i), hash(i + vec2(1, 0)), u.x), mix(hash(i + vec2(0, 1)), hash(i + vec2(1, 1)), u.x), u.y);
}
float fbm(vec2 p) {
  float s = 0.0, a = 0.5;
  for (int i = 0; i < 5; i++) { s += a * vnoise(p); p = p * 2.03 + 17.1; a *= 0.5; }
  return s;
}

void main() {
  vec2 css = vec2(gl_FragCoord.x, uRes.y - gl_FragCoord.y) / uDpr;
  vec2 w = uCam + css / uZoom;

  if (w.x < 0.0 || w.y < 0.0 || w.x > uWorld.x || w.y > uWorld.y) {
    outColor = vec4(0.11, 0.165, 0.2, 1.0);
    return;
  }

  vec3 col = texture(uBase, w / uWorld).rgb;
  int id = regionAt(w);

  if (id > 0) {
    int own = ownerOf(id);
    float myPlague = regInfo(id).b;

    // --- amostragem em anel: fronteira estrangeira próxima + praga suavizada entre regiões
    float jitter = hash(floor(w * uScale)) * 0.785;
    float foreign = 0.0, fw = 0.0, plagueSum = myPlague * 3.0, pw = 3.0;
    for (int ri = 0; ri < 4; ri++) {
      float R = ri == 0 ? 3.0 : ri == 1 ? 7.0 : ri == 2 ? 13.0 : 22.0;   // unidades do mundo
      float wt = ri == 0 ? 1.0 : ri == 1 ? 0.75 : ri == 2 ? 0.45 : 0.2;
      for (int k = 0; k < 8; k++) {
        float a = float(k) * 0.7854 + jitter + float(ri) * 0.39;
        int j = regionAt(w + vec2(cos(a), sin(a)) * R);
        if (j == 0) continue;
        fw += wt;
        if (ownerOf(j) != own) foreign += wt;
        plagueSum += regInfo(j).b; pw += 1.0;
      }
    }
    float glow = fw > 0.0 ? clamp(foreign / fw * 2.4, 0.0, 1.0) : 0.0;

    // --- campos bilineares sobre os 4 texels vizinhos: transições e linhas sem "escada" de píxeis
    vec2 t = w * uScale - 0.5;
    vec2 ti = floor(t), tf = t - ti;
    float sOwn[4], sId[4], sSel[4];
    vec3 cOwn[4];
    for (int k = 0; k < 4; k++) {
      ivec2 c = ivec2(clamp(ti + vec2(float(k % 2), float(k / 2)), vec2(0.0), uWorld * uScale - 1.0));
      vec4 v = texelFetch(uRegion, c, 0);
      int j = int(v.r * 255.0 + 0.5) + int(v.g * 255.0 + 0.5) * 256;
      int oj = j == 0 ? own : ownerOf(j);       // água conta como "igual": a costa já está desenhada
      sOwn[k] = oj == own ? 1.0 : 0.0;
      sId[k] = (j == 0 || j == id) ? 1.0 : 0.0;
      sSel[k] = (uSelected > 0 && j == uSelected) ? 1.0 : 0.0;
      cOwn[k] = (oj == 0 || oj == 255) ? vec3(-1.0) : facColor(oj);
    }
    #define BIL(a) mix(mix(a[0], a[1], tf.x), mix(a[2], a[3], tf.x), tf.y)
    // gradiente analítico do campo bilinear, em unidades por píxel de ecrã
    #define GRAD(a) (length(vec2(mix(a[1] - a[0], a[3] - a[2], tf.y), mix(a[2] - a[0], a[3] - a[1], tf.x))) * uScale / uZoom)
    float fOwn = BIL(sOwn), fId = BIL(sId), fSel = BIL(sSel);
    float gOwn = GRAD(sOwn), gId = GRAD(sId), gSel = GRAD(sSel);

    // --- tinta da fação (aguarela: mais densa junto à fronteira, com grão)
    vec3 tintSum = vec3(0.0); float tintW = 0.0;
    float wk[4];
    wk[0] = (1.0 - tf.x) * (1.0 - tf.y); wk[1] = tf.x * (1.0 - tf.y); wk[2] = (1.0 - tf.x) * tf.y; wk[3] = tf.x * tf.y;
    for (int k = 0; k < 4; k++) if (cOwn[k].x >= 0.0) { tintSum += cOwn[k] * wk[k]; tintW += wk[k]; }
    if (tintW > 0.0) {
      vec3 fc = tintSum / tintW;
      float grain = 0.85 + 0.3 * vnoise(w * 0.35);
      float a = (0.26 + 0.44 * glow) * grain * tintW;
      vec3 tinted = col * mix(vec3(1.0), fc * 1.18, 0.85);
      col = mix(col, tinted, clamp(a, 0.0, 0.78));
    }

    // --- linhas de fronteira anti-aliased (largura constante em píxeis de ecrã)
    if (uBorders) {
      float dOwn = gOwn > 1e-5 ? abs(fOwn - 0.5) / gOwn : 1e3;   // distância à fronteira em píxeis
      float dId = gId > 1e-5 ? abs(fId - 0.5) / gId : 1e3;
      float dSel = gSel > 1e-5 ? abs(fSel - 0.5) / gSel : 1e3;
      float lineOwn = 1.0 - smoothstep(0.8, 1.9, dOwn);
      float haloOwn = (1.0 - smoothstep(1.5, 4.5, dOwn)) * 0.25;
      float lineProv = (1.0 - smoothstep(0.3, 1.1, dId)) * smoothstep(1.2, 2.8, uZoom) * 0.38;
      float lineSel = 1.0 - smoothstep(1.2, 2.4, dSel);
      vec3 ink = vec3(0.17, 0.15, 0.12);
      col = mix(col, ink, lineProv * (1.0 - lineOwn));
      vec3 fc = (own == 0 || own == 255) ? vec3(0.4) : facColor(own);
      col = mix(col, mix(col, fc, 0.6), haloOwn);
      col = mix(col, mix(ink, fc * 0.5, 0.3), lineOwn * 0.88);
      col = mix(col, vec3(0.99, 0.94, 0.72), lineSel * 0.95);
    }

    if (id == uHover) col = mix(col, vec3(1.0, 0.97, 0.88), 0.14);

    // --- a Praga: massa orgânica que avança, com margem viva
    if (uPlague) {
      float p = mix(myPlague, plagueSum / pw, 0.75);
      if (p > 0.01) {
        vec2 q = w * 0.03 + vec2(uTime * 0.012, -uTime * 0.009);
        float n = fbm(q + 3.0 * vec2(fbm(q + 1.7), fbm(q - 4.2)));   // domain warp
        float v = p * 1.2 + (n - 0.5) * 1.0;
        float body = smoothstep(0.50, 0.55, v);
        float rim = smoothstep(0.43, 0.50, v) - body;
        // interior: carne escura manchada, com o relevo ainda a ler-se por baixo
        float m = fbm(w * 0.05 + vec2(-uTime * 0.006, uTime * 0.004));
        vec3 flesh = mix(vec3(0.09, 0.035, 0.11), vec3(0.33, 0.13, 0.33), smoothstep(0.3, 0.75, m));
        vec3 dark = col * 0.32 + flesh * 0.68;
        // veias que pulsam
        vec2 vq = w * 0.045 + 2.0 * vec2(fbm(w * 0.02), fbm(w * 0.02 + 5.3));
        float ridge = 1.0 - abs(fbm(vq) * 2.0 - 1.0);
        float vein = smoothstep(0.90, 0.97, ridge);
        float pulse = 0.65 + 0.35 * sin(uTime * 1.6 + n * 9.0);
        dark = mix(dark, vec3(0.55, 0.74, 0.30), vein * 0.45 * pulse * smoothstep(0.55, 0.75, v));
        col = mix(col, dark, body * 0.94);
        col = mix(col, vec3(0.66, 0.83, 0.32), rim * 0.8 * pulse);
      }
    }
  }
  outColor = vec4(col, 1.0);
}`;

function compile(type, src) {
  const s = gl.createShader(type);
  gl.shaderSource(s, src);
  gl.compileShader(s);
  if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s));
  return s;
}
const prog = gl.createProgram();
gl.attachShader(prog, compile(gl.VERTEX_SHADER, VERT));
gl.attachShader(prog, compile(gl.FRAGMENT_SHADER, FRAG));
gl.linkProgram(prog);
if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(prog));
gl.useProgram(prog);

const vbo = gl.createBuffer();
gl.bindBuffer(gl.ARRAY_BUFFER, vbo);
gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
const aPos = gl.getAttribLocation(prog, "aPos");
gl.enableVertexAttribArray(aPos);
gl.vertexAttribPointer(aPos, 2, gl.FLOAT, false, 0, 0);

gl.pixelStorei(gl.UNPACK_COLORSPACE_CONVERSION_WEBGL, gl.NONE);
gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, false);

function makeTex(unit, img, { nearest = false, mip = false } = {}) {
  const t = gl.createTexture();
  gl.activeTexture(gl.TEXTURE0 + unit);
  gl.bindTexture(gl.TEXTURE_2D, t);
  gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA8, gl.RGBA, gl.UNSIGNED_BYTE, img);
  const min = nearest ? gl.NEAREST : mip ? gl.LINEAR_MIPMAP_LINEAR : gl.LINEAR;
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, min);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, nearest ? gl.NEAREST : gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  if (mip) gl.generateMipmap(gl.TEXTURE_2D);
  return t;
}
makeTex(0, baseImg, { mip: true });
makeTex(1, regionImg, { nearest: true });

const LUT_W = 1024;
const regLut = new Uint8Array(LUT_W * 4);
const facLut = new Uint8Array(256 * 4);
const regTex = gl.createTexture();
const facTex = gl.createTexture();
for (const [unit, tex] of [[2, regTex], [3, facTex]]) {
  gl.activeTexture(gl.TEXTURE0 + unit);
  gl.bindTexture(gl.TEXTURE_2D, tex);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
}
const hexRgb = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
for (const f of factionById.values()) facLut.set([...hexRgb(f.color), 255], f.id * 4);
gl.activeTexture(gl.TEXTURE3);
gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA8, 256, 1, 0, gl.RGBA, gl.UNSIGNED_BYTE, facLut);

function uploadState() {
  for (let id = 1; id <= NREG; id++) {
    const o = state.owner[id];
    regLut[id * 4] = o & 255;
    regLut[id * 4 + 1] = o >> 8;
    regLut[id * 4 + 2] = Math.round(state.plague[id] * 255);
    regLut[id * 4 + 3] = 255;
  }
  gl.activeTexture(gl.TEXTURE2);
  gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA8, LUT_W, 1, 0, gl.RGBA, gl.UNSIGNED_BYTE, regLut);
}
uploadState();

const U = Object.fromEntries(
  ["uBase", "uRegion", "uRegLut", "uFacLut", "uCam", "uRes", "uWorld", "uZoom", "uDpr", "uScale", "uTime",
    "uHover", "uSelected", "uBorders", "uPlague"].map((n) => [n, gl.getUniformLocation(prog, n)])
);
gl.uniform1i(U.uBase, 0);
gl.uniform1i(U.uRegion, 1);
gl.uniform1i(U.uRegLut, 2);
gl.uniform1i(U.uFacLut, 3);
gl.uniform2f(U.uWorld, W, H);
gl.uniform1f(U.uScale, SCALE);

// ---------------------------------------------------------------- câmara
const cam = { x: 0, y: 0, zoom: 1, minZoom: 0.5, maxZoom: 10 };
let dpr = 1, vw = 0, vh = 0;
function resize() {
  dpr = Math.min(window.devicePixelRatio || 1, 2);
  vw = window.innerWidth; vh = window.innerHeight;
  for (const c of [glCanvas, ovCanvas]) { c.width = Math.round(vw * dpr); c.height = Math.round(vh * dpr); }
  gl.viewport(0, 0, glCanvas.width, glCanvas.height);
  cam.minZoom = Math.min(vw / W, vh / H) * 0.9;
  requestRedraw(true);
}
function fit() {
  cam.zoom = Math.min(vw / W, vh / H) * 0.98;
  cam.x = W / 2 - vw / 2 / cam.zoom;
  cam.y = H / 2 - vh / 2 / cam.zoom;
}
const toWorld = (sx, sy) => [cam.x + sx / cam.zoom, cam.y + sy / cam.zoom];
function zoomAt(sx, sy, factor) {
  const [wx, wy] = toWorld(sx, sy);
  cam.zoom = Math.min(cam.maxZoom, Math.max(cam.minZoom, cam.zoom * factor));
  cam.x = wx - sx / cam.zoom;
  cam.y = wy - sy / cam.zoom;
  requestRedraw(true);
}

// ---------------------------------------------------------------- interação
const ui = { hover: 0, selected: 0, borders: true, plague: true, rivers: true, labels: true };
const pointers = new Map();
let dragMoved = false, pinchDist = 0;

glCanvas.addEventListener("pointerdown", (e) => {
  glCanvas.setPointerCapture(e.pointerId);
  pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
  dragMoved = false;
  glCanvas.classList.add("dragging");
});
glCanvas.addEventListener("pointermove", (e) => {
  const prev = pointers.get(e.pointerId);
  if (!prev) {
    const [wx, wy] = toWorld(e.clientX, e.clientY);
    const h = regionAt(wx, wy);
    if (h !== ui.hover) { ui.hover = h; requestRedraw(false); }
    return;
  }
  if (pointers.size === 2) {
    pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
    const [a, b] = [...pointers.values()];
    const d = Math.hypot(a.x - b.x, a.y - b.y);
    if (pinchDist) zoomAt((a.x + b.x) / 2, (a.y + b.y) / 2, d / pinchDist);
    pinchDist = d;
    dragMoved = true;
    return;
  }
  const dx = e.clientX - prev.x, dy = e.clientY - prev.y;
  if (Math.abs(dx) + Math.abs(dy) > 2) dragMoved = true;
  cam.x -= dx / cam.zoom;
  cam.y -= dy / cam.zoom;
  pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
  requestRedraw(true);
});
const endPointer = (e) => {
  pointers.delete(e.pointerId);
  if (pointers.size < 2) pinchDist = 0;
  if (!pointers.size) glCanvas.classList.remove("dragging");
};
glCanvas.addEventListener("pointerup", (e) => {
  if (!dragMoved && pointers.size === 1) {
    const [wx, wy] = toWorld(e.clientX, e.clientY);
    select(regionAt(wx, wy));
  }
  endPointer(e);
});
glCanvas.addEventListener("pointercancel", endPointer);
glCanvas.addEventListener("pointerleave", () => { if (ui.hover) { ui.hover = 0; requestRedraw(false); } });
glCanvas.addEventListener("wheel", (e) => {
  e.preventDefault();
  zoomAt(e.clientX, e.clientY, Math.exp(-e.deltaY * 0.0015));
}, { passive: false });

for (const [id, key] of [["tBorders", "borders"], ["tPlague", "plague"], ["tRivers", "rivers"], ["tLabels", "labels"]]) {
  $(id).addEventListener("change", (e) => { ui[key] = e.target.checked; requestRedraw(true); });
}

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
  ui.selected = id;
  const box = $("info");
  if (!id) { box.classList.remove("show"); requestRedraw(false); return; }
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
  requestRedraw(false);
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
  uploadState();
  computeLabels();
  renderLegend();
  if (ui.selected) select(ui.selected);
  requestRedraw(true);
}
$("next").addEventListener("click", nextTurn);

// ---------------------------------------------------------------- nomes de fação
// rótulo no maior bloco contíguo de cada fação (evita nomes no meio do mar)
let factionLabels = [];
function computeLabels() {
  factionLabels = [];
  const seen = new Uint8Array(NREG + 1);
  const best = new Map();
  for (const r of regions) {
    const o = state.owner[r.id];
    if (!o || o === PRAGA || seen[r.id]) continue;
    const comp = [], q = [r.id];
    seen[r.id] = 1;
    while (q.length) {
      const u = q.pop();
      comp.push(u);
      for (const n of regions[u - 1].neighbors) if (!seen[n] && state.owner[n] === o) { seen[n] = 1; q.push(n); }
    }
    const area = comp.reduce((s, id) => s + regions[id - 1].area, 0);
    if (!best.has(o) || best.get(o).area < area) best.set(o, { comp, area });
  }
  for (const [o, { comp, area }] of best) {
    let cx = 0, cy = 0;
    for (const id of comp) { const r = regions[id - 1]; cx += r.center[0] * r.area; cy += r.center[1] * r.area; }
    cx /= area; cy /= area;
    // aproximar ao centro de região mais próximo (para ficar em terra)
    let bestR = null, bd = Infinity;
    for (const id of comp) { const r = regions[id - 1]; const d = (r.center[0] - cx) ** 2 + (r.center[1] - cy) ** 2; if (d < bd) { bd = d; bestR = r; } }
    const tx = (cx * 0.6 + bestR.center[0] * 0.4), ty = (cy * 0.6 + bestR.center[1] * 0.4);
    factionLabels.push({ name: factionById.get(o).name, x: tx, y: ty, size: Math.min(34, Math.max(11, Math.sqrt(area) / 9)), n: comp.length });
  }
}

// ---------------------------------------------------------------- overlay 2D
const ov = ovCanvas.getContext("2d");
function chaikin(pts, iters = 2) {
  let p = pts;
  for (let k = 0; k < iters; k++) {
    const q = [p[0]];
    for (let i = 0; i < p.length - 1; i++) {
      const [a, b] = [p[i], p[i + 1]];
      q.push([a[0] * 0.75 + b[0] * 0.25, a[1] * 0.75 + b[1] * 0.25], [a[0] * 0.25 + b[0] * 0.75, a[1] * 0.25 + b[1] * 0.75]);
    }
    q.push(p[p.length - 1]);
    p = q;
  }
  return p;
}
const riverPaths = world.rivers.map((r) => ({ ...r, pts: chaikin(r.pts, 3) }));
const roadPaths = world.roads.map((r) => chaikin(r, 2));

function drawOverlay() {
  ov.setTransform(dpr, 0, 0, dpr, 0, 0);
  ov.clearRect(0, 0, vw, vh);
  ov.save();
  ov.translate(-cam.x * cam.zoom, -cam.y * cam.zoom);
  ov.scale(cam.zoom, cam.zoom);
  const z = cam.zoom;
  ov.lineCap = "round";
  ov.lineJoin = "round";

  if (ui.rivers) {
    ov.strokeStyle = "rgba(52, 92, 112, 0.85)";
    for (const r of riverPaths) {
      ov.lineWidth = Math.max(0.6 / z, r.w * 0.55);
      ov.beginPath();
      ov.moveTo(r.pts[0][0], r.pts[0][1]);
      for (let i = 1; i < r.pts.length; i++) ov.lineTo(r.pts[i][0], r.pts[i][1]);
      ov.stroke();
    }
    ov.setLineDash([3 / z, 3 / z]);
    ov.strokeStyle = "rgba(92, 60, 34, 0.55)";
    ov.lineWidth = 1 / z;
    for (const r of roadPaths) {
      ov.beginPath();
      ov.moveTo(r[0][0], r[0][1]);
      for (let i = 1; i < r.length; i++) ov.lineTo(r[i][0], r[i][1]);
      ov.stroke();
    }
    ov.setLineDash([]);
  }

  // burgos
  const showTowns = z > 1.6;
  for (const b of world.burgs) {
    if (!b.capital && !showTowns) continue;
    if (!b.capital && b.pop < 8 / Math.max(1, z - 1)) continue;
    const r = (b.capital ? 3.2 : 1.8) / z;
    ov.beginPath();
    ov.arc(b.x, b.y, r, 0, Math.PI * 2);
    ov.fillStyle = b.capital ? "#2b2620" : "rgba(43,38,32,.85)";
    ov.fill();
    ov.lineWidth = 1.2 / z;
    ov.strokeStyle = "rgba(239,228,200,.9)";
    ov.stroke();
    if (b.capital) { ov.beginPath(); ov.arc(b.x, b.y, r * 0.38, 0, Math.PI * 2); ov.fillStyle = "#efe4c8"; ov.fill(); }
  }
  ov.restore();

  if (!ui.labels) return;
  const sx = (x) => (x - cam.x) * z, sy = (y) => (y - cam.y) * z;
  ov.textAlign = "center";
  ov.textBaseline = "middle";
  // burgos (texto em tamanho de ecrã constante)
  if (z > 1.1) {
    for (const b of world.burgs) {
      if (!b.capital && (!showTowns || b.pop < 8 / Math.max(1, z - 1))) continue;
      if (!b.capital && z < 2.4) continue;
      const x = sx(b.x), y = sy(b.y) - (b.capital ? 11 : 9);
      if (x < -50 || y < -20 || x > vw + 50 || y > vh + 20) continue;
      ov.font = b.capital ? `italic 600 13px "IM Fell English", serif` : `italic 11.5px "IM Fell English", serif`;
      ov.lineWidth = 3; ov.strokeStyle = "rgba(239,228,200,.85)"; ov.strokeText(b.name, x, y);
      ov.fillStyle = "#2b2620"; ov.fillText(b.name, x, y);
    }
  }
  // fações
  const facAlpha = Math.max(0, Math.min(1, (3.2 - z) / 1.2));
  if (facAlpha > 0) {
    const placed = [];  // caixas já ocupadas: nomes maiores têm prioridade, os que colidem ficam de fora
    for (const l of [...factionLabels].sort((a, b) => b.size - a.size)) {
      if (l.n < 2) continue;
      const size = l.size * Math.min(2.2, Math.max(0.75, z / 0.8));
      ov.font = `${size}px "IM Fell English SC", serif`;
      ov.letterSpacing = `${size * 0.22}px`;
      const text = l.name.toUpperCase();
      const x = sx(l.x), y = sy(l.y);
      const hw = ov.measureText(text).width / 2 + 6, hh = size * 0.6;
      const box = [x - hw, y - hh, x + hw, y + hh];
      if (placed.some((b) => box[0] < b[2] && box[2] > b[0] && box[1] < b[3] && box[3] > b[1])) continue;
      placed.push(box);
      ov.globalAlpha = facAlpha;
      ov.lineWidth = Math.max(2, size * 0.18); ov.strokeStyle = "rgba(239,228,200,.55)"; ov.strokeText(text, x, y);
      ov.fillStyle = "rgba(43,38,32,.88)"; ov.fillText(text, x, y);
      ov.globalAlpha = 1;
    }
    ov.letterSpacing = "0px";
  }
}

// ---------------------------------------------------------------- ciclo de desenho
let overlayDirty = true, rafPending = false;
const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const t0 = performance.now();
function requestRedraw(overlay) {
  if (overlay) overlayDirty = true;
  if (!rafPending) { rafPending = true; requestAnimationFrame(frame); }
}
function frame() {
  rafPending = false;
  gl.uniform2f(U.uCam, cam.x, cam.y);
  gl.uniform2f(U.uRes, glCanvas.width, glCanvas.height);
  gl.uniform1f(U.uZoom, cam.zoom);
  gl.uniform1f(U.uDpr, dpr);
  gl.uniform1f(U.uTime, (performance.now() - t0) / 1000);
  gl.uniform1i(U.uHover, ui.hover);
  gl.uniform1i(U.uSelected, ui.selected);
  gl.uniform1i(U.uBorders, ui.borders ? 1 : 0);
  gl.uniform1i(U.uPlague, ui.plague ? 1 : 0);
  gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
  if (overlayDirty) { drawOverlay(); overlayDirty = false; }
  // a Praga está viva: anima suavemente enquanto estiver visível
  if (ui.plague && !document.hidden && !window.__noAnim && !reduceMotion) requestRedraw(false);
}

window.addEventListener("resize", () => { resize(); });
resize();
fit();
computeLabels();
renderLegend();
log(`<b>Turno 1.</b> A Praga desperta nos ermos.`);
document.fonts.ready.then(() => requestRedraw(true));
requestRedraw(true);

// gancho para testes automáticos
window.__praga = { cam, state, nextTurn, select, requestRedraw, zoomAt, regions };
