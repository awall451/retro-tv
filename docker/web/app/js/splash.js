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
      // glow pass: the columns are blurred once; the rows, which move, get a plain wide stroke (cheap to redraw)
      + `<g fill="none" stroke="${color}" stroke-width="4" opacity=".5"><path class="gridRows" d="${rows}"/><path d="${cols}" filter="url(#${p}-soft)"/></g>`
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

// Every gradient is measured in scene units (userSpaceOnUse), never against
// an element's own box: browsers size a text's box differently, which would
// move the chrome's horizon line. The sun's bands are strips of sky painted
// over it through a clip, not a mask, for the same reason.
function vaporSvg(phase = 0) {
  const g = gridSvg('vg', HORIZON, '#0c0426', '#19e6ff', '#8ff2ff', { phase });
  const capTop = 322 - 63;   // the lettering's cap height at 88 px, above its baseline
  return open
    + '<defs>'
    + `<linearGradient id="v-sky" gradientUnits="userSpaceOnUse" x1="0" y1="${-PAD}" x2="0" y2="${HORIZON}"><stop offset="0" stop-color="#05020f"/><stop offset=".55" stop-color="#2a0a4e"/><stop offset="1" stop-color="#7a1a6e"/></linearGradient>`
    + `<linearGradient id="v-sun" gradientUnits="userSpaceOnUse" x1="0" y1="${SUN.cy - SUN.r}" x2="0" y2="${SUN.cy + SUN.r}"><stop offset="0" stop-color="#ffe26a"/><stop offset=".5" stop-color="#ff6f9c"/><stop offset="1" stop-color="#c0109a"/></linearGradient>`
    + `<linearGradient id="v-chrome" gradientUnits="userSpaceOnUse" x1="0" y1="${capTop}" x2="0" y2="322"><stop offset="0" stop-color="#f4fbff"/><stop offset=".3" stop-color="#9fd3ff"/><stop offset=".49" stop-color="#3f6ea6"/><stop offset=".51" stop-color="#160a2c"/><stop offset=".72" stop-color="#6a3aa6"/><stop offset="1" stop-color="#f6e8ff"/></linearGradient>`
    + '<filter id="v-glow" x="-20%" y="-60%" width="140%" height="220%"><feGaussianBlur stdDeviation="7"/></filter>'
    + `<clipPath id="v-sunclip"><circle cx="${SUN.cx}" cy="${SUN.cy}" r="${SUN.r}"/></clipPath>`
    + g.defs
    + '</defs>'
    // sky, from far above the frame down to the horizon
    + `<rect x="${-PAD}" y="${-PAD}" width="${W + 2 * PAD}" height="${HORIZON + PAD}" fill="url(#v-sky)"/>`
    + STARS
    + `<circle cx="${SUN.cx}" cy="${SUN.cy}" r="${SUN.r + 10}" fill="#ff5fa0" fill-opacity=".35" filter="url(#v-glow)"/>`
    + `<circle cx="${SUN.cx}" cy="${SUN.cy}" r="${SUN.r}" fill="url(#v-sun)"/>`
    + `<g clip-path="url(#v-sunclip)" fill="url(#v-sky)">${sunCuts()}</g>`
    // floor
    + g.body
    // lettering
    + '<text class="disp" x="320" y="322" font-size="88" text-anchor="middle" fill="#ff3fa4" fill-opacity=".7" filter="url(#v-glow)">RETRO TV</text>'
    + '<text class="disp" x="320" y="322" font-size="88" text-anchor="middle" fill="url(#v-chrome)" stroke="#fff" stroke-width="1.5">RETRO TV</text>'
    + '<g class="blink"><text class="script" x="320" y="408" font-size="58" text-anchor="middle" fill="#8ff2ff" stroke="#e9fcff" stroke-width=".8">please stand by</text></g>'
    + '</svg>';
}


// ---- The 2026-11 themes ----------------------------------------------------------
// Looks from the digital-cable, satellite and set-top era, drawn the same
// way: SVG in 640x480 units, the backdrop running past the frame. No real
// logos or names; each is "in the style of".
const back = fill => `<rect x="${-PAD}" y="${-PAD}" width="${W + 2 * PAD}" height="${H + 2 * PAD}" fill="${fill}"/>`;

