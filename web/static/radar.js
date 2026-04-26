/**
 * ALEV v2 — Radar Grafiği Bileşeni
 * Bağımlılık yok, saf SVG/Canvas ile çizilir.
 * Kullanım: new RadarChart(container, data, options)
 */

class RadarChart {
  constructor(container, data, options = {}) {
    this.container = typeof container === 'string'
      ? document.querySelector(container) : container;
    this.data = data;   // [{label, value, max, emoji, key}]
    this.opts = {
      size: options.size || 280,
      levels: options.levels || 5,
      color: options.color || '#D85A30',
      fillOpacity: options.fillOpacity || 0.25,
      animated: options.animated !== false,
      showValues: options.showValues !== false,
      darkMode: options.darkMode || window.matchMedia('(prefers-color-scheme: dark)').matches,
      ...options
    };
    this.render();
  }

  render() {
    const { size, levels, color, fillOpacity, darkMode, animated } = this.opts;
    const cx = size / 2, cy = size / 2, r = size * 0.38;
    const n = this.data.length;
    const angleStep = (2 * Math.PI) / n;
    const textColor = darkMode ? '#c2c0b6' : '#3d3d3a';
    const gridColor = darkMode ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.07)';
    const strokeColor = color;

    // Açı hesapla (üstten başlayarak)
    const angle = (i) => -Math.PI / 2 + i * angleStep;
    const point = (i, ratio) => ({
      x: cx + r * ratio * Math.cos(angle(i)),
      y: cy + r * ratio * Math.sin(angle(i))
    });

    // SVG oluştur
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('width', size);
    svg.setAttribute('height', size);
    svg.setAttribute('viewBox', `0 0 ${size} ${size}`);

    // Grid çizgileri
    for (let l = 1; l <= levels; l++) {
      const ratio = l / levels;
      const pts = Array.from({length: n}, (_, i) => {
        const p = point(i, ratio);
        return `${p.x},${p.y}`;
      }).join(' ');
      const poly = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
      poly.setAttribute('points', pts);
      poly.setAttribute('fill', 'none');
      poly.setAttribute('stroke', gridColor);
      poly.setAttribute('stroke-width', '0.5');
      svg.appendChild(poly);
    }

    // Eksen çizgileri
    for (let i = 0; i < n; i++) {
      const p = point(i, 1);
      const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      line.setAttribute('x1', cx); line.setAttribute('y1', cy);
      line.setAttribute('x2', p.x); line.setAttribute('y2', p.y);
      line.setAttribute('stroke', gridColor); line.setAttribute('stroke-width', '0.5');
      svg.appendChild(line);
    }

    // Veri poligonu
    const dataRatios = this.data.map(d => d.value / (d.max || 20));
    const dataPoints = dataRatios.map((ratio, i) => {
      const p = point(i, ratio);
      return `${p.x},${p.y}`;
    }).join(' ');

    const dataPoly = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
    dataPoly.setAttribute('points', dataPoints);
    dataPoly.setAttribute('fill', color);
    dataPoly.setAttribute('fill-opacity', fillOpacity);
    dataPoly.setAttribute('stroke', color);
    dataPoly.setAttribute('stroke-width', '1.5');
    dataPoly.setAttribute('stroke-linejoin', 'round');

    if (animated) {
      dataPoly.style.transition = 'all 0.6s ease';
    }
    svg.appendChild(dataPoly);

    // Veri noktaları
    dataRatios.forEach((ratio, i) => {
      const p = point(i, ratio);
      const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      circle.setAttribute('cx', p.x); circle.setAttribute('cy', p.y);
      circle.setAttribute('r', '3');
      circle.setAttribute('fill', color);
      svg.appendChild(circle);
    });

    // Etiketler
    this.data.forEach((d, i) => {
      const labelRatio = 1.22;
      const p = point(i, labelRatio);
      const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');

      // Emoji
      const emoji = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      emoji.setAttribute('x', p.x);
      emoji.setAttribute('y', p.y - 8);
      emoji.setAttribute('text-anchor', 'middle');
      emoji.setAttribute('dominant-baseline', 'central');
      emoji.setAttribute('font-size', '14');
      emoji.textContent = d.emoji || '';
      g.appendChild(emoji);

      // Label
      const label = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      label.setAttribute('x', p.x);
      label.setAttribute('y', p.y + 8);
      label.setAttribute('text-anchor', 'middle');
      label.setAttribute('dominant-baseline', 'central');
      label.setAttribute('font-size', '10');
      label.setAttribute('fill', textColor);
      label.textContent = d.label;
      g.appendChild(label);

      // Değer
      if (this.opts.showValues) {
        const val = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        val.setAttribute('x', p.x);
        val.setAttribute('y', p.y + 20);
        val.setAttribute('text-anchor', 'middle');
        val.setAttribute('font-size', '10');
        val.setAttribute('fill', color);
        val.setAttribute('font-weight', '600');
        val.textContent = `${d.value}/${d.max}`;
        g.appendChild(val);
      }
      svg.appendChild(g);
    });

    this.container.innerHTML = '';
    this.container.appendChild(svg);
  }

  update(newData) {
    this.data = newData;
    this.render();
  }
}

// Global erişim için
if (typeof window !== 'undefined') window.RadarChart = RadarChart;
if (typeof module !== 'undefined') module.exports = RadarChart;
