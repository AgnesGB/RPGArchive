// Editor de páginas em blocos (estilo Notion).
//  • "/" ou "+" insere blocos; ⋮⋮ arrasta (para cima/baixo ou para os lados, criando colunas) e abre opções.
//  • Texto rico com barra flutuante; [[ cria link para página; atalhos markdown (# , - , 1. , [] , > , ---).
//  • Imagens/vídeos redimensionáveis, players do YouTube/Spotify/SoundCloud/Vimeo/Deezer, áudio, arquivos,
//    divisores decorativos, subpáginas, tabelas, colunas e listas recolhíveis.
//  • Salva sozinho (com versão: se outra pessoa salvar antes, carrega a versão nova).
(() => {
  'use strict';
  const D = JSON.parse(document.getElementById('page-data').textContent);
  const root = document.getElementById('editor');
  const titleEl = document.getElementById('page-title');
  const stateEl = document.getElementById('save-state');
  const lockBtn = document.getElementById('lock-btn');
  let blocks = D.blocks || [];
  let version = D.version;
  let pages = D.pages || {};
  const READONLY = !!D.readonly;      // página revelada aos jogadores: só leitura, sem salvar
  let locked = READONLY || localStorage.getItem('page-locked') === '1';
  let selectedId = null;

  const RICH = new Set(['text', 'h1', 'h2', 'h3', 'bullet', 'number', 'todo', 'quote', 'callout', 'toggle']);
  const LISTS = new Set(['bullet', 'number', 'todo']);
  const COLORS = [['gray', 'Cinza'], ['brown', 'Marrom'], ['orange', 'Laranja'], ['yellow', 'Amarelo'], ['green', 'Verde'],
    ['blue', 'Azul'], ['purple', 'Roxo'], ['pink', 'Rosa'], ['red', 'Vermelho']];
  const ICONS = ['candle', 'scroll', 'book', 'tome', 'quill', 'parchment', 'redbook', 'fire', 'sword', 'shield', 'bow', 'staff',
    'potion', 'orb', 'gem', 'ruby', 'ring', 'key', 'chest', 'coin', 'bag', 'skull', 'heart', 'star', 'moon', 'sun', 'holy', 'map',
    'world', 'castle', 'tower', 'mountain', 'tree', 'rose', 'clover', 'mushroom', 'hood', 'wizard', 'helmet', 'beast', 'pirate',
    'flag', 'trophy', 'scales', 'anvil', 'chain', 'fish', 'people', 'picture', 'web', 'home', 'brick'];

  // ------------------------------------------------------------------ utilidades
  const el = (tag, cls, text) => { const n = document.createElement(tag); if (cls) n.className = cls; if (text !== undefined) n.textContent = text; return n; };
  const uid = () => Math.random().toString(36).slice(2, 10);
  const esc = s => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const norm = s => (s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
  const csrf = () => document.querySelector('meta[name="csrf-token"]').content;
  const fileUrl = id => `/f/${id}`;
  function button(content, title, cls = '') {
    const b = el('button', cls); b.type = 'button';
    if (typeof content === 'string') b.textContent = content; else b.append(content);
    if (title) { b.title = title; b.setAttribute('aria-label', title); }
    return b;
  }

  function newBlock(type) {
    const b = { id: uid(), type };
    if (RICH.has(type)) b.html = '';
    if (type === 'todo') b.checked = false;
    if (type === 'callout') b.icon = 'ri:candle';
    if (type === 'toggle') { b.open = true; b.children = []; }
    if (type === 'divider') b.style = D.dividers[0]?.key || 'line';
    if (type === 'image') Object.assign(b, { src: '', width: 100, align: 'center', caption: '' });
    if (type === 'embed') Object.assign(b, { url: '', width: 100, caption: '' });
    if (type === 'audio' || type === 'file') Object.assign(b, { file_id: 0, name: '', caption: '' });
    if (type === 'video') Object.assign(b, { file_id: 0, name: '', caption: '', width: 100 });
    if (type === 'table') Object.assign(b, { rows: [['', '', ''], ['', '', ''], ['', '', '']], header: true });
    if (type === 'code') b.text = '';
    if (type === 'markdown') Object.assign(b, { md: '', _html: '' });
    if (type === 'columns2' || type === 'columns3') {
      const n = type === 'columns2' ? 2 : 3;
      return { id: uid(), type: 'columns', cols: Array.from({ length: n }, () => ({ w: 100 / n, blocks: [newBlock('text')] })) };
    }
    return b;
  }
  function cloneBlock(b) {
    const c = JSON.parse(JSON.stringify(b));
    (function reid(x) { x.id = uid(); (x.children || []).forEach(reid); (x.cols || []).forEach(col => col.blocks.forEach(reid)); })(c);
    return c;
  }

  // ------------------------------------------------------------------ árvore de blocos
  function locate(id, list = blocks, owner = null, colIdx = -1) {
    for (let i = 0; i < list.length; i++) {
      const b = list[i];
      if (b.id === id) return { block: b, list, index: i, owner, colIdx };
      if (b.children) { const r = locate(id, b.children, b, -1); if (r) return r; }
      if (b.cols) for (let c = 0; c < b.cols.length; c++) { const r = locate(id, b.cols[c].blocks, b, c); if (r) return r; }
    }
    return null;
  }
  const isInside = (parent, id) => !!(parent.id !== id && locate(id, [parent]));
  function normalize(list = blocks) {
    for (let i = list.length - 1; i >= 0; i--) {
      const b = list[i];
      if (b.children) normalize(b.children);
      if (b.cols) {
        b.cols.forEach(c => normalize(c.blocks));
        b.cols = b.cols.filter(c => c.blocks.length);
        if (!b.cols.length) list.splice(i, 1);
        else if (b.cols.length === 1) list.splice(i, 1, ...b.cols[0].blocks);
        else { const t = b.cols.reduce((s, c) => s + c.w, 0); b.cols.forEach(c => { c.w = c.w * 100 / t; }); }
      }
    }
    if (list === blocks && !blocks.length) blocks.push(newBlock('text'));
  }
  function insertNear(refId, nb, where = 'after') {
    const r = refId && locate(refId);
    if (!r) { blocks.push(nb); return; }
    r.list.splice(r.index + (where === 'after' ? 1 : 0), 0, nb);
  }
  function removeBlock(id, keepHistory) { if (!keepHistory) snapshot(); const r = locate(id); if (r) r.list.splice(r.index, 1); normalize(); }

  // ------------------------------------------------------------------ cursor
  function caretOffset(node) {
    const sel = getSelection(); if (!sel.rangeCount) return 0;
    const range = sel.getRangeAt(0); if (!node.contains(range.endContainer)) return 0;
    const pre = range.cloneRange(); pre.selectNodeContents(node); pre.setEnd(range.endContainer, range.endOffset);
    return pre.toString().length;
  }
  function setCaret(node, off) {
    node.focus();
    const total = node.textContent.length;
    let left = off === 'end' ? total : Math.min(off, total);
    const range = document.createRange(), walker = document.createTreeWalker(node, NodeFilter.SHOW_TEXT);
    let t = walker.nextNode(), placed = false;
    while (t) { if (left <= t.length) { range.setStart(t, left); placed = true; break; } left -= t.length; t = walker.nextNode(); }
    if (!placed) { range.selectNodeContents(node); range.collapse(false); }
    range.collapse(true);
    const sel = getSelection(); sel.removeAllRanges(); sel.addRange(range);
  }
  function rangeFromOffsets(node, a, b) {
    const range = document.createRange(), walker = document.createTreeWalker(node, NodeFilter.SHOW_TEXT);
    let pos = 0, t = walker.nextNode(), startSet = false;
    while (t) {
      if (!startSet && a <= pos + t.length) { range.setStart(t, a - pos); startSet = true; }
      if (startSet && b <= pos + t.length) { range.setEnd(t, b - pos); return range; }
      pos += t.length; t = walker.nextNode();
    }
    return null;
  }
  const collapsed = () => { const s = getSelection(); return s.rangeCount && s.getRangeAt(0).collapsed; };
  function splitAtCaret(node) {
    const sel = getSelection(), range = sel.getRangeAt(0);
    range.deleteContents();
    const after = document.createRange(); after.setStart(range.endContainer, range.endOffset); after.setEnd(node, node.childNodes.length);
    const tmp = el('div'); tmp.append(after.extractContents());
    return cleanHtml(tmp.innerHTML);
  }
  const cleanHtml = h => (h === '<br>' || h === '<br/>' ? '' : h || '');
  const allRich = () => [...root.querySelectorAll('[data-rich]')].filter(r => r.dataset.key === 'html');
  function findRich(id, key = 'html', r, c) {
    return [...root.querySelectorAll('[data-rich]')].find(x => x.dataset.rich === id && x.dataset.key === key && (key !== 'cell' || (x.dataset.r == r && x.dataset.c == c)));
  }
  function focusBlock(id, where = 'end') {
    const r = findRich(id) || root.querySelector(`.blk[data-id="${id}"] [data-rich]`);
    if (r) setCaret(r, where === 'start' ? 0 : where); else select(id);
  }

  // ------------------------------------------------------------------ renderização
  function render() {
    const a = document.activeElement, keep = a?.dataset?.rich ? { id: a.dataset.rich, key: a.dataset.key, r: a.dataset.r, c: a.dataset.c, off: caretOffset(a) } : null;
    if (!blocks.length) blocks.push(newBlock('text'));
    root.classList.toggle('locked', locked);
    root.replaceChildren(renderList(blocks, 'root'));
    const below = el('div', 'add-below'); below.addEventListener('mousedown', clickBelow); root.append(below);
    titleEl.contentEditable = locked ? 'false' : 'plaintext-only';
    if (keep) { const r = findRich(keep.id, keep.key, keep.r, keep.c); if (r) setCaret(r, keep.off); }
    if (selectedId) root.querySelector(`.blk[data-id="${selectedId}"]`)?.classList.add('selected');
    if (READONLY) root.querySelectorAll('a[data-page]').forEach(x => { if (!pages[x.dataset.page]) x.classList.add('unrevealed'); });
  }
  function renderList(list, kind) {
    const wrap = el('div', 'list');
    if (!list.length && kind !== 'root') {
      const slot = el('div', 'empty-slot', locked ? '' : 'Vazio · clique para escrever ou arraste blocos para cá');
      slot._list = list;
      slot.addEventListener('mousedown', e => { if (locked) return; e.preventDefault(); const b = newBlock('text'); list.push(b); changed(); render(); focusBlock(b.id, 'start'); });
      wrap.append(slot);
    }
    let n = 0;
    for (const b of list) { n = b.type === 'number' ? n + 1 : 0; wrap.append(renderBlock(b, n)); }
    return wrap;
  }
  function rich(b, key = 'html', ph = '', cls = '') {
    const r = el('div', 'rich ' + cls);
    r.contentEditable = locked ? 'false' : 'true';
    r.dataset.rich = b.id; r.dataset.key = key;
    if (ph) r.dataset.ph = ph;
    if (key !== 'cell') r.innerHTML = b[key] || '';
    r._block = b;
    return r;
  }
  function renderBlock(b, num) {
    const w = el('div', 'blk'); w.dataset.id = b.id; w.dataset.type = b.type;
    if (b.color) w.classList.add(b.color.endsWith('_bg') ? 'bg-' + b.color.slice(0, -3) : 'c-' + b.color);
    const g = el('div', 'gutter');
    const plus = button(ui('plus', 'size-4'), 'Adicionar bloco (Alt: acima)');
    plus.addEventListener('click', e => openInsertMenu(plus.getBoundingClientRect(), { refId: b.id, where: e.altKey ? 'before' : 'after' }));
    const grip = button('⋮⋮', 'Arraste para mover · clique para opções', 'grip');
    grip.addEventListener('pointerdown', e => startDrag(e, b, w, grip));
    g.append(plus, grip); w.append(g);
    const body = el('div', 'body'); w.append(body);
    const ph = { text: "Escreva ou digite '/' para comandos…", h1: 'Título 1', h2: 'Título 2', h3: 'Título 3', quote: 'Citação',
      bullet: 'Item', number: 'Item', todo: 'Tarefa', callout: 'Escreva algo em destaque…', toggle: 'Lista recolhível' }[b.type];

    switch (b.type) {
      case 'text': case 'h1': case 'h2': case 'h3': case 'quote':
        body.append(rich(b, 'html', ph)); break;
      case 'bullet': case 'number': case 'todo': {
        const row = el('div', 'row'), mk = el('div', 'marker');
        if (b.type === 'number') mk.textContent = num + '.';
        if (b.type === 'todo') {
          const cb = el('input'); cb.type = 'checkbox'; cb.checked = !!b.checked; cb.disabled = READONLY;
          cb.addEventListener('change', () => { b.checked = cb.checked; w.classList.toggle('done', cb.checked); changed(); });
          mk.append(cb); w.classList.toggle('done', !!b.checked);
        }
        row.append(mk, rich(b, 'html', ph)); body.append(row); break;
      }
      case 'callout': {
        const c = el('div', 'callout'), ic = button(glyph(b.icon || 'ri:candle', 20), 'Trocar ícone', 'c-icon');
        ic.addEventListener('click', () => !locked && openIconPicker(ic.getBoundingClientRect(), v => { b.icon = v; changed(); render(); }));
        c.append(ic, el('div', 'c-bar'), rich(b, 'html', ph)); body.append(c); break;
      }
      case 'toggle': {
        w.classList.toggle('open', !!b.open);
        const head = el('div', 'toggle-head'), t = button(ui('chevron', 'size-3.5'), b.open ? 'Recolher' : 'Expandir', 'toggle-btn');
        t.addEventListener('click', () => { b.open = !b.open; changed(); render(); });
        head.append(t, rich(b, 'html', ph)); body.append(head);
        if (b.open) { const kids = el('div', 'toggle-kids'); kids.append(renderList(b.children, 'toggle')); body.append(kids); }
        break;
      }
      case 'divider': body.append(renderDivider(b)); break;
      case 'code': {
        const pre = el('pre', 'code'); pre.contentEditable = locked ? 'false' : 'plaintext-only'; pre.spellcheck = false;
        pre.textContent = b.text || ''; pre.dataset.ph = 'Código…';
        pre.addEventListener('input', () => { b.text = pre.textContent; changed(); });
        pre.addEventListener('keydown', e => { if (e.key === 'Tab') { e.preventDefault(); document.execCommand('insertText', false, '  '); } });
        body.append(pre); break;
      }
      case 'image': body.append(renderImage(b)); break;
      case 'embed': body.append(renderEmbed(b)); break;
      case 'audio': body.append(renderAudio(b)); break;
      case 'video': body.append(renderVideo(b)); break;
      case 'file': body.append(renderFile(b)); break;
      case 'page': body.append(renderPage(b)); break;
      case 'columns': body.append(renderColumns(b)); break;
      case 'table': body.append(renderTable(b)); break;
      case 'markdown': body.append(renderMarkdown(b)); break;
      default: body.append(el('p', 'text-faint', `Bloco desconhecido (${b.type})`));
    }
    body.addEventListener('mousedown', e => {
      if (locked || e.target.closest('[data-rich], input, textarea, button, a, audio, video, iframe, .code, .resize, .col-resize, .empty-slot')) return;
      if (!RICH.has(b.type) && b.type !== 'columns') { e.preventDefault(); select(b.id); }
    });
    return w;
  }

  function renderDivider(b) {
    const d = el('div', 'divider'), s = D.dividers.find(x => x.key === b.style);
    if (!s) d.append(el('hr'));
    else if (s.mask) { const m = el('div', 'dv'); m.style.setProperty('--dv', `url("${s.url}")`); d.append(m); }
    else { const i = el('img'); i.src = s.url; i.alt = ''; d.append(i); }
    d.title = locked ? '' : 'Clique para trocar o estilo';
    d.addEventListener('click', () => !locked && openDividerMenu(d.getBoundingClientRect(), b));
    return d;
  }

  // ---------- mídia
  function mediaBox(b, inner) {
    const m = el('div', 'media al-' + (b.align || 'center'));
    m.style.width = (b.width || 100) + '%';
    m.append(inner);
    if (!locked) for (const side of ['l', 'r']) {
      const h = el('div', 'resize ' + side); h.title = 'Arraste para redimensionar';
      h.addEventListener('pointerdown', e => startResize(e, b, m, side)); m.append(h);
    }
    return m;
  }
  function mediaTools(b, extra = []) {
    const t = el('div', 'media-tools');
    for (const [al, label] of [['left', '⇤'], ['center', '↔'], ['right', '⇥']]) {
      const x = button(label, { left: 'Alinhar à esquerda', center: 'Centralizar', right: 'Alinhar à direita' }[al]);
      x.addEventListener('click', () => { b.align = al; changed(); render(); }); t.append(x);
    }
    extra.forEach(x => t.append(x));
    return t;
  }
  function startResize(e, b, m, side) {
    e.preventDefault(); e.stopPropagation();
    const parentW = m.parentElement.getBoundingClientRect().width, startW = m.getBoundingClientRect().width, sx = e.clientX;
    const center = (b.align || 'center') === 'center';
    const move = ev => {
      let dx = ev.clientX - sx; if (side === 'l') dx = -dx;
      b.width = Math.max(10, Math.min(100, Math.round((startW + dx * (center ? 2 : 1)) / parentW * 100)));
      m.style.width = b.width + '%';
    };
    const up = () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up); changed(); };
    window.addEventListener('pointermove', move); window.addEventListener('pointerup', up);
  }
  function uploadPlaceholder(b, kind, label, accept, withLink) {
    const p = el('div', 'placeholder');
    if (locked) { p.textContent = label + ' (vazio)'; return p; }
    const up = button(iconLabel(ui('upload', 'size-4'), 'Enviar ' + label.toLowerCase()), '', 'btn btn-outline btn-sm');
    const fi = el('input'); fi.type = 'file'; fi.accept = accept; fi.hidden = true;
    up.addEventListener('click', () => fi.click());
    fi.addEventListener('change', () => fi.files[0] && uploadInto(b, fi.files[0], kind));
    p.append(ri({ image: 'picture', audio: 'candle', video: 'picture', file: 'parchment' }[kind] || 'parchment'), up, fi);
    if (withLink) {
      const inp = el('input', 'input py-1.5 text-sm'); inp.placeholder = 'ou cole o link de uma imagem (https://…)';
      inp.addEventListener('keydown', e => { if (e.key === 'Enter' && /^https:\/\//.test(inp.value.trim())) { b.src = inp.value.trim(); changed(); render(); } });
      p.append(inp);
    }
    p.addEventListener('dragover', e => { e.preventDefault(); e.stopPropagation(); });
    p.addEventListener('drop', e => { e.preventDefault(); e.stopPropagation(); if (e.dataTransfer.files[0]) uploadInto(b, e.dataTransfer.files[0], kind); });
    return p;
  }
  async function uploadFile(file, kind) {
    const fd = new FormData(); fd.append('files', file);
    stateEl.textContent = 'enviando…';
    try { const r = await api('POST', D.api.upload + (kind === 'image' ? '?images=1' : ''), fd); return r.files[0]; }
    finally { stateEl.textContent = ''; }
  }
  async function uploadInto(b, file, kind) {
    const f = await uploadFile(file, kind);
    if (kind === 'image') b.src = f.url; else { b.file_id = f.id; b.name = f.name; }
    changed(); render();
  }
  function renderImage(b) {
    if (!b.src) return uploadPlaceholder(b, 'image', 'Imagem', 'image/*', true);
    const img = el('img'); img.src = b.src; img.alt = ''; img.loading = 'lazy'; img.draggable = false;
    if (b.src.startsWith('https://')) img.referrerPolicy = 'no-referrer';
    const swap = button('⟳', 'Trocar imagem'); const fi = el('input'); fi.type = 'file'; fi.accept = 'image/*'; fi.hidden = true;
    swap.addEventListener('click', () => fi.click()); fi.addEventListener('change', () => fi.files[0] && uploadInto(b, fi.files[0], 'image'));
    const wrap = el('div'); const m = mediaBox(b, img); m.append(mediaTools(b, [swap]), fi);
    wrap.append(m, rich(b, 'caption', 'Legenda…', 'caption'));
    return wrap;
  }
  function parseEmbed(u) {
    let url; try { url = new URL(u); } catch { return null; }
    const h = url.hostname.replace(/^(www|m|music)\./, '');
    if (h === 'youtube.com' || h === 'youtube-nocookie.com') {
      let id = url.searchParams.get('v'); const list = url.searchParams.get('list');
      if (!id) id = url.pathname.match(/^\/(?:embed|shorts|live|v)\/([\w-]{6,})/)?.[1];
      if (id) return { kind: 'YouTube', src: `https://www.youtube-nocookie.com/embed/${id}${list ? '?list=' + encodeURIComponent(list) : ''}`, ratio: '16 / 9' };
      if (list) return { kind: 'YouTube', src: `https://www.youtube-nocookie.com/embed/videoseries?list=${encodeURIComponent(list)}`, ratio: '16 / 9' };
    }
    if (h === 'youtu.be') { const id = url.pathname.slice(1).split('/')[0]; if (id) return { kind: 'YouTube', src: `https://www.youtube-nocookie.com/embed/${id}`, ratio: '16 / 9' }; }
    if (h === 'open.spotify.com') {
      const m = url.pathname.match(/^\/(?:intl-[a-z-]+\/)?(track|album|playlist|episode|show|artist)\/([A-Za-z0-9]+)/);
      if (m) return { kind: 'Spotify', src: `https://open.spotify.com/embed/${m[1]}/${m[2]}?utm_source=generator&theme=0`, height: ['track', 'episode'].includes(m[1]) ? 152 : 380 };
    }
    if (h === 'soundcloud.com') return { kind: 'SoundCloud', src: `https://w.soundcloud.com/player/?url=${encodeURIComponent(u)}&color=%23ff5500&visual=true`, height: 300 };
    if (h === 'vimeo.com') { const m = url.pathname.match(/\/(\d+)/); if (m) return { kind: 'Vimeo', src: `https://player.vimeo.com/video/${m[1]}`, ratio: '16 / 9' }; }
    if (h === 'deezer.com') {
      const m = url.pathname.match(/\/(track|album|playlist)\/(\d+)/);
      if (m) return { kind: 'Deezer', src: `https://widget.deezer.com/widget/dark/${m[1]}/${m[2]}`, height: m[1] === 'track' ? 160 : 360 };
    }
    if (h === 'apple.com' && url.pathname.match(/^\/[a-z]{2}\/(album|playlist|song)\//)) return { kind: 'Apple Music', src: 'https://embed.music.apple.com' + url.pathname + url.search, height: 450 };
    if (h === 'twitch.tv') { const ch = url.pathname.split('/')[1]; if (ch) return { kind: 'Twitch', src: `https://player.twitch.tv/?channel=${encodeURIComponent(ch)}&parent=${location.hostname}`, ratio: '16 / 9' }; }
    return { kind: 'link' };
  }
  function renderEmbed(b) {
    if (!b.url) {
      const p = el('div', 'placeholder');
      if (locked) { p.textContent = 'Incorporação (vazia)'; return p; }
      const inp = el('input', 'input py-1.5 text-sm'); inp.placeholder = 'Cole o link do YouTube, Spotify, SoundCloud, Vimeo, Deezer…';
      const ok = button('Incorporar', '', 'btn btn-primary btn-sm');
      const go = () => { const v = inp.value.trim(); if (/^https?:\/\//.test(v)) { b.url = v; changed(); render(); } else toast('Cole um link que comece com https://', true); };
      ok.addEventListener('click', go); inp.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); go(); } });
      p.append(ui('link', 'size-4'), inp, ok);
      setTimeout(() => inp.focus(), 0);
      return p;
    }
    const e = parseEmbed(b.url) || { kind: 'link' };
    const wrap = el('div');
    if (e.kind === 'link') {
      const a = el('a', 'link-card'); a.href = b.url; a.target = '_blank'; a.rel = 'noopener noreferrer';
      let host = b.url; try { host = new URL(b.url).hostname; } catch { /* */ }
      a.append(el('span', 'font-medium text-ink', host), el('span', 'truncate text-xs text-faint', b.url));
      wrap.append(a);
    } else {
      const f = el('iframe'); f.src = e.src; f.loading = 'lazy'; f.title = e.kind;
      f.allow = 'autoplay; clipboard-write; encrypted-media; fullscreen; picture-in-picture';
      f.setAttribute('allowfullscreen', ''); f.referrerPolicy = 'strict-origin-when-cross-origin';
      f.setAttribute('sandbox', 'allow-scripts allow-same-origin allow-popups allow-presentation allow-forms');
      if (e.ratio) f.style.aspectRatio = e.ratio; else f.style.height = e.height + 'px';
      const edit = button('🔗', 'Trocar link');
      edit.addEventListener('click', () => { const v = prompt('Link', b.url); if (v && /^https?:\/\//.test(v.trim())) { b.url = v.trim(); changed(); render(); } });
      const m = mediaBox(b, f); m.append(mediaTools(b, [edit])); wrap.append(m);
    }
    wrap.append(rich(b, 'caption', 'Legenda…', 'caption'));
    return wrap;
  }
  function renderAudio(b) {
    if (!b.file_id) return uploadPlaceholder(b, 'audio', 'Áudio', 'audio/*', false);
    const box = el('div', 'audio-box');
    const top = el('div', 'flex items-center gap-2 text-sm text-ink'); top.append(ri('candle'), el('span', 'truncate', b.name || 'Áudio'));
    const a = el('audio'); a.controls = true; a.preload = 'metadata'; a.src = fileUrl(b.file_id);
    box.append(top, a);
    const wrap = el('div'); wrap.append(box, rich(b, 'caption', 'Legenda…', 'caption'));
    return wrap;
  }
  function renderVideo(b) {
    if (!b.file_id) return uploadPlaceholder(b, 'video', 'Vídeo', 'video/*', false);
    const v = el('video'); v.controls = true; v.preload = 'metadata'; v.src = fileUrl(b.file_id);
    const wrap = el('div'); const m = mediaBox(b, v); m.append(mediaTools(b)); wrap.append(m, rich(b, 'caption', 'Legenda…', 'caption'));
    return wrap;
  }
  function renderFile(b) {
    if (!b.file_id) return uploadPlaceholder(b, 'file', 'Arquivo', '', false);
    const a = el('a', 'file-card'); a.href = fileUrl(b.file_id); a.target = '_blank'; a.rel = 'noopener';
    a.append(ui('clip', 'size-5'), el('span', 'truncate font-medium text-ink', b.name || 'Arquivo'), el('span', 'ml-auto text-xs text-faint', 'abrir / baixar'));
    return a;
  }
  function renderPage(b) {
    const p = pages[b.page_id], a = el('a', 'pagelink');
    if (p) { a.href = p.u; a.append(glyph(p.i || 'ri:scroll', 18), el('span', 't', p.t)); }
    else { a.classList.add('gone'); a.textContent = READONLY ? 'Página ainda não revelada' : 'Página apagada'; }
    return a;
  }

  // ---------- colunas
  function renderColumns(b) {
    const row = el('div', 'cols');
    b.cols.forEach((c, i) => {
      const col = el('div', 'col'); col.style.flex = `${c.w} 1 0`;
      col.append(renderList(c.blocks, 'col'));
      if (i < b.cols.length - 1 && !locked) {
        const rz = el('div', 'col-resize'); rz.title = 'Arraste para mudar a largura';
        rz.addEventListener('pointerdown', e => startColResize(e, b, i, row, rz)); col.append(rz);
      }
      row.append(col);
    });
    return row;
  }
  function startColResize(e, b, i, row, rz) {
    e.preventDefault(); e.stopPropagation();
    const W = row.getBoundingClientRect().width, sx = e.clientX, a0 = b.cols[i].w, pair = b.cols[i].w + b.cols[i + 1].w;
    rz.classList.add('active');
    const cols = row.children;
    const move = ev => {
      const a = Math.max(10, Math.min(pair - 10, a0 + (ev.clientX - sx) / W * 100));
      b.cols[i].w = a; b.cols[i + 1].w = pair - a;
      cols[i].style.flex = `${a} 1 0`; cols[i + 1].style.flex = `${pair - a} 1 0`;
    };
    const up = () => { rz.classList.remove('active'); window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up); changed(); };
    window.addEventListener('pointermove', move); window.addEventListener('pointerup', up);
  }

  // ---------- tabela
  function renderTable(b) {
    const wrap = el('div', 'tbl-wrap'), t = el('table', 'tbl' + (b.header ? ' header' : ''));
    b.rows.forEach((row, ri) => {
      const tr = el('tr');
      row.forEach((cell, ci) => {
        const td = el('td'), r = rich(b, 'cell');
        r.dataset.r = ri; r.dataset.c = ci; r.innerHTML = cell; td.append(r); tr.append(td);
      });
      t.append(tr);
    });
    wrap.append(t);
    const tools = el('div', 'tbl-tools');
    const act = (label, fn) => { const x = button(label); x.addEventListener('click', () => { fn(); changed(); render(); }); tools.append(x); };
    act('+ linha', () => b.rows.push(b.rows[0].map(() => '')));
    act('+ coluna', () => b.rows.forEach(r => r.push('')));
    act('− linha', () => b.rows.length > 1 && b.rows.pop());
    act('− coluna', () => b.rows[0].length > 1 && b.rows.forEach(r => r.pop()));
    act(b.header ? 'sem cabeçalho' : 'com cabeçalho', () => { b.header = !b.header; });
    const box = el('div'); box.append(wrap, tools);
    return box;
  }

  // ---------- markdown (páginas antigas)
  function renderMarkdown(b) {
    const box = el('div', 'md-box');
    const view = el('div', 'lore'); view.innerHTML = b._html || '<p class="text-faint">Markdown vazio.</p>';
    box.append(view);
    if (!locked) {
      const hint = el('div', 'md-hint flex flex-wrap items-center gap-2');
      hint.append('Bloco Markdown (conteúdo antigo) · clique para editar ·');
      const conv = button('converter em blocos', 'Transforma o markdown em blocos editáveis', 'underline hover:text-ink');
      conv.addEventListener('click', e => { e.stopPropagation(); convertMarkdown(b); });
      hint.append(conv); box.append(hint);
      view.addEventListener('click', e => {
        if (e.target.closest('a')) return;
        const ta = el('textarea'); ta.value = b.md || ''; box.replaceChildren(ta); ta.focus();
        ta.addEventListener('input', () => { b.md = ta.value; changed(); });
        ta.addEventListener('blur', async () => {
          try { const r = await api('POST', D.api.preview, { content: b.md }); b._html = r.html; } catch { /* */ }
          render();
        });
      });
    }
    return box;
  }
  function inlineMd(s) {
    let h = esc(s);
    h = h.replace(/\[\[([^\]|]+)(?:\|([^\]]+))?\]\]/g, (m, name, label) => {
      const id = Object.keys(pages).find(k => norm(pages[k].t) === norm(name.trim()));
      return id ? `<a href="${pages[id].u}" data-page="${id}">${label || name}</a>` : m;
    });
    h = h.replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, '<a href="$2">$1</a>');
    h = h.replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>').replace(/(^|[^*])\*([^*]+)\*/g, '$1<i>$2</i>')
      .replace(/~~([^~]+)~~/g, '<s>$1</s>').replace(/`([^`]+)`/g, '<code>$1</code>');
    return h.replace(/\n/g, '<br>');
  }
  function mdToBlocks(md) {
    const out = [], lines = (md || '').replace(/\r/g, '').split('\n');
    let para = [];
    const flush = () => { if (para.length) { out.push({ ...newBlock('text'), html: inlineMd(para.join('\n')) }); para = []; } };
    for (let i = 0; i < lines.length; i++) {
      const l = lines[i], t = l.trim();
      let m;
      if (!t) { flush(); continue; }
      if (t.startsWith('```')) {
        flush(); const code = [];
        while (++i < lines.length && !lines[i].trim().startsWith('```')) code.push(lines[i]);
        out.push({ ...newBlock('code'), text: code.join('\n') }); continue;
      }
      if (t.startsWith('|')) {
        flush(); const rows = [];
        for (; i < lines.length && lines[i].trim().startsWith('|'); i++) {
          const row = lines[i].trim().replace(/^\||\|$/g, '').split(/(?<!\\)\|/).map(c => c.trim().replace(/\\\|/g, '|'));
          if (!row.every(c => /^:?-{2,}:?$/.test(c))) rows.push(row.map(inlineMd));
        }
        i--; const w = Math.max(...rows.map(r => r.length));
        out.push({ ...newBlock('table'), rows: rows.map(r => r.concat(Array(w - r.length).fill(''))) }); continue;
      }
      if ((m = t.match(/^(#{1,4})\s+(.*)$/))) { flush(); out.push({ ...newBlock(['h1', 'h1', 'h2', 'h3', 'h3'][m[1].length]), html: inlineMd(m[2]) }); continue; }
      if (/^(-{3,}|\*{3,})$/.test(t)) { flush(); out.push(newBlock('divider')); continue; }
      if ((m = t.match(/^[-*]\s+\[( |x)\]\s+(.*)$/i))) { flush(); out.push({ ...newBlock('todo'), checked: m[1].toLowerCase() === 'x', html: inlineMd(m[2]) }); continue; }
      if ((m = t.match(/^[-*]\s+(.*)$/))) { flush(); out.push({ ...newBlock('bullet'), html: inlineMd(m[1]) }); continue; }
      if ((m = t.match(/^\d+[.)]\s+(.*)$/))) { flush(); out.push({ ...newBlock('number'), html: inlineMd(m[1]) }); continue; }
      if ((m = t.match(/^>\s?(.*)$/))) { flush(); out.push({ ...newBlock('quote'), html: inlineMd(m[1]) }); continue; }
      if ((m = t.match(/^!\[[^\]]*\]\(((?:\/f\/\d+)|(?:https:\/\/[^)\s]+))\)$/))) { flush(); out.push({ ...newBlock('image'), src: m[1] }); continue; }
      para.push(l);
    }
    flush();
    return out;
  }
  function convertMarkdown(b) {
    const r = locate(b.id); if (!r) return;
    const nb = mdToBlocks(b.md);
    snapshot();
    r.list.splice(r.index, 1, ...(nb.length ? nb : [newBlock('text')]));
    changed(); render(); toast('Markdown convertido em blocos.');
  }

  // ------------------------------------------------------------------ menus flutuantes
  let pop = null, menu = null;
  function closePop() { pop?.remove(); pop = null; menu = null; }
  function openPop(rect, content, opts = {}) {
    closePop();
    pop = el('div', 'ed-pop ' + (opts.cls || '')); pop.append(content); document.body.append(pop);
    pop._rect = rect; placePop();
    return pop;
  }
  // posiciona abaixo do ponto; se não couber, acima (chamado de novo quando o conteúdo muda)
  function placePop() {
    if (!pop) return;
    const rect = pop._rect, pw = pop.offsetWidth, ph = pop.offsetHeight;
    let top = rect.bottom + 6;
    if (top + ph > innerHeight - 8) top = rect.top - ph - 6 >= 8 ? rect.top - ph - 6 : Math.max(8, innerHeight - ph - 8);
    pop.style.top = top + 'px'; pop.style.left = Math.max(8, Math.min(rect.left, innerWidth - pw - 8)) + 'px';
  }
  document.addEventListener('mousedown', e => { if (pop && !pop.contains(e.target)) closePop(); }, true);

  const MENU = [
    ['Básico'],
    ['text', 'Texto', 'Parágrafo simples', 'Aa', 'paragrafo texto'],
    ['h1', 'Título 1', 'Título grande', 'H1', 'heading titulo'],
    ['h2', 'Título 2', 'Título médio', 'H2', 'heading subtitulo'],
    ['h3', 'Título 3', 'Título pequeno', 'H3', 'heading'],
    ['bullet', 'Lista com marcadores', 'Lista simples', '•', 'lista bullet'],
    ['number', 'Lista numerada', '1, 2, 3…', '1.', 'lista numero'],
    ['todo', 'Lista de tarefas', 'Com caixinhas de marcar', '☐', 'tarefa checklist todo'],
    ['toggle', 'Lista recolhível', 'Esconde o conteúdo dentro', '▸', 'toggle recolher'],
    ['quote', 'Citação', 'Destaca uma fala', '❝', 'citacao quote'],
    ['callout', 'Destaque', 'Caixa com ícone (callout)', () => ri('candle'), 'callout caixa ficha propriedade'],
    ['divider', 'Divisor', 'Separador decorativo', '—', 'divisor linha separador hr'],
    ['table', 'Tabela', 'Linhas e colunas', '▦', 'tabela grade'],
    ['code', 'Código', 'Texto monoespaçado', '</>', 'codigo code'],
    ['Mídia'],
    ['image', 'Imagem', 'Enviar ou colar link', () => ri('picture'), 'imagem foto figura'],
    ['embed', 'Vídeo ou música (link)', 'YouTube, Spotify, SoundCloud, Vimeo…', '▶', 'youtube spotify soundcloud vimeo deezer embed player musica video'],
    ['audio', 'Áudio', 'Arquivo MP3, OGG, WAV…', '♪', 'audio som musica mp3'],
    ['video', 'Vídeo (arquivo)', 'MP4 ou WEBM', '🎞', 'video mp4'],
    ['file', 'Arquivo', 'PDF, livro, documento', () => ui('clip', 'size-4'), 'arquivo pdf anexo'],
    ['Páginas'],
    ['page', 'Subpágina', 'Cria uma página dentro desta', () => ri('scroll'), 'pagina subpagina'],
    ['pagelink', 'Link para página', 'Aponta para uma página existente', () => ui('link', 'size-4'), 'link pagina mencionar'],
    ['Layout'],
    ['columns2', '2 colunas', 'Lado a lado', '▥', 'colunas layout'],
    ['columns3', '3 colunas', 'Três lado a lado', '▦', 'colunas layout'],
    ['Avançado'],
    ['markdown', 'Markdown', 'Escrever em markdown', 'M↓', 'markdown'],
  ];
  function menuItems(q) {
    q = norm(q).trim();
    const out = []; let sec = null;
    for (const it of MENU) {
      if (it.length === 1) { sec = it[0]; continue; }
      const [t, label, desc, ic, kw] = it;
      if (q && !norm(label + ' ' + desc + ' ' + kw).includes(q)) continue;
      const nl = norm(label);
      out.push({ t, label, desc, ic, sec, score: !q ? 0 : nl.startsWith(q) ? 0 : nl.includes(q) ? 1 : norm(kw).includes(q) ? 2 : 3 });
    }
    // com filtro: quem bate no nome vem primeiro (sem repetir títulos de seção)
    if (q) { out.sort((a, b) => a.score - b.score); out.forEach(it => { it.sec = 'Resultados'; }); }
    return out;
  }
  function drawMenu(list, items) {
    list.replaceChildren();
    if (!items.length) { list.append(el('div', 'ed-hint', 'Nada encontrado.')); return; }
    let sec = null;
    items.forEach((it, i) => {
      if (it.sec !== sec) { sec = it.sec; list.append(el('div', 'sec', sec)); }
      const b = el('button', 'item' + (i === menu.idx ? ' on' : '')); b.type = 'button';
      const ic = el('span', 'ic'); ic.append(typeof it.ic === 'function' ? it.ic() : it.ic);
      const txt = el('span'); txt.append(el('span', 'text-ink', it.label), el('small', '', it.desc));
      b.append(ic, txt);
      b.addEventListener('mousedown', e => e.preventDefault());
      b.addEventListener('click', () => chooseMenu(it));
      b.addEventListener('mousemove', () => { if (menu.idx !== i) { menu.idx = i; drawMenu(list, items); } });
      list.append(b);
    });
    list.querySelector('.item.on')?.scrollIntoView({ block: 'nearest' });
    placePop();
  }
  function openInsertMenu(rect, ctx) {
    if (locked) return;
    const box = el('div', 'ed-menu');
    const inp = el('input', 'input mb-1 py-1.5 text-sm'); inp.placeholder = 'Filtrar blocos…';
    const list = el('div');
    if (!ctx.slash) box.append(inp);
    box.append(list);
    openPop(rect, box);
    menu = { ...ctx, idx: 0, items: menuItems(''), list, q: '' };
    drawMenu(list, menu.items);
    if (!ctx.slash) {
      inp.focus();
      inp.addEventListener('input', () => { menu.items = menuItems(inp.value); menu.idx = 0; drawMenu(list, menu.items); });
      inp.addEventListener('keydown', menuKeys);
    }
  }
  function menuKeys(e) {
    if (!menu) return false;
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault(); const n = menu.items.length; if (!n) return true;
      menu.idx = (menu.idx + (e.key === 'ArrowDown' ? 1 : n - 1)) % n; drawMenu(menu.list, menu.items); return true;
    }
    if (e.key === 'Enter') { e.preventDefault(); const it = menu.items[menu.idx]; if (it) chooseMenu(it); else closePop(); return true; }
    if (e.key === 'Escape') { e.preventDefault(); closePop(); return true; }
    return false;
  }
  async function chooseMenu(it) {
    const ctx = menu; closePop();
    let replaceId = null;
    if (ctx.slash) {
      const r = findRich(ctx.slash.id);
      if (r) {
        const rg = rangeFromOffsets(r, ctx.slash.start, caretOffset(r));
        if (rg) { rg.deleteContents(); ctx.slash.block.html = cleanHtml(r.innerHTML); }
        if (ctx.slash.block.type === 'text' && !r.textContent.trim()) replaceId = ctx.slash.block.id;
      }
    }
    await insertType(it.t, { refId: ctx.refId, where: ctx.where, replaceId, rect: ctx.rect });
  }
  async function insertType(type, { refId, where = 'after', replaceId, rect }) {
    let nb;
    if (type === 'page') {
      const r = await api('POST', D.api.subpage, {});
      pages[r.id] = { t: r.t, i: r.i, u: r.u };
      nb = { id: uid(), type: 'page', page_id: r.id };
    } else if (type === 'pagelink') {
      const anchor = rect || findRich(refId)?.getBoundingClientRect() || root.getBoundingClientRect();
      openPagePicker(anchor, p => place({ id: uid(), type: 'page', page_id: Number(p) }));
      return;
    } else nb = newBlock(type);
    place(nb);

    function place(block) {
      snapshot();
      if (replaceId && RICH.has(block.type)) { const r = locate(replaceId); Object.assign(r.block, { ...block, id: r.block.id, html: r.block.html || '' }); block = r.block; }
      else if (replaceId) { const r = locate(replaceId); r.list.splice(r.index, 1, block); }
      else insertNear(refId, block, where);
      changed(); render();
      if (RICH.has(block.type)) focusBlock(block.id, 'start');
      else if (block.type === 'columns') focusBlock(block.cols[0].blocks[0].id, 'start');
      else select(block.id);
    }
  }
  function transform(b, type) {
    if (!RICH.has(type) || !RICH.has(b.type)) return;
    const kids = b.type === 'toggle' ? b.children : null;
    b.type = type;
    if (type === 'todo' && b.checked === undefined) b.checked = false;
    if (type === 'callout' && !b.icon) b.icon = 'ri:candle';
    if (type === 'toggle') { b.open = true; b.children = b.children || []; }
    else if (kids?.length) { delete b.children; delete b.open; const r = locate(b.id); r.list.splice(r.index + 1, 0, ...kids); }
    else { delete b.children; delete b.open; }
  }
  function openBlockMenu(rect, b) {
    select(b.id);
    const box = el('div', 'ed-menu');
    const item = (label, fn, cls = '') => {
      const x = el('button', 'item ' + cls); x.type = 'button'; x.textContent = label;
      x.addEventListener('click', () => { closePop(); fn(); }); box.append(x);
    };
    if (RICH.has(b.type)) {
      box.append(el('div', 'sec', 'Transformar em'));
      const row = el('div', 'flex flex-wrap gap-1 px-1 pb-1');
      for (const [t, lbl] of [['text', 'Texto'], ['h1', 'H1'], ['h2', 'H2'], ['h3', 'H3'], ['bullet', '•'], ['number', '1.'], ['todo', '☐'], ['toggle', '▸'], ['quote', '❝'], ['callout', 'Destaque']]) {
        const x = button(lbl, t, 'rounded-md border border-line px-2 py-1 text-xs ' + (b.type === t ? 'bg-surface-2 text-ink' : ''));
        x.addEventListener('click', () => { closePop(); snapshot(); transform(b, t); changed(); render(); focusBlock(b.id); });
        row.append(x);
      }
      box.append(row);
    }
    box.append(el('div', 'sec', 'Cor'));
    const grid = el('div', 'colors');
    const sw = (val, label, txt) => {
      const x = button(txt, label); x.className = val.endsWith('_bg') ? 'bg-' + val.slice(0, -3) : (val ? 'c-' + val : '');
      if (val === '') x.textContent = '∅';
      x.addEventListener('click', () => { closePop(); snapshot(); if (val) b.color = val; else delete b.color; changed(); render(); });
      grid.append(x);
    };
    sw('', 'Sem cor', '∅');
    COLORS.forEach(([c, n]) => sw(c, 'Texto ' + n.toLowerCase(), 'A'));
    COLORS.forEach(([c, n]) => sw(c + '_bg', 'Fundo ' + n.toLowerCase(), ''));
    box.append(grid);
    box.append(el('div', 'sec', 'Bloco'));
    if (b.type === 'markdown') item('Converter em blocos', () => convertMarkdown(b));
    if (b.type === 'divider') item('Trocar estilo…', () => openDividerMenu(rect, b));
    if (b.type === 'callout') item('Trocar ícone…', () => openIconPicker(rect, v => { b.icon = v; changed(); render(); }));
    if (b.type === 'embed' && b.url) item('Trocar link…', () => { const v = prompt('Link', b.url); if (v && /^https?:\/\//.test(v.trim())) { b.url = v.trim(); changed(); render(); } });
    item('Duplicar  (Ctrl+D)', () => { snapshot(); const c = cloneBlock(b); insertNear(b.id, c); changed(); render(); select(c.id); });
    item('Mover para cima', () => moveStep(b, -1));
    item('Mover para baixo', () => moveStep(b, 1));
    item('Apagar  (Del)', () => { removeBlock(b.id); selectedId = null; changed(); render(); }, 'danger');
    openPop(rect, box);
  }
  function moveStep(b, d) {
    const r = locate(b.id); const j = r.index + d;
    if (j < 0 || j >= r.list.length) return;
    snapshot(); r.list.splice(r.index, 1); r.list.splice(j, 0, b); changed(); render(); select(b.id);
  }
  function openDividerMenu(rect, b) {
    const box = el('div', 'ed-menu');
    box.append(el('div', 'sec', 'Estilo do divisor'));
    const opts = [{ key: 'line' }, ...D.dividers];
    for (const s of opts) {
      const x = el('button', 'item' + (b.style === s.key ? ' on' : '')); x.type = 'button';
      x.append(renderDivider({ style: s.key }));
      x.firstChild.style.pointerEvents = 'none'; x.firstChild.style.width = '100%';
      x.addEventListener('click', () => { closePop(); b.style = s.key; changed(); render(); });
      box.append(x);
    }
    box.append(el('div', 'ed-hint', 'Novos estilos: coloque SVG ou PNG em lore/static/dividers/.'));
    openPop(rect, box);
  }
  function openIconPicker(rect, pick) {
    const box = el('div');
    const grid = el('div', 'icon-grid');
    for (const n of ICONS) { const x = button(ri(n), n); x.addEventListener('click', () => { closePop(); pick('ri:' + n); }); grid.append(x); }
    const inp = el('input', 'input mt-1 py-1.5 text-sm'); inp.placeholder = 'ou cole um emoji e Enter';
    inp.addEventListener('keydown', e => { if (e.key === 'Enter' && inp.value.trim()) { closePop(); pick(inp.value.trim().slice(0, 8)); } });
    box.append(grid, inp);
    openPop(rect, box);
  }
  function openPagePicker(rect, pick, query = '') {
    const box = el('div', 'ed-menu');
    const inp = el('input', 'input mb-1 py-1.5 text-sm'); inp.placeholder = 'Buscar página…'; inp.value = query;
    const list = el('div'); box.append(inp, list);
    openPop(rect, box);
    let idx = 0, items = [];
    const draw = () => {
      const q = norm(inp.value);
      items = Object.entries(pages).filter(([id]) => Number(id) !== D.aid).filter(([, p]) => !q || norm(p.t).includes(q))
        .sort((a, b) => a[1].t.localeCompare(b[1].t)).slice(0, 40);
      list.replaceChildren();
      items.forEach(([id, p], i) => {
        const x = el('button', 'item' + (i === idx ? ' on' : '')); x.type = 'button';
        const ic = el('span', 'ic'); ic.append(glyph(p.i || 'ri:scroll', 18)); x.append(ic, el('span', 'text-ink', p.t));
        x.addEventListener('mousedown', e => e.preventDefault());
        x.addEventListener('click', () => { closePop(); pick(id); }); list.append(x);
      });
      if (inp.value.trim()) {
        const x = el('button', 'item'); x.type = 'button'; x.append(el('span', 'ic', '+'), el('span', '', `Criar subpágina “${inp.value.trim()}”`));
        x.addEventListener('click', async () => {
          closePop(); const r = await api('POST', D.api.subpage, { title: inp.value.trim() });
          pages[r.id] = { t: r.t, i: r.i, u: r.u }; pick(String(r.id));
        });
        list.append(x);
      }
      placePop();
    };
    inp.addEventListener('input', () => { idx = 0; draw(); });
    inp.addEventListener('keydown', e => {
      if (e.key === 'ArrowDown') { e.preventDefault(); idx = Math.min(items.length - 1, idx + 1); draw(); }
      if (e.key === 'ArrowUp') { e.preventDefault(); idx = Math.max(0, idx - 1); draw(); }
      if (e.key === 'Enter') { e.preventDefault(); if (items[idx]) { closePop(); pick(items[idx][0]); } }
      if (e.key === 'Escape') closePop();
    });
    draw(); inp.focus();
  }

  // ---------- barra de formatação (seleção de texto)
  let bar = null;
  function hideBar() { bar?.remove(); bar = null; }
  function showBar() {
    if (locked) return hideBar();
    const sel = getSelection();
    if (!sel.rangeCount || sel.isCollapsed) return hideBar();
    const r = sel.anchorNode?.parentElement?.closest('[data-rich]');
    if (!r || !root.contains(r) || !r.contains(sel.focusNode)) return hideBar();
    const rect = sel.getRangeAt(0).getBoundingClientRect();
    if (!bar) {
      bar = el('div', 'ed-pop ed-bar');
      const cmd = (label, title, fn, cls = '') => { const x = button(label, title, cls); x.addEventListener('mousedown', e => e.preventDefault()); x.addEventListener('click', fn); bar.append(x); };
      const done = () => { const rr = getSelection().anchorNode?.parentElement?.closest('[data-rich]'); rr?.dispatchEvent(new Event('input', { bubbles: true })); };
      cmd('B', 'Negrito (Ctrl+B)', () => { document.execCommand('bold'); done(); }, 'font-bold');
      cmd('I', 'Itálico (Ctrl+I)', () => { document.execCommand('italic'); done(); }, 'italic');
      cmd('U', 'Sublinhado (Ctrl+U)', () => { document.execCommand('underline'); done(); }, 'underline');
      cmd('S', 'Riscado', () => { document.execCommand('strikeThrough'); done(); }, 'line-through');
      cmd('</>', 'Código', () => wrapSelection('code'));
      bar.append(el('span', 'sep'));
      cmd(ui('link', 'size-4'), 'Link (Ctrl+K)', () => addLink());
      cmd(ri('scroll'), 'Link para página', () => {
        const range = getSelection().getRangeAt(0).cloneRange();
        openPagePicker(bar.getBoundingClientRect(), id => {
          const s = getSelection(); s.removeAllRanges(); s.addRange(range);
          const p = pages[id];
          document.execCommand('insertHTML', false, `<a href="${p.u}" data-page="${id}">${esc(range.toString() || p.t)}</a>`);
          r.dispatchEvent(new Event('input', { bubbles: true }));
        });
      });
      bar.append(el('span', 'sep'));
      cmd('A', 'Cor do texto', () => colorMenu());
      document.body.append(bar);
    }
    const w = bar.offsetWidth;
    bar.style.left = Math.max(8, Math.min(innerWidth - w - 8, rect.left + rect.width / 2 - w / 2)) + 'px';
    bar.style.top = Math.max(8, rect.top - bar.offsetHeight - 8) + 'px';
  }
  function wrapSelection(tag, cls = '') {
    const sel = getSelection(); if (!sel.rangeCount) return;
    const range = sel.getRangeAt(0), tmp = el('div'); tmp.append(range.cloneContents());
    const inner = tag === 'code' ? esc(tmp.textContent) : tmp.innerHTML;
    document.execCommand('insertHTML', false, cls === null ? esc(tmp.textContent) : `<${tag}${cls ? ` class="${cls}"` : ''}>${inner}</${tag}>`);
    sel.anchorNode?.parentElement?.closest('[data-rich]')?.dispatchEvent(new Event('input', { bubbles: true }));
  }
  function colorMenu() {
    const range = getSelection().getRangeAt(0).cloneRange();
    const box = el('div', 'ed-menu');
    const grid = el('div', 'colors');
    const apply = (tag, cls) => () => { closePop(); const s = getSelection(); s.removeAllRanges(); s.addRange(range); wrapSelection(tag, cls); };
    const x0 = button('∅', 'Sem cor'); x0.addEventListener('click', apply('span', null)); grid.append(x0);
    COLORS.forEach(([c, n]) => { const x = button('A', 'Texto ' + n.toLowerCase(), 'c-' + c); x.addEventListener('click', apply('span', 'c-' + c)); grid.append(x); });
    COLORS.forEach(([c, n]) => { const x = button('A', 'Marca-texto ' + n.toLowerCase(), 'bg-' + c); x.addEventListener('click', apply('mark', 'bg-' + c)); grid.append(x); });
    box.append(el('div', 'sec', 'Texto e marca-texto'), grid);
    openPop(bar.getBoundingClientRect(), box);
  }
  function addLink() {
    const sel = getSelection(); if (!sel.rangeCount) return;
    const range = sel.getRangeAt(0).cloneRange();
    const url = prompt('Link (https://…)');
    if (!url || !/^(https?:\/\/|mailto:)/.test(url.trim())) return;
    sel.removeAllRanges(); sel.addRange(range);
    if (range.collapsed) document.execCommand('insertHTML', false, `<a href="${esc(url.trim())}">${esc(url.trim())}</a>`);
    else document.execCommand('createLink', false, url.trim());
    sel.anchorNode?.parentElement?.closest('[data-rich]')?.dispatchEvent(new Event('input', { bubbles: true }));
  }
  document.addEventListener('selectionchange', () => { if (!drag) requestAnimationFrame(showBar); });

  // ------------------------------------------------------------------ digitação
  const SHORTCUTS = [[/^#\s$/, 'h1'], [/^##\s$/, 'h2'], [/^###\s$/, 'h3'], [/^[-*]\s$/, 'bullet'], [/^1[.)]\s$/, 'number'],
    [/^\[\s?\]\s$/, 'todo'], [/^>\s$/, 'quote'], [/^"\s$/, 'quote'], [/^!\s$/, 'callout']];
  root.addEventListener('input', e => {
    const r = e.target.closest?.('[data-rich]'); if (!r) return;
    const b = r._block, key = r.dataset.key;
    const html = cleanHtml(r.innerHTML);
    if (key === 'cell') b.rows[r.dataset.r][r.dataset.c] = html; else b[key] = html;
    changed();
    if (key !== 'html') return;
    const off = caretOffset(r), before = r.textContent.slice(0, off);
    // atalhos markdown no começo do bloco
    if (b.type === 'text' && off <= 4) {
      for (const [re, t] of SHORTCUTS) if (re.test(before)) {
        rangeFromOffsets(r, 0, off)?.deleteContents(); b.html = cleanHtml(r.innerHTML);
        transform(b, t); render(); focusBlock(b.id, 'start'); return;
      }
      if (before === '---' || before === '***') {
        b.html = ''; const d = newBlock('divider'); const loc = locate(b.id);
        loc.list.splice(loc.index, 0, d); render(); focusBlock(b.id, 'start'); return;
      }
      if (before === '```') { const loc = locate(b.id); const c = newBlock('code'); loc.list.splice(loc.index, 1, c); render(); root.querySelector(`.blk[data-id="${c.id}"] .code`)?.focus(); return; }
    }
    // [[ → link para página
    if (before.endsWith('[[')) {
      const caretRect = getSelection().getRangeAt(0).getBoundingClientRect();
      openPagePicker(caretRect.width || caretRect.height ? caretRect : r.getBoundingClientRect(), id => {
        const cur = caretOffset(r) || off;
        setCaret(r, cur); rangeFromOffsets(r, Math.max(0, off - 2), off)?.deleteContents();
        const p = pages[id];
        document.execCommand('insertHTML', false, `<a href="${p.u}" data-page="${id}">${esc(p.t)}</a>&nbsp;`);
        r.dispatchEvent(new Event('input', { bubbles: true }));
      });
      return;
    }
    // "/" → menu de blocos
    const m = before.match(/(?:^|\s)\/([^\s/]{0,20})$/);
    if (m) {
      const start = off - m[1].length - 1;
      if (!menu?.slash || menu.slash.id !== b.id) {
        const caretRect = getSelection().getRangeAt(0).getBoundingClientRect();
        const rect = caretRect.height ? caretRect : r.getBoundingClientRect();
        openInsertMenu(rect, { refId: b.id, where: 'after', slash: { id: b.id, block: b, start }, rect });
      }
      menu.q = m[1]; menu.items = menuItems(m[1]); menu.idx = 0; drawMenu(menu.list, menu.items);
    } else if (menu?.slash) closePop();
  });

  root.addEventListener('keydown', e => {
    const r = e.target.closest?.('[data-rich]'); if (!r) return;
    if (menu?.slash && menuKeys(e)) return;
    const b = r._block, key = r.dataset.key;
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); addLink(); return; }
    if (key === 'cell') {
      if (e.key === 'Tab') {
        e.preventDefault();
        const cells = [...r.closest('table').querySelectorAll('[data-rich]')], i = cells.indexOf(r);
        const nx = cells[i + (e.shiftKey ? -1 : 1)];
        if (nx) setCaret(nx, 'end'); else if (!e.shiftKey) { b.rows.push(b.rows[0].map(() => '')); changed(); render(); setCaret(findRich(b.id, 'cell', b.rows.length - 1, 0), 0); }
      }
      return;
    }
    if (key === 'caption') {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); const nb = newBlock('text'); insertNear(b.id, nb); changed(); render(); focusBlock(nb.id, 'start'); }
      return;
    }
    if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
      e.preventDefault();
      if (LISTS.has(b.type) && !r.textContent.trim()) { transform(b, 'text'); changed(); render(); focusBlock(b.id, 'start'); return; }
      const after = splitAtCaret(r); b.html = cleanHtml(r.innerHTML);
      const nb = { ...newBlock(LISTS.has(b.type) ? b.type : 'text'), html: after };
      if (b.type === 'toggle' && b.open) b.children.unshift(nb); else insertNear(b.id, nb);
      changed(); render(); focusBlock(nb.id, 'start');
    } else if (e.key === 'Backspace' && collapsed() && caretOffset(r) === 0) {
      if (b.type !== 'text') { e.preventDefault(); transform(b, 'text'); changed(); render(); focusBlock(b.id, 'start'); return; }
      const list = allRich(), i = list.indexOf(r), prev = list[i - 1];
      if (!prev) { if (!r.textContent && blocks.length > 1) { e.preventDefault(); const nx = list[1]; removeBlock(b.id, true); changed(); render(); if (nx) focusBlock(nx.dataset.rich, 'start'); } return; }
      e.preventDefault();
      const pb = prev._block, off = prev.textContent.length;
      pb.html = (pb.html || '') + (b.html || '');
      removeBlock(b.id, true); changed(); render(); focusBlock(pb.id, off);
    } else if (e.key === 'ArrowUp' && collapsed() && caretOffset(r) === 0) {
      const list = allRich(), prev = list[list.indexOf(r) - 1]; if (prev) { e.preventDefault(); setCaret(prev, 'end'); }
    } else if (e.key === 'ArrowDown' && collapsed() && caretOffset(r) === r.textContent.length) {
      const list = allRich(), nx = list[list.indexOf(r) + 1]; if (nx) { e.preventDefault(); setCaret(nx, 0); }
    } else if (e.key === 'Escape') { r.blur(); select(b.id); }
    else if (e.key === 'Tab') e.preventDefault();
  });

  root.addEventListener('paste', async e => {
    const r = e.target.closest?.('[data-rich], .code'); if (!r || locked) return;
    const files = [...e.clipboardData.files];
    if (files.length) { e.preventDefault(); await insertFiles(files, r.dataset.rich || r.closest('.blk').dataset.id, 'after'); return; }
    if (r.classList.contains('code')) return;
    e.preventDefault();
    const text = e.clipboardData.getData('text/plain');
    const b = r._block, url = text.trim();
    if (/^https?:\/\/\S+$/.test(url) && r.dataset.key === 'html') {
      const k = parseEmbed(url);
      if (k && k.kind !== 'link' && !r.textContent.trim() && b.type === 'text') {
        const loc = locate(b.id); loc.list.splice(loc.index, 1, { ...newBlock('embed'), url }); changed(); render(); return;
      }
      document.execCommand('insertHTML', false, `<a href="${esc(url)}">${esc(url)}</a>`);
      return;
    }
    const parts = text.replace(/\r/g, '').split(/\n{2,}/);
    if (parts.length > 1 && r.dataset.key === 'html') {
      document.execCommand('insertText', false, parts[0]);
      let ref = b.id;
      for (const p of parts.slice(1)) { const nb = { ...newBlock('text'), html: esc(p).replace(/\n/g, '<br>') }; insertNear(ref, nb); ref = nb.id; }
      r.dispatchEvent(new Event('input', { bubbles: true })); render(); focusBlock(ref, 'end');
    } else document.execCommand('insertText', false, text);
  });

  root.addEventListener('click', async e => {
    const a = e.target.closest('a');
    if (!a || !root.contains(a) || dragJustEnded) { if (dragJustEnded) e.preventDefault(); return; }
    if (a.closest('.rich') || a.classList.contains('pagelink') || a.closest('.md-box')) {
      e.preventDefault();
      if (a.closest('.rich') && !a.dataset.page && !locked && !(e.ctrlKey || e.metaKey) && document.activeElement === a.closest('.rich') && !collapsed()) return;
      if (READONLY && (a.dataset.page && !pages[a.dataset.page] || a.classList.contains('gone'))) return;   // não revelada
      if (READONLY && a.dataset.page) { location.href = pages[a.dataset.page].u; return; }
      const internal = a.dataset.page || a.classList.contains('pagelink') || a.getAttribute('href')?.startsWith('/');
      if (internal) { await flush(); location.href = a.href; } else window.open(a.href, '_blank', 'noopener');
    }
  });

  // ------------------------------------------------------------------ seleção de bloco (teclado)
  function select(id) {
    selectedId = id;
    root.querySelectorAll('.blk.selected').forEach(x => x.classList.remove('selected'));
    if (id) root.querySelector(`.blk[data-id="${id}"]`)?.classList.add('selected');
  }
  root.addEventListener('focusin', e => { if (e.target.closest('[data-rich]')) select(null); });
  document.addEventListener('mousedown', e => { if (!root.contains(e.target) && !pop?.contains(e.target)) select(null); });
  document.addEventListener('keydown', e => {
    if (!selectedId || locked || e.target.closest('input, textarea, [contenteditable="true"], [contenteditable="plaintext-only"]')) return;
    const r = locate(selectedId); if (!r) return;
    if (e.key === 'Delete' || e.key === 'Backspace') { e.preventDefault(); removeBlock(selectedId); selectedId = null; changed(); render(); }
    else if (e.key === 'Enter') { e.preventDefault(); const nb = newBlock('text'); insertNear(selectedId, nb); changed(); render(); focusBlock(nb.id, 'start'); }
    else if (e.key === 'Escape') select(null);
    else if (e.key === 'ArrowUp' || e.key === 'ArrowDown') {
      e.preventDefault();
      const all = [...root.querySelectorAll('.blk')], i = all.findIndex(x => x.dataset.id === selectedId);
      const nx = all[i + (e.key === 'ArrowUp' ? -1 : 1)]; if (nx) select(nx.dataset.id);
    } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'd') {
      e.preventDefault(); snapshot(); const c = cloneBlock(r.block); insertNear(selectedId, c); changed(); render(); select(c.id);
    }
  });

  function clickBelow(e) {
    if (locked) return;
    e.preventDefault();
    const last = blocks[blocks.length - 1];
    if (last && last.type === 'text' && !last.html) { focusBlock(last.id, 'start'); return; }
    const nb = newBlock('text'); blocks.push(nb); changed(); render(); focusBlock(nb.id, 'start');
  }

  // ------------------------------------------------------------------ arrastar e soltar
  // Regras para não bagunçar a página:
  //  • acima/abaixo é o padrão; para criar colunas é preciso PARAR perto da borda lateral (~0,45 s)
  //  • nos vãos entre blocos usa o bloco mais próximo (o indicador não "pula")
  //  • soltar no mesmo lugar não muda nada; Esc cancela; Ctrl+Z desfaz
  let drag = null, dragJustEnded = false;
  const SIDE_PX = 30, SIDE_DWELL = 450, HYST = 8;
  const line = el('div', 'drop-line'); line.hidden = true; document.body.append(line);

  function nearestBlock(listEl, y) {
    let best = null, bd = Infinity;
    for (const be of listEl?.querySelectorAll(':scope > .blk') || []) {
      if (be === drag?.w) continue;
      const r = be.getBoundingClientRect(), d = y < r.top ? r.top - y : y > r.bottom ? y - r.bottom : 0;
      if (d < bd) { bd = d; best = be; }
    }
    return best;
  }
  function rawTarget(x, y, prev) {
    const t0 = document.elementFromPoint(x, y);
    if (!t0 || !root.contains(t0)) return null;
    if (t0.closest('.add-below')) return { kind: 'end' };
    const slot = t0.closest('.empty-slot');
    if (slot) return { kind: 'into', list: slot._list, el: slot };
    let be = t0.closest('.blk');
    if (!be) be = nearestBlock(t0.closest('.list') || root.querySelector(':scope > .list'), y);
    if (!be) return null;
    if (drag && (be === drag.w || drag.w.contains(be))) return { kind: 'self' };
    const dragged = drag ? locate(drag.id)?.block : null;
    const inCol = be.parentElement.closest('.col');
    const direct = inCol && be.parentElement.parentElement === inCol;
    if (dragged?.type === 'columns' && inCol) be = inCol.closest('.blk');   // colunas não entram em colunas
    const r = be.getBoundingClientRect(), side = Math.min(SIDE_PX, r.width * 0.12);
    const sideOk = be.dataset.type !== 'columns' && dragged?.type !== 'columns' && (!inCol || direct);
    if (sideOk && x < r.left + side) return { kind: 'left', id: be.dataset.id, el: be };
    if (sideOk && x > r.right - side) return { kind: 'right', id: be.dataset.id, el: be };
    // histerese: perto do meio do bloco, mantém o lado anterior (evita o indicador piscar)
    const mid = r.top + r.height / 2;
    if (prev && prev.el === be && (prev.kind === 'before' || prev.kind === 'after') && Math.abs(y - mid) < HYST) return prev;
    return { kind: y < mid ? 'before' : 'after', id: be.dataset.id, el: be };
  }
  // posição final (lista + índice) para saber se a soltura muda alguma coisa
  function isNoop(id, t) {
    if (!t || t.kind === 'self') return true;
    if (t.kind !== 'before' && t.kind !== 'after') return false;
    const src = locate(id), dst = locate(t.id);
    if (!src || !dst || src.list !== dst.list) return false;
    const idx = dst.index + (t.kind === 'after' ? 1 : 0);
    return idx === src.index || idx === src.index + 1;
  }
  function showLine(t, pending) {
    if (!t || t.kind === 'self' || (drag && isNoop(drag.id, t))) { line.hidden = true; return; }
    line.hidden = false;
    line.classList.toggle('pending', !!pending);
    let r;
    if (t.kind === 'end') {
      const lastEl = root.querySelector(':scope > .list > .blk:last-child'); r = lastEl.getBoundingClientRect();
      Object.assign(line.style, { left: r.left + 'px', top: r.bottom + 2 + 'px', width: r.width + 'px', height: '3px' }); return;
    }
    r = t.el.getBoundingClientRect();
    if (t.kind === 'into') Object.assign(line.style, { left: r.left + 'px', top: r.top + 'px', width: r.width + 'px', height: '3px' });
    else if (t.kind === 'before' || t.kind === 'after') Object.assign(line.style, { left: r.left + 'px', top: (t.kind === 'before' ? r.top - 2 : r.bottom - 1) + 'px', width: r.width + 'px', height: '3px' });
    else Object.assign(line.style, { left: (t.kind === 'left' ? r.left - 6 : r.right + 3) + 'px', top: r.top + 'px', width: '3px', height: r.height + 'px' });
  }
  function startDrag(e, b, w, grip) {
    if (locked || e.button !== 0) return;
    e.preventDefault();
    const sx = e.clientX, sy = e.clientY;
    let started = false, ghost = null, target = null, scrollTimer = null, side = null, dwellTimer = null, last = null, raf = 0;
    const evaluate = () => {
      if (!last) return;
      const raw = rawTarget(last.x, last.y, target);
      if (raw && (raw.kind === 'left' || raw.kind === 'right')) {
        const key = raw.id + raw.kind;
        if (!side || side.key !== key) {
          side = { key, at: Date.now() };
          clearTimeout(dwellTimer); dwellTimer = setTimeout(evaluate, SIDE_DWELL + 20);
        }
        if (Date.now() - side.at < SIDE_DWELL) {
          // ainda não decidiu criar coluna: mostra acima/abaixo e um aviso discreto na lateral
          const r = raw.el.getBoundingClientRect();
          target = { kind: last.y < r.top + r.height / 2 ? 'before' : 'after', id: raw.id, el: raw.el };
          showLine(target, true); return;
        }
        target = raw;
      } else { side = null; clearTimeout(dwellTimer); target = raw; }
      showLine(target);
    };
    const move = ev => {
      if (!started) {
        if (Math.hypot(ev.clientX - sx, ev.clientY - sy) < 6) return;
        started = true; drag = { id: b.id, w }; closePop(); hideBar(); select(null);
        w.classList.add('dragging'); document.body.classList.add('ed-dragging');
        ghost = el('div', 'drag-ghost'); ghost.append(w.querySelector('.body').cloneNode(true)); document.body.append(ghost);
        ghost.style.transform = `translate(${ev.clientX + 14}px, ${ev.clientY + 10}px) rotate(-1deg)`;
        addEventListener('keydown', onKey, true);
      }
      last = { x: ev.clientX, y: ev.clientY };
      evaluate();                                  // alvo sempre calculado na hora
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => { ghost.style.transform = `translate(${last.x + 14}px, ${last.y + 10}px) rotate(-1deg)`; });
      clearInterval(scrollTimer);
      const edge = 80;
      if (ev.clientY < edge) scrollTimer = setInterval(() => { scrollBy(0, -Math.ceil((edge - last.y) / 5)); evaluate(); }, 16);
      else if (ev.clientY > innerHeight - edge) scrollTimer = setInterval(() => { scrollBy(0, Math.ceil((last.y - innerHeight + edge) / 5)); evaluate(); }, 16);
    };
    const finish = drop => {
      removeEventListener('pointermove', move); removeEventListener('pointerup', up); removeEventListener('keydown', onKey, true);
      clearInterval(scrollTimer); clearTimeout(dwellTimer); cancelAnimationFrame(raf);
      ghost?.remove(); line.hidden = true; line.classList.remove('pending');
      w.classList.remove('dragging'); document.body.classList.remove('ed-dragging');
      drag = null; dragJustEnded = true; setTimeout(() => { dragJustEnded = false; }, 60);
      if (drop && target && !isNoop(b.id, target)) moveBlock(b.id, target);
    };
    const up = ev => { if (started && ev) { last = { x: ev.clientX, y: ev.clientY }; evaluate(); }
      if (!started) { removeEventListener('pointermove', move); removeEventListener('pointerup', up); openBlockMenu(grip.getBoundingClientRect(), b); return; } finish(true); };
    const onKey = ev => { if (ev.key === 'Escape') { ev.preventDefault(); ev.stopPropagation(); finish(false); } };
    addEventListener('pointermove', move); addEventListener('pointerup', up);
  }
  function moveBlock(id, t) {
    const src = locate(id); if (!src) return;
    if (t.id && (t.id === id || isInside(src.block, t.id))) return;
    snapshot();
    src.list.splice(src.index, 1);
    placeAt(src.block, t);
    normalize(); changed(); render(); select(id);
    undoToast(t.kind === 'left' || t.kind === 'right' ? 'Coluna criada' : 'Bloco movido');
  }
  function placeAt(b, t) {
    if (t.kind === 'end') { blocks.push(b); return; }
    if (t.kind === 'into') { t.list.push(b); return; }
    const r = locate(t.id); if (!r) { blocks.push(b); return; }
    if (t.kind === 'before' || t.kind === 'after') { r.list.splice(r.index + (t.kind === 'after' ? 1 : 0), 0, b); return; }
    if (r.owner && r.owner.type === 'columns') {
      const cols = r.owner.cols, n = cols.length + 1;
      if (n > 5) { r.list.splice(r.index + 1, 0, b); return; }
      // a coluna nova pega uma fatia; as outras encolhem na mesma proporção (sem desfazer o que você ajustou)
      const nw = 100 / n;
      cols.forEach(c => { c.w = c.w * (100 - nw) / 100; });
      cols.splice(r.colIdx + (t.kind === 'right' ? 1 : 0), 0, { w: nw, blocks: [b] });
      return;
    }
    const pair = t.kind === 'left' ? [b, r.block] : [r.block, b];
    r.list.splice(r.index, 1, { id: uid(), type: 'columns', cols: pair.map(x => ({ w: 50, blocks: [x] })) });
  }

  // ------------------------------------------------------------------ desfazer / refazer (mudanças de estrutura)
  // Vale para mover, apagar, inserir, transformar, duplicar e converter. Ao voltar a digitar, o histórico recomeça.
  const undoStack = [], redoStack = [];
  let lastWasStructural = false;
  function snapshot() {
    undoStack.push(JSON.stringify(blocks)); if (undoStack.length > 60) undoStack.shift();
    redoStack.length = 0; lastWasStructural = true;
  }
  function restoreFrom(from, to) {
    if (!from.length) return false;
    to.push(JSON.stringify(blocks)); blocks = JSON.parse(from.pop());
    selectedId = null; normalize(); changed(); render(); return true;
  }
  const undo = () => restoreFrom(undoStack, redoStack) && undoToast('Desfeito', true);
  const redo = () => restoreFrom(redoStack, undoStack) && undoToast('Refeito', true);
  let toastEl = null, toastTimer = null;
  function undoToast(msg, noButton) {
    toastEl?.remove(); clearTimeout(toastTimer);
    toastEl = el('div', 'ed-toast'); toastEl.append(el('span', '', msg));
    if (!noButton) { const u = button('Desfazer', 'Desfazer (Ctrl+Z)'); u.addEventListener('click', () => { undo(); }); toastEl.append(u, el('kbd', '', 'Ctrl+Z')); }
    document.body.append(toastEl);
    toastTimer = setTimeout(() => { toastEl?.remove(); toastEl = null; }, 5000);
  }
  document.addEventListener('keydown', e => {
    if (!(e.ctrlKey || e.metaKey) || locked) return;
    const k = e.key.toLowerCase();
    if (k !== 'z' && k !== 'y') return;
    const typing = e.target.closest?.('input, textarea, [contenteditable="true"], [contenteditable="plaintext-only"]');
    // dentro do texto, o Ctrl+Z do navegador desfaz a digitação; o nosso só entra logo após mover/apagar
    if (typing && !(undoStack.length && lastWasStructural)) return;
    if (k === 'y' || (k === 'z' && e.shiftKey)) { if (redoStack.length) { e.preventDefault(); redo(); } }
    else if (undoStack.length) { e.preventDefault(); undo(); }
  });
  // digitou de novo: o histórico de estrutura recomeça (o Ctrl+Z do texto é do navegador)
  root.addEventListener('input', () => { undoStack.length = 0; redoStack.length = 0; lastWasStructural = false; }, true);

  // arquivos soltos na página: imagens, áudios, vídeos e arquivos viram blocos
  async function insertFiles(files, refId, where) {
    snapshot();
    let ref = refId, w = where;
    for (const f of files) {
      const kind = f.type.startsWith('image/') ? 'image' : f.type.startsWith('audio/') ? 'audio' : f.type.startsWith('video/') ? 'video' : 'file';
      try {
        const up = await uploadFile(f, kind);
        const nb = newBlock(kind);
        if (kind === 'image') nb.src = up.url; else { nb.file_id = up.id; nb.name = up.name; }
        insertNear(ref, nb, w); ref = nb.id; w = 'after';
      } catch { /* toast já mostrado */ }
    }
    changed(); render();
  }
  root.addEventListener('dragover', e => { if (locked || !e.dataTransfer.types.includes('Files')) return; e.preventDefault(); root.classList.add('ed-drop-files'); drag = null; showLine(dropTarget(e.clientX, e.clientY)); });
  root.addEventListener('dragleave', e => { if (!root.contains(e.relatedTarget)) { root.classList.remove('ed-drop-files'); line.hidden = true; } });
  root.addEventListener('drop', e => {
    if (locked || !e.dataTransfer.files.length) return;
    e.preventDefault(); root.classList.remove('ed-drop-files'); line.hidden = true;
    const t = dropTarget(e.clientX, e.clientY);
    const ref = t?.id || blocks[blocks.length - 1]?.id;
    insertFiles([...e.dataTransfer.files], ref, t?.kind === 'before' ? 'before' : 'after');
  });

  // ------------------------------------------------------------------ título
  titleEl.addEventListener('keydown', e => {
    if (e.key === 'Enter') { e.preventDefault(); const first = allRich()[0]; if (first) setCaret(first, 0); }
  });
  titleEl.addEventListener('input', () => changed());
  titleEl.addEventListener('paste', e => { e.preventDefault(); document.execCommand('insertText', false, e.clipboardData.getData('text/plain').replace(/\s+/g, ' ')); });

  // ------------------------------------------------------------------ travar edição
  function syncLock() {
    lockBtn.replaceChildren(ui(locked ? 'x' : 'pencil', 'size-4'));
    lockBtn.title = locked ? 'Edição travada · clique para editar' : 'Editando · clique para travar (modo leitura)';
    lockBtn.setAttribute('aria-label', lockBtn.title);
    lockBtn.classList.toggle('text-accent-ink', !locked);
  }
  if (READONLY) lockBtn.hidden = true;
  lockBtn.addEventListener('click', () => { locked = !locked; localStorage.setItem('page-locked', locked ? '1' : ''); closePop(); hideBar(); syncLock(); render(); });

  // ------------------------------------------------------------------ salvar e sincronizar
  let dirty = false, saving = false, timer = null;
  const setState = t => { stateEl.textContent = t; };
  function changed() { if (READONLY) return; dirty = true; setState('editando…'); clearTimeout(timer); timer = setTimeout(save, 800); }
  const payload = () => JSON.parse(JSON.stringify(blocks, (k, v) => (k === '_html' ? undefined : v)));
  async function save() {
    if (!dirty) return;
    if (saving) { clearTimeout(timer); timer = setTimeout(save, 400); return; }
    saving = true; dirty = false; setState('salvando…');
    try {
      const res = await fetch(D.api.save, { method: 'PUT', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf(), Accept: 'application/json' },
        body: JSON.stringify({ blocks: payload(), version, title: titleEl.textContent.trim() }) });
      const j = await res.json().catch(() => ({}));
      if (res.status === 409) { applyRemote(j); toast('Outra pessoa editou esta página: carreguei a versão mais nova.', true); setState(''); }
      else if (res.ok) {
        version = j.version;
        if (j.title_error) { toast(j.title_error, true); }
        else if (j.title) { document.title = document.title.replace(/^[^·]*/, j.title + ' '); if (pages[D.aid]) pages[D.aid].t = j.title; }
        setState(dirty ? 'editando…' : 'salvo ✓');
      } else { dirty = true; setState('erro ao salvar'); toast(j.error || 'Não foi possível salvar.', true); }
    } catch { dirty = true; setState('sem conexão'); }
    saving = false;
    if (dirty) { clearTimeout(timer); timer = setTimeout(save, 1500); }
  }
  async function flush() { clearTimeout(timer); if (dirty) await save(); while (saving) await new Promise(r => setTimeout(r, 50)); }
  function applyRemote(j) {
    if (!j || !j.blocks) return;
    blocks = j.blocks; version = j.version; if (j.pages) pages = j.pages;
    if (j.title && document.activeElement !== titleEl) titleEl.textContent = j.title;
    render();
  }
  addEventListener('beforeunload', e => { if (dirty || saving) { save(); e.preventDefault(); e.returnValue = ''; } });
  document.addEventListener('keydown', e => { if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') { e.preventDefault(); flush(); } });
  setInterval(async () => {
    if (READONLY || dirty || saving || drag || document.hidden || pop) return;
    const a = document.activeElement;
    if (a && (root.contains(a) && a !== document.body) || a === titleEl) return;
    try {
      const r = await fetch(`${D.api.save}?v=${version}`, { headers: { Accept: 'application/json' } });
      if (r.status === 200) applyRemote(await r.json());
    } catch { /* tenta de novo */ }
  }, 6000);

  // ------------------------------------------------------------------ início
  syncLock();
  render();
  if (!locked && blocks.length === 1 && blocks[0].type === 'text' && !blocks[0].html && titleEl.textContent.trim().startsWith('Sem título')) {
    const s = getSelection(), rg = document.createRange(); rg.selectNodeContents(titleEl); titleEl.focus(); s.removeAllRanges(); s.addRange(rg);
  }
})();