// Digital Cable: a glowing blue orb over glossy swooshes, a loading bar.
function digitalSvg() {
  return open
    + '<defs>'
    + `<radialGradient id="dc-bg" gradientUnits="userSpaceOnUse" cx="460" cy="190" r="620"><stop offset="0" stop-color="#12357a"/><stop offset=".45" stop-color="#071a45"/><stop offset="1" stop-color="#000208"/></radialGradient>`
    + '<radialGradient id="dc-orb" cx=".35" cy=".3" r=".75"><stop offset="0" stop-color="#ffffff"/><stop offset=".18" stop-color="#9fd4ff"/><stop offset=".5" stop-color="#2f86e8"/><stop offset=".9" stop-color="#0b3a8c"/></radialGradient>'
    + '<linearGradient id="dc-sw" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#78beff" stop-opacity=".55"/><stop offset=".5" stop-color="#286edc" stop-opacity=".25"/><stop offset="1" stop-color="#0a2878" stop-opacity="0"/></linearGradient>'
    + '<linearGradient id="dc-shine" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".75"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>'
    + '<linearGradient id="dc-bar" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#bfe3ff"/><stop offset=".5" stop-color="#4aa3ff"/><stop offset="1" stop-color="#1764d6"/></linearGradient>'
    + '<filter id="dc-glow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="18"/></filter>'
    + '</defs>'
    + back('url(#dc-bg)')
    + '<rect x="-300" y="300" width="1300" height="70" rx="35" fill="url(#dc-sw)" transform="rotate(-9 320 330)"/>'
    + '<rect x="-300" y="350" width="1300" height="30" rx="15" fill="url(#dc-sw)" transform="rotate(-7 320 360)"/>'
    + '<circle cx="480" cy="160" r="86" fill="#3f9cff" opacity=".5" filter="url(#dc-glow)"/>'
    + '<circle cx="480" cy="160" r="80" fill="url(#dc-orb)"/>'
    + '<ellipse cx="465" cy="112" rx="46" ry="24" fill="url(#dc-shine)"/>'
    + '<text class="arimo" x="48" y="118" font-size="13" letter-spacing="5" fill="#8fc8ff">DIGITAL CABLE</text>'
    + '<text class="arimo" x="46" y="176" font-size="54" fill="#fff">Retro TV</text>'
    + '<text class="arimo" x="48" y="206" font-size="15" fill="#cfe6ff" style="font-weight:400">On Demand · Guide · Music</text>'
    + '<text class="arimo" x="48" y="392" font-size="13" fill="#cfe6ff" style="font-weight:400">Loading your channel guide…</text>'
    + '<rect x="48" y="404" width="240" height="12" rx="6" fill="#051231"/>'
    + '<rect class="loadbar" x="48" y="404" width="150" height="12" rx="6" fill="url(#dc-bar)"/>'
    + '</svg>';
}

