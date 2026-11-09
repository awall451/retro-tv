// Finds the black bars baked into the picture (a widescreen show sent in
// a 4:3 frame), so the viewer can zoom them away on a wide screen.
//
// Twice a second a tiny copy of the current frame is checked for rows
// and columns with nothing in them. One dark scene must not be mistaken
// for bars, so the picture area is the union of everything seen over
// the last several seconds: bars only grow when nothing has shown up in
// them for that long, and shrink the moment something does.

const W = 64, H = 48;          // size of the tiny copy
const SAMPLE_MS = 500;
const WINDOW = 16;             // samples remembered (8 s)
const FIRST = 3;               // samples needed for a first answer (1.5 s)
const LIT = 40;                // a pixel brighter than this is picture
const MIN_BAR = 0.05;          // thinner than this is not worth zooming for

export class BarWatcher {
  // onChange({ x, y }): fraction of the frame that is bar on each side,
  // left/right (x) and top/bottom (y). Bars are taken as centered.
  constructor(video, onChange) {
    this.video = video;
    this.onChange = onChange;
    this.canvas = document.createElement('canvas');
    this.canvas.width = W;
    this.canvas.height = H;
    this.ctx = this.canvas.getContext('2d', { willReadFrequently: true });
    this.timer = 0;
    this.samples = [];
    this.bars = { x: 0, y: 0 };
    // What the last look at a frame found (read by the ?debug panel).
    this.last = { at: 0, outcome: 'not started', lit: 0, box: null };
  }

  start() {
    if (!this.timer) this.timer = setInterval(() => this.#sample(), SAMPLE_MS);
  }

  stop() {
    clearInterval(this.timer);
    this.timer = 0;
  }

  // New channel: forget what the last one looked like.
  reset() {
    this.samples = [];
    this.#set(0, 0);
  }

  #set(x, y) {
    if (x === this.bars.x && y === this.bars.y) return;
    this.bars = { x, y };
    this.onChange(this.bars);
  }

  #sample() {
    const video = this.video;
    if (video.readyState < 2 || video.paused || !video.videoWidth) {
      this.last = { ...this.last, at: Date.now(), outcome: `waiting (readyState ${video.readyState}${video.paused ? ', paused' : ''})` };
      return;
    }
    let data;
    try {
      this.ctx.drawImage(video, 0, 0, W, H);
      data = this.ctx.getImageData(0, 0, W, H).data;
    } catch (err) {
      this.last = { at: Date.now(), outcome: 'cannot read frame: ' + (err && err.name), lit: 0, box: null };
      return this.stop();      // this browser will not let script see the frame
    }
    let top = H, bottom = -1, left = W, right = -1, lit = 0;
    for (let y = 0; y < H; y++) {
      for (let x = 0; x < W; x++) {
        const i = (y * W + x) * 4;
        if ((data[i] * 3 + data[i + 1] * 6 + data[i + 2]) / 10 < LIT) continue;
        lit++;
        if (y < top) top = y;
        if (y > bottom) bottom = y;
        if (x < left) left = x;
        if (x > right) right = x;
      }
    }
    let max = 0;
    for (let i = 0; i < data.length; i += 4) max = Math.max(max, data[i], data[i + 1], data[i + 2]);
    this.last = { at: Date.now(), outcome: 'read', lit: lit / (W * H), max, box: { top, bottom, left, right } };
    // A mostly dark frame says nothing about where the picture ends.
    if (lit < W * H * 0.1) return;
    this.samples.push({ top, bottom, left, right });
    if (this.samples.length > WINDOW) this.samples.shift();
    if (this.samples.length < FIRST) return;

    const area = this.samples.reduce((a, s) => ({
      top: Math.min(a.top, s.top), bottom: Math.max(a.bottom, s.bottom),
      left: Math.min(a.left, s.left), right: Math.max(a.right, s.right),
    }));
    let y = Math.min(area.top, H - 1 - area.bottom) / H;
    let x = Math.min(area.left, W - 1 - area.right) / W;
    if (y < MIN_BAR) y = 0;
    if (x < MIN_BAR) x = 0;
    this.#set(x, y);
  }
}
