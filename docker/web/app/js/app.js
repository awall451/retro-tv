// Retro TV guide viewer: the guide grid, the three screens (guide, full
// window, show details) and every way of steering them.
//
// One rule runs through all of it: there is a single <video>, playing the
// channel being watched. Browsing the guide never touches it.

import { HALF_HOUR, loadGuide, cellAt, programmeAt } from './data.js';
import { Player } from './player.js';
import { Warmer } from './warm.js';
import { BarWatcher } from './bars.js';
import { SETTINGS, getSetting, cycleSetting, setSetting } from './settings.js';
import { applyTheme, THEMES } from './themes.js';
import { showSplash, isSplashShowing } from './splash.js';

const $ = id => document.getElementById(id);
const el = {
  stage: $('stage'), previewFrame: $('previewFrame'), previewMsg: $('previewMsg'),
  info: $('info'), infoCh: $('infoCh'), infoTitle: $('infoTitle'), infoEp: $('infoEp'),
  infoTime: $('infoTime'), infoPlot: $('infoPlot'), infoPlotText: $('infoPlotText'),
  grid: $('grid'), clock: $('clock'), timebar: $('timebar'), chans: $('chans'), rows: $('rows'),
  nowTick: $('nowTick'), gridMsg: $('gridMsg'),
  details: $('details'), detPoster: $('detPoster'), detMeta: $('detMeta'), detText: $('detText'),
  detWatch: $('detWatch'), detBack: $('detBack'),
  cog: $('cog'), settings: $('settings'), setRows: $('setRows'), setHelp: $('setHelp'), setClose: $('setClose'),
  themePick: $('themePick'), tpGrid: $('tpGrid'), tpHelp: $('tpHelp'),
  screen: $('screen'), video: $('video'), tuning: $('tuning'),
  banner: $('banner'), banCh: $('banCh'), banClock: $('banClock'), banTitle: $('banTitle'),
  banEp: $('banEp'), banTime: $('banTime'), banFill: $('banFill'),
  banGuide: $('banGuide'), banDown: $('banDown'), banUp: $('banUp'), banMute: $('banMute'), banFull: $('banFull'),
  osd: $('osd'),
};

// ?tv forces the plain 640x480 layout, whatever the window's shape, and
// hides the pointer (the Pi box: a television, no mouse).
const TV_MODE = new URLSearchParams(location.search).has('tv');
document.body.classList.toggle('tv', TV_MODE);
const LAST_CHANNEL_KEY = 'retro-tv.last-channel';
const REFRESH_MS = 15 * 60 * 1000;       // re-read the listings this often
const HIDDEN_STOP_MS = 5 * 60 * 1000;    // stop streaming in a tab hidden this long
const BANNER_MS = 4000;
const SURF_MS = 30 * 1000;               // warm-up ends this long after the last flip
const SURF_SETTLE_MS = 900;              // start warming the next channel after this pause
const ROW = 29;                          // a 27 px row and its 2 px line
const NARROW = 30;                       // cells narrower than this get no label

const S = {
  channels: [],
  hasHd: false,                // the server has HD twins
  dataEnd: 0,
  loadedAt: 0,
  loading: false,
  mode: 'guide',               // 'guide' | 'full' | 'details' | 'settings' | 'themes'
  tpIndex: 0,                  // highlighted tile in the theme picker
  setRow: 0,                   // highlighted row on the settings screen
  focusCh: 0,                  // index into channels
  focusTime: Date.now(),       // the time position of the highlight
  winStart: floorHalf(Date.now()),
  rowTop: 0,                   // first channel row on screen
  tunedId: null,               // id of the channel being watched
  L: null,                     // current layout numbers
};

const clamp = (v, lo, hi) => Math.min(Math.max(v, lo), hi);
function floorHalf(t) { return Math.floor(t / HALF_HOUR) * HALF_HOUR; }

// ---- Time text ---------------------------------------------------------
// Listings carry their own UTC offset; everything is shown in the
// viewer's own time zone and clock style.

const timeFmt = new Intl.DateTimeFormat([], { hour: 'numeric', minute: '2-digit' });
const dayFmt = new Intl.DateTimeFormat([], { weekday: 'short' });
const fmtTime = t => timeFmt.format(t);
function fmtRange(a, b) {
  try { return timeFmt.formatRange(a, b); } catch { return `${fmtTime(a)} – ${fmtTime(b)}`; }
}

// ---- Layout --------------------------------------------------------------
// The guide is designed at 640x480. Wider windows get more time columns,
// taller ones more channel rows, upright phones a stacked version. The
// result is then scaled as one piece to fit the window.

