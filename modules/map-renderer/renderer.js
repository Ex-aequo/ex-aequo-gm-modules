// Renderizador partilhado do mapa-mundo (WebGL2 + Canvas 2D). Sem dependências.
//
// Camada 1: base.jpg — pintada uma vez, offline, a partir dos dados do Azgaar (módulo world-map); se existir
//           tiles.json, tiles renderizados no Blender por nível de zoom (só os visíveis; a base.jpg fica de reserva)
// Camada 2: shader — cores de fação, fronteiras anti-aliased e Praga, a partir de regions.png (IDs) e de duas
//           tabelas pequenas (dono + praga por região; cor por fação) que mudam a cada turno
// Camada 3: canvas 2D — rios, estradas, burgos, nomes e marcadores
//
// Uso:
//   const map = await createMapRenderer({ canvas, overlay, dataUrl: "data" });
//   map.setFactions([{ id, name, color }]);
//   map.setState({ owner, plague });          // arrays indexados pelo id da região (owner -1 = Praga)
//   map.setState({ owner, plague, fog });     // nevoeiro: 0 desconhecida, 1 conhecida, 2 visível, 3 espiada/própria
//   map.on("click", (regionId) => ...);

export const PRAGA = -1;
const PRAGA_LUT = 255;

async function loadImage(url) {
  const blob = await (await fetch(url)).blob();
  // sem conversão de cor nem pré-multiplicação: os IDs têm de chegar intactos ao GPU
  return createImageBitmap(blob, { colorSpaceConversion: "none", premultiplyAlpha: "none" });
}

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

const hexRgb = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));

