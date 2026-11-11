// Render the viewer's splash scenes (docker/web/app/js/splash.js) to PNG, so
// the Roku app and the Pi box show the very same pictures as the browser:
//
//   roku-tv/images/        icons and start-up splash (Cable), every theme's splash, the tinted icons, the cell shapes
//   pi-image/config/plymouth/retro-tv/   splash-<theme>-{640,720,1080}.png for the boot screen,
//                                        one set per scene in splash.js
//
// Run from this folder after `npm install` and `python fonts.py` (which unpacks
// the viewer's WOFF2 fonts into fonts/ttf/ for the rasterizer, and copies the
// themes' faces into roku-tv/fonts):  node render.mjs
// It ends by running jpg.py (Pillow) on the Roku splashes; PYTHON=... picks the interpreter.
import { Resvg } from '@resvg/resvg-js';
import fs from 'node:fs';
import { spawnSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const repo = path.resolve(here, '../..');
const app = path.join(repo, 'docker/web/app/js');

// The viewer's modules are plain ES modules in a folder without a package.json,
// which Node would read as CommonJS; import them from .mjs copies instead.
for (const f of ['themes', 'splash']) {
  const src = fs.readFileSync(path.join(app, `${f}.js`), 'utf8').replace("'./themes.js'", "'./themes.mjs'");
  fs.writeFileSync(path.join(here, `${f}.mjs`), src);
}
const { SCENES } = await import('./splash.mjs');

const ttfDir = path.join(here, 'fonts/ttf');
if (!fs.existsSync(ttfDir)) {
  console.error('fonts/ttf is missing: run `python fonts.py` here first (it unpacks the viewer fonts).');
  process.exit(1);
}
const fonts = [
  path.join(repo, 'roku-tv/fonts/Cabin-Bold.ttf'),
  path.join(repo, 'roku-tv/fonts/Audiowide-Regular.ttf'),
  path.join(here, 'fonts/MrDafoe-Regular.ttf'),
  path.join(repo, 'docker/web/app/fonts/PrevueGrid.ttf'),
].filter(fs.existsSync);

// The scenes pick fonts by CSS class (the rules are in guide.css under #splash);
// give the rasterizer explicit families and the same default weights. A text's
// own style="font-weight:…" still wins, as in the browser.
const FAMILIES = {
  cabin: ['Cabin', 700], disp: ['Audiowide'], script: ['Mr Dafoe'],
  arimo: ['Arimo', 700], exo: ['Exo 2', 800], nunito: ['Nunito', 900],
  osans: ['Open Sans', 300], lato: ['Lato', 900], archivo: ['Archivo Black'],
  chakra: ['Chakra Petch', 400], pv: ['PrevueGrid'],
};
const withFonts = svg => svg.replace(/class="([a-z]+)"/g, (m, c) => {
  const f = FAMILIES[c];
  if (!f) return m;                       // animation classes (blink, loadbar): nothing to draw
  return `font-family="${f[0]}"` + (f[1] ? ` font-weight="${f[1]}"` : '');
}).replace(/[▲▼] /g, '');       // the DVR scene's triangles: the browser borrows them from a system font, the rasterizer has none

// Re-frame a 640x480 scene for a target size: viewBox of the target's aspect,
// centred on the scene (the scenes draw their backdrop far past the frame).
// stretch=true keeps the 640x480 frame and stretches it (composite's 720x480).
function framed(svg, w, h, vb, stretch = false) {
  const par = stretch ? 'preserveAspectRatio="none"' : '';
  return withFonts(svg).replace(/viewBox="[^"]+" preserveAspectRatio="[^"]+"/, `width="${w}" height="${h}" viewBox="${vb}" ${par}`);
}

function render(svg, out) {
  const r = new Resvg(svg, { fitTo: { mode: 'original' }, font: { fontFiles: fonts, fontDirs: [ttfDir], loadSystemFonts: false, defaultFontFamily: 'Cabin' } });
  const png = r.render();
  fs.mkdirSync(path.dirname(out), { recursive: true });
  fs.writeFileSync(out, png.asPng());
  console.log(path.relative(repo, out), `${png.width}x${png.height}`);
}

const cable = SCENES.cable.svg();
const vapor = SCENES.vapor.svg(0.3);     // the grid a third of a square into its scroll
const roku = p => path.join(repo, 'roku-tv/images', p);
const pi = p => path.join(repo, 'pi-image/config/plymouth/retro-tv', p);

// Roku: icons (Cable television), the two splashes, Vaporwave versions of the small icons.
render(framed(cable, 540, 405, '0 0 640 480'), roku('icon_focus_fhd.png'));
render(framed(cable, 290, 218, '0 -0.55 640 481.1'), roku('icon_focus_hd.png'));
render(framed(cable, 246, 140, '-60 24 760 432.5'), roku('icon_side_fhd.png'));
render(framed(cable, 108, 69, '-20 10 680 434.5'), roku('icon_side_hd.png'));
render(framed(cable, 1920, 1080, '-320 -120 1280 720'), roku('splash_fhd.png'));   // the manifest's start-up picture
// Every theme's splash (MainScene.brs shows splash_<id>_fhd.png; Cable uses the one above).
for (const name of Object.keys(SCENES)) {
  if (name === 'cable') continue;
  const scene = name === 'vapor' ? vapor : SCENES[name].svg();
  render(framed(scene, 1920, 1080, '-320 -120 1280 720'), path.join(here, 'out', `splash_${name}_fhd.png`));
}
// Nine full-HD PNGs would make the Roku zip several megabytes: they go in as JPEG.
const jpg = spawnSync(process.env.PYTHON || 'python3', [path.join(here, 'jpg.py')], { stdio: 'inherit' });
if (jpg.status !== 0) { console.error('jpg.py failed (it needs Pillow: pip install pillow)'); process.exit(1); }

// Small white pictures the Roku app tints with the theme's colours (Poster.blendColor):
// the "playing" triangle and the settings cog, its hole cut out.
render('<svg xmlns="http://www.w3.org/2000/svg" width="18" height="23" viewBox="0 0 8 10"><path d="M0 0 L8 5 L0 10 Z" fill="#fff"/></svg>', roku('tri.png'));
render('<svg xmlns="http://www.w3.org/2000/svg" width="54" height="54" viewBox="0 0 24 24">'
  + '<mask id="hole"><rect width="24" height="24" fill="#fff"/><circle cx="12" cy="12" r="3.5" fill="#000"/></mask><g fill="#fff" mask="url(#hole)">'
  + '<rect x="10" y="1" width="4" height="22"/><rect x="10" y="1" width="4" height="22" transform="rotate(45 12 12)"/>'
  + '<rect x="10" y="1" width="4" height="22" transform="rotate(90 12 12)"/><rect x="10" y="1" width="4" height="22" transform="rotate(135 12 12)"/>'
  + '<circle cx="12" cy="12" r="8"/></g></svg>', roku('cog.png'));

// Cell shapes as 9-patch pictures (a Roku draws only square rectangles): a
// one-pixel border around the picture, black along the top and left edges
// where it may stretch. `inner` draws the picture in a size x size box.
function ninePatch(size, fixed, inner) {
  const n = size + 2, run = size - 2 * fixed;
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${n}" height="${n}" viewBox="0 0 ${n} ${n}" shape-rendering="crispEdges">`
    + `<rect x="${1 + fixed}" y="0" width="${run}" height="1" fill="#000"/><rect x="0" y="${1 + fixed}" width="1" height="${run}" fill="#000"/>`
    + `<g transform="translate(1 1)">${inner}</g></svg>`;
}
// Rounded cells, white shading a little darker toward the bottom (the gloss
// of the rounded themes); the app tints them. Corner radius in screen pixels.
for (const [name, r] of [['s', 10], ['m', 18], ['l', 27]]) {
  const size = 2 * r + 8;
  render(ninePatch(size, r + 1, `<defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff"/><stop offset="1" stop-color="#d2d2d2"/></linearGradient></defs>`
    + `<rect width="${size}" height="${size}" rx="${r}" fill="url(#g)" shape-rendering="geometricPrecision"/>`), roku(`round_${name}.9.png`));
}
// Set-Top Web: a bevel laid over a flat cell, light top and left, dark bottom and right.
render(ninePatch(24, 6, '<path d="M0 0H24V4H4V24H0Z" fill="#fff" fill-opacity=".28"/><path d="M24 24H0L4 20H20V4L24 0Z" fill="#000" fill-opacity=".45"/>'), roku('bevel.9.png'));
// TV Guide: the Amiga frame with its fill (a black line, a light top-left
// edge, a black bottom-right edge), for rows, the time bar and the highlight.
for (const [name, fill, light] of [['row', '#000051', '#aaaaaa'], ['bar', '#263383', '#aaaaaa'], ['sel', '#cbd100', '#f4f7a0']]) {
  render(ninePatch(24, 6, `<rect width="24" height="24" fill="#000"/><rect x="2" y="2" width="20" height="20" fill="${light}"/>`
    + `<rect x="4" y="4" width="18" height="18" fill="#000"/><rect x="4" y="4" width="16" height="16" fill="${fill}"/>`), roku(`prevue_${name}.9.png`));
}

// Pi boot splash: every scene at the three screen sizes the box can have.
for (const name of Object.keys(SCENES)) {
  const scene = name === 'vapor' ? vapor : SCENES[name].svg();
  render(framed(scene, 640, 480, '0 0 640 480'), pi(`splash-${name}-640.png`));
  render(framed(scene, 720, 480, '0 0 640 480', true), pi(`splash-${name}-720.png`));
  render(framed(scene, 1920, 1080, '-320 -120 1280 720'), pi(`splash-${name}-1080.png`));
}