function computeLayout() {
  const vw = window.innerWidth, vh = window.innerHeight, aspect = vw / vh;
  let W, H, portrait = false;
  if (TV_MODE) { W = 640; H = 480; }
  else if (aspect >= 4 / 3) { H = 480; W = Math.min(854, Math.round(H * aspect)); }
  else if (aspect >= 0.8) { W = 640; H = Math.min(800, Math.round(W / aspect)); }
  else { portrait = true; W = 360; H = clamp(Math.round(W / aspect), 560, 820); }

  const scale = Math.min(vw / W, vh / H);
  const L = { W, H, portrait, scale, ox: (vw - W * scale) / 2, oy: (vh - H * scale) / 2 };
  if (portrait) {
    L.pv = { x: 8, y: 8, w: 344, h: 259 };
    L.info = { x: 8, y: 272, w: 344, h: 152 };
    L.gridTop = 430; L.chanW = 100; L.slots = 2;
  } else {
    L.pv = { x: 8, y: 8, w: 256, h: 193 };
    L.info = { x: 274, y: 8, w: W - 282, h: 194 };
    L.gridTop = 210; L.chanW = 126; L.slots = Math.max(3, Math.round((W - 128) / 171));
  }
  L.timeX = L.chanW + 2;
  L.timeW = W - L.timeX;
  L.rows = Math.max(1, Math.floor((H - L.gridTop - ROW) / ROW));
  L.gridH = ROW * (L.rows + 1);
  L.span = L.slots * HALF_HOUR;

  // The picture's home when it fills the window: the largest box of the
  // stream's shape (4:3, or 16:9 for an HD stream).
  const shape = pictureShape();
  L.bw = Math.min(vw, vh * shape);
  L.bh = L.bw / shape;
  L.bx = (vw - L.bw) / 2;
  L.by = (vh - L.bh) / 2;
  L.u = L.bh / 480;
  L.vw = vw; L.vh = vh;

  // The channel bar and messages never grow past their design size with
  // the picture, so on a big screen they stay a slim strip. On a touch
  // screen they grow a little for fingers, as far as the window's width
  // allows, but never take over a short window (a phone held sideways).
  // The buttons' floor on touch is in the CSS.
  const finger = window.matchMedia('(pointer: coarse)').matches ? 1.25 : 1;
  L.b = Math.max(Math.min(L.u, 1), Math.min(finger, vw / 400, vh / 420));
  // Too narrow for programme, clock and buttons side by side: stack them.
  L.narrow = L.bw < 720 * L.b;
  return L;
}

function px(node, box) {
  for (const k in box) node.style[k] = `${box[k]}px`;
}

function applyLayout() {
  const L = S.L = computeLayout();
  const root = document.documentElement.style;
  root.setProperty('--u', `${L.u}px`);
  root.setProperty('--b', `${L.b}px`);
  px(el.stage, { width: L.W, height: L.H });
  el.stage.style.transform = `translate(${L.ox}px, ${L.oy}px) scale(${L.scale})`;
  px(el.previewFrame, { left: L.pv.x, top: L.pv.y, width: L.pv.w, height: L.pv.h });
  px(el.info, { left: L.info.x, top: L.info.y, width: L.info.w, height: L.info.h });
  px(el.grid, { top: L.gridTop, width: L.W, height: L.gridH });
  px(el.details, { top: L.gridTop });
  px(el.settings, { top: L.gridTop });
  px(el.themePick, { top: L.gridTop });
  px(el.cog, { left: L.info.x + L.info.w - 28, top: L.info.y - 3 });
  px(el.clock, { left: 0, top: 2, width: L.chanW });
  px(el.gridMsg, { top: 2 + ROW });

  px(el.screen, { left: L.bx, top: L.by, width: L.bw, height: L.bh });
  // The channel bar spans the picture and is locked to its bottom edge:
  // over the picture, or just under it when the window has room there.
  const margin = Math.min(24 * L.b, L.bw * 0.04);
  const below = L.vh - L.by - L.bh;
  const roomBelow = below >= (L.narrow ? 150 : 100) * L.b;
  el.banner.classList.toggle('narrow', L.narrow);
  px(el.banner, { left: L.bx, width: L.bw });
  el.banner.style.top = roomBelow ? `${L.by + L.bh}px` : 'auto';
  el.banner.style.bottom = roomBelow ? 'auto' : `${below}px`;
  fullLabel();
  px(el.osd, { top: L.by + margin, right: L.vw - L.bx - L.bw + margin });
  placeScreen(false);
}

// Put the picture in the corner box (guide, details) or its full-window
// home. Same element, moved with a transform so the stream never restarts.
function placeScreen(animate) {
  const L = S.L;
  el.screen.classList.toggle('anim', animate);
  if (S.mode === 'full') {
    el.screen.style.transform = 'translate(0px, 0px) scale(1)';
    return;
  }
  // Fit the picture inside the corner box, centered (an HD picture is
  // wider than the box and sits between black bars there).
  const iw = (L.pv.w - 4) * L.scale, ih = (L.pv.h - 4) * L.scale;
  const k = Math.min(iw / L.bw, ih / L.bh);
  const x = L.ox + (L.pv.x + 2) * L.scale + (iw - L.bw * k) / 2;
  const y = L.oy + (L.pv.y + 2) * L.scale + (ih - L.bh * k) / 2;
  el.screen.style.transform = `translate(${x - L.bx}px, ${y - L.by}px) scale(${k})`;
}

// ---- Standard or HD ----------------------------------------------------------
// With the HD setting on, the viewer asks for a channel's HD twin where
// it has one. Nothing else changes: same guide, names and numbers.

// If HD could not keep up on this connection (player.js reports it), the
// viewer drops to Standard for a while, then tries HD again on the next tune.
const SLOW_SD_MS = 10 * 60 * 1000;
let sdUntil = 0;
const slowNow = () => Date.now() < sdUntil;
const wantHd = () => S.hasHd && getSetting('quality') === 'hd' && !slowNow();
const streamOf = ch => ({ num: wantHd() && ch.hd ? ch.hd : ch.num, hd: wantHd() && !!ch.hd });
function pictureShape() {
  const ch = S.channels.find(c => c.id === S.tunedId);
  return ch && wantHd() && ch.hd ? 16 / 9 : 4 / 3;
}
const shownSettings = () => SETTINGS.filter(s => s.id !== 'quality' || S.hasHd);

// ---- Where the highlight and the time window may be ----------------------

const minWin = () => floorHalf(Date.now());
function maxWin() {
  return Math.max(minWin(), floorHalf(S.dataEnd - 1) - (S.L.slots - 1) * HALF_HOUR);
}

