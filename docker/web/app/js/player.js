// Plays one channel at a time in the page's single <video> element.
//
// Every open stream is a live transcode on the server, so there is never
// a second player: tuning tears the old stream down first.

const Hls = window.Hls;

const FLIP_WINDOW_MS = 2500;   // a tune this soon after the last one is "flipping"
const FLIP_SETTLE_MS = 800;    // then wait this long for the flipping to stop

export class Player {
  // onState(state, channel): 'idle' | 'tuning' | 'playing' | 'error' | 'unsupported'
  // onMuted(muted): the browser refused sound before the first key or click
  constructor(video, { onState, onMuted }) {
    this.video = video;
    this.onState = onState;
    this.onMuted = onMuted;
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
  tune(channel, { warm = false, stream = null } = {}) {
    const now = Date.now();
    const flipping = !warm && now - this.lastTuneAt < FLIP_WINDOW_MS;
    this.lastTuneAt = now;
    this.#teardown();
    this.channel = channel;
    this.stream = stream || channel.num;
    this.retries = 0;
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
        backBufferLength: 30,
        manifestLoadingMaxRetry: 2,
        levelLoadingMaxRetry: 3,
        fragLoadingMaxRetry: 3,
      });
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
