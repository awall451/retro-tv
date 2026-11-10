// The TV Guide Channel page: the late-1990s scrolling listings, drawn from
// the same channel list and XMLTV as the guide viewer (data.js). The grid
// shows a 90-minute window in half-hour columns and scrolls through every
// channel, top to bottom, round and round, while a clock with seconds ticks
// in the corner. The top half is for promos (a later step); it is black
// until then.
//
//   tvguide.html            the page, scaled to fit the window
//   tvguide.html?tv         the same, meant for a TV: no pointer, 640x480 scaled to the screen
//   …&screen=4:3            the screen shows the window as 4:3 whatever its pixel
//                           count (the Pi's composite output): stretch to match

import { HALF_HOUR, loadGuide } from './data.js';

const params = new URLSearchParams(location.search);
const SCREEN_SHAPE = (() => {
  const m = /^(\d+):(\d+)$/.exec(params.get('screen') || '');
  return m && +m[2] ? +m[1] / +m[2] : 0;
})();

const W = 640, H = 480;
const COLUMNS = 3;                         // half hours across
const WINDOW = COLUMNS * HALF_HOUR;
const ROW_H = 61;                          // matches --row-h in tvguide.css
const ROW_SECONDS = 2.6;                   // one channel row scrolls past in this time
const REFRESH_MS = 10 * 60 * 1000;         // listings re-read this often

const $ = id => document.getElementById(id);
const el = { stage: $('stage'), clock: $('clock'), times: $('times'), rows: $('rows'), viewport: $('viewport'), grid: $('grid') };

let guide = null;            // { channels, … } from loadGuide
let windowStart = 0;         // the first column's time
let cycleHeight = 0;         // height of one pass through all channels
let offset = 0;              // current scroll position in px
let lastFrame = 0;

// ---- Fitting the 640x480 page to the screen ------------------------------------

function fit() {
  let vw = window.innerWidth;
  const vh = window.innerHeight;
  const stretch = SCREEN_SHAPE ? (vw / vh) / SCREEN_SHAPE : 1;
  vw /= stretch;
  const scale = Math.min(vw / W, vh / H);
  const ox = (vw - W * scale) / 2 * stretch, oy = (vh - H * scale) / 2;
  el.stage.style.transform = `translate(${ox}px, ${oy}px) scale(${(scale * stretch).toFixed(5)}, ${scale.toFixed(5)})`;
}

// ---- Text --------------------------------------------------------------------------

const pad = n => String(n).padStart(2, '0');
const hour12 = d => (d.getHours() % 12) || 12;