export async function createMapRenderer({ canvas, overlay, dataUrl = "data", animate = true }) {
  const [world, baseImg, regionImg] = await Promise.all([
    fetch(`${dataUrl}/world.json`).then((r) => r.json()),
    loadImage(`${dataUrl}/base.jpg`),
    loadImage(`${dataUrl}/regions.png`),
  ]);
  const W = world.width, H = world.height, SCALE = world.rasterScale;
  const regions = world.regions;
  const NREG = regions.length;

  // raster de IDs também no CPU, para saber em que região está o rato
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

  // ------------------------------------------------------------------ WebGL
  const gl = canvas.getContext("webgl2", { antialias: false, premultipliedAlpha: false });
  if (!gl) throw new Error("Este browser não suporta WebGL2.");

const VERT = `#version 300 es
in vec2 aPos;
void main() { gl_Position = vec4(aPos, 0.0, 1.0); }`;

const FRAG = `#version 300 es
precision highp float;
precision highp int;
uniform sampler2D uBase;
uniform sampler2D uRegion;   // IDs de região (nearest)
uniform sampler2D uRegLut;   // por região: rg = dono, b = praga, a = visão (0 desconhecida, .5 conhecida, 1 visível)
uniform sampler2D uFacLut;   // por fação: cor
uniform sampler2D uDetail;   // tiles visíveis, desenhados à resolução do ecrã (a = 0 onde ainda não há tile)
uniform bool uHasDetail;
uniform vec2 uCam, uRes, uWorld;
uniform float uZoom, uDpr, uScale, uTime;
uniform int uHover, uSelected;
uniform bool uBorders, uPlague, uFog;
out vec4 outColor;

int regionAt(vec2 w) {
  ivec2 c = ivec2(clamp(w * uScale, vec2(0.0), uWorld * uScale - 1.0));
  vec4 v = texelFetch(uRegion, c, 0);
  return int(v.r * 255.0 + 0.5) + int(v.g * 255.0 + 0.5) * 256;
}
vec4 regInfo(int id) { return texelFetch(uRegLut, ivec2(id % 1024, id / 1024), 0); }
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
  if (uHasDetail) {
    vec4 det = texelFetch(uDetail, ivec2(gl_FragCoord.xy), 0);
    col = mix(col, det.rgb, det.a);
  }
  int id = regionAt(w);

  // --- nevoeiro: campo suave a partir da visão das regiões à volta (a água herda das terras próximas)
  float fog = 1.0;
  if (uFog) {
    float fs = 0.0, fwt = 0.0;
    if (id > 0) { fs = regInfo(id).a * 4.0; fwt = 4.0; }
    float fj = vnoise(w * 0.15) * 1.57;          // rotação contínua: sem blocos na orla do nevoeiro
    for (int ri = 0; ri < 3; ri++) {
      float R = ri == 0 ? 6.0 : ri == 1 ? 14.0 : 26.0;
      for (int k = 0; k < 8; k++) {
        float a = float(k) * 0.7854 + fj + float(ri) * 0.39;
        int j = regionAt(w + vec2(cos(a), sin(a)) * R);
        if (j == 0) continue;
        float wt = ri == 0 ? 1.0 : ri == 1 ? 0.6 : 0.3;
        fs += regInfo(j).a * wt; fwt += wt;
      }
    }
    fog = fwt > 0.0 ? fs / fwt : 0.0;
    if (id > 0) fog = mix(fog, regInfo(id).a, 0.5);
  }

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
  if (uFog) {
    // conhecida: tons lavados (fotografia antiga); desconhecida: pergaminho por desenhar
    float lum = dot(col, vec3(0.3, 0.55, 0.15));
    vec3 faded = mix(col, vec3(lum) * vec3(1.05, 1.0, 0.9), 0.55) * 0.92 + 0.06;
    col = mix(faded, col, smoothstep(0.6, 0.9, fog));
    float n = fbm(w * 0.012) * 0.6 + fbm(w * 0.09) * 0.4;
    vec3 parchment = vec3(0.83, 0.77, 0.63) * (0.86 + 0.22 * n);
    float hatch = smoothstep(0.92, 1.0, abs(fract((w.x + w.y) * 0.12) * 2.0 - 1.0)) * 0.05;
    parchment -= hatch;
    float edge = smoothstep(0.08, 0.32, fog + (n - 0.5) * 0.18);
    col = mix(parchment, col, edge);
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
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, nearest ? gl.NEAREST : mip ? gl.LINEAR_MIPMAP_LINEAR : gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, nearest ? gl.NEAREST : gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    if (mip) gl.generateMipmap(gl.TEXTURE_2D);
    return t;
  }
  makeTex(0, baseImg, { mip: true });
  makeTex(1, regionImg, { nearest: true });

  // ------------------------------------------------------------------ tiles da base (opcional: tiles.json)
  const tileMeta = await fetch(`${dataUrl}/tiles.json`).then((r) => (r.ok ? r.json() : null)).catch(() => null);
  const tileCache = new Map();               // "z/x_y" -> { tex, used } | { loading: true } | { failed: true }
  let tilesDirty = true, frameNo = 0;
  let tileProg = null, tileVao = null, tileBuf = null, fbo = null, detailTex = null, fboW = 0, fboH = 0;
  if (tileMeta) {
    tileProg = gl.createProgram();
    gl.attachShader(tileProg, compile(gl.VERTEX_SHADER, `#version 300 es
in vec2 aPos; in vec2 aUv; out vec2 vUv;
void main() { vUv = aUv; gl_Position = vec4(aPos, 0.0, 1.0); }`));
    gl.attachShader(tileProg, compile(gl.FRAGMENT_SHADER, `#version 300 es
precision mediump float;
uniform sampler2D uTile; in vec2 vUv; out vec4 o;
void main() { o = vec4(texture(uTile, vUv).rgb, 1.0); }`));
    gl.linkProgram(tileProg);
    tileVao = gl.createVertexArray();
    gl.bindVertexArray(tileVao);
    tileBuf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, tileBuf);
    gl.bufferData(gl.ARRAY_BUFFER, 16 * 4, gl.DYNAMIC_DRAW);
    const la = gl.getAttribLocation(tileProg, "aPos"), lu = gl.getAttribLocation(tileProg, "aUv");
    gl.enableVertexAttribArray(la);
    gl.vertexAttribPointer(la, 2, gl.FLOAT, false, 16, 0);
    gl.enableVertexAttribArray(lu);
    gl.vertexAttribPointer(lu, 2, gl.FLOAT, false, 16, 8);
    gl.bindVertexArray(null);
    gl.bindBuffer(gl.ARRAY_BUFFER, vbo);
    detailTex = gl.createTexture();
    gl.activeTexture(gl.TEXTURE4);
    gl.bindTexture(gl.TEXTURE_2D, detailTex);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
    fbo = gl.createFramebuffer();
  }

  function loadTile(z, key) {
    const id = `${z}/${key}`;
    tileCache.set(id, { loading: true });
    fetch(`${dataUrl}/tiles/${id}.${tileMeta.format}`)
      .then((r) => { if (!r.ok) throw new Error(r.status); return r.blob(); })
      .then((b) => createImageBitmap(b, { colorSpaceConversion: "none", premultiplyAlpha: "none" }))
      .then((img) => {
        if (!alive) return;
        const tex = gl.createTexture();
        gl.activeTexture(gl.TEXTURE5);
        gl.bindTexture(gl.TEXTURE_2D, tex);
        gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA8, gl.RGBA, gl.UNSIGNED_BYTE, img);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR_MIPMAP_LINEAR);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
        gl.generateMipmap(gl.TEXTURE_2D);
        tileCache.set(id, { tex, w: img.width, h: img.height, used: frameNo });
        evictTiles();
        tilesDirty = true;
        requestRedraw(false);
      })
      .catch(() => tileCache.set(id, { failed: true }));
  }
  function evictTiles() {
    const live = [...tileCache.entries()].filter(([, t]) => t.tex);
    if (live.length <= 320) return;
    live.sort((a, b) => a[1].used - b[1].used);
    for (const [id, t] of live.slice(0, live.length - 320)) { gl.deleteTexture(t.tex); tileCache.delete(id); }
  }
  // com nevoeiro, só se pedem tiles que tocam regiões conhecidas (tiles só de mar não revelam nada)
  const tileAllowed = (L, key) => {
    if (!fogOn) return true;
    const ids = L.regions[key];
    return !ids || !ids.length || ids.some((id) => fogLevel[id] >= 1);
  };

  function drawTiles() {
    if (fboW !== canvas.width || fboH !== canvas.height) {
      fboW = canvas.width; fboH = canvas.height;
      gl.activeTexture(gl.TEXTURE4);
      gl.bindTexture(gl.TEXTURE_2D, detailTex);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA8, fboW, fboH, 0, gl.RGBA, gl.UNSIGNED_BYTE, null);
      gl.bindFramebuffer(gl.FRAMEBUFFER, fbo);
      gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, detailTex, 0);
    }
    frameNo++;
    gl.bindFramebuffer(gl.FRAMEBUFFER, fbo);
    gl.viewport(0, 0, fboW, fboH);
    gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT);
    gl.useProgram(tileProg);
    gl.bindVertexArray(tileVao);
    gl.bindBuffer(gl.ARRAY_BUFFER, tileBuf);
    gl.activeTexture(gl.TEXTURE5);
    gl.uniform1i(gl.getUniformLocation(tileProg, "uTile"), 5);
    const levels = tileMeta.levels, ts = tileMeta.tileSize;
    const need = cam.zoom * dpr;                                // píxeis de ecrã por unidade do mundo
    let zt = 0;
    for (const L of levels) if (L.pxPerUnit >= need) zt = L.z;
    const sx = (wx) => ((wx - cam.x) * cam.zoom * dpr) / fboW * 2 - 1;
    const sy = (wy) => 1 - ((wy - cam.y) * cam.zoom * dpr) / fboH * 2;
    const quad = new Float32Array(16);
    // do nível mais grosseiro ao escolhido: os grosseiros tapam o que ainda está a carregar
    for (let z = levels.length - 1; z >= zt; z--) {
      const L = levels[z], ppu = L.pxPerUnit;
      const c0 = Math.max(0, Math.floor(cam.x * ppu / ts)), c1 = Math.min(L.cols - 1, Math.floor((cam.x + vw / cam.zoom) * ppu / ts));
      const r0 = Math.max(0, Math.floor(cam.y * ppu / ts)), r1 = Math.min(L.rows - 1, Math.floor((cam.y + vh / cam.zoom) * ppu / ts));
      for (let ty = r0; ty <= r1; ty++) {
        for (let tx = c0; tx <= c1; tx++) {
          const key = `${tx}_${ty}`;
          if (!tileAllowed(L, key)) continue;
          const t = tileCache.get(`${z}/${key}`);
          if (!t) { if (z === zt || z === levels.length - 1) loadTile(z, key); continue; }
          if (!t.tex) continue;
          t.used = frameNo;
          const x0 = tx * ts / ppu, y0 = ty * ts / ppu, x1 = (tx * ts + t.w) / ppu, y1 = (ty * ts + t.h) / ppu;
          quad.set([sx(x0), sy(y0), 0, 0, sx(x1), sy(y0), 1, 0, sx(x0), sy(y1), 0, 1, sx(x1), sy(y1), 1, 1]);
          gl.bindTexture(gl.TEXTURE_2D, t.tex);
          gl.bufferSubData(gl.ARRAY_BUFFER, 0, quad);
          gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
        }
      }
    }
    gl.bindVertexArray(null);
    gl.bindBuffer(gl.ARRAY_BUFFER, vbo);
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    gl.viewport(0, 0, canvas.width, canvas.height);
    gl.useProgram(prog);
  }

  const LUT_W = 1024;                                  // tabela de regiões em 2D: 1024 x LUT_H (até 4095 regiões)
  const LUT_H = Math.max(1, Math.ceil((NREG + 1) / LUT_W));
  if (LUT_H > 4) throw new Error(`demasiadas regiões (${NREG}); o máximo é 4095`);
  const regLut = new Uint8Array(LUT_W * LUT_H * 4);
  const facLut = new Uint8Array(256 * 4);
  for (const [unit] of [[2], [3]]) {
    gl.activeTexture(gl.TEXTURE0 + unit);
    gl.bindTexture(gl.TEXTURE_2D, gl.createTexture());
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
  }

  const U = Object.fromEntries(
    ["uBase", "uRegion", "uRegLut", "uFacLut", "uCam", "uRes", "uWorld", "uZoom", "uDpr", "uScale", "uTime",
      "uHover", "uSelected", "uBorders", "uPlague", "uFog", "uDetail", "uHasDetail"].map((n) => [n, gl.getUniformLocation(prog, n)])
  );
  gl.uniform1i(U.uBase, 0);
  gl.uniform1i(U.uRegion, 1);
  gl.uniform1i(U.uRegLut, 2);
  gl.uniform1i(U.uFacLut, 3);
  gl.uniform1i(U.uDetail, 4);
  gl.uniform2f(U.uWorld, W, H);
  gl.uniform1f(U.uScale, SCALE);

  // ------------------------------------------------------------------ estado mostrado
  const owner = new Int32Array(NREG + 1);
  const plague = new Float32Array(NREG + 1);
  const fogLevel = new Uint8Array(NREG + 1).fill(2);   // sem nevoeiro: tudo visível
  let fogOn = false;
  for (const r of regions) owner[r.id] = r.owner;
  const factionById = new Map();

  function uploadFactions() {
    facLut.fill(0);
    for (const f of factionById.values()) {
      const id = f.id === PRAGA ? PRAGA_LUT : f.id;
      if (id >= 0 && id < 256) facLut.set([...hexRgb(f.color), 255], id * 4);
    }
    gl.activeTexture(gl.TEXTURE3);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA8, 256, 1, 0, gl.RGBA, gl.UNSIGNED_BYTE, facLut);
  }
  function uploadState() {
    for (let id = 1; id <= NREG; id++) {
      const o = owner[id] === PRAGA ? PRAGA_LUT : owner[id];
      regLut[id * 4] = o & 255;
      regLut[id * 4 + 1] = o >> 8;
      regLut[id * 4 + 2] = Math.round(Math.max(0, Math.min(1, plague[id])) * 255);
      regLut[id * 4 + 3] = fogLevel[id] === 0 ? 0 : fogLevel[id] === 1 ? 128 : 255;
    }
    gl.activeTexture(gl.TEXTURE2);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA8, LUT_W, LUT_H, 0, gl.RGBA, gl.UNSIGNED_BYTE, regLut);
  }

  // ------------------------------------------------------------------ câmara e entrada
  const cam = { x: 0, y: 0, zoom: 1, minZoom: 0.3, maxZoom: 10 };
  const ui = { hover: 0, selected: 0, borders: true, plague: true, rivers: true, labels: true };
  const handlers = { click: [], hover: [] };
  let markers = [];
  let dpr = 1, vw = 0, vh = 0;
  const ov = overlay.getContext("2d");

  let fitted = false;
  function resize() {
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    const rect = canvas.getBoundingClientRect();
    vw = Math.max(1, rect.width); vh = Math.max(1, rect.height);
    // o primeiro tamanho real (o contentor pode nascer com 0 px) enquadra o mundo inteiro
    if (!fitted && rect.width > 1 && rect.height > 1) { fitted = true; queueMicrotask(fit); }
    for (const c of [canvas, overlay]) { c.width = Math.round(vw * dpr); c.height = Math.round(vh * dpr); }
    gl.viewport(0, 0, canvas.width, canvas.height);
    cam.minZoom = Math.min(vw / W, vh / H) * 0.9;
    requestRedraw(true);
  }
  function fit() {
    cam.zoom = Math.min(vw / W, vh / H) * 0.98;
    cam.x = W / 2 - vw / 2 / cam.zoom;
    cam.y = H / 2 - vh / 2 / cam.zoom;
    requestRedraw(true);
  }
  const local = (e) => { const r = canvas.getBoundingClientRect(); return [e.clientX - r.left, e.clientY - r.top]; };
  const toWorld = (sx, sy) => [cam.x + sx / cam.zoom, cam.y + sy / cam.zoom];
  function zoomAt(sx, sy, factor) {
    const [wx, wy] = toWorld(sx, sy);
    cam.zoom = Math.min(cam.maxZoom, Math.max(cam.minZoom, cam.zoom * factor));
    cam.x = wx - sx / cam.zoom;
    cam.y = wy - sy / cam.zoom;
    requestRedraw(true);
  }
  function focusOn(regionId, zoom = 3) {
    const r = regions[regionId - 1];
    if (!r) return;
    cam.zoom = zoom;
    cam.x = r.center[0] - vw / 2 / zoom;
    cam.y = r.center[1] - vh / 2 / zoom;
    requestRedraw(true);
  }

  const pointers = new Map();
  let dragMoved = false, pinchDist = 0;
  const onDown = (e) => {
    canvas.setPointerCapture(e.pointerId);
    pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
    dragMoved = false;
    canvas.style.cursor = "grabbing";
  };
  const onMove = (e) => {
    const prev = pointers.get(e.pointerId);
    if (!prev) {
      const h = regionAt(...toWorld(...local(e)));
      if (h !== ui.hover) { ui.hover = h; handlers.hover.forEach((f) => f(h)); requestRedraw(false); }
      return;
    }
    if (pointers.size === 2) {
      pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
      const [a, b] = [...pointers.values()];
      const d = Math.hypot(a.x - b.x, a.y - b.y);
      const r = canvas.getBoundingClientRect();
      if (pinchDist) zoomAt((a.x + b.x) / 2 - r.left, (a.y + b.y) / 2 - r.top, d / pinchDist);
      pinchDist = d; dragMoved = true;
      return;
    }
    const dx = e.clientX - prev.x, dy = e.clientY - prev.y;
    if (Math.abs(dx) + Math.abs(dy) > 2) dragMoved = true;
    cam.x -= dx / cam.zoom; cam.y -= dy / cam.zoom;
    pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
    requestRedraw(true);
  };
  const endPointer = (e) => {
    pointers.delete(e.pointerId);
    if (pointers.size < 2) pinchDist = 0;
    if (!pointers.size) canvas.style.cursor = "";
  };
  const onUp = (e) => {
    if (!dragMoved && pointers.size === 1) {
      const id = regionAt(...toWorld(...local(e)));
      handlers.click.forEach((f) => f(id, e));
    }
    endPointer(e);
  };
  const onLeave = () => { if (ui.hover) { ui.hover = 0; handlers.hover.forEach((f) => f(0)); requestRedraw(false); } };
  const onWheel = (e) => { e.preventDefault(); zoomAt(...local(e), Math.exp(-e.deltaY * 0.0015)); };
  canvas.addEventListener("pointerdown", onDown);
  canvas.addEventListener("pointermove", onMove);
  canvas.addEventListener("pointerup", onUp);
  canvas.addEventListener("pointercancel", endPointer);
  canvas.addEventListener("pointerleave", onLeave);
  canvas.addEventListener("wheel", onWheel, { passive: false });
  canvas.style.touchAction = "none";
  overlay.style.pointerEvents = "none";

  // ------------------------------------------------------------------ nomes de fação
  let factionLabels = [];
  function computeLabels() {
    factionLabels = [];
    const seen = new Uint8Array(NREG + 1);
    const best = new Map();
    for (const r of regions) {
      const o = owner[r.id];
      if (o <= 0 || seen[r.id]) continue;
      const comp = [], q = [r.id];
      seen[r.id] = 1;
      while (q.length) {
        const u = q.pop();
        comp.push(u);
        for (const n of regions[u - 1].neighbors) if (!seen[n] && owner[n] === o) { seen[n] = 1; q.push(n); }
      }
      const area = comp.reduce((s, id) => s + regions[id - 1].area, 0);
      if (!best.has(o) || best.get(o).area < area) best.set(o, { comp, area });
    }
    for (const [o, { comp, area }] of best) {
      const f = factionById.get(o);
      if (!f) continue;
      let cx = 0, cy = 0;
      for (const id of comp) { const r = regions[id - 1]; cx += r.center[0] * r.area; cy += r.center[1] * r.area; }
      cx /= area; cy /= area;
      let bestR = null, bd = Infinity;
      for (const id of comp) { const r = regions[id - 1]; const d = (r.center[0] - cx) ** 2 + (r.center[1] - cy) ** 2; if (d < bd) { bd = d; bestR = r; } }
      factionLabels.push({ name: f.name, x: cx * 0.6 + bestR.center[0] * 0.4, y: cy * 0.6 + bestR.center[1] * 0.4,
        size: Math.min(34, Math.max(11, Math.sqrt(area) / 9)), n: comp.length });
    }
  }

  // ------------------------------------------------------------------ overlay 2D
  const riverPaths = world.rivers.map((r) => {
    const pts = chaikin(r.pts, 3);
    return { ...r, pts, reg: pts.map(([x, y]) => regionAt(x, y)) };
  });
  const roadPaths = world.roads.map((r) => {
    const pts = chaikin(r, 2);
    return Object.assign(pts, { reg: pts.map(([x, y]) => regionAt(x, y)) });
  });
  // com nevoeiro, só se desenha o que está em regiões conhecidas (um ponto na água conta como conhecido)
  const knownAt = (rid) => !fogOn || rid === 0 || fogLevel[rid] >= 1;
  function strokeKnown(pts, reg) {
    // pontos na água (rotas marítimas, foz dos rios): conhecidos só se a terra antes e depois no traçado o for
    const n = pts.length, prev = new Array(n), next = new Array(n), ok = new Array(n);
    let f = null;
    for (let i = 0; i < n; i++) { if (reg[i]) f = knownAt(reg[i]); prev[i] = f; }
    f = null;
    for (let i = n - 1; i >= 0; i--) { if (reg[i]) f = knownAt(reg[i]); next[i] = f; }
    for (let i = 0; i < n; i++) ok[i] = reg[i] ? knownAt(reg[i]) : !!((prev[i] ?? next[i]) && (next[i] ?? prev[i]));
    let open = false;
    ov.beginPath();
    for (let i = 0; i < pts.length; i++) {
      if (!fogOn || ok[i]) {
        if (open) ov.lineTo(pts[i][0], pts[i][1]); else { ov.moveTo(pts[i][0], pts[i][1]); open = true; }
      } else open = false;
    }
    ov.stroke();
  }
  const MARKER = {
    suggestion: { stroke: "rgba(165, 209, 79, .95)", fill: "rgba(165, 209, 79, .18)", dash: [4, 3] },
    pending: { stroke: "rgba(107, 47, 110, 1)", fill: "rgba(165, 209, 79, .55)", dash: [] },
    focus: { stroke: "rgba(239, 228, 200, .95)", fill: "rgba(58, 29, 64, .7)", dash: [] },
    // jogo: exércitos e agentes (forma própria, ver drawMarker)
    army: { stroke: "#2b2620", fill: "#e8c862", dash: [], shape: "shield", dx: 0 },
    foe: { stroke: "#2b2620", fill: "#b5523b", dash: [], shape: "shield", dx: 14 },
    agent: { stroke: "#2b2620", fill: "#9fb7c9", dash: [], shape: "diamond", dx: -14 },
    target: { stroke: "rgba(239, 228, 200, .95)", fill: "rgba(239, 228, 200, .12)", dash: [3, 3] },
  };
  const PATH = {
    move: { color: "rgba(232, 200, 98, .95)", dash: [6, 4], width: 2.5 },
    attack: { color: "rgba(181, 82, 59, .95)", dash: [], width: 3 },
    agent: { color: "rgba(159, 183, 201, .95)", dash: [2, 4], width: 2 },
  };
  let paths = [];

  function drawOverlay() {
    ov.setTransform(dpr, 0, 0, dpr, 0, 0);
    ov.clearRect(0, 0, vw, vh);
    ov.save();
    ov.translate(-cam.x * cam.zoom, -cam.y * cam.zoom);
    ov.scale(cam.zoom, cam.zoom);
    const z = cam.zoom;
    ov.lineCap = "round"; ov.lineJoin = "round";
    if (ui.rivers) {
      ov.strokeStyle = "rgba(52, 92, 112, 0.85)";
      for (const r of riverPaths) {
        ov.lineWidth = Math.min(Math.max(0.6 / z, r.w * 0.55), 2.6 / z);   // no máximo ~2,6 px no ecrã
        strokeKnown(r.pts, r.reg);
      }
      ov.setLineDash([3 / z, 3 / z]);
      ov.strokeStyle = "rgba(92, 60, 34, 0.55)";
      ov.lineWidth = 1 / z;
      for (const r of roadPaths) strokeKnown(r, r.reg);
      ov.setLineDash([]);
    }
    const showTowns = z > 1.6;
    for (const b of world.burgs) {
      if (!knownAt(b.region)) continue;
      if (!b.capital && !showTowns) continue;
      if (!b.capital && b.pop < 8 / Math.max(1, z - 1)) continue;
      const r = (b.capital ? 3.2 : 1.8) / z;
      ov.beginPath(); ov.arc(b.x, b.y, r, 0, Math.PI * 2);
      ov.fillStyle = b.capital ? "#2b2620" : "rgba(43,38,32,.85)"; ov.fill();
      ov.lineWidth = 1.2 / z; ov.strokeStyle = "rgba(239,228,200,.9)"; ov.stroke();
      if (b.capital) { ov.beginPath(); ov.arc(b.x, b.y, r * 0.38, 0, Math.PI * 2); ov.fillStyle = "#efe4c8"; ov.fill(); }
    }
    ov.restore();

    const sx = (x) => (x - cam.x) * z, sy = (y) => (y - cam.y) * z;
    // caminhos das ordens (setas entre centros de regiões)
    for (const pth of paths) {
      const st = PATH[pth.kind] || PATH.move;
      const pts = pth.regions.map((id) => regions[id - 1]).filter(Boolean).map((r) => [sx(r.center[0]), sy(r.center[1])]);
      if (pts.length < 2) continue;
      ov.setLineDash(st.dash); ov.lineWidth = st.width; ov.strokeStyle = st.color; ov.lineCap = "round";
      ov.beginPath(); ov.moveTo(pts[0][0], pts[0][1]);
      for (const q of pts.slice(1)) ov.lineTo(q[0], q[1]);
      ov.stroke(); ov.setLineDash([]);
      const [a, b] = [pts[pts.length - 2], pts[pts.length - 1]];
      const ang = Math.atan2(b[1] - a[1], b[0] - a[0]);
      ov.beginPath();
      ov.moveTo(b[0], b[1]);
      ov.lineTo(b[0] - 11 * Math.cos(ang - 0.45), b[1] - 11 * Math.sin(ang - 0.45));
      ov.lineTo(b[0] - 11 * Math.cos(ang + 0.45), b[1] - 11 * Math.sin(ang + 0.45));
      ov.closePath(); ov.fillStyle = st.color; ov.fill();
    }
    // marcadores (tamanho constante no ecrã)
    for (const m of markers) {
      const r = regions[m.region - 1];
      if (!r) continue;
      const st = MARKER[m.kind] || MARKER.suggestion;
      const x = sx(r.center[0]) + (st.dx || 0), y = sy(r.center[1]);
      ov.beginPath();
      if (st.shape === "shield") {
        ov.moveTo(x - 7, y - 8); ov.lineTo(x + 7, y - 8); ov.lineTo(x + 7, y + 1);
        ov.quadraticCurveTo(x + 7, y + 7, x, y + 10); ov.quadraticCurveTo(x - 7, y + 7, x - 7, y + 1); ov.closePath();
      } else if (st.shape === "diamond") {
        ov.moveTo(x, y - 7); ov.lineTo(x + 6, y); ov.lineTo(x, y + 7); ov.lineTo(x - 6, y); ov.closePath();
      } else {
        ov.arc(x, y, 9, 0, Math.PI * 2);
      }
      ov.fillStyle = st.fill; ov.fill();
      ov.setLineDash(st.dash); ov.lineWidth = m.selected ? 3 : 1.6; ov.strokeStyle = m.selected ? "#fff6d8" : st.stroke;
      ov.stroke(); ov.setLineDash([]);
      if (m.label) {
        ov.font = `600 11px "Spectral", Georgia, serif`; ov.textAlign = "center"; ov.textBaseline = "top";
        ov.lineWidth = 3; ov.strokeStyle = "rgba(20,16,12,.8)"; ov.strokeText(m.label, x, y + 12);
        ov.fillStyle = "#efe4c8"; ov.fillText(m.label, x, y + 12);
      }
    }
    if (!ui.labels) return;
    ov.textAlign = "center"; ov.textBaseline = "middle";
    if (z > 1.1) {
      for (const b of world.burgs) {
        if (!knownAt(b.region)) continue;
        if (!b.capital && (!showTowns || b.pop < 8 / Math.max(1, z - 1))) continue;
        if (!b.capital && z < 2.4) continue;
        const x = sx(b.x), y = sy(b.y) - (b.capital ? 11 : 9);
        if (x < -50 || y < -20 || x > vw + 50 || y > vh + 20) continue;
        ov.font = b.capital ? `italic 600 13px "IM Fell English", serif` : `italic 11.5px "IM Fell English", serif`;
        ov.lineWidth = 3; ov.strokeStyle = "rgba(239,228,200,.85)"; ov.strokeText(b.name, x, y);
        ov.fillStyle = "#2b2620"; ov.fillText(b.name, x, y);
      }
    }
    const facAlpha = Math.max(0, Math.min(1, (3.2 - z) / 1.2));
    if (facAlpha > 0) {
      const placed = [];
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

  // ------------------------------------------------------------------ ciclo de desenho
  let overlayDirty = true, rafPending = false, alive = true;
  const t0 = performance.now();
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  function requestRedraw(ovr) {
    if (ovr) { overlayDirty = true; tilesDirty = true; }
    if (!rafPending && alive) { rafPending = true; requestAnimationFrame(frame); }
  }
  function frame() {
    rafPending = false;
    if (!alive) return;
    if (tileMeta && tilesDirty) { tilesDirty = false; drawTiles(); }
    gl.uniform1i(U.uHasDetail, tileMeta ? 1 : 0);
    gl.uniform2f(U.uCam, cam.x, cam.y);
    gl.uniform2f(U.uRes, canvas.width, canvas.height);
    gl.uniform1f(U.uZoom, cam.zoom);
    gl.uniform1f(U.uDpr, dpr);
    gl.uniform1f(U.uTime, (performance.now() - t0) / 1000);
    gl.uniform1i(U.uHover, ui.hover);
    gl.uniform1i(U.uSelected, ui.selected);
    gl.uniform1i(U.uBorders, ui.borders ? 1 : 0);
    gl.uniform1i(U.uPlague, ui.plague ? 1 : 0);
    gl.uniform1i(U.uFog, fogOn ? 1 : 0);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    if (overlayDirty) { drawOverlay(); overlayDirty = false; }
    const anyPlague = plague.some((p) => p > 0);
    if (animate && ui.plague && anyPlague && !document.hidden && !reduceMotion) requestRedraw(false);
  }

  const ro = new ResizeObserver(() => resize());
  ro.observe(canvas);
  resize();
  fit();
  uploadState();
  uploadFactions();
  if (document.fonts) document.fonts.ready.then(() => requestRedraw(true));

  return {
    world, regionAt, camera: cam, fit, focusOn, zoomAt,
    fogAt: (id) => (fogOn ? fogLevel[id] ?? 0 : 2),
    setFactions(list) {
      factionById.clear();
      for (const f of list) factionById.set(f.id, f);
      uploadFactions(); computeLabels(); requestRedraw(true);
    },
    setState(next) {
      if (next.owner) for (let id = 1; id <= NREG; id++) owner[id] = next.owner[id] ?? 0;
      if (next.plague) for (let id = 1; id <= NREG; id++) plague[id] = next.plague[id] ?? 0;
      if ("fog" in next) {
        fogOn = !!next.fog;
        for (let id = 1; id <= NREG; id++) fogLevel[id] = fogOn ? (next.fog[id] ?? 0) : 2;
      }
      uploadState(); computeLabels(); requestRedraw(true);
    },
    setOptions(opts) { Object.assign(ui, opts); requestRedraw(true); },
    setSelected(id) { ui.selected = id || 0; requestRedraw(false); },
    setMarkers(list) { markers = list || []; requestRedraw(true); },
    setPaths(list) { paths = list || []; requestRedraw(true); },
    setCamera(c) { Object.assign(cam, c); requestRedraw(true); },
    on(evt, fn) { handlers[evt].push(fn); return () => { handlers[evt] = handlers[evt].filter((f) => f !== fn); }; },
    requestRedraw,
    destroy() {
      alive = false; ro.disconnect();
      canvas.removeEventListener("pointerdown", onDown); canvas.removeEventListener("pointermove", onMove);
      canvas.removeEventListener("pointerup", onUp); canvas.removeEventListener("pointercancel", endPointer);
      canvas.removeEventListener("pointerleave", onLeave); canvas.removeEventListener("wheel", onWheel);
    },
  };
}
