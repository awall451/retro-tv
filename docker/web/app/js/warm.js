// Warm-up: keeps a channel running on the server without playing it, so
// that flipping to it shows a picture almost at once instead of waiting
// for the server to start it.
//
// A channel runs on the server for as long as somebody keeps asking for
// its playlist. That is all this does: ask for the playlist every few
// seconds. No video is downloaded.
//
// Every warm channel is a live transcode on the server (and a file being
// read from wherever the library lives), so this is used sparingly: only
// while the viewer is flipping channels, and only for the next channel in
// the direction of travel. See surf() in app.js.

const POLL_MS = 4000;
const MAX_FAILURES = 3;

async function getText(url, signal) {
  const res = await fetch(url, { cache: 'no-store', signal });
  if (!res.ok) throw new Error(`${url} answered ${res.status}`);
  return res.text();
}

function sleep(ms, signal) {
  return new Promise(resolve => {
    const timer = setTimeout(resolve, ms);
    signal.addEventListener('abort', () => { clearTimeout(timer); resolve(); }, { once: true });
  });
}

export class Warmer {
  #entries = new Map();   // channel number -> { ctl, ready }

  // Keep exactly these channels warm; let go of any others.
  set(channels) {
    const wanted = new Set(channels.map(c => c.num));
    for (const num of [...this.#entries.keys()]) if (!wanted.has(num)) this.#drop(num);
    for (const num of wanted) {
      if (this.#entries.has(num)) continue;
      const entry = { ctl: new AbortController(), ready: false };
      this.#entries.set(num, entry);
      this.#keep(num, entry);
    }
  }

  // True once the channel has video waiting on the server.
  isReady(channel) {
    const entry = this.#entries.get(channel.num);
    return !!entry && entry.ready;
  }

  // The player is taking this channel over (or it is no longer wanted).
  release(channel) {
    this.#drop(channel.num);
  }

  clear() {
    for (const num of [...this.#entries.keys()]) this.#drop(num);
  }

  #drop(num) {
    const entry = this.#entries.get(num);
    if (!entry) return;
    entry.ctl.abort();
    this.#entries.delete(num);
  }

  async #keep(num, entry) {
    const signal = entry.ctl.signal;
    let playlist = null, failures = 0;
    while (!signal.aborted) {
      try {
        if (!playlist) {
          // Asking for the channel's entry playlist is what starts it.
          const master = await getText(`/iptv/channel/${encodeURIComponent(num)}.m3u8?mode=segmenter`, signal);
          playlist = master.split(/\r?\n/).filter(line => line && !line.startsWith('#')).pop() || '';
          if (!playlist.startsWith('/iptv/session/')) throw new Error('unexpected channel playlist');
        }
        const live = await getText(playlist, signal);
        entry.ready = live.includes('#EXTINF');
        failures = 0;
      } catch {
        if (signal.aborted) return;
        // Most likely the server is full. Try a few times, then give up
        // quietly: the channel simply starts cold if the viewer gets there.
        entry.ready = false;
        playlist = null;
        if (++failures >= MAX_FAILURES) {
          if (this.#entries.get(num) === entry) this.#entries.delete(num);
          return;
        }
      }
      await sleep(POLL_MS, signal);
    }
  }
}
