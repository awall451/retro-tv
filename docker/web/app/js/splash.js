// The splash: the theme's scene, shown over everything while the guide
// loads, and again for a moment after a theme change. Each scene is drawn
// as SVG in the 640x480 design units and scaled to fit the window; its sky
// and floor extend well past the frame, so a wide or tall window shows more
// scenery instead of bars.
//
// Nothing here touches the document at import time, so the scenes can also
// be rendered outside a browser (the Roku icons are made from the Cable one).

import { themeById } from './themes.js';

const W = 640, H = 480, PAD = 420;   // the frame, and how far the backdrop extends past it
const MIN_MS = 2500;                 // how long the splash stays, at least
const FADE_MS = 450;

// ---- Floor grid ---------------------------------------------------------------
// A camera projection of equal squares on a ground plane. A ground point
// (X, Z) lands at x = cx + f*X/Z, y = horizon + f*h/Z. Depth Z = 1 is the
// bottom edge of the frame and `near` is the width of a square there (the
// camera is half a square up, so near squares are about 2.5x wider than
// tall). Rows crowd toward the horizon; a gradient mask fades them into the
// horizon glow before they could meet. `phase` (0..1) slides the rows one
// square toward the viewer, for the scrolling floor.
export function gridPaths(horizon, { near = 80, f = 300, zfar = 12, phase = 0 } = {}) {
  const K = H - horizon, s = near / f, cx = W / 2, bottom = H + PAD;
  let rows = '';
  for (let n = -4; ; n++) {
    const z = 1 + (n - phase) * s;
    if (z > zfar) break;
    if (z < 0.12) continue;
    const y = horizon + K / z;
    if (y > bottom) continue;
    rows += `M${-PAD} ${y.toFixed(1)}h${W + 2 * PAD}`;
  }
  const z0 = K / (bottom - horizon), yfar = (horizon + K / zfar).toFixed(1);
  let cols = '';
  for (let m = 0; ; m++) {
    const xf = f * m * s / zfar;
    if (xf > W / 2 + PAD) break;
    const x0 = f * m * s / z0;
    for (const sign of m ? [1, -1] : [1]) {
      cols += `M${(cx + sign * x0).toFixed(1)} ${bottom}L${(cx + sign * xf).toFixed(1)} ${yfar}`;
    }
  }
  return { rows, cols };
}

// The floor: its color, the grid (a glow pass and a crisp pass), a veil of
// floor color fading in toward the horizon so the far rows dissolve instead
// of meeting, and the horizon line.
function gridSvg(p, horizon, floor, color, bright, opts) {
  const { rows, cols } = gridPaths(horizon, opts);
  const fadeTo = horizon + (H - horizon) * 0.42;
  const x = -PAD, w = W + 2 * PAD, h = H + PAD - horizon;
  return {
    defs: `<linearGradient id="${p}-veil" gradientUnits="userSpaceOnUse" x1="0" y1="${horizon}" x2="0" y2="${fadeTo.toFixed(1)}">`
      + `<stop offset="0" stop-color="${floor}" stop-opacity="1"/><stop offset=".55" stop-color="${floor}" stop-opacity=".7"/><stop offset="1" stop-color="${floor}" stop-opacity="0"/></linearGradient>`
      + `<clipPath id="${p}-clip"><rect x="${x}" y="${horizon}" width="${w}" height="${h}"/></clipPath>`
      + `<filter id="${p}-soft" x="-10%" y="-10%" width="120%" height="120%"><feGaussianBlur stdDeviation="1.6"/></filter>`,
    body: `<g clip-path="url(#${p}-clip)">`
      + `<rect x="${x}" y="${horizon}" width="${w}" height="${h}" fill="${floor}"/>`
      + `<g fill="none" stroke="${color}" stroke-width="4" opacity=".5" filter="url(#${p}-soft)"><path class="gridRows" d="${rows}"/><path d="${cols}"/></g>`
      + `<g fill="none" stroke="${bright}" stroke-width="1.5"><path class="gridRows" d="${rows}"/><path d="${cols}"/></g>`
      + `<rect x="${x}" y="${horizon}" width="${w}" height="${(fadeTo - horizon).toFixed(1)}" fill="url(#${p}-veil)"/>`
      + `<rect x="${x}" y="${horizon - 2}" width="${w}" height="4" fill="${color}" filter="url(#${p}-soft)"/>`
      + '</g>',
  };
}