function clampState() {
  const n = S.channels.length;
  if (!n) return;
  S.winStart = clamp(S.winStart, minWin(), maxWin());
  S.focusTime = clamp(S.focusTime, S.winStart, S.winStart + S.L.span - 1);
  S.focusCh = clamp(S.focusCh, 0, n - 1);
  if (S.focusCh < S.rowTop) S.rowTop = S.focusCh;
  if (S.focusCh >= S.rowTop + S.L.rows) S.rowTop = S.focusCh - S.L.rows + 1;
  S.rowTop = clamp(S.rowTop, 0, Math.max(0, n - S.L.rows));
}

const focusChannel = () => S.channels[S.focusCh];
const focusCell = () => cellAt(focusChannel(), S.focusTime);
const tunedChannel = () => S.channels.find(c => c.id === S.tunedId) || null;

// ---- Drawing the guide ---------------------------------------------------

function cellNode(cls, text, left, top, width) {
  const node = document.createElement('div');
  node.className = `cell ${cls}`;
  node.textContent = text;
  px(node, { left, top, width });
  return node;
}

function cellLabel(cell) {
  return cell.items.length > 1 ? `${cell.title} · ${cell.items.length} shorts` : cell.title;
}

function renderGrid() {
  const L = S.L, t0 = S.winStart, t1 = t0 + L.span, now = Date.now();
  const x = t => L.timeX + Math.round((t - t0) / L.span * L.timeW);

  el.clock.textContent = `${dayFmt.format(now)} ${fmtTime(now)}`;

  const bar = document.createDocumentFragment();
  for (let i = 0; i < L.slots; i++) {
    const a = t0 + i * HALF_HOUR, left = x(a), right = x(a + HALF_HOUR);
    bar.append(cellNode('slot', fmtTime(a), left, 2, right - left - (i < L.slots - 1 ? 2 : 0)));
  }
  el.timebar.replaceChildren(bar);

  const chans = document.createDocumentFragment(), rows = document.createDocumentFragment();
  for (let r = 0; r < L.rows; r++) {
    const ci = S.rowTop + r, ch = S.channels[ci];
    if (!ch) break;
    const y = 2 + ROW * (r + 1), focused = ci === S.focusCh;
    const name = cellNode('chan', `${ch.num} ${ch.name}`, 0, y, L.chanW);
    name.dataset.ci = ci;
    name.classList.toggle('sel', focused);
    name.classList.toggle('playing', ch.id === S.tunedId);
    chans.append(name);

    for (let t = t0; t < t1;) {
      const cell = cellAt(ch, t);
      const start = Math.max(cell.start, t0), stop = Math.min(cell.stop, t1);
      const left = x(start), width = x(stop) - left - (stop < t1 ? 2 : 0);
      if (width >= 2) {
        const node = cellNode('show', cellLabel(cell), left, y, width);
        node.dataset.ci = ci;
        node.dataset.t = start;
        node.classList.toggle('none', !!cell.gap);
        node.classList.toggle('narrow', width < NARROW);
        node.classList.toggle('sel', focused && S.focusTime >= cell.start && S.focusTime < cell.stop);
        rows.append(node);
      }
      if (!(stop > t)) break;
      t = stop;
    }
  }
  el.chans.replaceChildren(chans);
  el.rows.replaceChildren(rows);

  const tick = now >= t0 && now < t1;
  el.nowTick.hidden = !tick;
  if (tick) px(el.nowTick, { left: Math.min(x(now), L.W - 2), top: 2 });
}

// Lines for the panel beside the picture, for one grid cell.
function describe(cell) {
  const one = cell.items.length === 1 ? cell.items[0] : null;
  const rating = (one || cell.items[0] || {}).rating;
  let ep = '', plot = '';
  if (one) {
    ep = one.sub ? `"${one.sub}"` : (one.movie && one.year ? one.year : '');
    plot = one.desc;
  } else if (cell.items.length) {
    ep = `${cell.items.length} shorts`;
    plot = cell.items.map(p => p.sub || p.title).join(' · ');
  }
  const timed = Number.isFinite(cell.start) && Number.isFinite(cell.stop);
  const time = timed ? fmtRange(cell.start, cell.stop) + (rating ? ` · ${rating}` : '') : '';
  return { title: cell.title, ep, time, plot };
}

function renderInfo() {
  const ch = focusChannel();
  if (!ch) return;
  const d = describe(focusCell());
  el.infoCh.textContent = `Ch ${ch.num} · ${ch.name}`;
  el.infoTitle.textContent = d.title;
  el.infoEp.textContent = d.ep;
  el.infoTime.textContent = d.time;
  // The details screen shows the full description below, so not here too.
  el.infoPlotText.textContent = S.mode === 'details' ? '' : d.plot;
  // Show only whole lines of the description.
  const lines = Math.max(1, Math.floor(el.infoPlot.clientHeight / 18));
  el.infoPlotText.style.setProperty('--lines', lines);
}

function render() {
  if (!S.channels.length) return;
  clampState();
  renderGrid();
  renderInfo();
  if (S.mode === 'details') fillDetails();
}

// ---- Show details ---------------------------------------------------------

function fillDetails() {
  const cell = focusCell();
  const one = cell.items.length === 1 ? cell.items[0] : null;
  const first = cell.items[0];
  const meta = [];
  if (one) {
    const genres = one.cats.filter(c => c !== 'Series' && c !== 'Movie').slice(0, 3).join(', ');
    meta.push(one.ep, one.year, one.rating, genres);
  } else if (first) {
    meta.push(`${cell.items.length} shorts`, first.rating);
  }
  el.detMeta.textContent = meta.filter(Boolean).join(' · ');

  if (one) {
    el.detText.textContent = one.desc || 'No description.';
  } else {
    const body = document.createDocumentFragment();
    for (const p of cell.items) {
      const head = document.createElement('b');
      head.textContent = `${fmtTime(p.start)}  ${p.sub || p.title}`;
      body.append(head, `\n${p.desc || ''}\n\n`);
    }
    el.detText.replaceChildren(body);
  }

  const poster = first && first.poster;
  el.detPoster.hidden = !poster;
  if (poster && el.detPoster.getAttribute('src') !== poster) el.detPoster.src = poster;
}

