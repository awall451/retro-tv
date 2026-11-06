// Viewer settings. They belong to the browser they were set in (kept in
// its localStorage), so a phone, a laptop and a TV can each have their own.

const KEY = 'retro-tv.settings';

// id, label, the choices as [value, label, what it means], and the default.
export const SETTINGS = [
  {
    // Only offered when the server has HD twins (see data.js).
    id: 'quality', label: 'Quality', default: 'sd',
    options: [
      ['sd', 'Standard', 'The 4:3 picture made for the old TV. Lightest on the connection.'],
      ['hd', 'HD', 'The same channels in widescreen 1080p, for modern screens. Needs a faster connection.'],
    ],
  },
  {
    id: 'picture', label: 'Picture', default: 'fit',
    options: [
      ['fit', 'Original', 'The whole 4:3 picture, as on the TV. Widescreen shows have black bars.'],
      ['fill', 'Fill the screen', 'Zooms in while watching to hide the black bars around widescreen shows. For wide monitors.'],
    ],
  },
  {
    id: 'warm', label: 'Fast flipping', default: 'on',
    options: [
      ['on', 'On', 'While you flip channels, the next one is started ahead of time, so it appears at once.'],
      ['off', 'Off', 'A channel is only started when you tune to it. Easier on the server, slower to flip.'],
    ],
  },
];

let values = null;

function load() {
  values = {};
  let stored = {};
  try { stored = JSON.parse(localStorage.getItem(KEY)) || {}; } catch { /* unreadable: use defaults */ }
  for (const s of SETTINGS) {
    values[s.id] = s.options.some(o => o[0] === stored[s.id]) ? stored[s.id] : s.default;
  }
}

export function getSetting(id) {
  if (!values) load();
  return values[id];
}

// Move a setting to its next (or previous) choice and remember it.
export function cycleSetting(id, step = 1) {
  if (!values) load();
  const s = SETTINGS.find(x => x.id === id);
  const at = s.options.findIndex(o => o[0] === values[id]);
  values[id] = s.options[((at + step) % s.options.length + s.options.length) % s.options.length][0];
  try { localStorage.setItem(KEY, JSON.stringify(values)); } catch { /* private mode */ }
  return values[id];
}
