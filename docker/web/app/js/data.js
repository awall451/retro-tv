// Guide data: the channel list (M3U) and listings (XMLTV), read through
// the viewer's own /iptv/ proxy and turned into plain objects.

export const HALF_HOUR = 30 * 60 * 1000;

// Programmes shorter than this are "shorts": a run of them with the same
// title inside one half hour is drawn as a single cell.
const SHORT_MS = 15 * 60 * 1000;

const HD_GROUP = 'HD';
const HD_OFFSET = 100;

async function getText(url) {
  const res = await fetch(url, { cache: 'no-store' });
  if (!res.ok) throw new Error(`${url} answered ${res.status}`);
  return res.text();
}

// ErsatzTV writes absolute URLs. The proxy already makes them relative;
// this is the second lock: only a path under /iptv/ is ever used.
function localPath(url) {
  if (!url) return null;
  const path = url.trim().replace(/^[a-z][a-z0-9+.-]*:\/\/[^/]+/i, '');
  return path.startsWith('/iptv/') ? path : null;
}

export function parseM3U(text) {
  const channels = [];
  for (const line of text.split(/\r?\n/)) {
    if (!line.startsWith('#EXTINF')) continue;
    const attrs = {};
    for (const m of line.matchAll(/([\w-]+)="([^"]*)"/g)) attrs[m[1]] = m[2];
    const comma = line.lastIndexOf(',');
    const name = (attrs['tvg-name'] || line.slice(comma + 1)).trim();
    const num = (attrs['tvg-chno'] || attrs['channel-number'] || '').trim();
    if (!attrs['tvg-id'] || !/^\d+(\.\d+)?$/.test(num)) continue;
    channels.push({ id: attrs['tvg-id'], num, name, group: (attrs['group-title'] || '').trim() });
  }
  channels.sort((a, b) => parseFloat(a.num) - parseFloat(b.num));
  return channels;
}

// "20261105150000 -0500" carries its own offset: return the instant in ms.
export function parseXmltvTime(value) {
  const m = /^(\d{4})(\d\d)(\d\d)(\d\d)(\d\d)(\d\d)?\s*(?:([+-])(\d\d)(\d\d))?/.exec(value || '');
  if (!m) return NaN;
  const utc = Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +(m[6] || 0));
  if (!m[7]) return utc;
  const offset = (+m[8] * 60 + +m[9]) * 60000;
  return m[7] === '+' ? utc - offset : utc + offset;
}

export function parseXmltv(text, keepFrom, keepTo) {
  const doc = new DOMParser().parseFromString(text, 'text/xml');
  if (doc.querySelector('parsererror')) throw new Error('The guide data is not valid XML');
  const byChannel = new Map();
  for (const node of doc.getElementsByTagName('programme')) {
    const start = parseXmltvTime(node.getAttribute('start'));
    const stop = parseXmltvTime(node.getAttribute('stop'));
    if (!(stop > start) || stop <= keepFrom || start >= keepTo) continue;
    const p = { start, stop, title: '', sub: '', desc: '', cats: [], rating: '', year: '', ep: '', poster: null, still: null };
    for (const c of node.children) {
      const value = c.textContent.trim();
      switch (c.tagName) {
        case 'title': p.title = value; break;
        case 'sub-title': p.sub = value; break;
        case 'desc': p.desc = value; break;
        case 'category': p.cats.push(value); break;
        case 'date': p.year = value.slice(0, 4); break;
        case 'rating': p.rating = value; break;
        case 'episode-num':
          if (c.getAttribute('system') === 'onscreen') p.ep = value;
          break;
        case 'icon': p.poster = p.poster || localPath(c.getAttribute('src')); break;
        case 'image':
          if (c.getAttribute('type') === 'poster') p.poster = localPath(value) || p.poster;
          else if (c.getAttribute('type') === 'still') p.still = localPath(value);
          break;
      }
    }
    p.movie = p.cats[0] === 'Movie';
    const id = node.getAttribute('channel');
    if (!byChannel.has(id)) byChannel.set(id, []);
    byChannel.get(id).push(p);
  }
  for (const list of byChannel.values()) list.sort((a, b) => a.start - b.start);
  return byChannel;
}

// Turn one channel's programmes into the cells the grid draws:
//  - a run of shorts with one title inside one half hour becomes one cell
//  - a hole in the listings becomes a "No information" cell
// Every cell has start, stop, title and items (the programmes in it).
export function buildCells(progs) {
  const cells = [];
  let last = null;
  for (const p of progs) {
    if (last && p.start > last.stop + 60000) {
      cells.push({ gap: true, start: last.stop, stop: p.start, title: 'No information', items: [] });
      last = null;
    }
    const short = p.stop - p.start < SHORT_MS;
    const bucket = Math.floor(p.start / HALF_HOUR);
    if (last && short && last.short && last.title === p.title && last.bucket === bucket) {
      last.items.push(p);
      last.stop = p.stop;
    } else {
      last = { start: p.start, stop: p.stop, title: p.title || 'No title', items: [p], short, bucket };
      cells.push(last);
    }
  }
  return cells;
}

// Fetch and parse everything. Throws if either file cannot be read.
export async function loadGuide(now = Date.now()) {
  const [m3u, xml] = await Promise.all([
    getText('/iptv/channels.m3u'),
    getText('/iptv/xmltv.xml'),
  ]);
  // HD twins: a channel in the group "HD", numbered 100 above the channel
  // it mirrors, is that channel's HD stream. Twins never appear in the
  // guide; the HD setting makes the viewer ask for them instead.
  const all = parseM3U(m3u);
  const channels = all.filter(c => c.group !== HD_GROUP);
  for (const twin of all.filter(c => c.group === HD_GROUP)) {
    const base = channels.find(c => parseFloat(c.num) + HD_OFFSET === parseFloat(twin.num));
    if (base) base.hd = twin.num;
  }
  if (!channels.length) throw new Error('The channel list is empty');
  const progs = parseXmltv(xml, now - 2 * HALF_HOUR, now + 96 * HALF_HOUR);
  let end = 0;
  for (const ch of channels) {
    ch.progs = progs.get(ch.id) || [];
    ch.cells = buildCells(ch.progs);
    if (ch.progs.length) end = Math.max(end, ch.progs[ch.progs.length - 1].stop);
  }
  return { channels, end, loadedAt: now, hasHd: channels.some(c => c.hd) };
}

// The cell of a channel that covers instant t. Outside the listings it is
// a made-up "No information" cell reaching to the nearest real one.
export function cellAt(channel, t) {
  const cells = channel.cells;
  let lo = 0, hi = cells.length - 1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (t < cells[mid].start) hi = mid - 1;
    else if (t >= cells[mid].stop) lo = mid + 1;
    else return cells[mid];
  }
  const before = cells[hi], after = cells[lo];
  return {
    gap: true, title: 'No information', items: [],
    start: before ? before.stop : -Infinity,
    stop: after ? after.start : Infinity,
  };
}

// The single programme on a channel at instant t, or null.
export function programmeAt(channel, t) {
  const cell = cellAt(channel, t);
  return cell.items.find(p => t >= p.start && t < p.stop) || null;
}