function clockText(d) {
  return `${hour12(d)}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

function columnText(t) {
  const d = new Date(t);
  return `${hour12(d)}:${pad(d.getMinutes())} ${d.getHours() < 12 ? 'AM' : 'PM'}`;
}

function startText(t) {
  const d = new Date(t);
  return `(${hour12(d)}:${pad(d.getMinutes())})`;
}

// Channel names become the short call-sign style label of the time: upper
// case, at most seven characters. Articles go first; then the first real
// word if it is a word on its own ("Cartoon Network" -> "CARTOON", "The
// Family Channel" -> "FAMILY"), squeezed of its inner vowels when too long
// ("Midnight Movies" -> "MDNGHT"); a short first word keeps the second
// ("80s Action" -> "80S ACT").
function callSign(name) {
  const s = name.toUpperCase().replace(/[^A-Z0-9 ]/g, '').replace(/\s+/g, ' ').trim();
  if (s.length <= 7) return s;
  const words = s.split(' ').filter(w => !/^(THE|A|AN|OF|AND)$/.test(w));
  if (!words.length) return s.slice(0, 7);
  const squeeze = w => (w.length <= 7 ? w : (w[0] + w.slice(1).replace(/[AEIOU]/g, '')).slice(0, 7));
  if (words.length === 1 || words[0].length >= 5) return squeeze(words[0]);
  return `${words[0]} ${squeeze(words[1])}`.slice(0, 7).trim();
}

function escapeHtml(s) {
  return s.replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
}

// What a cell says: movies in quotes with their rating and year, as the
// channel printed them; shows by title; a start time in brackets when the
// programme does not begin on the half hour.
function cellHtml(cell, from, to) {
  const p = cell.items[0];
  const parts = [];
  if (cell.start < from) parts.push('<span class="arrow left">&#9668;</span>');
  if (cell.start > from && cell.start % HALF_HOUR !== 0) parts.push(`<span class="at">${startText(cell.start)}</span> `);
  if (p && p.movie) {
    parts.push(`&ldquo;${escapeHtml(cell.title)}&rdquo;`);
    if (p.rating) parts.push(`<span class="rating">${escapeHtml(p.rating)}</span>`);
    if (p.year) parts.push(` <span class="year">(${p.year})</span>`);
  } else {
    parts.push(escapeHtml(cell.title));
  }
  let html = `<div class="text">${parts.join('')}</div>`;
  if (cell.stop > to) html += '<span class="arrow right">&#9658;&#9658;</span>';
  return html;
}

// ---- Building the grid -----------------------------------------------------------

function renderHeader() {
  const frag = document.createDocumentFragment();
  for (let i = 0; i < COLUMNS; i++) {
    const d = document.createElement('div');
    d.className = 'cell head';
    d.textContent = columnText(windowStart + i * HALF_HOUR);
    frag.append(d);
  }
  el.times.replaceChildren(frag);
}

function renderRow(ch, index) {
  const row = document.createElement('div');
  row.className = 'row' + (index % 2 ? ' alt' : '');
  const chan = document.createElement('div');
  chan.className = 'chan';
  chan.innerHTML = `<span class="num">${escapeHtml(ch.num)}</span><span class="name">${escapeHtml(callSign(ch.name))}</span>`;
  const progs = document.createElement('div');
  progs.className = 'progs';
  const from = windowStart, to = windowStart + WINDOW;
  let t = from;
  // Walk the window, cell by cell, filling holes with "No information".
  const cells = ch.cells.filter(c => c.stop > from && c.start < to);
  const covered = [];
  for (const c of cells) {
    if (c.start > t) covered.push({ gap: true, title: 'No information', items: [], start: t, stop: c.start });
    covered.push(c);
    t = c.stop;
  }
  if (t < to) covered.push({ gap: true, title: 'No information', items: [], start: t, stop: to });
  for (const c of covered) {
    const a = Math.max(c.start, from), b = Math.min(c.stop, to);
    if (b <= a) continue;
    const d = document.createElement('div');
    d.className = 'prog' + (c.gap ? ' gap' : '');
    d.style.left = `${((a - from) / WINDOW * 100).toFixed(3)}%`;
    d.style.width = `${((b - a) / WINDOW * 100).toFixed(3)}%`;
    d.innerHTML = cellHtml(c, from, to);
    progs.append(d);
  }
  row.append(chan, progs);
  return row;
}

function renderRows() {
  const frag = document.createDocumentFragment();
  const chans = guide.channels;
  chans.forEach((ch, i) => frag.append(renderRow(ch, i)));
  cycleHeight = chans.length * ROW_H;
  // A copy of the first rows after the last, so the wrap-around is seamless.
  const visible = Math.ceil(el.viewport.clientHeight / ROW_H) + 1;
  for (let i = 0; i < Math.min(visible, chans.length); i++) frag.append(renderRow(chans[i], chans.length + i));
  el.rows.replaceChildren(frag);
}

function message(text) {
  let m = $('msg');
  if (!text) { if (m) m.remove(); return; }
  if (!m) { m = document.createElement('div'); m.id = 'msg'; el.grid.append(m); }
  m.textContent = text;
}

function rebuild() {
  windowStart = Math.floor(Date.now() / HALF_HOUR) * HALF_HOUR;
  renderHeader();
  if (guide) renderRows();
}

// ---- Time ---------------------------------------------------------------------------

function tick() {
  const now = Date.now();
  el.clock.textContent = clockText(new Date(now));
  if (Math.floor(now / HALF_HOUR) * HALF_HOUR !== windowStart) rebuild();   // the half hour turned
}

function frame(ts) {
  if (lastFrame && cycleHeight) {
    offset += (ts - lastFrame) / 1000 * (ROW_H / ROW_SECONDS);
    if (offset >= cycleHeight) offset -= cycleHeight;
    el.rows.style.transform = `translateY(${(-Math.round(offset))}px)`;
  }
  lastFrame = ts;
  requestAnimationFrame(frame);
}

// ---- Data ---------------------------------------------------------------------------

async function refresh() {
  try {
    guide = await loadGuide();
    message('');
    rebuild();
  } catch (err) {
    if (!guide) message('Listings are not available right now.');
    console.warn('TV Guide: could not load the listings', err);
  }
}

// ---- Start --------------------------------------------------------------------------

fit();
window.addEventListener('resize', fit);
rebuild();
message('Loading listings…');
tick();
setInterval(tick, 250);
requestAnimationFrame(frame);
refresh();
setInterval(refresh, REFRESH_MS);