// Satellite: a starfield, the curve of the planet, a dish in orbit, signal bars.
function satelliteSvg() {
  return open
    + '<defs>'
    + `<radialGradient id="sa-bg" gradientUnits="userSpaceOnUse" cx="200" cy="560" r="760"><stop offset="0" stop-color="#3a1a6e"/><stop offset=".4" stop-color="#160a3a"/><stop offset="1" stop-color="#05041a"/></radialGradient>`
    + '<radialGradient id="sa-planet" gradientUnits="userSpaceOnUse" cx="320" cy="400" r="420"><stop offset="0" stop-color="#4b7be8"/><stop offset=".22" stop-color="#1d3a8f"/><stop offset=".5" stop-color="#0a1544"/><stop offset="1" stop-color="#05041a"/></radialGradient>'
    + '<linearGradient id="sa-type" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ffffff"/><stop offset=".55" stop-color="#dfe6ff"/><stop offset="1" stop-color="#9fb2ff"/></linearGradient>'
    + '<radialGradient id="sa-dish" cx=".35" cy=".35" r=".7"><stop offset="0" stop-color="#ffffff"/><stop offset=".3" stop-color="#d9d9e6"/><stop offset="1" stop-color="#7d8299"/></radialGradient>'
    + '<filter id="sa-glow" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="10"/></filter>'
    + '</defs>'
    + back('url(#sa-bg)') + STARS
    + '<ellipse cx="320" cy="760" rx="760" ry="380" fill="#6e96ff" opacity=".5" filter="url(#sa-glow)"/>'
    + '<ellipse cx="320" cy="760" rx="760" ry="380" fill="url(#sa-planet)"/>'
    + '<ellipse cx="470" cy="170" rx="170" ry="58" fill="none" stroke="#ffce5c" stroke-opacity=".35" stroke-width="2" transform="rotate(-20 470 170)"/>'
    + '<ellipse cx="520" cy="130" rx="24" ry="40" fill="url(#sa-dish)" transform="rotate(-30 520 130)"/>'
    + '<path d="M522 132 L548 168" stroke="#9aa0b8" stroke-width="5"/>'
    + '<text class="exo" x="48" y="110" font-size="12" letter-spacing="6" fill="#ffce5c">SATELLITE · 500 CHANNELS</text>'
    + '<text class="exo" x="44" y="172" font-size="60" fill="url(#sa-type)" font-style="italic">Retro TV</text>'
    + '<text class="exo" x="48" y="204" font-size="15" fill="#c9cff5" style="font-weight:400">Acquiring signal from orbit…</text>'
    + '<g fill="#ffce5c"><rect x="48" y="410" width="9" height="10" rx="2"/><rect x="62" y="402" width="9" height="18" rx="2"/><rect x="76" y="394" width="9" height="26" rx="2"/><rect x="90" y="386" width="9" height="34" rx="2"/><rect x="104" y="378" width="9" height="42" rx="2" opacity=".3"/></g>'
    + '<text class="exo" x="124" y="418" font-size="12" fill="#ffce5c" style="font-weight:400">Signal strength 82</text>'
    + '</svg>';
}

// DVR: a friendly round television with a face, thumbs up and down.
function dvrSvg() {
  return open
    + '<defs>'
    + `<radialGradient id="dv-bg" gradientUnits="userSpaceOnUse" cx="380" cy="220" r="560"><stop offset="0" stop-color="#4f8fe0"/><stop offset=".45" stop-color="#2a5fb8"/><stop offset="1" stop-color="#173a80"/></radialGradient>`
    + '<linearGradient id="dv-body" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ffffff"/><stop offset="1" stop-color="#dfe8f7"/></linearGradient>'
    + '<linearGradient id="dv-scr" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#23314f"/><stop offset="1" stop-color="#0f1830"/></linearGradient>'
    + '</defs>'
    + back('url(#dv-bg)')
    + '<path d="M445 120 L420 68 M515 120 L540 68" stroke="#e9eef8" stroke-width="6" stroke-linecap="round"/>'
    + '<circle cx="418" cy="62" r="11" fill="#ffd54a"/><circle cx="542" cy="62" r="11" fill="#7ed957"/>'
    + '<rect x="380" y="128" width="200" height="160" rx="60" fill="#12306a" transform="translate(0 10)"/>'
    + '<rect x="380" y="128" width="200" height="160" rx="60" fill="url(#dv-body)"/>'
    + '<rect x="405" y="152" width="150" height="100" rx="40" fill="url(#dv-scr)"/>'
    + '<ellipse cx="452" cy="190" rx="9" ry="13" fill="#fff"/><ellipse cx="508" cy="190" rx="9" ry="13" fill="#fff"/>'
    + '<path d="M458 214 h44 a22 20 0 0 1 -44 0z" fill="#ff7a7a"/>'
    + '<rect x="405" y="290" width="28" height="26" rx="10" fill="#dfe8f7"/><rect x="527" y="290" width="28" height="26" rx="10" fill="#dfe8f7"/>'
    + '<text class="nunito" x="42" y="170" font-size="62" fill="#12306a" transform="translate(0 4)">Retro TV</text>'
    + '<text class="nunito" x="42" y="170" font-size="62" fill="#ffffff">Retro TV</text>'
    + '<text class="nunito" x="44" y="206" font-size="19" fill="#ffd54a" style="font-weight:800">Your shows. Whenever.</text>'
    + '<rect x="44" y="370" width="150" height="40" rx="20" fill="#3a8a2a" transform="translate(0 4)"/><rect x="44" y="370" width="150" height="40" rx="20" fill="#7ed957"/>'
    + '<text class="nunito" x="119" y="396" font-size="16" fill="#134d12" text-anchor="middle">▲ Thumbs up</text>'
    + '<rect x="206" y="370" width="170" height="40" rx="20" fill="#b84040" transform="translate(0 4)"/><rect x="206" y="370" width="170" height="40" rx="20" fill="#ff7a7a"/>'
    + '<text class="nunito" x="291" y="396" font-size="16" fill="#5e1212" text-anchor="middle">▼ Thumbs down</text>'
    + '</svg>';
}