const open = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet" aria-hidden="true">`;
const STARS = '<g fill="#fff"><circle cx="50" cy="40" r="1.3"/><circle cx="140" cy="90" r="1"/><circle cx="560" cy="50" r="1.4"/>'
  + '<circle cx="600" cy="120" r="1"/><circle cx="90" cy="170" r="1"/><circle cx="520" cy="160" r="1.1"/><circle cx="250" cy="30" r="1"/>'
  + '<circle cx="400" cy="22" r="1.2"/><circle cx="30" cy="250" r="1"/><circle cx="610" cy="230" r="1"/>'
  + '<circle cx="-120" cy="80" r="1.2"/><circle cx="-260" cy="200" r="1"/><circle cx="760" cy="60" r="1.3"/><circle cx="900" cy="190" r="1"/>'
  + '<circle cx="200" cy="-120" r="1"/><circle cx="480" cy="-200" r="1.2"/></g>';

// ---- Cable: the little television ---------------------------------------------
// Flat cells in the guide's colors: a portable with rabbit ears, two knobs
// and a speaker grille, the name on its screen. Still, like the guide.
function cableSvg() {
  return open
    + `<rect x="${-PAD}" y="${-PAD}" width="${W + 2 * PAD}" height="${H + 2 * PAD}" fill="#0a1240"/>`
    + '<path d="M300 118 L206 26 M300 118 L394 26" stroke="#f2c200" stroke-width="7" stroke-linecap="square"/>'
    + '<rect x="278" y="104" width="44" height="18" fill="#f2c200"/>'
    + '<rect x="118" y="120" width="404" height="272" fill="#1c3fa8" stroke="#000" stroke-width="4"/>'
    + '<rect x="148" y="150" width="276" height="212" fill="#0a1240" stroke="#f2c200" stroke-width="4"/>'
    + '<circle cx="474" cy="200" r="22" fill="#f2c200" stroke="#000" stroke-width="4"/>'
    + '<circle cx="474" cy="262" r="22" fill="#cfe0ff" stroke="#000" stroke-width="4"/>'
    + '<path d="M450 306h48M450 320h48M450 334h48M450 348h48" stroke="#0a1240" stroke-width="5"/>'
    + '<rect x="160" y="392" width="44" height="16" fill="#0f2a7a"/><rect x="436" y="392" width="44" height="16" fill="#0f2a7a"/>'
    + '<text class="cabin" x="286" y="248" font-size="66" fill="#fff" text-anchor="middle">RETRO</text>'
    + '<text class="cabin" x="286" y="326" font-size="66" fill="#f2c200" text-anchor="middle">TV</text>'
    + '</svg>';
}

// ---- Vaporwave: sunset over the grid -------------------------------------------
// A banded sun on the horizon, chrome lettering with the horizon cut
// through it, "please stand by" in brush script, a cyan floor grid that
// scrolls toward the viewer.
const HORIZON = 330;
const SUN = { cx: 320, cy: 214, r: 140 };

function sunCuts() {
  let out = '', y = SUN.cy + SUN.r * 0.08, h = Math.max(3, SUN.r * 0.028);
  while (y < SUN.cy + SUN.r) {
    out += `<rect x="${SUN.cx - SUN.r}" y="${y.toFixed(1)}" width="${2 * SUN.r}" height="${h.toFixed(1)}"/>`;
    y += h * 3.4;
    h *= 1.3;
  }
  return out;
}