function openDetails() {
  if (!S.channels.length || focusCell().gap) return;
  S.mode = 'details';
  el.details.hidden = false;
  el.detText.scrollTop = 0;
  render();
}

function closeDetails() {
  S.mode = 'guide';
  el.details.hidden = true;
  render();
}

// ---- Watching -------------------------------------------------------------

const SOUND_HINT = 'Sound is off: press a key or click';
let autoMuted = false;

const player = new Player(el.video, {
  onState(state, ch) {
    const text = {
      tuning: ch && `Tuning to ${ch.num} ${ch.name}…`,
      error: 'Channel unavailable, retrying…',
      unsupported: 'This browser cannot play the channels',
    }[state];
    el.tuning.hidden = !text;
    el.tuning.textContent = text || '';
  },
  // The browser refused sound before the first key press or click.
  onMuted(muted) {
    autoMuted = muted;
    el.banMute.textContent = muted ? 'Unmute' : 'Mute';
    if (muted) showOsd(SOUND_HINT, 0);
    else hideOsd();
  },
  // HD cannot keep up on this connection: switch to Standard for a while.
  onSlow(ch) {
    if (!ch || ch !== player.channel) return;
    sdUntil = Date.now() + SLOW_SD_MS;
    stopSurf();
    bars.reset();
    applyLayout();
    player.tune(ch, { warm: true, stream: ch.num });
    showOsd('Slow connection: switched to Standard', 5000);
  },
});

// ?debug: expose the player, to read its padding and speed from the console.
if (new URLSearchParams(location.search).has('debug')) window.rtvPlayer = player;

// A real key press or click is what browsers want before they allow sound.
function wake() {
  if (autoMuted) player.unmute();
}

function setMode(mode) {
  S.mode = mode;
  document.body.classList.toggle('full', mode === 'full');
  document.body.classList.toggle('settings', mode === 'settings' || mode === 'themes');
  el.details.hidden = mode !== 'details';
  el.settings.hidden = mode !== 'settings';
  el.themePick.hidden = mode !== 'themes';
  if (mode !== 'full') hideBanner();
  placeScreen(true);
  syncZoom();
  render();
}

// "Fill the screen": while watching, zoom the picture until the black
// bars it carries are off the screen. A true 4:3 show has no bars and is
// left alone. Never in the corner box, where the whole frame is shown.
const bars = new BarWatcher(el.video, applyZoom);

function applyZoom() {
  const L = S.L, b = bars.bars;
  let zoom = 1;
  if (S.mode === 'full' && getSetting('picture') === 'fill' && (b.x || b.y)) {
    const w = L.bw * (1 - 2 * b.x), h = L.bh * (1 - 2 * b.y);
    zoom = clamp(Math.min(L.vw / w, L.vh / h), 1, 2.5);
  }
  el.video.style.transform = `scale(${zoom.toFixed(4)})`;
}

function syncZoom() {
  if (S.mode === 'full' && getSetting('picture') === 'fill') bars.start();
  else bars.stop();
  applyZoom();
}

// ---- Settings screen ----------------------------------------------------------

function renderSettings() {
  const rows = document.createDocumentFragment();
  shownSettings().forEach((s, i) => {
    const option = s.options.find(o => o[0] === getSetting(s.id));
    const label = document.createElement('div'), value = document.createElement('div');
    label.className = 'setLabel';
    label.textContent = s.label;
    value.className = 'setValue';
    value.textContent = option[1];
    label.dataset.row = value.dataset.row = i;
    if (i === S.setRow) { label.classList.add('sel'); value.classList.add('sel'); }
    rows.append(label, value);
  });
  el.setRows.replaceChildren(rows);
  const focused = shownSettings()[S.setRow];
  el.setHelp.textContent = focused.options.find(o => o[0] === getSetting(focused.id))[2];
  if (focused.id === 'theme') el.setHelp.textContent += ' Tap it to see them all.';
}

function openSettings() {
  S.setRow = 0;
  setMode('settings');
  renderSettings();
}

function changeSetting(step) {
  const id = shownSettings()[S.setRow].id;
  cycleSetting(id, step);
  if (id === 'theme') {
    // Reskin at once, and replay the new theme's splash so the change is seen.
    applyTheme(getSetting('theme'));
    showSplash(getSetting('theme'), { min: 2000 });
  }
  if (id === 'picture') syncZoom();
  if (id === 'quality') {
    sdUntil = 0;   // a choice made by hand ends any automatic drop to Standard
    // Switch the channel being watched to its other stream right away.
    const ch = tunedChannel();
    stopSurf();
    if (ch && player.channel) {
      bars.reset();
      applyLayout();
      const st = streamOf(ch);
      player.tune(ch, { stream: st.num, watchSlow: st.hd });
    }
  }
  if (id === 'warm' && getSetting('warm') !== 'on') stopSurf();
  renderSettings();
}

// The theme row opens the picker; left and right on it still step through
// the themes one at a time (quick on a remote).
function selectSetting() {
  if (shownSettings()[S.setRow].id === 'theme') return openThemes();
  changeSetting(1);
}

// ---- Theme picker ---------------------------------------------------------------
// Every theme as a tile with a live preview: the tile's preview carries the
// theme's own data-theme, so guide.css draws it in that theme's fills,
// radius, gloss and faces. Pick one to apply it (and see its splash).