// Media Center: a green glowing play button and a glassy menu.
function mediacenterSvg() {
  return open
    + '<defs>'
    + `<linearGradient id="mc-bg" gradientUnits="userSpaceOnUse" x1="0" y1="${-PAD}" x2="${W}" y2="${H + PAD}"><stop offset="0" stop-color="#0d4f8f"/><stop offset=".45" stop-color="#08356a"/><stop offset="1" stop-color="#031a3a"/></linearGradient>`
    + '<radialGradient id="mc-orb" cx=".4" cy=".32" r=".7"><stop offset="0" stop-color="#e9ffe0"/><stop offset=".25" stop-color="#7be05a"/><stop offset=".6" stop-color="#2f9d2a"/><stop offset="1" stop-color="#155d14"/></radialGradient>'
    + '<linearGradient id="mc-pill" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#8fe06a"/><stop offset=".5" stop-color="#3fae32"/><stop offset=".51" stop-color="#2a8f22"/><stop offset="1" stop-color="#2f9d2a"/></linearGradient>'
    + '<linearGradient id="mc-shine" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".85"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>'
    + '<radialGradient id="mc-haze" gradientUnits="userSpaceOnUse" cx="160" cy="-60" r="420"><stop offset="0" stop-color="#78c8ff" stop-opacity=".35"/><stop offset="1" stop-color="#78c8ff" stop-opacity="0"/></radialGradient>'
    + '<filter id="mc-glow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="14"/></filter>'
    + '</defs>'
    + back('url(#mc-bg)') + back('url(#mc-haze)')
    + '<circle cx="104" cy="120" r="56" fill="#7be05a" opacity=".6" filter="url(#mc-glow)"/>'
    + '<circle cx="104" cy="120" r="52" fill="url(#mc-orb)" stroke="#fff" stroke-opacity=".85" stroke-width="4"/>'
    + '<ellipse cx="98" cy="88" rx="30" ry="15" fill="url(#mc-shine)"/>'
    + '<path d="M92 98 L124 120 L92 142 Z" fill="#fff"/>'
    + '<text class="osans" x="180" y="128" font-size="50" fill="#fff">Retro TV</text>'
    + '<text class="osans" x="182" y="154" font-size="16" fill="#b7e0ff" style="font-weight:400">media center edition</text>'
    + '<text class="osans" x="196" y="236" font-size="20" fill="#b7e0ff">Recorded TV</text>'
    + '<rect x="180" y="252" width="250" height="38" rx="19" fill="#7be05a" opacity=".5" filter="url(#mc-glow)"/>'
    + '<rect x="180" y="252" width="250" height="38" rx="19" fill="url(#mc-pill)"/>'
    + '<text class="osans" x="196" y="278" font-size="20" fill="#fff" style="font-weight:600">Live TV</text>'
    + '<text class="osans" x="196" y="320" font-size="20" fill="#b7e0ff">Guide</text>'
    + '<text class="osans" x="196" y="360" font-size="20" fill="#7fa9d0">Settings</text>'
    + '</svg>';
}

