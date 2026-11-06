// Ícones do site no JS — mesmas regras de lore/icons.py.
(() => {
  const SVG = document.currentScript.dataset.uiSprite;
  const NS = 'http://www.w3.org/2000/svg';
  // pixel-art: ri('castle'), ri('map', 32)
  window.ri = (name, size = 16, cls = '') => {
    const s = document.createElement('span');
    s.className = `ri ri-${name}${size !== 16 ? ' ri-' + size : ''} ${cls}`.trim();
    s.setAttribute('aria-hidden', 'true');
    return s;
  };
  // traço: ui('trash')
  window.ui = (name, cls = 'size-4') => {
    const svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('class', 'ui ' + cls); svg.setAttribute('aria-hidden', 'true');
    for (const [k, v] of Object.entries({ fill: 'none', stroke: 'currentColor', 'stroke-width': 2, 'stroke-linecap': 'round', 'stroke-linejoin': 'round' })) svg.setAttribute(k, v);
    const use = document.createElementNS(NS, 'use'); use.setAttribute('href', `${SVG}#${name}`);
    svg.append(use); return svg;
  };
  // valor de campo: emoji da pessoa ou "ri:<nome>"
  window.glyph = (v, size = 16, cls = '') => {
    v = v || '';
    if (v.startsWith('ri:')) return ri(v.slice(3), size, cls);
    if (v.startsWith('img:')) {
      const i = document.createElement('img'); i.src = v.slice(4); i.alt = ''; i.loading = 'lazy';
      i.className = 'inline-block shrink-0 rounded-[22%] object-cover align-middle ' + cls;
      i.style.width = i.style.height = size + 'px'; return i;
    }
    const s = document.createElement('span'); s.className = cls; s.textContent = v; return s;
  };
  window.glyphText = v => /^(ri|img):/.test(v || '') ? '' : (v || '');
  // botão/label com ícone + texto: iconLabel(ui('trash'), 'Apagar')
  window.iconLabel = (icon, text) => {
    const f = document.createDocumentFragment(); f.append(icon);
    if (text) { const t = document.createElement('span'); t.textContent = text; f.append(t); }
    return f;
  };
})();

// Seletor de ícone (templates/_icon_picker.html)
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.icon-picker').forEach(root => {
    const hidden = root.querySelector('input[name=icon]'), file = root.querySelector('input[name=icon_file]');
    const pop = root.querySelector('.ip-pop'), preview = root.querySelector('.ip-preview'), emoji = root.querySelector('.ip-emoji');
    const size = Number(root.dataset.size) || 48;
    const show = () => preview.replaceChildren(glyph(hidden.value || root.dataset.default, size));
    root.refresh = show;   // usado quando o padrão muda (ex.: categoria da página)
    const set = v => { hidden.value = v; file.value = ''; show(); };
    root.querySelector('.ip-trigger').addEventListener('click', () => pop.classList.toggle('hidden'));
    root.querySelectorAll('[data-ip]').forEach(b => b.addEventListener('click', () => { set(b.dataset.ip); emoji.value = ''; pop.classList.add('hidden'); }));
    emoji.addEventListener('input', () => { set(emoji.value.trim()); });
    root.querySelector('.ip-upload').addEventListener('click', () => file.click());
    file.addEventListener('change', () => {
      const f = file.files[0]; if (!f) return;
      hidden.value = '';
      const i = glyph('img:' + URL.createObjectURL(f), size); preview.replaceChildren(i);
      pop.classList.add('hidden');
    });
    document.addEventListener('click', e => { if (!root.contains(e.target)) pop.classList.add('hidden'); });
    root.addEventListener('keydown', e => { if (e.key === 'Escape' && !pop.classList.contains('hidden')) { e.stopPropagation(); pop.classList.add('hidden'); root.querySelector('.ip-trigger').focus(); } });
  });
});
