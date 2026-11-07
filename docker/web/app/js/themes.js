// Themes: a named look for the whole viewer. A theme is a set of color and
// font tokens in css/guide.css (the [data-theme=...] blocks) plus the splash
// scene drawn while the guide loads (splash.js). The choice is a per-device
// setting (settings.js); js/theme-boot.js puts the saved one on <html>
// before the first paint.

export const THEMES = [
  {
    id: 'cable', label: 'Cable', splash: 'cable', color: '#0a1240',
    help: 'The late-90s cable guide: navy and yellow, flat cells. The splash is the little television.',
  },
  {
    id: 'vapor', label: 'Vaporwave', splash: 'vapor', color: '#1a0b3f',
    help: 'Purple cells, pink highlights, cyan text. The splash is a sunset over a neon grid.',
  },
];

export function themeById(id) {
  return THEMES.find(t => t.id === id) || THEMES[0];
}

// Put the theme on <html> (the CSS keys off data-theme) and tint the
// browser's own chrome to match.
export function applyTheme(id) {
  const t = themeById(id);
  document.documentElement.dataset.theme = t.id;
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.content = t.color;
  // On the Pi box, tell it the choice so its boot splash can match (its web
  // server has /pi/theme, see pi-image/). Anywhere else this answers 404 and
  // is ignored.
  try {
    fetch('/pi/theme', { method: 'POST', body: t.id, keepalive: true }).catch(() => {});
  } catch { /* no fetch: nothing to tell */ }
  return t;
}