const TP_COLS = 3;

function openThemes() {
  S.tpIndex = Math.max(0, THEMES.findIndex(t => t.id === getSetting('theme')));
  setMode('themes');
  renderThemes();
}

function renderThemes() {
  const current = getSetting('theme');
  const tiles = document.createDocumentFragment();
  THEMES.forEach((t, i) => {
    const tile = document.createElement('button');
    tile.type = 'button';
    tile.className = 'tp' + (i === S.tpIndex ? ' sel' : '');
    tile.dataset.tp = i;
    tile.setAttribute('aria-label', t.label + (t.id === current ? ' (in use)' : ''));
    tile.innerHTML = `<span class="tpPrev" data-theme="${t.id}"><span class="tpName"></span>`
      + '<span class="tpRow"><i class="k"></i><i class="s"></i><i class="s"></i></span>'
      + '<span class="tpRow"><i class="c"></i><i class="h"></i><i class="p"></i></span>'
      + '<span class="tpRow"><i class="c"></i><i class="p"></i><i class="p"></i></span>'
      + (t.id === current ? '<span class="tpUsing">In use</span>' : '') + '</span>';
    tile.querySelector('.tpName').textContent = t.label;
    tiles.append(tile);
  });
  el.tpGrid.replaceChildren(tiles);
  el.tpHelp.textContent = THEMES[S.tpIndex].help;
}

function moveTheme(delta) {
  const next = S.tpIndex + delta;
  if (next < 0 || next >= THEMES.length) return;
  S.tpIndex = next;
  renderThemes();
}

function pickTheme(i) {
  setSetting('theme', THEMES[i].id);
  applyTheme(getSetting('theme'));
  showSplash(getSetting('theme'), { min: 2000 });
  setMode('settings');
  renderSettings();
}

function moveSetting(delta) {
  S.setRow = clamp(S.setRow + delta, 0, shownSettings().length - 1);
  renderSettings();
}

// Warm-up for channel flipping. After a channel up/down, the next channel
// in the same direction is started on the server ahead of time, so the
// next flip lands on a running stream. It stops 30 s after the last flip:
// while simply watching, only the channel on screen is streamed.
const warmer = new Warmer();
let surfTimer = 0, surfSettleTimer = 0;

function surf(direction) {
  clearTimeout(surfTimer);
  clearTimeout(surfSettleTimer);
  if (getSetting('warm') !== 'on') return warmer.clear();
  surfSettleTimer = setTimeout(() => {
    const n = S.channels.length, at = S.channels.findIndex(c => c.id === S.tunedId);
    if (at < 0 || n < 3) return;
    warmer.set([streamOf(S.channels[((at + direction) % n + n) % n])]);
  }, SURF_SETTLE_MS);
  surfTimer = setTimeout(stopSurf, SURF_MS);
}

function stopSurf() {
  clearTimeout(surfTimer);
  clearTimeout(surfSettleTimer);
  warmer.clear();
}

function tune(ch, direction = 0) {
  S.tunedId = ch.id;
  try { localStorage.setItem(LAST_CHANNEL_KEY, ch.id); } catch { /* private mode */ }
  applyLayout();               // the picture's shape can change with the channel
  if (el.screen.hidden) {
    // First channel of the visit: start the picture in the corner box so
    // that going to the full window is a zoom from there.
    el.screen.hidden = false;
    placeScreen(false);
    void el.screen.offsetWidth;
  }
  el.previewMsg.hidden = true;
  const stream = streamOf(ch);
  const warm = warmer.isReady(stream);
  warmer.release(stream);
  bars.reset();
  player.tune(ch, { warm, stream: stream.num, watchSlow: stream.hd });
  if (direction) surf(direction);
  else stopSurf();
}

// Select: straight into the full window, tuning first if needed.
function watch(ch) {
  if (!ch) return;
  if (S.tunedId !== ch.id || player.state === 'idle' || player.state === 'error') tune(ch);
  setMode('full');
  showBanner();
}

// Channel up and down while watching.
function stepChannel(delta) {
  const n = S.channels.length;
  if (!n) return;
  const at = S.channels.findIndex(c => c.id === S.tunedId);
  const next = ((at < 0 ? S.focusCh : at + delta) % n + n) % n;
  S.focusCh = next;
  tune(S.channels[next], delta);
  render();
  showBanner();
}

// Back to the guide, highlight on what is playing now.
function openGuide() {
  const at = S.channels.findIndex(c => c.id === S.tunedId);
  if (at >= 0) {
    S.focusCh = at;
    S.focusTime = Date.now();
    S.winStart = minWin();
  }
  setMode('guide');
}

let bannerTimer = 0;
function fillBanner() {
  const ch = tunedChannel();
  if (!ch) return;
  const now = Date.now(), p = programmeAt(ch, now);
  el.banCh.textContent = `Ch ${ch.num} · ${ch.name}`;
  el.banClock.textContent = fmtTime(now);
  el.banTitle.textContent = p ? p.title : 'No information';
  el.banEp.textContent = p ? (p.sub ? `"${p.sub}"` : (p.movie && p.year ? p.year : '')) : '';
  el.banTime.textContent = p ? fmtRange(p.start, p.stop) + (p.rating ? ` · ${p.rating}` : '') : '';
  el.banFill.style.width = p ? `${clamp((now - p.start) / (p.stop - p.start), 0, 1) * 100}%` : '0';
}
function showBanner() {
  if (S.mode !== 'full' || !tunedChannel()) return;
  fillBanner();
  el.banner.hidden = false;
  clearTimeout(bannerTimer);
  bannerTimer = setTimeout(hideBanner, BANNER_MS);
}
function hideBanner() {
  clearTimeout(bannerTimer);
  el.banner.hidden = true;
}