// Aqua: pinstripes, a brushed title bar with three gel buttons, a gel icon.
function aquaSvg() {
  return open
    + '<defs>'
    + '<pattern id="aq-stripe" patternUnits="userSpaceOnUse" width="4" height="4"><rect width="4" height="2" fill="#eef1f5"/><rect y="2" width="4" height="2" fill="#e3e7ec"/></pattern>'
    + `<linearGradient id="aq-bar" gradientUnits="userSpaceOnUse" x1="0" y1="${-PAD}" x2="0" y2="36"><stop offset="0" stop-color="#e9ebee"/><stop offset=".9" stop-color="#c9ced5"/><stop offset=".95" stop-color="#b9bfc8"/><stop offset="1" stop-color="#cfd4da"/></linearGradient>`
    + '<linearGradient id="aq-icon" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#6fd6ff"/><stop offset=".45" stop-color="#18a7e8"/><stop offset="1" stop-color="#0a6fb0"/></linearGradient>'
    + '<linearGradient id="aq-shine" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".85"/><stop offset="1" stop-color="#fff" stop-opacity=".05"/></linearGradient>'
    + '<linearGradient id="aq-gel" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#d8f1ff"/><stop offset=".45" stop-color="#6cc4ff"/><stop offset=".5" stop-color="#2a95ef"/><stop offset="1" stop-color="#7fd0ff"/></linearGradient>'
    + '<radialGradient id="aq-r" cx=".35" cy=".3" r=".7"><stop offset="0" stop-color="#ffd0c8"/><stop offset=".4" stop-color="#ff5f4f"/><stop offset="1" stop-color="#c0261a"/></radialGradient>'
    + '<radialGradient id="aq-y" cx=".35" cy=".3" r=".7"><stop offset="0" stop-color="#fff1c2"/><stop offset=".4" stop-color="#ffbf2f"/><stop offset="1" stop-color="#c08414"/></radialGradient>'
    + '<radialGradient id="aq-g" cx=".35" cy=".3" r=".7"><stop offset="0" stop-color="#d6ffd0"/><stop offset=".4" stop-color="#43c93a"/><stop offset="1" stop-color="#23801c"/></radialGradient>'
    + '<filter id="aq-sh" x="-30%" y="-30%" width="160%" height="170%"><feDropShadow dx="0" dy="12" stdDeviation="12" flood-color="#0a3c6e" flood-opacity=".35"/></filter>'
    + '</defs>'
    + back('url(#aq-stripe)')
    + `<rect x="${-PAD}" y="${-PAD}" width="${W + 2 * PAD}" height="${PAD + 36}" fill="url(#aq-bar)"/>`
    + `<rect x="${-PAD}" y="35" width="${W + 2 * PAD}" height="1" fill="#8f96a0"/>`
    + '<circle cx="20" cy="18" r="6" fill="url(#aq-r)"/><circle cx="38" cy="18" r="6" fill="url(#aq-y)"/><circle cx="56" cy="18" r="6" fill="url(#aq-g)"/>'
    + '<text class="lato" x="320" y="23" font-size="13" fill="#3a4350" text-anchor="middle" style="font-weight:700">Retro TV</text>'
    + '<g filter="url(#aq-sh)"><rect x="56" y="110" width="190" height="190" rx="40" fill="url(#aq-icon)"/></g>'
    + '<path d="M74 140 a32 32 0 0 1 32 -14 h90 a32 32 0 0 1 32 14 v40 a90 40 0 0 1 -154 0z" fill="url(#aq-shine)"/>'
    + '<rect x="114" y="186" width="74" height="56" rx="12" fill="#00284f" fill-opacity=".35" stroke="#fff" stroke-opacity=".85" stroke-width="3"/>'
    + '<text class="lato" x="280" y="200" font-size="54" fill="#1d2a3a">Retro TV</text>'
    + '<text class="lato" x="282" y="232" font-size="17" fill="#4c5868" style="font-weight:400">Now in five flavors.</text>'
    + '<rect x="282" y="262" width="110" height="34" rx="17" fill="url(#aq-gel)" stroke="#2b6fb0"/>'
    + '<text class="lato" x="337" y="284" font-size="15" fill="#04305a" text-anchor="middle" style="font-weight:700">Watch</text>'
    + '</svg>';
}

