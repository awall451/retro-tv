// Plays one channel at a time in the page's single <video> element.
//
// Every open stream is a live transcode on the server, so there is never
// a second player: tuning tears the old stream down first.

const Hls = window.Hls;

const FLIP_WINDOW_MS = 2500;   // a tune this soon after the last one is "flipping"
const FLIP_SETTLE_MS = 800;    // then wait this long for the flipping to stop

// ---- Padding ----------------------------------------------------------------------
// A live channel only exists a little ahead of real time: the server keeps
// the last ~40 s of 4 s segments and makes new ones about as fast as they
// play. hls.js by default plays 3 segments behind the newest, so a dip in
// the connection longer than ~12 s empties the buffer. We play further back
// instead (PAD_SEGMENTS) so more is always queued. Joining a channel that is
// already running starts that far back at once; on a channel that has just
// started there is nothing older yet, so playback runs a few percent slow
// (pitch kept) until the padding has built up, then back to normal speed.
const PAD_SEGMENTS = 7;          // aim to play this many 4 s segments behind the newest
const PAD_TARGET_S = 26;         // slow down while the live latency is under this
const PAD_RATE = 0.96;           // how slow (4%: hard to notice, ~1 s gained every 25 s)
const PAD_MIN_BUFFER_S = 3;      // never slow down with less than this queued (it would only stall)

// ---- Too slow for this stream -------------------------------------------------
// While watching an HD twin, every segment's download time is compared with
// its length. A link that needs about as long to fetch a segment as to play
// it cannot keep up; together with real stalls, that tells the app to drop
// to Standard (onSlow).
const SLOW_WINDOW = 4;           // average over the last this many segments
const SLOW_RATIO = 0.85;         // fetch time / segment length above this = not keeping up
const SLOW_STALLS = 2;           // or this many stalls ...
const SLOW_STALL_MS = 60000;     // ... within this long

export class Player {
  // onState(state, channel): 'idle' | 'tuning' | 'playing' | 'error' | 'unsupported'
  // onMuted(muted): the browser refused sound before the first key or click
  // onSlow(channel): the connection cannot keep up with this stream (only
  // reported for tunes made with watchSlow, i.e. HD)
  constructor(video, { onState, onMuted, onSlow = () => {} }) {
    this.video = video;
    this.onState = onState;
    this.onMuted = onMuted;
    this.onSlow = onSlow;
    this.padTimer = 0;
    this.slow = null;
    this.channel = null;
    this.hls = null;
    this.retries = 0;
    this.retryTimer = 0;
    this.lastTuneAt = 0;
    this.state = 'idle';

    video.addEventListener('playing', () => {
      if (!this.channel) return;
      this.retries = 0;
      this.#set('playing');
    });
    // A stall after playback had started (not the first load).
    video.addEventListener('waiting', () => {
      if (!this.slow || this.state !== 'playing') return;
      const now = Date.now();
      this.slow.stalls = this.slow.stalls.filter(t => now - t < SLOW_STALL_MS).concat(now);
      if (this.slow.stalls.length >= SLOW_STALLS) this.#tooSlow();
    });
    video.addEventListener('error', () => {
      // Only the native (Safari) path reports errors here; hls.js has its own.
      if (this.channel && !this.hls && video.getAttribute('src')) this.#fail();
    });
  }

