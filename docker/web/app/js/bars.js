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
const BLANK_LIMIT = 6;         // pure-black 2D reads in a row before trying WebGL (3 s)

// Two ways to look at a frame. The 2D canvas copy works in most browsers.
// Firefox for Android hands a 2D canvas an all-black copy of hardware-
// decoded video (no error, every pixel 0), while the same frame drawn
// through WebGL (the GPU path video players use for effects) is readable.
// So after a few pure-black 2D reads during playback, the watcher switches
// to WebGL for that page.
class GlReader {
  constructor() {
    const c = document.createElement('canvas');
    c.width = W; c.height = H;
    const gl = c.getContext('webgl', { preserveDrawingBuffer: true, antialias: false })
      || c.getContext('experimental-webgl', { preserveDrawingBuffer: true });
    if (!gl) throw new Error('no WebGL');
    const shader = (type, src) => {
      const sh = gl.createShader(type);
      gl.shaderSource(sh, src);
      gl.compileShader(sh);
      if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(sh));
      return sh;
    };
    const prog = gl.createProgram();
    // A quad over the whole canvas. Drawn unflipped, the picture lands
    // upside down in GL terms, so readPixels (which starts at the bottom
    // row) returns the top of the picture first, as the 2D copy does.
    gl.attachShader(prog, shader(gl.VERTEX_SHADER,
      'attribute vec2 p; varying vec2 t; void main(){ t = vec2((p.x + 1.0) / 2.0, (1.0 + p.y) / 2.0); gl_Position = vec4(p, 0.0, 1.0); }'));
    gl.attachShader(prog, shader(gl.FRAGMENT_SHADER,
      'precision mediump float; uniform sampler2D v; varying vec2 t; void main(){ gl_FragColor = texture2D(v, t); }'));
    gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(prog));
    gl.useProgram(prog);
    const buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
    const loc = gl.getAttribLocation(prog, 'p');
    gl.enableVertexAttribArray(loc);
    gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
    const tex = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, tex);
    // Video sizes are rarely powers of two: no mipmaps, clamp at the edges.
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    gl.viewport(0, 0, W, H);
    this.gl = gl;
    this.pixels = new Uint8Array(W * H * 4);
  }

  read(video) {
    const gl = this.gl;
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, video);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    gl.readPixels(0, 0, W, H, gl.RGBA, gl.UNSIGNED_BYTE, this.pixels);
    return this.pixels;
  }
}

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
    this.method = '2d';          // '2d', 'webgl' or 'none' (this browser shows no frames)
    this.blank = 0;              // pure-black reads in a row with the current method
    this.gl = null;
  }

  // The frame as RGBA pixels, W x H, top row first.
  #read(video) {
    if (this.method === 'webgl') return this.gl.read(video);
    this.ctx.drawImage(video, 0, 0, W, H);
    return this.ctx.getImageData(0, 0, W, H).data;
  }

  // Too many pure-black frames in a row: the next way of looking, if any.
  #giveUpOn(method) {
    this.blank = 0;
    if (method === '2d') {
      try { this.gl = new GlReader(); this.method = 'webgl'; return; } catch { /* no WebGL here */ }
    }
    this.method = 'none';
    this.stop();
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
    if (this.method === 'none') return this.stop();
    let data;
    try {
      data = this.#read(video);
    } catch (err) {
      this.last = { at: Date.now(), outcome: `${this.method}: cannot read frame: ${err && err.name}`, lit: 0, box: null };
      return this.#giveUpOn(this.method);
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
    this.last = { at: Date.now(), outcome: `read (${this.method})`, lit: lit / (W * H), max, box: { top, bottom, left, right } };
    // Pure black, every pixel 0, while playing: a real picture almost never
    // is (even a black scene has noise above 0). Count it; enough in a row
    // and this way of looking is blind.
    if (max === 0) {
      if (++this.blank >= BLANK_LIMIT) this.#giveUpOn(this.method);
      return;
    }
    this.blank = 0;
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
