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
    const s = document.createElement('span'); s.className = cls; s.textContent = v; return s;
  };
  window.glyphText = v => (v || '').startsWith('ri:') ? '' : (v || '');
  // botão/label com ícone + texto: iconLabel(ui('trash'), 'Apagar')
  window.iconLabel = (icon, text) => {
    const f = document.createDocumentFragment(); f.append(icon);
    if (text) { const t = document.createElement('span'); t.textContent = text; f.append(t); }
    return f;
  };
})();
