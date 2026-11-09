// Render the viewer's splash scenes (docker/web/app/js/splash.js) to PNG, so
// the Roku app and the Pi box show the very same pictures as the browser:
//
//   roku-tv/images/        icons and splash (Cable), splash_vapor_fhd.png, Vaporwave icons
//   pi-image/config/plymouth/retro-tv/   splash-<theme>-{640,720,1080}.png for the boot screen,
//                                        one set per scene in splash.js
//
// Run from this folder after `npm install` and `python fonts.py` (which unpacks
// the viewer's WOFF2 fonts into fonts/ttf/ for the rasterizer):  node render.mjs
import { Resvg } from '@resvg/resvg-js';
import fs from 'node:fs';
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
].filter(fs.existsSync);

// The scenes pick fonts by CSS class (the rules are in guide.css under #splash);
// give the rasterizer explicit families and the same default weights. A text's
// own style="font-weight:…" still wins, as in the browser.
const FAMILIES = {
  cabin: ['Cabin', 700], disp: ['Audiowide'], script: ['Mr Dafoe'],
  arimo: ['Arimo', 700], exo: ['Exo 2', 800], nunito: ['Nunito', 900],
  osans: ['Open Sans', 300], lato: ['Lato', 900], archivo: ['Archivo Black'],
  chakra: ['Chakra Petch', 400], vt: ['VT323'],
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
render(framed(cable, 1920, 1080, '-320 -120 1280 720'), roku('splash_fhd.png'));
render(framed(vapor, 1920, 1080, '-320 -120 1280 720'), roku('splash_vapor_fhd.png'));
const tri = c => `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="23" viewBox="0 0 8 10"><path d="M0 0 L8 5 L0 10 Z" fill="${c}"/></svg>`;
const cog = (c, hole) => `<svg xmlns="http://www.w3.org/2000/svg" width="54" height="54" viewBox="0 0 24 24"><g fill="${c}">`
  + '<rect x="10" y="1" width="4" height="22"/><rect x="10" y="1" width="4" height="22" transform="rotate(45 12 12)"/>'
  + '<rect x="10" y="1" width="4" height="22" transform="rotate(90 12 12)"/><rect x="10" y="1" width="4" height="22" transform="rotate(135 12 12)"/>'
  + `<circle cx="12" cy="12" r="8"/></g><circle cx="12" cy="12" r="3.5" fill="${hole}"/></svg>`;
render(tri('#ff3fa4'), roku('playing_vapor.png'));
render(tri('#0d0624'), roku('playing_sel_vapor.png'));
render(cog('#d9c8ff', '#0d0624'), roku('cog_vapor.png'));
render(cog('#19e6ff', '#0d0624'), roku('cog_sel_vapor.png'));

// Pi boot splash: every scene at the three screen sizes the box can have.
for (const name of Object.keys(SCENES)) {
  const scene = name === 'vapor' ? vapor : SCENES[name].svg();
  render(framed(scene, 640, 480, '0 0 640 480'), pi(`splash-${name}-640.png`));
  render(framed(scene, 720, 480, '0 0 640 480', true), pi(`splash-${name}-720.png`));
  render(framed(scene, 1920, 1080, '-320 -120 1280 720'), pi(`splash-${name}-1080.png`));
}