// Set-Top Web: a golden orb in a purple sunburst, "connecting", bevelled blocks.
function settopSvg() {
  let rays = '';
  for (let a = 0; a < 360; a += 30) rays += `<path d="M320 200 L${(320 + 700 * Math.cos(a * Math.PI / 180)).toFixed(1)} ${(200 + 700 * Math.sin(a * Math.PI / 180)).toFixed(1)} L${(320 + 700 * Math.cos((a + 12) * Math.PI / 180)).toFixed(1)} ${(200 + 700 * Math.sin((a + 12) * Math.PI / 180)).toFixed(1)}Z"/>`;
  let blocks = '';
  for (let i = 0; i < 5; i++) {
    const on = i < 3, x = 186 + i * 56;
    blocks += `<rect x="${x}" y="350" width="50" height="22" fill="${on ? '#ffbe3c' : '#3a2468'}"/>`
      + `<path d="M${x} 372V350H${x + 50}" fill="none" stroke="${on ? '#ffe7a8' : '#1a0c38'}" stroke-width="3"/>`
      + `<path d="M${x + 50} 350V372H${x}" fill="none" stroke="${on ? '#8a4a00' : '#6a4aa8'}" stroke-width="3"/>`;
  }
  return open
    + '<defs>'
    + `<radialGradient id="st-bg" gradientUnits="userSpaceOnUse" cx="320" cy="190" r="560"><stop offset="0" stop-color="#3d1f6e"/><stop offset=".5" stop-color="#1c0c38"/><stop offset="1" stop-color="#07020f"/></radialGradient>`
    + '<radialGradient id="st-orb" cx=".4" cy=".35" r=".7"><stop offset="0" stop-color="#fff4cc"/><stop offset=".35" stop-color="#ffbe3c"/><stop offset="1" stop-color="#c46a00"/></radialGradient>'
    + '<radialGradient id="st-rayfade" gradientUnits="userSpaceOnUse" cx="320" cy="200" r="380"><stop offset="0" stop-color="#ffbe3c" stop-opacity=".35"/><stop offset="1" stop-color="#b478ff" stop-opacity="0"/></radialGradient>'
    + '<filter id="st-glow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="16"/></filter>'
    + '</defs>'
    + back('url(#st-bg)')
    + `<g fill="url(#st-rayfade)">${rays}</g>`
    + '<circle cx="320" cy="200" r="58" fill="#ffbe3c" opacity=".6" filter="url(#st-glow)"/>'
    + '<circle cx="320" cy="200" r="52" fill="url(#st-orb)"/>'
    + '<text class="archivo" x="323" y="93" font-size="52" letter-spacing="2" fill="#5a2a9a" text-anchor="middle">RETRO TV</text>'
    + '<text class="archivo" x="320" y="90" font-size="52" letter-spacing="2" fill="#ffbe3c" text-anchor="middle">RETRO TV</text>'
    + '<text class="chakra" x="320" y="326" font-size="18" fill="#d9c8ff" text-anchor="middle">Connecting to the network…</text>'
    + blocks
    + '<text class="chakra" x="320" y="452" font-size="12" fill="#8f7bc0" text-anchor="middle">Dialing 56k · Please wait</text>'
    + '</svg>';
}