let osdTimer = 0;
function showOsd(text, ms) {
  el.osd.textContent = text;
  el.osd.hidden = false;
  clearTimeout(osdTimer);
  if (ms) osdTimer = setTimeout(hideOsd, ms);
}
function hideOsd() {
  clearTimeout(osdTimer);
  el.osd.hidden = true;
  if (autoMuted && player.channel) showOsd(SOUND_HINT, 0);
}

function toggleMute() {
  if (el.video.muted) {
    el.video.muted = false;
    autoMuted = false;
    el.banMute.textContent = 'Mute';
    return showOsd('Sound is on', 1500);
  }
  el.video.muted = true;
  el.banMute.textContent = 'Unmute';
  showOsd('Sound is off', 1500);
}

// Browser full screen. On a phone or tablet it also turns the screen on
// its side, where the picture is biggest.
const inFullscreen = () => !!(document.fullscreenElement || document.webkitFullscreenElement);

async function toggleFullscreen() {
  const root = document.documentElement;
  if (inFullscreen()) {
    try { screen.orientation.unlock(); } catch { /* not supported */ }
    return (document.exitFullscreen || document.webkitExitFullscreen).call(document);
  }
  const request = root.requestFullscreen || root.webkitRequestFullscreen;
  if (!request) {
    // iPhones cannot put a page in full screen, only the video itself.
    if (el.video.webkitEnterFullscreen && player.channel) el.video.webkitEnterFullscreen();
    return;
  }
  try {
    await request.call(root, { navigationUI: 'hide' });
    if (window.matchMedia('(pointer: coarse)').matches) await screen.orientation.lock('landscape');
  } catch { /* refused, or the screen cannot be turned: stay as we are */ }
}

// Short labels when the bar's buttons share a phone's width.
function fullLabel() {
  const narrow = S.L && S.L.narrow;
  el.banFull.textContent = inFullscreen()
    ? (narrow ? 'Exit' : 'Exit full screen')
    : (narrow ? 'Full' : 'Full screen');
}
for (const name of ['fullscreenchange', 'webkitfullscreenchange']) {
  document.addEventListener(name, fullLabel);
}

// ---- Moving around the guide ---------------------------------------------

// Up and down keep the time position; they never jump back to "now".
function moveRow(delta) {
  S.focusCh = clamp(S.focusCh + delta, 0, S.channels.length - 1);
  render();
}

function moveTime(dir) {
  const cell = focusCell(), min = minWin();
  if (dir > 0) {
    if (!Number.isFinite(cell.stop) || cell.stop >= S.dataEnd) return;
    S.focusTime = cell.stop;
    while (S.focusTime >= S.winStart + S.L.span) S.winStart += HALF_HOUR;
  } else if (cell.start < S.winStart && S.winStart > min) {
    // The show began to the left of the window: bring its start into view.
    S.winStart = Math.max(min, floorHalf(cell.start));
    S.focusTime = Math.max(cell.start, S.winStart);
  } else if (cell.start > min) {
    const prev = cellAt(focusChannel(), cell.start - 1);
    S.focusTime = Math.max(prev.start, min);
    S.winStart = Math.min(S.winStart, Math.max(min, floorHalf(S.focusTime)));
  }
  render();
}

function scrollRows(delta) {
  const L = S.L;
  S.rowTop = clamp(S.rowTop + delta, 0, Math.max(0, S.channels.length - L.rows));
  S.focusCh = clamp(S.focusCh, S.rowTop, S.rowTop + L.rows - 1);
  render();
}

function scrollTime(delta) {
  S.winStart = clamp(S.winStart + delta * HALF_HOUR, minWin(), maxWin());
  S.focusTime = clamp(S.focusTime, S.winStart, S.winStart + S.L.span - 1);
  render();
}

// Typing a channel number.
let digits = '', digitTimer = 0;
function typeDigit(d) {
  digits = (digits + d).slice(-3);
  showOsd(`Ch ${digits}`, 0);
  clearTimeout(digitTimer);
  digitTimer = setTimeout(commitDigits, 1300);
}
function commitDigits() {
  clearTimeout(digitTimer);
  const num = String(parseInt(digits, 10));
  digits = '';
  const at = S.channels.findIndex(c => c.num === num);
  if (at < 0) return showOsd('No such channel', 1500);
  hideOsd();
  S.focusCh = at;
  if (S.mode === 'full') { tune(S.channels[at]); showBanner(); }
  render();
}

// ---- One place where every input ends up ---------------------------------

