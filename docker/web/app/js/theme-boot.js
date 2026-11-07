// Runs in <head>, before the stylesheet paints: puts the saved theme on
// <html>, so a device set to Vaporwave never flashes the Cable colors. The
// settings themselves are read and written by js/settings.js (same key).
(function () {
  try {
    var saved = JSON.parse(localStorage.getItem('retro-tv.settings') || '{}').theme;
    if (saved && /^[a-z]+$/.test(saved)) document.documentElement.dataset.theme = saved;
  } catch (e) { /* private mode or nothing saved: the default theme */ }
})();
