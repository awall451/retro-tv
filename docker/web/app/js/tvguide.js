// The TV Guide Channel page: the late-1990s scrolling listings, drawn from
// the same channel list and XMLTV as the guide viewer (data.js). The grid
// shows a 90-minute window in half-hour columns and scrolls through every
// channel, top to bottom, round and round, while a clock with seconds ticks
// in the corner. The top half plays a channel's live stream: the promos,
// commercials and infomercials the real channel ran up there come from a
// channel on the server, so they are curated like everything else and
// nothing is stored here. Without a promo channel the top half stays black.
//
//   tvguide.html            the page, scaled to fit the window
//   tvguide.html?tv         the same, meant for a TV: no pointer, 640x480 scaled to the screen
//   …&screen=4:3            the screen shows the window as 4:3 whatever its pixel
//                           count (the Pi's composite output): stretch to match
//   …&promo=<number>        the channel whose stream plays in the top half

import { HALF_HOUR, loadGuide } from './data.js';
import { Player } from './player.js';

const params = new URLSearchParams(location.search);
const SCREEN_SHAPE = (() => {
  const m = /^(\d+):(\d+)$/.exec(params.get('screen') || '');
  return m && +m[2] ? +m[1] / +m[2] : 0;
})();

const W = 640, H = 480;
const COLUMNS = 3;                         // half hours across
const WINDOW = COLUMNS * HALF_HOUR;
const ROW_H = 53;                          // matches --row-h in tvguide.css
const ROW_SECONDS = 2.0;                   // one channel row scrolls past in this time (the Amiga did a pixel a frame)
const REFRESH_MS = 10 * 60 * 1000;         // listings re-read this often

const PROMO = (params.get('promo') || '').trim();   // a channel number, or nothing

const CARD_SECONDS = 12;                   // a promo card stays this long
const FLIP_MINUTES = 4;                    // video and card swap sides this often
const CARD_HORIZON = 6 * HALF_HOUR;        // cards promote shows starting within three hours
const TOP_PAUSE_SECONDS = 4;               // the grid parks on the first channels at the top of every pass

const $ = id => document.getElementById(id);
const el = { stage: $('stage'), clock: $('clock'), times: $('times'), rows: $('rows'), viewport: $('viewport'), grid: $('grid'), top: $('top'), promo: $('promo'), card: $('card') };

let guide = null;            // { channels, … } from loadGuide
let windowStart = 0;         // the first column's time
let cycleHeight = 0;         // height of one pass through all channels
let offset = 0;              // current scroll position in px
let lastFrame = 0;
let pauseUntil = 0;          // while the grid is parked at the top of a pass (ms timestamp)

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
// The Amiga font keeps the rating badges as glyphs of its own; the browser's
// fallback font shows the abbreviation in a box instead (tvguide.css).
const RATING_GLYPH = {
  NR: '', G: '', PG: '', 'PG-13': '', 'NC-17': '', R: '',
  ADULT: '', 'TV-Y': '', 'TV-Y7': '', 'TV-G': '', 'TV-PG': '',
  'TV-14': '', 'TV-M': '', 'TV-MA': '',
};
const realFont = () => !document.body.classList.contains('fallback');

function ratingHtml(rating) {
  const key = rating.toUpperCase().replace(/\s+/g, '');
  const glyph = RATING_GLYPH[key];
  if (glyph && realFont()) return `<span class="rating">${glyph}</span>`;
  return `<span class="rating">${escapeHtml(rating.replace(/^TV-?/i, 'TV'))}</span>`;
}

function cellHtml(cell, from, to) {
  const p = cell.items[0];
  const parts = [];
  if (cell.start > from && cell.start % HALF_HOUR !== 0) parts.push(`${startText(cell.start)} `);
  if (p && p.movie) {
    parts.push(`&ldquo;${escapeHtml(cell.title)}&rdquo;`);
    if (p.rating) parts.push(ratingHtml(p.rating));
    if (p.year) parts.push(` (${p.year})`);
  } else {
    parts.push(escapeHtml(cell.title));
  }
  let html = `<div class="text">${parts.join('')}</div>`;
  if (cell.start < from) html += `<span class="arrow left${cell.start < from - HALF_HOUR ? ' double' : ''}"></span>`;
  if (cell.stop > to) html += `<span class="arrow right${cell.stop > to + HALF_HOUR ? ' double' : ''}"></span>`;
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
    if (c.start > t) covered.push({ gap: true, title: 'No Data', items: [], start: t, stop: c.start });
    covered.push(c);
    t = c.stop;
  }
  if (t < to) covered.push({ gap: true, title: 'No Data', items: [], start: t, stop: to });
  for (const c of covered) {
    const a = Math.max(c.start, from), b = Math.min(c.stop, to);
    if (b <= a) continue;
    const d = document.createElement('div');
    d.className = 'prog' + (c.gap ? ' gap' : '')
      + (c.start < from ? ' has-left' + (c.start < from - HALF_HOUR ? ' left-double' : '') : '')
      + (c.stop > to ? ' has-right' + (c.stop > to + HALF_HOUR ? ' right-double' : '') : '');
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
  if (lastFrame && cycleHeight && ts >= pauseUntil) {
    offset += (ts - lastFrame) / 1000 * (ROW_H / ROW_SECONDS);
    if (offset >= cycleHeight) {
      // Back at channel 1: park for a moment before rolling again.
      offset = 0;
      pauseUntil = ts + TOP_PAUSE_SECONDS * 1000;
    }
    el.rows.style.transform = `translateY(${(-Math.round(offset))}px)`;
  }
  lastFrame = ts;
  requestAnimationFrame(frame);
}