function act(action) {
  if (isSplashShowing()) return;       // nothing moves under the splash
  if (!S.channels.length) {
    if (action === 'refresh') refresh(true);
    return;
  }
  if (/^\d$/.test(action)) return typeDigit(action);
  if (digits && action === 'select') return commitDigits();
  switch (action) {
    case 'refresh': return refresh(true);
    case 'mute': return toggleMute();
    case 'fullscreen': return toggleFullscreen();
  }
  if (S.mode === 'settings') {
    switch (action) {
      case 'up': return moveSetting(-1);
      case 'down': return moveSetting(1);
      case 'left': return changeSetting(-1);
      case 'right': return changeSetting(1);
      case 'select': return selectSetting();
      case 'back': case 'info': case 'settings': return setMode('guide');
    }
    return;
  }
  if (S.mode === 'themes') {
    switch (action) {
      case 'up': return moveTheme(-TP_COLS);
      case 'down': return moveTheme(TP_COLS);
      case 'left': return moveTheme(-1);
      case 'right': return moveTheme(1);
      case 'select': return pickTheme(S.tpIndex);
      case 'back': case 'info': case 'settings':
        setMode('settings');
        return renderSettings();
    }
    return;
  }
  if (S.mode === 'guide') {
    switch (action) {
      case 'up': return moveRow(-1);
      case 'down': return moveRow(1);
      case 'left': return moveTime(-1);
      case 'right': return moveTime(1);
      case 'chUp': return moveRow(-S.L.rows);
      case 'chDown': return moveRow(S.L.rows);
      case 'select': return watch(focusChannel());
      case 'info': return openDetails();
      case 'settings': return openSettings();
      case 'back':
        if (tunedChannel()) { setMode('full'); showBanner(); }
        return;
    }
  } else if (S.mode === 'full') {
    switch (action) {
      case 'up': case 'chUp': return stepChannel(1);
      case 'down': case 'chDown': return stepChannel(-1);
      case 'back': return openGuide();
      case 'select': case 'info':
        return el.banner.hidden ? showBanner() : hideBanner();
      case 'left': case 'right': return showBanner();
    }
  } else {
    switch (action) {
      case 'up': el.detText.scrollTop -= 42; return;
      case 'down': el.detText.scrollTop += 42; return;
      case 'select': closeDetails(); return watch(focusChannel());
      case 'back': case 'info': return closeDetails();
    }
  }
}

// ---- Keyboard --------------------------------------------------------------

const KEYS = {
  ArrowUp: 'up', ArrowDown: 'down', ArrowLeft: 'left', ArrowRight: 'right',
  Enter: 'select', ' ': 'select', Escape: 'back', Backspace: 'back',
  PageUp: 'chUp', PageDown: 'chDown',
  i: 'info', g: 'back', r: 'refresh', m: 'mute', f: 'fullscreen', s: 'settings',
};

window.addEventListener('keydown', e => {
  if (e.ctrlKey || e.metaKey || e.altKey) return;
  const action = /^\d$/.test(e.key) ? e.key : KEYS[e.key.length === 1 ? e.key.toLowerCase() : e.key];
  if (!action) return;
  e.preventDefault();
  if (action !== 'mute') wake();
  act(action);
});

// ---- Mouse and touch -------------------------------------------------------
// A tap on a show is Select. A long press (or right click) opens its
// details. Dragging the grid scrolls channels and time.

let drag = null;

function focusNode(node) {
  S.focusCh = +node.dataset.ci;
  if (node.dataset.t) S.focusTime = +node.dataset.t;
  render();
}

el.grid.addEventListener('pointerdown', e => {
  if (e.button > 0 || S.mode !== 'guide') return;
  const node = e.target.closest('.cell[data-ci]');
  drag = { x: e.clientX, y: e.clientY, doneX: 0, doneY: 0, axis: '', moved: false, held: false, node };
  drag.timer = setTimeout(() => {
    if (!drag || drag.moved || !drag.node) return;
    drag.held = true;
    focusNode(drag.node);
    openDetails();
  }, 550);
});

window.addEventListener('pointermove', e => {
  if (!drag) return;
  const dx = (e.clientX - drag.x) / S.L.scale, dy = (e.clientY - drag.y) / S.L.scale;
  if (!drag.moved && Math.hypot(dx, dy) < 12) return;
  drag.moved = true;
  clearTimeout(drag.timer);
  drag.axis = drag.axis || (Math.abs(dx) > Math.abs(dy) ? 'x' : 'y');
  if (drag.axis === 'y') {
    const steps = Math.trunc(-dy / ROW);
    if (steps !== drag.doneY) { scrollRows(steps - drag.doneY); drag.doneY = steps; }
  } else {
    const steps = Math.trunc(-dx / (S.L.timeW / S.L.slots));
    if (steps !== drag.doneX) { scrollTime(steps - drag.doneX); drag.doneX = steps; }
  }
});

window.addEventListener('pointerup', () => {
  if (!drag) return;
  const d = drag;
  drag = null;
  clearTimeout(d.timer);
  wake();
  if (d.moved || d.held || !d.node || S.mode !== 'guide') return;
  focusNode(d.node);
  watch(focusChannel());
});
window.addEventListener('pointercancel', () => {
  if (drag) clearTimeout(drag.timer);
  drag = null;
});

el.grid.addEventListener('contextmenu', e => {
  e.preventDefault();
  const node = e.target.closest('.cell[data-ci]');
  if (!node || S.mode !== 'guide') return;
  if (drag) { clearTimeout(drag.timer); drag.held = true; }
  focusNode(node);
  openDetails();
});

let wheelRest = 0;
window.addEventListener('wheel', e => {
  e.preventDefault();
  if (isSplashShowing()) return;
  if (S.mode === 'details') { el.detText.scrollTop += e.deltaY; return; }
  if (S.mode !== 'guide' || !S.channels.length) return;
  const sideways = e.shiftKey || Math.abs(e.deltaX) > Math.abs(e.deltaY);
  wheelRest += sideways ? (e.deltaX || e.deltaY) : e.deltaY;
  const steps = Math.trunc(wheelRest / 50);
  if (!steps) return;
  wheelRest -= steps * 50;
  if (sideways) scrollTime(Math.sign(steps));
  else scrollRows(Math.sign(steps));
}, { passive: false });

function pictureClick() {
  wake();
  if (S.mode === 'full') return el.banner.hidden ? showBanner() : hideBanner();
  if (tunedChannel()) { setMode('full'); showBanner(); }
}
el.screen.addEventListener('click', pictureClick);
$('backdrop').addEventListener('click', pictureClick);
el.screen.addEventListener('dblclick', toggleFullscreen);

