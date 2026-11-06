// Mapa do mundo.
//  • Jogar: marcadores (locais, livros anexados) e tokens dos jogadores, sincronizados entre todos.
//  • Editar: grade quadrada ou hexagonal, pincel/balde de terreno, paredes nas arestas, objetos (assets) e fundo.
(() => {
  const D = JSON.parse(document.getElementById('map-data').textContent);
  const $ = id => document.getElementById(id);
  const el = (tag, cls = '', text) => { const n = document.createElement(tag); if (cls) n.className = cls; if (text !== undefined) n.textContent = text; return n; };
  const vp = $('mviewport'), world = $('mworld'), pinsEl = $('pins'), side = $('side'), img = $('map-img');
  const cv = { terrain: $('cv-terrain'), grid: $('cv-grid'), objects: $('cv-objects'), ui: $('cv-ui') };
  const ctx = Object.fromEntries(Object.entries(cv).map(([k, c]) => [k, c.getContext('2d')]));
  const SQ3 = Math.sqrt(3);

  // ================================================================== estado do mapa
  function normalize(d) {
    d = d && typeof d === 'object' ? d : {};
    const g = d.grid || {};
    return {
      grid: { type: g.type || (img ? 'none' : 'square'), size: g.size || 48, cols: g.cols || 30, rows: g.rows || 20,
              color: g.color || '#000000', opacity: g.opacity ?? 0.25, show: g.show ?? true },
      base: d.base || '', bg: d.bg || '#1c1917', imageOpacity: d.imageOpacity ?? 1,
      terrain: d.terrain || {}, walls: d.walls || {}, props: d.props || [],
    };
  }
  let M = normalize(D.data);
  let version = D.version;
  let W = 0, H = 0, Q = 1;   // tamanho do mundo (px) e fator de resolução dos canvas

  // ================================================================== geometria da grade
  const R = () => M.grid.size / SQ3;              // raio do hexágono (pontudo em cima)
  const HEX_DIRS = [
    [[1, 0], [0, -1], [-1, -1], [-1, 0], [-1, 1], [0, 1]],   // linhas pares:  L, NE, NO, O, SO, SE
    [[1, 0], [1, -1], [0, -1], [-1, 0], [0, 1], [1, 1]],     // linhas ímpares
  ];
  const SQ_DIRS = [[1, 0], [0, -1], [-1, 0], [0, 1]];       // L, N, O, S
  const isHex = () => M.grid.type === 'hex';
  const gridOn = () => M.grid.type !== 'none';
  const inside = (c, r) => c >= 0 && r >= 0 && c < M.grid.cols && r < M.grid.rows;
  const key = (c, r) => c + ',' + r;
  const parseKey = k => k.split(',').map(Number);

  function computeSize() {
    const g = M.grid, s = g.size;
    if (img && img.naturalWidth) {
      W = img.naturalWidth; H = img.naturalHeight;
      if (g.type === 'hex') { g.cols = Math.ceil(W / s); g.rows = Math.ceil((H - R() / 2) / (1.5 * R())); }
      else { g.cols = Math.ceil(W / s); g.rows = Math.ceil(H / s); }
    } else if (g.type === 'hex') { W = Math.round(s * (g.cols + 0.5)); H = Math.round(R() * (1.5 * g.rows + 0.5)); }
    else { W = g.cols * s; H = g.rows * s; }
    Q = W * H < 3_000_000 ? 2 : 1;
    for (const c of Object.values(cv)) {
      c.width = W * Q; c.height = H * Q; c.style.width = W + 'px'; c.style.height = H + 'px';
    }
    for (const c of Object.values(ctx)) { c.setTransform(Q, 0, 0, Q, 0, 0); c.imageSmoothingEnabled = false; }
    world.style.width = W + 'px'; world.style.height = H + 'px';
    if (img) img.style.opacity = M.imageOpacity;
  }
  function center(c, r) {
    const s = M.grid.size;
    if (isHex()) return { x: s * (c + 0.5 * (r & 1)) + s / 2, y: 1.5 * R() * r + R() };
    return { x: (c + 0.5) * s, y: (r + 0.5) * s };
  }
  function cellAt(x, y) {
    const s = M.grid.size;
    let c, r;
    if (isHex()) {
      const rr = R(), px = x - s / 2, py = y - rr;
      const q = (SQ3 / 3 * px - py / 3) / rr, ar = (2 / 3 * py) / rr;
      let rx = Math.round(q), rz = Math.round(ar), ry = Math.round(-q - ar);
      const dx = Math.abs(rx - q), dz = Math.abs(rz - ar), dy = Math.abs(ry + q + ar);
      if (dx > dy && dx > dz) rx = -ry - rz; else if (dz > dy) rz = -rx - ry;
      r = rz; c = rx + (r - (r & 1)) / 2;
    } else { c = Math.floor(x / s); r = Math.floor(y / s); }
    return inside(c, r) ? [c, r] : null;
  }
  function cellPath(g, c, r) {
    const s = M.grid.size;
    if (!isHex()) { g.rect(c * s, r * s, s, s); return; }
    const { x, y } = center(c, r), rr = R();
    for (let i = 0; i < 6; i++) {
      const a = Math.PI / 180 * (60 * i - 30);
      const px = x + rr * Math.cos(a), py = y + rr * Math.sin(a);
      i ? g.lineTo(px, py) : g.moveTo(px, py);
    }
    g.closePath();
  }
  const dirsOf = (c, r) => isHex() ? HEX_DIRS[r & 1] : SQ_DIRS;
  function neighbors(c, r) { return dirsOf(c, r).map(([dc, dr]) => [c + dc, r + dr]); }
  function segment(c, r, k) {
    const s = M.grid.size;
    if (isHex()) {
      const { x, y } = center(c, r), rr = R(), th = -60 * k;
      const p = deg => [x + rr * Math.cos(deg * Math.PI / 180), y + rr * Math.sin(deg * Math.PI / 180)];
      return [...p(th - 30), ...p(th + 30)];
    }
    const x = c * s, y = r * s;
    return [[x + s, y, x + s, y + s], [x, y, x + s, y], [x, y, x, y + s], [x, y + s, x + s, y + s]][k];
  }
  function edgeKey(a, b) {
    const [p, q] = (a[1] < b[1] || (a[1] === b[1] && a[0] < b[0])) ? [a, b] : [b, a];
    return key(...p) + '|' + key(...q);
  }
  function edgeAt(x, y) {
    if (!gridOn()) return null;
    const s = M.grid.size;
    // a célula pode estar fora (borda do mapa): calcula sem checar limites
    let cell = cellAt(x, y);
    if (!cell) {
      const cx = Math.min(Math.max(x, 1), W - 1), cy = Math.min(Math.max(y, 1), H - 1);
      cell = cellAt(cx, cy); if (!cell) return null;
    }
    const [c, r] = cell, ce = center(c, r), dx = x - ce.x, dy = y - ce.y;
    if (Math.hypot(dx, dy) < s * 0.22) return null;   // muito no meio: ambíguo
    let k;
    if (isHex()) k = ((Math.round(-Math.atan2(dy, dx) / (Math.PI / 3)) % 6) + 6) % 6;
    else k = Math.abs(dx) > Math.abs(dy) ? (dx > 0 ? 0 : 2) : (dy < 0 ? 1 : 3);
    const [dc, dr] = dirsOf(c, r)[k];
    return { key: edgeKey([c, r], [c + dc, r + dr]), seg: segment(c, r, k) };
  }
  function edgeSegment(k) {
    const [a, b] = k.split('|').map(parseKey);
    const ds = dirsOf(a[0], a[1]);
    const i = ds.findIndex(([dc, dr]) => a[0] + dc === b[0] && a[1] + dr === b[1]);
    return i < 0 ? null : segment(a[0], a[1], i);
  }

  // ================================================================== kit de assets
  const KIT = { terrains: [], props: [], terrainMap: {}, propMap: {}, patterns: {}, images: {}, walls: {} };
  function noiseTile(c1, c2, seed) {
    const t = document.createElement('canvas'); t.width = t.height = 16;
    const g = t.getContext('2d'); g.fillStyle = c1; g.fillRect(0, 0, 16, 16); g.fillStyle = c2;
    let s = seed;
    const rnd = () => (s = (s * 9301 + 49297) % 233280) / 233280;
    for (let i = 0; i < 46; i++) g.fillRect(Math.floor(rnd() * 16), Math.floor(rnd() * 16), 1 + Math.floor(rnd() * 2), 1);
    return t;
  }
  async function loadKit() {
    const m = await (await fetch(D.kit + 'manifest.json')).json();
    KIT.terrains = m.terrains; KIT.props = m.props;
    m.props.forEach(p => { KIT.propMap[p.key] = p; });
    await Promise.all(m.terrains.map((t, i) => new Promise(res => {
      KIT.terrainMap[t.key] = t;
      if (!t.file) { t.px = 16; t.src = noiseTile(t.color, t.color2, i * 977 + 13); KIT.patterns[t.key] = ctx.terrain.createPattern(t.src, 'repeat'); return res(); }
      const im = new Image(); im.onload = () => { t.src = im; KIT.patterns[t.key] = ctx.terrain.createPattern(im, 'repeat'); res(); };
      im.onerror = res; im.src = D.kit + t.file;
    })));
    // texturas das paredes das arestas
    KIT.walls.wood = { img: plankTile(), px: 16 };
    await Promise.all(Object.entries(m.walls || {}).map(([k, w]) => new Promise(res => {
      const im = new Image(); im.onload = () => { KIT.walls[k] = { img: im, px: w.px }; res(); }; im.onerror = res; im.src = D.kit + w.file;
    })));
    for (const t of Object.values(KIT.walls)) t.pat = ctx.objects.createPattern(t.img, 'repeat');
  }
  function propImage(k) {
    if (KIT.images[k]) return KIT.images[k];
    const p = KIT.propMap[k]; if (!p) return null;
    const im = new Image(); im.onload = () => drawObjects(); im.src = D.kit + p.file;
    return (KIT.images[k] = im);
  }
  function fillStyleFor(t) {
    const pat = KIT.patterns[t], info = KIT.terrainMap[t];
    if (!pat) return info?.color || '#888';
    const k = M.grid.size / (info.px || 16);
    pat.setTransform(new DOMMatrix([k, 0, 0, k, 0, 0]));
    return pat;
  }

  // ================================================================== desenho
  function drawTerrainAll() {
    const g = ctx.terrain;
    g.clearRect(0, 0, W, H);
    if (!img) { g.fillStyle = M.bg; g.fillRect(0, 0, W, H); }
    if (M.base && KIT.terrainMap[M.base]) { g.fillStyle = fillStyleFor(M.base); g.fillRect(0, 0, W, H); }
    if (!gridOn()) return;
    for (const k in M.terrain) { const [c, r] = parseKey(k); if (inside(c, r)) drawCell(c, r, true); }
  }
  function drawCell(c, r, bulk) {
    const g = ctx.terrain, t = M.terrain[key(c, r)] || M.base;
    g.beginPath(); cellPath(g, c, r);
    if (t && KIT.terrainMap[t]) {
      const fs = fillStyleFor(t);
      g.fillStyle = fs; g.fill();
      if (isHex()) { g.strokeStyle = fs; g.lineWidth = 1; g.stroke(); }   // esconde a costura entre hexágonos
    } else if (!bulk) {
      g.save(); g.clip();
      const { x, y } = center(c, r), s = M.grid.size;
      g.clearRect(x - s, y - s, s * 2, s * 2);
      if (!img) { g.fillStyle = M.bg; g.fillRect(x - s, y - s, s * 2, s * 2); }
      g.restore();
    }
  }
  function drawGrid() {
    const g = ctx.grid; g.clearRect(0, 0, W, H);
    if (!gridOn() || !M.grid.show) return;
    g.save(); g.globalAlpha = M.grid.opacity; g.strokeStyle = M.grid.color; g.lineWidth = 1;
    g.beginPath();
    const s = M.grid.size;
    if (isHex()) { for (let r = 0; r < M.grid.rows; r++) for (let c = 0; c < M.grid.cols; c++) cellPath(g, c, r); }
    else {
      for (let c = 0; c <= M.grid.cols; c++) { g.moveTo(c * s, 0); g.lineTo(c * s, M.grid.rows * s); }
      for (let r = 0; r <= M.grid.rows; r++) { g.moveTo(0, r * s); g.lineTo(M.grid.cols * s, r * s); }
    }
    g.stroke(); g.restore();
  }

  // Paredes nas arestas: faixa com textura (pedra, tijolo, bloco, madeira), porta e janela com imagem
  const WALLS = {
    stone: { label: 'Muro de pedra', tex: 'stone' },
    brick: { label: 'Muro de tijolos', tex: 'brick' },
    block: { label: 'Muro de blocos', tex: 'block' },
    wood: { label: 'Parede de madeira', tex: 'wood' },
    door: { label: 'Porta', tex: 'stone' },
    window: { label: 'Janela', tex: 'stone' },
    fence: { label: 'Cerca', tex: 'wood' },
    secret: { label: 'Passagem secreta', tex: 'stone' },
  };
  function plankTile() {
    const t = document.createElement('canvas'); t.width = t.height = 16;
    const g = t.getContext('2d');
    g.fillStyle = '#8a5a2b'; g.fillRect(0, 0, 16, 16);
    g.fillStyle = '#6e4521'; [5, 10, 15].forEach(y => g.fillRect(0, y, 16, 1));
    g.fillStyle = '#a06d38'; [0, 6, 11].forEach(y => g.fillRect(0, y, 16, 1));
    g.fillStyle = '#5a3818'; g.fillRect(4, 0, 1, 5); g.fillRect(11, 6, 1, 4); g.fillRect(7, 11, 1, 4);
    return t;
  }
  function wallFill(tex, w) {
    const t = KIT.walls[tex]; if (!t) return '#77737f';
    t.pat.setTransform(new DOMMatrix().scale(w / t.px));
    return t.pat;
  }
  // desenha um trecho [a,b] (0..1) da aresta como uma faixa de espessura w, já no sistema girado
  function band(g, L, w, a, b, fill, caps) {
    const x0 = a * L - (caps && a === 0 ? w / 2 : 0), x1 = b * L + (caps && b === 1 ? w / 2 : 0);
    g.beginPath(); g.rect(x0, -w / 2, x1 - x0, w);
    g.fillStyle = fill; g.fill();
    g.lineWidth = 1.5; g.strokeStyle = 'rgba(15,12,18,.9)'; g.stroke();
    g.fillStyle = 'rgba(255,255,255,.14)'; g.fillRect(x0, -w / 2, x1 - x0, Math.max(1, w * 0.12));   // brilho no topo
  }
  function drawWall(g, seg, type, ghost) {
    const [x1, y1, x2, y2] = seg, L = Math.hypot(x2 - x1, y2 - y1), w = Math.max(6, M.grid.size * 0.3);
    const st = WALLS[type] || WALLS.stone;
    g.save(); if (ghost) g.globalAlpha = 0.6;
    g.translate(x1, y1); g.rotate(Math.atan2(y2 - y1, x2 - x1));
    g.imageSmoothingEnabled = false;
    if (type === 'door') {
      band(g, L, w, 0, 0.18, wallFill('stone', w), true); band(g, L, w, 0.82, 1, wallFill('stone', w), true);
      const d = KIT.walls.door;
      if (d) g.drawImage(d.img, L * 0.18, -w * 0.75, L * 0.64, w * 1.5);
      else { g.fillStyle = '#a0682e'; g.fillRect(L * 0.18, -w / 2, L * 0.64, w); }
    } else if (type === 'window') {
      band(g, L, w, 0, 1, wallFill('stone', w), true);
      g.fillStyle = '#2b1a0e'; g.fillRect(L * 0.3 - 2, -w * 0.32 - 2, L * 0.4 + 4, w * 0.64 + 4);
      g.fillStyle = '#9fd8ff'; g.fillRect(L * 0.3, -w * 0.32, L * 0.4, w * 0.64);
      g.fillStyle = '#2b1a0e'; g.fillRect(L * 0.5 - 1, -w * 0.32, 2, w * 0.64);
    } else if (type === 'fence') {
      g.fillStyle = '#3d2614'; g.fillRect(0, -w * 0.16, L, w * 0.32);
      g.fillStyle = '#b07a43'; g.fillRect(0, -w * 0.1, L, w * 0.2);
      for (const t of [0, 0.5, 1]) { g.fillStyle = '#3d2614'; g.fillRect(t * L - w * 0.22, -w * 0.3, w * 0.44, w * 0.6); g.fillStyle = '#c48a4f'; g.fillRect(t * L - w * 0.13, -w * 0.21, w * 0.26, w * 0.42); }
    } else {
      band(g, L, w, 0, 1, wallFill(st.tex, w), true);
      if (type === 'secret' && mode === 'edit') {     // jogadores veem uma parede comum
        g.setLineDash([w * 0.6, w * 0.5]); g.lineWidth = 3; g.strokeStyle = '#c4b5fd';
        g.beginPath(); g.moveTo(0, 0); g.lineTo(L, 0); g.stroke(); g.setLineDash([]);
      }
    }
    g.restore();
  }
  function propRect(p) {
    const a = KIT.propMap[p.a]; if (!a) return null;
    const k = M.grid.size / (a.u || 16) * (p.s || 1);
    const w = a.w * k, h = a.h * k;
    return { x: p.x - w / 2, y: p.y - h, w, h };
  }
  // caixa (sem rotação) que envolve o objeto girado — usada para clicar e selecionar
  function propBounds(p) {
    const r = propRect(p); if (!r) return null;
    const ang = (p.r || 0) * Math.PI / 180; if (!ang) return r;
    const cx = r.x + r.w / 2, cy = r.y + r.h / 2, c = Math.abs(Math.cos(ang)), s = Math.abs(Math.sin(ang));
    const w = r.w * c + r.h * s, h = r.w * s + r.h * c;
    return { x: cx - w / 2, y: cy - h / 2, w, h };
  }
  function drawObjects() {
    const g = ctx.objects; g.clearRect(0, 0, W, H);
    if (gridOn()) for (const k in M.walls) { const seg = edgeSegment(k); if (seg) drawWall(g, seg, M.walls[k]); }
    const sorted = [...M.props].sort((a, b) => a.y - b.y);
    for (const p of sorted) {
      const im = propImage(p.a), r = propRect(p);
      if (!im || !im.complete || !r) continue;
      g.save();
      g.translate(r.x + r.w / 2, r.y + r.h / 2);
      if (p.r) g.rotate(p.r * Math.PI / 180);
      if (p.f) g.scale(-1, 1);
      g.drawImage(im, -r.w / 2, -r.h / 2, r.w, r.h);
      if (mode === 'edit' && selectedProp === p.id) {
        g.strokeStyle = (getComputedStyle(document.documentElement).getPropertyValue('--a500') || '#f59e0b').trim();
        g.lineWidth = 2; g.setLineDash([5, 4]); g.strokeRect(-r.w / 2 - 2, -r.h / 2 - 2, r.w + 4, r.h + 4);
      }
      g.restore();
    }
  }
  function redrawAll() { computeSize(); drawTerrainAll(); drawGrid(); drawObjects(); clearUi(); renderPins(); applyView(); }
  const clearUi = () => ctx.ui.clearRect(0, 0, W, H);

  // ================================================================== view (pan/zoom)
  const viewKey = 'map-view-' + D.mapId;
  let view = JSON.parse(localStorage.getItem(viewKey) || 'null');
  function applyView() {
    if (!view) return;
    world.style.transform = `translate(${view.x}px, ${view.y}px) scale(${view.z})`;
    $('zoom-level').textContent = Math.round(view.z * 100) + '%';
    for (const n of pinsEl.children) scalePin(n);
    localStorage.setItem(viewKey, JSON.stringify(view));
  }
  function fit() {
    const r = vp.getBoundingClientRect();
    const z = Math.min(r.width / W, r.height / H) * 0.95;
    view = { z, x: (r.width - W * z) / 2, y: (r.height - H * z) / 2 };
    applyView();
  }
  function zoomAt(f, cx, cy) {
    const r = vp.getBoundingClientRect();
    if (cx === undefined) { cx = r.left + r.width / 2; cy = r.top + r.height / 2; }
    const wx = (cx - r.left - view.x) / view.z, wy = (cy - r.top - view.y) / view.z;
    view.z = Math.min(8, Math.max(0.05, view.z * f));
    view.x = cx - r.left - wx * view.z; view.y = cy - r.top - wy * view.z;
    applyView();
  }
  const toWorld = (cx, cy) => { const r = vp.getBoundingClientRect(); return { x: (cx - r.left - view.x) / view.z, y: (cy - r.top - view.y) / view.z }; };
  const toFrac = (cx, cy) => { const p = toWorld(cx, cy); return { x: Math.min(1, Math.max(0, p.x / W)), y: Math.min(1, Math.max(0, p.y / H)) }; };

  // ================================================================== modo
  let mode = 'play', tool = 'terrain';
  function setMode(m) {
    mode = m;
    document.querySelectorAll('[data-mode]').forEach(b => b.classList.toggle('bg-surface', b.dataset.mode === m));
    document.querySelectorAll('[data-only]').forEach(e => { e.classList.toggle('hidden', e.dataset.only !== m); e.classList.toggle('flex', e.dataset.only === m); });
    $('palette').classList.toggle('hidden', m !== 'edit'); $('palette').classList.toggle('flex', m === 'edit');
    vp.classList.toggle('editing', m === 'edit');
    if (m === 'edit') closeSide();
    const u = new URL(location); m === 'edit' ? u.searchParams.set('edit', 1) : u.searchParams.delete('edit'); history.replaceState(null, '', u);
    drawObjects(); clearUi();
  }
  document.querySelectorAll('[data-mode]').forEach(b => b.addEventListener('click', () => { flushSave(); setMode(b.dataset.mode); }));

  function setTool(t) {
    tool = t;
    document.querySelectorAll('[data-tool]').forEach(b => b.classList.toggle('active', b.dataset.tool === t));
    document.querySelectorAll('[data-panel]').forEach(p => p.classList.toggle('hidden', !p.dataset.panel.split(' ').includes(t)));
    vp.classList.toggle('tool-move', t === 'move');
    if (t !== 'props') { selectedProp = null; showPropSel(); drawObjects(); }
    clearUi();
  }
  document.querySelectorAll('[data-tool]').forEach(b => b.addEventListener('click', () => setTool(b.dataset.tool)));

  // ================================================================== paleta
  let terrainSel = 'grama', brush = 1, wallSel = 'stone', assetSel = null, selectedProp = null;
  function buildPalette() {
    const tl = $('terrain-list'); tl.replaceChildren();
    for (const t of KIT.terrains) {
      const b = el('button', 'swatch group flex flex-col items-center gap-1 rounded-lg p-1 hover:bg-surface-2');
      b.dataset.terrain = t.key; b.title = t.label;
      const sw = el('div', 'size-12 rounded-md ring-1 ring-black/20');
      sw.style.background = `url(${t.src instanceof HTMLCanvasElement ? t.src.toDataURL() : t.src.src}) 0 0 / 24px 24px repeat`;
      sw.style.imageRendering = 'pixelated';
      b.append(sw, el('span', 'w-full truncate text-center text-[10px] text-muted', t.label));
      b.addEventListener('click', () => { terrainSel = t.key; markActive(); if (tool !== 'fill') setTool('terrain'); });
      tl.append(b);
    }
    const wl = $('wall-list'); wl.replaceChildren();
    for (const [k, w] of Object.entries(WALLS)) {
      const b = el('button', 'swatch flex items-center gap-3 rounded-lg px-2 py-1.5 text-left hover:bg-surface-2');
      b.dataset.wall = k;
      const c = el('canvas', 'h-5 w-14'); c.width = 112; c.height = 40;
      const g = c.getContext('2d'); const old = M.grid.size; M.grid.size = 48; drawWall(g, [8, 20, 104, 20], k); M.grid.size = old;
      b.append(c, el('span', 'text-sm text-ink-2', w.label));
      b.addEventListener('click', () => { wallSel = k; markActive(); });
      wl.append(b);
    }
    const cats = [...new Set(KIT.props.map(p => p.category))];
    const sel = $('prop-cat'); sel.replaceChildren(new Option('Todas as categorias', ''));
    cats.forEach(c => sel.append(new Option(c, c)));
    sel.value = cats[0] || '';
    renderProps();
    const bs = $('grid-form').querySelector('[data-m="base"]');
    bs.replaceChildren(new Option('— nenhum —', ''));
    KIT.terrains.forEach(t => bs.append(new Option(t.label, t.key)));
    markActive(); syncGridForm();
  }
  function renderProps() {
    const cat = $('prop-cat').value, q = $('prop-search').value.trim().toLowerCase();
    const list = $('prop-list'); list.replaceChildren();
    for (const p of KIT.props) {
      if ((cat && p.category !== cat) || (q && !p.label.toLowerCase().includes(q))) continue;
      const b = el('button', 'asset grid aspect-square place-items-center rounded-md bg-canvas p-1 hover:ring-1 hover:ring-accent');
      b.dataset.asset = p.key; b.title = p.label;
      const im = el('img', 'max-h-full max-w-full'); im.src = D.kit + p.file; im.loading = 'lazy'; im.style.imageRendering = 'pixelated';
      b.append(im);
      b.addEventListener('click', () => { assetSel = p.key; selectedProp = null; showPropSel(); markActive(); drawObjects(); });
      list.append(b);
    }
    markActive();
  }
  $('prop-cat').addEventListener('change', renderProps);
  $('prop-search').addEventListener('input', renderProps);
  function markActive() {
    document.querySelectorAll('[data-terrain]').forEach(b => b.classList.toggle('active', b.dataset.terrain === terrainSel));
    document.querySelectorAll('[data-wall]').forEach(b => b.classList.toggle('active', b.dataset.wall === wallSel));
    document.querySelectorAll('[data-asset]').forEach(b => b.classList.toggle('active', b.dataset.asset === assetSel));
    document.querySelectorAll('[data-brush]').forEach(b => b.classList.toggle('bg-accent', Number(b.dataset.brush) === brush));
  }
  document.querySelectorAll('[data-brush]').forEach(b => b.addEventListener('click', () => { brush = Number(b.dataset.brush); markActive(); }));

  // configurações de grade / fundo
  const gf = $('grid-form');
  function syncGridForm() {
    gf.querySelectorAll('[data-g]').forEach(i => { const v = M.grid[i.dataset.g]; i.type === 'checkbox' ? (i.checked = !!v) : (i.value = v); });
    gf.querySelectorAll('[data-m]').forEach(i => { i.value = M[i.dataset.m]; });
    gf.querySelector('[data-out="size"]').textContent = M.grid.size;
    gf.querySelectorAll('[data-blank-only]').forEach(e => e.classList.toggle('hidden', !!img));
    gf.querySelectorAll('[data-image-only]').forEach(e => e.classList.toggle('hidden', !img));
  }
  let gridEditPushed = false;
  gf.addEventListener('input', e => {
    const i = e.target; if (!i.dataset.g && !i.dataset.m) return;
    if (!gridEditPushed) { pushHistory(); gridEditPushed = true; }
    const v = i.type === 'checkbox' ? i.checked : (i.type === 'range' || i.type === 'number') ? Number(i.value) : i.value;
    if (i.dataset.g) M.grid[i.dataset.g] = v; else M[i.dataset.m] = v;
    if (i.dataset.g === 'cols' || i.dataset.g === 'rows') M.grid[i.dataset.g] = Math.max(2, Math.min(150, v || 2));
    gf.querySelector('[data-out="size"]').textContent = M.grid.size;
    redrawAll(); markDirty();
  });
  gf.addEventListener('change', () => { gridEditPushed = false; });

  // objeto selecionado
  const propById = id => M.props.find(p => p.id === id);
  function showPropSel() {
    const p = selectedProp && propById(selectedProp);
    $('prop-sel').classList.toggle('hidden', !p);
    if (p) { $('prop-scale').value = p.s || 1; $('prop-rot').value = p.r || 0; $('prop-rot-val').textContent = (p.r || 0) + '°'; }
  }
  function rotateSelected(delta, absolute) {
    const p = propById(selectedProp); if (!p) return;
    p.r = ((((absolute ? delta : (p.r || 0) + delta)) % 360) + 360) % 360;
    showPropSel(); drawObjects(); markDirty();
  }
  $('prop-rot').addEventListener('pointerdown', () => pushHistory());
  $('prop-rot').addEventListener('input', e => rotateSelected(Number(e.target.value), true));
  $('prop-rot-l').addEventListener('click', () => { pushHistory(); rotateSelected(-90); });
  $('prop-rot-r').addEventListener('click', () => { pushHistory(); rotateSelected(90); });
  $('prop-scale').addEventListener('pointerdown', () => pushHistory());
  $('prop-scale').addEventListener('input', e => { const p = propById(selectedProp); if (p) { p.s = Number(e.target.value); drawObjects(); markDirty(); } });
  $('prop-flip').addEventListener('click', () => { const p = propById(selectedProp); if (p) { pushHistory(); p.f = !p.f; drawObjects(); markDirty(); } });
  $('prop-dup').addEventListener('click', () => {
    const p = propById(selectedProp); if (!p) return;
    pushHistory(); const n = { ...p, id: newId(), x: p.x + M.grid.size, y: p.y };
    M.props.push(n); selectedProp = n.id; drawObjects(); markDirty();
  });
  $('prop-del').addEventListener('click', deleteSelectedProp);
  function deleteSelectedProp() {
    if (!selectedProp) return;
    pushHistory(); M.props = M.props.filter(p => p.id !== selectedProp); selectedProp = null; showPropSel(); drawObjects(); markDirty();
  }
  const newId = () => Math.random().toString(36).slice(2, 9);

  // ================================================================== histórico, salvar e sincronizar
  const undo = [], redo = [];
  function pushHistory() { undo.push(JSON.stringify(M)); if (undo.length > 80) undo.shift(); redo.length = 0; }
  function restore(from, to) {
    if (!from.length) return;
    to.push(JSON.stringify(M)); M = normalize(JSON.parse(from.pop()));
    selectedProp = null; showPropSel(); syncGridForm(); redrawAll(); markDirty();
  }
  $('undo').addEventListener('click', () => restore(undo, redo));
  $('redo').addEventListener('click', () => restore(redo, undo));

  let dirty = false, saving = false, saveTimer = null, lastThumb = 0;
  const saveState = t => { $('save-state').textContent = t; };
  function markDirty() { dirty = true; saveState('editando…'); clearTimeout(saveTimer); saveTimer = setTimeout(save, 900); }
  function thumbnail() {
    const k = Math.min(1, 480 / Math.max(W, H)), c = document.createElement('canvas');
    c.width = Math.max(1, Math.round(W * k)); c.height = Math.max(1, Math.round(H * k));
    const g = c.getContext('2d'); g.fillStyle = M.bg; g.fillRect(0, 0, c.width, c.height);
    if (img) { g.globalAlpha = M.imageOpacity; g.drawImage(img, 0, 0, c.width, c.height); g.globalAlpha = 1; }
    for (const k2 of ['terrain', 'grid', 'objects']) g.drawImage(cv[k2], 0, 0, c.width, c.height);
    return c.toDataURL('image/jpeg', 0.72);
  }
  async function save() {
    if (!dirty) return;
    if (saving) { clearTimeout(saveTimer); saveTimer = setTimeout(save, 400); return; }
    saving = true; dirty = false; saveState('salvando…');
    const body = { data: M, version };
    if (Date.now() - lastThumb > 8000) { try { body.thumb = thumbnail(); lastThumb = Date.now(); } catch { /* imagem externa */ } }
    try {
      const res = await fetch(D.dataUrl, { method: 'PUT', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf() }, body: JSON.stringify(body) });
      const j = await res.json().catch(() => ({}));
      if (res.status === 409) {
        M = normalize(j.data); version = j.version; undo.length = 0; redo.length = 0; syncGridForm(); redrawAll();
        toast('Outra pessoa salvou o mapa antes: carreguei a versão mais nova.', true); saveState('');
      } else if (res.ok) { version = j.version; saveState(dirty ? 'editando…' : 'salvo'); }
      else { dirty = true; saveState('erro ao salvar'); toast(j.error || 'Não foi possível salvar o mapa.', true); }
    } catch { dirty = true; saveState('sem conexão'); }
    saving = false;
    if (dirty) { clearTimeout(saveTimer); saveTimer = setTimeout(save, 2000); }
  }
  function flushSave() { if (dirty) { clearTimeout(saveTimer); lastThumb = 0; save(); } }   // miniatura atualizada ao sair
  const csrf = () => document.querySelector('meta[name="csrf-token"]').content;
  window.addEventListener('beforeunload', e => { if (dirty || saving) { flushSave(); e.preventDefault(); e.returnValue = ''; } });

  // ================================================================== edição (ponteiro)
  let stroke = null;   // {type, erase, done:Set}
  function brushCells(cell) {
    if (!cell) return [];
    if (brush === 1) return [cell];
    const out = [], [c0, r0] = cell, n = brush;
    if (!isHex()) {
      const h = Math.floor((n - 1) / 2);
      for (let r = r0 - h; r < r0 - h + n; r++) for (let c = c0 - h; c < c0 - h + n; c++) if (inside(c, r)) out.push([c, r]);
      return out;
    }
    // hexágono: anéis por busca em largura
    const seen = new Set([key(c0, r0)]); let frontier = [cell]; out.push(cell);
    for (let i = 1; i < Math.ceil(n / 2) + (n > 2 ? 0 : 1); i++) {
      const next = [];
      for (const [c, r] of frontier) for (const nb of neighbors(c, r)) {
        const k = key(...nb); if (seen.has(k) || !inside(...nb)) continue; seen.add(k); next.push(nb); out.push(nb);
      }
      frontier = next;
    }
    return out;
  }
  function paint(cell, erase) {
    for (const [c, r] of brushCells(cell)) {
      const k = key(c, r);
      if (stroke.done.has(k)) continue; stroke.done.add(k);
      if (erase) delete M.terrain[k]; else M.terrain[k] = terrainSel;
      drawCell(c, r);
    }
  }
  function floodFill(cell, erase) {
    const target = M.terrain[key(...cell)] || M.base || '';
    const repl = erase ? '' : terrainSel;
    if (target === (repl || M.base || '') && !erase) return;
    const q = [cell], seen = new Set([key(...cell)]);
    let n = 0;
    while (q.length && n < 25000) {
      const [c, r] = q.pop(); n++;
      const k = key(c, r);
      if (repl && repl !== M.base) M.terrain[k] = repl; else delete M.terrain[k];
      for (const nb of neighbors(c, r)) {
        const nk = key(...nb);
        if (!seen.has(nk) && inside(...nb) && (M.terrain[nk] || M.base || '') === target) { seen.add(nk); q.push(nb); }
      }
    }
    drawTerrainAll();
  }
  function propAt(x, y) {
    const sorted = [...M.props].sort((a, b) => b.y - a.y);
    return sorted.find(p => { const r = propBounds(p); return r && x >= r.x && x <= r.x + r.w && y >= r.y && y <= r.y + r.h; });
  }
  function snapPoint(x, y) {
    if (!$('snap').checked || !gridOn()) return { x, y };
    const cell = cellAt(x, y); if (!cell) return { x, y };
    const c = center(...cell);
    return { x: c.x, y: c.y + (isHex() ? R() * 0.75 : M.grid.size / 2) };
  }

  function drawHover(e) {
    clearUi();
    if (mode !== 'edit' || action) return;
    const p = toWorld(e.clientX, e.clientY), g = ctx.ui;
    if ((tool === 'terrain' || tool === 'fill') && gridOn()) {
      const cells = tool === 'fill' ? [cellAt(p.x, p.y)].filter(Boolean) : brushCells(cellAt(p.x, p.y));
      g.save(); g.fillStyle = 'rgba(255,255,255,0.25)'; g.strokeStyle = 'rgba(255,255,255,0.9)'; g.lineWidth = 2;
      g.beginPath(); cells.forEach(([c, r]) => cellPath(g, c, r)); g.fill(); g.stroke(); g.restore();
    } else if (tool === 'walls') {
      const ed = edgeAt(p.x, p.y);
      if (ed) drawWall(g, ed.seg, wallSel, true);
    } else if (tool === 'props' && assetSel && !propAt(p.x, p.y)) {
      const s = snapPoint(p.x, p.y), r = propRect({ a: assetSel, x: s.x, y: s.y, s: 1 }), im = propImage(assetSel);
      if (r && im?.complete) { g.save(); g.globalAlpha = 0.6; g.drawImage(im, r.x, r.y, r.w, r.h); g.restore(); }
    }
  }

  // ================================================================== marcadores e tokens (modo jogar)
  let pins = new Map(D.pins.map(p => [p.id, p]));
  let selected = null, placing = null, lastLocal = 0;
  const touched = () => { lastLocal = Date.now(); };
  function scalePin(n) {
    const k = 1 / (view?.z || 1);
    n.style.transform = n.classList.contains('token') ? `translate(-50%, -50%) scale(${k})` : `translate(-50%, -100%) scale(${k})`;
  }
  function renderPin(p) {
    const n = el('div', 'pin' + (p.kind === 'token' ? ' token' : '') + (selected === p.id ? ' selected' : ''));
    n.dataset.id = p.id;
    n.style.left = p.x * W + 'px'; n.style.top = p.y * H + 'px';
    n.title = p.label || (p.article?.title ?? '');
    if (p.kind === 'token') {
      const coin = el('div', 'coin'); coin.style.borderColor = p.color;
      if (p.image) { const i = el('img', 'size-full object-cover pointer-events-none'); i.src = p.image; i.draggable = false; i.referrerPolicy = 'no-referrer'; coin.append(i); }
      else coin.textContent = (p.label || p.article?.title || '?').slice(0, 2).toUpperCase();
      n.append(coin);
      if (p.label || p.article) { const t = el('div', 'tag', p.label || p.article.title); t.style.top = '52px'; n.append(t); }
    } else {
      const d = el('div', 'drop'); d.style.background = p.color;
      d.append(p.file ? ui('clip', 'size-3.5') : (p.article ? glyph(p.article.icon) : el('span')));
      n.append(d);
      if (p.label || p.article) { const t = el('div', 'tag', p.label || p.article.title); t.style.top = '34px'; n.append(t); }
    }
    scalePin(n);
    return n;
  }
  function renderPins() {
    pinsEl.replaceChildren();
    [...pins.values()].sort((a, b) => (a.kind === 'token') - (b.kind === 'token')).forEach(p => pinsEl.append(renderPin(p)));
  }
  const savePin = (p, fields) => { touched(); return api('PATCH', `${D.api}/${p.id}`, fields).then(u => { pins.set(p.id, u); return u; }); };

  function closeSide() { selected = null; side.classList.add('hidden'); side.classList.remove('flex'); renderPins(); }
  function openSide(p) {
    selected = p.id; renderPins();
    side.classList.remove('hidden'); side.classList.add('flex');
    side.replaceChildren();
    const isToken = p.kind === 'token';
    const head = el('div', 'flex items-center justify-between border-b border-line p-4');
    const h = el('p', 'flex items-center gap-2 font-display text-lg text-ink'); h.append(iconLabel(ri(isToken ? 'coin' : 'flag'), isToken ? 'Token' : 'Marcador')); head.append(h);
    const x = el('button', 'btn btn-ghost btn-sm btn-icon'); x.append(ui('x')); x.title = 'Fechar (Esc)'; x.setAttribute('aria-label', 'Fechar'); x.addEventListener('click', closeSide); head.append(x);
    side.append(head);
    const body = el('div', 'space-y-4 p-4'); side.append(body);

    if (p.article) {
      const a = el('a', 'group block overflow-hidden rounded-xl border border-line hover:border-accent'); a.href = p.article.url;
      if (p.article.cover) { const i = el('img', 'h-32 w-full object-cover'); i.src = p.article.cover; i.referrerPolicy = 'no-referrer'; a.append(i); }
      const t = el('div', 'p-3');
      const tt = el('p', 'flex items-center gap-1.5 font-semibold text-ink group-hover:text-accent-ink'); tt.append(glyph(p.article.icon), el('span', 'flex-1', p.article.title), ui('external', 'size-3.5 text-faint')); t.append(tt);
      if (p.article.summary) t.append(el('p', 'mt-1 text-sm text-muted', p.article.summary));
      a.append(t); body.append(a);
    }
    if (p.file) {
      const a = el('a', 'flex items-center gap-3 rounded-xl border border-line p-3 hover:border-accent');
      a.href = p.file.url; a.target = '_blank'; a.rel = 'noopener';
      a.append(ri(p.file.is_image ? 'picture' : 'redbook', 32));
      const t = el('div', 'min-w-0'); t.append(el('p', 'truncate text-sm font-medium text-ink', p.file.name), el('p', 'text-xs text-accent-ink', 'abrir / baixar'));
      a.append(t); body.append(a);
    }
    const field = (label, input) => { const w = el('label', 'block'); w.append(el('span', 'label', label), input); body.append(w); return input; };
    const name = field('Nome', el('input', 'input py-1.5'));
    name.value = p.label; name.placeholder = isToken ? 'Nome do jogador / personagem' : 'Nome do local';
    name.addEventListener('change', () => savePin(p, { label: name.value }).then(renderPins));
    const page = field(isToken ? 'Personagem (página)' : 'Página ligada', el('select', 'input py-1.5'));
    page.append(new Option('— nenhuma —', ''));
    D.pages.forEach(pg => page.append(new Option(`${glyphText(pg.icon)} ${pg.title}`.trim(), pg.id, false, pg.id === p.article_id)));
    page.addEventListener('change', () => savePin(p, { article_id: page.value ? Number(page.value) : null }).then(u => { renderPins(); openSide(u); }));
    const uploadTo = async (file, imagesOnly) => {
      const fd = new FormData(); fd.append('files', file);
      const r = await api('POST', D.upload + (imagesOnly ? '?images=1' : ''), fd);
      D.files.unshift(r.files[0]); return r.files[0].id;
    };
    if (isToken) {
      const portrait = el('div', 'flex items-center gap-2');
      const up = el('label', 'btn btn-outline btn-sm cursor-pointer', p.image_file_id ? 'Trocar retrato' : 'Enviar retrato');
      const fi = el('input', 'hidden'); fi.type = 'file'; fi.accept = 'image/*'; up.append(fi);
      fi.addEventListener('change', async () => { if (fi.files[0]) { openSide(await savePin(p, { image_file_id: await uploadTo(fi.files[0], true) })); renderPins(); } });
      portrait.append(up);
      if (p.image_file_id) { const rm = el('button', 'btn btn-ghost btn-sm', 'Remover'); rm.addEventListener('click', async () => { openSide(await savePin(p, { image_file_id: null })); renderPins(); }); portrait.append(rm); }
      field('Retrato', portrait);
    } else {
      const attach = el('div', 'space-y-2');
      const sel = el('select', 'input py-1.5'); sel.append(new Option('— nenhum —', ''));
      D.files.forEach(f => sel.append(new Option(f.name, f.id, false, f.id === p.file_id)));
      sel.addEventListener('change', async () => { openSide(await savePin(p, { file_id: sel.value ? Number(sel.value) : null })); renderPins(); });
      const up = el('label', 'btn btn-outline btn-sm w-full cursor-pointer'); up.append(iconLabel(ui('upload', 'size-3.5'), 'Enviar livro / arquivo'));
      const fi = el('input', 'hidden'); fi.type = 'file'; up.append(fi);
      fi.addEventListener('change', async () => { if (fi.files[0]) { openSide(await savePin(p, { file_id: await uploadTo(fi.files[0], false) })); renderPins(); } });
      attach.append(sel, up); field('Livro / arquivo anexado', attach);
    }
    const colors = el('div', 'flex flex-wrap gap-2');
    D.colors.forEach(c => {
      const b = el('button', 'size-7 rounded-full ring-offset-2 ring-offset-surface border border-black/20' + (c === p.color ? ' ring-2 ring-[var(--a500)]' : ''));
      b.style.background = c; b.title = 'Cor'; b.setAttribute('aria-label', 'Cor ' + c); b.addEventListener('click', () => savePin(p, { color: c }).then(u => { renderPins(); openSide(u); }));
      colors.append(b);
    });
    field('Cor', colors);
    const note = field('Anotações', el('textarea', 'input text-sm'));
    note.rows = 5; note.value = p.note; note.placeholder = isToken ? 'HP, condições, inventário…' : 'O que há neste lugar? Segredos, encontros…';
    note.addEventListener('change', () => savePin(p, { note: note.value }));
    const del = el('button', 'btn btn-ghost btn-sm btn-quiet-danger w-full'); del.append(iconLabel(ui('trash', 'size-3.5'), 'Apagar ' + (isToken ? 'token' : 'marcador')));
    del.addEventListener('click', async () => { if (!confirm(`Apagar ${isToken ? 'o token' : 'o marcador'}${p.label ? ' “' + p.label + '”' : ''}?`)) return; touched(); await api('DELETE', `${D.api}/${p.id}`); pins.delete(p.id); closeSide(); });
    body.append(del);
  }
  function startPlacing(kind) { placing = kind; vp.classList.add('placing'); $('place-hint').classList.remove('hidden'); }
  function stopPlacing() { placing = null; vp.classList.remove('placing'); $('place-hint').classList.add('hidden'); }
  $('add-pin').addEventListener('click', () => startPlacing('pin'));
  $('add-token').addEventListener('click', () => startPlacing('token'));

  // ================================================================== eventos do ponteiro
  let action = null, spaceDown = false;
  vp.addEventListener('contextmenu', e => e.preventDefault());
  vp.addEventListener('pointerdown', async e => {
    if (!view) return;
    const p = toWorld(e.clientX, e.clientY);
    const wantsPan = e.button === 1 || spaceDown || (mode === 'edit' && tool === 'move') || (mode === 'play' && e.button === 0 && !e.target.closest('.pin') && !placing);
    if (wantsPan || (mode === 'play' && e.button !== 0)) {
      if (!wantsPan) return;
      e.preventDefault();
      action = { type: 'pan', sx: e.clientX, sy: e.clientY, vx: view.x, vy: view.y };
      vp.classList.add('panning'); return;
    }
    if (mode === 'play') {
      if (placing) {
        const f = toFrac(e.clientX, e.clientY), kind = placing; stopPlacing(); touched();
        const np = await api('POST', D.api, { kind, ...f, color: kind === 'token' ? '#3b82f6' : '#ef4444', label: kind === 'token' ? 'Jogador' : '' });
        pins.set(np.id, np); renderPins(); openSide(np); return;
      }
      const pinEl = e.target.closest('.pin');
      if (pinEl) action = { type: 'pin', p: pins.get(Number(pinEl.dataset.id)), n: pinEl, moved: false, sx: e.clientX, sy: e.clientY };
      return;
    }
    // ----- modo edição
    const erase = e.button === 2;
    if (tool === 'terrain' && gridOn()) {
      pushHistory(); stroke = { done: new Set() }; action = { type: 'paint', erase, last: p };
      paint(cellAt(p.x, p.y), erase);
    } else if (tool === 'fill' && gridOn()) {
      const cell = cellAt(p.x, p.y); if (!cell) return;
      pushHistory(); floodFill(cell, erase); markDirty();
    } else if (tool === 'walls' && gridOn()) {
      pushHistory(); stroke = { done: new Set() }; action = { type: 'walls', erase, last: p };
      wallAt(p, erase);
    } else if (tool === 'props') {
      const hit = propAt(p.x, p.y);
      if (hit && erase) { selectedProp = hit.id; deleteSelectedProp(); return; }
      if (hit) {
        pushHistory(); selectedProp = hit.id; showPropSel(); drawObjects();
        action = { type: 'prop', prop: hit, dx: p.x - hit.x, dy: p.y - hit.y, moved: false };
      } else if (assetSel && !erase) {
        pushHistory();
        const s = snapPoint(p.x, p.y), np = { id: newId(), a: assetSel, x: Math.round(s.x), y: Math.round(s.y), s: 1, r: 0, f: false };
        M.props.push(np); selectedProp = np.id; showPropSel(); drawObjects(); markDirty();
      } else { selectedProp = null; showPropSel(); drawObjects(); }
    } else if (!gridOn() && ['terrain', 'fill', 'walls'].includes(tool)) {
      toast('Ative uma grade na ferramenta “Grade” para pintar terreno e paredes.', true);
    }
    clearUi();
  });
  function lockedEdge(p) {
    // grade quadrada: depois da 1ª borda o traço segue o mesmo eixo (muro reto e comprido)
    const s = M.grid.size;
    if (stroke.axis === 'h') {
      const r = Math.round(p.y / s), c = Math.floor(p.x / s);
      if (c < 0 || c >= M.grid.cols || r < 0 || r > M.grid.rows) return null;
      return { key: edgeKey([c, r - 1], [c, r]), seg: [c * s, r * s, (c + 1) * s, r * s] };
    }
    const c = Math.round(p.x / s), r = Math.floor(p.y / s);
    if (r < 0 || r >= M.grid.rows || c < 0 || c > M.grid.cols) return null;
    return { key: edgeKey([c - 1, r], [c, r]), seg: [c * s, r * s, c * s, (r + 1) * s] };
  }
  function wallAt(p, erase) {
    let ed = stroke.axis ? lockedEdge(p) : edgeAt(p.x, p.y);
    if (ed && !stroke.axis && !isHex()) stroke.axis = ed.seg[1] === ed.seg[3] ? 'h' : 'v';
    if (!ed || stroke.done.has(ed.key)) return;
    stroke.done.add(ed.key);
    if (erase) delete M.walls[ed.key]; else M.walls[ed.key] = wallSel;
    drawObjects();
  }
  window.addEventListener('pointermove', e => {
    if (!action) { if (e.target.closest?.('#mviewport')) drawHover(e); return; }
    const p = toWorld(e.clientX, e.clientY);
    if (action.type === 'pan') { view.x = action.vx + e.clientX - action.sx; view.y = action.vy + e.clientY - action.sy; applyView(); }
    else if (action.type === 'paint' || action.type === 'walls') {
      // mouse rápido pula quadrados: percorre o caminho desde o último ponto
      const last = action.last || p, dist = Math.hypot(p.x - last.x, p.y - last.y);
      const steps = Math.max(1, Math.ceil(dist / (M.grid.size / 4)));
      for (let i = 1; i <= steps; i++) {
        const q = { x: last.x + (p.x - last.x) * i / steps, y: last.y + (p.y - last.y) * i / steps };
        action.type === 'paint' ? paint(cellAt(q.x, q.y), action.erase) : wallAt(q, action.erase);
      }
      action.last = p;
    }
    else if (action.type === 'prop') {
      const s = snapPoint(p.x - action.dx, p.y - action.dy + (($('snap').checked && gridOn()) ? 0 : 0));
      action.prop.x = Math.round($('snap').checked && gridOn() ? s.x : p.x - action.dx);
      action.prop.y = Math.round($('snap').checked && gridOn() ? s.y : p.y - action.dy);
      action.moved = true; drawObjects();
    } else if (action.type === 'pin') {
      if (!action.moved && Math.hypot(e.clientX - action.sx, e.clientY - action.sy) < 4) return;
      const f = toFrac(e.clientX, e.clientY);
      action.p.x = f.x; action.p.y = f.y; action.moved = true;
      action.n.style.left = f.x * W + 'px'; action.n.style.top = f.y * H + 'px';
    }
  });
  window.addEventListener('pointerup', () => {
    if (!action) return;
    const a = action; action = null; vp.classList.remove('panning');
    if (a.type === 'paint' || a.type === 'walls') { stroke = null; markDirty(); }
    if (a.type === 'prop') { if (a.moved) markDirty(); else undo.pop(); }
    if (a.type === 'pin') { if (a.moved) savePin(a.p, { x: a.p.x, y: a.p.y }); else openSide(a.p); }
    if (a.type === 'pan' && mode === 'play' && Math.abs(view.x - a.vx) + Math.abs(view.y - a.vy) < 3 && selected) closeSide();
  });
  vp.addEventListener('pointerleave', clearUi);
  vp.addEventListener('wheel', e => { e.preventDefault(); zoomAt(Math.exp(-e.deltaY * (e.ctrlKey ? 0.01 : 0.0015)), e.clientX, e.clientY); }, { passive: false });
  document.querySelectorAll('[data-zoom]').forEach(b => b.addEventListener('click', () => zoomAt(Number(b.dataset.zoom))));
  $('fit').addEventListener('click', fit);

  document.addEventListener('keydown', e => {
    const typing = e.target.closest('input, textarea, select');
    if (e.key === ' ' && !typing) { spaceDown = true; vp.classList.add('tool-move'); e.preventDefault(); }
    if (e.key === 'Escape') { stopPlacing(); if (!typing) closeSide(); }
    if (typing || mode !== 'edit') return;
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') { e.preventDefault(); e.shiftKey ? restore(redo, undo) : restore(undo, redo); }
    else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'y') { e.preventDefault(); restore(redo, undo); }
    else if ((e.key === 'Delete' || e.key === 'Backspace') && selectedProp) { e.preventDefault(); deleteSelectedProp(); }
    else if (e.key.toLowerCase() === 'r' && selectedProp && !e.ctrlKey && !e.metaKey) { pushHistory(); rotateSelected(e.shiftKey ? -90 : 90); }
    else if (!e.ctrlKey && !e.metaKey) {
      const t = { b: 'terrain', f: 'fill', w: 'walls', o: 'props' }[e.key.toLowerCase()];
      if (t) setTool(t);
    }
  });
  document.addEventListener('keyup', e => { if (e.key === ' ') { spaceDown = false; vp.classList.toggle('tool-move', tool === 'move' && mode === 'edit'); } });

  // ================================================================== sincronização (outros jogadores/editores)
  setInterval(async () => {
    if (document.hidden || action) return;
    try {
      if (!dirty && !saving) {
        const r = await fetch(`${D.dataUrl}?v=${version}`, { headers: { Accept: 'application/json' } });
        if (r.status === 200) { const j = await r.json(); if (!dirty && !action) { M = normalize(j.data); version = j.version; syncGridForm(); redrawAll(); } }
      }
      if (Date.now() - lastLocal > 3000 && !side.contains(document.activeElement)) {
        const r = await fetch(D.api, { headers: { Accept: 'application/json' } });
        if (r.ok) {
          const list = await r.json();
          const mine = [...pins.values()].sort((a, b) => (b.kind > a.kind) - (b.kind < a.kind) || a.id - b.id);
          if (JSON.stringify(list) !== JSON.stringify(mine)) { pins = new Map(list.map(p => [p.id, p])); if (selected && !pins.has(selected)) closeSide(); else renderPins(); }
        }
      }
    } catch { /* tenta de novo */ }
  }, 4000);

  // ================================================================== início
  async function start() {
    await loadKit();
    computeSize();
    if (!view) fit(); else applyView();
    drawTerrainAll(); drawGrid(); drawObjects(); renderPins();
    buildPalette(); setTool('terrain'); setMode(D.startEdit ? 'edit' : 'play');
    window.addEventListener('resize', () => applyView());
    // mapa novo (ou antigo sem miniatura): salva uma vez para a lista de mapas mostrar a prévia
    if (!D.hasThumb) setTimeout(() => { dirty = true; lastThumb = 0; save(); }, 600);
  }
  if (img && !img.complete) img.addEventListener('load', start); else start();
})();