// ---- Data ---------------------------------------------------------------------------

async function refresh() {
  try {
    const first = !guide;
    guide = await loadGuide();
    message('');
    rebuild();
    cardQueue = [];                    // cards are rebuilt from the fresh listings
    if (first) {
      // The listings have just arrived: start at channel 1 and park there first.
      offset = 0;
      el.rows.style.transform = 'translateY(0px)';
      pauseUntil = performance.now() + TOP_PAUSE_SECONDS * 1000;
    }
  } catch (err) {
    if (!guide) message('Listings are not available right now.');
    console.warn('TV Guide: could not load the listings', err);
  }
}

// ---- The top half -----------------------------------------------------------------
// The promo channel plays through the viewer's own player (hls.js, padded
// against dips). The picture is shown once it is really playing; while the
// stream is tuning or down the top half is simply black, as the real
// channel's was between ads.

let promoPlayer = null;

function startPromo() {
  if (!PROMO || !/^\d+(\.\d+)?$/.test(PROMO)) return;
  promoPlayer = new Player(el.promo, {
    onState(state) { el.promo.classList.toggle('on', state === 'playing'); },
    onMuted(muted) {
      // A desktop browser refuses sound before the first key or click; the
      // TV's kiosk allows it. Either way the first input turns the sound on.
      if (!muted) return;
      const unmute = () => { promoPlayer.unmute(); window.removeEventListener('keydown', unmute); window.removeEventListener('pointerdown', unmute); };
      window.addEventListener('keydown', unmute);
      window.addEventListener('pointerdown', unmute);
    },
  });
  promoPlayer.tune({ num: PROMO, name: 'Promos' }, { stream: PROMO });
}

// ---- Promo cards ---------------------------------------------------------------------
// The text side of the top half: "coming up" cards built from the listings,
// the way the channel's text ads read: the channel, the show in quotes with
// its rating, when, and the channel number. A fresh card every CARD_SECONDS,
// drawn from what starts in the next few hours, movies first.

let cardQueue = [];

function whenText(t) {
  const d = new Date(t), now = new Date();
  const time = `${hour12(d)}:${pad(d.getMinutes())} ${d.getHours() < 12 ? 'AM' : 'PM'}`;
  if (d.toDateString() === now.toDateString()) return `${d.getHours() >= 17 ? 'Tonight' : 'Today'} ${time}`;
  const tomorrow = new Date(now); tomorrow.setDate(now.getDate() + 1);
  if (d.toDateString() === tomorrow.toDateString()) return `Tomorrow ${time}`;
  return `${d.toLocaleDateString(undefined, { weekday: 'long' })} ${time}`;
}

function buildCards() {
  if (!guide) return [];
  const now = Date.now(), cards = [];
  for (const ch of guide.channels) {
    for (const p of ch.progs) {
      if (p.start < now - HALF_HOUR || p.start > now + CARD_HORIZON) continue;
      if (p.stop - p.start < 20 * 60 * 1000) continue;            // not the shorts and bumpers
      cards.push({ ch, p, weight: p.movie ? 3 : 1 });
    }
  }
  // Weighted shuffle: movies come up about three times as often.
  for (const c of cards) c.key = -Math.log(Math.random()) / c.weight;
  return cards.sort((a, b) => a.key - b.key);
}

function showCard() {
  if (!guide) return;
  if (!cardQueue.length) cardQueue = buildCards();
  const c = cardQueue.shift();
  if (!c) { el.card.replaceChildren(); return; }
  const { ch, p } = c;
  const title = p.movie ? `&ldquo;${escapeHtml(p.title)}&rdquo;` : escapeHtml(p.title);
  const rating = p.rating ? ' ' + ratingHtml(p.rating) : '';
  const started = p.start <= Date.now();
  el.card.innerHTML =
    `<span class="line hi">${escapeHtml(ch.name.toUpperCase())}</span>` +
    `<span class="line title">${title}${rating}</span>` +
    `<span class="line hi">${started ? 'Now Showing' : escapeHtml(whenText(p.start))}</span>` +
    `<span class="line hi">Channel ${escapeHtml(ch.num)}</span>`;
}

function flipSides() {
  el.top.classList.toggle('flip');
}

// ---- Start --------------------------------------------------------------------------

// Is the Amiga font there? If not, the page styles itself for the fallback.
document.fonts.load('22px "PrevueGrid"').then(list => {
  const ok = list.length > 0 && document.fonts.check('22px "PrevueGrid"');
  document.body.classList.toggle('fallback', !ok);
  if (guide) renderRows();
}).catch(() => document.body.classList.add('fallback'));

fit();
window.addEventListener('resize', fit);
rebuild();
message('Loading listings…');
tick();
setInterval(tick, 250);
requestAnimationFrame(frame);
refresh().then(showCard);
setInterval(refresh, REFRESH_MS);
setInterval(showCard, CARD_SECONDS * 1000);
setInterval(flipSides, FLIP_MINUTES * 60 * 1000);
startPromo();
