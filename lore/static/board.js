// Mapa mental: cards (ideia, página, imagem, arquivo) ligados por setas com rótulo.
// Pan/zoom no canvas, arrastar páginas da lateral, colar/soltar imagens, sincronização entre colaboradores.
(() => {
  const DATA = JSON.parse(document.getElementById('board-data').textContent);
  const API = DATA.api;                       // /w/<wid>/b/<bid>
  const COLORS = DATA.colors;                 // {nome: [fundo, bolinha]}
  const $ = id => document.getElementById(id);
  const viewport = $('viewport'), world = $('world'), nodesEl = $('nodes'), edgeGroup = $('edge-group'), tempLine = $('temp-line');
  const NS = 'http://www.w3.org/2000/svg';

  let cards = new Map(DATA.state.cards.map(c => [c.id, c]));
  let links = DATA.state.links;
  const els = new Map();                      // id -> elemento do card
  let selection = null;                       // {type: 'card'|'link', id}
  let action = null;                          // pan | move | connect | resize
  let editing = false;
  let lastLocalChange = 0;

  // ------------------------------------------------------------------ helpers
  const el = (tag, cls = '', text) => { const n = document.createElement(tag); if (cls) n.className = cls; if (text !== undefined) n.textContent = text; return n; };
  const touched = () => { lastLocalChange = Date.now(); };
  const patchCard = (c, fields) => { touched(); return api('PATCH', `${API}/cards/${c.id}`, fields).then(u => { Object.assign(c, u); }); };

  // ------------------------------------------------------------------ view (pan/zoom)
  const viewKey = 'board-view-' + DATA.boardId;
  let view = JSON.parse(localStorage.getItem(viewKey) || 'null') || { x: 80, y: 60, z: 1 };
  function applyView() {
    world.style.transform = `translate(${view.x}px, ${view.y}px) scale(${view.z})`;
    viewport.style.backgroundPosition = `${view.x}px ${view.y}px`;
    viewport.style.backgroundSize = `${24 * view.z}px ${24 * view.z}px`;
    $('zoom-level').textContent = Math.round(view.z * 100) + '%';
    localStorage.setItem(viewKey, JSON.stringify(view));
  }
  function toWorld(cx, cy) {
    const r = viewport.getBoundingClientRect();
    return { x: (cx - r.left - view.x) / view.z, y: (cy - r.top - view.y) / view.z };
  }
  function zoomAt(factor, cx, cy) {
    const r = viewport.getBoundingClientRect();
    if (cx === undefined) { cx = r.left + r.width / 2; cy = r.top + r.height / 2; }
    const before = toWorld(cx, cy);
    view.z = Math.min(2.5, Math.max(0.15, view.z * factor));
    view.x = cx - r.left - before.x * view.z;
    view.y = cy - r.top - before.y * view.z;
    applyView();
  }
  function fit() {
    if (!cards.size) { view = { x: 80, y: 60, z: 1 }; return applyView(); }
    let x1 = Infinity, y1 = Infinity, x2 = -Infinity, y2 = -Infinity;
    for (const c of cards.values()) {
      const e = els.get(c.id);
      x1 = Math.min(x1, c.x); y1 = Math.min(y1, c.y);
      x2 = Math.max(x2, c.x + (e?.offsetWidth || c.w)); y2 = Math.max(y2, c.y + (e?.offsetHeight || 120));
    }
    const r = viewport.getBoundingClientRect(), pad = 60;
    view.z = Math.min(1.2, Math.max(0.15, Math.min((r.width - pad * 2) / (x2 - x1), (r.height - pad * 2) / (y2 - y1))));
    view.x = (r.width - (x2 - x1) * view.z) / 2 - x1 * view.z;
    view.y = (r.height - (y2 - y1) * view.z) / 2 - y1 * view.z;
    applyView();
  }
  function screenCenter(jitter = true) {
    const r = viewport.getBoundingClientRect();
    const p = toWorld(r.left + r.width / 2, r.top + r.height / 2);
    const j = () => jitter ? Math.random() * 80 - 40 : 0;
    return { x: Math.round(p.x - 120 + j()), y: Math.round(p.y - 60 + j()) };
  }

  // ------------------------------------------------------------------ cards
  function renderCard(c) {
    const [bg] = COLORS[c.color] || COLORS.white;
    const n = el('div', `node rounded-xl text-stone-800 shadow-lg shadow-black/25 ring-1 ring-black/10 ${bg}`);
    n.dataset.id = c.id;
    Object.assign(n.style, { left: c.x + 'px', top: c.y + 'px', width: c.w + 'px' });
    if (selection?.type === 'card' && selection.id === c.id) n.classList.add('selected');

    if (c.kind === 'article') {
      const a = c.article;
      if (!a) { n.append(el('p', 'p-3 text-sm italic text-stone-500', 'Página apagada.')); }
      else {
        n.classList.add('overflow-hidden');
        n.append(el('div', 'h-1.5 bg-[var(--a500)]'));
        if (a.cover) {
          const img = el('img', 'h-28 w-full object-cover pointer-events-none');
          img.src = a.cover; img.referrerPolicy = 'no-referrer'; img.draggable = false;
          img.style.objectPosition = `center ${a.cover_pos ?? 50}%`;
          img.addEventListener('load', renderEdges);
          n.append(img);
        }
        const body = el('div', 'p-3');
        body.append(el('p', 'text-[10px] font-semibold uppercase tracking-wider text-stone-500', a.category));
        body.append(el('p', 'mt-0.5 font-bold leading-snug text-stone-900', `${a.icon} ${a.title}`));
        if (a.summary) body.append(el('p', 'mt-1 text-xs leading-relaxed text-stone-600', a.summary));
        n.append(body);
        n.title = 'Dois cliques para abrir a página';
      }
    } else if (c.kind === 'image') {
      n.classList.add('overflow-hidden', 'p-1.5');
      if (c.file) {
        const img = el('img', 'w-full rounded-lg pointer-events-none');
        img.src = c.file.url; img.draggable = false;
        img.addEventListener('load', renderEdges);
        n.append(img);
      } else n.append(el('p', 'p-3 text-sm italic text-stone-500', 'Imagem apagada do acervo.'));
      if (c.title) n.append(el('p', 'px-2 pb-1 pt-2 text-xs italic text-stone-600 whitespace-pre-wrap', c.title));
    } else if (c.kind === 'file') {
      const f = c.file;
      const row = el('div', 'flex items-center gap-3 p-3');
      row.append(el('div', 'text-3xl', f && f.name.toLowerCase().endsWith('.pdf') ? '📕' : '📘'));
      const info = el('div', 'min-w-0');
      info.append(el('p', 'truncate text-sm font-semibold text-stone-900', f ? f.name : 'Arquivo apagado'));
      if (f) {
        const open = el('a', 'text-xs text-stone-600 underline', 'abrir / baixar');
        open.href = f.url; open.target = '_blank'; open.rel = 'noopener';
        info.append(open);
      }
      row.append(info); n.append(row);
      if (c.title) n.append(el('p', 'px-3 pb-3 text-xs text-stone-600 whitespace-pre-wrap', c.title));
    } else {
      const body = el('div', 'p-3');
      body.append(el('p', 'text-[10px] font-semibold uppercase tracking-wider text-stone-500', '💡 Ideia'));
      if (c.title) body.append(el('p', 'mt-0.5 font-bold text-stone-900', c.title));
      body.append(el('p', 'mt-0.5 whitespace-pre-wrap break-words text-sm leading-relaxed text-stone-700', c.body || (c.title ? '' : 'Dois cliques para escrever…')));
      if (!c.body && !c.title) body.lastChild.classList.add('italic', 'text-stone-400');
      n.append(body);
    }
    n.append(el('div', 'handle'));
    const grip = el('div', 'grip absolute bottom-0 right-0 h-4 w-4 cursor-ew-resize opacity-0 hover:opacity-60');
    grip.style.background = 'linear-gradient(135deg, transparent 50%, rgba(0,0,0,.45) 50%)';
    n.addEventListener('mouseenter', () => grip.classList.replace('opacity-0', 'opacity-30'));
    n.addEventListener('mouseleave', () => grip.classList.replace('opacity-30', 'opacity-0'));
    n.append(grip);
    return n;
  }

  function renderAll() {
    nodesEl.replaceChildren(); els.clear();
    for (const c of cards.values()) { const n = renderCard(c); els.set(c.id, n); nodesEl.append(n); }
    $('empty').classList.toggle('hidden', cards.size > 0);
    $('empty').classList.toggle('grid', cards.size === 0);
    renderEdges(); renderSelBar();
  }
  function rerenderCard(c) {
    const old = els.get(c.id); const n = renderCard(c);
    els.set(c.id, n); old ? old.replaceWith(n) : nodesEl.append(n);
    renderEdges();
  }

  // ------------------------------------------------------------------ conexões
  function box(c) { const e = els.get(c.id); return { x: c.x, y: c.y, w: e.offsetWidth, h: e.offsetHeight }; }
  function borderPoint(b, tx, ty) {
    const cx = b.x + b.w / 2, cy = b.y + b.h / 2, dx = tx - cx, dy = ty - cy;
    if (!dx && !dy) return { x: cx, y: cy };
    const t = Math.min(dx ? (b.w / 2 + 6) / Math.abs(dx) : Infinity, dy ? (b.h / 2 + 6) / Math.abs(dy) : Infinity);
    return { x: cx + dx * t, y: cy + dy * t };
  }
  function renderEdges() {
    edgeGroup.replaceChildren();
    for (const l of links) {
      const a = cards.get(l.from_card), b = cards.get(l.to_card);
      if (!a || !b || !els.has(a.id) || !els.has(b.id)) continue;
      const ba = box(a), bb = box(b);
      const ca = { x: ba.x + ba.w / 2, y: ba.y + ba.h / 2 }, cb = { x: bb.x + bb.w / 2, y: bb.y + bb.h / 2 };
      const p1 = borderPoint(ba, cb.x, cb.y), p2 = borderPoint(bb, ca.x, ca.y);
      const sel = selection?.type === 'link' && selection.id === l.id;
      const g = document.createElementNS(NS, 'g');
      g.setAttribute('class', 'edge' + (sel ? ' selected' : '')); g.dataset.id = l.id;
      const d = `M${p1.x},${p1.y} L${p2.x},${p2.y}`;
      const line = document.createElementNS(NS, 'path');
      line.setAttribute('d', d); line.setAttribute('class', 'edge-line');
      line.setAttribute('marker-end', `url(#${sel ? 'arrow-sel' : 'arrow'})`);
      const hit = document.createElementNS(NS, 'path');
      hit.setAttribute('d', d); hit.setAttribute('class', 'edge-hit');
      g.append(line, hit);
      edgeGroup.append(g);            // precisa estar no DOM para medir o texto (getBBox)
      if (l.label) {
        const mx = (p1.x + p2.x) / 2, my = (p1.y + p2.y) / 2;
        const txt = document.createElementNS(NS, 'text');
        txt.setAttribute('x', mx); txt.setAttribute('y', my + 4); txt.setAttribute('text-anchor', 'middle');
        txt.setAttribute('class', 'edge-label'); txt.textContent = l.label;
        const bg = document.createElementNS(NS, 'rect');
        bg.setAttribute('class', 'edge-label-bg'); bg.setAttribute('rx', 6);
        g.append(bg, txt);
        const bbx = txt.getBBox();
        bg.setAttribute('x', bbx.x - 6); bg.setAttribute('y', bbx.y - 3);
        bg.setAttribute('width', bbx.width + 12); bg.setAttribute('height', bbx.height + 6);
        bg.style.cursor = 'pointer';
      }
    }
  }

  // ------------------------------------------------------------------ seleção e barra contextual
  function select(s) {
    selection = s;
    document.querySelectorAll('.node.selected').forEach(n => n.classList.remove('selected'));
    if (s?.type === 'card') els.get(s.id)?.classList.add('selected');
    renderEdges(); renderSelBar();
  }
  function barButton(label, fn, cls = '') {
    const b = el('button', 'whitespace-nowrap rounded-lg px-2.5 py-1.5 text-sm text-ink-2 hover:bg-surface-2 ' + cls, label);
    b.addEventListener('click', fn); return b;
  }
  function renderSelBar() {
    const bar = $('sel-bar'); bar.replaceChildren();
    if (!selection) { bar.classList.add('hidden'); bar.classList.remove('flex'); return; }
    bar.classList.remove('hidden'); bar.classList.add('flex');
    if (selection.type === 'card') {
      const c = cards.get(selection.id); if (!c) return select(null);
      for (const [name, [, dot]] of Object.entries(COLORS)) {
        const b = el('button', `size-5 rounded-full ${dot} ring-1 ring-black/20 mx-0.5 hover:scale-125 transition ${c.color === name ? 'ring-2 ring-[var(--a500)]' : ''}`);
        b.title = name; b.addEventListener('click', async () => { await patchCard(c, { color: name }); rerenderCard(c); renderSelBar(); });
        bar.append(b);
      }
      bar.append(el('span', 'mx-1 h-6 w-px bg-line'));
      if (c.kind === 'article' && c.article) bar.append(barButton('↗ Abrir página', () => { location.href = c.article.url; }));
      if (c.kind === 'note') bar.append(barButton('✎ Escrever', () => editCard(c)));
      if (c.kind === 'image' || c.kind === 'file') {
        bar.append(barButton('✎ Legenda', () => editCard(c)));
        if (c.file) bar.append(barButton('↗ Abrir', () => window.open(c.file.url, '_blank', 'noopener')));
      }
      bar.append(barButton('🗑 Apagar', () => removeSelection(), 'text-red-500'));
    } else {
      const l = links.find(x => x.id === selection.id); if (!l) return select(null);
      bar.append(barButton('🏷️ Rótulo', () => editLabel(l)));
      bar.append(barButton('⇄ Inverter seta', async () => { touched(); Object.assign(l, await api('PATCH', `${API}/links/${l.id}`, { reverse: true })); renderEdges(); }));
      bar.append(barButton('🗑 Apagar ligação', () => removeSelection(), 'text-red-500'));
    }
  }
  async function removeSelection() {
    if (!selection) return;
    touched();
    if (selection.type === 'card') {
      const c = cards.get(selection.id);
      if (c.kind === 'note' && (c.title || c.body) && !confirm('Apagar esta ideia?')) return;
      await api('DELETE', `${API}/cards/${c.id}`);
      cards.delete(c.id); links = links.filter(l => l.from_card !== c.id && l.to_card !== c.id);
      selection = null; renderAll();
    } else {
      await api('DELETE', `${API}/links/${selection.id}`);
      links = links.filter(l => l.id !== selection.id); selection = null; renderEdges(); renderSelBar();
    }
  }

  // ------------------------------------------------------------------ edição inline
  function editCard(c) {
    const n = els.get(c.id); if (!n) return;
    editing = true;
    const isNote = c.kind === 'note';
    const wrap = el('div', 'p-3 space-y-1');
    let title;
    if (isNote) {
      title = el('input', 'w-full bg-transparent font-bold text-stone-900 outline-none placeholder:text-stone-400');
      title.placeholder = 'Título (opcional)'; title.value = c.title;
      wrap.append(title);
    }
    const ta = el('textarea', 'block w-full resize-none bg-transparent text-sm leading-relaxed text-stone-800 outline-none placeholder:text-stone-400');
    ta.placeholder = isNote ? 'Escreva a ideia…' : 'Legenda…';
    ta.value = isNote ? c.body : c.title; ta.rows = 3;
    const grow = () => { ta.style.height = 'auto'; ta.style.height = ta.scrollHeight + 'px'; renderEdges(); };
    ta.addEventListener('input', grow);
    wrap.append(ta);
    wrap.append(el('p', 'text-[10px] text-stone-500', 'Ctrl+Enter ou clique fora para salvar · Esc cancela'));
    if (isNote) n.replaceChildren(wrap, el('div', 'handle'));
    else n.append(wrap);
    setTimeout(() => { (isNote && !c.title && !c.body ? ta : (title || ta)).focus(); grow(); }, 0);

    let done = false;
    const finish = async (save) => {
      if (done) return; done = true; editing = false;
      if (save) {
        const fields = isNote ? { title: title.value.trim(), body: ta.value } : { title: ta.value };
        if ((isNote && (fields.title !== c.title || fields.body !== c.body)) || (!isNote && fields.title !== c.title)) await patchCard(c, fields);
      }
      rerenderCard(c); if (selection?.id === c.id) els.get(c.id).classList.add('selected');
    };
    const onBlur = () => setTimeout(() => { if (!wrap.contains(document.activeElement)) finish(true); }, 0);
    [title, ta].filter(Boolean).forEach(i => {
      i.addEventListener('blur', onBlur);
      i.addEventListener('keydown', e => {
        e.stopPropagation();
        if (e.key === 'Escape') finish(false);
        if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) finish(true);
        if (e.key === 'Enter' && i === title) { e.preventDefault(); ta.focus(); }
      });
    });
  }

  function editLabel(l) {
    const a = cards.get(l.from_card), b = cards.get(l.to_card);
    const ba = box(a), bb = box(b);
    const mx = (ba.x + ba.w / 2 + bb.x + bb.w / 2) / 2, my = (ba.y + ba.h / 2 + bb.y + bb.h / 2) / 2;
    const r = viewport.getBoundingClientRect();
    const input = el('input', 'input absolute z-20 w-56 py-1 text-sm shadow-xl');
    input.placeholder = 'ex.: é filho de, traiu, governa…'; input.value = l.label;
    Object.assign(input.style, { left: (mx * view.z + view.x - 112) + 'px', top: (my * view.z + view.y - 16) + 'px' });
    viewport.append(input); input.focus(); input.select(); editing = true;
    let done = false;
    const finish = async save => {
      if (done) return; done = true; editing = false; input.remove();
      if (save && input.value !== l.label) { touched(); Object.assign(l, await api('PATCH', `${API}/links/${l.id}`, { label: input.value.trim() })); }
      renderEdges();
    };
    input.addEventListener('keydown', e => { e.stopPropagation(); if (e.key === 'Enter') finish(true); if (e.key === 'Escape') finish(false); });
    input.addEventListener('blur', () => finish(true));
    void r;
  }

  // ------------------------------------------------------------------ criar
  async function createCard(body) {
    touched();
    const c = await api('POST', `${API}/cards`, body);
    cards.set(c.id, c); renderAll(); select({ type: 'card', id: c.id });
    return c;
  }
  async function uploadFiles(files, pos) {
    if (!files.length) return;
    const p = pos || screenCenter();
    const fd = new FormData();
    [...files].forEach(f => fd.append('files', f));
    fd.append('x', Math.round(p.x)); fd.append('y', Math.round(p.y));
    $('sync').textContent = 'enviando…';
    try {
      touched();
      const res = await api('POST', `${API}/upload`, fd);
      res.cards.forEach(c => cards.set(c.id, c));
      if (res.errors?.length) toast(res.errors.join(' '), true);
      renderAll();
    } finally { $('sync').textContent = ''; }
  }

  $('add-note').addEventListener('click', async () => { const c = await createCard({ kind: 'note', ...screenCenter() }); editCard(c); });
  $('file-input').addEventListener('change', e => { uploadFiles(e.target.files); e.target.value = ''; });
  document.querySelectorAll('[data-zoom]').forEach(b => b.addEventListener('click', () => zoomAt(Number(b.dataset.zoom))));
  $('fit').addEventListener('click', fit);

  // ------------------------------------------------------------------ painel de páginas
  const panel = $('panel');
  $('toggle-panel').addEventListener('click', () => { panel.classList.toggle('hidden'); panel.classList.toggle('flex'); localStorage.setItem('board-panel', panel.classList.contains('flex') ? '1' : ''); });
  if (localStorage.getItem('board-panel')) { panel.classList.remove('hidden'); panel.classList.add('flex'); }
  function renderPageList() {
    const q = $('page-search').value.trim().toLowerCase();
    const onBoard = new Set([...cards.values()].filter(c => c.kind === 'article').map(c => c.article_id));
    const ul = $('page-list'); ul.replaceChildren();
    const list = DATA.pages.filter(p => !q || p.title.toLowerCase().includes(q));
    if (!list.length) {
      const li = el('li', 'p-3 text-sm text-faint'); li.append('Nenhuma página. ');
      const a = el('a', 'text-accent-ink underline', 'Criar uma'); a.href = DATA.newPage; li.append(a); ul.append(li);
    }
    for (const p of list) {
      const li = el('li', 'flex cursor-grab items-center gap-2 rounded-md px-2 py-1.5 text-sm text-ink-2 hover:bg-surface-2');
      li.draggable = true;
      li.append(el('span', '', p.icon), el('span', 'flex-1 truncate', p.title));
      if (onBoard.has(p.id)) li.append(el('span', 'text-[10px] text-faint', 'no mapa'));
      li.title = p.category;
      li.addEventListener('dragstart', e => { e.dataTransfer.setData('text/page-id', String(p.id)); e.dataTransfer.effectAllowed = 'copy'; });
      li.addEventListener('click', () => createCard({ kind: 'article', article_id: p.id, ...screenCenter() }).then(renderPageList));
      ul.append(li);
    }
  }
  $('page-search').addEventListener('input', renderPageList);

  // soltar páginas e arquivos no canvas
  viewport.addEventListener('dragover', e => { e.preventDefault(); e.dataTransfer.dropEffect = 'copy'; });
  viewport.addEventListener('drop', e => {
    e.preventDefault();
    const p = toWorld(e.clientX, e.clientY);
    const pid = e.dataTransfer.getData('text/page-id');
    if (pid) createCard({ kind: 'article', article_id: Number(pid), x: Math.round(p.x - 130), y: Math.round(p.y - 40) }).then(renderPageList);
    else if (e.dataTransfer.files.length) uploadFiles(e.dataTransfer.files, { x: p.x - 150, y: p.y - 80 });
  });
  document.addEventListener('paste', e => {
    if (editing || e.target.closest('input, textarea')) return;
    if (e.clipboardData.files.length) { e.preventDefault(); uploadFiles(e.clipboardData.files); }
    else {
      const text = e.clipboardData.getData('text/plain').trim();
      if (text) createCard({ kind: 'note', body: text.slice(0, 20000), ...screenCenter() });
    }
  });

  // ------------------------------------------------------------------ ponteiro
  let target = null;
  viewport.addEventListener('pointerdown', e => {
    if (e.button !== 0 || editing) return;
    if (e.target.closest('input, textarea, a, button, #sel-bar')) return;
    const node = e.target.closest('.node');
    const edge = e.target.closest('.edge');
    if (node && e.target.classList.contains('handle')) {
      const c = cards.get(Number(node.dataset.id)); const b = box(c);
      action = { type: 'connect', from: c };
      tempLine.setAttribute('x1', b.x + b.w / 2); tempLine.setAttribute('y1', b.y + b.h / 2);
      tempLine.setAttribute('x2', b.x + b.w / 2); tempLine.setAttribute('y2', b.y + b.h / 2);
      tempLine.style.display = '';
    } else if (node && e.target.classList.contains('grip')) {
      const c = cards.get(Number(node.dataset.id));
      action = { type: 'resize', card: c, sx: e.clientX, w0: c.w };
    } else if (node) {
      const c = cards.get(Number(node.dataset.id));
      select({ type: 'card', id: c.id });
      node.parentElement.append(node);       // traz para frente
      const p = toWorld(e.clientX, e.clientY);
      action = { type: 'move', card: c, dx: p.x - c.x, dy: p.y - c.y, moved: false };
    } else if (edge) {
      select({ type: 'link', id: Number(edge.dataset.id) });
      return;
    } else {
      select(null);
      action = { type: 'pan', sx: e.clientX, sy: e.clientY, vx: view.x, vy: view.y };
      viewport.classList.add('panning');
    }

  });
  window.addEventListener('pointermove', e => {
    if (!action) return;
    if (action.type === 'pan') {
      view.x = action.vx + e.clientX - action.sx; view.y = action.vy + e.clientY - action.sy; applyView();
    } else if (action.type === 'move') {
      const p = toWorld(e.clientX, e.clientY), c = action.card;
      c.x = Math.round(p.x - action.dx); c.y = Math.round(p.y - action.dy); action.moved = true;
      const n = els.get(c.id); n.style.left = c.x + 'px'; n.style.top = c.y + 'px';
      renderEdges();
    } else if (action.type === 'resize') {
      const c = action.card;
      c.w = Math.round(Math.min(900, Math.max(140, action.w0 + (e.clientX - action.sx) / view.z)));
      els.get(c.id).style.width = c.w + 'px'; renderEdges();
    } else if (action.type === 'connect') {
      const p = toWorld(e.clientX, e.clientY);
      tempLine.setAttribute('x2', p.x); tempLine.setAttribute('y2', p.y);
      const under = document.elementFromPoint(e.clientX, e.clientY)?.closest('.node');
      const t = under && Number(under.dataset.id) !== action.from.id ? under : null;
      if (t !== target) { target?.classList.remove('target'); t?.classList.add('target'); target = t; }
    }
  });
  const endAction = async () => {
    if (!action) return;
    const a = action; action = null;
    viewport.classList.remove('panning');
    if (a.type === 'move' && a.moved) patchCard(a.card, { x: a.card.x, y: a.card.y });
    if (a.type === 'resize' && a.card.w !== a.w0) patchCard(a.card, { w: a.card.w });
    if (a.type === 'connect') {
      tempLine.style.display = 'none';
      if (target) {
        const to = Number(target.dataset.id); target.classList.remove('target'); target = null;
        touched();
        const l = await api('POST', `${API}/links`, { from_card: a.from.id, to_card: to });
        if (!links.some(x => x.id === l.id)) links.push(l);
        select({ type: 'link', id: l.id });
        editLabel(l);
      }
    }
  };
  window.addEventListener('pointerup', endAction);
  window.addEventListener('pointercancel', endAction);

  viewport.addEventListener('dblclick', e => {
    if (editing || e.target.closest('input, textarea, a, button, #sel-bar')) return;
    const node = e.target.closest('.node'), edge = e.target.closest('.edge');
    if (node) {
      const c = cards.get(Number(node.dataset.id));
      if (c.kind === 'article' && c.article) location.href = c.article.url;
      else editCard(c);
    } else if (edge) {
      editLabel(links.find(l => l.id === Number(edge.dataset.id)));
    } else {
      const p = toWorld(e.clientX, e.clientY);
      createCard({ kind: 'note', x: Math.round(p.x - 120), y: Math.round(p.y - 30) }).then(editCard);
    }
  });
  viewport.addEventListener('wheel', e => {
    e.preventDefault();
    const f = Math.exp(-e.deltaY * (e.ctrlKey ? 0.01 : 0.0015));
    zoomAt(f, e.clientX, e.clientY);
  }, { passive: false });
  document.addEventListener('keydown', e => {
    if (editing || e.target.closest('input, textarea, select')) return;
    if ((e.key === 'Delete' || e.key === 'Backspace') && selection) { e.preventDefault(); removeSelection(); }
    if (e.key === 'Escape') select(null);
  });

  // ------------------------------------------------------------------ sincronização com colaboradores
  async function sync() {
    if (document.hidden || action || editing || Date.now() - lastLocalChange < 3000) return;
    try {
      const res = await fetch(`${API}/state`, { headers: { Accept: 'application/json' } });
      if (!res.ok) return;
      const s = await res.json();
      if (action || editing || Date.now() - lastLocalChange < 3000) return;
      const now = JSON.stringify(s), mine = JSON.stringify({ cards: [...cards.values()], links });
      if (now !== mine) {
        cards = new Map(s.cards.map(c => [c.id, c])); links = s.links;
        if (selection && !(selection.type === 'card' ? cards.has(selection.id) : links.some(l => l.id === selection.id))) selection = null;
        renderAll(); renderPageList();
        $('sync').textContent = 'atualizado'; setTimeout(() => { $('sync').textContent = ''; }, 1500);
      }
    } catch { /* offline: tenta de novo */ }
  }
  setInterval(sync, 5000);
  window.addEventListener('resize', renderEdges);

  applyView(); renderAll(); renderPageList();
  if (!localStorage.getItem(viewKey) && cards.size) fit();
})();
