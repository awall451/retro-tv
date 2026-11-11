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
  {
    id: 'digital', label: 'Digital Cable', splash: 'digital', color: '#000814',
    help: 'A 2000s digital cable box: black and deep blue, glossy rounded bars, a light-blue highlight that glows.',
  },
  {
    id: 'satellite', label: 'Satellite', splash: 'satellite', color: '#1a0d4a',
    help: 'An early-2000s satellite receiver: navy into purple, rounded tabs, a gold highlight. The splash is a dish in orbit.',
  },
  {
    id: 'dvr', label: 'DVR', splash: 'dvr', color: '#173a80',
    help: 'A hard-disk recorder from around 2000: soft blues, rounded white pills, a green highlight and a friendly little TV.',
  },
  {
    id: 'mediacenter', label: 'Media Center', splash: 'mediacenter', color: '#08356a',
    help: 'A 2005 living-room PC: glassy blue, see-through tiles, a green glowing highlight, a thin face.',
  },
  {
    id: 'aqua', label: 'Aqua', splash: 'aqua', color: '#e3e7ec',
    help: 'The Y2K desktop: light pinstripes, white rounded cells, brushed-metal tabs and a blue gel highlight.',
  },
  {
    id: 'settop', label: 'Set-Top Web', splash: 'settop', color: '#12082a',
    help: 'A late-90s internet box on the TV: purple and black, chunky bevelled buttons, everything in capitals.',
  },
  {
    // The id is still "listings" (the theme this one replaced), so a device
    // that had it chosen, and the box's boot splash files, carry over.
    id: 'listings', label: 'TV Guide', splash: 'listings', color: '#000030',
    help: 'The scrolling TV Guide Channel of the late 90s, as on channel 1: dark blue boxes in 3-D frames, yellow channels and times, grey listings in the Amiga font.',
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
