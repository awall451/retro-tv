// Watch beacons: tell the channel tracker which channel this viewer is
// watching, so it can count watch time per channel (its "Popular" page).
// The server says where the tracker is, in TRACKER_URL; the container puts
// it in /config.json as "tracker" (web/config.d/tracker.sh) and lets it into
// the page's connect-src. Without it the key is missing and nothing is sent.
// See docker/README.md.
//
// What is sent, on each tune (once flipping settles), every minute while
// watching, and on leaving: the channel number, HD or not, the channels
// being warmed for fast flipping, the kind of screen (tv, mobile, desktop)
// and a random id kept in this browser's storage, so the tracker can join
// the minutes of one screen. Nothing else: no titles, no names. A stream
// counts while it plays (also in a hidden tab, until the viewer stops it
// there).

import { serverSetting } from './config.js';

const CLIENT_KEY = 'retro-tv.client-id';
const HEARTBEAT_MS = 60 * 1000;
const SETTLE_MS = 1500;

// The tracker's origin, or '' when the server has none.
export async function loadTracker() {
  const cfg = await serverSetting('tracker');
  return cfg && typeof cfg.url === 'string' && /^https?:\/\/[^/?#\s]+$/i.test(cfg.url) ? cfg.url : '';
}

function clientId() {
  let id = null;
  try { id = localStorage.getItem(CLIENT_KEY); } catch { /* private mode */ }
  if (id && /^[A-Za-z0-9_-]{8,64}$/.test(id)) return id;
  const bytes = crypto.getRandomValues(new Uint8Array(12));
  id = btoa(String.fromCharCode(...bytes)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  try { localStorage.setItem(CLIENT_KEY, id); } catch { /* private mode: a new id per visit */ }
  return id;
}

function uaClass(tvMode) {
  if (tvMode) return 'tv';
  return /Mobi|Android|iPhone|iPad|iPod/i.test(navigator.userAgent) ? 'mobile' : 'desktop';
}

export class Beacon {
  // tracker: the promise from loadTracker().
  // watching(): what is being watched now, {channel, kind, hd, warm}, or null.
  // kind is 'stream' (the tracker also takes 'web', for a page shown instead
  // of a stream).
  constructor(tracker, watching, { tvMode = false } = {}) {
    this.url = null;
    this.watching = watching;
    this.ua = uaClass(tvMode);
    this.client = null;
    this.last = null;
    this.settle = 0;
    tracker.then(url => {
      if (!url) return;
      this.url = url + '/api/watch/beacon';
      this.client = clientId();
      setInterval(() => this.#send(), HEARTBEAT_MS);
      this.changed();
    });
    // Closing the tab or leaving the page: say so, so the minutes end here.
    window.addEventListener('pagehide', () => this.#send(true));
  }

  // The channel, the player or the tab's visibility changed: report once
  // things settle (flipping through channels sends one beacon, not ten).
  changed() {
    if (!this.url) return;
    clearTimeout(this.settle);
    this.settle = setTimeout(() => this.#send(), SETTLE_MS);
  }

  #send(leaving = false) {
    if (!this.url) return;
    const now = leaving ? null : this.watching();
    let body;
    if (now) body = { ...now, event: 'watch' };
    else if (this.last) body = { ...this.last, event: 'stop' };
    else return;
    this.last = now;
    body.client = this.client;
    body.ua = this.ua;
    try {
      // text/plain keeps it a "simple" request: no CORS preflight.
      fetch(this.url, {
        method: 'POST', mode: 'cors', credentials: 'omit', keepalive: true, cache: 'no-store',
        headers: { 'Content-Type': 'text/plain' }, body: JSON.stringify(body),
      }).catch(() => { /* the tracker is down: just a lost minute */ });
    } catch { /* ignore */ }
  }
}
