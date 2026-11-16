// Server settings: /config.json, written when the server starts from its
// environment (docker/web/config.envsh and the pieces in config.d/). One
// request, shared by every feature that has a setting there. A missing or
// broken file reads as {}, so each feature falls back to its default.

let pending = null;

export function serverConfig() {
  if (!pending) {
    pending = fetch('/config.json', { cache: 'no-store' })
      .then(r => (r.ok ? r.json() : {}))
      .then(c => (c && typeof c === 'object' && !Array.isArray(c) ? c : {}))
      .catch(() => ({}));
  }
  return pending;
}

// One key of it, or undefined.
export function serverSetting(key) {
  return serverConfig().then(c => c[key]);
}