function button(node, fn) {
  node.addEventListener('click', e => {
    e.stopPropagation();
    if (node !== el.banMute) wake();
    fn();
    if (S.mode === 'full' && !el.banner.hidden) showBanner();   // keep it up while in use
  });
}
button(el.banGuide, openGuide);
button(el.banUp, () => stepChannel(1));
button(el.banDown, () => stepChannel(-1));
button(el.banMute, toggleMute);
button(el.detWatch, () => { closeDetails(); watch(focusChannel()); });
button(el.detBack, closeDetails);
button(el.banFull, toggleFullscreen);
button(el.setClose, () => setMode('guide'));
button(el.cog, () => (S.mode === 'settings' || S.mode === 'themes' ? setMode('guide') : S.mode === 'guide' && S.channels.length ? openSettings() : null));
el.setRows.addEventListener('click', e => {
  const node = e.target.closest('[data-row]');
  if (!node) return;
  S.setRow = +node.dataset.row;
  selectSetting();
});
el.tpGrid.addEventListener('click', e => {
  const tile = e.target.closest('[data-tp]');
  if (tile) pickTheme(+tile.dataset.tp);
});

// ---- Game controllers ------------------------------------------------------
// Standard mapping: A/Cross select, B/Circle back, X/Square info, D-pad or
// left stick to move, shoulders for channel down/up. A pad shows up only
// after its first button press on the page.

const PAD_BUTTONS = { 0: 'select', 1: 'back', 2: 'info', 3: 'settings', 4: 'chDown', 5: 'chUp', 9: 'settings', 12: 'up', 13: 'down', 14: 'left', 15: 'right' };
const PAD_REPEATS = new Set(['up', 'down', 'left', 'right', 'chUp', 'chDown']);
const padHeld = new Map();   // action -> time of next repeat

function pollPads(now) {
  const down = new Set();
  for (const pad of navigator.getGamepads ? navigator.getGamepads() : []) {
    if (!pad || !pad.connected) continue;
    for (const [index, action] of Object.entries(PAD_BUTTONS)) {
      if (pad.buttons[index] && pad.buttons[index].pressed) down.add(action);
    }
    const [ax = 0, ay = 0] = pad.axes;
    if (ax < -0.6) down.add('left'); else if (ax > 0.6) down.add('right');
    if (ay < -0.6) down.add('up'); else if (ay > 0.6) down.add('down');
  }
  for (const action of down) {
    const next = padHeld.get(action);
    if (next === undefined) {
      padHeld.set(action, now + 400);
      act(action);
    } else if (PAD_REPEATS.has(action) && now >= next) {
      padHeld.set(action, now + 110);
      act(action);
    }
  }
  for (const action of padHeld.keys()) if (!down.has(action)) padHeld.delete(action);
  requestAnimationFrame(pollPads);
}
requestAnimationFrame(pollPads);

// ---- Keeping the listings fresh ---------------------------------------------
// Schedules are rebuilt on the server now and then, so the guide is read
// again every 15 minutes, when the tab comes back, and on R.

let retryMs = 5000, retryTimer = 0;

async function refresh(manual = false) {
  if (S.loading) return;
  S.loading = true;
  clearTimeout(retryTimer);
  const first = !S.channels.length;
  const focusId = first ? null : focusChannel().id;
  try {
    const guide = await loadGuide();
    S.channels = guide.channels;
    S.hasHd = guide.hasHd;
    S.dataEnd = guide.end;
    S.loadedAt = Date.now();
    retryMs = 5000;
    let wanted = focusId;
    if (first) {
      try { wanted = localStorage.getItem(LAST_CHANNEL_KEY); } catch { /* private mode */ }
    }
    const at = S.channels.findIndex(c => c.id === wanted);
    S.focusCh = at >= 0 ? at : (first ? 0 : S.focusCh);
    el.gridMsg.hidden = true;
    render();
    if (manual) showOsd('Guide updated', 1500);
  } catch (err) {
    console.error('guide refresh failed:', err);
    if (first) {
      el.gridMsg.hidden = false;
      el.gridMsg.textContent = "Can't reach the TV server. Trying again…";
    }
    retryTimer = setTimeout(refresh, retryMs);
    retryMs = Math.min(60000, retryMs * 2);
  } finally {
    S.loading = false;
  }
}

setInterval(refresh, REFRESH_MS);

// Once a second: the clock, the half-hour realignment and the banner's
// progress bar. The grid is only redrawn when the minute changes.
let lastMinute = 0;
setInterval(() => {
  const minute = Math.floor(Date.now() / 60000);
  if (minute !== lastMinute) {
    lastMinute = minute;
    if (S.mode !== 'full') render();
  }
  if (!el.banner.hidden) fillBanner();
}, 1000);

// A forgotten tab must not keep the server streaming all night.
let hiddenTimer = 0, suspendedId = null;
document.addEventListener('visibilitychange', () => {
  if (document.hidden) {
    hiddenTimer = setTimeout(() => {
      if (!player.channel) return;
      suspendedId = player.channel.id;
      player.stop();
      stopSurf();
    }, HIDDEN_STOP_MS);
    return;
  }
  clearTimeout(hiddenTimer);
  if (suspendedId) {
    const ch = S.channels.find(c => c.id === suspendedId);
    suspendedId = null;
    if (ch) { const st = streamOf(ch); player.tune(ch, { stream: st.num, watchSlow: st.hd }); }
  }
  if (Date.now() - S.loadedAt > 60000) refresh();
  render();
});

window.addEventListener('resize', () => { applyLayout(); applyZoom(); render(); });

// Start: the theme, then the splash over the loading guide. The guide is
// read in the meantime and is usually ready by the time the splash fades.
applyTheme(getSetting('theme'));
applyLayout();
showSplash(getSetting('theme'));
refresh();