function vaporSvg(phase = 0) {
  const g = gridSvg('vg', HORIZON, '#0c0426', '#19e6ff', '#8ff2ff', { phase });
  return open
    + '<defs>'
    + '<linearGradient id="v-sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#05020f"/><stop offset=".55" stop-color="#2a0a4e"/><stop offset="1" stop-color="#7a1a6e"/></linearGradient>'
    + '<linearGradient id="v-sun" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ffe26a"/><stop offset=".5" stop-color="#ff6f9c"/><stop offset="1" stop-color="#c0109a"/></linearGradient>'
    + '<linearGradient id="v-chrome" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#f4fbff"/><stop offset=".3" stop-color="#9fd3ff"/><stop offset=".49" stop-color="#3f6ea6"/><stop offset=".51" stop-color="#160a2c"/><stop offset=".72" stop-color="#6a3aa6"/><stop offset="1" stop-color="#f6e8ff"/></linearGradient>'
    + '<filter id="v-glow" x="-20%" y="-60%" width="140%" height="220%"><feGaussianBlur stdDeviation="7"/></filter>'
    + `<mask id="v-cut"><circle cx="${SUN.cx}" cy="${SUN.cy}" r="${SUN.r}" fill="#fff"/><g fill="#000">${sunCuts()}</g></mask>`
    + g.defs
    + '</defs>'
    // sky, from far above the frame down to the horizon
    + `<rect x="${-PAD}" y="${-PAD}" width="${W + 2 * PAD}" height="${HORIZON + PAD}" fill="url(#v-sky)"/>`
    + STARS
    + `<circle cx="${SUN.cx}" cy="${SUN.cy}" r="${SUN.r + 10}" fill="#ff5fa0" opacity=".35" filter="url(#v-glow)"/>`
    + `<circle cx="${SUN.cx}" cy="${SUN.cy}" r="${SUN.r}" fill="url(#v-sun)" mask="url(#v-cut)"/>`
    // floor
    + g.body
    // lettering
    + '<text class="disp" x="320" y="322" font-size="88" text-anchor="middle" fill="#ff3fa4" filter="url(#v-glow)" opacity=".7">RETRO TV</text>'
    + '<text class="disp" x="320" y="322" font-size="88" text-anchor="middle" fill="url(#v-chrome)" stroke="#fff" stroke-width="1.5">RETRO TV</text>'
    + '<g class="blink"><text class="script" x="320" y="408" font-size="58" text-anchor="middle" fill="#8ff2ff" stroke="#e9fcff" stroke-width=".8">please stand by</text></g>'
    + '</svg>';
}

export const SCENES = {
  cable: { svg: cableSvg, fonts: ['700 66px Cabin'] },
  vapor: {
    svg: vaporSvg,
    fonts: ['88px Audiowide', '58px "Mr Dafoe"'],
    // One square per 1.2 s toward the viewer: only the rows move.
    animate(rowPaths, elapsed) {
      const { rows } = gridPaths(HORIZON, { phase: (elapsed / 1200) % 1 });
      for (const path of rowPaths) path.setAttribute('d', rows);
    },
  },
};

export function sceneFor(themeId) {
  return SCENES[themeById(themeId).splash] || SCENES.cable;
}

// ---- Showing it ---------------------------------------------------------------

let fadeTimer = 0, raf = 0;

// Draw the theme's scene over the page and take it down again after `min`
// ms (longer if the fonts are slow). Resolves once it is gone.
export function showSplash(themeId, { min = MIN_MS } = {}) {
  const node = document.getElementById('splash');
  if (!node) return Promise.resolve();
  const scene = sceneFor(themeId);
  clearTimeout(fadeTimer);
  cancelAnimationFrame(raf);

  node.hidden = false;
  node.classList.remove('fade', 'ready');
  node.innerHTML = scene.svg();
  void node.offsetWidth;                // the fade starts from fully shown
  const shown = performance.now();

  // Lettering waits for its fonts, so it never flashes in a fallback face.
  const fonts = scene.fonts.map(f => document.fonts.load(f).catch(() => {}));
  Promise.race([Promise.all(fonts), new Promise(r => setTimeout(r, 900))])
    .then(() => node.classList.add('ready'));

  if (scene.animate && window.matchMedia('(prefers-reduced-motion: no-preference)').matches) {
    const rows = node.querySelectorAll('.gridRows');
    const frame = now => { scene.animate(rows, now - shown); raf = requestAnimationFrame(frame); };
    raf = requestAnimationFrame(frame);
  }

  return new Promise(resolve => {
    fadeTimer = setTimeout(() => {
      node.classList.add('fade');
      fadeTimer = setTimeout(() => {
        cancelAnimationFrame(raf);
        node.hidden = true;
        node.innerHTML = '';
        resolve();
      }, FADE_MS);
    }, min);
  });
}