  #set(state) {
    this.state = state;
    this.onState(state, this.channel);
  }

  // Flipping through channels must not start a stream for each one passed:
  // on the server every started channel keeps transcoding for about a
  // minute after it is left, and the server can only run a few at once.
  // So the first tune starts at once, and tunes that follow close behind
  // wait until the flipping settles. A channel that is already running
  // on the server (warm) costs nothing to join, so it never waits.
  // stream: the channel number to ask the server for, when it is not the
  // channel's own (its HD twin).
  // watchSlow: report onSlow if the connection cannot keep up (HD).
  tune(channel, { warm = false, stream = null, watchSlow = false } = {}) {
    const now = Date.now();
    const flipping = !warm && now - this.lastTuneAt < FLIP_WINDOW_MS;
    this.lastTuneAt = now;
    this.#teardown();
    this.channel = channel;
    this.stream = stream || channel.num;
    this.retries = 0;
    this.slow = watchSlow ? { ratios: [], stalls: [], reported: false } : null;
    if (!flipping) return this.#start();
    this.#set('tuning');
    this.retryTimer = setTimeout(() => this.#start(), FLIP_SETTLE_MS);
  }

  stop() {
    this.#teardown();
    this.channel = null;
    this.#set('idle');
  }

  #start() {
    const video = this.video;
    const url = `/iptv/channel/${encodeURIComponent(this.stream)}.m3u8?mode=segmenter`;
    const native = video.canPlayType('application/vnd.apple.mpegurl');
    const mse = Hls && Hls.isSupported();
    this.#set('tuning');

    // Safari plays HLS itself, and does it better than script can on
    // iPhones. Everything else goes through hls.js.
    if (mse && !(native && !window.chrome)) {
      const hls = this.hls = new Hls({
        lowLatencyMode: false,          // ErsatzTV is plain HLS with 4 s segments
        liveSyncDurationCount: PAD_SEGMENTS,
        liveMaxLatencyDurationCount: PAD_SEGMENTS + 3,   // fallen this far behind: jump forward
        maxBufferLength: 45,
        backBufferLength: 30,
        manifestLoadingMaxRetry: 2,
        levelLoadingMaxRetry: 3,
        fragLoadingMaxRetry: 3,
      });
      hls.on(Hls.Events.FRAG_LOADED, (_event, data) => this.#measure(data));
      this.#pad();
      let recovered = false;
      hls.on(Hls.Events.MANIFEST_PARSED, () => this.#play());
      hls.on(Hls.Events.ERROR, (_event, data) => {
        if (!data.fatal || hls !== this.hls) return;
        if (data.type === Hls.ErrorTypes.MEDIA_ERROR && !recovered) {
          recovered = true;
          hls.recoverMediaError();
          return;
        }
        this.#fail();
      });
      hls.loadSource(url);
      hls.attachMedia(video);
    } else if (native) {
      video.src = url;
      video.addEventListener('loadedmetadata', () => this.#play(), { once: true });
      video.load();
    } else {
      this.#set('unsupported');
    }
  }

  #play() {
    const video = this.video;
    const attempt = video.play();
    if (!attempt) return;
    attempt.catch(err => {
      if (err && err.name !== 'NotAllowedError') return;
      // No sound allowed before the first key press or click: start muted.
      video.muted = true;
      this.onMuted(true);
      video.play().catch(() => {});
    });
  }

  unmute() {
    this.video.muted = false;
    this.onMuted(false);
  }

  // Live latency (seconds behind the newest segment) and what is queued.
  stats() {
    const video = this.video, hls = this.hls;
    const b = video.buffered;
    const ahead = b.length ? Math.max(0, b.end(b.length - 1) - video.currentTime) : 0;
    return {
      latency: hls && Number.isFinite(hls.latency) ? hls.latency : null,
      buffered: ahead,
      rate: video.playbackRate,
      bandwidth: hls ? hls.bandwidthEstimate : null,
    };
  }

  // Once a second: play a little slow while the padding is short.
  #pad() {
    clearInterval(this.padTimer);
    this.padTimer = setInterval(() => {
      const video = this.video;
      if (!this.hls || this.state !== 'playing' || video.paused) { video.playbackRate = 1; return; }
      const { latency, buffered } = this.stats();
      const short = latency !== null && latency < PAD_TARGET_S;
      video.playbackRate = short && buffered >= PAD_MIN_BUFFER_S ? PAD_RATE : 1;
    }, 1000);
  }

  // Each segment: how long it took to fetch against how long it plays.
  #measure(data) {
    if (!this.slow || this.slow.reported) return;
    const st = data.frag && data.frag.stats, dur = data.frag && data.frag.duration;
    if (!st || !dur || !st.loading || !st.loading.end) return;
    const ms = st.loading.end - st.loading.start;
    if (ms <= 0) return;
    const r = this.slow.ratios;
    r.push(ms / (dur * 1000));
    if (r.length > SLOW_WINDOW) r.shift();
    if (r.length === SLOW_WINDOW && r.reduce((a, x) => a + x, 0) / r.length > SLOW_RATIO
        && this.stats().buffered < 2 * PAD_SEGMENTS) this.#tooSlow();
  }

  #tooSlow() {
    if (!this.slow || this.slow.reported) return;
    this.slow.reported = true;
    this.onSlow(this.channel);
  }

  #fail() {
    const channel = this.channel;
    this.#teardown();
    this.channel = channel;
    this.#set('error');
    const wait = Math.min(30000, 2000 * 2 ** this.retries++);
    this.retryTimer = setTimeout(() => this.#start(), wait);
  }

  #teardown() {
    clearTimeout(this.retryTimer);
    clearInterval(this.padTimer);
    this.video.playbackRate = 1;
    if (this.hls) {
      this.hls.destroy();
      this.hls = null;
    }
    const video = this.video;
    video.pause();
    if (video.getAttribute('src')) {
      video.removeAttribute('src');
      video.load();
    }
  }
}