// Listings Channel: a promo up top, the red bar, the listings grid below.
function listingsSvg() {
  const rows = [['37 MCU', [['Iron Man', 2], ['Iron Man 2', 1]]], ['39 SCI-FI', [['Stargate SG-1', 2], ['Fringe', 1]]],
    ['42 SPEED', [['Initial D', 1], ['MF Ghost', 1], ['Dirt Every Day', 1]]], ['44 MARATHON', [['The Terminator', 3]]],
    ['46 DISCOVERY', [['Planet Earth', 2], ['Mail Call', 1]]]];
  let grid = '', y = 260;
  for (const [ch, cells] of rows) {
    grid += `<rect x="${-PAD}" y="${y}" width="${PAD + 120}" height="34" fill="#3d5fd1"/><text class="vt" x="8" y="${y + 24}" font-size="22" fill="#fff">${ch}</text>`;
    let x = 122;
    for (const [t, span] of cells) {
      const w = span * 172 - 2 + (x + span * 172 >= 638 ? PAD : 0);
      grid += `<rect x="${x}" y="${y}" width="${w}" height="34" fill="#1c2e8a"/><text class="vt" x="${x + 8}" y="${y + 24}" font-size="22" fill="#fff">${t.toUpperCase()}</text>`;
      x += span * 172;
    }
    y += 36;
  }
  return open
    + '<defs><linearGradient id="ls-top" gradientUnits="userSpaceOnUse" x1="0" y1="-420" x2="0" y2="226"><stop offset="0" stop-color="#2a2a2a"/><stop offset="1" stop-color="#0a0a0a"/></linearGradient></defs>'
    + back('#000')
    + `<rect x="${-PAD}" y="${-PAD}" width="${W + 2 * PAD}" height="${PAD + 226}" fill="url(#ls-top)"/>`
    + '<text class="vt" x="324" y="104" font-size="72" letter-spacing="4" fill="#b3001b" text-anchor="middle">RETRO TV</text>'
    + '<text class="vt" x="320" y="100" font-size="72" letter-spacing="4" fill="#ffe14d" text-anchor="middle">RETRO TV</text>'
    + '<text class="vt" x="320" y="140" font-size="28" letter-spacing="3" fill="#fff" text-anchor="middle">THE ALL-LISTINGS CHANNEL</text>'
    + '<text class="vt" x="320" y="172" font-size="21" fill="#9fd0ff" text-anchor="middle">Stay tuned for local weather</text>'
    + `<rect x="${-PAD}" y="228" width="${W + 2 * PAD}" height="30" fill="#b3001b"/>`
    + '<text class="vt" x="10" y="250" font-size="22" fill="#fff">SUNDAY 8:00 PM      SCROLLING LISTINGS      CH 1-57</text>'
    + grid
    + '</svg>';
}

export const SCENES = {
  cable: { svg: cableSvg, fonts: ['700 66px Cabin'] },
  digital: { svg: digitalSvg, fonts: ['700 54px Arimo', '400 15px Arimo'] },
  satellite: { svg: satelliteSvg, fonts: ['800 60px "Exo 2"', '400 15px "Exo 2"'] },
  dvr: { svg: dvrSvg, fonts: ['900 62px Nunito', '800 19px Nunito'] },
  mediacenter: { svg: mediacenterSvg, fonts: ['300 50px "Open Sans"', '400 16px "Open Sans"', '600 20px "Open Sans"'] },
  aqua: { svg: aquaSvg, fonts: ['900 54px Lato', '400 17px Lato', '700 15px Lato'] },
  settop: { svg: settopSvg, fonts: ['52px "Archivo Black"', '18px "Chakra Petch"'] },
  listings: { svg: listingsSvg, fonts: ['72px VT323'] },
  vapor: {
    svg: vaporSvg,
    fonts: ['88px Audiowide', '58px "Mr Dafoe"'],
    // One square per 1.2 s toward the viewer: only the rows move, at 30 fps.
    animate(rowPaths, elapsed) {
      const step = Math.floor(elapsed / 33);
      if (step === this.lastStep) return;
      this.lastStep = step;
      const { rows } = gridPaths(HORIZON, { phase: (elapsed / 1200) % 1 });
      for (const path of rowPaths) path.setAttribute('d', rows);
    },
  },
};

export function sceneFor(themeId) {
  return SCENES[themeById(themeId).splash] || SCENES.cable;
}

// ---- Showing it ---------------------------------------------------------------

let fadeTimer = 0, raf = 0, showing = false;

// True while a splash covers the page; input is ignored meanwhile (app.js).
export const isSplashShowing = () => showing;

// Draw the theme's scene over the page and take it down again after `min`
// ms. The lettering waits for its fonts first, up to 0.9 s, so it never
// flashes in a fallback face. Resolves once the splash is gone.
export function showSplash(themeId, { min = MIN_MS } = {}) {
  const node = document.getElementById('splash');
  if (!node) return Promise.resolve();
  const scene = sceneFor(themeId);
  clearTimeout(fadeTimer);
  cancelAnimationFrame(raf);

  showing = true;
  node.hidden = false;
  node.classList.add('js');             // this script is in charge now: no CSS safety fade
  node.classList.remove('fade', 'ready');
  node.innerHTML = scene.svg();
  void node.offsetWidth;                // the fade starts from fully shown
  const shown = performance.now();

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
        showing = false;
        resolve();
      }, FADE_MS);
    }, min);
  });
}
